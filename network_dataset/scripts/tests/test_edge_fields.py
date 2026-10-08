"""
Tests for edge_fields.py and 08_add_edge_fields.py. They need no ArcGIS: the scripts are
imported against a stand-in for arcpy.

Run from network_dataset/scripts:
  > python -m unittest discover -s tests -v
"""

import logging
import sys
import types
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "tests"))

from test_network_definitions import load_script  # noqa: E402

QUIET = logging.getLogger("test_edge_fields_quiet")
QUIET.addHandler(logging.NullHandler())
QUIET.propagate = False


def with_fake_arcpy(module, existing_names, added):
    module.arcpy.ListFields = lambda path: [types.SimpleNamespace(name=n) for n in existing_names]
    module.arcpy.management = types.SimpleNamespace(
        AddField=lambda table, name, field_type, **kwargs: added.append((name, field_type, kwargs))
    )


class EdgeFieldsTests(unittest.TestCase):

    def test_both_fields_are_missing_from_a_plain_edge_class(self):
        module = load_script("edge_fields.py", None)

        names = [name for name, _, _ in module.missing_fields(["OBJECTID", "FDMID"])]

        self.assertEqual(names, ["SPEED", "TRAVEL_TIME"])

    def test_an_existing_field_is_not_added_again_whatever_its_case(self):
        module = load_script("edge_fields.py", None)

        names = [name for name, _, _ in module.missing_fields(["speed", "FDMID"])]

        self.assertEqual(names, ["TRAVEL_TIME"])

    def test_nothing_is_added_when_both_exist(self):
        module = load_script("edge_fields.py", None)
        added = []
        with_fake_arcpy(module, ["SPEED", "TRAVEL_TIME"], added)

        self.assertEqual(module.add_travel_fields("fc", QUIET), [])
        self.assertEqual(added, [])

    def test_the_missing_fields_are_added_with_their_types(self):
        module = load_script("edge_fields.py", None)
        added = []
        with_fake_arcpy(module, ["OBJECTID"], added)

        self.assertEqual(module.add_travel_fields("fc", QUIET), ["SPEED", "TRAVEL_TIME"])
        self.assertEqual([(n, t) for n, t, _ in added], [("SPEED", "SHORT"), ("TRAVEL_TIME", "DOUBLE")])

    def test_the_standalone_script_loads_for_both_networks(self):
        for env in (None, "HRFE"):
            module = load_script("08_add_edge_fields.py", env)

            self.assertTrue(module.EDGE_FC.endswith("SDEADM." + module.NETWORK.edge_name))


if __name__ == "__main__":
    unittest.main()
