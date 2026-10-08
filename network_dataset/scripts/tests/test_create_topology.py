"""
Tests for 07_create_topology.py. They need no ArcGIS: the script is imported against a
stand-in for arcpy.

Run from network_dataset/scripts:
  > python -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "tests"))

from test_network_definitions import load_script  # noqa: E402


class TopologyScriptTests(unittest.TestCase):

    def test_distance_topology_has_the_name_made_in_pro(self):
        module = load_script("07_create_topology.py", None)

        self.assertEqual(module.TOPOLOGY_NAME, "TRNLRS_TRN_STREET_topology")
        self.assertTrue(module.TOPOLOGY.endswith("SDEADM.TRNLRS_TRN_STREET_topology"))

    def test_hrfe_topology_sits_on_the_hrfe_edge_copy(self):
        module = load_script("07_create_topology.py", "HRFE")

        self.assertEqual(module.TOPOLOGY_NAME, "TRNLRS_TRN_STREET_HRFE_topology")
        self.assertIn("TRNLRS_network_HRFE", module.TOPOLOGY)

    # The values AddRuleToTopology accepts for line rules, from its ERROR 000800 message.
    VALID_LINE_RULES = {
        "Must Not Overlap (Line)",
        "Must Not Intersect (Line)",
        "Must Not Have Dangles (Line)",
        "Must Not Self-Overlap (Line)",
        "Must Not Self-Intersect (Line)",
        "Must Not Intersect Or Touch Interior (Line)",
        "Must Be Single Part (Line)",
    }

    def test_default_rules_are_the_six_agreed_with_robbie(self):
        module = load_script("07_create_topology.py", None)
        rules = module.rules_to_add()

        self.assertEqual(len(rules), 6)
        self.assertNotIn("Must Not Intersect Or Touch Interior (Line)", rules)

    def test_every_rule_is_a_name_arcpy_accepts(self):
        module = load_script("07_create_topology.py", None)
        module.INCLUDE_OPTIONAL_RULES = True

        for rule in module.rules_to_add():

            self.assertIn(rule, self.VALID_LINE_RULES)

    def test_the_optional_rule_is_added_only_on_request(self):
        module = load_script("07_create_topology.py", None)
        module.INCLUDE_OPTIONAL_RULES = True

        self.assertIn("Must Not Intersect Or Touch Interior (Line)", module.rules_to_add())

    def test_rule_field_prefers_the_description_whatever_the_case(self):
        module = load_script("07_create_topology.py", None)

        self.assertEqual(
            module.rule_field(["OBJECTID", "SHAPE", "RuleType", "RULEDESCRIPTION"]),
            "RULEDESCRIPTION",
        )
        self.assertEqual(module.rule_field(["OBJECTID", "RuleType"]), "RuleType")
        self.assertIsNone(module.rule_field(["OBJECTID", "SHAPE"]))

    def test_counts_are_largest_first(self):
        module = load_script("07_create_topology.py", None)

        self.assertEqual(
            module.count_values(["Dangles", "Overlap", "Dangles", "Dangles", "Overlap", "Single"]),
            [("Dangles", 3), ("Overlap", 2), ("Single", 1)],
        )

    def test_every_setting_main_reads_is_defined(self):
        """main() reads these as globals; one missing from the module would fail only at run time."""
        module = load_script("07_create_topology.py", None)

        for name in ("USE_SCRATCH", "VALIDATE", "EXPORT_ERRORS", "INCLUDE_OPTIONAL_RULES", "RESET_EDGE_SOURCE"):

            self.assertIsInstance(getattr(module, name), bool, name)

        self.assertFalse(module.USE_SCRATCH)


if __name__ == "__main__":
    unittest.main()
