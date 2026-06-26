# Network Dataset Migration Plan
## TRN_street_network → LRS-based Network Dataset

### Overview

The existing `SDEADM.TRN_street_network` was built on `SDEADM.TRN_street` (the
old street feature class). The goal is to create a new, equivalent network
dataset whose edge source is `SDEADM.TRNLRS_TRN_STREET_VW` — a real SDE feature
class (the `_VW` suffix is a naming convention, not a database view) that is
truncated and repopulated by `LRS_updates.py` on each LRS refresh cycle.

**Important:** `TRNLRS_TRN_STREET_VW` is registered in SDE as a standalone
feature class, not inside any feature dataset. ArcGIS network datasets require
all source FCs to reside inside the target feature dataset, so
`03_create_network_dataset.py` automatically copies it into `SDEADM.TRNLRS`
before creating the network. See [Rebuild Cadence](#rebuild-cadence) for how to
keep that copy current after each LRS refresh.

#### LRS Data Pipeline

```
LRSN_Route + 7 event tables (E_StreetDirection, E_StreetClass, E_AddressRange,
    E_PSAB, E_StreetOwnership, E_StreetStatus, E_WinterMaintenance)
        │
        ▼  arcpy.locref.OverlayEvents
TRNLRS_segmented_street_events   (intermediate dynamic segmentation feature class)
        │
        ▼  SQL query layer (joins E_AddressRange for ADDDATE/MODDATE)
        │  filtered: TO_DATE IS NULL  (active streets only)
        │
        ▼  TruncateTable → Append
TRNLRS_TRN_STREET_VW             (standalone SDE FC — authoritative edge source)
        │
        ▼  CopyFeatures (performed by 03_create_network_dataset.py)
SDEADM.TRNLRS\TRNLRS_TRN_STREET_VW   (copy inside feature dataset — used by ND)
```

---

### Current Network Dataset: TRN_street_network

| Property | Value |
|---|---|
| Location | `SDEADM.TRN_street_network` (SDE, prod_RW_sdeadm) |
| Feature dataset | `SDEADM.TRN_streets_routes` |
| Edge source | `SDEADM.TRN_street` |
| Junction sources | `SDEADM.TRN_street_junction`, `SDEADM.TRN_street_network_Junctions` (system) |
| Turn source | `SDEADM.TRN_traffic_turn` |
| Status | Read-only |
| Uses | Routing, service areas |

### New Network Dataset: TRNLRS_street_network

| Property | Value |
|---|---|
| Location | `SDEADM.TRNLRS_street_network` (SDE, SDEADM.TRNLRS) |
| Feature dataset | `SDEADM.TRNLRS` |
| Edge source | `TRNLRS_TRN_STREET_VW` (copied from standalone FC into FD by script 03) |
| Junction source | `TRNLRS_street_junction` (copied from `TRN_streets_routes`) |
| Turn source | `TRNLRS_traffic_turn` (copied from `TRN_streets_routes`) |
| System junction | `TRNLRS_street_network_Junctions` (auto-created) |

---

### Phase 1 — Extract Old Configuration

**Script:** `scripts/01_extract_network_config.py`  
**Status:** Complete — outputs exist in `data/`

Run this script against the existing network dataset. It produces:

| Output | Purpose |
|---|---|
| `data/network_config.json` | Human-readable dump of all sources, attributes, evaluators, directions, and traffic config |
| `data/network_template.xml` | ArcGIS XML template — the authoritative input for recreating the dataset |

**What to capture and review in `network_config.json`:**

- **Sources**: names, source types (Edge/Junction/Turn), connectivity policies, connectivity groups
- **Travel Attributes** (check each one):
  - Cost attributes (e.g. distance in metres, travel time in minutes) — note units and evaluator field names
  - Restriction attributes (e.g. one-way, turn restrictions, road class restrictions) — note field names and default restriction usage type
  - Descriptor attributes — note field names
  - Hierarchy attribute — note field name and value ranges
- **Directions**: length attribute, time attribute, road class attribute, field mappings (street name field, etc.)
- **Traffic**: type, speed profile table, historical/live attribute names (if configured)

---

### Phase 2 — Schema Comparison

**Script:** `scripts/02_compare_schemas.py`  
**Status:** Complete — outputs in `data/`

Compares fields between `TRN_street` (old) and `TRNLRS_TRN_STREET_VW` (new).
Configure `SDE_CONNECTION`, `OLD_EDGE_SOURCE`, and `NEW_EDGE_SOURCE` at the top
of the script before running. Produces:

| Output | Purpose |
|---|---|
| `data/schema_comparison.json` | Full field-level diff: shared, only-in-old, only-in-new, type/length changes |
| `data/evaluator_field_map.json` | Per-evaluator status — empty because all evaluators use VB Script expressions, not direct field evaluators |

#### Evaluator review

`evaluator_field_map.json` is empty. This is expected: the existing evaluators use VB
Script expressions (`[SHAPE.STLength()]` for Length; `[STR_DIR]` inside a Select Case for
OneWay) rather than direct field evaluators. `STR_DIR` is present and unchanged in the new
source, so no evaluator changes are needed.

#### Fields only in old source — impact assessment

| Field | Impact |
|---|---|
| `FROM_ELEV` / `TO_ELEV` | **CRITICAL** — referenced as elevation fields in the XML template. Fixed in Phase 3. |
| `ACC`, `DATE_ACT`, `LANECOUNT`, `MAINTSUMMER`, `SOURCE`, `SYS_DATE`, `TECH_ACT`, `TECH_MOD` | None — not referenced by any network evaluator |

#### Notable attribute differences

| Field | Change | Impact |
|---|---|---|
| `ROUTE_ID` | Integer → String(255) | None — not referenced by any evaluator |
| `FULL_NAME` | length 50 → 255 | None — wider; directions field reference is unaffected |
| `MAINTENANCE` | length 4 → 8 | None |
| `MUN_CODE` | length 3 → 50, domain dropped | None |
| `PAR_LEFT` / `PAR_RIGHT` | length 10 → 50 | None |
| `PSAB_CODE` | domain dropped | None |
| `STR_TYPE` | length 6 → 50 | None |

**Known schema changes in `TRNLRS_TRN_STREET_VW`** (from `LRS_updates.py`):

Fields added (not in `TRN_street`):

| New Field | Source in pipeline | Notes |
|---|---|---|
| `STR_CODE_L` | `TRNLRS_segmented_street_events` | Left Street Code (Long) |
| `STR_CODE_R` | `TRNLRS_segmented_street_events` | Right Street Code (Long) |
| `ASSETID` | `TRNLRS_segmented_street_events` | Asset ID (Text 50) |
| `ORIGIN_DATE` | `TRNLRS_segmented_street_events` | Origin Date |
| `MAINTENANCE` | `E_WinterMaintenance` event | Text 8, domain `SNF_maintenance` |
| `ADDDATE` | `E_AddressRange` join | Min(ADDDATE) per FDMID |
| `MODDATE` | `E_AddressRange` join | Max(MODDATE) per FDMID |

Fields with internal renames (output field name is unchanged, source column differs):

| Output Field | Old source | New source column | Action |
|---|---|---|---|
| `FULL_NAME` | stored field in `TRN_street` | `ROUTENAME` from `LRSN_Route` | Verify evaluators reference `FULL_NAME` — the output name is the same |
| `STR_REM` | stored field in `TRN_street` | `COMMENT__2` from dyn-seg | Output name unchanged — no evaluator change needed |
| `FLAGS` | stored field in `TRN_street` | `FLAG` from dyn-seg | Output name unchanged — no evaluator change needed |

All additions are additive and should not break any existing evaluators.

**Review any fields listed as "only in old source"** — if they are referenced by
a network evaluator, a replacement field in the new source must be identified
before proceeding.

---

### Phase 3 — Edit the XML Template

**Status:** Complete — `data/network_template.xml` has been updated

The following changes have been applied to `data/network_template.xml`:

| Element | Old value | New value |
|---|---|---|
| `<Name>` / `<LogicalNetworkName>` | `TRN_street_network` | `TRNLRS_street_network` |
| `<CatalogPath>` | `/FD=TRN_streets_routes/ND=TRN_street_network` | `/FD=TRNLRS/ND=TRNLRS_street_network` |
| Edge source `<Name>` | `TRN_street` | `TRNLRS_TRN_STREET_VW` |
| Junction source `<Name>` | `TRN_street_junction` | `TRNLRS_street_junction` |
| Turn source `<Name>` | `TRN_traffic_turn` | `TRNLRS_traffic_turn` |
| System junction `<Name>` | `TRN_street_network_Junctions` | `TRNLRS_street_network_Junctions` |
| `NetworkSourceName` (evaluators) | `TRN_street` | `TRNLRS_TRN_STREET_VW` |
| `FromElevationFieldName` / `ToElevationFieldName` | `FROM_ELEV` / `TO_ELEV` | *(empty)* |
| `NetworkElevationModel` | `1` (Elevation Fields) | `0` (None) |

The elevation field change was identified during Phase 2: `TRNLRS_TRN_STREET_VW` does not
have `FROM_ELEV` or `TO_ELEV` fields, so the network must use endpoint-only connectivity
(no 3D elevation modelling). The old network used elevation fields to handle grade separations
(bridges, underpasses); verify during Phase 5 validation that connectivity at these locations
is acceptable.

If re-extracting the template from scratch (Phase 1 re-run), these edits must be
re-applied. The XML `<Name>` element determines the output network dataset name
when `CreateNetworkDatasetFromTemplate` is called — it must match `NEW_ND_NAME`
in `03_create_network_dataset.py`.

---

### Phase 4 — Create and Build the New Network Dataset

**Script:** `scripts/03_create_network_dataset.py`

Review and set these configuration variables at the top of the script:

| Variable | Purpose | Current value |
|---|---|---|
| `SDE_CONNECTION` | Path to `.sde` connection file | `E:\HRM\Scripts\SDE\SQL\Dev\dev_RW_sdeadm.sde` |
| `FEATURE_DATASET` | Target feature dataset for the new ND | `SDEADM.TRNLRS` |
| `NEW_ND_NAME` | Name of the network dataset to create | `TRNLRS_street_network` |
| `STANDALONE_EDGE_SOURCE` | SDE path to the standalone `TRNLRS_TRN_STREET_VW` FC | `SDEADM.TRNLRS_TRN_STREET_VW` |

The script performs these steps in order:

1. **Validates** that the template XML and target feature dataset both exist.
2. **Copies** the standalone `TRNLRS_TRN_STREET_VW` into `SDEADM.TRNLRS` using
   `arcpy.management.CopyFeatures` (skipped if the destination already exists).
3. **Verifies** that all three source FCs are present inside the feature dataset:
   `TRNLRS_TRN_STREET_VW`, `TRNLRS_street_junction`, `TRNLRS_traffic_turn`.
4. **Creates** the network dataset from the XML template via
   `arcpy.na.CreateNetworkDatasetFromTemplate`.
5. **Builds** the network dataset via `arcpy.na.BuildNetwork`.

> **Prerequisites before running:**
> - `TRNLRS_TRN_STREET_VW` must exist as a standalone SDE FC (run `LRS_updates.py` first).
> - `TRNLRS_street_junction` and `TRNLRS_traffic_turn` must already exist inside
>   `SDEADM.TRNLRS` (copy them from `SDEADM.TRN_streets_routes`).

---

### Phase 5 — Validation

After building, validate the new network dataset before retiring the old one:

- [ ] Open Network Dataset Properties in ArcGIS Pro — step through every tab and confirm Sources, Travel Attributes, Directions match expectations
- [ ] Run a **Route** solve between two known endpoints and compare the result path and travel time against the old network
- [ ] Run a **Service Area** solve (e.g. 5-minute drive time) from a known origin and compare coverage against the old network
- [ ] Check that **one-way** and **turn restriction** logic is correctly enforced
- [ ] Verify **address range** fields (`FROM_LEFT`, `TO_LEFT`, `FROM_RIGHT`, `TO_RIGHT`) are intact for geocoding if used

---

### Rebuild Cadence

`TRNLRS_TRN_STREET_VW` is a standalone SDE feature class maintained by
`LRS_updates.py` (truncate/append on each LRS refresh). The copy of this FC
inside `SDEADM.TRNLRS` — which the network dataset references — goes stale after
each refresh and must be overwritten.

After each LRS refresh, two steps are required:

1. **Re-copy the edge source** into the feature dataset, overwriting the stale copy:
   ```python
   arcpy.management.CopyFeatures(
       r"<sde>\SDEADM.TRNLRS_TRN_STREET_VW",          # standalone (authoritative)
       r"<sde>\SDEADM.TRNLRS\TRNLRS_TRN_STREET_VW",   # FD copy (used by ND)
   )
   ```
2. **Rebuild the network dataset**:
   ```python
   arcpy.na.BuildNetwork(r"<sde>\SDEADM.TRNLRS\TRNLRS_street_network")
   ```

Both steps can be appended to the end of `LRS_updates.py`'s main block to automate the refresh.

---

### File Reference

```
hrm_LRS/
├── data/
│   ├── network_config.json          ← generated by 01_extract_network_config.py
│   ├── network_template.xml         ← generated by 01_extract_network_config.py, edited (see Phase 3)
│   ├── schema_comparison.json       ← generated by 02_compare_schemas.py
│   └── evaluator_field_map.json     ← generated by 02_compare_schemas.py
├── docs/
│   └── network_dataset_migration_plan.md   ← this file
└── scripts/
    ├── 01_extract_network_config.py
    ├── 02_compare_schemas.py
    └── 03_create_network_dataset.py
```
