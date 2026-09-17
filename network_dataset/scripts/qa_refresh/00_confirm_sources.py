"""Read-only confirmation of current QA refresh paths and live metadata."""

import arcpy

import config
from _shared import load_and_validate_core_scripts


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


def main():
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

