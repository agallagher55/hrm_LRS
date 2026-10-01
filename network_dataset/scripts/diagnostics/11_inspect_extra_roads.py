"""
11_inspect_extra_roads.py

Read-only. Looks at the roads Robbie Evans (HRFE) supplies for the HRFE network, such as the
Station 2 turning lane, and reports what the network needs to know before they are loaded:

  - the feature classes in his geodatabase: geometry type, spatial reference, row count
  - which of the fields the network uses are present (STR_DIR, STR_NAME, STR_TYPE, FULL_NAME)
  - for each segment, how each end meets the LRS streets (see connectivity_check.py): at a
    street end point (connects), in the middle of a street (needs a split there), a small gap
    (needs snapping), or free (fine for a dead-end driveway)

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
is enough to turn a connecting end into a gap.
"""

import csv
import sys

try:
    import arcpy
except ImportError:
    print("ERROR: arcpy is required. Run this from an ArcGIS Pro Python environment.")
    sys.exit(1)

import connectivity_check
import network_exclusions

# The T:\work\giss prefix is assumed from the other monthly folders; the rest is from Robbie's folder.
EXTRA_GDB = r"T:\work\giss\monthly\202610oct\evansr\Network_Segments_For_Alex\Network_Segments.gdb"
EXTRA_FCS = None

PROD_SDE = r"E:\HRM\Scripts\SDE\SQL\Prod\prod_RW_sdeadm.sde"
STREETS_FC = PROD_SDE + r"\SDEADM.TRNLRS_TRN_STREET_VW"

# The fields the network reads: STR_DIR for the OneWay restriction, the rest for Directions.
NETWORK_FIELDS = ["STR_DIR", "STR_NAME", "STR_TYPE", "FULL_NAME"]

OUTPUT_CSV = "extra_roads_check.csv"


def line_feature_classes(gdb):
    """Return the names of the polyline feature classes in gdb, or in EXTRA_FCS."""
    arcpy.env.workspace = gdb
    names = arcpy.ListFeatureClasses(feature_type="Polyline") or []

    if EXTRA_FCS:
        names = [n for n in names if n in EXTRA_FCS]

    return names


def describe(gdb, name):
    """Print the schema facts the network needs and return the Describe object."""
    desc = arcpy.Describe(gdb + "\\" + name)
    count = int(arcpy.management.GetCount(gdb + "\\" + name)[0])
    fields = {f.name.upper() for f in arcpy.ListFields(gdb + "\\" + name)}

    print("{}: {:,} rows, {}, {}".format(name, count, desc.shapeType, desc.spatialReference.name))

    for field in NETWORK_FIELDS:
        print("  {:<10} {}".format(field, "present" if field in fields else "MISSING"))

    return desc


def nearest_street(point, streets_sr, keep_clause):
    """
    Return (distance to the nearest street, distance from the nearest point to that street's
    nearer end, street FDMID and name), or (None, None, None) if none is within the search.
    """
    search = point.buffer(connectivity_check.SEARCH_DISTANCE)
    best = None

    with arcpy.da.SearchCursor(
        STREETS_FC, ["SHAPE@", "FDMID", "FULL_NAME"], keep_clause,
        spatial_reference=streets_sr, spatial_filter=search, spatial_relationship="INTERSECTS",
    ) as cursor:

        for shape, fdmid, full_name in cursor:
            _, along, distance, _ = shape.queryPointAndDistance(point, False)
            to_end = min(along, shape.length - along)

            if best is None or distance < best[0]:
                best = (distance, to_end, "{} {}".format(fdmid, full_name))

    return best if best else (None, None, None)


def check_segments(gdb, name, streets_sr, keep_clause):
    """Return one row per segment: its OID, both end classes, the nearest streets and a verdict."""
    rows = []
    fc = gdb + "\\" + name

    with arcpy.da.SearchCursor(fc, ["OID@", "SHAPE@"], spatial_reference=streets_sr) as cursor:

        for oid, shape in cursor:
            ends = []

            for label, point in (("start", shape.firstPoint), ("end", shape.lastPoint)):
                point_geometry = arcpy.PointGeometry(point, streets_sr)
                distance, to_end, street = nearest_street(point_geometry, streets_sr, keep_clause)
                ends.append((
                    label,
                    connectivity_check.classify_endpoint(distance, to_end),
                    distance,
                    street,
                ))

            rows.append({
                "feature_class": name,
                "oid": oid,
                "length_m": round(shape.length, 2),
                "start": ends[0][1],
                "start_gap_m": None if ends[0][2] is None else round(ends[0][2], 2),
                "start_street": ends[0][3],
                "end": ends[1][1],
                "end_gap_m": None if ends[1][2] is None else round(ends[1][2], 2),
                "end_street": ends[1][3],
                "verdict": connectivity_check.segment_verdict([ends[0][1], ends[1][1]]),
            })

    return rows


def main():
    for path, label in ((EXTRA_GDB, "Robbie's geodatabase"), (STREETS_FC, "Prod streets")):

        if not arcpy.Exists(path):
            sys.exit("ERROR: Cannot find {}: {}".format(label, path))

    streets_sr = arcpy.Describe(STREETS_FC).spatialReference
    keep_clause = network_exclusions.build_keep_clause("HRFE")
    print("Streets: {} ({}), HRFE exclusions applied.\n".format(STREETS_FC, streets_sr.name))

    names = line_feature_classes(EXTRA_GDB)

    if not names:
        sys.exit("No polyline feature classes found in {}".format(EXTRA_GDB))

    all_rows = []

    for name in names:
        describe(EXTRA_GDB, name)
        rows = check_segments(EXTRA_GDB, name, streets_sr, keep_clause)
        all_rows.extend(rows)

        for row in rows:
            print("  OID {oid}, {length_m} m: start {start}, end {end}. {verdict}".format(**row))

        print()

    print("Key:")

    for code, text in connectivity_check.DESCRIPTIONS.items():
        print("  {:<12} {}".format(code, text))

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)

    print("\nReport written to: {}".format(OUTPUT_CSV))


if __name__ == "__main__":
    main()
