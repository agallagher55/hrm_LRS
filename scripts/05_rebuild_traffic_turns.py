"""
05_rebuild_traffic_turns.py

Rebuilds TRNLRS_traffic_turn by spatially remapping edge references from the old
TRN_street_network edge source (TRN_street) to the new edge source (TRNLRS_TRN_STREET).

Background
----------
Turn feature classes store edge references as Edge{N}FID fields containing the ObjectID
of a feature in the registered edge source FC. TRNLRS_traffic_turn was initially created
by copying TRN_traffic_turn, which referenced OIDs in TRN_street. Those OIDs have no
meaning in TRNLRS_TRN_STREET, so every turn record fails at BuildNetwork time.

This script resolves the mismatch by matching turn junction points (edge endpoints,
determined by Edge{N}Pos) to spatially coincident endpoints in TRNLRS_TRN_STREET,
then writes a new turn FC with corrected OID references.

Usage
-----
1. Set configuration variables below.
2. Run from an ArcGIS Pro Python environment (arcpy required).
3. Review the written/skipped summary printed on completion, and the skipped OID
   list in the log file if you need to investigate individual turns.
4. If skipped count is acceptable, run the swap block at the bottom to replace
   the old turn FC and rebuild the network.

Output
------
Creates TRNLRS_traffic_turn_new inside SDEADM.TRNLRS. The old TRNLRS_traffic_turn
is not touched until the optional swap step at the end.

See docs/traffic_turns.md for full diagnosis and post-run steps.
"""

import arcpy
import sys

from log_utils import setup_logger

logger = setup_logger("05_rebuild_traffic_turns")

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

SDE = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"
# Prod: TRNLRS_TRN_STREET has already been created against this connection.
# Uncomment to point this script at prod instead of QA.
# SDE = r"E:\HRM\Scripts\SDE\SQL\Prod\prod_RW_sdeadm.sde"

OLD_TURN_FC  = SDE + r"\SDEADM.TRN_streets_routes\SDEADM.TRN_traffic_turn"
OLD_EDGE_FC  = SDE + r"\SDEADM.TRN_streets_routes\SDEADM.TRN_street"
NEW_EDGE_FC  = SDE + r"\SDEADM.TRNLRS\SDEADM.TRNLRS_TRN_STREET"
NEW_TURN_FC  = SDE + r"\SDEADM.TRNLRS\SDEADM.TRNLRS_traffic_turn_new"
OLD_TURN_FC_FINAL = SDE + r"\SDEADM.TRNLRS\SDEADM.TRNLRS_traffic_turn"
NEW_NETWORK  = SDE + r"\SDEADM.TRNLRS\SDEADM.TRNLRS_street_network"

# Snap tolerance in map units (metres). Turn junctions must fall within this
# distance of a new edge endpoint to be matched. Widen if skipped count is
# unexpectedly high; tighten if intersections are very closely spaced.
SNAP_TOLERANCE = 0.5

# Set to True to delete OLD_TURN_FC_FINAL, rename NEW_TURN_FC, and rebuild the
# network automatically after a successful remap. Set to False to review the
# output first before committing.
AUTO_SWAP_AND_REBUILD = False


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def point_key(pt, tolerance):
    """
    Round a point's coordinates to a tolerance grid for fuzzy spatial matching.
    Returns a tuple usable as a dict key.
    """
    return (
        round(pt.X / tolerance) * tolerance,
        round(pt.Y / tolerance) * tolerance,
    )


def build_endpoint_index(edge_fc, tolerance):
    """
    Build a spatial index of edge endpoints.
    Returns a dict mapping snapped point keys to lists of edge OIDs.
    Each edge contributes its firstPoint and lastPoint.
    """
    index = {}
    with arcpy.da.SearchCursor(edge_fc, ["OID@", "SHAPE@"]) as cur:
        for oid, shape in cur:
            if shape is None:
                continue
            for pt in (shape.firstPoint, shape.lastPoint):
                if pt is None:
                    continue
                key = point_key(pt, tolerance)
                index.setdefault(key, []).append(oid)
    return index


