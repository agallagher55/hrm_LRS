"""Delete the QA network dataset and its three registered source classes."""

import json
import time

import arcpy

import config
from _shared import load_and_validate_core_scripts, require_network, same_path


# Set this to True only after reviewing the configured QA paths in config.py.
CONFIRM_DELETE_QA_NETWORK = False

# The network this run deletes. It must match HRM_NETWORK (unset means DISTANCE, the live network),
# so set both on purpose: for HRFE, set this to "HRFE" and run with HRM_NETWORK=HRFE.
NETWORK_TO_DELETE = "DISTANCE"

# Step 01's backup is the only copy of the live turn class once it is deleted below.
REQUIRE_RECENT_BACKUP = True
MAX_BACKUP_AGE_HOURS = 24


def require_recent_backup():
    """Refuse to delete anything unless step 01 left a recent, intact turn backup."""
    reports = []

    # Both networks write their baselines to the same folder, so only use this network's.
    for path in sorted(config.OUTPUT_DIR.glob("baseline_*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))

        if same_path(report.get("network", ""), config.NETWORK):
            reports.append(path)

    if not reports:
        raise RuntimeError(
            f"No baseline report for {config.NETWORK} in {config.OUTPUT_DIR}. "
            "Run 01_backup_and_baseline.py first, on this network."
        )

    latest = reports[-1]
    age_hours = (time.time() - latest.stat().st_mtime) / 3600

    if age_hours > MAX_BACKUP_AGE_HOURS:
        raise RuntimeError(
            f"The latest baseline report {latest.name} is {age_hours:.0f} hours old "
            f"(limit {MAX_BACKUP_AGE_HOURS}). Run 01_backup_and_baseline.py again."
        )

    baseline = json.loads(latest.read_text(encoding="utf-8"))
    backup = baseline["backup"]

    if not arcpy.Exists(backup):
        raise RuntimeError(f"The turn backup named in {latest.name} no longer exists: {backup}")

    print(f"Turn backup confirmed ({latest.name}): {backup}")

    if config.OFFLINE_BACKUP:
        offline = baseline.get("offline_backup")

        if not offline or not arcpy.Exists(offline["gdb"]):
            raise RuntimeError(
                f"No file geodatabase export outside SDE is recorded in {latest.name}, or it "
                "no longer exists. Run 01_backup_and_baseline.py again."
            )

        print(f"Export outside SDE confirmed: {offline['gdb']}")


def main():
    if not CONFIRM_DELETE_QA_NETWORK:
        raise RuntimeError(
            "Refusing destructive step while CONFIRM_DELETE_QA_NETWORK is False. "
            "Review config.py, then set the global to True before running this script."
        )

    load_and_validate_core_scripts()
    require_network(NETWORK_TO_DELETE, "NETWORK_TO_DELETE")

    if REQUIRE_RECENT_BACKUP:
        require_recent_backup()

    # A topology member cannot be deleted, so the topology goes first. Rebuild it afterward
    # with 07_create_topology.py.
    for label, path in [
        ("topology", config.TOPOLOGY),
        ("network dataset", config.NETWORK),
        ("edge source", config.EDGE),
        ("junction source", config.JUNCTION),
        ("turn source", config.TURN),
    ]:
        if arcpy.Exists(path):
            print(f"Deleting {label}: {path}")
            arcpy.management.Delete(path)
        else:
            print(f"Already absent, skipping {label}: {path}")


if __name__ == "__main__":
    main()
