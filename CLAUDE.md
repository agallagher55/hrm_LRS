# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Python Files
- Use pep8 styling

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
| `STR_DIR` | Text(4) | One-way direction; drives network restriction evaluator |
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
