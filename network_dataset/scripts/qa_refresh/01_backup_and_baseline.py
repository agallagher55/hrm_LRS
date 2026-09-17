"""Create a timestamped turn backup and record the pre-refresh QA baseline."""

import json
import os
from datetime import datetime

import arcpy

import config
from _shared import load_and_validate_core_scripts, require_exists


def count(path):
    return int(arcpy.management.GetCount(path)[0]) if arcpy.Exists(path) else None


def main():
    load_and_validate_core_scripts()
    require_exists(config.TURN, "Live QA turn feature class")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = os.path.join(
        config.QA_NETWORK_FD, f"TRNLRS_traffic_turn_bak_{timestamp}"
    )
    print(f"Backing up {config.TURN}\n       to {backup}")
    arcpy.management.CopyFeatures(config.TURN, backup)
    source_count = count(config.TURN)
    backup_count = count(backup)
    if source_count != backup_count:
        raise RuntimeError(
            f"Backup count mismatch: source={source_count}, backup={backup_count}"
        )

    baseline = {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "qa_sde": config.QA_SDE,
        "network": config.NETWORK,
        "backup": backup,
        "counts": {
            "edge": count(config.EDGE),
            "junction": count(config.JUNCTION),
            "turn": source_count,
            "turn_backup": backup_count,
        },
    }
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    report = config.OUTPUT_DIR / f"baseline_{timestamp}.json"
    report.write_text(json.dumps(baseline, indent=2), encoding="utf-8")
    print(f"Backup verified ({backup_count:,} rows). Baseline written to {report}")
    print("Record Network Dataset Properties and registration IDs before step 02.")


if __name__ == "__main__":
    main()
