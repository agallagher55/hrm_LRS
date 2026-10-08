"""
Tests for network_exclusions.py. They need no ArcGIS: the clause builders are pure,
and make_filtered_layer is exercised against a fake arcpy.

Run from network_dataset/scripts:
  > python -m unittest discover -s tests -v
"""

import csv
import logging
import re
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import network_exclusions as ne  # noqa: E402


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


DIAGNOSTIC_CSV = (
    Path(__file__).resolve().parents[2]
    / "intermediate_results" / "candidate_exclusions_20260929.csv"
)


def like_to_regex(pattern):
    """Translate a SQL Server LIKE pattern to a regex, case-insensitive like the collation."""
    parts = []
    i = 0

    while i < len(pattern):
        char = pattern[i]

        if char == "%":
            parts.append(".*")

        elif char == "_":
            parts.append(".")

        elif char == "[":
            end = pattern.index("]", i)
            parts.append(pattern[i:end + 1])
            i = end

        else:
            parts.append(re.escape(char))

        i += 1

    return re.compile("^" + "".join(parts) + "$", re.IGNORECASE)


def like(name, pattern):
    return bool(like_to_regex(pattern).match(name))


def fake_arcpy(counts, default=1):
    """
    Build a stand-in for arcpy. counts maps a where clause (None for the whole
    source) to the row count a layer with that clause reports. Any other clause
    reports default rows.
    """
    layers = {}

    def make_feature_layer(source, name, where_clause=None):
        layers[name] = where_clause

        return [name]

    def get_count(layer_or_fc):
        where_clause = layers.get(layer_or_fc)

        return [counts.get(where_clause, default)]

    management = types.SimpleNamespace(
        MakeFeatureLayer=make_feature_layer,
        GetCount=get_count,
        Delete=lambda layer: None,
    )

    return types.SimpleNamespace(management=management)


class ClauseTests(unittest.TestCase):

    def test_general_wa_rule_is_unchanged(self):
        _, exclude, keep = ne.get_rules("GENERAL")[0]

        self.assertEqual(exclude, "STR_TYPE IN ('WA')")
        self.assertEqual(keep, "(STR_TYPE IS NULL OR STR_TYPE NOT IN ('WA'))")

    def test_general_keeps_transit_access_roads(self):
        """Decided 2026-10-08: the distance network leaves transit access roads in."""
        exclude = ne.build_exclude_clause("GENERAL")

        self.assertEqual(exclude, "STR_TYPE IN ('WA')")
        self.assertNotIn("TA[0-9]%", ne.build_keep_clause("GENERAL"))

    def test_hrfe_still_drops_transit_access_roads(self):
        """HRFE is for fire and keeps transit access roads out (Alex, 2026-10-08)."""
        self.assertIn("FULL_NAME LIKE 'TA[0-9]%'", ne.build_exclude_clause("HRFE"))
        self.assertIn(
            "(FULL_NAME IS NULL OR FULL_NAME NOT LIKE 'TA[0-9]%')",
            ne.build_keep_clause("HRFE"),
        )

    def test_under_review_streets_are_kept_in_every_profile(self):
        for name in ne.PROFILES:

            self.assertNotIn("UNDER REVIEW", ne.build_exclude_clause(name))

    def test_default_profile_is_general(self):
        self.assertEqual(ne.DEFAULT_PROFILE, "GENERAL")
        self.assertEqual(ne.build_keep_clause(), ne.build_keep_clause("GENERAL"))

    def test_hrfe_includes_general_and_its_own_rules(self):
        exclude = ne.build_exclude_clause("HRFE")

        self.assertIn("STR_TYPE IN ('WA')", exclude)
        self.assertIn("FULL_NAME LIKE 'TA[0-9]%'", exclude)
        self.assertIn("FULL_NAME LIKE '%EMERGENCY ACCESS%'", exclude)
        self.assertIn("FULL_NAME LIKE '% ETA [0-9]%'", exclude)

    def test_general_does_not_pick_up_hrfe_rules(self):
        exclude = ne.build_exclude_clause("GENERAL")

        self.assertNotIn("EMERGENCY", exclude)
        self.assertNotIn("ETA", exclude)

    def test_hrfe_keep_clause_is_null_safe_for_every_rule(self):
        keep = ne.build_keep_clause("HRFE")

        self.assertIn("(STR_TYPE IS NULL OR STR_TYPE NOT IN ('WA'))", keep)
        self.assertIn("(FULL_NAME IS NULL OR FULL_NAME NOT LIKE '%EMERGENCY ACCESS%')", keep)
        self.assertEqual(keep.count(" AND "), len(ne.get_rules("HRFE")) - 1)

        for _, _, rule_keep in ne.get_rules("HRFE"):

            self.assertIn(" IS NULL OR ", rule_keep)

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


