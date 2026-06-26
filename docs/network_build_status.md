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
| 4 | Create & build new network dataset | ⏳ Blocked (see prerequisites) |
| 5 | Validation | ⏳ Not started |

## Confirmed Prerequisites

| Item | Status | Notes |
|---|---|---|
| `SDEADM.TRNLRS` feature dataset exists | ✅ Confirmed | Target FD is ready |
| Spatial reference — `TRNLRS` FD | ✅ Confirmed | `NAD_1983_CSRS_2010_MTM_5_Nova_Scotia` |
| Spatial reference — `TRN_streets_routes` FD | ✅ Confirmed | Identical — no projection on copy |
| `SDEADM.TRNLRS_TRN_STREET_VW` (standalone, outside FD) | ✅ Exists | Script 03 copies it into FD |
| `SDEADM.TRNLRS\TRNLRS_street_junction` | ❌ Does not exist | Must be copied from `TRN_street_junction` (Step 1) |
| `SDEADM.TRNLRS\TRNLRS_traffic_turn` | ❌ Does not exist | Must be copied from `TRN_traffic_turn` (Step 1) |

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
element and `NetworkElevationModel` set to `0` (None). The new network will use endpoint
connectivity only (no 3D elevation modelling).

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

## Remaining Steps

### Step 1 — Copy junction and turn sources into `SDEADM.TRNLRS` (Phase 4 prerequisite)

The network dataset requires all source FCs to live inside the target feature dataset.
Script 03 handles the edge source automatically but **not** the junction or turn sources.
These FCs do not yet exist in `TRNLRS` and must be copied from their current location in
`SDEADM.TRN_streets_routes`.

> **Spatial reference:** Both FDs use `NAD_1983_CSRS_2010_MTM_5_Nova_Scotia` (confirmed) —
> no reprojection will occur on copy.

- [ ] Copy `SDEADM.TRN_streets_routes\TRN_street_junction` → `SDEADM.TRNLRS\TRNLRS_street_junction`
- [ ] Copy `SDEADM.TRN_streets_routes\TRN_traffic_turn` → `SDEADM.TRNLRS\TRNLRS_traffic_turn`

```python
import arcpy

sde = r"E:\HRM\Scripts\SDE\SQL\Dev\dev_RW_sdeadm.sde"

# Source FCs live in TRN_streets_routes; copies go into TRNLRS for the new ND
arcpy.management.CopyFeatures(
    sde + r"\SDEADM.TRN_streets_routes\SDEADM.TRN_street_junction",
    sde + r"\SDEADM.TRNLRS\TRNLRS_street_junction",
)
arcpy.management.CopyFeatures(
    sde + r"\SDEADM.TRN_streets_routes\SDEADM.TRN_traffic_turn",
    sde + r"\SDEADM.TRNLRS\TRNLRS_traffic_turn",
)
```

---

### Step 2 — Confirm edge source is populated (Phase 4 prerequisite)

`SDEADM.TRNLRS_TRN_STREET_VW` exists as a standalone SDE FC outside the feature dataset
(confirmed). Script 03 will copy it into `SDEADM.TRNLRS` automatically.

- [ ] Confirm `SDEADM.TRNLRS_TRN_STREET_VW` has features (not empty or stale)
- [ ] If stale or empty, run `LRS_updates.py` to refresh it

---

### Step 3 — Create and build the new network dataset (Phase 4)

**Script:** `scripts/03_create_network_dataset.py`

- [ ] Confirm `SDE_CONNECTION` points to the target environment (currently Dev)
- [ ] Run the script — it will:
  1. Copy `TRNLRS_TRN_STREET_VW` into `SDEADM.TRNLRS`
  2. Verify all three source FCs are present
  3. Create the network dataset from `data/network_template.xml`
  4. Build the network dataset (`arcpy.na.BuildNetwork`)
- [ ] Check for errors in the output log

---

### Step 4 — Validate the new network dataset (Phase 5)

- [ ] Open Network Dataset Properties in ArcGIS Pro — check Sources, Travel Attributes, Directions
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
