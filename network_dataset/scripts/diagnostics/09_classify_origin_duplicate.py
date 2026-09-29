"""
09_classify_duplicate_origin.py

Read-only follow-up to 08_find_duplicate_siblings.py. Now that every one of the 165
duplicate turns has a matched sibling, this answers the open question in
traffic_turns_duplicates.md: is the duplication a legacy artifact (the sibling already
existed and resolves fine) or something the remap introduced (the sibling also fails)?

Cross-references duplicate_turn_siblings.csv (from 08) against the full set of failing
OIDs (from the BuildErrors file, same parse as before). For each of the 165:
  - If its sibling(s) are NOT in the failing set, the sibling built successfully, this
    duplicate has been sitting alongside a working record. Points to legacy origin.
  - If its sibling(s) ARE also in the failing set, both copies of this maneuver fail,
    which could mean the legacy data had the duplicate already (and neither resolves for
    an unrelated reason), or that the remap's tiebreaker logic produced two records that
    now collide with each other. Worth a manual look at a sample of these.

Usage
-----
1. Set DUPLICATE_SIBLINGS_CSV to the output of 08_find_duplicate_siblings.py.
2. Set BUILD_ERRORS_FILE to the same file used throughout.
3. Run (no arcpy needed, this only reads two text files):
       python 09_classify_duplicate_origin.py
"""

import csv
import re
import sys

DUPLICATE_SIBLINGS_CSV = "duplicate_turn_siblings.csv"
BUILD_ERRORS_FILE = r"T:\work\giss\monthly\202607jul\gallaga\network_dataset\New folder\BuildErrors_7f5e2ac0-64f1-4421-97d7-9be28cf15c3a.txt"

TURN_FC_NAME = "TRNLRS_traffic_turn"

LINE_PATTERN = re.compile(
    rf"SourceName:\s*[\w.]*{re.escape(TURN_FC_NAME)}.*?ObjectID:\s*(\d+)",
    re.IGNORECASE,
)


def parse_all_failing_oids(errors_path):
    oids = set()
    with open(errors_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = LINE_PATTERN.search(line)
            if m:
                oids.add(int(m.group(1)))
    return oids


def main():
    try:
        failing_oids = parse_all_failing_oids(BUILD_ERRORS_FILE)
    except FileNotFoundError:
        print(f"ERROR: BuildErrors file not found: {BUILD_ERRORS_FILE}")
        sys.exit(1)
    print(f"Total failing OIDs (all categories): {len(failing_oids)}")

    legacy_pattern = []   # sibling resolved successfully
    both_failing = []     # sibling also fails
    no_sibling = []       # shouldn't happen per 08's output, but check anyway

    try:
        with open(DUPLICATE_SIBLINGS_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                oid = int(row["turn_oid"])
                sib_field = row["sibling_oids"].strip()
                if not sib_field:
                    no_sibling.append(oid)
                    continue
                sibs = [int(s) for s in sib_field.split(";") if s]
                sib_failing = [s for s in sibs if s in failing_oids]
                sib_resolved = [s for s in sibs if s not in failing_oids]
                if sib_resolved:
                    legacy_pattern.append((oid, sib_resolved))
                elif sib_failing:
                    both_failing.append((oid, sib_failing))
                else:
                    no_sibling.append(oid)
    except FileNotFoundError:
        print(f"ERROR: {DUPLICATE_SIBLINGS_CSV} not found. Run 08_find_duplicate_siblings.py first.")
        sys.exit(1)

    total = len(legacy_pattern) + len(both_failing) + len(no_sibling)
    print()
    print("=" * 78)
    print(f"Total duplicate turns checked: {total}")
    print(f"  Sibling resolved successfully (legacy-pattern duplication): {len(legacy_pattern)}")
    print(f"  Sibling also failing (both copies broken):                 {len(both_failing)}")
    print(f"  No sibling found (unexpected):                             {len(no_sibling)}")
    print("=" * 78)

    if legacy_pattern:
        print()
        print(f"Sample of legacy-pattern duplicates (turn_oid -> resolved sibling_oid):")
        for oid, sibs in legacy_pattern[:10]:
            print(f"  {oid} -> {sibs}")

    if both_failing:
        print()
        print(f"Sample of both-failing duplicates (turn_oid -> failing sibling_oid):")
        for oid, sibs in both_failing[:10]:
            print(f"  {oid} -> {sibs}")

    print()
    if len(legacy_pattern) == total:
        print("CONCLUSION: every duplicate's sibling resolved successfully. This is")
        print("consistent with pre-existing legacy duplication, not something the remap")
        print("introduced. No change needed to 05_rebuild_traffic_turns.py on this front.")
    elif len(both_failing) == total:
        print("CONCLUSION: every duplicate's sibling is also failing. Worth a manual look")
        print("at a few of the both_failing examples above to see if they're two remap")
        print("outputs colliding (same tiebreaker outcome for two different legacy turns)")
        print("or two legacy duplicates that both happen to fail independently.")
    else:
        print("CONCLUSION: mixed. Some duplicates look legacy, others may be remap-")
        print("introduced or coincidental. The both_failing sample above is the set worth")
        print("a manual look before deciding whether 05_rebuild_traffic_turns.py needs a")
        print("dedupe step.")


if __name__ == "__main__":
    main()