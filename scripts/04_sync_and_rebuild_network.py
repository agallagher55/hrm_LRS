"""
Sync the network edge source and rebuild TRNLRS_street_network in prod.

TRNLRS_TRN_STREET_VW is the authoritative edge source, refreshed by
LRS_updates.py, and it only exists in prod. TRNLRS_TRN_STREET (the FD copy
prod's network dataset references) goes stale every time TRNLRS_TRN_STREET_VW
is refreshed, so this script re-syncs it and rebuilds TRNLRS_street_network --
both within prod.

Dev and QA builds of TRNLRS_street_network are one-off/test builds created by
scripts/03_create_network_dataset.py, which already loads a fresh copy of
TRNLRS_TRN_STREET_VW from prod at creation time. They are not kept in
continuous sync and do not need this script run against them -- re-run script
03 if a Dev/QA build needs a newer snapshot.

Run this script at the end of every LRS refresh cycle, or call
sync_and_rebuild() directly from LRS_updates.py:

    from scripts.04_sync_and_rebuild_network import sync_and_rebuild
    sync_and_rebuild()

Once TRNLRS_TRN_STREET_VW is moved into the feature dataset permanently, this
script and the copy step in 03_create_network_dataset.py can both be retired.

Run standalone from ArcGIS Pro Python environment:
  > python scripts/04_sync_and_rebuild_network.py
"""

import os
import sys

import arcpy

from log_utils import setup_logger

logger = setup_logger("04_sync_and_rebuild_network")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# This script only ever runs against prod: TRNLRS_TRN_STREET_VW is refreshed
# in prod by LRS_updates.py, and prod's TRNLRS_TRN_STREET / TRNLRS_street_network
# are what live routing actually uses, so they're the only copies that need
# continuous re-syncing after every refresh.
PROD_SDE_CONNECTION = r"E:\HRM\Scripts\SDE\SQL\Prod\prod_RW_sdeadm.sde"
# ---------------------------------------------------------------------------


def sync_and_rebuild(
    prod_sde_connection: str = PROD_SDE_CONNECTION,
    street_source_fc: str = None,
    streets_target_fc: str = None,
    network: str = None,
):
    """Truncate the FD edge source copy, reload from the standalone FC, and rebuild the network.

    Both the standalone edge source and the FD copy/network dataset being
    refreshed live in prod_sde_connection -- this script does not support
    syncing across environments (see module docstring for why Dev/QA don't
    need it).

    Parameters default to the module-level constant so the function can be
    called from LRS_updates.py without arguments:

        from scripts.sync_and_rebuild_network import sync_and_rebuild
        sync_and_rebuild()
    """

    street_source_fc  = street_source_fc  or os.path.join(prod_sde_connection, "SDEADM.TRNLRS_TRN_STREET_VW")
    streets_target_fc = streets_target_fc or os.path.join(prod_sde_connection, "SDEADM.TRNLRS", "TRNLRS_TRN_STREET")
    network           = network           or os.path.join(prod_sde_connection, "SDEADM.TRNLRS", "TRNLRS_street_network")

    for path, label in [(street_source_fc, "standalone edge source"), (streets_target_fc, "FD edge copy"), (network, "network dataset")]:

        if not arcpy.Exists(path):
            logger.error(f"Cannot find {label}: {path}")
            sys.exit(f"ERROR: Cannot find {label}:\n  {path}")

    logger.info(f"Syncing edge source: {street_source_fc} -> {streets_target_fc}")
    # streets_target_fc (TRNLRS_TRN_STREET) is a registered edge source of
    # `network`, which makes it a "controller dataset" participant.
    # TruncateTable is not supported on controller-dataset feature classes
    # (ERROR 001395: "Operation not supported on a feature class in a
    # controller dataset") -- unlike Delete/Rename (ERROR 001919), there's no
    # need to delete the network dataset here, since DeleteRows is a normal
    # edit operation that IS supported on controller-dataset members. It's
    # slower than TruncateTable for large tables (>10k rows), which this is,
    # but it's the only option that doesn't require tearing down and
    # rebuilding the network dataset on every sync.
    arcpy.management.DeleteRows(streets_target_fc)
    arcpy.management.Append(
        inputs=street_source_fc,
        target=streets_target_fc,
        schema_type="NO_TEST",
    )

    count = int(arcpy.management.GetCount(streets_target_fc)[0])
    logger.info(f"Sync complete -- {count:,} features loaded.")

    logger.info(f"Rebuilding network dataset: {network}")
    arcpy.na.BuildNetwork(network)
    logger.info("Rebuild complete.")

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


def main():
    if arcpy.CheckExtension("Network") != "Available":
        logger.error("Network Analyst extension is not available.")
        sys.exit("ERROR: Network Analyst extension is not available.")

    arcpy.CheckOutExtension("Network")

    try:
        sync_and_rebuild()

    finally:
        arcpy.CheckInExtension("Network")


if __name__ == "__main__":
    main()
