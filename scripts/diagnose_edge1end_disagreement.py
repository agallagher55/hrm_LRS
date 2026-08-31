"""
diagnose_edge1end_disagreement.py

Read-only. Re-derives the exact same Edge1End integrity check
05_rebuild_traffic_turns.py runs, but for every disagreement prints enough
detail to tell apart the two possible causes:

  (a) shared_endpoint() picked the wrong endpoint pairing -- most likely at a
      short Edge1 or a busy intersection where Edge1's OTHER end is also
      close to Edge2, making the "closest pair" tiebreak unreliable.
  (b) the source's own Edge1End field is simply wrong on that record (a
      legacy data-quality issue, not a remap bug).

Case (a) is flagged directly: "ambiguous" is True when Edge1's non-chosen
endpoint is ALSO within tolerance of an Edge2 endpoint -- i.e. the pairing
was a coin flip, not a clean single match.

Background
----------
Run against QA on 2026-08-31, 05_rebuild_traffic_turns.py reported:

    Edge1End integrity check: 846/1194 (70.9%) agree

well below the 95% threshold the script gates an auto-swap on. The skip
counts and DSID from that same run were otherwise healthy (4.0% skipped,
all in expected categories), so the problem is isolated to this one check.
This script exists to find out whether that's a real weakness in
shared_endpoint()'s tiebreak, or legacy Edge1End data errors that predate
any of this project's scripts.

Mirrors 05_rebuild_traffic_turns.py's own config and geometry helpers so
this diagnoses the exact computation that ran, not a reimplementation.

Usage
-----
Run from an ArcGIS Pro Python environment (arcpy required):
    python diagnose_edge1end_disagreement.py
"""

import math

import arcpy

SDE        = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"
NETWORK_FD = r"SDEADM.TRNLRS_network"
OLD_TURN_FC = SDE + r"\SDEADM.TRN_streets_routes\SDEADM.TRN_traffic_turn"
OLD_EDGE_FC = SDE + r"\SDEADM.TRN_streets_routes\SDEADM.TRN_street"
SNAP_TOLERANCE = 0.5

SAMPLE_SIZE = 40  # how many disagreements to print in full detail


def points_equal(pt_a, pt_b, tolerance):
    if pt_a is None or pt_b is None:
        return False
    return math.hypot(pt_a.X - pt_b.X, pt_a.Y - pt_b.Y) <= tolerance


def endpoint_pair_distances(geom_a, geom_b):
    """All four (label, dist) endpoint-pair distances between two polylines."""
    out = []
    for la, pt_a in (("A.first", geom_a.firstPoint), ("A.last", geom_a.lastPoint)):
        for lb, pt_b in (("B.first", geom_b.firstPoint), ("B.last", geom_b.lastPoint)):
            if pt_a is None or pt_b is None:
                continue
            out.append((f"{la}~{lb}", math.hypot(pt_a.X - pt_b.X, pt_a.Y - pt_b.Y)))
    return sorted(out, key=lambda kv: kv[1])


def shared_endpoint(geom_a, geom_b, tolerance):
    best_pt, best_dist = None, None
    for pt_a in (geom_a.firstPoint, geom_a.lastPoint):
        for pt_b in (geom_b.firstPoint, geom_b.lastPoint):
            if pt_a is None or pt_b is None:
                continue
            dist = math.hypot(pt_a.X - pt_b.X, pt_a.Y - pt_b.Y)
            if dist <= tolerance and (best_dist is None or dist < best_dist):
                best_pt, best_dist = pt_a, dist
    return best_pt


def edge_end_flag(geom, junction_pt, tolerance):
    if points_equal(geom.lastPoint, junction_pt, tolerance):
        return "Y"
    if points_equal(geom.firstPoint, junction_pt, tolerance):
        return "N"
    return None


def edge_length(geom):
    return geom.length if geom is not None else None


