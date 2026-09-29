"""
08_find_duplicate_siblings.py

Read-only follow-up once BuildNetwork's own errors confirmed the split: 165 turns
fail with "Turn element already exists" (true duplicates) and 23 fail with
"Cannot find at junction" (topology lookup failure, likely linked to the
junctions.md investigation).

06_classify_unresolved_turns.py tried to find duplicate siblings by matching
exact (Edge{N}FID, Edge{N}Pos) tuples and found none, which is now understood to
be the wrong signature: BuildNetwork's own duplicate check almost certainly keys
on which END of the edge the turn lands on (front vs back, i.e. the junction it
resolves to), not the raw continuous Pos value. Two turns with Pos = 0.001 and
Pos = 0.002 both resolve to the same junction and collide, but would never match
on exact Pos.

This script rebuilds the signature using (Edge{N}FID, end-flag) per slot, where
end-flag is "N" for Pos < 0.5 (start of edge) and "Y" for Pos >= 0.5 (end of
edge), the same convention already established for the Edge1End field in
traffic_turns_edge1end_addendum.md. It only needs to run against the 165 known
duplicate OIDs (from FAILING_OIDS_DUPLICATE below, paste in from the 07 script's
output or BuildErrors file), but matches against the full turn FC so it can find
a sibling that resolved successfully, not just another failing one.

Usage
-----
1. Set TURN_FC.
2. Paste the full list of 165 duplicate-classified OIDs into FAILING_OIDS_DUPLICATE
   (pull these from BuildErrors_<guid>.txt, filtering to the "Turn element already
   exists" message, same approach as 07_inspect_turn_error_messages.py but keeping
   OIDs instead of just counting).
3. Run from an ArcGIS Pro Python environment.
"""

import csv
import sys

try:
    import arcpy
except ImportError:
    print("ERROR: arcpy is required. Run this from an ArcGIS Pro Python environment.")
    sys.exit(1)

SDE        = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"
NETWORK_FD = r"SDEADM.TRNLRS_network"
TURN_FC    = SDE + rf"\{NETWORK_FD}\SDEADM.TRNLRS_traffic_turn"

# Paste the 165 OIDs here. If you'd rather not paste manually, point
# BUILD_ERRORS_FILE at the same file and this script will pull them directly,
# filtering on the confirmed message text.
BUILD_ERRORS_FILE = r"T:\work\giss\monthly\202607jul\gallaga\network_dataset\New folder\BuildErrors_7f5e2ac0-64f1-4421-97d7-9be28cf15c3a.txt"

TARGET_MESSAGE = "Turn element already exists."

OUTPUT_CSV = "duplicate_turn_siblings.csv"
POSITION_PRECISION = 6


def parse_oids_for_message(errors_path, turn_fc_name, target_message):
    import re
    pattern = re.compile(
        rf"SourceName:\s*[\w.]*{re.escape(turn_fc_name)}.*?ObjectID:\s*(\d+)\s*,?\s*(.*)",
        re.IGNORECASE,
    )
    oids = []
    with open(errors_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = pattern.search(line)
            if m and target_message.lower() in m.group(2).strip().lower():
                oids.append(int(m.group(1)))
    return oids


def detect_edge_slots(fld_map):
    return [i for i in range(1, 6) if f"EDGE{i}FID" in fld_map]


def end_flag(pos):
    if pos is None:
        return None
    return "Y" if pos >= 0.5 else "N"


def build_end_signatures(turn_fc, edge_slots, fld_map):
    fields = ["OID@"]
    for i in edge_slots:
        fields.append(fld_map.get(f"EDGE{i}FID", f"Edge{i}FID"))
        fields.append(fld_map.get(f"EDGE{i}POS", f"Edge{i}Pos"))

    signatures = {}
    with arcpy.da.SearchCursor(turn_fc, fields) as cur:
        for row in cur:
            oid = row[0]
            sig = []
            for idx, i in enumerate(edge_slots):
                fid = row[1 + idx * 2]
                pos = row[2 + idx * 2]
                if fid is None or fid == 0:
                    continue
                sig.append((i, fid, end_flag(pos)))
            signatures[oid] = tuple(sig)
    return signatures


def main():
    turn_fc_name = TURN_FC.rsplit(".", 1)[-1]

    print(f"Turn FC: {TURN_FC}")

    duplicate_oids = parse_oids_for_message(BUILD_ERRORS_FILE, turn_fc_name, TARGET_MESSAGE)
    print(f"OIDs matching '{TARGET_MESSAGE}': {len(duplicate_oids)}")
    if not duplicate_oids:
        print("No matching OIDs found. Check BUILD_ERRORS_FILE / TARGET_MESSAGE.")
        return

    fld_map = {f.name.upper(): f.name for f in arcpy.ListFields(TURN_FC)}
    edge_slots = detect_edge_slots(fld_map)
    print(f"Edge slots detected: {edge_slots}")

    signatures = build_end_signatures(TURN_FC, edge_slots, fld_map)
    print(f"Total turn records loaded: {len(signatures)}")

    by_signature = {}
    for oid, sig in signatures.items():
        if sig:
            by_signature.setdefault(sig, []).append(oid)

    matched = 0
    unmatched = []

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["turn_oid", "sibling_oids", "num_siblings", "signature"])

        for oid in duplicate_oids:
            sig = signatures.get(oid)
            sibs = [o for o in by_signature.get(sig, []) if o != oid] if sig else []
            if sibs:
                matched += 1
            else:
                unmatched.append(oid)
            writer.writerow([oid, ";".join(str(s) for s in sibs), len(sibs), sig])

    print()
    print(f"Matched a sibling (front/back-end signature): {matched} / {len(duplicate_oids)}")
    print(f"Still unmatched: {len(unmatched)}")
    if unmatched:
        print(f"  sample unmatched OIDs: {unmatched[:10]}")
        print("  If a meaningful number remain unmatched, the end-flag signature may")
        print("  still be too strict (e.g. multi-edge turns where a middle edge slot")
        print("  differs) or BuildNetwork's duplicate key includes something else,")
        print("  such as the resolved junction OID directly rather than edge/end pairs.")
    print(f"Report written to: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()