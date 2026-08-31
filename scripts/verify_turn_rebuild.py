"""
verify_turn_rebuild.py

Validates a turn feature class against the edge source it references, WITHOUT
needing a network dataset to exist or a build to have run.

Every regression this project has hit -- the unremapped OIDs (2026-07-07), the
TRNLRS_network fallback copy (2026-07-14), FCID=2 instead of the edge FC's DSID
(2026-07-21), and unset/incorrect Edge1End -- is detectable from the turn FC and
the edge FC alone. Each was instead found days or weeks later by reading a
BuildErrors file. These checks close that gap: run this on
TRNLRS_traffic_turn_staging before swapping it in, and again on the live
TRNLRS_traffic_turn after the swap.

The geometry helpers here are deliberately re-implemented rather than imported
from 05_rebuild_traffic_turns.py. A verifier that shares its logic with the
writer agrees with the writer by construction, including when both are wrong --
which is exactly how the FCID=2 bug survived a cross-check for a full day.

Checks
------
1.  Turn FC is non-empty.
2.  Edge{N}FCID has a single distinct value and it equals the edge FC's DSID.
3.  Edge{N}Pos values (reported; 0.5 expected under endpoint connectivity).
4.  Edge1End is a mix of Y and N -- an all-Y or all-N column is the signature of
    a value derived from a constant rather than from geometry.
5.  Edge1 and Edge2 are populated on every row (a turn needs >= 2 edges).
6.  No gaps in the edge slot sequence.
7.  Every Edge{N}FID exists in the edge FC.
8.  Consecutive referenced edges share an endpoint -- i.e. the turn describes a
    real path through a real intersection.
9.  Edge1End agrees with the geometry: "Y" iff the junction with Edge2 is at
    Edge1's lastPoint, "N" iff at its firstPoint.
10. No two records resolve to the identical (Edge{N}FID..., Edge1End) signature.
    A collision here is what BuildNetwork itself rejects as "Turn element
    already exists" -- and it is a DIFFERENT problem from checks 1-9: it means
    two distinct source turn records now describe the same physical maneuver
    in the new network, most often because LRS resegmentation merged two old
    street segments into a single new edge (a turn "from segment A onto
    segment B" becomes "from an edge onto itself"). Reported as a warning, not
    a failure -- prior investigation (intermediate_results/turn_review_for_mel.csv,
    intersection_context_check_v2.csv) found this pattern at real intersections
    and consistent with legacy near-duplicate U-turn records, not a remap bug.
    Whether to keep one record per collision or drop both is an unresolved
    domain decision (intermediate_results/degenerate_turns_disambiguated.csv is
    all UNRESOLVED) -- this check surfaces the current count, it does not decide.

Checks 8 and 9 are the ones that catch a plausible-looking but wrong remap.
Check 10 catches a different failure mode entirely: correct remaps that
collide with each other post-resegmentation.

Run from ArcGIS Pro Python environment:
  > python scripts/verify_turn_rebuild.py
"""

import math
import sys
from collections import Counter

import arcpy

from log_utils import setup_logger

logger = setup_logger("verify_turn_rebuild")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SDE        = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"
NETWORK_FD = r"SDEADM.TRNLRS_network"

# Staging output of 05_rebuild_traffic_turns.py -- verify this BEFORE swapping.
TURN_FC = SDE + rf"\{NETWORK_FD}\SDEADM.TRNLRS_traffic_turn_staging"
# After the swap, re-run against the live turn FC:
# TURN_FC = SDE + rf"\{NETWORK_FD}\SDEADM.TRNLRS_traffic_turn"

EDGE_FC = SDE + rf"\{NETWORK_FD}\SDEADM.TRNLRS_TRN_STREET"

# Must match SNAP_TOLERANCE in 05_rebuild_traffic_turns.py.
TOLERANCE = 0.5

# Number of offending OIDs to print per failed check (all of them go to the log
# file at DEBUG level regardless).
SAMPLE_SIZE = 15

# Below this record count, an Edge1End column with a single distinct value is
# reported as a warning rather than a failure -- a handful of turns can
# legitimately all share one value.
MIN_RECORDS_FOR_VARIANCE = 20
# ---------------------------------------------------------------------------


