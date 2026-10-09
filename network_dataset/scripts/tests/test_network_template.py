"""
Guards for the TrafficTurn evaluators and the Directions units in the committed network template. They need no ArcGIS.

A template re-exported on 2026-09-18 had the Turn default evaluator set to restricted and no
evaluator for the turn source. With TrafficTurn ticked in a travel mode that restricts every turn,
so no route could turn a corner (found by the smoke test's control check on 2026-10-09). The
original design, and the one restored on 2026-10-09, is: restricted on the TRNLRS_traffic_turn
source only, and not restricted on every default.

Run from network_dataset/scripts:
  > python -m unittest discover -s tests -v
"""

import re
import sys
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import network_definitions as nd  # noqa: E402

TEMPLATE = SCRIPTS.parent / "data" / "network_template.xml"


def traffic_turn_assignments(text):
    """Return [(element type, source name, is default, constant value)] for the TrafficTurn attribute."""
    root = ElementTree.fromstring(text.encode("utf-8"))
    found = []

    for assignment in root.iter("NetworkAssignment"):
        if assignment.findtext("NetworkAttributeName") != "TrafficTurn":
            continue

        value = None

        for prop in assignment.iter("PropertySetProperty"):
            if prop.findtext("Key") == "ConstantValue":
                value = prop.findtext("Value")

        found.append((
            assignment.findtext("NetworkElementType"),
            assignment.findtext("NetworkSourceName"),
            assignment.findtext("IsDefault"),
            value,
        ))

    return found


class TrafficTurnTemplateTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_every_default_is_not_restricted(self):
        defaults = [item for item in traffic_turn_assignments(self.text) if item[2] == "true"]

        self.assertEqual(sorted(item[0] for item in defaults), ["esriNETEdge", "esriNETJunction", "esriNETTurn"])
        self.assertTrue(all(item[3] == "false" for item in defaults), defaults)

    def test_only_the_turn_source_is_restricted(self):
        restricted = [item for item in traffic_turn_assignments(self.text) if item[3] == "true"]

        self.assertEqual(len(restricted), 1, restricted)
        self.assertEqual(restricted[0][1], "TRNLRS_traffic_turn")
        self.assertEqual(restricted[0][2], "false")

    def test_the_hrfe_template_restricts_the_hrfe_turn_source(self):
        rendered = nd.render_template(self.text, nd.HRFE)

        restricted = [item for item in traffic_turn_assignments(rendered) if item[3] == "true"]

        self.assertEqual([item[1] for item in restricted], ["TRNLRS_traffic_turn_HRFE"])

    def test_directions_report_in_kilometres(self):
        root = ElementTree.fromstring(self.text.encode("utf-8"))

        self.assertEqual(root.findtext("./NetworkDirections/DefaultOutputLengthUnits"), "esriNAUKilometers")
        self.assertEqual(root.findtext("./NetworkDirections/LengthAttributeName"), "Length")

    def test_the_template_is_still_well_formed_and_python(self):
        ElementTree.fromstring(self.text.encode("utf-8"))
        self.assertNotIn("Select Case", self.text)
        self.assertTrue(re.search(r"<NetworkDirections", self.text))


if __name__ == "__main__":
    unittest.main()