def build_geometry_lookup(edge_fc):
    """
    Build a dict of OID -> Polyline geometry for an edge feature class.
    Used to resolve old edge OIDs to their endpoint coordinates.
    """
    geoms = {}
    with arcpy.da.SearchCursor(edge_fc, ["OID@", "SHAPE@"]) as cur:
        for oid, shape in cur:
            if shape is not None:
                geoms[oid] = shape
    return geoms


def find_new_oid(old_oid, pos, old_geoms, new_endpoint_index, tolerance):
    """
    Resolve an old edge reference (OID + 0-to-1 position along edge) to the
    ObjectID of the spatially coincident new edge.

    pos < 0.5 means the turn junction is near the start of the old edge
    (firstPoint); pos >= 0.5 means it is near the end (lastPoint).

    Returns the new OID (int) if a match is found, else None.
    """
    shape = old_geoms.get(old_oid)
    if shape is None:
        return None

    pt = shape.firstPoint if pos < 0.5 else shape.lastPoint
    if pt is None:
        return None

    key = point_key(pt, tolerance)
    candidates = new_endpoint_index.get(key, [])

    if not candidates:
        return None

    # If there is only one candidate, return it directly.
    if len(candidates) == 1:
        return candidates[0]

    # Multiple candidates share this endpoint (multi-leg intersection).
    # Prefer the candidate whose geometry most closely aligns with the old edge
    # by comparing the direction vector from the junction point to each edge's
    # other endpoint against the direction of the old edge at the junction.
    # This is a best-effort tiebreaker; complex intersections may still require
    # manual review.
    import math

    def angle(from_pt, to_pt):
        dx = to_pt.X - from_pt.X
        dy = to_pt.Y - from_pt.Y
        return math.atan2(dy, dx)

    # Direction of old edge departing from the junction
    if pos < 0.5:
        old_junction_pt = shape.firstPoint
        old_other_pt    = shape.lastPoint
    else:
        old_junction_pt = shape.lastPoint
        old_other_pt    = shape.firstPoint

    old_angle = angle(old_junction_pt, old_other_pt)

    # Re-build geometry lookup on demand (passed in via closure below)
    best_oid  = candidates[0]
    best_diff = math.pi  # worst possible angular difference

    for cand_oid in candidates:
        cand_shape = _new_geoms.get(cand_oid)
        if cand_shape is None:
            continue
        # Determine which end of the candidate is at the junction
        fp = cand_shape.firstPoint
        lp = cand_shape.lastPoint
        fp_key = point_key(fp, tolerance) if fp else None
        jkey   = point_key(old_junction_pt, tolerance)
        if fp_key == jkey:
            other = lp
        else:
            other = fp
        if other is None:
            continue
        cand_angle = angle(old_junction_pt, other)
        diff = abs(math.atan2(
            math.sin(cand_angle - old_angle),
            math.cos(cand_angle - old_angle)
        ))
        if diff < best_diff:
            best_diff = diff
            best_oid  = cand_oid

    return best_oid


# Module-level new geometry lookup, populated in main() and referenced by
# find_new_oid's tiebreaker closure.
_new_geoms = {}


# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------

