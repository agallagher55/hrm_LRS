# Network Dataset Build Status & Action Plan
## TRNLRS_street_network

**Goal:** Replace the legacy `TRN_street_network` with a new LRS-based network dataset
(`TRNLRS_street_network`) whose edge source is `TRNLRS_TRN_STREET_VW`.

For full technical details see [`network_dataset_migration_plan.md`](network_dataset_migration_plan.md).

---

## Current Status

| Phase | Description | Status |
|---|---|---|
| 1 | Extract old network configuration | ✅ Complete |
| 2 | Schema comparison (old vs. new edge source) | ✅ Complete |
| 3 | Edit XML template | ✅ Complete (elevation fields cleared — see below) |
| 4 | Create & build new network dataset | ✅ Complete — Dev and QA built (2026-06-26) |
| 5 | Validation | 🔄 In progress — properties check passed; solve tests pending |
| 5a | Traffic turn rebuild | ✅ Complete -- remapped FC renamed to `TRNLRS_traffic_turn` and left in the `TRNLRS` feature dataset, as planned |

## Confirmed Prerequisites

| Item | Status | Notes |
|---|---|---|
| `SDEADM.TRNLRS` feature dataset exists | ✅ Confirmed | Target FD is ready |
| Spatial reference — `TRNLRS` FD | ✅ Confirmed | `NAD_1983_CSRS_2010_MTM_5_Nova_Scotia` |
| Spatial reference — `TRN_streets_routes` FD | ✅ Confirmed | Identical — no projection on copy |
| `SDEADM.TRNLRS_TRN_STREET_VW` (standalone, outside FD) | ✅ Exists | Script 03 copies it into FD |
| `SDEADM.TRNLRS\TRNLRS_street_junction` | ✅ Copied | Copied from `TRN_streets_routes\TRN_street_junction` |
| `SDEADM.TRNLRS\TRNLRS_traffic_turn` | ✅ Rebuilt | Copied from `TRN_streets_routes\TRN_traffic_turn`, OID-remapped via script 05, and renamed to `TRNLRS_traffic_turn` per the swap step -- see `traffic_turns.md` |
| `SDEADM.TRNLRS\TRNLRS_TRN_STREET` (FD edge copy) | ✅ Copied | Script 03 copied from standalone `TRNLRS_TRN_STREET_VW` |
| `SDEADM.TRNLRS\TRNLRS_street_network` | ✅ Created & built | Dev and QA environments |

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

### Step 2 — Grant PUBLIC SELECT on network system tables ✅

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

```sql
SELECT name FROM sys.tables
WHERE schema_id = SCHEMA_ID('SDEADM')
AND (name LIKE 'N_%' OR name LIKE 'ND_%')
ORDER BY name;
```

Then cross-reference against `SDEADM.GDB_ITEMS` to confirm which IDs belong to `TRNLRS_street_network`:

```sql
SELECT name, physicalname FROM SDEADM.GDB_ITEMS
WHERE name LIKE '%TRNLRS%';
```

**Note:** also verify that the edge source feature classes inside `SDEADM.TRNLRS` (`TRNLRS_TRN_STREET`, `TRNLRS_street_junction`, `TRNLRS_traffic_turn`) have appropriate grants so that OS auth users can run solves, not just open the network dataset.

---

## Remaining Steps

### Step 3 — Rebuild traffic turn feature class ✅ Complete

`TRN_traffic_turn` (the pre-migration FC in `TRN_streets_routes`) was copied into
`SDEADM.TRNLRS`, and its edge references (stored as ObjectIDs of features in the old
`TRN_street` edge source) were spatially remapped against `TRNLRS_TRN_STREET` using
`scripts/05_rebuild_traffic_turns.py`. Per the script's swap step, the remapped output
was renamed to `TRNLRS_traffic_turn` and left in the `SDEADM.TRNLRS` feature dataset --
matching the `TRNLRS_` prefix used by the other two sources and what
`network_template.xml` already expects. No naming corrections were needed.

See [`traffic_turns.md`](traffic_turns.md) for the original diagnosis and remapping script.

- [x] Run `scripts/05_rebuild_traffic_turns.py` to spatially remap turns to new edge OIDs
- [x] Verify written/skipped counts from script output
- [x] Rebuild network after turn FC is replaced
- [ ] Confirm turn restriction logic in a solve test

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

---

## Open Questions / Future Work

### Prod cutover — SDE connection gap

`TRNLRS_TRN_STREET` has now been created against a **prod** SDE connection
(`E:\HRM\Scripts\SDE\SQL\Prod\prod_RW_sdeadm.sde`). Scripts 01/03/04/05 (see
[Key Paths Reference](#key-paths-reference)) only defined `SDE_CONNECTION` / `SDE`
constants pointing at `dev_RW_sdeadm.sde` or `qa_RW_sdeadm.sde` -- none of them had a
prod path wired in. (`LRS_updates.py` is the exception: it already reads
`SDEADM_RW`/`SDEADM_RO` from `config.ini`, which is presumably the real prod config.)

Scripts 03, 04, and 05 now have a commented-out prod `SDE_CONNECTION` / `SDE` line
alongside the active Dev/QA one, using the confirmed path above -- uncomment it to
point a given run at prod instead of manually retyping the path.

Impact of running scripts 01/03/04/05 against prod:
- Because `TRNLRS_TRN_STREET` already exists in prod, `copy_fc_to_fd()`'s
  `arcpy.Exists(dest)` check will skip the copy step (safe), but
  `CreateNetworkDatasetFromTemplate` / `BuildNetwork` will still run against whatever
  `SDE_CONNECTION` is currently set to -- so the active connection line must be
  double-checked before every run, not just the edge source's existence.

**Still open:**
- [ ] Add the same prod connection constant/comment to `01_extract_network_config.py`
      if it will ever need to run against prod (currently unused there -- that script
      targets the legacy `TRN_street_network`, not the TRNLRS one)
- [ ] Consider replacing the "comment out the line you don't want" pattern with an
      explicit `--env` flag or a `ConfigParser` section (as `LRS_updates.py` already
      uses) so prod runs don't depend on remembering to toggle a comment
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
| Prod SDE connection | `E:\HRM\Scripts\SDE\SQL\Prod\prod_RW_sdeadm.sde` -- commented-out option in scripts 03/04/05, see "Prod cutover" above |
| Target feature dataset | `SDEADM.TRNLRS` |
| New network dataset name | `TRNLRS_street_network` |
| Standalone edge source (authoritative) | `SDEADM.TRNLRS_TRN_STREET_VW` |
| FD copy of edge source (used by ND) | `SDEADM.TRNLRS\TRNLRS_TRN_STREET` |
| Turn source (used by ND) | `SDEADM.TRNLRS\TRNLRS_traffic_turn` |
| XML template | `data/network_template.xml` |
| Old network dataset | `SDEADM.TRN_street_network` (in `TRN_streets_routes`) |
