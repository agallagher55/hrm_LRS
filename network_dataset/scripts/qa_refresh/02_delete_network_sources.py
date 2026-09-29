"""Delete the QA network dataset and its three registered source classes."""

import json
import time

import arcpy

import config
from _shared import load_and_validate_core_scripts


# Set this to True only after reviewing the configured QA paths in config.py.
CONFIRM_DELETE_QA_NETWORK = False

# Step 01's backup is the only copy of the live turn class once it is deleted below.
REQUIRE_RECENT_BACKUP = True
MAX_BACKUP_AGE_HOURS = 24


def require_recent_backup():
    """Refuse to delete anything unless step 01 left a recent, intact turn backup."""
    reports = sorted(config.OUTPUT_DIR.glob("baseline_*.json"))

    if not reports:
        raise RuntimeError(
            f"No baseline report in {config.OUTPUT_DIR}. Run 01_backup_and_baseline.py first."
        )

    latest = reports[-1]
    age_hours = (time.time() - latest.stat().st_mtime) / 3600

    if age_hours > MAX_BACKUP_AGE_HOURS:
        raise RuntimeError(
            f"The latest baseline report {latest.name} is {age_hours:.0f} hours old "
            f"(limit {MAX_BACKUP_AGE_HOURS}). Run 01_backup_and_baseline.py again."
        )

    backup = json.loads(latest.read_text(encoding="utf-8"))["backup"]

    if not arcpy.Exists(backup):
        raise RuntimeError(f"The turn backup named in {latest.name} no longer exists: {backup}")

    print(f"Turn backup confirmed ({latest.name}): {backup}")


def main():
    if not CONFIRM_DELETE_QA_NETWORK:
        raise RuntimeError(
            "Refusing destructive step while CONFIRM_DELETE_QA_NETWORK is False. "
            "Review config.py, then set the global to True before running this script."
        )

    load_and_validate_core_scripts()

    if REQUIRE_RECENT_BACKUP:
        require_recent_backup()

    for label, path in [
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
