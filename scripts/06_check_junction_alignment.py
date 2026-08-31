"""
06_check_junction_alignment.py

Read-only diagnostic. Finds locations where TRNLRS_TRN_STREET edge endpoints do
not coincide with active Route Intersection Class points, and writes the
misaligned pairs to a point FC and a line FC for review in Pro.

Background
----------
Route Intersection Class is generated directly from LRSN_Route geometry via
GenerateIntersections and represents where LRS considers two routes to cross.
TRNLRS_TRN_STREET is reconstructed from route measures via OverlayEvents. Spot
checks (Blowers/Barrington, Barrington/Salter, Upper Water/Hollis) found the
edge source consistently offset from the route intersection point at real
intersections, all in a similar direction and magnitude. This script checks
that pattern city-wide rather than at a handful of hand-picked locations.

This does not touch source data. It only reads TRNLRS_TRN_STREET and Route
Intersection Class, and writes two new output FCs.

Method
------
1. Read active Route Intersection Class points (TODATE IS NULL).
2. Build an in-memory point FC of every TRNLRS_TRN_STREET edge endpoint
   (firstPoint and lastPoint per feature), matching the endpoint model used by
   05_rebuild_traffic_turns.py.
3. GenerateNearTable from intersection points to edge endpoints (closest
   match within SEARCH_RADIUS).
4. Anything farther than ALIGNMENT_TOLERANCE from its nearest edge endpoint
   is written out as a misaligned pair, points and connecting lines, with the
   offset distance, dx/dy vector, and a severity band.
5. Active intersections with no edge endpoint at all within SEARCH_RADIUS are
   logged separately and written with a NO_MATCH band, since that likely
   means a missing junction rather than a small offset.

Output
------
Two feature classes inside SDEADM.TRNLRS_network (the FD-separation FD, not
SDEADM.TRNLRS -- avoids the branch-versioning edit-session requirement
documented for direct-cursor writes into SDEADM.TRNLRS):
    - TRNLRS_junction_offset_points
    - TRNLRS_junction_offset_lines

Both carry INTERSECTIONID, INTERSECTIONNAME, ROUTEID, EDGE_OID, DIST_M, DX,
DY, and BAND. The dx/dy columns are for root-cause investigation (a
consistent vector across many locations points to a systematic transform or
calibration issue rather than isolated bad measures); DIST_M and BAND are
what Mel needs to see severity at a glance.

Usage
-----
1. Set configuration variables below.
2. Run from an ArcGIS Pro Python environment (arcpy required).
3. Review the summary printed on completion, then open the two output FCs
   in Pro. Sort/symbolize TRNLRS_junction_offset_points by BAND.
"""

import arcpy
import math

from log_utils import setup_logger

logger = setup_logger("06_check_junction_alignment")

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

# QA: network source FCs live in SDEADM.TRNLRS_network (moved out of
# SDEADM.TRNLRS by scripts/06_migrate_network_fd.py).
arcpy.env.overwriteOutput = True

SDE        = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"
NETWORK_FD = r"SDEADM.TRNLRS_network"
LRS_FD     = r"SDEADM.TRNLRS"

ROUTE_INTERSECTION_FC = SDE + rf"\{LRS_FD}\SDEADM.INT_RouteOnRoute"
EDGE_FC               = SDE + rf"\{NETWORK_FD}\SDEADM.TRNLRS_TRN_STREET"

OUT_POINTS_NAME = "TRNLRS_junction_offset_points"
OUT_LINES_NAME  = "TRNLRS_junction_offset_lines"
OUT_POINTS_FC   = SDE + rf"\{NETWORK_FD}\{OUT_POINTS_NAME}"
OUT_LINES_FC    = SDE + rf"\{NETWORK_FD}\{OUT_LINES_NAME}"

# How far GenerateNearTable will look for a candidate edge endpoint. Widen if
# NO_MATCH count is unexpectedly high.
SEARCH_RADIUS = "10 Meters"

