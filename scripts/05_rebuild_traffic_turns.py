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

This script resolves the mismatch by locating each turn's junction geometrically --
the endpoint shared by consecutive old edges -- and matching it to coincident
endpoints in TRNLRS_TRN_STREET, then writing a new turn FC with corrected OID
references.

How the junction is identified (rewritten 2026-08-31)
-----------------------------------------------------
Earlier versions inferred the junction from Edge{N}Pos ("pos < 0.5 means the
junction is at the old edge's firstPoint"). That reading of Edge{N}Pos is wrong.
In the Esri turn schema Edge{N}Pos identifies *which edge element* of the edge
feature the turn uses, expressed as the relative position of that element's
midpoint along the feature -- an edge feature that is not split into multiple
elements canonically carries 0.5. It does not encode which end of the edge the
junction sits at. network_template.xml sets ClassConnectivity = 1 (endpoint), so
edge features are not split at interior junctions and every Pos collapses to the
same value, which made the old test degenerate to a constant.

The junction is now derived from geometry alone, which is correct under either
reading of Edge{N}Pos: for a turn traversing E1 -> E2 -> ... -> En, the junction
between consecutive edges is the endpoint their geometries share. Edge1End is then
derived from the *matched new* Edge1 ("Y" if the junction is at its lastPoint,
"N" if at its firstPoint) rather than from the old edge, because the new LRS
segment may be digitised in the opposite direction to the old one.

The source Edge1End value is read purely as an integrity check: it is compared
against the junction this script derives on the *old* Edge1, and the agreement
rate is logged. A low agreement rate means the geometric junction detection is
disagreeing with the authoritative source value and the run should not be trusted.

Divided-road tie-break (fixed 2026-08-31)
------------------------------------------
Run against QA, the Edge1End integrity check above came back at 70.9% (846/1194)
-- well below the swap threshold. Diagnosis (scripts/diagnose_edge1end_disagreement.py)
found 345 of the 348 disagreements shared one exact signature: Edge1 and Edge2 tied
at 0.0m on BOTH possible endpoint pairings simultaneously (Edge1.first~Edge2.last
AND Edge1.last~Edge2.first). That happens when two edges are digitised between the
same pair of cross-street nodes -- e.g. the two carriageways of a divided road --
and it is a genuine structural ambiguity, not noise: both ends of Edge1 touch Edge2
equally, so no distance-based tie-break can tell them apart. A fixed
closest-candidate rule resolves every such tie the same way regardless of which end
this specific turn is actually about, and every sampled case showed that fixed
choice disagreeing with the source's own (correct) Edge1End.

The turn record's own SHAPE is not ambiguous, though -- it is a point placed by
whoever authored the turn at the real physical junction. shared_endpoint() now
takes that point as a tie-break hint for the Edge1/Edge2 junction specifically:
with a single candidate the hint is irrelevant, but when candidates tie, the one
closest to the turn's own recorded point wins. Not extended to junctions beyond
the first (3+ edge turns) -- Esri's exact multipoint-per-junction geometry
convention for those has not been confirmed against real data, so those junctions
keep the prior (unhinted) behaviour rather than guess at an unverified assumption.

Usage
-----
1. Set configuration variables below.
2. Run from an ArcGIS Pro Python environment (arcpy required).
3. Review the written/skipped summary printed on completion. Skips are broken out
   by reason; the per-reason OID lists are in the log file at DEBUG level.
4. If the skip counts are acceptable, run the swap block at the bottom to replace
   the old turn FC and rebuild the network.

Output
------
Creates TRNLRS_traffic_turn_staging inside NETWORK_FD. It is created via
in_template_feature_class (schema copied from the current TRNLRS_traffic_turn),
NOT in_network_dataset -- passing in_network_dataset to CreateTurnFeatureClass
actually registers the output as a live turn source of that network dataset,
which makes it a "controller dataset" participant that ArcGIS refuses to
delete or rename (ERROR 001919) until the network dataset itself is deleted.
Using in_template_feature_class gets the same Edge{N}FCID/FID/Pos schema
without that side effect, so the output FC stays freely disposable until you
deliberately swap it in. The old TRNLRS_traffic_turn is not touched until the
optional swap step at the end -- and that step, too, must delete the network
dataset first, because the CURRENT TRNLRS_traffic_turn is itself a registered
turn source and subject to the same lock.

See docs/network_traffic_turns.md for the original diagnosis and post-run steps,
and docs/network_dataset_script_review.md for the reasoning behind the
2026-08-31 rewrite of the junction/Edge1End logic.
"""

import math
import sys

import arcpy

from log_utils import setup_logger

logger = setup_logger("05_rebuild_traffic_turns")

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

# QA: active. The network source FCs live in SDEADM.TRNLRS_network in both Dev
# and QA (see docs/network_build_status.md, feature dataset separation).
# scripts/03_create_network_dataset.py must point at the SAME environment --
# run_full_network_rebuild.py asserts that before it does anything.
SDE        = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"
NETWORK_FD = r"SDEADM.TRNLRS_network"

# Dev: uncomment to point this script at Dev instead of QA (and change
# SDE_CONNECTION_UPDATE in 03_create_network_dataset.py to match).
# SDE        = r"E:\HRM\Scripts\SDE\SQL\Dev\dev_RW_sdeadm.sde"

# Prod: network source FCs still live in SDEADM.TRNLRS -- the FD separation
# pilot has not been applied there yet, and no network dataset has been built
# there. Do not use until the prod cutover is planned.
# SDE        = r"E:\HRM\Scripts\SDE\SQL\Prod\prod_RW_sdeadm.sde"
# NETWORK_FD = r"SDEADM.TRNLRS"

OLD_TURN_FC       = SDE + r"\SDEADM.TRN_streets_routes\SDEADM.TRN_traffic_turn"
OLD_EDGE_FC       = SDE + r"\SDEADM.TRN_streets_routes\SDEADM.TRN_street"
NEW_EDGE_FC       = SDE + rf"\{NETWORK_FD}\SDEADM.TRNLRS_TRN_STREET"
NEW_TURN_FC       = SDE + rf"\{NETWORK_FD}\SDEADM.TRNLRS_traffic_turn_staging"
OLD_TURN_FC_FINAL = SDE + rf"\{NETWORK_FD}\SDEADM.TRNLRS_traffic_turn"
NEW_NETWORK       = SDE + rf"\{NETWORK_FD}\SDEADM.TRNLRS_street_network"

# Edge source name, used only in log messages below. The FCID itself is read
# directly from the edge FC's own DSID (arcpy.Describe(NEW_EDGE_FC).DSID), not
# looked up by name from a template or a live network's source list -- see the
# comment at Section 5 for why those approaches were wrong.
EDGE_SOURCE_NAME = "TRNLRS_TRN_STREET"

# Snap tolerance in map units (metres). Turn junctions must fall within this
# distance of a new edge endpoint to be matched. Widen if skipped count is
# unexpectedly high; tighten if intersections are very closely spaced.
SNAP_TOLERANCE = 0.5

# Edge{N}Pos written to every resolved slot. Under endpoint connectivity
# (ClassConnectivity = 1 in network_template.xml) an edge feature is never split
# into multiple edge elements, so the single element's midpoint -- 0.5 -- is the
# canonical position. The old record's Pos value refers to a different feature
# and is deliberately NOT carried across. If the network is ever changed to
# any-vertex connectivity this needs revisiting.
NEW_EDGE_POS = 0.5

# Below this agreement rate between the source Edge1End value and the junction
# this script derives on the old Edge1, the run is treated as untrustworthy and
# the automatic swap is refused. See the module docstring.
MIN_EDGE1END_AGREEMENT = 0.95

# Set to True to delete OLD_TURN_FC_FINAL, rename NEW_TURN_FC, and rebuild the
# network automatically after a successful remap. Set to False to review the
# output first before committing.
AUTO_SWAP_AND_REBUILD = False


# ------------------------------------------------------------------------------
# Geometry helpers
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


def points_equal(pt_a, pt_b, tolerance):
    """True if two points are within tolerance of each other."""
    if pt_a is None or pt_b is None:
        return False
    return math.hypot(pt_a.X - pt_b.X, pt_a.Y - pt_b.Y) <= tolerance


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


def shared_endpoint(geom_a, geom_b, tolerance, hint_pt=None):
    """
    Return the endpoint shared by two polylines -- the turn junction between two
    consecutive edges of a turn -- or None if they do not meet end to end.

    Two edges can share BOTH endpoints -- e.g. the two carriageways of a divided
    road, each digitised as its own line between the same pair of cross-street
    nodes. When that happens, a plain closest-candidate tie-break has no
    geometric basis to prefer one shared endpoint over the other, and resolves
    every such tie the same way regardless of which end a given turn is
    actually about. Confirmed 2026-08-31 against real QA data: this exact
    signature (both pairings tied at 0.0m) accounted for 345 of 348 Edge1End
    integrity-check disagreements, all resolving to the same wrong answer.

    hint_pt, when given, is the turn's OWN recorded junction point -- placed by
    whoever authored the turn at the real physical location, so it carries no
    such ambiguity. With a single candidate it is irrelevant; with more than
    one tied within tolerance, the candidate closest to hint_pt wins. With no
    hint, falls back to the closest candidate exactly as before (first
    encountered on a tie, via Python's stable min()).
    """
    if geom_a is None or geom_b is None:
        return None

    candidates = []
    for pt_a in (geom_a.firstPoint, geom_a.lastPoint):
        for pt_b in (geom_b.firstPoint, geom_b.lastPoint):
            if pt_a is None or pt_b is None:
                continue
            dist = math.hypot(pt_a.X - pt_b.X, pt_a.Y - pt_b.Y)
            if dist <= tolerance:
                candidates.append((pt_a, dist))

    if not candidates:
        return None
    if len(candidates) == 1 or hint_pt is None:
        return min(candidates, key=lambda c: c[1])[0]

    return min(
        candidates,
        key=lambda c: math.hypot(c[0].X - hint_pt.X, c[0].Y - hint_pt.Y),
    )[0]


def tangent_at(geom, junction_pt, tolerance):
    """
    Bearing in radians from junction_pt into geom, measured to the first vertex
    more than `tolerance` away from the junction.

    This is the local direction of the street at the intersection. It replaces
    the previous whole-edge chord bearing (firstPoint -> lastPoint), which is a
    poor proxy on curved or long streets -- and LRS resegmentation makes the new
    edges much shorter than the old ones, so the two are not comparable.

    Returns None if neither end of geom is at junction_pt.
    """
    if geom is None:
        return None

    pts = [pt for part in geom for pt in part if pt is not None]
    if len(pts) < 2:
        return None

    if points_equal(pts[0], junction_pt, tolerance):
        sequence = pts
    elif points_equal(pts[-1], junction_pt, tolerance):
        sequence = list(reversed(pts))
    else:
        return None

    origin = sequence[0]
    for pt in sequence[1:]:
        if math.hypot(pt.X - origin.X, pt.Y - origin.Y) > tolerance:
            return math.atan2(pt.Y - origin.Y, pt.X - origin.X)
    return None


def candidate_edges_at(junction_pt, endpoint_index, new_geoms, tolerance):
    """
    Return the OIDs of new edges with an endpoint at junction_pt.

    Checks the 3x3 neighbourhood of grid cells around the junction rather than
    the single cell it rounds into -- a junction landing near a cell boundary
    can otherwise round away from an edge endpoint that is well within
    tolerance, producing a false skip. Candidates are then filtered by true
    distance, so widening the cell search does not loosen the match.
    """
    base_x, base_y = point_key(junction_pt, tolerance)
    seen = set()
    candidates = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            key = (base_x + dx * tolerance, base_y + dy * tolerance)
            for oid in endpoint_index.get(key, []):
                if oid in seen:
                    continue
                seen.add(oid)
                geom = new_geoms.get(oid)
                if geom is None:
                    continue
                if (points_equal(geom.firstPoint, junction_pt, tolerance)
                        or points_equal(geom.lastPoint, junction_pt, tolerance)):
                    candidates.append(oid)
    return candidates


def resolve_new_edge(junction_pt, old_geom, endpoint_index, new_geoms, tolerance):
    """
    Find the new edge that carries the turn through junction_pt, matching the
    direction the old edge ran at that junction.

    Returns the new edge OID, or None if nothing coincides with the junction.
    """
    candidates = candidate_edges_at(junction_pt, endpoint_index, new_geoms, tolerance)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    # Multiple candidates share this endpoint (multi-leg intersection). Compare
    # the local bearing of each candidate against the local bearing of the old
    # edge at the same junction. Best effort -- very complex intersections may
    # still need manual review (see docs/traffic_turn_staging_review_checklist.txt).
    old_angle = tangent_at(old_geom, junction_pt, tolerance)
    if old_angle is None:
        return candidates[0]

    best_oid = None
    best_diff = None
    for oid in candidates:
        cand_angle = tangent_at(new_geoms.get(oid), junction_pt, tolerance)
        if cand_angle is None:
            continue
        diff = abs(math.atan2(
            math.sin(cand_angle - old_angle),
            math.cos(cand_angle - old_angle),
        ))
        if best_diff is None or diff < best_diff:
            best_oid, best_diff = oid, diff

    return best_oid if best_oid is not None else candidates[0]


def edge_end_flag(new_geom, junction_pt, tolerance):
    """
    Esri Edge1End for the matched new Edge1: "Y" if the turn passes through the
    end (lastPoint) of the edge, "N" if through the beginning (firstPoint).

    Derived from the NEW edge, not the old one -- the new LRS segment may be
    digitised in the opposite direction to the old edge it replaces, which would
    invert the flag. Returns None if the junction is at neither end.
    """
    if new_geom is None:
        return None
    if points_equal(new_geom.lastPoint, junction_pt, tolerance):
        return "Y"
    if points_equal(new_geom.firstPoint, junction_pt, tolerance):
        return "N"
    return None


# ------------------------------------------------------------------------------
# Diagnostics
# ------------------------------------------------------------------------------

def log_source_edge1_distribution(turn_fc, fld_map):
    """
    Log the distribution of Edge1Pos and Edge1End on the source turn FC.

    This is the evidence for why the junction is derived from geometry rather
    than from Edge1Pos: if Edge1Pos is a single repeated value (0.5 is the
    canonical position for an unsplit edge feature), it carries no information
    about which end of the edge the junction is at.
    """
    fields = []
    if "EDGE1POS" in fld_map:
        fields.append(fld_map["EDGE1POS"])
    if "EDGE1END" in fld_map:
        fields.append(fld_map["EDGE1END"])
    if not fields:
        logger.warning("Source turn FC has neither Edge1Pos nor Edge1End -- skipping distribution check.")
        return

    counts = [{} for _ in fields]
    with arcpy.da.SearchCursor(turn_fc, fields) as cur:
        for row in cur:
            for i, value in enumerate(row):
                key = round(value, 3) if isinstance(value, float) else value
                counts[i][key] = counts[i].get(key, 0) + 1

    for name, tally in zip(fields, counts):
        top = sorted(tally.items(), key=lambda kv: -kv[1])[:10]
        logger.info(f"  {name} distribution (top {len(top)}): {top}")


# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------

def main():
    # Validate inputs. NEW_NETWORK is intentionally NOT required here -- the
    # FCID is read from the edge FC's own DSID (Section 5), so this script can
    # run during a clean rebuild, before any network dataset exists.
    for path, label in [
        (OLD_TURN_FC,       "Old turn FC"),
        (OLD_EDGE_FC,       "Old edge FC"),
        (NEW_EDGE_FC,       "New edge FC"),
        (OLD_TURN_FC_FINAL, "Current TRNLRS_traffic_turn (used as schema template)"),
    ]:
        if not arcpy.Exists(path):
            logger.error(f"{label} not found: {path}")
            sys.exit(1)

    if arcpy.Exists(NEW_TURN_FC):
        logger.error(f"Output FC already exists: {NEW_TURN_FC}. Delete or rename it before running.")
        sys.exit(1)

    logger.info(f"Environment: {SDE}")
    logger.info(f"Network feature dataset: {NETWORK_FD}")

    # ------------------------------------------------------------------
    # 1. Index new edge endpoints
    # ------------------------------------------------------------------
    logger.info("Indexing new edge endpoints...")
    new_endpoint_index = build_endpoint_index(NEW_EDGE_FC, SNAP_TOLERANCE)
    new_edge_count = sum(len(v) for v in new_endpoint_index.values())
    logger.info(f"  {new_edge_count} endpoint entries indexed (snap tolerance: {SNAP_TOLERANCE}m)")

    # ------------------------------------------------------------------
    # 2. Build new edge geometry lookup
    # ------------------------------------------------------------------
    logger.info("Loading new edge geometries...")
    new_geoms = build_geometry_lookup(NEW_EDGE_FC)
    logger.info(f"  {len(new_geoms)} new edge features loaded")

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
    fld_map = {f.name.upper(): f.name for f in arcpy.ListFields(OLD_TURN_FC)}
    turn_field_names = list(fld_map.values())

    edge_slots = [i for i in range(1, 6) if f"EDGE{i}FID" in fld_map]
    if not edge_slots:
        logger.error(f"No Edge{{N}}FID fields found in old turn FC. Available fields: {turn_field_names}")
        sys.exit(1)
    logger.info(f"  Edge slots detected: {edge_slots}")

    has_node = "NODE_" in fld_map
    has_edge1end = "EDGE1END" in fld_map
    if not has_edge1end:
        logger.warning(
            "Source turn FC has no Edge1End field -- the integrity check comparing it "
            "against the geometrically derived junction will be skipped."
        )

    logger.info("Source Edge1Pos / Edge1End distribution:")
    log_source_edge1_distribution(OLD_TURN_FC, fld_map)

    # ------------------------------------------------------------------
    # 5. Get FCID of new edge source
    # ------------------------------------------------------------------
    # CONFIRMED WRONG (2026-07-21): both approaches previously used here
    # -- reading Describe(NEW_NETWORK).sources[i].sourceID from a live
    # network, and reading <EdgeFeatureSource><ID> from
    # network_template.xml -- report the edge source's ORDERING INDEX
    # within the network dataset (a small sequential number, "2" every
    # single time observed in this project), not the edge FC's actual
    # dataset ID. Both stayed "2" all day regardless of how many times
    # TRNLRS_TRN_STREET was deleted and recreated, which is exactly why
    # every cross-check between them kept passing while every turn 05
    # produced still failed to resolve at build time -- both numbers were
    # wrong in the same way, so they always agreed with each other.
    #
    # The value Edge{N}FCID actually needs is the edge FC's real DSID.
    # Confirmed directly: a turn created natively in Pro's turn-editing
    # tool at a live intersection resolved correctly with FCID=39618 (the
    # edge FC's actual DSID at the time), while every 05-produced turn on
    # the same build used FCID=2 and failed uniformly.
    #
    # NOTE: DSID changes whenever TRNLRS_TRN_STREET is deleted and recreated
    # (script 03's fallback copy, script 06's move, any manual drop). Re-run
    # this script after anything that recreates the edge FC, not just after
    # its geometry changes.
    logger.info(f"Reading edge source FCID (DSID) from: {NEW_EDGE_FC}")
    new_edge_fcid = arcpy.Describe(NEW_EDGE_FC).DSID
    logger.info(f"  {EDGE_SOURCE_NAME} DSID: {new_edge_fcid}")

    if new_edge_fcid is None:
        logger.error(f"Could not read DSID for {NEW_EDGE_FC}.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 6. Create new turn feature class
    # ------------------------------------------------------------------
    # Deliberately uses in_template_feature_class, NOT in_network_dataset.
    # Passing in_network_dataset registers the output as a real turn source
    # of that network dataset (a "controller dataset" relationship), which
    # then blocks Delete/Rename on it (ERROR 001919) until the network
    # dataset is deleted. in_template_feature_class copies the same schema
    # from the current TRNLRS_traffic_turn without that side effect.
    logger.info(f"Creating output turn FC: {NEW_TURN_FC}")
    out_path, out_name = NEW_TURN_FC.rsplit("\\", 1)
    arcpy.na.CreateTurnFeatureClass(
        out_location=out_path,
        out_feature_class_name=out_name,
        maximum_edges=max(edge_slots),
        in_template_feature_class=OLD_TURN_FC_FINAL,
    )

    # ------------------------------------------------------------------
    # 7. Build cursor field lists
    # ------------------------------------------------------------------
    # Read fields are indexed by name rather than by arithmetic offset, so
    # adding or reordering a field cannot silently shift the edge slot reads.
    # Edge{N}FCID is not read: the old FCID is discarded and replaced with the
    # new edge FC's DSID. Edge{N}Pos is read only for the distribution check
    # and is not carried across (see NEW_EDGE_POS).
    read_fields = ["OID@", "SHAPE@"]
    read_idx = {"oid": 0, "shape": 1}

    if has_node:
        read_idx["node"] = len(read_fields)
        read_fields.append(fld_map["NODE_"])
    if has_edge1end:
        read_idx["edge1end"] = len(read_fields)
        read_fields.append(fld_map["EDGE1END"])

    slot_fid_idx = {}
    for i in edge_slots:
        slot_fid_idx[i] = len(read_fields)
        read_fields.append(fld_map[f"EDGE{i}FID"])

    # Insert fields, in the order new_row is assembled below.
    insert_fields = ["SHAPE@", "Edge1End"]
    for i in edge_slots:
        insert_fields += [f"Edge{i}FCID", f"Edge{i}FID", f"Edge{i}Pos"]
    if has_node:
        insert_fields.append("NODE_")

    # ------------------------------------------------------------------
    # 8. Remap turns
    # ------------------------------------------------------------------
    logger.info("Remapping turn edge references...")

    written = 0
    # Every rejection reason is counted and its OIDs recorded. Previously only
    # an Edge1 miss counted as a skip: a miss on Edge2..5 wrote NULLs into that
    # slot and carried on, producing one-edge turns and gapped edge sequences
    # that are invalid at build time but were reported as successfully written.
    skips = {
        "too_few_edges":        [],  # fewer than 2 populated edge slots in the source
        "missing_old_geometry": [],  # referenced old edge OID has no geometry
        "no_shared_endpoint":   [],  # consecutive old edges do not meet end to end
        "unresolved_edge":      [],  # no new edge coincides with the junction
        "new_edge_not_spanning": [],  # matched middle edge does not reach both junctions
        "edge1end_undetermined": [],  # junction is at neither end of the matched new Edge1
    }
    edge1end_agree = 0
    edge1end_checked = 0

    with arcpy.da.SearchCursor(OLD_TURN_FC, read_fields) as read_cur, \
         arcpy.da.InsertCursor(NEW_TURN_FC, insert_fields) as ins_cur:

        for row in read_cur:
            turn_oid = row[read_idx["oid"]]
            shape    = row[read_idx["shape"]]
            node_val = row[read_idx["node"]] if has_node else None
            src_end  = row[read_idx["edge1end"]] if has_edge1end else None

            # Collect the populated edge slots, stopping at the first empty one
            # so a gap in the source is never carried into the output.
            slot_fids = []
            for i in edge_slots:
                fid = row[slot_fid_idx[i]]
                if fid is None or fid == 0:
                    break
                slot_fids.append(fid)

            if len(slot_fids) < 2:
                skips["too_few_edges"].append(turn_oid)
                continue

            slot_geoms = [old_geoms.get(fid) for fid in slot_fids]
            if any(geom is None for geom in slot_geoms):
                skips["missing_old_geometry"].append(turn_oid)
                continue

            # Junction k is where the turn crosses from edge k to edge k+1. The
            # turn's own recorded point (shape) breaks ties for the Edge1/Edge2
            # junction specifically -- see shared_endpoint's docstring and the
            # "Divided-road tie-break" module note above. Not extended to
            # junctions beyond the first: Esri's multipoint-per-junction
            # convention for 3+ edge turns hasn't been confirmed against real
            # data, so those keep the prior (unhinted) behaviour.
            edge1_hint = shape.firstPoint if shape is not None else None
            junctions = [
                shared_endpoint(
                    slot_geoms[k], slot_geoms[k + 1], SNAP_TOLERANCE,
                    hint_pt=edge1_hint if k == 0 else None,
                )
                for k in range(len(slot_geoms) - 1)
            ]
            if any(pt is None for pt in junctions):
                skips["no_shared_endpoint"].append(turn_oid)
                continue

            # Integrity check: does the source Edge1End agree with the junction
            # this script found on the OLD Edge1? (Compared on the old edge --
            # the value written to the output is derived from the new edge.)
            if has_edge1end and src_end in ("Y", "N"):
                derived_old_end = edge_end_flag(slot_geoms[0], junctions[0], SNAP_TOLERANCE)
                if derived_old_end is not None:
                    edge1end_checked += 1
                    if derived_old_end == src_end:
                        edge1end_agree += 1
                    else:
                        logger.debug(
                            f"Turn {turn_oid}: source Edge1End={src_end} but the shared "
                            f"endpoint with Edge2 is at the old edge's "
                            f"{'end' if derived_old_end == 'Y' else 'start'}."
                        )

            # Resolve each old edge to a new one, anchored at the junction where
            # the turn enters that edge (the exit junction for Edge1).
            new_fids = []
            failure = None
            for k, old_geom in enumerate(slot_geoms):
                anchor = junctions[0] if k == 0 else junctions[k - 1]
                new_fid = resolve_new_edge(
                    anchor, old_geom, new_endpoint_index, new_geoms, SNAP_TOLERANCE
                )
                if new_fid is None:
                    failure = "unresolved_edge"
                    break

                # A middle edge must reach both of its junctions -- if LRS
                # resegmentation split the old edge between them, no single new
                # edge carries the turn and the record cannot be represented.
                if 0 < k < len(slot_geoms) - 1:
                    exit_pt = junctions[k]
                    cand_geom = new_geoms.get(new_fid)
                    if not (points_equal(cand_geom.firstPoint, exit_pt, SNAP_TOLERANCE)
                            or points_equal(cand_geom.lastPoint, exit_pt, SNAP_TOLERANCE)):
                        failure = "new_edge_not_spanning"
                        break

                new_fids.append(new_fid)

            if failure:
                skips[failure].append(turn_oid)
                continue

            edge1_end = edge_end_flag(new_geoms.get(new_fids[0]), junctions[0], SNAP_TOLERANCE)
            if edge1_end is None:
                skips["edge1end_undetermined"].append(turn_oid)
                continue

            new_row = [shape, edge1_end]
            for k, i in enumerate(edge_slots):
                if k < len(new_fids):
                    new_row += [new_edge_fcid, new_fids[k], NEW_EDGE_POS]
                else:
                    new_row += [None, None, None]
            if has_node:
                new_row.append(node_val)

            ins_cur.insertRow(new_row)
            written += 1

    # ------------------------------------------------------------------
    # 9. Summary
    # ------------------------------------------------------------------
    skipped = sum(len(oids) for oids in skips.values())
    total = written + skipped
    skip_pct = (skipped / total * 100) if total > 0 else 0

    logger.info("=" * 50)
    logger.info("Remap complete")
    logger.info(f"  Total input turns : {total}")
    logger.info(f"  Written           : {written}")
    logger.info(f"  Skipped           : {skipped} ({skip_pct:.1f}%)")
    for reason, oids in skips.items():
        if oids:
            logger.info(f"    {reason:22s}: {len(oids)}")
            logger.debug(f"    {reason} old turn OIDs (from {OLD_TURN_FC}): {oids}")
    logger.info("=" * 50)

    if edge1end_checked:
        agreement = edge1end_agree / edge1end_checked
        logger.info(
            f"Edge1End integrity check: {edge1end_agree}/{edge1end_checked} "
            f"({agreement:.1%}) of source Edge1End values agree with the junction "
            "derived from geometry."
        )
        if agreement < MIN_EDGE1END_AGREEMENT:
            logger.warning(
                f"Edge1End agreement is below {MIN_EDGE1END_AGREEMENT:.0%}. The geometric "
                "junction detection is disagreeing with the source's own Edge1End values "
                "-- do NOT swap this output in until that is understood. Disagreeing turn "
                "OIDs are in the log file at debug level."
            )
    else:
        logger.warning("Edge1End integrity check did not run (no comparable source values).")

    if skip_pct > 5:
        logger.warning(
            "Skipped rate exceeds 5%. Consider widening SNAP_TOLERANCE "
            "or inspecting skipped turns manually before proceeding. "
            "Per-reason OID lists are in the log file (debug level)."
        )

    # ------------------------------------------------------------------
    # 10. Optional: swap old turn FC for new, then recreate/rebuild the network
    # ------------------------------------------------------------------
    # NOTE: TRNLRS_traffic_turn is itself a registered turn source of
    # TRNLRS_street_network (defined in data/network_template.xml), which
    # makes it a "controller dataset" participant -- ArcGIS refuses to
    # Delete or Rename it (ERROR 001919: "cannot be deleted because it
    # participates in a controller dataset") while the network dataset still
    # references it. There is no arcpy call to unregister a single source
    # from an existing network dataset -- the network dataset itself must be
    # deleted first to release the lock on ALL its sources, then recreated
    # from the template afterward (see scripts/03_create_network_dataset.py,
    # which is idempotent and will just recreate + rebuild the network
    # dataset since the three source FCs already exist).
    if AUTO_SWAP_AND_REBUILD:
        if total == 0:
            logger.warning("No input turns were read -- aborting auto swap.")
            return
        if skip_pct > 5:
            logger.warning("Skipped rate > 5% -- aborting auto swap. Review output first.")
            return
        if edge1end_checked and (edge1end_agree / edge1end_checked) < MIN_EDGE1END_AGREEMENT:
            logger.warning("Edge1End agreement below threshold -- aborting auto swap.")
            return

        logger.info("AUTO_SWAP_AND_REBUILD is True -- swapping turn FCs...")

        logger.info(f"  Deleting network dataset {NEW_NETWORK} (releases the controller-dataset lock)...")
        arcpy.management.Delete(NEW_NETWORK)

        logger.info(f"  Deleting {OLD_TURN_FC_FINAL}...")
        arcpy.management.Delete(OLD_TURN_FC_FINAL)

        logger.info(f"  Renaming {NEW_TURN_FC} -> TRNLRS_traffic_turn...")
        arcpy.management.Rename(NEW_TURN_FC, "TRNLRS_traffic_turn")

        logger.info(
            "Turn FC swap complete. The network dataset was deleted and must be recreated: "
            "run scripts/03_create_network_dataset.py to recreate TRNLRS_street_network "
            "from the template and rebuild it (it will skip re-copying the three source "
            "FCs since they already exist, and go straight to create + build)."
        )
    else:
        logger.info("AUTO_SWAP_AND_REBUILD is False.")
        logger.info(f"Review the output FC before committing: {NEW_TURN_FC}")
        logger.info(
            "To complete the swap manually, in this order "
            "(TRNLRS_traffic_turn is a registered network source and cannot be deleted "
            "or renamed while the network dataset exists -- delete it first): "
            f"1) arcpy.management.Delete(r'{NEW_NETWORK}') "
            f"2) arcpy.management.Delete(r'{OLD_TURN_FC_FINAL}') "
            f"3) arcpy.management.Rename(r'{NEW_TURN_FC}', 'TRNLRS_traffic_turn') "
            "4) Run scripts/03_create_network_dataset.py to recreate and rebuild the network dataset."
        )


if __name__ == "__main__":
    main()
