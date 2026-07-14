"""
06_migrate_network_fd.py

Dev-only pilot: moves the three TRNLRS_street_network source feature classes
(TRNLRS_TRN_STREET, TRNLRS_street_junction, TRNLRS_traffic_turn) out of
SDEADM.TRNLRS (the LRS feature dataset) and into SDEADM.TRNLRS_network (a
feature dataset dedicated to the network sources), separating network data
from LRS data. SDEADM.TRNLRS_network already exists in both Dev and QA; this
script only ever targets Dev (SDE_CONNECTION below) -- QA/prod get the same
treatment later, once the Dev pilot is validated. See
docs/network_dataset_migration_plan.md for the full plan.

Steps performed
----------------
1. Verify SDEADM.TRNLRS_network exists and that its spatial reference
   (XYTolerance, ZTolerance, MTolerance, HighPrecision -- not just coordinate
   system) matches SDEADM.TRNLRS exactly. Any mismatch is logged and the
   script exits WITHOUT making changes -- mismatches are flagged for review,
   never silently "fixed".
2. For each of the three source FCs: copy from SDEADM.TRNLRS into
   SDEADM.TRNLRS_network via arcpy.management.CopyFeatures, then compare
   feature counts between source and destination.
3. Only if every count matches, and only if DELETE_ORIGINALS is True, delete
   the three originals from SDEADM.TRNLRS.

Controller dataset gotcha
--------------------------
If TRNLRS_street_network has already been built in SDEADM.TRNLRS (it has, as
of the 2026-06-26 Dev build -- see docs/network_build_status.md), the three
source FCs there are registered network sources, which makes them controller
dataset participants. arcpy.management.Delete refuses to delete a controller
dataset member (ERROR 001919) while the network dataset that registers it
still exists. This script does NOT delete SDEADM.TRNLRS\\TRNLRS_street_network
automatically -- that's a bigger, more destructive action than "move three
FCs" and deserves an explicit decision, not a silent side effect. If the
delete step hits ERROR 001919, stop and read the logged guidance: the
existing network dataset in SDEADM.TRNLRS must be deleted first to release
the lock, and scripts/03_create_network_dataset.py (already updated to target
SDEADM.TRNLRS_network) re-created and rebuilt in its place afterward.

Usage
-----
1. Run once with DELETE_ORIGINALS = False (default). Review the logged
   feature counts for all three FCs -- confirm they look reasonable, not just
   equal to the destination (Dev's copies may be stale relative to QA/prod;
   flag to Alex if TRNLRS_TRN_STREET, TRNLRS_street_junction, or
   TRNLRS_traffic_turn look out of date or missing/empty).
2. Set DELETE_ORIGINALS = True and re-run to remove the originals from
   SDEADM.TRNLRS now that the copies are verified. If this fails with
   ERROR 001919, see "Controller dataset gotcha" above.

Run from ArcGIS Pro Python environment:
  > python scripts/06_migrate_network_fd.py
"""

import os
import sys

import arcpy

from log_utils import setup_logger

logger = setup_logger("06_migrate_network_fd")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SDE_CONNECTION = r"E:\HRM\Scripts\SDE\SQL\Dev\dev_RW_sdeadm.sde"

LRS_FD     = os.path.join(SDE_CONNECTION, "SDEADM.TRNLRS")
NETWORK_FD = os.path.join(SDE_CONNECTION, "SDEADM.TRNLRS_network")

FC_NAMES = ["TRNLRS_TRN_STREET", "TRNLRS_street_junction", "TRNLRS_traffic_turn"]

# Set True only after reviewing the feature counts logged by a prior run.
# Leave False to do a copy + count-verification dry run that leaves the
# originals in SDEADM.TRNLRS untouched.
DELETE_ORIGINALS = False

# Spatial reference properties that must match exactly between the two
# feature datasets before any data is moved -- coordinate system alone is not
# enough, since a tolerance/resolution mismatch on copy can silently corrupt
# geometry precision.
SR_PROPERTIES = ["XYTolerance", "ZTolerance", "MTolerance", "HighPrecision"]
# ---------------------------------------------------------------------------


def check_spatial_reference_match(fd_a, fd_b):
    """Compare SR tolerance/precision properties between two feature datasets.

    Returns True only if every property in SR_PROPERTIES matches (coordinate
    system is checked first as a prerequisite). Logs every property checked,
    not just mismatches, so a clean run leaves a full record.
    """
    desc_a = arcpy.Describe(fd_a)
    desc_b = arcpy.Describe(fd_b)
    sr_a = desc_a.spatialReference
    sr_b = desc_b.spatialReference

    if sr_a.name != sr_b.name:
        logger.error(f"Coordinate system mismatch: {fd_a} = {sr_a.name} | {fd_b} = {sr_b.name}")
        return False

    all_match = True
    for prop in SR_PROPERTIES:
        val_a = getattr(sr_a, prop)
        val_b = getattr(sr_b, prop)
        status = "OK" if val_a == val_b else "MISMATCH"
        if val_a != val_b:
            all_match = False
        logger.info(f"  {prop}: {fd_a}={val_a} | {fd_b}={val_b} [{status}]")

    return all_match