# Below this distance, a pair is considered aligned and is not written out.
ALIGNMENT_TOLERANCE = 0.01

# Severity bands for the BAND field, in metres. Anything past the last
# threshold falls in the final band.
DISTANCE_BANDS = [
    (0.5, "UNDER_0.5M"),
    (2.0, "0.5_TO_2M"),
    (5.0, "2_TO_5M"),
    (float("inf"), "OVER_5M"),
]


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def band_for_distance(dist):
    for threshold, label in DISTANCE_BANDS:
        if dist <= threshold:
            return label
    return DISTANCE_BANDS[-1][1]


def build_edge_endpoint_fc(edge_fc, out_name, spatial_ref):
    """
    Create an in-memory point FC, one point per edge endpoint (firstPoint and
    lastPoint for every feature in edge_fc). Carries EDGE_OID and END_TYPE
    (FROM / TO) so a matched point can be traced back to its source edge.
    Read-only against edge_fc.
    """
    out_fc = arcpy.management.CreateFeatureclass(
        out_path="memory",
        out_name=out_name,
        geometry_type="POINT",
        spatial_reference=spatial_ref,
    )[0]

    arcpy.management.AddField(out_fc, "EDGE_OID", "LONG")
    arcpy.management.AddField(out_fc, "END_TYPE", "TEXT", field_length=4)

    with arcpy.da.SearchCursor(edge_fc, ["OID@", "SHAPE@"]) as read_cur, \
         arcpy.da.InsertCursor(out_fc, ["SHAPE@", "EDGE_OID", "END_TYPE"]) as ins_cur:

        for oid, shape in read_cur:
            if shape is None:
                continue
            for pt, end_type in ((shape.firstPoint, "FROM"), (shape.lastPoint, "TO")):
                if pt is None:
                    continue
                ins_cur.insertRow([pt, oid, end_type])

    return out_fc


def create_output_fc(out_fc_path, geometry_type, spatial_ref):
    out_path, out_name = out_fc_path.rsplit("\\", 1)
    arcpy.management.CreateFeatureclass(
        out_path=out_path,
        out_name=out_name,
        geometry_type=geometry_type,
        spatial_reference=spatial_ref,
    )
    arcpy.management.AddField(out_fc_path, "INTERSECTIONID", "TEXT", field_length=38)
    arcpy.management.AddField(out_fc_path, "INTERSECTIONNAME", "TEXT", field_length=1000)
    arcpy.management.AddField(out_fc_path, "ROUTEID", "TEXT", field_length=1000)
    arcpy.management.AddField(out_fc_path, "EDGE_OID", "LONG")
    arcpy.management.AddField(out_fc_path, "DIST_M", "DOUBLE")
    arcpy.management.AddField(out_fc_path, "DX", "DOUBLE")
    arcpy.management.AddField(out_fc_path, "DY", "DOUBLE")
    arcpy.management.AddField(out_fc_path, "BAND", "TEXT", field_length=20)
    return out_fc_path


# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------

