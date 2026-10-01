"""Create a timestamped turn backup and record the pre-refresh QA baseline."""

import datetime
import json
import os

import arcpy

import config
from _shared import load_and_validate_core_scripts, require_exists


def count(path):
    return int(arcpy.management.GetCount(path)[0]) if arcpy.Exists(path) else None


def export_outside_sde(timestamp):
    """Copy the network sources into a file geodatabase outside SDE and check the counts."""
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    gdb = arcpy.management.CreateFileGDB(
        str(config.OUTPUT_DIR), f"qa_network_sources_{timestamp}.gdb"
    ).getOutput(0)
    counts = {}

    for name, source in [
        ("TRNLRS_TRN_STREET", config.EDGE),
        ("TRNLRS_street_junction", config.JUNCTION),
        ("TRNLRS_traffic_turn", config.TURN),
    ]:
        if not arcpy.Exists(source):
            print(f"Not exported, not found: {source}")
            continue

        target = os.path.join(gdb, name)
        arcpy.management.CopyFeatures(source, target)

        if count(source) != count(target):
            raise RuntimeError(
                f"Export count mismatch for {name}: source={count(source)}, copy={count(target)}"
            )

        counts[name] = count(target)
        print(f"Exported {name}: {counts[name]:,} rows")

    print(f"Sources exported outside SDE to {gdb}")

    return {"gdb": gdb, "counts": counts}


def main():
    load_and_validate_core_scripts()
    require_exists(config.TURN, "Live QA turn feature class")
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = os.path.join(
        config.QA_NETWORK_FD, f"{config.NETWORK_DEF.turn_name}_bak_{timestamp}"
    )
    print(f"Backing up {config.TURN}\n       to {backup}")
    arcpy.management.CopyFeatures(config.TURN, backup)
    source_count = count(config.TURN)
    backup_count = count(backup)
    if source_count != backup_count:
        raise RuntimeError(
            f"Backup count mismatch: source={source_count}, backup={backup_count}"
        )

    offline = export_outside_sde(timestamp) if config.OFFLINE_BACKUP else None

    baseline = {
        "captured_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "qa_sde": config.QA_SDE,
        "network": config.NETWORK,
        "network_key": config.NETWORK_DEF.key,
        "backup": backup,
        "offline_backup": offline,
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
