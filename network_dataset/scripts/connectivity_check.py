"""
Does the end of an added road meet the street network the way End Point connectivity needs?

The network uses End Point connectivity (ClassConnectivity = 1 in the template), so a road only
connects to a street where one of its ends meets one of the street's ends. A road whose end
touches the middle of a street does not connect unless the street is split at that point.

This is the pure logic, kept free of arcpy so it can be tested. The script that applies it to
real data is diagnostics/11_inspect_extra_roads.py.
"""

# Metres. Matches SNAP_TOLERANCE in 05_rebuild_traffic_turns.py.
SNAP_TOLERANCE = 0.5

# How far from an end to look for a street before calling it a free end.
SEARCH_DISTANCE = 25.0

END_POINT = "end_point"
MID_SEGMENT = "mid_segment"
GAP = "gap"
FREE_END = "free_end"

DESCRIPTIONS = {
    END_POINT: "connects at a street end point",
    MID_SEGMENT: "touches a street mid-segment: the street needs a split here",
    GAP: "near a street but not touching it: snap it, or split the street and snap",
    FREE_END: "no street nearby: a free end, fine for a dead-end driveway",
}

# Classes that mean the end will not connect to anything as it is, though a street is close.
PROBLEMS = (MID_SEGMENT, GAP)


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


def segment_verdict(end_classes):
    """
    Summarise a segment from the classes of its two ends.

    A problem at either end is reported, because it is the end that will not connect.
    """
    problems = [c for c in end_classes if c in PROBLEMS]

    if problems:
        return "needs attention: " + ", ".join(sorted(set(problems)))

    if all(c == FREE_END for c in end_classes):
        return "isolated: neither end meets a street"

    return "ok"
