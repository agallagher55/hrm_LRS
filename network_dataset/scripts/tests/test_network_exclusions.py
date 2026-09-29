"""
Tests for network_exclusions.py. They need no ArcGIS: the clause builders are pure,
and make_filtered_layer is exercised against a fake arcpy.

Run from network_dataset/scripts:
  > python -m unittest discover -s tests -v
"""

import logging
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import network_exclusions as ne


def profile(str_types=(), fdmids=(), name_patterns=()):
    return {
        "str_types": list(str_types),
        "fdmids": list(fdmids),
        "name_patterns": list(name_patterns),
    }


class ListHandler(logging.Handler):
    """Collect log records so tests can assert on warnings."""

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def messages(self, level):
        return [r.getMessage() for r in self.records if r.levelno == level]


def fake_arcpy(counts):
    """
    Build a stand-in for arcpy. counts maps a where clause (None for the whole
    source) to the row count a layer with that clause reports.
    """
    layers = {}

    def make_feature_layer(source, name, where_clause=None):
        layers[name] = where_clause

        return [name]

    def get_count(layer_or_fc):
        where_clause = layers.get(layer_or_fc)

        return [counts[where_clause]]

    management = types.SimpleNamespace(
        MakeFeatureLayer=make_feature_layer,
        GetCount=get_count,
        Delete=lambda layer: None,
    )

    return types.SimpleNamespace(management=management)


class ClauseTests(unittest.TestCase):

    def test_general_matches_the_original_wa_clauses(self):
        self.assertEqual(ne.build_exclude_clause("GENERAL"), "STR_TYPE IN ('WA')")
        self.assertEqual(
            ne.build_keep_clause("GENERAL"),
            "(STR_TYPE IS NULL OR STR_TYPE NOT IN ('WA'))",
        )

    def test_default_profile_is_general(self):
        self.assertEqual(ne.DEFAULT_PROFILE, "GENERAL")
        self.assertEqual(ne.build_keep_clause(), ne.build_keep_clause("GENERAL"))

    def test_hrfe_includes_general_and_emergency_access(self):
        exclude = ne.build_exclude_clause("HRFE")

        self.assertIn("STR_TYPE IN ('WA')", exclude)
        self.assertIn("FULL_NAME LIKE '%EMERGENCY ACCESS%'", exclude)

    def test_general_does_not_pick_up_hrfe_rules(self):
        self.assertNotIn("EMERGENCY", ne.build_exclude_clause("GENERAL"))

    def test_hrfe_keep_clause_is_null_safe_for_every_rule(self):
        keep = ne.build_keep_clause("HRFE")

        self.assertIn("(STR_TYPE IS NULL OR STR_TYPE NOT IN ('WA'))", keep)
        self.assertIn("(FULL_NAME IS NULL OR FULL_NAME NOT LIKE '%EMERGENCY ACCESS%')", keep)
        self.assertEqual(keep.count(" AND "), 1)

    def test_unknown_profile_raises(self):
        with self.assertRaises(ValueError):
            ne.build_keep_clause("NOPE")

    def test_empty_profile_gives_no_clauses(self):
        with mock.patch.dict(ne.PROFILES, {"EMPTY": profile()}):
            self.assertIsNone(ne.build_exclude_clause("EMPTY"))
            self.assertIsNone(ne.build_keep_clause("EMPTY"))
            self.assertEqual(ne.get_rules("EMPTY"), [])

    def test_fdmid_rule(self):
        with mock.patch.dict(ne.PROFILES, {"P": profile(fdmids=[10, "20"])}):
            self.assertEqual(ne.build_exclude_clause("P"), "FDMID IN (10, 20)")
            self.assertEqual(
                ne.build_keep_clause("P"),
                "(FDMID IS NULL OR FDMID NOT IN (10, 20))",
            )

    def test_fdmid_rejects_non_numbers(self):
        with mock.patch.dict(ne.PROFILES, {"P": profile(fdmids=["1; DROP TABLE x"])}):
            with self.assertRaises(ValueError):
                ne.build_exclude_clause("P")

    def test_quotes_are_escaped(self):
        with mock.patch.dict(ne.PROFILES, {"P": profile(name_patterns=["%O'BRIEN%"])}):
            self.assertEqual(ne.build_exclude_clause("P"), "FULL_NAME LIKE '%O''BRIEN%'")

    def test_each_name_pattern_is_its_own_rule(self):
        with mock.patch.dict(ne.PROFILES, {"P": profile(name_patterns=["TA[0-9]%", "%X%"])}):
            self.assertEqual(len(ne.get_rules("P")), 2)
            self.assertEqual(
                ne.build_exclude_clause("P"),
                "FULL_NAME LIKE 'TA[0-9]%' OR FULL_NAME LIKE '%X%'",
            )

    def test_merge_drops_repeated_values_and_keeps_order(self):
        merged = ne._merge(
            profile(str_types=["WA"], name_patterns=["A"]),
            profile(str_types=["WA", "XX"], name_patterns=["B", "A"]),
        )

        self.assertEqual(merged["str_types"], ["WA", "XX"])
        self.assertEqual(merged["name_patterns"], ["A", "B"])

    def test_merge_does_not_share_lists_with_its_inputs(self):
        source = profile(str_types=["WA"])
        merged = ne._merge(source)
        merged["str_types"].append("ZZ")

        self.assertEqual(source["str_types"], ["WA"])


