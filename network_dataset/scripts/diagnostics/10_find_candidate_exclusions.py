"""
10_find_candidate_exclusions.py

Read-only. Counts and lists the street segments that each candidate exclusion
filter would drop, so the filters in network_exclusions.py can be chosen from
real data instead of guessed.

Background: Robbie Evans (HRFE) asked for these to be removed from the HRFE
network (email thread "HRFE network dataset", 2026-09-01 to 2026-09-17):

  - Water access roads: STR_TYPE = 'WA'. Already excluded; listed here as a
    baseline (expect 61 rows).
  - Transit access roads: "roads like 'TA# RD'". The filter is not decided. The
    older guess of STR_TYPE 'ATA' does not match his description.
  - Emergency access roads: FULL_NAME LIKE '%EMERGENCY ACCESS%'. He says there
    are 4 (expect 4 rows).
  - ETAs (emergency turnarounds): small connectors between divided highways. He
    gave no query, so the candidates below are guesses to help find them.

For every candidate this prints the row count, the STR_TYPE / ST_CLASS mix of the
matches, and the first rows. Every matched row is written to OUTPUT_CSV so it can
be sent to Robbie and Melanie Parker to confirm. A candidate that matches far
more rows than expected, or picks up ordinary street names, is not safe to use
as an exclusion.

Also prints every STR_TYPE value with its row count, to check the domain for a
transit access code.

Nothing is edited. It only reads TRNLRS_TRN_STREET_VW.

Usage
-----
1. Set SOURCE_FC if you are not reading Prod.
2. Run from an ArcGIS Pro Python environment.
3. Send OUTPUT_CSV to Robbie and Melanie. Once a filter is confirmed, add it to
   HRFE_EXTRA in network_exclusions.py.

The [0-9] range in a LIKE pattern works against SQL Server (the enterprise
geodatabase) but not against a file geodatabase.
"""

import csv
import sys
from collections import Counter

try:
    import arcpy
except ImportError:
    print("ERROR: arcpy is required. Run this from an ArcGIS Pro Python environment.")
    sys.exit(1)

PROD_SDE = r"E:\HRM\Scripts\SDE\SQL\Prod\prod_RW_sdeadm.sde"
SOURCE_FC = PROD_SDE + r"\SDEADM.TRNLRS_TRN_STREET_VW"

OUTPUT_CSV = "candidate_exclusions.csv"
SAMPLE_ROWS = 15

# (name, where clause, note). The first three are the baseline and the filters
# Robbie described; the rest are searches for what he has not described.
CANDIDATES = [
    ("WA baseline", "STR_TYPE = 'WA'", "already excluded; expect 61"),
    ("Emergency access", "FULL_NAME LIKE '%EMERGENCY ACCESS%'", "Robbie says 4"),
    ("Transit: TA + digit", "FULL_NAME LIKE 'TA[0-9]%'", "first choice for 'TA# RD'"),
    ("Transit: TA prefix", "FULL_NAME LIKE 'TA%'", "wider; look for ordinary names such as TAYLOR"),
    ("Transit: STR_TYPE ATA", "STR_TYPE = 'ATA'", "older guess from a noisy transcript"),
    (
        "ETA: name search",
        "FULL_NAME LIKE '%TURNAROUND%' OR FULL_NAME LIKE '%TURN AROUND%' "
        "OR FULL_NAME LIKE '%CROSSOVER%' OR FULL_NAME LIKE '%CONNECTOR%' "
        "OR FULL_NAME LIKE '% ETA %' OR FULL_NAME LIKE '% ETA' OR FULL_NAME LIKE 'ETA %'",
        "guesses only; Robbie gave no ETA query",
    ),
]

WANTED_FIELDS = ["FDMID", "STR_TYPE", "ST_CLASS", "FULL_NAME"]


def existing_fields(fc):
    """Return WANTED_FIELDS that exist on fc, in order."""
    names = {f.name.upper() for f in arcpy.ListFields(fc)}

    return [f for f in WANTED_FIELDS if f in names]


def print_str_type_counts(fc):
    """Print every STR_TYPE value with its row count."""
    counts = Counter()

    with arcpy.da.SearchCursor(fc, ["STR_TYPE"]) as cursor:

        for (str_type,) in cursor:
            counts[str_type] += 1

    print("STR_TYPE values in {} ({:,} rows):".format(fc, sum(counts.values())))

    for str_type, n in sorted(counts.items(), key=lambda item: (item[0] is None, item[0])):
        print("  {!r:>8}: {:,}".format(str_type, n))

    print()


def read_matches(fc, fields, where_clause):
    """Return the rows of fc matching where_clause as a list of dicts."""
    rows = []

    with arcpy.da.SearchCursor(fc, fields, where_clause) as cursor:

        for values in cursor:
            rows.append(dict(zip(fields, values)))

    return rows


def summarize(name, note, rows):
    """Print the count, attribute mix and a sample for one candidate."""
    print("{}: {:,} rows ({})".format(name, len(rows), note))

    if not rows:
        print()
        return

    for field in ("STR_TYPE", "ST_CLASS"):

        if field in rows[0]:
            mix = Counter(row[field] for row in rows)
            print("  {} mix: {}".format(field, dict(mix.most_common(8))))

    for row in rows[:SAMPLE_ROWS]:
        print("  " + " | ".join("{}={}".format(k, row[k]) for k in row))

    if len(rows) > SAMPLE_ROWS:
        print("  ... {:,} more in {}".format(len(rows) - SAMPLE_ROWS, OUTPUT_CSV))

    print()


def main():
    if not arcpy.Exists(SOURCE_FC):
        sys.exit("ERROR: Cannot find {}".format(SOURCE_FC))

    fields = existing_fields(SOURCE_FC)
    missing = [f for f in WANTED_FIELDS if f not in fields]

    if missing:
        print("WARNING: fields not found and skipped: {}".format(missing))

    print_str_type_counts(SOURCE_FC)

    all_rows = []

    for name, where_clause, note in CANDIDATES:

        try:
            rows = read_matches(SOURCE_FC, fields, where_clause)

        except Exception as error:
            print("{}: FAILED ({}). Clause: {}".format(name, error, where_clause))
            print()
            continue

        summarize(name, note, rows)

        for row in rows:
            all_rows.append(dict(row, candidate=name))

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["candidate"] + fields)
        writer.writeheader()
        writer.writerows(all_rows)

    print("Report written to: {}".format(OUTPUT_CSV))


if __name__ == "__main__":
    main()
