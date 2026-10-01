"""
11_inspect_extra_roads.py

Read-only. Looks at the roads Robbie Evans (HRFE) supplies for the HRFE network, such as the
Station 2 turning lane, and reports what the network needs to know before they are loaded:

  - the feature classes in his geodatabase: geometry type, spatial reference, row count
  - which of the fields the network uses are present (STR_DIR, STR_NAME, STR_TYPE, FULL_NAME)
  - for each segment, how each end meets the LRS streets (see connectivity_check.py): at a
    street end point (connects), in the middle of a street (needs a split there), a small gap
    (needs snapping), or free (fine for a dead-end driveway)
  - how many streets each segment crosses away from its own ends, which also need a split
  - a second CSV, OUTPUT of SPLIT_POINTS_CSV, listing every point where a street would need
    splitting for the roads to connect

The streets are Prod's TRNLRS_TRN_STREET_VW with the HRFE exclusions applied, which is what the
HRFE network's edge copy will hold.

Why it matters: the network uses End Point connectivity, so an added road whose end touches the
middle of a street does not connect. This finds those ends so the street can be split there, and
shows whether Robbie's segment is fine as it is. Robbie agreed on 2026-10-01 that split points
live in their own layer and are re-applied after each LRS update.

Usage
-----
1. Set EXTRA_GDB (and EXTRA_FCS to limit it to named classes; None checks every line class).
2. Run from an ArcGIS Pro Python environment.
3. Read the printout and the CSV written to OUTPUT_CSV.

If the spatial references differ, the segment ends are projected to the streets' on the fly;
check the datum transformation if the two use different datums, because a shift of a metre or two
is enough to turn a connecting end into a gap. An end counts as meeting a street only within the
XY tolerance of the streets' spatial reference (about a millimetre), because that is how close two
ends must be for End Point connectivity to join them.
"""

import csv
import os
import sys

try:
    import arcpy
except ImportError:
    print("ERROR: arcpy is required. Run this from an ArcGIS Pro Python environment.")
    sys.exit(1)

# This script lives in diagnostics/, so Python puts that folder on the path, not the scripts folder
# that holds connectivity_check.py and network_exclusions.py. abspath (not resolve) keeps a mapped
# T: drive from being expanded to its server path.
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import connectivity_check  # noqa: E402
import network_exclusions  # noqa: E402

# The T:\work\giss prefix is assumed from the other monthly folders; the rest is from
# Robbie's folder.
EXTRA_GDB = r"T:\work\giss\monthly\202610oct\evansr\Network_Segments_For_Alex\Network_Segments.gdb"
EXTRA_FCS = None

PROD_SDE = r"E:\HRM\Scripts\SDE\SQL\Prod\prod_RW_sdeadm.sde"
STREETS_FC = PROD_SDE + r"\SDEADM.TRNLRS_TRN_STREET_VW"

# The fields the network reads: STR_DIR for the OneWay restriction, the rest for Directions.
NETWORK_FIELDS = ["STR_DIR", "STR_NAME", "STR_TYPE", "FULL_NAME"]

OUTPUT_CSV = "extra_roads_check.csv"
SPLIT_POINTS_CSV = "extra_roads_split_points.csv"


def line_feature_classes(gdb):
    """Return the full paths of the polyline feature classes in gdb, or in EXTRA_FCS.

    Looks in the geodatabase root and inside each feature dataset, because network sources are
    often kept in a feature dataset.
    """
    arcpy.env.workspace = gdb
    paths = [os.path.join(gdb, n) for n in arcpy.ListFeatureClasses(feature_type="Polyline") or []]

    for dataset in arcpy.ListDatasets("", "Feature") or []:
        names = arcpy.ListFeatureClasses(feature_type="Polyline", feature_dataset=dataset) or []
        paths.extend(os.path.join(gdb, dataset, n) for n in names)

    if EXTRA_FCS:
        paths = [p for p in paths if os.path.basename(p) in EXTRA_FCS]

    return paths


def describe(path):
    """Print the schema facts the network needs."""
    desc = arcpy.Describe(path)
    count = int(arcpy.management.GetCount(path)[0])
    fields = {f.name.upper() for f in arcpy.ListFields(path)}

    print("{}: {:,} rows, {}, {}".format(path, count, desc.shapeType, desc.spatialReference.name))

    for field in NETWORK_FIELDS:
        print("  {:<10} {}".format(field, "present" if field in fields else "MISSING"))


def nearest_street(point, streets_sr, keep_clause, tolerance):
    """
    Return (distance to the street, distance from the nearest point to that street's nearer end,
    street FDMID and name), or (None, None, None) if no street is within the search.
    """
    search = point.buffer(connectivity_check.SEARCH_DISTANCE)
    candidates = []

    with arcpy.da.SearchCursor(
        STREETS_FC, ["SHAPE@", "FDMID", "FULL_NAME"], keep_clause,
        spatial_reference=streets_sr, spatial_filter=search, spatial_relationship="INTERSECTS",
    ) as cursor:

        for shape, fdmid, full_name in cursor:
            _, along, distance, _ = shape.queryPointAndDistance(point, False)
            to_end = min(along, shape.length - along)
            candidates.append((distance, to_end, "{} {}".format(fdmid, full_name)))

    best = connectivity_check.pick_nearest(candidates, tolerance)

    return best if best else (None, None, None)


