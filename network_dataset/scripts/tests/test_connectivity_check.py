"""
Tests for connectivity_check.py, the logic behind diagnostics/11_inspect_extra_roads.py.

Run from network_dataset/scripts:
  > python -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import connectivity_check as cc  # noqa: E402


class ClassifyEndpointTests(unittest.TestCase):

    def test_an_end_on_a_street_end_point_connects(self):
        self.assertEqual(cc.classify_endpoint(0.0, 0.0), cc.END_POINT)
        self.assertEqual(cc.classify_endpoint(0.0005, 0.0008), cc.END_POINT)

    def test_an_end_on_the_middle_of_a_street_needs_a_split(self):
        self.assertEqual(cc.classify_endpoint(0.0, 37.5), cc.MID_SEGMENT)
        self.assertEqual(cc.classify_endpoint(0.0004, 0.6), cc.MID_SEGMENT)

    def test_a_near_miss_is_a_gap_not_a_connection(self):
        """End Point connectivity needs ends within the XY tolerance (about a millimetre)."""
        self.assertEqual(cc.classify_endpoint(0.3, 0.0), cc.GAP)
        self.assertEqual(cc.classify_endpoint(0.01, 0.0), cc.GAP)
        self.assertEqual(cc.classify_endpoint(12.0, 50.0), cc.GAP)

    def test_an_end_with_no_street_nearby_is_free(self):
        self.assertEqual(cc.classify_endpoint(None, None), cc.FREE_END)
        self.assertEqual(cc.classify_endpoint(60.0, 1.0), cc.FREE_END)

    def test_the_tolerances_are_inclusive_at_the_edge(self):
        self.assertEqual(cc.classify_endpoint(cc.SNAP_TOLERANCE, cc.SNAP_TOLERANCE), cc.END_POINT)
        self.assertEqual(cc.classify_endpoint(cc.SNAP_TOLERANCE * 2, 0.0), cc.GAP)
        self.assertEqual(cc.classify_endpoint(cc.SEARCH_DISTANCE, 0.0), cc.GAP)
        self.assertEqual(cc.classify_endpoint(cc.SEARCH_DISTANCE + 0.01, 0.0), cc.FREE_END)

    def test_custom_tolerances(self):
        self.assertEqual(cc.classify_endpoint(0.003, 0.003, snap_tolerance=0.005), cc.END_POINT)
        self.assertEqual(cc.classify_endpoint(10.0, 0.0, search_distance=5.0), cc.FREE_END)

    def test_the_default_tolerance_is_the_xy_tolerance_not_the_turn_snap(self):
        self.assertLess(cc.SNAP_TOLERANCE, 0.01)


class PickNearestTests(unittest.TestCase):

    def test_no_candidates(self):
        self.assertIsNone(cc.pick_nearest([]))

    def test_prefers_the_street_it_meets_at_an_end_over_one_it_crosses(self):
        """A through street and a side street meet at the same point: the end connects."""
        through = (0.0, 40.0, "through street")
        side = (0.0, 0.0, "side street")

        for order in ([through, side], [side, through]):
            self.assertEqual(cc.pick_nearest(order), side)

    def test_with_nothing_touching_the_nearest_wins(self):
        near = (3.0, 10.0, "near")
        far = (9.0, 0.0, "far")

        self.assertEqual(cc.pick_nearest([far, near]), near)

    def test_touching_beats_a_closer_end_that_does_not_touch(self):
        touching = (0.0, 25.0, "touching mid-street")
        off = (0.4, 0.0, "off, at an end")

        self.assertEqual(cc.pick_nearest([off, touching]), touching)

    def test_a_mid_street_touch_alone_stays_mid_street(self):
        best = cc.pick_nearest([(0.0, 30.0, "only street")])

        self.assertEqual(cc.classify_endpoint(best[0], best[1]), cc.MID_SEGMENT)


class InteriorPointsTests(unittest.TestCase):

    ENDS = [(0.0, 0.0), (100.0, 0.0)]

    def test_points_at_the_segments_own_ends_are_left_out(self):
        self.assertEqual(cc.interior_points([(0.0, 0.0), (100.0, 0.0)], self.ENDS), [])
        self.assertEqual(cc.interior_points([(0.0005, 0.0)], self.ENDS), [])

    def test_a_point_part_way_along_is_a_crossing(self):
        self.assertEqual(cc.interior_points([(40.0, 0.0)], self.ENDS), [(40.0, 0.0)])

    def test_a_point_just_off_an_end_is_a_crossing(self):
        """A crossing one centimetre from the end is not at the end for End Point connectivity."""
        self.assertEqual(cc.interior_points([(0.01, 0.0)], self.ENDS), [(0.01, 0.0)])

    def test_repeated_points_are_counted_once(self):
        points = [(40.0, 0.0), (40.0, 0.0), (70.0, 5.0)]

        self.assertEqual(cc.interior_points(points, self.ENDS), [(40.0, 0.0), (70.0, 5.0)])

    def test_no_points(self):
        self.assertEqual(cc.interior_points([], self.ENDS), [])


class SegmentVerdictTests(unittest.TestCase):

    def test_a_crossing_needs_attention_even_when_both_ends_connect(self):
        verdict = cc.segment_verdict([cc.END_POINT, cc.END_POINT], crossings=2)

        self.assertEqual(verdict, "needs attention: 2 crossings")

    def test_one_crossing_is_singular(self):
        self.assertEqual(
            cc.segment_verdict([cc.END_POINT, cc.FREE_END], crossings=1),
            "needs attention: 1 crossing",
        )

    def test_a_crossing_and_a_bad_end_are_both_named(self):
        verdict = cc.segment_verdict([cc.MID_SEGMENT, cc.FREE_END], crossings=1)

        self.assertIn("mid_segment", verdict)
        self.assertIn("1 crossing", verdict)

    def test_an_isolated_road_that_crosses_a_street_is_not_called_isolated(self):
        verdict = cc.segment_verdict([cc.FREE_END, cc.FREE_END], crossings=1)

        self.assertTrue(verdict.startswith("needs attention"))

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
