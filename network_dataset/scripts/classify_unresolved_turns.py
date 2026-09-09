"""
06_classify_unresolved_turns.py

Read-only diagnostic script to classify why turns in TRNLRS_traffic_turn are not
included in a completed network build. Written to generate the record-level list
behind the duplicate / geometry-gap split described in traffic_turns_status.md,
traffic_turns_duplicates.md, and traffic_turns_geometry_gaps.md. Nothing here is a
guess at which OIDs fall in which bucket, it is derived from the actual build
errors file and the actual edge references stored on each turn record.

Background
----------
A completed BuildNetwork run can report far fewer turns than exist in
TRNLRS_traffic_turn (e.g. 1,021 built vs 1,209 present) without that showing up as
a build-time error at the message-count level. As established in
traffic_turns_edge1end_addendum.md, the per-record detail only lives in the linked
BuildErrors_<guid>.txt file, so this script reads that file directly rather than
trusting the summary.

What this script does
----------------------
1. Parses the supplied BuildErrors_<guid>.txt for every failing ObjectID reported
   against TRNLRS_traffic_turn. This is the authoritative list of unresolved turns,
   not an assumption.
2. Loads every record in TRNLRS_traffic_turn (not just the failing ones) and builds
   an edge-reference signature per turn: the ordered sequence of (EdgeNFID, EdgeNPos)
   for every populated edge slot.
3. For each failing turn, checks whether any OTHER turn record (failing or not)
   shares an identical signature. A match means the same physical maneuver is
   already defined by a sibling record, classified as a likely duplicate.
4. Turns with no matching sibling are classified as likely geometry gaps.
5. Optionally (if SYSTEM_JUNCTION_FC is set and exists), flags geometry-gap turns
   whose shared junction point has no system junction within JUNCTION_CHECK_TOLERANCE,
   as a data point for the junctions.md investigation. This does not resolve that
   investigation, it only surfaces which of the 23 geometry-gap turns might be
   linked to it.
6. Writes a CSV report and prints a summary. Makes NO edits.

Usage
-----
1. Set BUILD_ERRORS_FILE to the path of the current build's BuildErrors_<guid>.txt.
   Confirm the GUID in that path matches the current build's log before running,
   per the lesson in traffic_turns_edge1end_addendum.md, this script does not
   verify that for you.
2. Set configuration variables below (SDE / NETWORK_FD already default to QA).
3. Run from an ArcGIS Pro Python environment (arcpy required):
       python 06_classify_unresolved_turns.py
4. Review the printed summary and the CSV written to OUTPUT_CSV.
"""

import csv
import math
import re
import sys

try:
    import arcpy
except ImportError:
    print("ERROR: arcpy is required. Run this from an ArcGIS Pro Python environment.")
    sys.exit(1)


# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

# Path to the BuildErrors_<guid>.txt file from the CURRENT build. Confirm the GUID
# matches the current build's log before running, do not reuse a stale path.
BUILD_ERRORS_FILE = r"T:\work\giss\monthly\202607jul\gallaga\network_dataset\New folder\BuildErrors_7f5e2ac0-64f1-4421-97d7-9be28cf15c3a.txt"

SDE        = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"
NETWORK_FD = r"SDEADM.TRNLRS_network"

TURN_FC = SDE + rf"\{NETWORK_FD}\SDEADM.TRNLRS_traffic_turn"
EDGE_FC = SDE + rf"\{NETWORK_FD}\SDEADM.TRNLRS_TRN_STREET"

# Optional: system junction FC, used only for the junctions.md cross-check in
# step 5. Set to None to skip that check entirely.
SYSTEM_JUNCTION_FC = SDE + rf"\{NETWORK_FD}\SDEADM.TRNLRS_street_network_Junctions"
JUNCTION_CHECK_TOLERANCE = 0.5  # metres

# Field on EDGE_FC to pull for a human-readable location in the report. Adjust if
# the confirmed street name field differs (see network_dataset_migration_plan.md
# Directions field mapping: Base Name -> STR_NAME).
STREET_NAME_FIELD = "STR_NAME"

# Position values are compared rounded to this many decimal places when building
# the duplicate signature, to avoid floating point noise producing false negatives.
POSITION_PRECISION = 6

