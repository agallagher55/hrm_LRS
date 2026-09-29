"""Read-only confirmation of current QA refresh paths and live metadata."""

import datetime

import arcpy

import config
from _shared import load_and_validate_core_scripts


TEMPLATE = config.NETWORK_DATASET_DIR / "data" / "network_template.xml"

# Text each deployed file must contain. A missing marker means the copy on the T: drive
# is older than the repo.
EXPECTED_MARKERS = {
    config.FULL_REBUILD_SCRIPT: "def main(argv=None):",
    TEMPLATE: "<NetworkDirections",
}


def summarize(label, path):
    if not arcpy.Exists(path):
        print(f"{label}: MISSING\n  {path}")
        return
    count = int(arcpy.management.GetCount(path)[0])
    fields = {field.name.upper() for field in arcpy.ListFields(path)}
    dates = []
    if "MODDATE" in fields:
        dates = [row[0] for row in arcpy.da.SearchCursor(path, ["MODDATE"]) if row[0]]
    print(f"{label}:\n  path={path}\n  count={count:,}")
    print(f"  min_MODDATE={min(dates) if dates else None}")
    print(f"  max_MODDATE={max(dates) if dates else None}")


def check_deployment():
    """Show size and date of the deployed files and flag ones that look stale.

    Two stale files on the T: drive cost time on 2026-09-29: the network template
    (a July VBScript copy) and run_full_network_rebuild.py (an older main()). Compare
    the sizes and dates below with the repo before continuing.
    """
    print("Deployed files")
    problems = []

    for path in [
        config.SCRIPT_03,
        config.SCRIPT_05,
        config.VERIFY_SCRIPT,
        config.FULL_REBUILD_SCRIPT,
        TEMPLATE,
    ]:
        if not path.exists():
            problems.append(f"missing: {path}")
            continue

        stat = path.stat()
        modified = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  {path.name}: {stat.st_size:,} bytes, modified {modified}")

    for path, marker in EXPECTED_MARKERS.items():
        if path.exists() and marker not in path.read_text(encoding="utf-8"):
            problems.append(f"{path.name} does not contain {marker!r}: probably a stale copy")

    if TEMPLATE.exists() and "Select Case" in TEMPLATE.read_text(encoding="utf-8"):
        problems.append(f"{TEMPLATE.name} contains VBScript ('Select Case'): stale copy")

    for problem in problems:
        print(f"  WARNING: {problem}")

    print()


def main():
    check_deployment()
    build, _, _ = load_and_validate_core_scripts()
    print("Current tracked configuration")
    print(f"  Prod edge input: {build.STANDALONE_EDGE_SOURCE}")
    print(f"  QA target FD:    {build.FEATURE_DATASET}")
    print()
    summarize("Script 03 edge input (expected Prod _VW)", build.STANDALONE_EDGE_SOURCE)
    summarize("QA standalone _VW (not the network source)", config.QA_STANDALONE_VIEW)
    summarize("QA network edge source", config.EDGE)
    print(
        "\nCounts and dates are evidence, not provenance proof. Spot-check known "
        "changed FDMID geometries in Prod and the QA network edge source."
    )


if __name__ == "__main__":
    main()