class Results:
    """Collects check outcomes so a single run reports everything, not just
    the first failure -- a partial picture is what sends people back for a
    second round trip."""

    def __init__(self):
        self.failed = []
        self.warned = []

    def ok(self, name, detail=""):
        logger.info(f"  PASS   {name}{(' -- ' + detail) if detail else ''}")

    def warn(self, name, detail, oids=None):
        self.warned.append(name)
        logger.warning(f"  WARN   {name} -- {detail}")
        self._samples(name, oids)

    def fail(self, name, detail, oids=None):
        self.failed.append(name)
        logger.error(f"  FAIL   {name} -- {detail}")
        self._samples(name, oids)

    def _samples(self, name, oids):
        if not oids:
            return
        sample = sorted(oids)[:SAMPLE_SIZE]
        more = f" (+{len(oids) - len(sample)} more)" if len(oids) > len(sample) else ""
        logger.info(f"         sample OIDs: {sample}{more}")
        logger.debug(f"         all {name} OIDs: {sorted(oids)}")


def points_equal(pt_a, pt_b, tolerance):
    if pt_a is None or pt_b is None:
        return False
    return math.hypot(pt_a.X - pt_b.X, pt_a.Y - pt_b.Y) <= tolerance


def shares_endpoint(geom_a, geom_b, tolerance):
    """True if two polylines meet end to end."""
    if geom_a is None or geom_b is None:
        return False
    for pt_a in (geom_a.firstPoint, geom_a.lastPoint):
        for pt_b in (geom_b.firstPoint, geom_b.lastPoint):
            if points_equal(pt_a, pt_b, tolerance):
                return True
    return False


def junction_between(geom_a, geom_b, tolerance):
    """The endpoint two polylines share, or None."""
    if geom_a is None or geom_b is None:
        return None
    for pt_a in (geom_a.firstPoint, geom_a.lastPoint):
        for pt_b in (geom_b.firstPoint, geom_b.lastPoint):
            if points_equal(pt_a, pt_b, tolerance):
                return pt_a
    return None


