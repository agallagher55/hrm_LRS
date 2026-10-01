"""
Does the end of an added road meet the street network the way End Point connectivity needs?

The network uses End Point connectivity (ClassConnectivity = 1 in the template), so a road only
connects to a street where one of its ends meets one of the street's ends. A road whose end
touches the middle of a street does not connect unless the street is split at that point.

This is the pure logic, kept free of arcpy so it can be tested. The script that applies it to
real data is diagnostics/11_inspect_extra_roads.py.
"""

import math

# Metres. End Point connectivity joins two ends only if they coincide to within the XY tolerance
# of the feature dataset's spatial reference, which is far tighter than the 0.5 m that
# 05_rebuild_traffic_turns.py uses to match a turn to an edge. This is the usual default; the
# inspection script passes the real value from the streets' spatial reference.
SNAP_TOLERANCE = 0.001

# How far from an end to look for a street before calling it a free end.
SEARCH_DISTANCE = 25.0

END_POINT = "end_point"
MID_SEGMENT = "mid_segment"
GAP = "gap"
FREE_END = "free_end"

DESCRIPTIONS = {
    END_POINT: "connects at a street end point",
    MID_SEGMENT: "touches a street mid-segment: the street needs a split here",
    GAP: "near a street but not on it (further than the XY tolerance): snap it, "
         "or split the street and snap",
    FREE_END: "no street nearby: a free end, fine for a dead-end driveway",
}

# Classes that mean the end will not connect to anything as it is, though a street is close.
PROBLEMS = (MID_SEGMENT, GAP)


def pick_nearest(candidates, snap_tolerance=SNAP_TOLERANCE):
    """
    Choose the street an end should be judged against from
    (distance, distance_to_street_end, label) candidates.

    Several streets can meet at the same point. Among those the end touches, prefer the one it
    meets at an end point, so a through street that happens to come first does not hide a side
    street that ends there. If it touches none, the nearest one. Returns None for no candidates.
    """
    if not candidates:
        return None

    touching = [c for c in candidates if c[0] <= snap_tolerance]

    if touching:
        return min(touching, key=lambda c: (c[1], c[0]))

    return min(candidates, key=lambda c: c[0])


def classify_endpoint(distance_to_street, distance_to_street_end, snap_tolerance=SNAP_TOLERANCE,
                      search_distance=SEARCH_DISTANCE):
    """
    Classify one end of an added road.

    distance_to_street is how far the end is from the nearest street, or None if no street is
    within the search distance. distance_to_street_end is how far the nearest point on that
    street is from the street's nearer end.
    """
    if distance_to_street is None or distance_to_street > search_distance:
        return FREE_END

    if distance_to_street > snap_tolerance:
        return GAP

    if distance_to_street_end is not None and distance_to_street_end <= snap_tolerance:
        return END_POINT

    return MID_SEGMENT


def interior_points(points, end_points, tolerance=SNAP_TOLERANCE):
    """
    Return the (x, y) points that are not within tolerance of either end of the segment.

    A road that crosses a street away from its own ends does not connect to it under End Point
    connectivity, and needs a split there just as an end touching mid-street does. The points
    that are at the segment's own ends are already judged by classify_endpoint, so they are left
    out here.
    """
    kept = []

    for x, y in points:
        near_an_end = any(
            math.hypot(x - end_x, y - end_y) <= tolerance for end_x, end_y in end_points
        )

        if not near_an_end and (x, y) not in kept:
            kept.append((x, y))

    return kept


def segment_verdict(end_classes, crossings=0):
    """
    Summarise a segment from the classes of its two ends and how many streets it crosses.

    A problem at either end is reported, because it is the end that will not connect.
    """
    problems = [c for c in end_classes if c in PROBLEMS]

    if crossings:
        problems.append("{} crossing{}".format(crossings, "" if crossings == 1 else "s"))

    if problems:
        return "needs attention: " + ", ".join(sorted(set(problems)))

    if all(c == FREE_END for c in end_classes):
        return "isolated: neither end meets a street"

    return "ok"
