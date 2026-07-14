# Network Dataset SQL View Permissions

## Why this is needed

Building or rebuilding a network dataset (e.g. `TRNLRS_street_network`) creates a set of
internal SQL Server system tables under the owning schema (`SDEADM`). By default only the
owning login can read them. OS-authentication users can browse to the network dataset in
Catalog and even see it listed, but adding it to a map fails with:

```
DBMS table not found [SDEADM.N_<id>_Props]
```

or

```
DBMS table not found [SDEADM.ND_<id>_DirtyObjects]
```

until `PUBLIC` is explicitly granted `SELECT` on the specific tables backing that network
dataset instance.

**This has to be redone every time the network dataset is deleted and recreated** (e.g. as
part of the `05_rebuild_traffic_turns.py` swap procedure -- see
[`network_traffic_turns.md`](network_traffic_turns.md)). Deleting a network dataset drops its
system tables; recreating it builds fresh ones, and SQL Server permissions do not carry over
to a new object even if it happens to get the same name/ID.

## Two families of system tables

| Prefix | Count | Tables | Purpose | ID stability |
|---|---|---|---|---|
| `N_<id>_*` | 6 | `DESC`, `EDGEWEIGHT`, `JUNCTIONWEIGHT`, `PROPS`, `TOPOLOGY`, `TURNWEIGHT` | Network dataset metadata and weight/evaluator storage | Small sequential integer, assigned per network dataset. Observed to sometimes stay the same across a delete+recreate if it's reused as the next free slot -- don't assume it changed, but don't assume it didn't either. |
| `ND_<id>_*` | 2 | `DIRTYAREAS`, `DIRTYOBJECTS` | Dirty-area tracking (what needs rebuilding after edits) | Larger integer, drawn from a different sequence than `N_<id>`. Reliably changes on delete+recreate. |

Both prefixes are unrelated numbering schemes -- e.g. `TRNLRS_street_network` has been seen
as `N_3` paired with `ND_37029` in one build and `N_3` paired with `ND_38712` (or `ND_7293`,
unconfirmed as of this writing) after a rebuild. Never assume the two IDs match or move
together.

## Step-by-step procedure

### 1. Confirm you're in the right database

New SSMS query windows default to your login's default database, not necessarily the one
hosting the geodatabase. Check first:

```sql
SELECT DB_NAME();
```

If it's wrong, switch via the database dropdown in the SSMS toolbar, or:

```sql
USE <gis_database_name>;
GO
```

(For this project: database `GISRW01` on `ms-gis-sql-q21` for QA.)

### 2. List current registration IDs

```sql
SELECT name FROM sys.tables
WHERE schema_id = SCHEMA_ID('SDEADM')
AND (name LIKE 'N\_%' ESCAPE '\' OR name LIKE 'ND\_%' ESCAPE '\')
ORDER BY name;
```

This lists every `N_<id>_*` and `ND_<id>_*` set currently registered under `SDEADM`. On a
shared database, expect to see sets that belong to **other** networks entirely -- filter
mentally by table count (a proper Network Dataset's `ND_<id>` set has both `DIRTYAREAS` and
`DIRTYOBJECTS`; older/different network types may only have `DIRTYOBJECTS`).

### 2b. Faster combined audit (list IDs + grant status in one query)

The raw table list above can run to dozens of rows on a shared database, and steps 2-4 as
written mean re-querying per candidate ID one at a time. This single query collapses the
raw list into one row per registration group, with a per-group grant count so the groups
still needing a grant are obvious without any manual per-ID follow-up:

```sql
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
ORDER BY reg_group;
```