def main():

    if arcpy.Exists(OUT_POINTS_FC):
        logger.error(f"{OUT_POINTS_FC} already exists. Delete or rename it before re-running.")
        return
    if arcpy.Exists(OUT_LINES_FC):
        logger.error(f"{OUT_LINES_FC} already exists. Delete or rename it before re-running.")
        return

    spatial_ref = arcpy.Describe(EDGE_FC).spatialReference

    # --------------------------------------------------------------------
    # 1. Active route intersections
    # --------------------------------------------------------------------
    logger.info("Reading active Route Intersection Class points (TODATE IS NULL)...")
    intersections = {}
    with arcpy.da.SearchCursor(
        ROUTE_INTERSECTION_FC,
        ["OID@", "SHAPE@XY", "INTERSECTIONID", "INTERSECTIONNAME", "ROUTEID"],
        where_clause="TODATE IS NULL",
    ) as cur:
        for oid, xy, int_id, int_name, route_id in cur:
            intersections[oid] = {
                "xy": xy,
                "id": int_id,
                "name": int_name,
                "route_id": route_id,
            }
    logger.info(f"  {len(intersections)} active route intersections")

    if not intersections:
        logger.warning("No active route intersections found. Nothing to check.")
        return

    # --------------------------------------------------------------------
    # 2. Edge endpoints (in-memory)
    # --------------------------------------------------------------------
    logger.info(f"Building edge endpoint index from {EDGE_FC}...")
    endpoint_fc = build_edge_endpoint_fc(EDGE_FC, "edge_endpoints", spatial_ref)
    endpoint_count = int(arcpy.management.GetCount(endpoint_fc)[0])
    logger.info(f"  {endpoint_count} edge endpoints")

    # --------------------------------------------------------------------
    # 3. Near table: intersection points -> nearest edge endpoint
    # --------------------------------------------------------------------
    logger.info(f"Running GenerateNearTable (search radius {SEARCH_RADIUS})...")
    near_table = "memory/junction_near_table"
    if arcpy.Exists(near_table):
        arcpy.management.Delete(near_table)

    arcpy.analysis.GenerateNearTable(
        in_features=ROUTE_INTERSECTION_FC,
        near_features=endpoint_fc,
        out_table=near_table,
        search_radius=SEARCH_RADIUS,
        location="LOCATION",
        closest="CLOSEST",
        method="PLANAR",
    )

    # Map near table rows back to source OID and matched edge endpoint
    near_results = {}  # intersection OID -> (near_x, near_y, near_dist, near_fid)
    with arcpy.da.SearchCursor(near_table, ["IN_FID", "NEAR_FID", "NEAR_DIST", "NEAR_X", "NEAR_Y"]) as cur:
        for in_fid, near_fid, near_dist, near_x, near_y in cur:
            near_results[in_fid] = (near_x, near_y, near_dist, near_fid)

    # Edge OID/END_TYPE for each endpoint feature OID, for lookups against near_fid
    endpoint_lookup = {}
    with arcpy.da.SearchCursor(endpoint_fc, ["OID@", "EDGE_OID", "END_TYPE"]) as cur:
        for oid, edge_oid, end_type in cur:
            endpoint_lookup[oid] = (edge_oid, end_type)

    # --------------------------------------------------------------------
    # 4. Classify: aligned / misaligned / no match
    # --------------------------------------------------------------------
    misaligned = []  # rows to write out
    no_match_ids = []
    aligned_count = 0

    for in_fid, info in intersections.items():
        orig_x, orig_y = info["xy"]

        if in_fid not in near_results:
            no_match_ids.append(info["id"])
            misaligned.append({
                "shape_from": (orig_x, orig_y),
                "shape_to": None,
                "int_id": info["id"],
                "int_name": info["name"],
                "route_id": info["route_id"],
                "edge_oid": None,
                "dist": None,
                "dx": None,
                "dy": None,
                "band": "NO_MATCH",
            })
            continue

        near_x, near_y, near_dist, near_fid = near_results[in_fid]

        if near_dist <= ALIGNMENT_TOLERANCE:
            aligned_count += 1
            continue

        edge_oid, end_type = endpoint_lookup.get(near_fid, (None, None))
        dx = near_x - orig_x
        dy = near_y - orig_y

        misaligned.append({
            "shape_from": (orig_x, orig_y),
            "shape_to": (near_x, near_y),
            "int_id": info["id"],
            "int_name": info["name"],
            "route_id": info["route_id"],
            "edge_oid": edge_oid,
            "dist": near_dist,
            "dx": dx,
            "dy": dy,
            "band": band_for_distance(near_dist),
        })

    # --------------------------------------------------------------------
    # 5. Write outputs
    # --------------------------------------------------------------------
    logger.info(f"Creating output point FC: {OUT_POINTS_FC}")
    create_output_fc(OUT_POINTS_FC, "POINT", spatial_ref)

    logger.info(f"Creating output line FC: {OUT_LINES_FC}")
    create_output_fc(OUT_LINES_FC, "POLYLINE", spatial_ref)

    point_fields = ["SHAPE@XY", "INTERSECTIONID", "INTERSECTIONNAME", "ROUTEID",
                     "EDGE_OID", "DIST_M", "DX", "DY", "BAND"]
    line_fields = ["SHAPE@", "INTERSECTIONID", "INTERSECTIONNAME", "ROUTEID",
                    "EDGE_OID", "DIST_M", "DX", "DY", "BAND"]

    # Two separate passes, not nested -- SDE does not allow two concurrent
    # edit transactions against the same workspace connection, so opening
    # both InsertCursors at once (points and lines are both in NETWORK_FD,
    # same SDE connection) raises "workspace already in transaction mode".
    logger.info("Writing points...")
    with arcpy.da.InsertCursor(OUT_POINTS_FC, point_fields) as pt_cur:
        for row in misaligned:
            pt_cur.insertRow([
                row["shape_from"], row["int_id"], row["int_name"], row["route_id"],
                row["edge_oid"], row["dist"], row["dx"], row["dy"], row["band"],
            ])

    logger.info("Writing lines...")
    with arcpy.da.InsertCursor(OUT_LINES_FC, line_fields) as ln_cur:
        for row in misaligned:
            if row["shape_to"] is None:
                continue
            line_geom = arcpy.Polyline(
                arcpy.Array([arcpy.Point(*row["shape_from"]), arcpy.Point(*row["shape_to"])]),
                spatial_ref,
            )
            ln_cur.insertRow([
                line_geom, row["int_id"], row["int_name"], row["route_id"],
                row["edge_oid"], row["dist"], row["dx"], row["dy"], row["band"],
            ])

    # --------------------------------------------------------------------
    # 6. Summary
    # --------------------------------------------------------------------
    band_counts = {}
    dx_vals, dy_vals = [], []
    for row in misaligned:
        band_counts[row["band"]] = band_counts.get(row["band"], 0) + 1
        if row["dx"] is not None:
            dx_vals.append(row["dx"])
            dy_vals.append(row["dy"])

    logger.info("=" * 50)
    logger.info("Alignment check complete")
    logger.info(f"  Active intersections checked : {len(intersections)}")
    logger.info(f"  Aligned (<= {ALIGNMENT_TOLERANCE}m)         : {aligned_count}")
    logger.info(f"  Misaligned                   : {len(misaligned) - len(no_match_ids)}")
    logger.info(f"  No edge endpoint within radius: {len(no_match_ids)}")
    for _, label in DISTANCE_BANDS:
        logger.info(f"    {label:12s}: {band_counts.get(label, 0)}")
    logger.info(f"    NO_MATCH    : {band_counts.get('NO_MATCH', 0)}")

    if dx_vals:
        mean_dx = sum(dx_vals) / len(dx_vals)
        mean_dy = sum(dy_vals) / len(dy_vals)
        spread_dx = math.sqrt(sum((v - mean_dx) ** 2 for v in dx_vals) / len(dx_vals))
        spread_dy = math.sqrt(sum((v - mean_dy) ** 2 for v in dy_vals) / len(dy_vals))
        logger.info(f"  Mean offset vector (dx, dy)   : ({mean_dx:.3f}, {mean_dy:.3f})")
        logger.info(f"  Std dev of offset (dx, dy)    : ({spread_dx:.3f}, {spread_dy:.3f})")
        logger.info(
            "  A small std dev relative to the mean means most offsets point the same "
            "direction and distance -- consistent with a systematic transform or "
            "calibration issue rather than isolated bad measures."
        )
    logger.info("=" * 50)
    logger.info(f"Review output: {OUT_POINTS_FC}")
    logger.info(f"Review output: {OUT_LINES_FC}")
    logger.info("Sort/symbolize the point FC by BAND to prioritize review with Mel.")


if __name__ == "__main__":
    main()