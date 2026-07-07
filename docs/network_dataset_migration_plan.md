# Network Dataset Migration Plan
## TRN_street_network → LRS-based Network Dataset

### Overview

The existing `SDEADM.TRN_street_network` was built on `SDEADM.TRN_street` (the
old street feature class). The goal is to create a new, equivalent network
dataset whose edge source is `SDEADM.TRNLRS_TRN_STREET_VW` -- a real SDE feature
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
SDEADM.TRNLRS\TRNLRS_TRN_STREET  (copy inside feature dataset — used by ND)
```

Note: the FD copy is named `TRNLRS_TRN_STREET`, not `TRNLRS_TRN_STREET_VW`.
SDE enforces unique feature class base names across the entire geodatabase, so
the copy cannot share the standalone FC's name. See Phase 4 for details.

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
| Edge source | `TRNLRS_TRN_STREET` (copied from standalone `TRNLRS_TRN_STREET_VW` into FD by script 03) |
| Junction source | `TRNLRS_street_junction` (copied from `TRN_streets_routes`) |
| Turn source | `TRNLRS_traffic_turn` (copied from `TRN_streets_routes`, OID-remapped and renamed -- see Phase 4b) |
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
  - Cost attributes (e.g. distance in metres, travel time in minutes) -- note units and evaluator field names
  - Restriction attributes (e.g. one-way, turn restrictions, road class restrictions) -- note field names and default restriction usage type
  - Descriptor attributes -- note field names
  - Hierarchy attribute -- note field name and value ranges
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
| `data/evaluator_field_map.json` | Per-evaluator status -- empty because all evaluators use VB Script expressions, not direct field evaluators |

#### Evaluator review

`evaluator_field_map.json` is empty. This is expected: the existing evaluators use VB
Script expressions (`[SHAPE.STLength()]` for Length; `[STR_DIR]` inside a Select Case for
OneWay) rather than direct field evaluators. `STR_DIR` is present and unchanged in the new
source, so no evaluator changes are needed.

#### Fields only in old source -- impact assessment

| Field | Impact |
|---|---|
| `FROM_ELEV` / `TO_ELEV` | **CRITICAL** -- referenced as elevation fields in the XML template. Fixed in Phase 3. |
| `ACC`, `DATE_ACT`, `LANECOUNT`, `MAINTSUMMER`, `SOURCE`, `SYS_DATE`, `TECH_ACT`, `TECH_MOD` | None -- not referenced by any network evaluator |

#### Notable attribute differences

| Field | Change | Impact |
|---|---|---|
| `ROUTE_ID` | Integer → String(255) | None -- not referenced by any evaluator |
| `FULL_NAME` | length 50 → 255 | None -- wider; directions field reference is unaffected |
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
| `FULL_NAME` | stored field in `TRN_street` | `ROUTENAME` from `LRSN_Route` | Verify evaluators reference `FULL_NAME` -- the output name is the same |
| `STR_REM` | stored field in `TRN_street` | `COMMENT__2` from dyn-seg | Output name unchanged -- no evaluator change needed |
| `FLAGS` | stored field in `TRN_street` | `FLAG` from dyn-seg | Output name unchanged -- no evaluator change needed |

All additions are additive and do not break any existing evaluators.

---

### Phase 3 — Edit the XML Template

**Status:** Complete -- `data/network_template.xml` has been updated

The following changes have been applied to `data/network_template.xml`:

| Element | Old value | New value |
|---|---|---|
| `<Name>` / `<LogicalNetworkName>` | `TRN_street_network` | `TRNLRS_street_network` |
| `<CatalogPath>` | `/FD=TRN_streets_routes/ND=TRN_street_network` | `/FD=TRNLRS/ND=TRNLRS_street_network` |
| Edge source `<Name>` | `TRN_street` | `TRNLRS_TRN_STREET` |
| Junction source `<Name>` | `TRN_street_junction` | `TRNLRS_street_junction` |
| Turn source `<Name>` | `TRN_traffic_turn` | `TRNLRS_traffic_turn` |
| System junction `<Name>` | `TRN_street_network_Junctions` | `TRNLRS_street_network_Junctions` |
| `NetworkSourceName` (evaluators) | `TRN_street` | `TRNLRS_TRN_STREET` |
| `FromElevationFieldName` / `ToElevationFieldName` | `FROM_ELEV` / `TO_ELEV` | *(empty)* |
| `ElevationFieldName` on `SystemJunctionSource` | `ZELEV` | *(empty)* |
| `NetworkElevationModel` | `1` (Elevation Fields) | `0` (None) |

**Elevation:** `TRNLRS_TRN_STREET_VW` does not have `FROM_ELEV` or `TO_ELEV` fields, so
the network uses endpoint-only connectivity (no 3D elevation modelling). The old network
used elevation fields to handle grade separations (bridges, underpasses); verify during
Phase 5 validation that connectivity at these locations is acceptable.

**Edge source name:** the template references `TRNLRS_TRN_STREET` (not `TRNLRS_TRN_STREET_VW`)
because SDE requires unique FC base names across the entire geodatabase. The FD copy must be
named differently from the standalone authoritative FC.

If re-extracting the template from scratch (Phase 1 re-run), all edits above must be
re-applied. The XML `<Name>` element determines the output network dataset name when
`CreateNetworkDatasetFromTemplate` is called -- it must match `NEW_ND_NAME` in
`03_create_network_dataset.py`.

---

### Phase 4 — Create and Build the New Network Dataset

**Script:** `scripts/03_create_network_dataset.py`
**Status:** Complete -- built on Dev and QA (2026-06-26). `TRNLRS_TRN_STREET` has since
been created against **prod** (`E:\HRM\Scripts\SDE\SQL\Prod\prod_RW_sdeadm.sde`) as well.
The script now has a commented-out prod `SDE_CONNECTION` line alongside the active
Dev/QA one -- see the "Prod cutover" note in `network_build_status.md`.

Review and set these configuration variables at the top of the script:

| Variable | Purpose | Current value |
|---|---|---|
| `SDE_CONNECTION` | Path to `.sde` connection file | `E:\HRM\Scripts\SDE\SQL\Dev\dev_RW_sdeadm.sde` / `qa_RW_sdeadm.sde` active; `Prod\prod_RW_sdeadm.sde` available as a commented-out line |
| `FEATURE_DATASET` | Target feature dataset for the new ND | `SDEADM.TRNLRS` |
| `NEW_ND_NAME` | Name of the network dataset to create | `TRNLRS_street_network` |
| `STANDALONE_EDGE_SOURCE` | SDE path to the standalone `TRNLRS_TRN_STREET_VW` FC | `SDEADM.TRNLRS_TRN_STREET_VW` |

The script performs these steps in order:

1. **Validates** that the template XML and target feature dataset both exist.
2. **Copies** the standalone `TRNLRS_TRN_STREET_VW` into `SDEADM.TRNLRS` as `TRNLRS_TRN_STREET`
   using `arcpy.management.CopyFeatures` (skipped if the destination already exists).
3. **Verifies** that all three source FCs are present inside the feature dataset:
   `TRNLRS_TRN_STREET`, `TRNLRS_street_junction`, `TRNLRS_traffic_turn`.
4. **Creates** the network dataset from the XML template via
   `arcpy.na.CreateNetworkDatasetFromTemplate`.
5. **Builds** the network dataset via `arcpy.na.BuildNetwork`.

> **Prerequisites before running:**
> - `TRNLRS_TRN_STREET_VW` must exist as a standalone SDE FC (run `LRS_updates.py` first).
> - `TRNLRS_street_junction` and `TRNLRS_traffic_turn` must already exist inside
>   `SDEADM.TRNLRS` (copy them from `SDEADM.TRN_streets_routes`).
> - `TRNLRS_traffic_turn` must have been remapped to new edge OIDs (see Phase 4b below)
>   before the build will produce a working turn restriction layer.

#### Issues encountered during build (Dev, 2026-06-26)

**Name collision on CopyFeatures**

`CopyFeatures` failed because SDE enforces unique feature class base names across the entire
geodatabase. `TRNLRS_TRN_STREET_VW` already existed as a standalone FC, so the FD copy could
not share that name. Fix: rename the destination copy to `TRNLRS_TRN_STREET` and update all
references in `03_create_network_dataset.py` and `data/network_template.xml` accordingly.

**ERROR 030347: system junction elevation field**

`BuildNetwork` failed because the system junction source still had `ZELEV` set as its
elevation field despite `NetworkElevationModel` being set to `0` (None). Fix: clear
`ElevationFieldName` on the `SystemJunctionSource` element in `network_template.xml`.

#### SQL Server permissions for OS auth users

After the build, OS authentication users received `DBMS table not found` errors when
attempting to add the network dataset. Two sets of system tables required PUBLIC SELECT grants:

**Network metadata tables** (`N_3_*` -- registration ID `3` for `TRNLRS_street_network`):

```sql
GRANT SELECT ON SDEADM.N_3_DESC           TO PUBLIC;
GRANT SELECT ON SDEADM.N_3_EDGEWEIGHT     TO PUBLIC;
GRANT SELECT ON SDEADM.N_3_JUNCTIONWEIGHT TO PUBLIC;
GRANT SELECT ON SDEADM.N_3_PROPS          TO PUBLIC;
GRANT SELECT ON SDEADM.N_3_TOPOLOGY       TO PUBLIC;
GRANT SELECT ON SDEADM.N_3_TURNWEIGHT     TO PUBLIC;
```

**Dirty area tracking tables** (`ND_37029_*` -- registration ID `37029`):

```sql
GRANT SELECT ON SDEADM.ND_37029_DIRTYAREAS   TO PUBLIC;
GRANT SELECT ON SDEADM.ND_37029_DIRTYOBJECTS  TO PUBLIC;
```

**If the network is ever deleted and recreated**, the registration IDs will change. Confirm
the new IDs before re-applying grants:

```sql
SELECT name FROM sys.tables
WHERE schema_id = SCHEMA_ID('SDEADM')
AND (name LIKE 'N_%' OR name LIKE 'ND_%')
ORDER BY name;
```

Cross-reference against `SDEADM.GDB_ITEMS` to confirm which IDs belong to the network:

```sql
SELECT name, physicalname FROM SDEADM.GDB_ITEMS
WHERE name LIKE '%TRNLRS%';
```

---

### Phase 4b — Rebuild Traffic Turn Feature Class

**Script:** `scripts/05_rebuild_traffic_turns.py`
**Status:** Complete

See [`traffic_turns.md`](traffic_turns.md) for full diagnosis and script.

**Problem:** turn feature classes store edge references as `Edge{N}FID` fields containing
the ObjectID of a feature in the registered edge source. The turn FC copied into
`SDEADM.TRNLRS` was copied from `TRN_traffic_turn`, which referenced OIDs in `TRN_street`.
Those OIDs have no meaning in `TRNLRS_TRN_STREET`, so every turn record failed at build
time:

```
Cannot find edge element corresponding to turn identifier 1.
```

**Solution:** spatially remap turn edge references from old OIDs to new OIDs by matching
turn junction points (edge endpoints) against the spatial index of `TRNLRS_TRN_STREET`.
The script creates a new turn FC (`TRNLRS_traffic_turn_new`), populates it with remapped
records, then the old FC is deleted and the new one renamed to `TRNLRS_traffic_turn` --
matching the `TRNLRS_` prefix used by the other two sources, and what
`network_template.xml` already expects.

**Standalone junction warnings** (hundreds of `Standalone user-defined junction is detected`
entries for `TRNLRS_street_junction` in the build errors file) are a separate, non-critical
issue. LRS resegmentation shifted some edge endpoints, leaving manually-placed junctions
no longer coincident with an edge. These are ignored during solves and do not affect results.

**Steps:**

1. Run `scripts/05_rebuild_traffic_turns.py`
2. Review the `written`/`skipped` counts. A small number of skipped turns is acceptable
   (segments removed during resegmentation). A high skipped count (>5% of total) suggests
   the snap tolerance needs adjustment.
3. Delete `TRNLRS_traffic_turn` and rename `TRNLRS_traffic_turn_new` to `TRNLRS_traffic_turn`
4. Rebuild the network
5. Confirm the build errors file no longer contains turn errors
6. Run a turn restriction solve test

---

### Phase 5 — Validation

**Status:** In progress -- properties check passed (2026-06-26); solve tests and turn
rebuild pending

#### Properties check (2026-06-26) ✅

| Check | Result |
|---|---|
| Sources tab | Edge: `TRNLRS_TRN_STREET`; Junction: system + `TRNLRS_street_junction`; Turn: `TRNLRS_traffic_turn` |
| Length cost evaluator | `[SHAPE.STLength()]` Field Script on Along/Against -- correct |
| OneWay restriction | Field Script (VB) on Along/Against referencing `STR_DIR` -- correct |
| TrafficTurn restriction | Prohibited; turn source assigned -- correct |
| Directions field mappings | `Base Name → STR_NAME`, `Suffix Type → STR_TYPE`, `Full Name → FULL_NAME` -- correct |

#### Service area solve (2026-06-29) ✅

Robbie Evans ran a 50,000m (50km) away-from-facility service area solve. Completed without
major issues; network performance was acceptable across the city.

#### Remaining solve tests

- [ ] Route solve between two known endpoints; compare path and cost against `TRN_street_network`
- [ ] Service area solve (5-minute drive) from a known origin; compare coverage against old network
- [ ] One-way restriction enforcement -- route both directions on a known one-way street
- [ ] Turn restriction enforcement -- blocked until Phase 4b is complete
- [ ] Address range fields (`FROM_LEFT`, `TO_LEFT`, `FROM_RIGHT`, `TO_RIGHT`) for geocoding

#### Known differences from old network

- **No elevation modelling** -- endpoint connectivity only; no 3D grade separation handling.
  Pay attention to bridges and underpasses during route solve testing.
- **No travel time attribute** -- Length (metres) is the only cost attribute. Travel time
  is deferred to a future phase (blocked on `E_SpeedLimit` segmentation compatibility).
- **Edge source has 18,575 features** vs. the old `TRN_street` -- the LRS-derived source
  has different segmentation. Standalone junction warnings at build time are expected and
  non-critical.

#### QA review notes (2026-06-29, Robbie Evans)

The following items were flagged during the initial QA session and require follow-up.
See [`network_review.md`](network_review.md) for full details.

- **Transit access roads** (`STR_TYPE = 'ATA'` or similar) -- should be excluded from
  vehicle routing; currently present in the edge source
- **Water access roads** (`STR_TYPE = 'WA'`) -- present because civic addresses are coded
  to them; exclusion from routing requires further discussion given geocoding dependency
- **George's Island** -- road segment present in network but not reachable by road; should
  be excluded
- **Emergency turnarounds** -- flagged by Robbie as potentially needing removal from the
  turn source; confirm scope before finalising turn rebuild

Filtering approach: exclusions should be applied in the SQL/query layer that populates
`TRNLRS_TRN_STREET_VW`, so ineligible segments never enter the edge source. Re-sync and
rebuild required after any filter is applied.

---

### Rebuild Cadence

`TRNLRS_TRN_STREET_VW` is a standalone SDE feature class maintained by
`LRS_updates.py` (truncate/append on each LRS refresh). The copy of this FC
inside `SDEADM.TRNLRS` -- which the network dataset references -- goes stale after
each refresh and must be overwritten.

After each LRS refresh, two steps are required:

1. **Re-copy the edge source** into the feature dataset, overwriting the stale copy:
   ```python
   arcpy.management.CopyFeatures(
       r"<sde>\SDEADM.TRNLRS_TRN_STREET_VW",       # standalone (authoritative)
       r"<sde>\SDEADM.TRNLRS\TRNLRS_TRN_STREET",   # FD copy (used by ND)
   )
   ```
2. **Rebuild the network dataset**:
   ```python
   arcpy.na.BuildNetwork(r"<sde>\SDEADM.TRNLRS\TRNLRS_street_network")
   ```

Both steps are implemented in `scripts/LRS_updates.py` via `sync_network_edge_source()`,
called after the `street_features` loop inside the QC-pass `else` block. A standalone
script `scripts/04_sync_and_rebuild_network.py` also exists for one-off rebuilds outside
a full LRS refresh cycle.

**Note:** the traffic turn FC (`TRNLRS_traffic_turn`) does not need to be rebuilt on each
LRS refresh -- turn restrictions are maintained separately from the street LRS pipeline and
only need to be rebuilt if the turn source itself is updated.

---

### Known Limitations

#### No elevation modelling

`TRNLRS_TRN_STREET_VW` does not carry `FROM_ELEV`/`TO_ELEV` fields because the LRS
pipeline does not segment elevation data. The network uses endpoint-only connectivity.
Grade separations (bridges, underpasses) that were handled by elevation fields in the old
network may produce incorrect connectivity results. Assess during Phase 5 route testing.

#### No travel time attribute

`E_SpeedLimit` segmentation is not compatible with the other LRS event tables used to
build `TRNLRS_TRN_STREET_VW` -- it cannot be included in the same `OverlayEvents` call.
Travel time is therefore not available as a cost attribute in this network. Adding it
requires org approval to modify the `LRS_updates.py` event pipeline. See
`network_build_status.md` for proposed approach and default speed values.

#### Two copies of edge source

`TRNLRS_TRN_STREET_VW` (standalone, authoritative) and `TRNLRS_TRN_STREET` (FD copy,
used by the network) must be kept in sync manually after each LRS refresh. The preferred
long-term fix -- writing `LRS_updates.py` output directly into the FD -- requires an
impact assessment to identify all consumers of `TRNLRS_TRN_STREET_VW` before any
rename/move can happen.

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
│   ├── network_dataset_migration_plan.md   ← this file
│   ├── network_build_status.md             ← current build status and action items
│   ├── network_review.md                   ← QA session notes (Robbie Evans, 2026-06-29)
│   └── traffic_turns.md                    ← turn FC rebuild diagnosis and script
└── scripts/
    ├── 01_extract_network_config.py
    ├── 02_compare_schemas.py
    ├── 03_create_network_dataset.py
    ├── 04_sync_and_rebuild_network.py
    └── 05_rebuild_traffic_turns.py
```
