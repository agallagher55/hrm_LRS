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
| 2 | Schema comparison (old vs. new edge source) | ⏳ Not run |
| 3 | Edit XML template with new names | ✅ Complete |
| 4 | Create & build new network dataset | ⏳ Blocked (see prerequisites) |
| 5 | Validation | ⏳ Not started |

---

## Remaining Steps

### Step 1 — Run schema comparison (Phase 2)

**Script:** `scripts/02_compare_schemas.py`

- [ ] Set `SDE_CONNECTION`, `OLD_EDGE_SOURCE`, `NEW_EDGE_SOURCE` at top of script
- [ ] Run against a QA or prod environment where both FCs exist
- [ ] Review `data/evaluator_field_map.json` — resolve any `ACTION REQUIRED` items before
      proceeding to Phase 4

Expected outputs:
- `data/schema_comparison.json`
- `data/evaluator_field_map.json`

---

### Step 2 — Copy junction and turn sources into `SDEADM.TRNLRS` (Phase 4 prerequisite)

The network dataset requires all source FCs to live inside the target feature dataset.
Script 03 handles the edge source automatically but **not** the junction or turn sources.

- [ ] Copy `SDEADM.TRN_street_junction` → `SDEADM.TRNLRS\TRNLRS_street_junction`
- [ ] Copy `SDEADM.TRN_traffic_turn` → `SDEADM.TRNLRS\TRNLRS_traffic_turn`

```python
import arcpy

sde = r"E:\HRM\Scripts\SDE\SQL\Dev\dev_RW_sdeadm.sde"

arcpy.management.CopyFeatures(
    sde + r"\SDEADM.TRN_street_junction",
    sde + r"\SDEADM.TRNLRS\TRNLRS_street_junction",
)
arcpy.management.CopyFeatures(
    sde + r"\SDEADM.TRN_traffic_turn",
    sde + r"\SDEADM.TRNLRS\TRNLRS_traffic_turn",
)
```

---

### Step 3 — Run `LRS_updates.py` to populate edge source (Phase 4 prerequisite)

`TRNLRS_TRN_STREET_VW` must exist as a populated standalone SDE FC before script 03
can copy it into the feature dataset.

- [ ] Confirm `SDEADM.TRNLRS_TRN_STREET_VW` exists and has features
- [ ] If stale or empty, run `LRS_updates.py` to refresh it

---

### Step 4 — Create and build the new network dataset (Phase 4)

**Script:** `scripts/03_create_network_dataset.py`

- [ ] Confirm `SDE_CONNECTION` points to the target environment (currently Dev)
- [ ] Run the script — it will:
  1. Copy `TRNLRS_TRN_STREET_VW` into `SDEADM.TRNLRS`
  2. Verify all three source FCs are present
  3. Create the network dataset from `data/network_template.xml`
  4. Build the network dataset (`arcpy.na.BuildNetwork`)
- [ ] Check for errors in the output log

---

### Step 5 — Validate the new network dataset (Phase 5)

- [ ] Open Network Dataset Properties in ArcGIS Pro — check Sources, Travel Attributes, Directions
- [ ] Solve a **Route** between two known endpoints; compare path and cost against `TRN_street_network`
- [ ] Solve a **Service Area** (e.g. 5-minute drive) from a known origin; compare coverage
- [ ] Confirm **one-way restriction** is enforced (test a one-way street in both directions)
- [ ] Confirm **turn restriction** logic works
- [ ] Check address range fields (`FROM_LEFT`, `TO_LEFT`, `FROM_RIGHT`, `TO_RIGHT`) for geocoding

---

### Step 6 — Automate refresh in `LRS_updates.py`

Once validated, append these two calls to the end of `LRS_updates.py`'s main block so the
network stays current after every LRS refresh:

```python
# Re-copy edge source and rebuild network after each LRS refresh
arcpy.management.CopyFeatures(
    r"<sde>\SDEADM.TRNLRS_TRN_STREET_VW",          # standalone (authoritative)
    r"<sde>\SDEADM.TRNLRS\TRNLRS_TRN_STREET_VW",   # FD copy (used by ND)
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
| Standalone edge source | `SDEADM.TRNLRS_TRN_STREET_VW` |
| XML template | `data/network_template.xml` |
| Old network dataset | `SDEADM.TRN_street_network` (in `TRN_streets_routes`) |
