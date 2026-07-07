"""
Sync the network edge source and rebuild TRNLRS_street_network.

TRNLRS_TRN_STREET_VW is the authoritative edge source, maintained by
LRS_updates.py, and it only exists in prod. Dev and QA do not keep their own
standalone copy -- each environment's network dataset instead pulls directly
from prod's TRNLRS_TRN_STREET_VW and rebuilds its own TRNLRS_street_network.

This script truncates the target environment's FD copy (TRNLRS_TRN_STREET) and
reloads it from prod's TRNLRS_TRN_STREET_VW, then rebuilds that environment's
network dataset. Run it at the end of every LRS refresh cycle, or call
sync_and_rebuild() directly from LRS_updates.py:

    from scripts.04_sync_and_rebuild_network import sync_and_rebuild
    sync_and_rebuild(update_sde_connection=SDEADM_RW)

Once TRNLRS_TRN_STREET_VW is moved into the feature dataset permanently, this
script and the copy step in 03_create_network_dataset.py can both be retired.

Run standalone from ArcGIS Pro Python environment:
  > python scripts/04_sync_and_rebuild_network.py
"""

import os
import sys

import arcpy

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Environment whose TRNLRS_TRN_STREET (FD copy) and TRNLRS_street_network get
# truncated/reloaded/rebuilt by this script.
SDE_CONNECTION_UPDATE = r"E:\HRM\Scripts\SDE\SQL\Dev\dev_RW_sdeadm.sde"
SDE_CONNECTION_UPDATE = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"

# Prod is always the read source: TRNLRS_TRN_STREET_VW (the authoritative
# standalone edge source refreshed by LRS_updates.py) only exists in prod, so
# every environment's network sync pulls from here regardless of which
# environment SDE_CONNECTION_UPDATE points at above.
PROD_SDE_CONNECTION = r"E:\HRM\Scripts\SDE\SQL\Prod\prod_RW_sdeadm.sde"
# ---------------------------------------------------------------------------


def sync_and_rebuild(
    update_sde_connection: str = SDE_CONNECTION_UPDATE,
    prod_sde_connection: str = PROD_SDE_CONNECTION,
    street_source_fc: str = None,
    streets_target_fc: str = None,
    network: str = None,
):
    """Truncate the FD edge source copy, reload from prod's standalone FC, and rebuild the network.

    The edge source is always read from prod_sde_connection (TRNLRS_TRN_STREET_VW
    only exists in prod). The FD copy and network dataset that get overwritten and
    rebuilt live in update_sde_connection, which may be Dev, QA, or prod itself.

    Parameters default to the module-level constants so the function can be called
    from LRS_updates.py without arguments when the paths are the same environment:

        from scripts.sync_and_rebuild_network import sync_and_rebuild
        sync_and_rebuild(update_sde_connection=SDEADM_RW)
    """

    street_source_fc = street_source_fc or os.path.join(prod_sde_connection, "SDEADM.TRNLRS_TRN_STREET_VW")
    streets_target_fc    = streets_target_fc or os.path.join(update_sde_connection, "SDEADM.TRNLRS", "TRNLRS_TRN_STREET")
    network    = network    or os.path.join(update_sde_connection, "SDEADM.TRNLRS", "TRNLRS_street_network")

    for path, label in [(street_source_fc, "prod standalone edge source"), (streets_target_fc, "FD edge copy"), (network, "network dataset")]:

        if not arcpy.Exists(path):
            sys.exit(f"ERROR: Cannot find {label}:\n  {path}")

    print(f"Syncing edge source:\n  {street_source_fc}\n  → {streets_target_fc}")
    arcpy.management.TruncateTable(streets_target_fc)
    arcpy.management.Append(
        inputs=street_source_fc,
        target=streets_target_fc,
        schema_type="NO_TEST",
    )
    
    count = int(arcpy.management.GetCount(streets_target_fc)[0])
    print(f"Sync complete — {count:,} features loaded.")

    print(f"Rebuilding network dataset: {network}")
    arcpy.na.BuildNetwork(network)
    print("Rebuild complete.")


def main():
    if arcpy.CheckExtension("Network") != "Available":
        sys.exit("ERROR: Network Analyst extension is not available.")

    arcpy.CheckOutExtension("Network")

    try:
        sync_and_rebuild()

    finally:
        arcpy.CheckInExtension("Network")


if __name__ == "__main__":
    main()
