# Network Dataset Migration Plan
## TRN_street_network → LRS-based Network Dataset

### Overview

The existing `SDEADM.TRN_street_network` was built on `SDEADM.TRN_street` (the old street feature class). The goal is to create a new, equivalent network dataset whose edge source is the LRS-derived street layer (`SDEADM.TRNLRS_TRN_STREET_VW`), preserving all routing and service area behaviour.

---

### Current Network Dataset: TRN_street_network

| Property | Value |
|---|---|
| Location | `SDEADM.TRN_street_network` (SDE, prod_RW_sdeadm) |
| Edge source | `SDEADM.TRN_street` |
| Junction sources | `SDEADM.TRN_street_junction`, `SDEADM.TRN_street_network_Junctions` (system) |
| Turn source | `SDEADM.TRN_traffic_turn` |
| Status | Read-only |
| Uses | Routing, service areas |

---

### Phase 1 — Extract Old Configuration

**Script:** `scripts/01_extract_network_config.py`

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

Compares fields between `TRN_street` (old) and `TRNLRS_TRN_STREET_VW` (new). Produces:

| Output | Purpose |
|---|---|
| `data/schema_comparison.json` | Full field-level diff: shared, only-in-old, only-in-new, type/length changes |
| `data/evaluator_field_map.json` | Per-evaluator status: OK, ACTION REQUIRED, or WARNING |

**Known schema additions in new LRS source** (from visual inspection):

| New Field | Notes |
|---|---|
| `STR_CODE_L` | Left Street Code (Long) |
| `STR_CODE_R` | Right Street Code (Long) |
| `ASSETID` | Asset ID (Text 50) |
| `ADDDATE` | Add Date |
| `MODDATE` | Modified Date |
| `ORIGIN_DATE` | Origin Date |
| `MAINTENANCE` | Winter Maintenance (Text 8, domain `SNF_maintenance`) |

These are additive — they should not break any existing evaluators.

**Review any fields listed as "only in old source"** — if they are referenced by a network evaluator, a replacement field in the new source must be identified before proceeding.

---

### Phase 3 — Edit the XML Template

Before running the creation script, the exported `data/network_template.xml` must be edited. Work from a copy.

**Required changes:**

1. **Edge source name**: Replace all occurrences of `TRN_street` (the old edge source) with the correct new edge source name throughout the XML.

2. **Evaluator field names**: For any evaluator flagged `ACTION REQUIRED` in `data/evaluator_field_map.json`, find the corresponding `<Evaluator>` element in the XML and update `<FieldName>` to the correct field in the new source.

3. **Directions field mappings**: Confirm the street name field (`STR_NAME`) and other directions field references still match the new source.

4. **Junction and turn sources**: If `TRN_street_junction` or `TRN_traffic_turn` are unchanged, no edit is needed. If they are renamed or replaced, update accordingly.

**XML elements to locate:**

```xml
<!-- Edge source definition -->
<NetworkSource xsi:type="esri:NetworkEdgeSource">
  <Name>TRN_street</Name>   ← update this
  ...
</NetworkSource>

<!-- Field evaluator example -->
<Evaluator xsi:type="esri:NetworkFieldEvaluator">
  <FieldName>STR_DIR</FieldName>   ← verify or update
  <Expression> ... </Expression>
</Evaluator>

<!-- Directions field mapping -->
<FieldMap>
  <FieldName>STR_NAME</FieldName>   ← verify
</FieldMap>
```

---

### Phase 4 — Create and Build the New Network Dataset

**Script:** `scripts/03_create_network_dataset.py`

Creates the new network dataset inside the target feature dataset using the edited XML template, then immediately builds it.

Update `FEATURE_DATASET` and `NEW_ND_NAME` in the script before running.

---

### Phase 5 — Validation

After building, validate the new network dataset before retiring the old one:

- [ ] Open Network Dataset Properties in ArcGIS Pro — step through every tab and confirm Sources, Travel Attributes, Directions match expectations
- [ ] Run a **Route** solve between two known endpoints and compare the result path and travel time against the old network
- [ ] Run a **Service Area** solve (e.g. 5-minute drive time) from a known origin and compare coverage against the old network
- [ ] Check that **one-way** and **turn restriction** logic is correctly enforced
- [ ] Verify **address range** fields (`FROM_LEFT`, `TO_LEFT`, `FROM_RIGHT`, `TO_RIGHT`) are intact for geocoding if used

---

### Key Risk: Edge Source is a Database View

`TRNLRS_TRN_STREET_VW` has a `_VW` suffix indicating it is a database view. **ArcGIS Network Datasets require the edge source to be a true, registered feature class — not a view.**

Confirm one of the following before proceeding:
- The underlying materialized feature class (not the view) will be used as the edge source, **or**
- The view is registered with the geodatabase as a versioned, queryable feature class (rare but possible in some SDE configurations)

If using the underlying feature class, update the source name in the XML template and in `scripts/03_create_network_dataset.py` accordingly.

---

### File Reference

```
hrm_LRS/
├── data/
│   ├── network_config.json          ← generated by 01_extract_network_config.py
│   ├── network_template.xml         ← generated by 01_extract_network_config.py, edited manually
│   ├── schema_comparison.json       ← generated by 02_compare_schemas.py
│   └── evaluator_field_map.json     ← generated by 02_compare_schemas.py
├── docs/
│   └── network_dataset_migration_plan.md   ← this file
└── scripts/
    ├── 01_extract_network_config.py
    ├── 02_compare_schemas.py
    └── 03_create_network_dataset.py
```
