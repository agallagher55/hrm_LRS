# Network Dataset Build Status & Action Plan
## TRN_lrs_street_network

**Goal:** Replace the legacy `TRN_street_network` with a new LRS-based network dataset
(`TRN_lrs_street_network`) whose edge source is `TRNLRS_TRN_STREET_VW`.

For full technical details see [`network_dataset_migration_plan.md`](network_dataset_migration_plan.md).

---

## Current Status

| Phase | Description | Status |
|---|---|---|
| 1 | Extract old network configuration | ✅ Complete |
| 2 | Schema comparison (old vs. new edge source) | ✅ Complete |
| 3 | Edit XML template | ✅ Complete (elevation fields cleared — see below) |
| 4 | Create & build new network dataset | ✅ Complete (Dev) |
| 5 | Validation | 🔄 In progress — properties check passed; solve tests pending |

## Confirmed Prerequisites

| Item | Status | Notes |
|---|---|---|
| `SDEADM.TRNLRS` feature dataset exists | ✅ Confirmed | Target FD is ready |
| Spatial reference — `TRNLRS` FD | ✅ Confirmed | `NAD_1983_CSRS_2010_MTM_5_Nova_Scotia` |
| Spatial reference — `TRN_streets_routes` FD | ✅ Confirmed | Identical — no projection on copy |
| `SDEADM.TRNLRS_TRN_STREET_VW` (standalone, outside FD) | ✅ Exists | Script 03 copies it into FD |
| `SDEADM.TRNLRS\TRNLRS_street_junction` | ✅ Copied | Copied from `TRN_streets_routes\TRN_street_junction` |
| `SDEADM.TRNLRS\TRNLRS_traffic_turn` | ✅ Copied | Copied from `TRN_streets_routes\TRN_traffic_turn` |
| `SDEADM.TRNLRS\TRNLRS_TRN_STREET` (FD edge copy) | ✅ Copied | Script 03 copied from standalone `TRNLRS_TRN_STREET_VW` |
| `SDEADM.TRNLRS\TRN_lrs_street_network` | ✅ Created & built | Dev environment |

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

### Step 1 — Copy junction and turn sources into `SDEADM.TRNLRS` ✅

Copied from `SDEADM.TRN_streets_routes` into `SDEADM.TRNLRS`:
- `TRN_street_junction` → `TRNLRS_street_junction`
- `TRN_traffic_turn` → `TRNLRS_traffic_turn`

Both FDs share `NAD_1983_CSRS_2010_MTM_5_Nova_Scotia` — no reprojection occurred.

---

### Step 2 — Edge source populated ✅

`SDEADM.TRNLRS_TRN_STREET_VW` confirmed populated. Script 03 copied it into
`SDEADM.TRNLRS\TRNLRS_TRN_STREET` (renamed to avoid SDE geodatabase-wide name uniqueness
constraint — two FCs cannot share the same name even across feature datasets).

---

### Step 3 — Create and build the new network dataset ✅

**Script:** `scripts/03_create_network_dataset.py`

Run successfully on Dev. Network dataset `TRN_lrs_street_network` created and built inside
`SDEADM.TRNLRS`.

**Issues encountered and resolved during build:**
- `CopyFeatures` failed with name conflict — SDE requires unique FC names across the entire
  geodatabase. Fixed by renaming the FD copy to `TRNLRS_TRN_STREET` and updating the XML
  template accordingly.
- `BuildNetwork` failed with `ERROR 030347: The system junction class does not have the
  elevation field` — the system junction source still had `ZELEV` set despite
  `NetworkElevationModel=0`. Fixed by clearing `ElevationFieldName` on the
  `SystemJunctionSource` element in `network_template.xml`.

---

## Remaining Steps

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
- [ ] Confirm **turn restriction** logic works
- [ ] Check address range fields (`FROM_LEFT`, `TO_LEFT`, `FROM_RIGHT`, `TO_RIGHT`) for geocoding

---

### Step 5 — Automate refresh in `LRS_updates.py`

Once validated, append these two calls to the end of `LRS_updates.py`'s main block so the
network stays current after every LRS refresh:

```python
# Re-copy edge source and rebuild network after each LRS refresh
arcpy.management.CopyFeatures(
    r"<sde>\SDEADM.TRNLRS_TRN_STREET_VW",      # standalone (authoritative)
    r"<sde>\SDEADM.TRNLRS\TRNLRS_TRN_STREET",  # FD copy (used by ND; named without _VW to avoid SDE name conflict)
)
arcpy.na.BuildNetwork(r"<sde>\SDEADM.TRNLRS\TRN_lrs_street_network")
```

- [ ] Add rebuild steps to `LRS_updates.py`
- [ ] Run a full LRS refresh cycle end-to-end and confirm the network rebuilds cleanly

---

## Key Paths Reference

| Item | Path |
|---|---|
| Dev SDE connection | `E:\HRM\Scripts\SDE\SQL\Dev\dev_RW_sdeadm.sde` |
| QA SDE connection | `E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde` |
| Target feature dataset | `SDEADM.TRNLRS` |
| New network dataset name | `TRN_lrs_street_network` |
| Standalone edge source (authoritative) | `SDEADM.TRNLRS_TRN_STREET_VW` |
| FD copy of edge source (used by ND) | `SDEADM.TRNLRS\TRNLRS_TRN_STREET` |
| XML template | `data/network_template.xml` |
| Old network dataset | `SDEADM.TRN_street_network` (in `TRN_streets_routes`) |