def main():
    global _new_geoms

    # Validate inputs
    for path, label in [
        (OLD_TURN_FC,  "Old turn FC"),
        (OLD_EDGE_FC,  "Old edge FC"),
        (NEW_EDGE_FC,  "New edge FC"),
        (NEW_NETWORK,  "New network dataset"),
    ]:
        if not arcpy.Exists(path):
            logger.error(f"{label} not found: {path}")
            sys.exit(1)

    if arcpy.Exists(NEW_TURN_FC):
        logger.error(f"Output FC already exists: {NEW_TURN_FC}. Delete or rename it before running.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 1. Index new edge endpoints
    # ------------------------------------------------------------------
    logger.info("Indexing new edge endpoints...")
    new_endpoint_index = build_endpoint_index(NEW_EDGE_FC, SNAP_TOLERANCE)
    new_edge_count = sum(len(v) for v in new_endpoint_index.values())
    logger.info(f"  {new_edge_count} endpoint entries indexed (snap tolerance: {SNAP_TOLERANCE}m)")

    # ------------------------------------------------------------------
    # 2. Build new edge geometry lookup (used by tiebreaker)
    # ------------------------------------------------------------------
    logger.info("Loading new edge geometries...")
    _new_geoms = build_geometry_lookup(NEW_EDGE_FC)
    logger.info(f"  {len(_new_geoms)} new edge features loaded")

    # ------------------------------------------------------------------
    # 3. Build old edge geometry lookup
    # ------------------------------------------------------------------
    logger.info("Loading old edge geometries...")
    old_geoms = build_geometry_lookup(OLD_EDGE_FC)
    logger.info(f"  {len(old_geoms)} old edge features loaded")

    # ------------------------------------------------------------------
    # 4. Inspect old turn FC schema
    # ------------------------------------------------------------------
    # Build a case-insensitive map (UPPER -> actual name) so field detection
    # works regardless of whether ArcGIS returns EDGE1FID or Edge1FID.
    _fld_map = {f.name.upper(): f.name for f in arcpy.ListFields(OLD_TURN_FC)}
    turn_field_names = list(_fld_map.values())

    edge_slots = [i for i in range(1, 6) if f"EDGE{i}FID" in _fld_map]
    if not edge_slots:
        logger.error(f"No Edge{{N}}FID fields found in old turn FC. Available fields: {turn_field_names}")
        sys.exit(1)
    logger.info(f"  Edge slots detected: {edge_slots}")

    has_node = "NODE_" in _fld_map

    # ------------------------------------------------------------------
    # 5. Get FCID of new edge source from network dataset
    # ------------------------------------------------------------------
    logger.info("Reading network dataset source FCID...")
    nd_desc = arcpy.Describe(NEW_NETWORK)
    new_edge_fcid = None
    for src in nd_desc.sources:
        if "TRNLRS_TRN_STREET" in src.name.upper():
            new_edge_fcid = src.sourceID
            break

    if new_edge_fcid is None:
        logger.error(
            "Could not find FCID for TRNLRS_TRN_STREET in network sources. "
            "Ensure the network dataset has been built at least once."
        )
        sys.exit(1)
    logger.info(f"  TRNLRS_TRN_STREET FCID: {new_edge_fcid}")

    # ------------------------------------------------------------------
    # 6. Create new turn feature class
    # ------------------------------------------------------------------
    logger.info(f"Creating output turn FC: {NEW_TURN_FC}")
    out_path, out_name = NEW_TURN_FC.rsplit("\\", 1)
    arcpy.na.CreateTurnFeatureClass(
        out_location=out_path,
        out_feature_class_name=out_name,
        maximum_edges=max(edge_slots),
        in_network_dataset=NEW_NETWORK,
    )

    # ------------------------------------------------------------------
    # 7. Build cursor field lists
    # ------------------------------------------------------------------
    # Read fields: SHAPE@, [NODE_,] Edge1FCID, Edge1FID, Edge1Pos, ..., OID@
    # Use actual field names from _fld_map so casing matches what ArcGIS expects.
    # OID@ is appended last (rather than inserted after SHAPE@) so it doesn't
    # shift the offsets used to walk the edge slot data below.
    read_fields = ["SHAPE@"]
    if has_node:
        read_fields.append(_fld_map["NODE_"])
    for i in edge_slots:
        read_fields += [
            _fld_map.get(f"EDGE{i}FCID", f"Edge{i}FCID"),
            _fld_map.get(f"EDGE{i}FID",  f"Edge{i}FID"),
            _fld_map.get(f"EDGE{i}POS",  f"Edge{i}Pos"),
        ]
    read_fields.append("OID@")
    oid_idx = len(read_fields) - 1

    # Insert fields match read fields
    insert_fields = ["SHAPE@"]
    for i in edge_slots:
        insert_fields += [f"Edge{i}FCID", f"Edge{i}FID", f"Edge{i}Pos"]
    if has_node:
        insert_fields.append("NODE_")

    # Offset into row where edge slot data begins (after SHAPE@ and optional NODE_)
    edge_data_offset = 2 if has_node else 1

    # ------------------------------------------------------------------
    # 8. Remap turns
    # ------------------------------------------------------------------
    logger.info("Remapping turn edge references...")

    written  = 0
    skipped  = 0
    no_match = []  # OIDs of turns that could not be remapped

    with arcpy.da.SearchCursor(OLD_TURN_FC, read_fields) as read_cur, \
         arcpy.da.InsertCursor(NEW_TURN_FC, insert_fields) as ins_cur:

        for row in read_cur:
            row      = list(row)
            shape    = row[0]
            node_val = row[1] if has_node else None
            turn_oid = row[oid_idx]

            new_row = [shape]
            valid   = True

            for idx, i in enumerate(edge_slots):
                base      = edge_data_offset + idx * 3
                old_fid   = row[base + 1]
                old_pos   = row[base + 2]

                # No more edges in this turn record
                if old_fid is None or old_fid == 0:
                    new_row += [None, None, None]
                    continue

                new_fid = find_new_oid(
                    old_fid, old_pos, old_geoms, new_endpoint_index, SNAP_TOLERANCE
                )

                if new_fid is None:
                    if i == 1:
                        # First edge is required; cannot write this turn
                        valid = False
                        break
                    else:
                        # Subsequent edge unresolved -- write None and continue
                        new_row += [None, None, None]
                        continue

                new_row += [new_edge_fcid, new_fid, old_pos]

            if not valid:
                skipped += 1
                no_match.append(turn_oid)
                continue

            if has_node:
                new_row.append(node_val)

            ins_cur.insertRow(new_row)
            written += 1

    # ------------------------------------------------------------------
    # 9. Summary
    # ------------------------------------------------------------------
    total = written + skipped
    skip_pct = (skipped / total * 100) if total > 0 else 0

    logger.info("=" * 50)
    logger.info("Remap complete")
    logger.info(f"  Total input turns : {total}")
    logger.info(f"  Written           : {written}")
    logger.info(f"  Skipped           : {skipped} ({skip_pct:.1f}%)")
    logger.info("=" * 50)
    if no_match:
        logger.debug(f"Skipped old turn OIDs (from {OLD_TURN_FC}): {no_match}")

    if skip_pct > 5:
        logger.warning(
            "Skipped rate exceeds 5%. Consider widening SNAP_TOLERANCE "
            "or inspecting skipped turns manually before proceeding. "
            "Skipped OID list is in the log file (debug level)."
        )

    # ------------------------------------------------------------------
    # 10. Optional: swap old turn FC for new and rebuild network
    # ------------------------------------------------------------------
    if AUTO_SWAP_AND_REBUILD:
        if skipped / total > 0.05:
            logger.warning("Skipped rate > 5% -- aborting auto swap. Review output first.")
            return

        logger.info("AUTO_SWAP_AND_REBUILD is True -- swapping turn FCs and rebuilding...")

        logger.info(f"  Deleting {OLD_TURN_FC_FINAL}...")
        arcpy.management.Delete(OLD_TURN_FC_FINAL)

        logger.info(f"  Renaming {NEW_TURN_FC} -> TRNLRS_traffic_turn...")
        arcpy.management.Rename(NEW_TURN_FC, "TRNLRS_traffic_turn")

        logger.info(f"  Rebuilding {NEW_NETWORK}...")
        arcpy.na.BuildNetwork(NEW_NETWORK)

        message_count = arcpy.GetMessageCount()
        severity_counts = {0: 0, 1: 0, 2: 0}
        for i in range(message_count):
            severity = arcpy.GetSeverity(i)
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        logger.info(
            f"BuildNetwork messages: {message_count} total "
            f"({severity_counts.get(2, 0)} errors, {severity_counts.get(1, 0)} warnings) "
            "-- full detail in the log file"
        )
        logger.debug(f"BuildNetwork full messages:\n{arcpy.GetMessages()}")

        logger.info("Done. Check the BuildNetwork messages above for any remaining errors.")
    else:
        logger.info("AUTO_SWAP_AND_REBUILD is False.")
        logger.info(f"Review the output FC before committing: {NEW_TURN_FC}")
        logger.info(
            "To complete the swap manually: "
            f"1) arcpy.management.Delete(r'{OLD_TURN_FC_FINAL}') "
            f"2) arcpy.management.Rename(r'{NEW_TURN_FC}', 'TRNLRS_traffic_turn') "
            f"3) arcpy.na.BuildNetwork(r'{NEW_NETWORK}')"
        )


if __name__ == "__main__":
    main()