OUTPUT_CSV = "unresolved_turns_classification.csv"


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def section(title):
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def parse_failing_oids(errors_path, turn_fc_name):
    """
    Extract ObjectIDs of failing records for turn_fc_name from a BuildErrors file.
    Matches lines of the form:
        SourceName: SDEADM.TRNLRS_traffic_turn, ObjectID: 42, <message text>
    Deliberately matches on ObjectID presence, not on specific message wording,
    since the point of this script is to find every failure, whatever its cause.
    """
    pattern = re.compile(
        rf"SourceName:\s*[\w.]*{re.escape(turn_fc_name)}.*?ObjectID:\s*(\d+)",
        re.IGNORECASE,
    )
    oids = set()
    try:
        with open(errors_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = pattern.search(line)
                if m:
                    oids.add(int(m.group(1)))
    except FileNotFoundError:
        print(f"ERROR: BuildErrors file not found: {errors_path}")
        sys.exit(1)
    return oids


def detect_edge_slots(fld_map):
    return [i for i in range(1, 6) if f"EDGE{i}FID" in fld_map]


def build_turn_signatures(turn_fc, edge_slots, fld_map):
    """
    Returns:
      signatures: dict of turn_oid -> tuple of (EdgeNFID, rounded EdgeNPos) for
                  each populated slot, in slot order
      edge_refs:  dict of turn_oid -> list of (fid, pos) for slot 1 only, used
                  for the report and the junction proximity check
      shapes:     dict of turn_oid -> SHAPE@ (turn point geometry), used for the
                  junction proximity check
    """
    fields = ["OID@", "SHAPE@"]
    for i in edge_slots:
        fields.append(fld_map.get(f"EDGE{i}FID", f"Edge{i}FID"))
        fields.append(fld_map.get(f"EDGE{i}POS", f"Edge{i}Pos"))

    signatures = {}
    edge1_refs = {}
    shapes = {}

    with arcpy.da.SearchCursor(turn_fc, fields) as cur:
        for row in cur:
            oid = row[0]
            shape = row[1]
            sig = []
            for idx, i in enumerate(edge_slots):
                fid = row[2 + idx * 2]
                pos = row[3 + idx * 2]
                if fid is None or fid == 0:
                    continue
                pos_r = round(pos, POSITION_PRECISION) if pos is not None else None
                sig.append((i, fid, pos_r))
                if i == 1:
                    edge1_refs[oid] = (fid, pos_r)
            signatures[oid] = tuple(sig)
            shapes[oid] = shape

    return signatures, edge1_refs, shapes


def find_siblings(failing_oids, signatures):
    """
    For each failing OID, find other OIDs (any status) sharing an identical
    edge-reference signature. Returns dict of turn_oid -> list of sibling OIDs.
    """
    by_signature = {}
    for oid, sig in signatures.items():
        if not sig:
            continue
        by_signature.setdefault(sig, []).append(oid)

    siblings = {}
    for oid in failing_oids:
        sig = signatures.get(oid)
        if not sig:
            siblings[oid] = []
            continue
        matches = [o for o in by_signature.get(sig, []) if o != oid]
        siblings[oid] = matches

    return siblings


def load_edge_lookup(edge_fc, street_field):
    """
    Returns dict of edge OID -> (SHAPE@, street name or None), used to resolve
    edge1 endpoints to a readable location for the report.
    """
    fields = ["OID@", "SHAPE@"]
    has_name = street_field in [f.name for f in arcpy.ListFields(edge_fc)]
    if has_name:
        fields.append(street_field)

    lookup = {}
    with arcpy.da.SearchCursor(edge_fc, fields) as cur:
        for row in cur:
            oid = row[0]
            shape = row[1]
            name = row[2] if has_name else None
            lookup[oid] = (shape, name)
    return lookup


def nearest_junction_distance(pt, junction_geoms):
    if pt is None or not junction_geoms:
        return None
    min_dist = None
    for jshape in junction_geoms:
        jpt = jshape.firstPoint if jshape else None
        if jpt is None:
            continue
        dx = jpt.X - pt.X
        dy = jpt.Y - pt.Y
        dist = math.sqrt(dx * dx + dy * dy)
        if min_dist is None or dist < min_dist:
            min_dist = dist
    return min_dist


def turn_junction_point(turn_shape):
    """
    Turn feature classes store the turn as a point or multipoint at the shared
    junction. Handles both by returning firstPoint.
    """
    if turn_shape is None:
        return None
    return turn_shape.firstPoint


# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------

def main():
    section("06_classify_unresolved_turns.py")
    print(f"Turn FC:          {TURN_FC}")
    print(f"Edge FC:          {EDGE_FC}")
    print(f"Build errors:     {BUILD_ERRORS_FILE}")
    print(f"System junctions: {SYSTEM_JUNCTION_FC if SYSTEM_JUNCTION_FC else '(skipped)'}")

    for path, label in [(TURN_FC, "Turn FC"), (EDGE_FC, "Edge FC")]:
        if not arcpy.Exists(path):
            print(f"ERROR: {label} not found: {path}")
            sys.exit(1)

    turn_fc_name = TURN_FC.rsplit(".", 1)[-1]

    section("STEP 1: Parse build errors file for failing ObjectIDs")
    failing_oids = parse_failing_oids(BUILD_ERRORS_FILE, turn_fc_name)
    print(f"Failing turn OIDs found: {len(failing_oids)}")
    if not failing_oids:
        print("No failing OIDs matched. Check BUILD_ERRORS_FILE path and turn_fc_name matching.")
        return

    section("STEP 2: Load turn edge-reference signatures")
    fld_map = {f.name.upper(): f.name for f in arcpy.ListFields(TURN_FC)}
    edge_slots = detect_edge_slots(fld_map)
    if not edge_slots:
        print(f"ERROR: no Edge{{N}}FID fields found on {TURN_FC}.")
        sys.exit(1)
    print(f"Edge slots detected: {edge_slots}")

    signatures, edge1_refs, shapes = build_turn_signatures(TURN_FC, edge_slots, fld_map)
    print(f"Total turn records loaded: {len(signatures)}")

    section("STEP 3: Classify failing turns as duplicate or geometry gap")
    siblings = find_siblings(failing_oids, signatures)

    duplicates = {oid: sibs for oid, sibs in siblings.items() if sibs}
    geometry_gaps = {oid: sibs for oid, sibs in siblings.items() if not sibs}

    print(f"Classified as likely duplicate:     {len(duplicates)}")
    print(f"Classified as likely geometry gap:  {len(geometry_gaps)}")

    section("STEP 4: Optional junction proximity check for geometry-gap turns")
    junction_flags = {}
    if SYSTEM_JUNCTION_FC and arcpy.Exists(SYSTEM_JUNCTION_FC):
        junction_geoms = []
        with arcpy.da.SearchCursor(SYSTEM_JUNCTION_FC, ["SHAPE@"]) as cur:
            for (shape,) in cur:
                if shape is not None:
                    junction_geoms.append(shape)
        print(f"Loaded {len(junction_geoms)} system junction geometries.")

        for oid in geometry_gaps:
            pt = turn_junction_point(shapes.get(oid))
            dist = nearest_junction_distance(pt, junction_geoms)
            junction_flags[oid] = dist
            print(f"  turn OID {oid}: nearest system junction {dist:.3f} m" if dist is not None
                  else f"  turn OID {oid}: could not compute distance")
    else:
        print("SYSTEM_JUNCTION_FC not set or not found. Skipping junction cross-check.")
        print("Geometry-gap turns will be reported without a junction-linkage flag.")

    section("STEP 5: Resolve edge1 location for the report")
    edge_lookup = load_edge_lookup(EDGE_FC, STREET_NAME_FIELD)

    section("STEP 6: Write report")
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "turn_oid", "category", "sibling_oids", "edge1_fid", "edge1_pos",
            "edge1_street_name", "nearest_system_junction_m", "junction_linked_candidate"
        ])

        for oid in sorted(failing_oids):
            category = "duplicate" if oid in duplicates else "geometry_gap"
            sibs = siblings.get(oid, [])
            fid, pos = edge1_refs.get(oid, (None, None))
            _, street_name = edge_lookup.get(fid, (None, None))
            dist = junction_flags.get(oid)
            # Threshold matches JUNCTION_CHECK_TOLERANCE; flag as a candidate for
            # the junctions.md linkage only when clearly beyond normal snap distance
            # but the check itself is advisory, not a determination.
            linked_candidate = (
                dist is not None and dist > JUNCTION_CHECK_TOLERANCE
                and category == "geometry_gap"
            )
            writer.writerow([
                oid, category, ";".join(str(s) for s in sibs), fid, pos,
                street_name, f"{dist:.3f}" if dist is not None else "",
                linked_candidate,
            ])

    print(f"Report written to: {OUTPUT_CSV}")

    section("SUMMARY")
    print(f"Total failing turns:          {len(failing_oids)}")
    print(f"  Likely duplicates:          {len(duplicates)}")
    print(f"  Likely geometry gaps:       {len(geometry_gaps)}")
    if junction_flags:
        linked = sum(
            1 for oid, d in junction_flags.items()
            if d is not None and d > JUNCTION_CHECK_TOLERANCE
        )
        print(f"    of which junction-linked candidates: {linked}")
    print()
    print("This is a diagnostic classification, not a final decision. Duplicate")
    print("candidates still need Mel's confirmation that the sibling truly enforces")
    print("the same restriction (see traffic_turns_duplicates.md). Geometry-gap")
    print("candidates still need manual review to separate confirmed authoring gaps")
    print("from junctions.md-linked cases (see traffic_turns_geometry_gaps.md).")


if __name__ == "__main__":
    main()