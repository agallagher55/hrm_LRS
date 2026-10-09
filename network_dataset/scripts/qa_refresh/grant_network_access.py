"""
Grant PUBLIC SELECT on the network's registration tables and source tables in QA.

Rebuilding the network creates new N_<id> and ND_<id> system tables that only SDEADM can read, so
nobody else can open it until PUBLIC has SELECT on them (see network_dataset_sql_permissions.md).
This script does that step: it finds the network's own tables, checks which lack the grant and
grants only those.

It is a dry run unless APPLY is True. A dry run prints the GRANT statements and changes nothing.
After an apply it checks every table again and stops with an error if one still has no grant.

How it picks the tables:
  - The ND_ group is ND_<DSID of the network dataset>. It must exist with 2 tables.
  - The N_ group is the only N_ group with 6 tables and no grants at all. With more than one it
    stops and asks you to set N_GROUP below, since it must not guess on a shared database. With none
    it assumes the N_ tables were granted already.
  - The source tables are the edge, junction and turn classes and the system junction class of
    this network (config.NETWORK_DEF), which must all exist.

Run it after step 06, then run audit_grants.py with LABEL = "after" to see the result. It grants
PUBLIC SELECT only. Editor role grants (INSERT, UPDATE, DELETE) are not touched.

The SQL runs through arcpy.ArcSDESQLExecute on the QA connection file. The login must be able to
grant on SDEADM tables, which SDEADM can. Written 2026-10-09, not yet run on live QA.
"""

import csv
import datetime
import re

import arcpy

import audit_grants
import config


# False prints the GRANT statements and changes nothing. Set True to run them.
APPLY = False

# Set this (for example "N_3") only when the script reports more than one candidate N_ group.
N_GROUP = None

SCHEMA = "SDEADM"
SAFE_NAME = re.compile(r"^[A-Za-z0-9_]+$")


def safe_name(name):
    """Only plain table names go into a SQL statement."""
    if not SAFE_NAME.match(str(name)):
        raise RuntimeError(f"Refusing to use the unexpected table name {name!r} in SQL.")

    return str(name)


def fetch(executor, sql):
    """Return the rows of a SELECT as a list of lists, whatever shape ArcSDESQLExecute gave."""
    result = executor.execute(sql)

    if isinstance(result, (str, int, float)) and result is not True:
        return [[result]]

    return audit_grants.normalize_rows(result)


def tables_with_prefix(executor, prefix):
    """Names of the SDEADM tables that start with the registration prefix, for example N_3_."""
    pattern = safe_name(prefix).replace("_", "\\_") + "%"
    sql = (
        f"SELECT name FROM sys.tables WHERE schema_id = SCHEMA_ID('{SCHEMA}') "
        f"AND name LIKE '{pattern}' ESCAPE '\\' ORDER BY name"
    )

    return [row[0] for row in fetch(executor, sql)]


def public_select_status(executor, names):
    """Return {table name: True when PUBLIC has SELECT}. A table that does not exist is missing."""
    listed = ", ".join(f"'{safe_name(name)}'" for name in names)
    sql = f"""
SELECT t.name,
    CASE WHEN EXISTS (
        SELECT 1
        FROM sys.database_permissions p
        JOIN sys.database_principals dp ON p.grantee_principal_id = dp.principal_id
        WHERE p.major_id = t.object_id
          AND dp.name = 'public'
          AND p.permission_name = 'SELECT'
          AND p.state IN ('G', 'W')
    ) THEN 1 ELSE 0 END AS has_select
FROM sys.tables t
WHERE t.schema_id = SCHEMA_ID('{SCHEMA}') AND t.name IN ({listed})
"""
    status = {}

    for name, has_select in fetch(executor, sql):
        status[name] = bool(has_select)

    return status