Read the result: `tables_with_public_select = 0` means nothing in that group is granted yet
(a freshly rebuilt network's tables always start here -- see step 3); `= table_count` means
fully granted already; anything in between is an inconsistent/partial state worth
investigating rather than re-granting over. `table_count` alone still tells you the group's
*shape* (6 = Network Analyst network dataset `N_<id>`, 2 = a complete `ND_<id>` dirty-area
pair, 1 = an orphaned/incomplete `ND_<id>` leftover, other counts = likely an unrelated
object type such as a geometric network). This is exactly what identified `N_3` and
`ND_38726` in the 2026-07-14 QA run below -- both came back `0 / table_count`, with no
ambiguous partial grants to sort out.

Cross-reference against the geodatabase item catalog if you want to confirm a dataset is
actually registered (note: this system table lives under the `sde` schema, **not**
`SDEADM` -- querying `SDEADM.GDB_ITEMS` fails with `Invalid object name`):

```sql
SELECT name, physicalname FROM sde.GDB_ITEMS
WHERE name LIKE '%TRNLRS_street_network%';
```

This confirms the dataset exists but does **not** give you the `N_<id>`/`ND_<id>` numbers
directly -- those only come from the `sys.tables` query above.

### 3. Disambiguate `ND_<id>` candidates on a shared database

If more than one `ND_<id>` pair looks plausible (both tables present, no obvious legacy
markers), do not guess. Check each candidate's existing permission history first:

```sql
SELECT dp.name AS principal, p.permission_name
FROM sys.database_permissions p
JOIN sys.database_principals dp ON p.grantee_principal_id = dp.principal_id
WHERE p.major_id = OBJECT_ID('SDEADM.ND_<id>_DIRTYAREAS');
```

A rich pre-existing grant set tied to unrelated roles (e.g. `LRSUSER`,
`HRM\GIS_LRS_EVENT_EDITOR` -- roles associated with the LRS event tables, not the street
network) is a red flag that the ID belongs to a **different** dataset, not the one you just
rebuilt. A freshly rebuilt network's `ND_<id>` tables should have **no** grants at all before
you add them.

The only fully reliable confirmation is the client-side error itself: have an OS-auth user
(anyone connecting *without* the SDE admin login) try adding the network dataset to a map.
The exact `DBMS table not found [SDEADM.ND_<id>_...]` error names the correct ID directly --
no inference needed. Re-test after each grant attempt to confirm you fixed the right table.

### 4. Grant PUBLIC SELECT

Once an ID is confirmed correct:

```sql
GRANT SELECT ON SDEADM.N_<id>_DESC           TO PUBLIC;
GRANT SELECT ON SDEADM.N_<id>_EDGEWEIGHT     TO PUBLIC;
GRANT SELECT ON SDEADM.N_<id>_JUNCTIONWEIGHT TO PUBLIC;
GRANT SELECT ON SDEADM.N_<id>_PROPS          TO PUBLIC;
GRANT SELECT ON SDEADM.N_<id>_TOPOLOGY       TO PUBLIC;
GRANT SELECT ON SDEADM.N_<id>_TURNWEIGHT     TO PUBLIC;

GRANT SELECT ON SDEADM.ND_<id>_DIRTYAREAS    TO PUBLIC;
GRANT SELECT ON SDEADM.ND_<id>_DIRTYOBJECTS  TO PUBLIC;
```

Check before granting if you want to avoid redundant no-op grants (also useful as the
disambiguation check in step 3):

```sql
SELECT dp.name AS principal, p.permission_name
FROM sys.database_permissions p
JOIN sys.database_principals dp ON p.grantee_principal_id = dp.principal_id
WHERE p.major_id = OBJECT_ID('SDEADM.N_<id>_PROPS');
```

### 5. Verify grants on the source feature classes -- all four, not just three

Opening the network dataset only needs the `N_<id>_*`/`ND_<id>_*` grants above. Actually
**solving** against it also requires read access to the three *registered* sources, plus a
fourth table that's easy to miss:

```sql
SELECT dp.name AS principal, p.permission_name
FROM sys.database_permissions p
JOIN sys.database_principals dp ON p.grantee_principal_id = dp.principal_id
WHERE p.major_id = OBJECT_ID('SDEADM.TRNLRS_TRN_STREET');
-- repeat for SDEADM.TRNLRS_street_junction, SDEADM.TRNLRS_traffic_turn,
-- and SDEADM.TRNLRS_street_network_Junctions
```

Grant `SELECT ... TO PUBLIC` on any of the four missing it.

**`SDEADM.TRNLRS_street_network_Junctions` is easy to overlook.** It's the auto-created
*system junction* feature class (the `SystemJunctionSource` in `network_template.xml`) --
a separate physical table from `TRNLRS_street_junction`, generated automatically when the
network dataset is built, living in the same feature dataset. Missing its grant produces:

```
Insufficient permissions [SDEADM.TRNLRS_street_network_Junctions]
```

immediately followed by a secondary, misleading

```
DBMS table not found [...] Invalid object name 'SDEADM.TRNLRS_street_network'.
```

on the network dataset itself when adding it to a map -- the second error is fallout from
the first failed lookup (same `STATE_ID`), not a separate root cause. Diagnose by the first
line, not the second.

### 6. Re-test

Have an OS-auth user:
1. Add `TRNLRS_street_network` to a fresh map -- confirms the `N_<id>`/`ND_<id>` grants and
   all four source-table `SELECT` grants (including the system junctions table).
2. Run a Route or Service Area solve -- confirms the source feature class grants.

## Write access for editor roles

Everything above is `PUBLIC SELECT` -- enough to browse and solve, but not to edit. Editing
(e.g. deleting bad/duplicate turn records) needs `INSERT`/`UPDATE`/`DELETE` granted to the
*specific* editor role, not `PUBLIC`. Missing this produces a distinct, less obvious error
in ArcGIS Pro when you try to delete/edit features:

```
Delete Selected Features failed.
The selection contains no editable features. - No edits producing database changes were found.
```

This can also mean the connection itself is read-only (e.g. an `RO`-prefixed `.sde`
connection file) -- rule that out first by confirming you're on an `RW` connection before
chasing SQL grants.

Once on a genuine read-write connection, check/grant per table, per role -- same pattern as
the `PUBLIC SELECT` grants above but scoped to the specific role and including write verbs:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE ON SDEADM.TRNLRS_TRN_STREET               TO [HRM\GIS_LRS_EVENT_EDITOR];
GRANT SELECT, INSERT, UPDATE, DELETE ON SDEADM.TRNLRS_street_junction          TO [HRM\GIS_LRS_EVENT_EDITOR];
GRANT SELECT, INSERT, UPDATE, DELETE ON SDEADM.TRNLRS_street_network_Junctions TO [HRM\GIS_LRS_EVENT_EDITOR];
GRANT SELECT, INSERT, UPDATE, DELETE ON SDEADM.TRNLRS_traffic_turn             TO [HRM\GIS_LRS_EVENT_EDITOR];
```

Windows domain logins/roles need bracket-quoting (`[HRM\GIS_LRS_EVENT_EDITOR]`) because of
the `\`. `SELECT` has to be included even if the role already has `PUBLIC SELECT` -- editing
in ArcGIS Pro reads the current value before writing, and the same "no editable features"
error can mask a read-side gap as easily as a write-side one.

**Caveat on `TRNLRS_TRN_STREET` specifically:** it's the FD copy of the LRS-authoritative
edge source, truncated and reloaded from `TRNLRS_TRN_STREET_VW` on every LRS refresh via
`sync_network_edge_source()` (see `network_dataset_migration_plan.md`). Any manual edits
made there through this grant will be silently overwritten on the next sync. Granted anyway
in QA per the confirmed status below -- worth keeping in mind if edits there seem to
"disappear."

**SQL Server has no "grant on the whole feature dataset" statement** -- a feature dataset is
a geodatabase-level grouping, not a SQL Server securable. Every grant above (`PUBLIC SELECT`
or role-specific write access) has to be issued per physical table. This is also why the
Catalog "Manage > Privileges" dialog for a feature dataset works by silently iterating and
granting each child table individually -- and why it can fail once that per-table state gets
inconsistent (see the gotcha below).

## Known gotchas

- **`GDB_ITEMS` lives under the `sde` schema**, not `SDEADM` -- despite `SDEADM` owning the
  network dataset's own `N_<id>`/`ND_<id>` tables, the core geodatabase repository tables
  belong to a different owner.
- **New SSMS query tabs default to your login's default database**, which is often not the
  GIS database. Always confirm with `SELECT DB_NAME();` before running lookups.
- **Placeholder text is not valid SQL.** `<id>` in the templates above must be replaced with
  an actual number before running -- leaving it in literally produces
  `Msg 102, Incorrect syntax near '<'`.
- **`N_<id>` can reuse the same number across a delete+recreate**; `ND_<id>` reliably does
  not. Never assume either way -- always re-check.
- **This is a shared, multi-project database.** Multiple unrelated `N_<id>`/`ND_<id>` sets
  will exist simultaneously. Don't grant based on "looks new" alone -- confirm via existing
  permission history and, ideally, the actual client-side error.
- **ArcGIS Pro's Catalog "Manage > Privileges" dialog stops working on a feature dataset
  after you grant its network dataset's system tables directly via SQL.** Applying (Apply or
  OK) fails with a generic `Error: Unexpected operation`, no further detail. Cause: granting
  `N_<id>_*`/`ND_<id>_*` tables via raw `GRANT` puts the feature dataset's children into a
  mixed privilege state (some objects grant-managed via SQL, others still at their prior
  ArcGIS-managed default) that the dialog can't reconcile into the single uniform state it
  needs to render checkboxes for. Observed on QA (`SDEADM.TRNLRS_network`, 2026-07-14) right
  after granting `N_3_*`/`ND_38726_*` via SSMS -- Dev's equivalent dialog still worked at the
  time because Dev hadn't had any manual SQL grants applied yet. This does **not** mean the
  SQL grants failed or anything is broken -- confirm via the permission-check queries above
  instead of the GUI. Once a feature dataset's network dataset tables have been granted via
  SQL, keep managing that dataset's permissions via SQL going forward; don't fall back to the
  Catalog dialog expecting it to still work.

## Current status (QA, `ms-gis-sql-q21` / `GISRW01`, as of 2026-07-14)

**Supersedes the 2026-07-13 entry below.** `TRNLRS_street_network` was deleted and
recreated again on 2026-07-14 as part of the turn FC swap
(`scripts/05_rebuild_traffic_turns.py` + `scripts/03_create_network_dataset.py` -- see
`network_build_status.md` Step 3), which drops and reassigns these tables again regardless
of what was granted before.

| Table set | Status |
|---|---|
| `N_1_*` | Unrelated -- 10 tables including `ESTATUS`/`FLODIR`/`JSTATUS` is a geometric network's table shape, not the 6-table Network Analyst `N_<id>` pattern. Not touched. |
| `N_2_*` | `TRN_street_network` (legacy). Not touched. |
| `N_3_*` | `TRNLRS_street_network`. Same ID number as the 2026-07-13 build, but the 2026-07-14 delete+recreate dropped its `PUBLIC SELECT` grant -- confirmed via the [2b audit query](#2b-faster-combined-audit-list-ids--grant-status-in-one-query) returning `0 / 6`, then **granted** (all 6 tables). |
| `ND_7293_*` | `TRN_street_network`'s dirty-area tracking -- matches the `<DSID>7293</DSID>` captured in the original `network_template.xml` extraction (Phase 1, from the old network, before any of the LRS-migration edits). This resolves the 2026-07-13 "Blocked" disambiguation below: `ND_7293` belongs to the *old* network, not `TRNLRS_street_network`. Not touched. |
| `ND_12010_*`, `ND_21268_*`, `ND_396_*` | Only `DIRTYOBJECTS` present (no matching `DIRTYAREAS`) -- orphaned leftovers from earlier deleted/recreated network datasets during this migration. Not touched. |
| `ND_38726_*` | `TRNLRS_street_network`'s new dirty-area tracking ID -- replaces both the original `ND_37029` and the 2026-07-13 session's unconfirmed `ND_38712` guess (neither exists anymore after this rebuild). Confirmed via the audit query returning `0 / 2` with no pre-existing `LRSUSER`/etc. grants (unlike the `ND_38712` false lead from 2026-07-13), then **granted** (both tables). |

**Resolved:** the 2026-07-13 "Blocked" item (disambiguating `ND_38712` vs `ND_7293`) is moot
now -- `ND_38712` no longer exists after the 2026-07-14 rebuild, and `ND_7293` is confirmed
to belong to `TRN_street_network`, not `TRNLRS_street_network`, via the `DSID` match above.

**PUBLIC SELECT on the four source tables: done (2026-07-14).** `TRNLRS_TRN_STREET`,
`TRNLRS_street_junction`, `TRNLRS_traffic_turn`, and `TRNLRS_street_network_Junctions`
(the auto-created system junction FC -- see step 5) all confirmed granted. Add-to-map and
attribute browsing confirmed working for an OS-auth user after these were applied.

**Write access for `HRM\GIS_LRS_EVENT_EDITOR`: done (2026-07-14).** `SELECT, INSERT,
UPDATE, DELETE` granted on all four source tables (`TRNLRS_TRN_STREET`,
`TRNLRS_street_junction`, `TRNLRS_street_network_Junctions`, `TRNLRS_traffic_turn`) -- see
"Write access for editor roles" above. Triggered by a real editing need: deleting duplicate
turn records at an intersection failed with `The selection contains no editable features`
until this was granted. Note the `TRNLRS_TRN_STREET` caveat above -- edits there get
overwritten by the next LRS refresh sync.

**Still open:**
1. Re-test via an OS-auth "add to map" + solve (step 6 below) -- add-to-map confirmed; Route
   / Service Area solve test still pending.
2. Run this whole procedure against **Dev** -- Dev's `TRNLRS_street_network` went through
   the same delete+recreate swap on 2026-07-14, so its registration IDs need to be looked
   up fresh (both the `PUBLIC SELECT` grants and, if the same editor role needs to edit
   turns/junctions in Dev, the write-access grants too); they will almost certainly differ
   from QA's numbers above.
3. Run against prod once `TRNLRS_street_network` is built there.

## Historical status (QA, 2026-07-13, superseded above)

| Table set | Status |
|---|---|
| `N_1_*` | Legacy/different network, unrelated to `TRNLRS_street_network`. Not touched. |
| `N_2_*` | `TRN_street_network` (legacy). Already granted (pre-existing). |
| `N_3_*` | `TRNLRS_street_network`. Registration ID unchanged across the latest rebuild. `PUBLIC SELECT` confirmed already present -- no action needed. |
| `ND_12010_*`, `ND_21268_*`, `ND_396_*` | Only `DIRTYOBJECTS` present (no matching `DIRTYAREAS`) -- legacy/different networks. Not touched. |
| `ND_38712_*` | `PUBLIC SELECT` granted on both tables this session, **but unconfirmed** -- `DIRTYAREAS` already had a pre-existing grant set built around `LRSUSER`/`HRM\GIS_LRS_EVENT_EDITOR` (LRS event-table roles), suggesting this ID may actually belong to a different, LRS-related dataset rather than `TRNLRS_street_network`. |
| `ND_7293_*` | Untested candidate. Not yet checked or granted. |

**Blocked:** disambiguating `ND_38712` vs `ND_7293` requires an OS-auth "add to map" test,
which needs a second machine/account -- not available in the current session. Next steps
for whoever picks this up:

1. Run the OS-auth add-to-map test.
2. If the error names `ND_7293`, run the permission check + grant for that ID (same pattern
   as step 3/4 above).
3. Update this table with the confirmed result.
4. If `ND_38712` turns out to belong to a different dataset, the `PUBLIC SELECT` grant added
   to it this session is a harmless extra (read-only, low risk) and does not need to be
   revoked unless someone objects.

**Still open from `network_build_status.md`:** the same procedure needs to be run against
prod once `TRNLRS_street_network` is built there -- prod's registration IDs will almost
certainly differ from QA's.
