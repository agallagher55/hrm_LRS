# Network Dataset Build Status & Action Plan
## TRNLRS_street_network

**Goal:** Replace the legacy `TRN_street_network` with a new LRS-based network dataset
(`TRNLRS_street_network`) whose edge source is `TRNLRS_TRN_STREET_VW`.

For full technical details see [`network_dataset_migration_plan.md`](network_dataset_migration_plan.md).

**Feature dataset separation (in progress, 2026-07-14):** the network source FCs and
`TRNLRS_street_network` are being moved out of `SDEADM.TRNLRS` (the LRS feature
dataset) into a dedicated `SDEADM.TRNLRS_network` feature dataset.
`SDEADM.TRNLRS_network` now has `TRNLRS_street_network` built in **both Dev and
QA** -- prod is still on the original layout described throughout most of this
document (FCs living inside `SDEADM.TRNLRS`). In both Dev and QA, script 03 was
run before `scripts/06_migrate_network_fd.py` (which was meant to move the
already-remapped FCs from `SDEADM.TRNLRS` first), so `SDEADM.TRNLRS_network`
was empty when script 03 ran and its fallback copy logic kicked in for all
three sources in both environments -- see the 2026-07-14 regression note under
Step 3. That means:
- The edge (`TRNLRS_TRN_STREET`) and junction (`TRNLRS_street_junction`)
  copies in `TRNLRS_network` are fresh copies from their respective sources
  (prod's `TRNLRS_TRN_STREET_VW` and legacy `TRN_streets_routes`), which is
  fine.
- The turn (`TRNLRS_traffic_turn`) copies in `TRNLRS_network` were fresh,
  **unremapped** copies from the legacy `TRN_traffic_turn` in both
  environments. **Fixed (2026-07-14):** both Dev and QA have since been
  re-remapped via `scripts/05_rebuild_traffic_turns.py` and swapped in
  (delete network dataset → swap turn FCs → re-run script 03 to recreate and
  rebuild) -- see Step 3 below.
- The original three FCs are still sitting untouched in `SDEADM.TRNLRS` in
  **both** Dev and QA -- `scripts/06_migrate_network_fd.py` (the intended
  clean move-and-verify path) hasn't been run in either environment yet, so
  there's duplicate data in both feature datasets for now. No urgency to clean
  this up until the `TRNLRS_network` builds are validated.
- **New action item:** the swap step deletes and recreates
  `TRNLRS_street_network` in both environments, which changes its SQL Server
  registration IDs (the `N_3_*` / `ND_37029_*` numbers from Step 2 are
  specific to the network dataset instance they were granted against). The
  PUBLIC SELECT grants from Step 2 need to be re-applied under the new IDs in
  both Dev and QA before OS-auth users can open the rebuilt network dataset --
  see Step 2 below for the query to find the new IDs.

Sections below that predate this move are left as historical record of what
happened in Dev/QA at the time; where a path is still current for prod but has
changed for Dev/QA, that's called out inline.

---

## Current Status

| Phase | Description | Status |
|---|---|---|
| 1 | Extract old network configuration | ✅ Complete |
| 2 | Schema comparison (old vs. new edge source) | ✅ Complete |
| 3 | Edit XML template | ✅ Complete (elevation fields cleared — see below) |
| 4 | Create & build new network dataset | ✅ Complete — Dev and QA built (2026-06-26) |
| 5 | Validation | 🔄 In progress — properties check passed; solve tests pending |
| 5a | Traffic turn rebuild | ✅ Complete (2026-07-14) -- Dev and QA both re-remapped and swapped in; solve test to confirm turn restrictions still pending; see note below Step 3 |

## Confirmed Prerequisites

| Item | Status | Notes |
|---|---|---|
| `SDEADM.TRNLRS` feature dataset exists | ✅ Confirmed | Target FD is ready |
| Spatial reference — `TRNLRS` FD | ✅ Confirmed | `NAD_1983_CSRS_2010_MTM_5_Nova_Scotia` |
| Spatial reference — `TRN_streets_routes` FD | ✅ Confirmed | Identical — no projection on copy |
| `SDEADM.TRNLRS_TRN_STREET_VW` (standalone, outside FD) | ✅ Exists | Script 03 copies it into FD |
| `SDEADM.TRNLRS\TRNLRS_street_junction` | ✅ Copied | Copied from `TRN_streets_routes\TRN_street_junction` |
| `SDEADM.TRNLRS\TRNLRS_traffic_turn` | ⚠️ Regressed (2026-07-07) | Copied from `TRN_streets_routes\TRN_traffic_turn`, OID-remapped via script 05, and renamed to `TRNLRS_traffic_turn` per the swap step -- see `network_traffic_turns.md`. Reverted to unremapped OIDs; needs script 05 re-run. |
| `SDEADM.TRNLRS\TRNLRS_TRN_STREET` (FD edge copy) | ✅ Copied | Script 03 copied from standalone `TRNLRS_TRN_STREET_VW` |
| `SDEADM.TRNLRS\TRNLRS_street_network` | ✅ Created & built | Dev and QA environments |

**Dev/QA update (2026-07-14):** the four `SDEADM.TRNLRS\...` paths above have
been superseded by `SDEADM.TRNLRS_network\...` copies in **both** Dev and QA
as part of the feature dataset separation (see the note under
[Current Status](#current-status)) -- this table's rows still describe the
original `SDEADM.TRNLRS` copies, which remain in place untouched in both
environments (not yet cleaned up). The new `TRNLRS_network\TRNLRS_traffic_turn`
copies in both Dev and QA started out as fresh, unremapped copies from the
legacy `TRN_traffic_turn` (picked up via script 03's fallback copy logic
rather than the intended FD move), but both have since been re-remapped and
swapped in -- see Step 3 below.

---

## Schema Comparison Findings (Phase 2)

**Outputs:** `data/schema_comparison.json`, `data/evaluator_field_map.json`

### Evaluators — no changes needed

`evaluator_field_map.json` is empty because the existing evaluators use VB Script expressions,
not direct field evaluators. Both are safe with the new source:
- **Length**: `[SHAPE.STLength()]` — geometry-based, no field dependency
- **OneWay**: VB script referencing `[STR_DIR]` — field present and unchanged in new source

### Fields missing from new source

These fields exist in `TRN_street` but **not** in `TRNLRS_TRN_STREET_VW`:

| Field | Type | Impact |
|---|---|---|
| `FROM_ELEV` | SmallInteger | **CRITICAL** — was edge elevation field in ND template (fixed, see below) |
| `TO_ELEV` | SmallInteger | **CRITICAL** — was edge elevation field in ND template (fixed, see below) |
| `ACC` | String(5) | None — not referenced by any evaluator |
| `DATE_ACT` | Date | None |
| `LANECOUNT` | SmallInteger | None |
| `MAINTSUMMER` | String(4) | None |
| `SOURCE` | String(12) | None |
| `SYS_DATE` | Date | None |
| `TECH_ACT` | String(32) | None |
| `TECH_MOD` | String(32) | None |

**XML template fix applied:** `FROM_ELEV`/`TO_ELEV` references cleared from the edge source
element, `ZELEV` cleared from the system junction source, and `NetworkElevationModel` set to
`0` (None). The new network will use endpoint connectivity only (no 3D elevation modelling).

### Fields added in new source

| Field | Type | Notes |
|---|---|---|
| `ADDDATE` | Date | Min add date from `E_AddressRange` |
| `MODDATE` | Date | Max modified date from `E_AddressRange` |
| `ORIGIN_DATE` | Date | Origin date from dyn-seg |

### Notable attribute differences

| Field | Change | Impact |
|---|---|---|
| `ROUTE_ID` | Integer → String(255) | None — not referenced by any evaluator |
| `FULL_NAME` | length 50 → 255 | None — wider is fine for directions field |
| `MAINTENANCE` | length 4 → 8 | None |
| `MUN_CODE` | length 3 → 50, domain dropped | None |
| `PAR_LEFT` / `PAR_RIGHT` | length 10 → 50 | None |
| `PSAB_CODE` | domain dropped | None |
| `STR_TYPE` | length 6 → 50 | None |

---

## Completed Steps

### Step 1 — Create and build the new network dataset ✅

**Script:** `scripts/03_create_network_dataset.py`

Run successfully on Dev and QA. The script automatically copies all three source FCs into
`SDEADM.TRNLRS` if not already present (skips if they exist), then creates and builds
`TRNLRS_street_network`.

- `TRNLRS_TRN_STREET_VW` (standalone) → copied into FD as `TRNLRS_TRN_STREET`
  (renamed to avoid SDE geodatabase-wide name uniqueness constraint)
- `TRN_street_junction` → copied into FD as `TRNLRS_street_junction`
- `TRN_traffic_turn` → copied into FD, OID-remapped (script 05), and renamed to
  `TRNLRS_traffic_turn` -- consistent with the `TRNLRS_` prefix used by the other
  two sources

Both `TRN_streets_routes` and `TRNLRS` FDs share `NAD_1983_CSRS_2010_MTM_5_Nova_Scotia` —
no reprojection occurs on copy.

**Issues encountered and resolved during Dev build:**
- `CopyFeatures` failed with name conflict — SDE requires unique FC names across the entire
  geodatabase. Fixed by renaming the FD copy to `TRNLRS_TRN_STREET` and updating the XML
  template accordingly.
- `BuildNetwork` failed with `ERROR 030347: The system junction class does not have the
  elevation field` — the system junction source still had `ZELEV` set despite
  `NetworkElevationModel=0`. Fixed by clearing `ElevationFieldName` on the
  `SystemJunctionSource` element in `network_template.xml`.

### Step 2 — Grant PUBLIC SELECT on network system tables ✅ QA re-granted (2026-07-14); Dev still pending

OS authentication users could not add `TRNLRS_street_network` to ArcGIS Pro. Two separate sets of SDE system tables required grants, resolved in sequence:

**Error 1:** `DBMS table not found [SDEADM.N_3_Props]`

Missing SELECT grants on the network metadata tables (`N_3_*`). These are created by ArcGIS when the network dataset is registered; the registration ID is `3` for `TRNLRS_street_network`. Confirmed by querying `sys.tables` for `N_3_%` in the `SDEADM` schema -- six tables exist. Modelled on the PUBLIC grant already in place for the equivalent `N_2_*` tables backing `TRN_street_network`.

```sql
GRANT SELECT ON SDEADM.N_3_DESC           TO PUBLIC;
GRANT SELECT ON SDEADM.N_3_EDGEWEIGHT     TO PUBLIC;
GRANT SELECT ON SDEADM.N_3_JUNCTIONWEIGHT TO PUBLIC;
GRANT SELECT ON SDEADM.N_3_PROPS          TO PUBLIC;
GRANT SELECT ON SDEADM.N_3_TOPOLOGY       TO PUBLIC;
GRANT SELECT ON SDEADM.N_3_TURNWEIGHT     TO PUBLIC;
```

**Error 2:** `DBMS table not found [SDEADM.ND_37029_DirtyObjects]`

After the `N_3_*` grants, a second error surfaced for the dirty area tracking tables (`ND_37029_*`). These are separate from the `N_3_*` metadata tables and also require PUBLIC SELECT. The registration ID `37029` is specific to this network dataset instance.

```sql
GRANT SELECT ON SDEADM.ND_37029_DIRTYAREAS   TO PUBLIC;
GRANT SELECT ON SDEADM.ND_37029_DIRTYOBJECTS  TO PUBLIC;
```

After both sets of grants, `TRNLRS_street_network` loads successfully under OS auth connections. ✅

**If rebuilding the network dataset from scratch**, both sets of grants will need to be re-applied -- the registration IDs (`3` and `37029`) may change if the network is deleted and recreated. Confirm the new IDs by querying:

**This has now actually happened (2026-07-14):** the turn FC swap in both Dev and QA
deleted and recreated `TRNLRS_street_network` (delete network dataset → swap turn FCs →
re-run script 03 -- see Step 3). The `3` / `37029` registration IDs above were captured
against the original 2026-06-26 build and were stale after the rebuild.

A full step-by-step procedure (plus a faster aggregated audit query and known gotchas --
including that `GDB_ITEMS` actually lives under the `sde` schema, not `SDEADM` as the old
snippet here claimed) now lives in
[`network_dataset_sql_permissions.md`](network_dataset_sql_permissions.md). Short version of
that query:

```sql
SELECT name FROM sys.tables
WHERE schema_id = SCHEMA_ID('SDEADM')
AND (name LIKE 'N\_%' ESCAPE '\' OR name LIKE 'ND\_%' ESCAPE '\')
ORDER BY name;
```

**QA: done (2026-07-14).** New IDs identified and granted: `N_3` (same number as the
original build, but its grant had been dropped by the delete+recreate) and `ND_38726`
(replacing the original `ND_37029`). Full disambiguation trail in
`network_dataset_sql_permissions.md`.

**Dev: still pending.** Dev's `TRNLRS_street_network` went through the same swap, so its
`N_<id>`/`ND_<id>` need to be looked up fresh -- run the same procedure there; the IDs will
almost certainly differ from QA's.

**Note:** also verify that the three source feature classes (`TRNLRS_TRN_STREET`,
`TRNLRS_street_junction`, `TRNLRS_traffic_turn`) have appropriate grants so that OS auth
users can run solves, not just open the network dataset -- see step 5 in
`network_dataset_sql_permissions.md`.

---

## Remaining Steps

### Step 3 — Rebuild traffic turn feature class ✅ Complete (2026-07-14, Dev and QA)

`TRN_traffic_turn` (the pre-migration FC in `TRN_streets_routes`) was originally copied into
`SDEADM.TRNLRS`, and its edge references (stored as ObjectIDs of features in the old
`TRN_street` edge source) were spatially remapped against `TRNLRS_TRN_STREET` using
`scripts/05_rebuild_traffic_turns.py`. Per the script's swap step, the remapped output
was renamed to `TRNLRS_traffic_turn` and left in the `SDEADM.TRNLRS` feature dataset --
matching the `TRNLRS_` prefix used by the other two sources and what
`network_template.xml` already expects. This was marked complete after the 2026-06-26 QA build.

**Regression found 2026-07-07:** a fresh QA build (`ms-gis-sql-q21`, Build Time Jul 7 17:55:29)
again showed all 1,209 `TRNLRS_traffic_turn` records failing with
`Cannot find edge element corresponding to turn identifier 1` -- i.e. `TRNLRS_traffic_turn`
is back to referencing the old, unremapped `TRN_street` OIDs, and Turns shows `0` in
Network Dataset Properties.

Most likely cause: `scripts/03_create_network_dataset.py`'s `copy_fc_to_fd()` only copies
`TRN_traffic_turn` → `TRNLRS_traffic_turn` if the destination doesn't already exist. If the
network dataset (and its feature dataset contents) was deleted and recreated at some point
after 2026-06-26, re-running script 03 would have silently re-copied the raw, unremapped
turn FC over the previously-remapped one. Script 03 and `05_rebuild_traffic_turns.py` now
log this distinction explicitly (copy vs. skip) via `scripts/log_utils.py` to make this
easier to catch going forward.

**Same regression hit again in Dev and QA (2026-07-14):** during the `SDEADM.TRNLRS_network`
feature-dataset-separation pilot, `scripts/03_create_network_dataset.py` was run against
both Dev and QA before `scripts/06_migrate_network_fd.py` (which was supposed to move the
already-remapped `TRNLRS_traffic_turn` out of `SDEADM.TRNLRS` first). Since
`SDEADM.TRNLRS_network` was still empty in both environments, `copy_fc_to_fd()`'s "skip if
destination exists" check didn't fire, and script 03 fell back to copying fresh from the
raw, unremapped `SDEADM.TRN_streets_routes\TRN_traffic_turn` in each -- confirmed in Dev by
inspecting the new `SDEADM.TRNLRS_network\TRNLRS_traffic_turn` attribute table: every row
has `EDGE1FCID = 7134`, the old `TRN_street` source's registration ID (also the value baked
into `network_template.xml`'s original `<ClassID>` from the Phase 1 extraction), not the
new `TRNLRS_TRN_STREET` copy's freshly assigned ID. `scripts/05_rebuild_traffic_turns.py`
now has a Dev + `SDEADM.TRNLRS_network` configuration (active by default) plus a commented
QA + `SDEADM.TRNLRS_network` config, so the remap can be re-run against the new location in
either environment -- see the "Key Paths Reference" note on script 05 below.

**Status:** both Dev and QA turn FCs have been re-remapped via script 05 and swapped in
(2026-07-14). QA's remap: 1,238 total input turns, 1,209 written, 29 skipped (2.3% --
within the acceptable range). Both environments completed the full swap sequence: delete
network dataset → swap turn FCs → re-run script 03 to recreate and rebuild. The original,
previously-remapped `SDEADM.TRNLRS\TRNLRS_traffic_turn` copies were left untouched in both
environments during this whole process and may still be good copies -- worth comparing
before fully retiring them.

Remaining before this is fully validated:
- Confirm the rebuilt networks in both Dev and QA show nonzero turns in Network Dataset
  Properties (Sources tab).
- Re-apply the Step 2 PUBLIC SELECT grants under the new registration IDs in both
  environments -- deleting and recreating the network dataset changed them (see Step 2
  above).
- Run a turn-restriction solve test in both environments.

**Swap step also corrected (2026-07-13):** `TRNLRS_traffic_turn` is a registered turn source
of `TRNLRS_street_network`, which makes it a "controller dataset" participant -- ArcGIS
refuses to `Delete` or `Rename` it (`ERROR 001919`) while the network dataset exists. The
documented swap order (delete old, rename new, then `BuildNetwork`) never actually worked as
written for that reason. `05_rebuild_traffic_turns.py` now deletes the network dataset first
to release the lock, then swaps the turn FCs, then requires re-running
`scripts/03_create_network_dataset.py` to recreate and rebuild the network dataset. The
staging FC (`TRNLRS_traffic_turn_staging`) is also now created via `in_template_feature_class`
instead of `in_network_dataset`, so it isn't registered as a live source and stays freely
deletable/renameable before it's swapped in.

See [`network_traffic_turns.md`](network_traffic_turns.md) for the original diagnosis and remapping script.

- [x] Run `scripts/05_rebuild_traffic_turns.py` to spatially remap turns to new edge OIDs (2026-06-26, QA)
- [x] Verify written/skipped counts from script output
- [x] Rebuild network after turn FC is replaced
- [x] Re-run `scripts/05_rebuild_traffic_turns.py` against Dev + `SDEADM.TRNLRS_network` (2026-07-14 regression)
- [x] Re-run `scripts/05_rebuild_traffic_turns.py` against QA + `SDEADM.TRNLRS_network` (2026-07-14 regression; 1,209/1,238 written, 2.3% skipped)
- [x] Complete the swap in Dev (delete network dataset → swap turn FCs → re-run script 03)
- [x] Complete the swap in QA (delete network dataset → swap turn FCs → re-run script 03)
- [ ] Confirm rebuilt Dev and QA networks show nonzero turns in Network Dataset Properties
- [x] Re-apply Step 2 PUBLIC SELECT grants under the new registration IDs (QA -- `N_3` + `ND_38726`, 2026-07-14)
- [ ] Re-apply Step 2 PUBLIC SELECT grants under the new registration IDs (Dev -- still pending)
- [ ] Confirm turn restriction logic in a solve test (Dev and QA)

---

### Step 4 — Validate the new network dataset (Phase 5)

**Properties check ✅ (2026-06-26)**

| Check | Result |
|---|---|
| Sources tab | Edge: `TRNLRS_TRN_STREET`; Junction: system + `TRNLRS_street_junction`; Turn: `TRNLRS_traffic_turn` |
| Length cost evaluator | `[SHAPE.STLength()]` Field Script on Along/Against — correct |
| OneWay restriction | Field Script (VB) on Along/Against referencing `STR_DIR` — correct |
| TrafficTurn restriction | Prohibited; turn source assigned — correct |
| Directions field mappings | `Base Name → STR_NAME`, `Suffix Type → STR_TYPE`, `Full Name → FULL_NAME` — correct |

**Solve tests — pending**

- [ ] Solve a **Route** between two known endpoints; compare path and cost against `TRN_street_network`
- [ ] Solve a **Service Area** (e.g. 5-minute drive) from a known origin; compare coverage
- [ ] Confirm **one-way restriction** is enforced (test a one-way street in both directions)
- [ ] Confirm **turn restriction** logic works against `TRNLRS_traffic_turn` (rebuilt -- see Step 3)
- [ ] Check address range fields (`FROM_LEFT`, `TO_LEFT`, `FROM_RIGHT`, `TO_RIGHT`) for geocoding

---

### Step 5 — Automate sync and rebuild in `LRS_updates.py` ✅

**Script:** `scripts/04_sync_and_rebuild_network.py`

`TRNLRS_TRN_STREET` (FD copy used by the network) must be kept in sync with
`TRNLRS_TRN_STREET_VW` (standalone authoritative FC) after every LRS refresh.

**Implemented in `scripts/LRS_updates.py`:**
- Network Analyst extension checked out at startup (alongside LocationReferencing); raises
  `LicenseError` if unavailable
- `sync_network_edge_source(sde_connection)` function added — calls `append_feature()` to
  truncate/reload `TRNLRS_TRN_STREET` from `TRNLRS_TRN_STREET_VW`, then calls `BuildNetwork`
- Called after the `street_features` loop, inside the QC-pass `else` block
- Both extensions checked in the `finally` block

`scripts/04_sync_and_rebuild_network.py` also exists as a standalone script if a one-off
sync/rebuild is needed outside of a full LRS refresh cycle.

- [x] Check out Network Analyst extension in `LRS_updates.py`
- [x] Add `sync_network_edge_source()` call to `LRS_updates.py` after the `street_features` loop
- [ ] Deploy updated `LRS_updates.py` to `E:\HRM\Scripts\Python\LRS_updates.py`
- [ ] Run a full LRS refresh cycle end-to-end and confirm the network rebuilds cleanly

**Feature dataset separation note:** `sync_network_edge_source()` and
`scripts/04_sync_and_rebuild_network.py` now target `SDEADM.TRNLRS_network`
instead of `SDEADM.TRNLRS` for the FD copy and network dataset path. Since
`LRS_updates.py` has not been deployed to prod yet (see checklist above), this
hasn't caused a live failure -- but prod's FCs must be moved into
`SDEADM.TRNLRS_network` (mirroring the Dev pilot) before this deploys,
otherwise the sync step will fail to find `TRNLRS_TRN_STREET` at its new
expected path.

---

## Open Questions / Future Work

### Prod cutover — SDE connection gap

`TRNLRS_TRN_STREET` has now been created against a **prod** SDE connection
(`E:\HRM\Scripts\SDE\SQL\Prod\prod_RW_sdeadm.sde`). Scripts 01/03/04/05 (see
[Key Paths Reference](#key-paths-reference)) only defined `SDE_CONNECTION` / `SDE`
constants pointing at `dev_RW_sdeadm.sde` or `qa_RW_sdeadm.sde` -- none of them had a
prod path wired in. (`LRS_updates.py` is the exception: it already reads
`SDEADM_RW`/`SDEADM_RO` from `config.ini`, which is presumably the real prod config.)

This has since been resolved differently for each script, based on where each
one's data actually needs to live:

- **`scripts/03_create_network_dataset.py`** always reads `TRNLRS_TRN_STREET_VW`
  from a dedicated `PROD_SDE_CONNECTION` (using the confirmed path above),
  since that FC only exists in prod. `SDE_CONNECTION_UPDATE` (Dev/QA/prod, still
  a manually-edited constant) controls where the FD copy, junction/turn sources,
  and new network dataset get created.
- **`scripts/04_sync_and_rebuild_network.py`** is now prod-only -- there's no
  Dev/QA target at all. Dev/QA builds are one-off snapshots created by script 03;
  only prod's copy of `TRNLRS_TRN_STREET` needs continuous re-syncing after every
  LRS refresh, since that's the copy live routing actually uses. See the script's
  docstring for the reasoning.
- **`scripts/05_rebuild_traffic_turns.py`** still has a manually-edited `SDE`
  constant (Dev/QA/prod) with no dedicated prod constant yet -- see the open item
  below.

**Still open:**
- [ ] Add a dedicated `PROD_SDE_CONNECTION` to `scripts/05_rebuild_traffic_turns.py`
      (currently just a single manually-edited `SDE` constant) for consistency
      with scripts 03/04
- [ ] Add the same prod connection constant/comment to `01_extract_network_config.py`
      if it will ever need to run against prod (currently unused there -- that script
      targets the legacy `TRN_street_network`, not the TRNLRS one)
- [ ] Consider replacing the "manually edit the active connection constant" pattern
      in script 03 with an explicit `--env` flag or a `ConfigParser` section (as
      `LRS_updates.py` already uses) so prod-vs-Dev/QA runs don't depend on
      remembering to edit the right line
- [ ] Re-verify the PUBLIC SELECT grants (`N_3_*`, `ND_37029_*`, and the three source
      FCs) against prod's registration IDs -- these are almost certainly different from
      the Dev/QA IDs recorded above

### Edge source naming

The current approach copies `TRNLRS_TRN_STREET_VW` (standalone, outside FD) into
`TRNLRS_TRN_STREET` (inside `SDEADM.TRNLRS`) on each network refresh. This is the agreed
working approach. The copy is necessary because SDE enforces unique FC names across the entire
geodatabase, so the FD copy cannot share the `_VW` name.

The preferred long-term fix — writing `LRS_updates.py` output directly into the FD, eliminating
the copy step — requires an **impact assessment** to identify all scripts and services consuming
`SDEADM.TRNLRS_TRN_STREET_VW` outside the feature dataset before any rename/move can happen.

- [ ] Impact assessment: audit all scripts and map services referencing `SDEADM.TRNLRS_TRN_STREET_VW`
- [ ] Based on findings, decide whether to rename/move the FC or keep the copy approach long-term

---

### Travel time cost attribute (speed limits)

Not included in the initial network build — the old `TRN_street_network` never had a travel
time attribute, so this is a net-new capability deferred to a future phase.

**Data source:** `SDEADM.E_SpeedLimit` (field `SPEED`, km/h) — already in the TRNLRS FD.
**Not** `TRNLRS_SpeedLimit_Neighbourhood_VW`, which is a display/review product for areas
under neighbourhood speed review and does not represent adopted posted speeds.
`E_SpeedLimit_Neighbourhood` represents zones where a speed limit change is under community
review — it has no routing speed value.

**Preferred approach:** add `E_SpeedLimit` to the main `event_tables` in `DynSegFeature.__init__`
(one line, same pattern as the existing 7 events) so `SPEED` is segmented into
`TRNLRS_TRN_STREET_VW`. Requires org approval before modifying this org-wide product's schema.

**Proposed default speeds** (for segments with no posted speed limit, derived from `ST_CLASS`):

| ST_CLASS | Default speed (km/h) |
|---|---|
| `FREEWAY` | 100 |
| `EXPRESSWAY` | 80 |
| `ARTERIAL` | 60 |
| `MAJOR COLLECTOR` | 50 |
| `MINOR COLLECTOR` | 50 |
| `LOCAL STREET` | 50 |

- [ ] Get approval to add `E_SpeedLimit` to the main `OverlayEvents` call in `LRS_updates.py`
- [ ] Confirm default speed values with traffic/operations team
- [ ] Add `SPEED` to SQL in `_update_streets` and to the edge source
- [ ] Add `TravelTime` cost attribute to `network_template.xml` with VB script evaluator
- [ ] Delete and recreate `TRNLRS_street_network` after template update

---

## Key Paths Reference

| Item | Path |
|---|---|
| Dev SDE connection | `E:\HRM\Scripts\SDE\SQL\Dev\dev_RW_sdeadm.sde` |
| QA SDE connection | `E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde` |
| Prod SDE connection | `E:\HRM\Scripts\SDE\SQL\Prod\prod_RW_sdeadm.sde` -- always used as `PROD_SDE_CONNECTION` in scripts 03/04 (04 uses it exclusively); still a manually-edited `SDE` constant in script 05, see "Prod cutover" above |
| Target feature dataset | `SDEADM.TRNLRS_network` in Dev and QA (both built 2026-07-14); `SDEADM.TRNLRS` still in prod -- see feature dataset separation note above |
| New network dataset name | `TRNLRS_street_network` |
| Standalone edge source (authoritative) | `SDEADM.TRNLRS_TRN_STREET_VW` (unchanged -- outside any feature dataset, prod only) |
| FD copy of edge source (used by ND) | `SDEADM.TRNLRS_network\TRNLRS_TRN_STREET` in Dev/QA; `SDEADM.TRNLRS\TRNLRS_TRN_STREET` in prod |
| Turn source (used by ND) | `SDEADM.TRNLRS_network\TRNLRS_traffic_turn` in Dev/QA -- both re-remapped via script 05 and swapped in (2026-07-14); `SDEADM.TRNLRS\TRNLRS_traffic_turn` in prod |
| XML template | `data/network_template.xml` |
| Old network dataset | `SDEADM.TRN_street_network` (in `TRN_streets_routes`) |