def main():
    for path, label in [(TURN_FC, "Turn FC"), (EDGE_FC, "Edge FC")]:
        if not arcpy.Exists(path):
            logger.error(f"{label} not found: {path}")
            sys.exit(1)

    logger.info(f"Turn FC : {TURN_FC}")
    logger.info(f"Edge FC : {EDGE_FC}")

    results = Results()

    # -- edge source: DSID and geometry -------------------------------------
    edge_dsid = arcpy.Describe(EDGE_FC).DSID
    logger.info(f"Edge FC DSID (the value Edge{{N}}FCID must carry): {edge_dsid}")

    logger.info("Loading edge geometries...")
    edge_geoms = {}
    with arcpy.da.SearchCursor(EDGE_FC, ["OID@", "SHAPE@"]) as cur:
        for oid, shape in cur:
            edge_geoms[oid] = shape
    logger.info(f"  {len(edge_geoms):,} edge features loaded")

    # -- turn FC schema ------------------------------------------------------
    fld_map = {f.name.upper(): f.name for f in arcpy.ListFields(TURN_FC)}
    edge_slots = [i for i in range(1, 6) if f"EDGE{i}FID" in fld_map]
    if not edge_slots:
        logger.error(f"No Edge{{N}}FID fields on {TURN_FC} -- is this a turn feature class?")
        sys.exit(1)
    logger.info(f"Edge slots present: {edge_slots}")

    has_edge1end = "EDGE1END" in fld_map

    fields = ["OID@"]
    idx = {"oid": 0}
    if has_edge1end:
        idx["edge1end"] = len(fields)
        fields.append(fld_map["EDGE1END"])
    slot_idx = {}
    for i in edge_slots:
        slot_idx[i] = {}
        for suffix in ("FCID", "FID", "POS"):
            key = f"EDGE{i}{suffix}"
            if key in fld_map:
                slot_idx[i][suffix] = len(fields)
                fields.append(fld_map[key])

    # -- scan ----------------------------------------------------------------
    total = 0
    fcid_values = Counter()
    pos_values = Counter()
    end_values = Counter()

    bad_fcid = set()
    too_few_edges = set()
    gapped = set()
    dangling_fid = set()
    not_connected = set()
    bad_edge1end = set()
    no_junction = set()

    # Check 10: signature = ordered Edge{N}FID per populated slot, plus Edge1End
    # (the only per-slot End field Esri's schema provides). Under endpoint
    # connectivity Edge{N}Pos carries no discriminating information (it is
    # written as the constant 0.5 by 05_rebuild_traffic_turns.py), so it is
    # deliberately excluded here -- including it would hide real collisions.
    by_signature = {}

    with arcpy.da.SearchCursor(TURN_FC, fields) as cur:
        for row in cur:
            total += 1
            oid = row[idx["oid"]]

            populated = []
            gap_seen = False
            for i in edge_slots:
                fid = row[slot_idx[i]["FID"]] if "FID" in slot_idx[i] else None
                if fid is None or fid == 0:
                    gap_seen = True
                    continue
                if gap_seen:
                    gapped.add(oid)          # a populated slot after an empty one
                populated.append(i)

                if "FCID" in slot_idx[i]:
                    fcid = row[slot_idx[i]["FCID"]]
                    fcid_values[fcid] += 1
                    if fcid != edge_dsid:
                        bad_fcid.add(oid)
                if "POS" in slot_idx[i]:
                    pos = row[slot_idx[i]["POS"]]
                    pos_values[round(pos, 3) if isinstance(pos, float) else pos] += 1
                if fid not in edge_geoms:
                    dangling_fid.add(oid)

            if has_edge1end:
                end_values[row[idx["edge1end"]]] += 1

            if len(populated) < 2:
                too_few_edges.add(oid)
                continue

            fids_all = [row[slot_idx[i]["FID"]] for i in populated]
            sig = (tuple(fids_all), row[idx["edge1end"]] if has_edge1end else None)
            by_signature.setdefault(sig, []).append(oid)

            # -- connectivity of consecutive referenced edges -----------------
            fids = [row[slot_idx[i]["FID"]] for i in populated]
            if any(f not in edge_geoms for f in fids):
                continue                      # already counted as dangling

            for k in range(len(fids) - 1):
                if not shares_endpoint(edge_geoms[fids[k]], edge_geoms[fids[k + 1]], TOLERANCE):
                    not_connected.add(oid)

            # -- Edge1End vs geometry ----------------------------------------
            if has_edge1end and oid not in not_connected:
                junction = junction_between(edge_geoms[fids[0]], edge_geoms[fids[1]], TOLERANCE)
                if junction is None:
                    no_junction.add(oid)
                else:
                    geom1 = edge_geoms[fids[0]]
                    if points_equal(geom1.lastPoint, junction, TOLERANCE):
                        expected = "Y"
                    elif points_equal(geom1.firstPoint, junction, TOLERANCE):
                        expected = "N"
                    else:
                        expected = None
                    actual = row[idx["edge1end"]]
                    if expected is not None and actual != expected:
                        bad_edge1end.add(oid)

    # -- report --------------------------------------------------------------
    logger.info("=" * 60)
    logger.info(f"Turn records: {total:,}")
    logger.info(f"Edge{{N}}FCID values : {dict(fcid_values)}")
    logger.info(f"Edge{{N}}Pos values  : {dict(pos_values.most_common(10))}")
    if has_edge1end:
        logger.info(f"Edge1End values    : {dict(end_values)}")
    logger.info("=" * 60)

    if total == 0:
        results.fail("1. non-empty", "the turn FC has no records")
    else:
        results.ok("1. non-empty", f"{total:,} records")

    if bad_fcid:
        results.fail(
            "2. Edge{N}FCID == edge FC DSID",
            f"{len(bad_fcid)} records carry an FCID other than {edge_dsid}. "
            "A value of 2 is the 2026-07-21 ordering-index bug.",
            bad_fcid,
        )
    else:
        results.ok("2. Edge{N}FCID == edge FC DSID", f"all records carry {edge_dsid}")

    off_pos = {p: c for p, c in pos_values.items() if p != 0.5}
    if off_pos:
        results.warn(
            "3. Edge{N}Pos == 0.5",
            f"non-0.5 positions present: {off_pos}. Expected 0.5 under endpoint "
            "connectivity; investigate before trusting the remap.",
        )
    else:
        results.ok("3. Edge{N}Pos == 0.5")

    if not has_edge1end:
        results.warn("4. Edge1End varies", "no Edge1End field on this FC")
    elif len(end_values) >= 2:
        results.ok("4. Edge1End varies", f"{dict(end_values)}")
    elif total < MIN_RECORDS_FOR_VARIANCE:
        # A handful of turns can legitimately all share one value; only a
        # population-sized FC makes a single value diagnostic.
        results.warn(
            "4. Edge1End varies",
            f"every record has the same Edge1End ({dict(end_values)}), but only {total} "
            f"records -- too few to be conclusive.",
        )
    else:
        results.fail(
            "4. Edge1End varies",
            f"every record has the same Edge1End ({dict(end_values)}). This is the "
            "signature of a value derived from a constant rather than from geometry.",
        )

    if too_few_edges:
        results.fail(
            "5. Edge1 and Edge2 populated",
            f"{len(too_few_edges)} records have fewer than 2 edge references",
            too_few_edges,
        )
    else:
        results.ok("5. Edge1 and Edge2 populated")

    if gapped:
        results.fail(
            "6. no gaps in edge slots",
            f"{len(gapped)} records have a populated slot after an empty one",
            gapped,
        )
    else:
        results.ok("6. no gaps in edge slots")

    if dangling_fid:
        results.fail(
            "7. Edge{N}FID exists in edge FC",
            f"{len(dangling_fid)} records reference an ObjectID not present in the edge FC. "
            "This is the original 'Cannot find edge element' failure.",
            dangling_fid,
        )
    else:
        results.ok("7. Edge{N}FID exists in edge FC")

    if not_connected:
        results.fail(
            "8. consecutive edges share an endpoint",
            f"{len(not_connected)} records reference edges that do not meet -- the turn "
            "does not describe a real path through an intersection",
            not_connected,
        )
    else:
        results.ok("8. consecutive edges share an endpoint")

    if not has_edge1end:
        results.warn("9. Edge1End matches geometry", "no Edge1End field to check")
    elif bad_edge1end:
        results.fail(
            "9. Edge1End matches geometry",
            f"{len(bad_edge1end)} records have an Edge1End that contradicts which end of "
            "Edge1 the junction with Edge2 sits at",
            bad_edge1end,
        )
    else:
        results.ok("9. Edge1End matches geometry")

    if no_junction:
        results.warn(
            "9b. junction locatable",
            f"{len(no_junction)} records where Edge1/Edge2 touch but not at a clean endpoint",
            no_junction,
        )

    duplicate_groups = {sig: oids for sig, oids in by_signature.items() if len(oids) > 1}
    if duplicate_groups:
        duplicate_oids = {oid for oids in duplicate_groups.values() for oid in oids}
        degenerate_groups = {
            sig: oids for sig, oids in duplicate_groups.items()
            if len(set(sig[0])) < len(sig[0])   # a repeated FID within one turn's own sequence
        }
        logger.info(
            f"  {len(duplicate_groups)} duplicate signature group(s), "
            f"{len(duplicate_oids)} record(s) involved "
            f"({len(degenerate_groups)} group(s) are edge-onto-itself / degenerate)"
        )
        for sig, oids in sorted(duplicate_groups.items(), key=lambda kv: -len(kv[1]))[:SAMPLE_SIZE]:
            logger.info(f"    signature {sig}: OIDs {sorted(oids)}")
        logger.debug(f"  full duplicate signature map: {duplicate_groups}")
        results.warn(
            "10. no duplicate turn signatures",
            f"{len(duplicate_groups)} signature(s) shared by {len(duplicate_oids)} records "
            "-- BuildNetwork will keep one per group and reject the rest as 'Turn element "
            "already exists'. See intermediate_results/turn_review_for_mel.csv and "
            "degenerate_turns_disambiguated.csv for the prior (unresolved) investigation "
            "into whether these should be deduplicated before the swap.",
            duplicate_oids,
        )
    else:
        results.ok("10. no duplicate turn signatures")

    logger.info("=" * 60)
    if results.failed:
        logger.error(f"VERIFICATION FAILED -- {len(results.failed)} check(s): {results.failed}")
        logger.error("Do NOT swap this feature class in. Full OID lists are in the log at DEBUG level.")
        sys.exit(1)

    if results.warned:
        logger.warning(f"Verification passed with {len(results.warned)} warning(s): {results.warned}")
    else:
        logger.info("VERIFICATION PASSED -- all checks clean.")
    logger.info(
        "Note: this validates the turn FC against the edge FC only. It does not "
        "confirm each turn landed on the CORRECT intersection -- that still needs the "
        "spatial spot checks in docs/traffic_turn_staging_review_checklist.txt."
    )


if __name__ == "__main__":
    main()
