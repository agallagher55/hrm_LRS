"""Copy fresh sources into the QA network feature dataset. Creates and builds nothing.

The edge source comes from Prod's TRNLRS_TRN_STREET_VW (minus the edge exclusions); the
junction and raw turn classes come from QA's legacy TRN_street_junction and
TRN_traffic_turn. The network dataset is created and built once, in step 06, after the
turn remap, so there is no throwaway build in between. To prove the template creates
and builds without touching QA, run test_template_create.py.

When the copies finish it prints the three counts next to Prod's edge count and the last
step 01 baseline, and stops if a class is empty or the edge copy has more rows than Prod.
"""

import json

import arcpy

import config
from _shared import load_and_validate_core_scripts, same_path


def count(path):
    return int(arcpy.management.GetCount(path)[0]) if arcpy.Exists(path) else None


def latest_baseline_counts():
    """Return the counts from the newest step 01 baseline for this network, or an empty dict."""
    for path in sorted(config.OUTPUT_DIR.glob("baseline_*.json"), reverse=True):
        with open(path, encoding="utf-8") as baseline_file:
            report = json.load(baseline_file)

        if same_path(report.get("network", ""), config.NETWORK):
            return report.get("counts", {})

    return {}


def find_problems(counts, prod_count):
    """Return what is wrong with the copied counts. An empty list means they look right."""
    problems = []

    for label, number in counts.items():
        if not number:
            problems.append(f"The {label} copy is empty or missing.")

    if counts.get("edge") and prod_count is not None and counts["edge"] > prod_count:
        problems.append(
            f"The edge copy has {counts['edge']:,} rows, more than Prod's {prod_count:,}. "
            "Exclusions only remove rows."
        )

    return problems


def report_counts(prod_edge_source):
    """Print the copied counts with Prod's edge count and the last baseline, and stop on a problem."""
    counts = {
        "edge": count(config.EDGE),
        "junction": count(config.JUNCTION),
        "turn": count(config.TURN),
    }
    prod_count = count(prod_edge_source)
    baseline = latest_baseline_counts()

    def last(label):
        return f"{baseline[label]:,}" if baseline.get(label) is not None else "none found"

    def show(number):
        return f"{number:,}" if number is not None else "missing"

    print("\nSource counts after the copy")
    edge_note = f"Prod view {show(prod_count)}"

    if prod_count is not None and counts["edge"] is not None:
        edge_note += f", excluded {prod_count - counts['edge']:,}"

    print(f"  edge      {show(counts['edge']):>8}  ({edge_note}; last QA baseline {last('edge')})")
    print(f"  junction  {show(counts['junction']):>8}  (last QA baseline {last('junction')})")
    print(f"  turn      {show(counts['turn']):>8}  (raw, before the remap; last QA baseline {last('turn')} remapped)")
    print("  The excluded count should equal the 'Edge exclusions applied' line in the step 03 log.")

    problems = find_problems(counts, prod_count)

    if problems:
        raise RuntimeError("Do not continue to step 04. " + " ".join(problems))


def main():
    build, _, _ = load_and_validate_core_scripts()
    build.main(copy_only=True)
    report_counts(build.STANDALONE_EDGE_SOURCE)
    print(
        "Sources copied. Confirm the edge count equals Prod's minus the excluded WA "
        "and island rows (see the 'Edge exclusions applied' log line) before step 04."
    )


if __name__ == "__main__":
    main()
