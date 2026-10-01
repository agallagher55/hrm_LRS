"""
Tests for connectivity_check.py, the logic behind diagnostics/11_inspect_extra_roads.py.

Run from network_dataset/scripts:
  > python -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import connectivity_check as cc


class ClassifyEndpointTests(unittest.TestCase):

    def test_an_end_on_a_street_end_point_connects(self):
        self.assertEqual(cc.classify_endpoint(0.0, 0.0), cc.END_POINT)
        self.assertEqual(cc.classify_endpoint(0.3, 0.4), cc.END_POINT)

    def test_an_end_on_the_middle_of_a_street_needs_a_split(self):
        self.assertEqual(cc.classify_endpoint(0.0, 37.5), cc.MID_SEGMENT)
        self.assertEqual(cc.classify_endpoint(0.4, 0.6), cc.MID_SEGMENT)

    def test_an_end_just_off_a_street_is_a_gap(self):
        self.assertEqual(cc.classify_endpoint(0.8, 0.0), cc.GAP)
        self.assertEqual(cc.classify_endpoint(12.0, 50.0), cc.GAP)

    def test_an_end_with_no_street_nearby_is_free(self):
        self.assertEqual(cc.classify_endpoint(None, None), cc.FREE_END)
        self.assertEqual(cc.classify_endpoint(60.0, 1.0), cc.FREE_END)

    def test_the_tolerances_are_inclusive_at_the_edge(self):
        self.assertEqual(cc.classify_endpoint(cc.SNAP_TOLERANCE, cc.SNAP_TOLERANCE), cc.END_POINT)
        self.assertEqual(cc.classify_endpoint(cc.SNAP_TOLERANCE + 0.01, 0.0), cc.GAP)
        self.assertEqual(cc.classify_endpoint(cc.SEARCH_DISTANCE, 0.0), cc.GAP)
        self.assertEqual(cc.classify_endpoint(cc.SEARCH_DISTANCE + 0.01, 0.0), cc.FREE_END)

    def test_custom_tolerances(self):
        self.assertEqual(cc.classify_endpoint(1.5, 1.5, snap_tolerance=2.0), cc.END_POINT)
        self.assertEqual(cc.classify_endpoint(10.0, 0.0, search_distance=5.0), cc.FREE_END)

    def test_snap_tolerance_matches_the_turn_remap(self):
        source = (Path(__file__).resolve().parents[1] / "05_rebuild_traffic_turns.py").read_text(encoding="utf-8")

        self.assertIn("SNAP_TOLERANCE = {}".format(cc.SNAP_TOLERANCE), source)


class SegmentVerdictTests(unittest.TestCase):

    def test_both_ends_connected_is_ok(self):
        self.assertEqual(cc.segment_verdict([cc.END_POINT, cc.END_POINT]), "ok")

    def test_a_dead_end_driveway_is_ok(self):
        self.assertEqual(cc.segment_verdict([cc.END_POINT, cc.FREE_END]), "ok")

    def test_a_mid_segment_end_needs_attention(self):
        verdict = cc.segment_verdict([cc.END_POINT, cc.MID_SEGMENT])

        self.assertTrue(verdict.startswith("needs attention"))
        self.assertIn(cc.MID_SEGMENT, verdict)

    def test_both_problems_are_named_once(self):
        verdict = cc.segment_verdict([cc.GAP, cc.GAP])

        self.assertEqual(verdict, "needs attention: gap")

    def test_a_road_that_meets_nothing_is_isolated(self):
        self.assertTrue(cc.segment_verdict([cc.FREE_END, cc.FREE_END]).startswith("isolated"))

    def test_every_class_has_a_description(self):
        for code in (cc.END_POINT, cc.MID_SEGMENT, cc.GAP, cc.FREE_END):

            self.assertIn(code, cc.DESCRIPTIONS)


if __name__ == "__main__":
    unittest.main()