def intersection_points(geometry):
    """Return the (x, y) points of an intersect() result: none, one or several."""
    if geometry is None or not geometry.pointCount:
        return []

    part = geometry.getPart()

    if isinstance(part, arcpy.Point):
        return [(part.X, part.Y)]

    return [(p.X, p.Y) for p in part if p is not None]


def crossings(shape, streets_sr, keep_clause, tolerance):
    """
    Return [(x, y, street)] where the segment meets a street away from its own two ends.

    Under End Point connectivity such a crossing does not connect, so the street and the road
    both need a split there.
    """
    ends = [(shape.firstPoint.X, shape.firstPoint.Y), (shape.lastPoint.X, shape.lastPoint.Y)]
    found = []

    with arcpy.da.SearchCursor(
        STREETS_FC, ["SHAPE@", "FDMID", "FULL_NAME"], keep_clause,
        spatial_reference=streets_sr, spatial_filter=shape, spatial_relationship="INTERSECTS",
    ) as cursor:

        for street_shape, fdmid, full_name in cursor:
            points = intersection_points(shape.intersect(street_shape, 1))

            for x, y in connectivity_check.interior_points(points, ends, tolerance):
                found.append((x, y, "{} {}".format(fdmid, full_name)))

    return found


def check_segments(path, streets_sr, keep_clause, tolerance):
    """
    Return (rows, split_points). rows has one entry per segment: its OID, both end classes, the
    nearest streets, how many streets it crosses and a verdict. split_points lists every place a
    street would need splitting for the segment to connect.
    """
    rows = []
    split_points = []

    with arcpy.da.SearchCursor(path, ["OID@", "SHAPE@"], spatial_reference=streets_sr) as cursor:

        for oid, shape in cursor:
            ends = []

            for label, point in (("start", shape.firstPoint), ("end", shape.lastPoint)):
                point_geometry = arcpy.PointGeometry(point, streets_sr)
                distance, to_end, street = nearest_street(
                    point_geometry, streets_sr, keep_clause, tolerance
                )
                end_class = connectivity_check.classify_endpoint(
                    distance, to_end, snap_tolerance=tolerance
                )
                ends.append((end_class, distance, street))

                if end_class == connectivity_check.MID_SEGMENT:
                    split_points.append({
                        "x": round(point.X, 3), "y": round(point.Y, 3), "street": street,
                        "reason": "{} of segment OID {}".format(label, oid),
                    })

            crossed = crossings(shape, streets_sr, keep_clause, tolerance)

            for x, y, street in crossed:
                split_points.append({
                    "x": round(x, 3), "y": round(y, 3), "street": street,
                    "reason": "segment OID {} crosses it".format(oid),
                })

            rows.append({
                "feature_class": os.path.basename(path),
                "oid": oid,
                "length_m": round(shape.length, 2),
                "start": ends[0][0],
                "start_gap_m": None if ends[0][1] is None else round(ends[0][1], 3),
                "start_street": ends[0][2],
                "end": ends[1][0],
                "end_gap_m": None if ends[1][1] is None else round(ends[1][1], 3),
                "end_street": ends[1][2],
                "crossings": len(crossed),
                "verdict": connectivity_check.segment_verdict(
                    [ends[0][0], ends[1][0]], len(crossed)
                ),
            })

    return rows, split_points


def main():
    for path, label in ((EXTRA_GDB, "Robbie's geodatabase"), (STREETS_FC, "Prod streets")):

        if not arcpy.Exists(path):
            sys.exit("ERROR: Cannot find {}: {}".format(label, path))

    streets_sr = arcpy.Describe(STREETS_FC).spatialReference
    tolerance = streets_sr.XYTolerance or connectivity_check.SNAP_TOLERANCE
    keep_clause = network_exclusions.build_keep_clause("HRFE")
    print("Streets: {} ({}), HRFE exclusions applied.".format(STREETS_FC, streets_sr.name))
    print("Ends count as meeting a street within the XY tolerance, {} m.\n".format(tolerance))

    paths = line_feature_classes(EXTRA_GDB)

    if not paths:
        sys.exit("No polyline feature classes found in {}".format(EXTRA_GDB))

    all_rows = []
    all_split_points = []

    for path in paths:
        describe(path)
        rows, split_points = check_segments(path, streets_sr, keep_clause, tolerance)
        all_rows.extend(rows)
        all_split_points.extend(split_points)

        for row in rows:
            print(
                "  OID {oid}, {length_m} m: start {start}, end {end}, crosses {crossings} "
                "streets. {verdict}".format(**row)
            )

        print()

    print("Key:")

    for code, text in connectivity_check.DESCRIPTIONS.items():
        print("  {:<12} {}".format(code, text))

    if not all_rows:
        sys.exit("\nThe feature classes above have no rows, so there is nothing to check.")

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)

    with open(SPLIT_POINTS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["x", "y", "street", "reason"])
        writer.writeheader()
        writer.writerows(all_split_points)

    print("\n{} places where a street needs splitting for these roads to connect.".format(
        len(all_split_points)
    ))
    print("Reports written to: {} and {}".format(OUTPUT_CSV, SPLIT_POINTS_CSV))


if __name__ == "__main__":
    main()