class FilteredLayerTests(unittest.TestCase):

    def setUp(self):
        self.handler = ListHandler()
        self.logger = logging.getLogger("test_network_exclusions")
        self.logger.handlers = [self.handler]
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False

    def run_filter(self, counts, profile_name="HRFE"):
        with mock.patch.dict(sys.modules, {"arcpy": fake_arcpy(counts)}):
            return ne.make_filtered_layer("SRC", "edges", self.logger, profile_name)

    def test_logs_per_rule_counts(self):
        counts = {
            None: 100,
            ne.build_keep_clause("HRFE"): 90,
            "STR_TYPE IN ('WA')": 6,
            "FULL_NAME LIKE '%EMERGENCY ACCESS%'": 4,
        }
        self.run_filter(counts)
        info = "\n".join(self.handler.messages(logging.INFO))

        self.assertIn("profile HRFE", info)
        self.assertIn("90 of 100 kept, 10 excluded", info)
        self.assertIn("6 rows", info)
        self.assertIn("4 rows", info)
        self.assertEqual(self.handler.messages(logging.WARNING), [])

    def test_warns_when_a_rule_matches_nothing(self):
        counts = {
            None: 100,
            ne.build_keep_clause("HRFE"): 94,
            "STR_TYPE IN ('WA')": 6,
            "FULL_NAME LIKE '%EMERGENCY ACCESS%'": 0,
        }
        self.run_filter(counts)
        warnings = self.handler.messages(logging.WARNING)

        self.assertEqual(len(warnings), 1)
        self.assertIn("EMERGENCY ACCESS", warnings[0])

    def test_raises_when_everything_is_excluded(self):
        counts = {
            None: 100,
            ne.build_keep_clause("GENERAL"): 0,
            "STR_TYPE IN ('WA')": 100,
        }

        with self.assertRaises(RuntimeError):
            self.run_filter(counts, "GENERAL")

    def test_no_rules_uses_every_edge(self):
        with mock.patch.dict(ne.PROFILES, {"EMPTY": profile()}):
            self.run_filter({None: 50}, "EMPTY")

        self.assertIn("No edge exclusions configured", self.handler.messages(logging.INFO)[0])

    def test_count_excluded_warns_about_a_stale_copy(self):
        with mock.patch.dict(sys.modules, {"arcpy": fake_arcpy({"STR_TYPE IN ('WA')": 3})}):
            n = ne.count_excluded("COPY", self.logger, "GENERAL")

        self.assertEqual(n, 3)
        self.assertEqual(len(self.handler.messages(logging.WARNING)), 1)


if __name__ == "__main__":
    unittest.main()