def copy_and_verify(fc_name):
    """Copy fc_name from LRS_FD into NETWORK_FD and compare feature counts.

    Returns (source_count, dest_count). Exits if the source FC is missing --
    there is nothing to migrate in that case.
    """
    source = os.path.join(LRS_FD, fc_name)
    dest = os.path.join(NETWORK_FD, fc_name)

    if not arcpy.Exists(source):
        msg = f"Source FC not found, cannot migrate: {source}"
        logger.error(msg)
        sys.exit(f"ERROR: {msg}")

    source_count = int(arcpy.management.GetCount(source)[0])
    logger.info(f"Source count for {fc_name}: {source_count:,}")

    if arcpy.Exists(dest):
        logger.warning(f"Destination already exists, skipping copy: {dest}")
    else:
        logger.info(f"Copying {source} -> {dest}")
        arcpy.management.CopyFeatures(source, dest)

    dest_count = int(arcpy.management.GetCount(dest)[0])
    logger.info(f"Destination count for {fc_name}: {dest_count:,}")

    return source_count, dest_count


def main():
    logger.info(f"Verifying feature datasets exist: {LRS_FD}, {NETWORK_FD}")
    for fd in (LRS_FD, NETWORK_FD):
        if not arcpy.Exists(fd):
            msg = f"Feature dataset not found: {fd}. This script does not create feature datasets."
            logger.error(msg)
            sys.exit(f"ERROR: {msg}")

    logger.info(f"Comparing spatial reference of {LRS_FD} and {NETWORK_FD}...")
    if not check_spatial_reference_match(LRS_FD, NETWORK_FD):
        msg = (
            f"Spatial reference mismatch between {LRS_FD} and {NETWORK_FD}. "
            "Flagging for review -- NOT proceeding with the FC migration. "
            "Resolve (or explicitly confirm acceptable) before re-running."
        )
        logger.error(msg)
        sys.exit(f"ERROR: {msg}")
    logger.info("Spatial reference match confirmed.")

    counts = {fc_name: copy_and_verify(fc_name) for fc_name in FC_NAMES}

    mismatches = {
        fc_name: (src, dst) for fc_name, (src, dst) in counts.items() if src != dst
    }
    if mismatches:
        msg = f"Feature count mismatch after copy -- originals will NOT be deleted: {mismatches}"
        logger.error(msg)
        sys.exit(f"ERROR: {msg}")
    logger.info("All feature counts match between source and destination.")

    for fc_name, (src_count, _) in counts.items():
        if src_count == 0:
            logger.warning(
                f"{fc_name} has 0 features in Dev. This may mean Dev's copy is stale, empty, "
                "or was never populated -- flag to Alex before treating this as a clean pilot."
            )

    if not DELETE_ORIGINALS:
        logger.info(
            "DELETE_ORIGINALS is False -- originals left in place in SDEADM.TRNLRS. "
            "Review the counts above (including whether they look reasonable, not just "
            "equal), then set DELETE_ORIGINALS = True and re-run to remove the originals."
        )
        return

    existing_nd = os.path.join(LRS_FD, "TRNLRS_street_network")
    if arcpy.Exists(existing_nd):
        msg = (
            f"{existing_nd} still exists. The three source FCs in {LRS_FD} are registered "
            "sources of that network dataset (controller dataset participants), so "
            "arcpy.management.Delete on them will raise ERROR 001919. This script does not "
            "delete network datasets automatically -- that's a bigger action than moving "
            "three FCs. Delete the network dataset in SDEADM.TRNLRS yourself (releasing the "
            "controller-dataset lock) if you intend to fully retire that copy, then re-run "
            "this script. Aborting without deleting anything."
        )
        logger.error(msg)
        sys.exit(f"ERROR: {msg}")

    logger.info("DELETE_ORIGINALS is True -- deleting originals from SDEADM.TRNLRS...")
    for fc_name in FC_NAMES:
        original = os.path.join(LRS_FD, fc_name)
        logger.info(f"Deleting {original}")
        arcpy.management.Delete(original)
    logger.info("Migration complete. Originals removed from SDEADM.TRNLRS.")


if __name__ == "__main__":
    main()
