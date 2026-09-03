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

**⚠️ Everything below dated 2026-07-14 or earlier describing Phase 4/5a as complete has been
superseded by the 2026-09-01 rebuild — see [the 2026-09-01 update](#update-2026-09-01--qa-network-dataset-rebuilt-from-scratch) immediately below this table.**

| Phase | Description | Status |
|---|---|---|
| 1 | Extract old network configuration | ✅ Complete — but `data/network_template.xml` is **stale**, see 2026-09-01 update |
| 2 | Schema comparison (old vs. new edge source) | ✅ Complete |
| 3 | Edit XML template | ✅ Complete (elevation fields cleared — see below) |
| 4 | Create & build new network dataset | ✅ **QA rebuilt from scratch 2026-09-01** (interactive wizard, Python evaluators). Dev still on its original 2026-06-26 build — VBScript, permanently read-only, not rebuilt. Prod: nothing built. |
| 5 | Validation | 🔄 Properties ✅; service area ✅; **turn-restriction solve ✅ (2026-09-01)**; **one-way solve ✅ (2026-09-02/03, after a real multi-day debugging saga — see below)**; route comparison / address-range pending |
| 5a | Traffic turn rebuild | ✅ **Re-verified 2026-09-01** — 1,189 turns written, 99.7% Edge1End agreement, all 10 verifier checks clean, 5 spatial spot checks correct, **1,180 built as live turn elements** (9 rejected at build, see the 2026-09-01 update) |

### Update 2026-09-01 — QA network dataset rebuilt from scratch

QA's `TRNLRS_street_network` was **deleted and rebuilt from scratch** on 2026-09-01. This was
not a routine rebuild — the delete happened as part of the normal turn-FC swap, and then
recreating it from `data/network_template.xml` proved **impossible**: `ERROR 030386`, because
that template's `Length`/`OneWay` evaluators are VBScript, which ArcGIS Pro 3.5 refuses to
build from. The documented fix (convert evaluators to Python via Properties) is itself blocked,
because a network dataset carrying VBScript evaluators opens **permanently read-only** in Pro
3.4+ by design. Full diagnosis, including the four hypotheses tested and ruled out:
[`network_dataset_script_review.md` §F2](network_dataset_script_review.md#f2-error-030386--vbscript-evaluators-make-the-network-dataset-permanently-read-only-qas-nd-must-be-rebuilt-from-scratch-not-from-this-template-confirmed-2026-09-01).

What this means for the state of each environment:

| Environment | Network dataset | Evaluator language | Editable? |
|---|---|---|---|
| **QA** | Rebuilt 2026-09-01, built, 1,180 turns | **Python** | ✅ Yes |
| **Dev** | Original 2026-06-26 build, still functional for solves | VBScript | ❌ **Permanently read-only.** Cannot be edited or rebuilt. Will need the same from-scratch rebuild treatment. |
| **Prod** | Not built | n/a | n/a |

**`data/network_template.xml` is stale and must not be trusted.** Beyond the VBScript problem,
it was found to be missing logic that the live networks actually had: its `OneWay` evaluator is
a hardcoded no-op (`restricted = False`, never reads `STR_DIR`), while Dev's *live* network
carries a real `STR_DIR`-driven `Select Case`. The template was evidently captured in Phase 1
before someone fixed `OneWay` directly in Pro's Properties dialog, and was never re-exported
afterward. The real logic was recovered on 2026-09-01 by running
`CreateTemplateFromNetworkDataset` against Dev (which succeeded on a Pro 3.5.8 machine despite
Esri's KB claiming that operation fails on VBScript-bearing networks — a documented inaccuracy
worth knowing). See [Step 6](#step-6--rebuild-and-re-export-the-network-template-2026-09-01).

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

**QA: superseded — re-done 2026-09-01.** The 2026-09-01 rebuild dropped and reassigned these
tables again. Current IDs: **`N_3`** (reused the same number a third time) and **`ND_40171`**
(replacing `ND_38726`, which no longer exists). Both granted and confirmed working via an
OS-auth add-to-map test. Full trail in `network_dataset_sql_permissions.md`.

*Historical (2026-07-14, now stale):* `N_3` + `ND_38726`, replacing the original `ND_37029`.

**Dev: still pending.** Dev's `TRNLRS_street_network` went through the same swap, so its
`N_<id>`/`ND_<id>` need to be looked up fresh -- run the same procedure there; the IDs will
almost certainly differ from QA's.

**QA: source table grants done (2026-07-14).** All four source tables -- `TRNLRS_TRN_STREET`,
`TRNLRS_street_junction`, `TRNLRS_traffic_turn`, and the easy-to-miss auto-created
`TRNLRS_street_network_Junctions` -- confirmed `PUBLIC SELECT` in QA, plus write access
(`SELECT, INSERT, UPDATE, DELETE`) granted to `HRM\GIS_LRS_EVENT_EDITOR` on all four for
editing turns/junctions. See "Write access for editor roles" in
`network_dataset_sql_permissions.md` for the write-access grants and the caveat that
`TRNLRS_TRN_STREET` edits get overwritten by the next LRS refresh sync. Dev still needs the
same treatment (both the PUBLIC read grants and, if needed there, the editor write grants).

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

**Solve tests — updated 2026-09-01 (against QA's rebuilt network)**

- [ ] Solve a **Route** between two known endpoints; compare path and cost against `TRN_street_network`
- [x] Solve a **Service Area** (e.g. 5-minute drive) from a known origin; compare coverage — 50km service area, Robbie Evans, 2026-06-29
- [ ] ❌ **Confirm one-way restriction is enforced — BLOCKED, currently failing.** Tested 2026-09-01
      against Bishop St (`STR_DIR = 'FOTD'`, geometry confirms Along Digitized = west, so
      *eastbound* should be prohibited). Eastbound solved straight through, 253 ft, no detour.
      Root cause: the Python `OneWay` evaluator entered during the rebuild uses `!STR_DIR!`
      inline inside the **Code Block**, which is not valid — field-token substitution only
      applies to the single-line **Value** expression; the Code Block must be a plain function
      that *receives* the field as a parameter. Corrected form (not yet applied or verified):
      Code Block `def oneway_restricted(str_dir): ...` and Value `oneway_restricted(!STR_DIR!)`.
      See the runbook's §4.4 and [`network_dataset_script_review.md` §F2](network_dataset_script_review.md#f2-error-030386--vbscript-evaluators-make-the-network-dataset-permanently-read-only-qas-nd-must-be-rebuilt-from-scratch-not-from-this-template-confirmed-2026-09-01).
- [x] ✅ **Confirm turn restriction logic works** against `TRNLRS_traffic_turn` — 2026-09-01.
      Turn OID 2 (`QUINPOOL RD → ROBIE ST`, a genuine prohibited movement) solved straight
      through at first (51 ft) because the Route layer's **Travel Mode** did not have
      `TrafficTurn`/`OneWay` checked. After enabling both, the same stops produced a correct
      411 ft loop-around detour. **Restriction attributes do nothing unless the Travel Mode
      enables them** — now recorded in `CLAUDE.md`.
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

### Step 6 — Rebuild and re-export the network template (2026-09-01)

The VBScript deprecation (see [the 2026-09-01 update](#update-2026-09-01--qa-network-dataset-rebuilt-from-scratch))
means the template-driven rebuild path in `scripts/03_create_network_dataset.py` is broken
until a **Python-evaluator template** replaces `data/network_template.xml`. Until then, any
rebuild of this network dataset requires the manual wizard procedure documented in the
[runbook's Phase 3.2](turn_rebuild_qa_test_runbook.md).

**What QA's rebuilt network was configured with** (matching the original, except evaluator
language, and except the `OneWay` bug noted below):

| Attribute | Type | Assignment |
|---|---|---|
| `Length` | Cost, Meters, double | Field Script (Python), `!Shape!` on Along/Against; Constant 0 for Junction/Edge/Turn defaults |
| `OneWay` | Restriction, Prohibited (`-1`) | Field Script (Python) on Along/Against; Constant False for all defaults. **Currently broken — see below.** |
| `TrafficTurn` | Restriction, Prohibited (`-1`) | Constant `True` on the `TRNLRS_traffic_turn` source; Constant `False` on all defaults |

**The recovered `OneWay` logic** (from Dev's live network via `CreateTemplateFromNetworkDataset`,
2026-09-01 — this is the authoritative original, which `data/network_template.xml` never had):

```vbscript
' Along Digitized
restricted = False
Select Case UCase([STR_DIR])
  Case "N", "FDTO", "T": restricted = True
End Select

' Against Digitized -- note FOTD, not FDTO
restricted = False
Select Case UCase([STR_DIR])
  Case "N", "FOTD", "T": restricted = True
End Select
```

So: `FDTO` blocks travel *along* the digitized direction, `FOTD` blocks travel *against* it,
and `N` or `T` block **both** directions (a fully closed segment). Anything else is
unrestricted both ways.

**Correct, confirmed-working Python translation:**

```python
# Code Block
def oneway_restricted(str_dir):
    restricted = False
    if (str_dir or "").upper() in ("N", "FDTO", "T"):   # FOTD for Against Digitized
        restricted = True
    return restricted

# Value
oneway_restricted(!STR_DIR!)
```

**`OneWay` confirmed working 2026-09-02/03 — full debugging trail, worth reading before touching
this evaluator again:**

1. First attempt put `!STR_DIR!` inline inside the Code Block (no function). Build succeeded,
   no errors, but the restriction never fired in either direction.
2. Found via a fresh `CreateTemplateFromNetworkDataset` export that the *Against Digitized*
   evaluator had a copy-paste typo — it tested for `FDTO` (the Along code) instead of `FOTD`.
   Fixed the typo, same inline structure, rebuilt: **still no effect at all**, exact same
   symptom, which ruled out the typo alone as sufficient explanation.
3. Restructured to the function-in-Code-Block/call-from-Value form above. Still no effect —
   even a version hardcoded to unconditionally `return True` (which should prohibit *every*
   edge network-wide in that direction) produced zero change in any solve.
4. Confirmed the Route layer's Travel Mode had `OneWay`/`TrafficTurn` checked (it did) — ruled
   that out too.
5. **Root cause: `Force Full Build` was not checked.** Editing an evaluator's script content
   without a forced rebuild leaves the network's precomputed per-edge weight tables
   (`N_<id>_EDGEWEIGHT`) stale — the solver was reading old cached values the whole time,
   regardless of how correct or hardcoded the evaluator itself was. See the new `CLAUDE.md`
   gotcha ("Editing a Field Script evaluator's Code Block requires Force Full Build"). With
   Force Full Build checked, the hardcoded `return True` immediately produced
   `ERROR 030212: Solve did not find a solution` as expected.
6. That forced rebuild then hung for **18 hours** — a genuine blocking session on the shared
   QA SQL Server, killed by a DBA the next morning (see the new `CLAUDE.md` gotcha
   "Long-running Build Network = check for a blocking SQL session"). Properties showed the
   actual rebuild had committed successfully in the normal ~90 seconds; only a trailing
   client-side step was left hanging on the now-nonexistent session and had to be cancelled
   manually.
7. Reverted the evaluator to the real `STR_DIR` logic (function form, correct `FDTO`/`FOTD`
   per direction), re-ran Force Full Build (normal duration this time), and confirmed on
   `TRNLRS_TRN_STREET` OID 12002 (`STR_DIR='FOTD'`): Along Digitized (west) solves clean;
   Against Digitized (east) correctly returns `ERROR 030212: Solve did not find a solution`.

**Checklist:**

- [x] Rebuild QA's network dataset with Python evaluators (interactive wizard)
- [x] Recover the authoritative `OneWay` logic from Dev before it becomes unrecoverable
- [x] Apply the corrected `OneWay` Python evaluator to QA and re-run Build Network (with Force
      Full Build — required, see above)
- [x] Re-run the one-way solve test — confirmed working 2026-09-03
- [ ] Export the corrected template via `CreateTemplateFromNetworkDataset` and commit it over
      `data/network_template.xml` — now unblocked
- [ ] Confirm `scripts/03_create_network_dataset.py` can rebuild from that new template
      (`CreateNetworkDatasetFromTemplate` with Python evaluators is untested in this project)
- [ ] Apply the same from-scratch rebuild to **Dev** (still VBScript, still read-only)
- [ ] Reply to the DBA (Sylvie Blanchard) who killed the blocking session, confirming it was
      this ArcGIS Pro Build Network operation and not a rogue process
- [ ] Apply to **prod** as part of cutover

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
- [ ] Re-verify the PUBLIC SELECT grants (`N_3_*`, `ND_37029_*`, and all four source
      tables -- `TRNLRS_TRN_STREET`, `TRNLRS_street_junction`, `TRNLRS_traffic_turn`,
      and `TRNLRS_street_network_Junctions`) against prod's registration IDs -- these
      are almost certainly different from the Dev/QA IDs recorded above

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