def find_n_group(audit, override):
    """Return the network's N_ group name, or None when no N_ group with 6 tables lacks grants.

    More than one such group is an error: it cannot be told apart safely on a shared database.
    """
    by_name = {row["reg_group"]: row for row in audit}

    if override:
        row = by_name.get(override)

        if row is None or row["table_count"] != 6:
            raise RuntimeError(f"N_GROUP is {override!r} but no N_ group with 6 tables has that name.")

        return override

    candidates = [
        row["reg_group"] for row in audit
        if row["reg_group"].startswith("N_")
        and row["table_count"] == 6
        and row["tables_with_public_select"] == 0
    ]

    if len(candidates) > 1:
        raise RuntimeError(
            f"Found more than one N_ group with 6 tables and no grants: {candidates}. "
            "Set N_GROUP at the top of the script to the network's group."
        )

    return candidates[0] if candidates else None


def find_nd_group(audit, dsid):
    name = f"ND_{int(dsid)}"
    row = {row["reg_group"]: row for row in audit}.get(name)

    if row is None or row["table_count"] != 2:
        raise RuntimeError(
            f"Expected {name} (the network dataset's DSID) with 2 tables, but it is not there. "
            "Check that step 06 finished and run audit_grants.py."
        )

    return name


def source_table_names():
    definition = config.NETWORK_DEF

    return [
        definition.edge_name,
        definition.junction_name,
        definition.turn_name,
        definition.network_name + "_Junctions",
    ]


def plan_grants(executor):
    """Work out which tables belong to the network and which of them still need a grant."""
    audit = audit_grants.run_audit(config.QA_SDE)
    dsid = arcpy.Describe(config.NETWORK).DSID
    nd_group = find_nd_group(audit, dsid)
    n_group = find_n_group(audit, N_GROUP)

    registration = tables_with_prefix(executor, nd_group + "_")

    if n_group:
        registration += tables_with_prefix(executor, n_group + "_")

    sources = source_table_names()
    # SQL Server answers with the stored case of each name. Use that in the statements.
    found = {name.upper(): (name, has_select) for name, has_select in public_select_status(executor, registration + sources).items()}

    for name in sources:
        if name.upper() not in found:
            raise RuntimeError(f"Source table {SCHEMA}.{name} does not exist in QA.")

    tables = [found[name.upper()][0] for name in registration + sources]
    missing = [actual for actual, has_select in (found[name.upper()] for name in registration + sources) if not has_select]

    return {"nd_group": nd_group, "n_group": n_group, "tables": tables, "missing": missing}


def write_record(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["table", "statement", "result"])

        for row in rows:
            writer.writerow(row)


def main():
    """Print or run the grants. Returns the number of tables that were missing the grant."""
    executor = arcpy.ArcSDESQLExecute(config.QA_SDE)
    plan = plan_grants(executor)
    print(f"Network: {config.NETWORK_DEF.key}; connection: {config.QA_SDE}")
    print(f"Registration groups: {plan['nd_group']} and {plan['n_group'] or 'none (no N_ group with 6 tables lacks grants)'}")
    print(f"Tables checked: {len(plan['tables'])}; missing PUBLIC SELECT: {len(plan['missing'])}")

    if not plan["missing"]:
        print("Nothing to grant.")

        return 0

    statements = [(name, f"GRANT SELECT ON {SCHEMA}.[{safe_name(name)}] TO PUBLIC") for name in plan["missing"]]
    record = []

    for name, statement in statements:
        print(("  " if APPLY else "  would run: ") + statement)

        if APPLY:
            executor.execute(statement)

        record.append([name, statement, "granted" if APPLY else "dry run"])

    if not APPLY:
        print("\nDry run only. Set APPLY = True to run these statements.")

        return len(plan["missing"])

    after = {name.upper(): has_select for name, has_select in public_select_status(executor, plan["tables"]).items()}
    still_missing = [name for name in plan["tables"] if not after.get(name.upper(), False)]

    for row in record:
        if row[0] in still_missing:
            row[2] = "STILL MISSING"

    config.OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = config.OUTPUT_DIR / f"grants_applied_{stamp}.csv"
    write_record(path, record)
    print(f"\nWrote {path}")

    if still_missing:
        raise RuntimeError(f"These tables still have no PUBLIC SELECT after the grants: {still_missing}")

    print("Verified: every table now has PUBLIC SELECT. Run audit_grants.py with LABEL = \"after\" to confirm.")

    return len(plan["missing"])


if __name__ == "__main__":
    main()
