# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Python Files
- Use pep8 styling

## Environment
- ArcGIS Pro 3.3.5

### SQL Server instances
- `ms-gis-sql-q21` → QA
- `ms-gis-sql-p21` → Prod

## arcpy Gotchas

### `arcpy.na.CreateTurnFeatureClass`
On ArcGIS Pro 3.3.5, correct keyword arguments are `out_location` and `out_feature_class_name`
(**not** `out_name` — confirmed against ArcGIS Pro's documented signature
`CreateTurnFeatureClass(out_location, out_feature_class_name, {maximum_edges}, ...)`).
`out_name`, `out_path`/`out_name`, and `out_location`/`out_feature_class` all raise
`TypeError: unexpected keyword argument`.

Also avoid the `in_network_dataset` parameter unless you actually want the output FC
registered as a live source of that network dataset (see "Controller dataset restrictions"
below — it immediately locks the output against `Delete`/`Rename`). To just match an
existing turn FC's schema without that side effect, use `in_template_feature_class` instead:

```python
arcpy.na.CreateTurnFeatureClass(
    out_location=out_path,
    out_feature_class_name=out_name,
    maximum_edges=max(edge_slots),
    in_template_feature_class=EXISTING_TURN_FC,  # schema only, no ND registration
)
```

### Controller dataset restrictions (network dataset member feature classes)
Any feature class that is a registered source of a network dataset (edge, junction, or turn
— defined in the network's XML template / Sources tab) becomes a **controller dataset**
participant. Several arcpy operations are blocked on it while the network dataset exists,
and there is no arcpy call to unregister a single source — the network dataset itself must
be deleted to release the lock, then recreated (`CreateNetworkDatasetFromTemplate` +
`BuildNetwork`) afterward. Two variants hit in this project:

- **`arcpy.management.Delete` / `arcpy.management.Rename`** → `ERROR 001919: <value> cannot
  be deleted because it participates in a controller dataset such as a network dataset,
  utility network, or trace network.` Hit when trying to delete/rename a turn or edge source
  FC in place (e.g. the old→new turn FC swap in `scripts/05_rebuild_traffic_turns.py`).
- **`arcpy.management.TruncateTable`** → `ERROR 001395: Operation not supported on a feature
  class in a controller dataset.` Hit when re-syncing the edge source FC
  (`scripts/04_sync_and_rebuild_network.py`). Fix: use `arcpy.management.DeleteRows` instead
  — it's a normal edit operation and IS supported on controller-dataset members (slower than
  `TruncateTable` on large tables, but doesn't require deleting the network dataset).

### VBScript network evaluators lock the network dataset read-only (ArcGIS Pro 3.4+)
A network dataset whose `Length`/other evaluators are still VBScript Field/Element Script
(the legacy authoring language) opens in Properties as **permanently read-only** starting in
Pro 3.4 — not just the evaluators, everything — with no in-place fix, because the only
documented remediation (convert to Python via Properties → Travel Attributes) requires the
exact dialog that's locked. Confirmed against Esri KB 000034955 / FAQ 000034321; ruled out
lock/session state, Pro client version, and network dataset schema version as causes before
landing on this (see `docs/network_dataset_script_review.md` §F2 for the full diagnosis). Fix:
rebuild the network dataset from scratch with Python evaluators (interactive New Network
Dataset wizard, not `CreateNetworkDatasetFromTemplate` against an old VBScript-bearing
template — that reproduces `ERROR 030386`), then re-export the template via
`CreateTemplateFromNetworkDataset`.

### Restriction attributes do nothing unless the Travel Mode enables them
Defining a restriction attribute (e.g. `OneWay`, `TrafficTurn`) on the network dataset's
Travel Attributes tab does not mean any given solve honors it. Enforcement is controlled
per **Travel Mode** — Route/Service Area layer → Travel Mode → Edit → Restrictions tab — and
a freshly created Route layer's default travel mode does not automatically pick up custom
restrictions. A solve will silently route straight through a real prohibited turn or the
wrong way down a one-way street, with no error, if the restriction isn't checked there.
Confirmed 2026-09-01 against QA: a known-prohibited turn (`QUINPOOL RD -> ROBIE ST`) was
solved straight through until `TrafficTurn`/`OneWay` were checked in the travel mode, after
which the same stops correctly produced a detour.

### Python Field Script evaluators: `!FIELD!` only substitutes in Value, not the Code Block
In the Field Script Evaluator Properties dialog, the **Value** line is where `!FIELD!` tokens
get substituted; the **Code Block** is a plain Python function body that must *receive* fields
as parameters. Writing `!STR_DIR!` inline inside the Code Block does not work — and worse, it
fails **silently**: the network builds without error and the evaluator simply never enforces
anything. Confirmed 2026-09-01 (an eastbound solve on a `FOTD`-coded one-way segment ran
straight through). Correct shape:

```python
# Code Block
def oneway_restricted(str_dir):
    return (str_dir or "").upper() in ("N", "FDTO", "T")

# Value
oneway_restricted(!STR_DIR!)
```

Note this differs from the legacy VBScript convention, where `[FIELD]` bracket tokens *are*
substituted inside the PreLogic block — so a literal VBScript→Python transcription of an
existing evaluator will look right and behave wrong. Always verify a restriction evaluator
with a real two-direction solve rather than trusting a clean build.

## Project Purpose

This repository holds all data, scripts, and documentation for the **Halifax Regional Municipality (HRM) Linear Referencing System (LRS)** — a system for locating assets and events along road/route networks using route identifiers and measure values (e.g., kilometre points) rather than X/Y coordinates.

## Repository Structure

```
hrm_LRS/
├── data/       # Source and processed LRS data
├── scripts/    # Processing, validation, and export scripts
├── docs/       # Technical documentation and specifications
└── tests/      # Data validation and regression tests
```

> This structure is the intended layout. Populate this file further as scripts, data formats, and tooling are established.

## Key Feature Classes

### TRNLRS_TRN_STREET_VW (SDE: `SDEADM.TRNLRS_TRN_STREET_VW`)

The primary LRS street feature class used as the edge source for the network dataset. Despite the `_VW` suffix it is a **real SDE feature class**, not a database view — the name reflects its derived nature.

**How it is created (`LRS_updates.py`):**

```
LRSN_Route + 7 event tables
    (E_StreetDirection, E_StreetClass, E_AddressRange, E_PSAB,
     E_StreetOwnership, E_StreetStatus, E_WinterMaintenance)
        │
        ▼  arcpy.locref.OverlayEvents
TRNLRS_segmented_street_events       ← intermediate dynamic segmentation FC
        │
        ▼  SQL query layer (joins E_AddressRange for ADDDATE/MODDATE)
        │  filter: TO_DATE IS NULL (active streets only)
        │
        ▼  TruncateTable → Append
TRNLRS_TRN_STREET_VW                 ← this feature class
```

The feature class is **truncated and repopulated on every LRS refresh run**, so the network dataset must be rebuilt after each update.

**Key fields:**

| Field | Type | Notes |
|---|---|---|
| `FDMID` | Long | Primary street identifier; links to address range and other event tables |
| `ROUTE_ID` | Text(255) | LRS route identifier |
| `STR_NAME` / `STR_TYPE` / `FULL_NAME` | Text | Street name components; `FULL_NAME` sourced from `ROUTENAME` |
| `STR_DIR` | Text(4) | One-way direction; drives the `OneWay` network restriction evaluator. Known codes (recovered 2026-09-01 from the live network's evaluator, see below): `FDTO` blocks travel **along** the digitized direction, `FOTD` blocks travel **against** it, `N` and `T` block **both** (fully closed segment). Any other value (including blank) is unrestricted in both directions. The full domain has never been enumerated — these four are simply the values the evaluator tests for. |
| `STR_STATUS` | Text(4) | Domain `SNF_street_status` |
| `ST_CLASS` | Text(40) | Street class; domain `SNF_pst_class`; drives hierarchy evaluator |
| `FROM_LEFT/TO_LEFT/FROM_RIGHT/TO_RIGHT` | Long | Address ranges for geocoding |
| `GSA_LEFT` / `GSA_RIGHT` | Text(40) | Geographic service areas |
| `MAINTENANCE` | Text(8) | Winter maintenance; domain `SNF_maintenance`; sourced from `E_WinterMaintenance` |
| `ADDDATE` / `MODDATE` | Date | Min/max dates joined from `E_AddressRange` per FDMID |
| `STR_CODE_L` / `STR_CODE_R` | Long | Left/right street codes |
| `ASSETID` | Text(50) | Asset identifier |

**Internal column renames** (source column → output field name):
- `COMMENT__2` → `STR_REM`
- `FLAG` → `FLAGS`
- `ROUTENAME` → `FULL_NAME`