def main():
    print("Loading old edge geometries...")
    old_geoms = {}
    with arcpy.da.SearchCursor(OLD_EDGE_FC, ["OID@", "SHAPE@"]) as cur:
        for oid, shape in cur:
            if shape is not None:
                old_geoms[oid] = shape
    print(f"  {len(old_geoms)} loaded")

    fld_map = {f.name.upper(): f.name for f in arcpy.ListFields(OLD_TURN_FC)}
    edge_slots = [i for i in range(1, 6) if f"EDGE{i}FID" in fld_map]
    has_edge1end = "EDGE1END" in fld_map

    fields = ["OID@"]
    idx = {"oid": 0}
    if has_edge1end:
        idx["edge1end"] = len(fields)
        fields.append(fld_map["EDGE1END"])
    slot_fid_idx = {}
    slot_pos_idx = {}
    for i in edge_slots:
        slot_fid_idx[i] = len(fields)
        fields.append(fld_map[f"EDGE{i}FID"])
        if f"EDGE{i}POS" in fld_map:
            slot_pos_idx[i] = len(fields)
            fields.append(fld_map[f"EDGE{i}POS"])

    checked = 0
    agree = 0
    disagreements = []

    with arcpy.da.SearchCursor(OLD_TURN_FC, fields) as cur:
        for row in cur:
            turn_oid = row[idx["oid"]]
            src_end = row[idx["edge1end"]] if has_edge1end else None
            if src_end not in ("Y", "N"):
                continue

            slot_fids = []
            for i in edge_slots:
                fid = row[slot_fid_idx[i]]
                if fid is None or fid == 0:
                    break
                slot_fids.append(fid)
            if len(slot_fids) < 2:
                continue

            geom1 = old_geoms.get(slot_fids[0])
            geom2 = old_geoms.get(slot_fids[1])
            if geom1 is None or geom2 is None:
                continue

            junction = shared_endpoint(geom1, geom2, SNAP_TOLERANCE)
            if junction is None:
                continue

            derived = edge_end_flag(geom1, junction, SNAP_TOLERANCE)
            if derived is None:
                continue

            checked += 1
            if derived == src_end:
                agree += 1
                continue

            pair_dists = endpoint_pair_distances(geom1, geom2)
            chosen_dist = pair_dists[0][1]
            # Ambiguous if a SECOND pairing is also within tolerance -- the
            # "closest pair" tiebreak was a coin flip, not a clean single match.
            ambiguous = len(pair_dists) > 1 and pair_dists[1][1] <= SNAP_TOLERANCE

            pos1 = row[slot_pos_idx[1]] if 1 in slot_pos_idx else None
            disagreements.append({
                "oid": turn_oid, "src_end": src_end, "derived": derived,
                "edge1_fid": slot_fids[0], "edge2_fid": slot_fids[1],
                "edge1_pos": pos1, "chosen_pair": pair_dists[0][0], "chosen_dist": chosen_dist,
                "all_pair_dists": pair_dists, "ambiguous": ambiguous,
                "edge1_len": edge_length(geom1), "edge2_len": edge_length(geom2),
                "edge1_first_xy": (geom1.firstPoint.X, geom1.firstPoint.Y),
            })

    print("=" * 70)
    print(f"Checked: {checked}   Agree: {agree} ({agree / checked:.1%})   Disagree: {len(disagreements)}")
    print("=" * 70)

    ambiguous_count = sum(1 for d in disagreements if d["ambiguous"])
    print(f"Of the disagreements, AMBIGUOUS pairing (2nd candidate also in tolerance): {ambiguous_count}")
    print(f"Of the disagreements, CLEAN single pairing (source field likely just wrong): {len(disagreements) - ambiguous_count}")
    print()

    short_edge_disagreements = [d for d in disagreements if d["edge1_len"] is not None and d["edge1_len"] < 5]
    print(f"Disagreements where Edge1 is under 5m long: {len(short_edge_disagreements)}")
    print()

    print(f"Sample of {min(SAMPLE_SIZE, len(disagreements))} disagreements (full detail):")
    for d in disagreements[:SAMPLE_SIZE]:
        print(f"  turn {d['oid']}: src={d['src_end']} derived={d['derived']}  "
              f"edge1_pos={d['edge1_pos']}  ambiguous={d['ambiguous']}  "
              f"edge1_len={d['edge1_len']:.2f}m edge2_len={d['edge2_len']:.2f}m  "
              f"chosen_pair={d['chosen_pair']} @ {d['chosen_dist']:.3f}m  "
              f"edge1={d['edge1_fid']} edge2={d['edge2_fid']}  "
              f"all_pairs={[(p, round(dd, 3)) for p, dd in d['all_pair_dists']]}  "
              f"xy={d['edge1_first_xy']}")


if __name__ == "__main__":
    main()
