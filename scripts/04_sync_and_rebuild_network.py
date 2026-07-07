"""
Sync the network edge source and rebuild TRNLRS_street_network.

TRNLRS_TRN_STREET_VW (standalone, outside SDEADM.TRNLRS) is the authoritative
edge source maintained by LRS_updates.py.  TRNLRS_TRN_STREET (inside SDEADM.TRNLRS)
is the copy referenced by the network dataset — it must be kept in sync whenever
TRNLRS_TRN_STREET_VW is refreshed.

This script truncates the FD copy and reloads it from the standalone FC, then
rebuilds the network dataset.  Run it at the end of every LRS refresh cycle, or
call sync_and_rebuild() directly from LRS_updates.py:

    from scripts.04_sync_and_rebuild_network import sync_and_rebuild
    sync_and_rebuild(sde_connection=SDEADM_RW)

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
SDE_CONNECTION_UPDATE = r"E:\HRM\Scripts\SDE\SQL\Dev\dev_RW_sdeadm.sde"
SDE_CONNECTION_UPDATE = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"

# Prod: TRNLRS_TRN_STREET has already been created against this connection.
# Uncomment to point this script at prod instead of Dev.
PROD_SDE_CONNECTION = r"E:\HRM\Scripts\SDE\SQL\Prod\prod_RW_sdeadm.sde"
# ---------------------------------------------------------------------------


def sync_and_rebuild(
    update_sde_connection: str = SDE_CONNECTION_UPDATE,
    prod_sde_connection: str = PROD_SDE_CONNECTION,
    street_source_fc: str = None,
    streets_target_fc: str = None,
    network: str = None,
):
    """Truncate the FD edge source copy, reload from the standalone FC, and rebuild the network.

    Parameters default to the module-level constants so the function can be called
    from LRS_updates.py without arguments when the paths are the same environment:

        from scripts.sync_and_rebuild_network import sync_and_rebuild
        sync_and_rebuild(sde_connection=SDEADM_RW)
    """
    
    street_source_fc = street_source_fc or os.path.join(prod_sde_connection, "SDEADM.TRNLRS_TRN_STREET_VW")
    streets_target_fc    = streets_target_fc or os.path.join(update_sde_connection, "SDEADM.TRNLRS", "TRNLRS_TRN_STREET")
    network    = network    or os.path.join(update_sde_connection, "SDEADM.TRNLRS", "TRNLRS_street_network")

    for path, label in [(street_source_fc, "standalone edge source"), (streets_target_fc, "FD edge copy"), (network, "network dataset")]:
        
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
