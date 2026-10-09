"""
Audit the network registration tables in QA and save the result as CSV files.

This replaces running the section 2b audit query from network_dataset_sql_permissions.md by
hand in SSMS. It lists every N_<id> and ND_<id> registration group under SDEADM with a count of
the tables that have PUBLIC SELECT, and the object class IDs (DSIDs) of the network and its
sources. It changes nothing in QA.

Run it twice per refresh and keep both sets of files:
  - LABEL = "before", ahead of step 02, to record the state that step 02 deletes.
  - LABEL = "after", once step 06 has built the network, to find the new registration IDs and
    see which ones still need a grant. Grant them with network_dataset_sql_permissions.md, then
    run it again to confirm.

The SQL runs through arcpy.ArcSDESQLExecute on the QA connection file the other scripts use, so
it needs no extra driver or password. The connection must belong to a login that can read
sys.database_permissions, which SDEADM can.

Files go to qa_refresh\\output, named grants_audit_<LABEL>_<timestamp>.csv and
network_ids_<LABEL>_<timestamp>.csv.
"""

import csv
import datetime
import os

import arcpy

import config


# Names the output files so the before and after runs sit side by side.
LABEL = "before"

OUTPUT_DIR = config.OUTPUT_DIR

AUDIT_COLUMNS = [
    "reg_group",
    "table_count",
    "example_table",
    "tables_with_public_select",
    "status",
]

# The section 2b query from network_dataset_sql_permissions.md.
AUDIT_SQL = r"""
SELECT
    CASE
        WHEN t.name LIKE 'ND\_%' ESCAPE '\'
            THEN 'ND_' + SUBSTRING(t.name, 4, CHARINDEX('_', t.name + '_', 4) - 4)
        ELSE 'N_' + SUBSTRING(t.name, 3, CHARINDEX('_', t.name + '_', 3) - 3)
    END AS reg_group,
    COUNT(*) AS table_count,
    MIN(t.name) AS example_table,
    SUM(CASE WHEN pub.permission_name = 'SELECT' THEN 1 ELSE 0 END) AS tables_with_public_select
FROM sys.tables t
OUTER APPLY (
    SELECT TOP 1 p.permission_name
    FROM sys.database_permissions p
    JOIN sys.database_principals dp ON p.grantee_principal_id = dp.principal_id
    WHERE p.major_id = t.object_id
      AND dp.name = 'public'
      AND p.permission_name = 'SELECT'
) pub
WHERE t.schema_id = SCHEMA_ID('SDEADM')
AND (t.name LIKE 'N\_%' ESCAPE '\' OR t.name LIKE 'ND\_%' ESCAPE '\')
GROUP BY
    CASE
        WHEN t.name LIKE 'ND\_%' ESCAPE '\'
            THEN 'ND_' + SUBSTRING(t.name, 4, CHARINDEX('_', t.name + '_', 4) - 4)
        ELSE 'N_' + SUBSTRING(t.name, 3, CHARINDEX('_', t.name + '_', 3) - 3)
    END
ORDER BY reg_group
"""

# The network and its sources, whose object class IDs the registration IDs cluster around.
NETWORK_ITEMS = {
    "network dataset": config.NETWORK,
    "edge source": config.EDGE,
    "junction source": config.JUNCTION,
    "turn source": config.TURN,
    "system junctions": os.path.join(
        config.QA_NETWORK_FD, "SDEADM." + config.NETWORK_DEF.network_name + "_Junctions"
    ),
}


def normalize_rows(result):
    """ArcSDESQLExecute returns a list of rows, but a single row comes back as a flat list."""
    if not result or result is True:
        return []

    if not isinstance(result[0], (list, tuple)):
        return [list(result)]

    return [list(row) for row in result]


def grant_status(table_count, granted):
    if granted == 0:
        return "none granted"

    if granted == table_count:
        return "all granted"

    return "partial"


def run_audit(sde_connection):
    """Return the audit as one dict per registration group."""
    executor = arcpy.ArcSDESQLExecute(sde_connection)
    rows = normalize_rows(executor.execute(AUDIT_SQL))
    audit = []

    for reg_group, table_count, example_table, granted in rows:
        audit.append({
            "reg_group": reg_group,
            "table_count": int(table_count),
            "example_table": example_table,
            "tables_with_public_select": int(granted),
            "status": grant_status(int(table_count), int(granted)),
        })

    return audit


def describe_ids(items):
    """Return (item, path, DSID) for each item. DSID is blank when the item is missing."""
    found = []

    for label, path in items.items():
        dsid = ""

        if arcpy.Exists(path):
            dsid = getattr(arcpy.Describe(path), "DSID", "")

        found.append((label, path, dsid))

    return found


def write_csv(path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(columns)

        for row in rows:
            writer.writerow(row)


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"Network: {config.NETWORK_DEF.key}; label: {LABEL}; connection: {config.QA_SDE}")

    audit = run_audit(config.QA_SDE)
    audit_path = OUTPUT_DIR / f"grants_audit_{LABEL}_{stamp}.csv"
    write_csv(audit_path, AUDIT_COLUMNS, [[row[name] for name in AUDIT_COLUMNS] for row in audit])

    print("\nRegistration groups under SDEADM")

    for row in audit:
        print(
            f"  {row['reg_group']:<12} {row['table_count']:>3} tables  "
            f"{row['tables_with_public_select']:>3} with PUBLIC SELECT  {row['status']}"
        )

    # A network's dirty area tracking set is a DIRTYAREAS and DIRTYOBJECTS pair. Other ND_ groups
    # with one table belong to other networks or to leftovers.
    pairs = [
        row["reg_group"] for row in audit
        if row["reg_group"].startswith("ND_") and row["table_count"] == 2
    ]
    print(f"\nND_ groups with a DIRTYAREAS and DIRTYOBJECTS pair: {', '.join(pairs) if pairs else 'none'}")

    # Single table ND_ groups are other networks or leftovers and are expected to have no grant.
    ungranted = [
        row["reg_group"] for row in audit
        if row["status"] != "all granted" and row["table_count"] > 1
    ]

    if ungranted:
        print(f"Groups with more than one table and a missing grant: {', '.join(ungranted)}")

    ids = describe_ids(NETWORK_ITEMS)
    ids_path = OUTPUT_DIR / f"network_ids_{LABEL}_{stamp}.csv"
    write_csv(ids_path, ["item", "path", "dsid"], ids)

    print("\nObject class IDs")

    for label, _, dsid in ids:
        print(f"  {label:<18} {dsid if dsid != '' else 'not found'}")

    print(f"\nWrote {audit_path}\nWrote {ids_path}")


if __name__ == "__main__":
    main()