class PatternTests(unittest.TestCase):
    """The name patterns, checked against sample names and the saved Prod diagnostic."""

    def test_like_helper(self):
        self.assertTrue(like("TA52 RD", "TA[0-9]%"))
        self.assertFalse(like("TAYLOR DR", "TA[0-9]%"))
        self.assertTrue(like("a1", "_[0-9]"))
        self.assertFalse(like("A.1", "_[0-9]"))

    def test_transit_pattern_takes_ta_roads_and_not_ordinary_streets(self):
        for name in ("TA1 RD", "TA52 RD", "TA43 RD"):

            self.assertTrue(like(name, "TA[0-9]%"), name)

        for name in ("TAYLOR DR", "TAMARACK DR", "TANLOR DR", "STATE ST", "META1 RD"):

            self.assertFalse(like(name, "TA[0-9]%"), name)

    def test_eta_pattern_takes_eta_segments_only(self):
        for name in ("HIGHWAY 101 ETA 294", "HIGHWAY 118 ETA 5"):

            self.assertTrue(like(name, "% ETA [0-9]%"), name)

        for name in ("BETA 5 RD", "HIGHWAY 101", "PETALS LANE", "ETA ROAD"):

            self.assertFalse(like(name, "% ETA [0-9]%"), name)

    @unittest.skipUnless(DIAGNOSTIC_CSV.exists(), "diagnostic CSV not in the repository")
    def test_patterns_reproduce_the_prod_counts_from_2026_09_29(self):
        with open(DIAGNOSTIC_CSV, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        def names(candidate):
            return {r["FDMID"]: r["FULL_NAME"] for r in rows if r["candidate"] == candidate}

        # The wide TA search returned 209 rows; the digit pattern must keep 124 of them.
        transit = [n for n in names("Transit: TA prefix").values() if like(n, "TA[0-9]%")]
        self.assertEqual(len(transit), 124)
        self.assertEqual(len(names("Transit: TA prefix")), 209)

        etas = [n for n in names("ETA: name search").values() if like(n, "% ETA [0-9]%")]
        self.assertEqual(len(etas), 22)

        emergency = [n for n in names("Emergency access").values() if like(n, "%EMERGENCY ACCESS%")]
        self.assertEqual(len(emergency), 4)

    @unittest.skipUnless(DIAGNOSTIC_CSV.exists(), "diagnostic CSV not in the repository")
    def test_the_four_saved_sets_do_not_overlap(self):
        with open(DIAGNOSTIC_CSV, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        sets = ("WA baseline", "Emergency access", "Transit: TA + digit", "ETA: name search")
        ids = [r["FDMID"] for r in rows if r["candidate"] in sets]

        self.assertEqual(len(ids), 211)
        self.assertEqual(len(set(ids)), 211)


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
        }

        with self.assertRaises(RuntimeError):
            self.run_filter(counts, "GENERAL")

    def test_no_rules_uses_every_edge(self):
        with mock.patch.dict(ne.PROFILES, {"EMPTY": profile()}):
            self.run_filter({None: 50}, "EMPTY")

        self.assertIn("No edge exclusions configured", self.handler.messages(logging.INFO)[0])

    def test_count_excluded_warns_about_a_stale_copy(self):
        counts = {ne.build_exclude_clause("GENERAL"): 3}

        with mock.patch.dict(sys.modules, {"arcpy": fake_arcpy(counts)}):
            n = ne.count_excluded("COPY", self.logger, "GENERAL")

        self.assertEqual(n, 3)
        self.assertEqual(len(self.handler.messages(logging.WARNING)), 1)


if __name__ == "__main__":
    unittest.main()
