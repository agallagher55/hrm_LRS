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

    def test_default_rules_are_the_six_agreed_with_robbie(self):
        module = load_script("07_create_topology.py", None)
        keywords = [keyword for keyword, _ in module.rules_to_add()]

        self.assertEqual(len(keywords), 6)
        self.assertNotIn("MUST_NOT_INTERSECT_OR_TOUCH_INTERIOR", keywords)

    def test_the_optional_rule_is_added_only_on_request(self):
        module = load_script("07_create_topology.py", None)
        module.INCLUDE_OPTIONAL_RULES = True

        self.assertIn(
            "MUST_NOT_INTERSECT_OR_TOUCH_INTERIOR",
            [keyword for keyword, _ in module.rules_to_add()],
        )


if __name__ == "__main__":
    unittest.main()
