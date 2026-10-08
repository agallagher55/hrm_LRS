# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Start here: read [`handoff.md`](handoff.md)** for the current status, what is waiting on whom, and the
next steps. Keep it up to date: when status changes or you finish a piece of work, update it before
ending the session. The detailed history is in `network_dataset/docs/network_build_status.md`.

## Python Files
- Use pep8 styling
- Write prose, comments and docs without em dashes and without Oxford commas.
- Scripts take no command line arguments. Put every setting in global variables (constants) at the top of the script.

## Environment
- ArcGIS Pro 3.3.5 for the original build. Network dataset work since 2026-09-01 is on **3.5.8**, and the
  Prod script host was **3.3.7** per Ryan's 2026-08-31 email to Esri. Verify the version before relying on
  any version-specific behaviour below.
- Enterprise geodatabase: QA 11.5.0. Prod was 11.3.0 until the upgrade to 11.5, which Alex confirmed
  finished on 2026-09-29 (planned for 2026-09-26/27; exact completion date and patch level not recorded).
  Anything dated before that describing Prod as 11.3.0 is history.

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
  FC in place (e.g. the old→new turn FC swap in `network_dataset/scripts/05_rebuild_traffic_turns.py`).
- **`arcpy.management.TruncateTable`** → `ERROR 001395: Operation not supported on a feature
  class in a controller dataset.` Hit when re-syncing the edge source FC
  (`network_dataset/scripts/04_sync_and_rebuild_network.py`). Fix: use `arcpy.management.DeleteRows` instead
  — it's a normal edit operation and IS supported on controller-dataset members (slower than
  `TruncateTable` on large tables, but doesn't require deleting the network dataset).

### Client / geodatabase version mismatch can show phantom gaps and overlaps (unconfirmed)
Reported 2026-09-23 by Melanie Parker: a newer Pro client (3.5.8) against an older enterprise
geodatabase (Prod 11.3.0, before the 11.5 upgrade that finished by 2026-09-29) shows gaps, overlaps and differences in
LRS data that are not really there. Not verified, and it does not explain the same errors seen in
QA (already 11.5.0), so do not assume it accounts for any given batch of "source geometry errors".
Before fixing a suspected geometry error, check it from a client and geodatabase pair that match.
Prod is now on 11.5, so re-baseline the 57 new issues from a matching pair to test the theory.

### A wholesale QA-from-Prod refresh erases the QA network
Prod has no `SDEADM.TRNLRS_network` feature dataset and no network dataset. Any database-level
refresh of QA from Prod therefore removes QA's network dataset, remapped `TRNLRS_traffic_turn`,
the turn backup that `qa_refresh/01_backup_and_baseline.py` writes into that feature dataset, and
the SQL grants. Export the network sources outside SDE first, and expect to redo the `qa_refresh`
procedure from the network build onward.

### VBScript network evaluators lock the network dataset read-only (ArcGIS Pro 3.4+)
A network dataset whose `Length`/other evaluators are still VBScript Field/Element Script
(the legacy authoring language) opens in Properties as **permanently read-only** starting in
Pro 3.4 — not just the evaluators, everything — with no in-place fix, because the only
documented remediation (convert to Python via Properties → Travel Attributes) requires the
exact dialog that's locked. Confirmed against Esri KB 000034955 / FAQ 000034321; ruled out
lock/session state, Pro client version, and network dataset schema version as causes before
landing on this (see `network_dataset/docs/network_dataset_script_review.md` §F2 for the full diagnosis). Fix:
rebuild the network dataset from scratch with Python evaluators (interactive New Network
Dataset wizard, not `CreateNetworkDatasetFromTemplate` against an old VBScript-bearing
template — that reproduces `ERROR 030386`), then re-export the template via
`CreateTemplateFromNetworkDataset`.

### Deployed copies on the T: drive drift from the repo
Two stale files on the T: drive each cost time on 2026-09-29: `data\network_template.xml` (a July
VBScript copy, which made script 03 fail with `ERROR 030386`) and `scripts\run_full_network_rebuild.py`
(an older `main()` with no arguments, which made step 06 raise a `TypeError`). Neither changed any
data. Before a run, compare file sizes or hashes of the T: scripts and template with the repo.
Script 03 now refuses to continue if its template contains VBScript (`Select Case`).

### Recreating the network dataset by hand (`ERROR 030386` workaround) — two more gotchas
**Fallback only, as of 2026-09-29.** The committed template is Python and creates and builds by
script (`qa_refresh` step 03 and the step 06 orchestrator), so the interactive wizard is needed
only if that template is ever rejected again. Confirmed 2026-09-18, on top of the fix above:

- **The Elevation Model parameter defaults to "Elevation fields", not "None"**, whether
  you use the interactive New Network Dataset wizard or the `arcpy.na.CreateNetworkDataset`
  GP tool directly. Easy to miss since nothing in the dialog calls out the default — set
  it to **None** explicitly, or the network builds elevation-aware connectivity it isn't
  meant to have.
- **The interactive recovery does not include configuring Directions**, and it's easy to
  walk away thinking the rebuild is complete without it — the network builds and solves
  fine either way, so nothing surfaces an error. Confirmed missed entirely on 2026-09-18:
  the resulting `CreateTemplateFromNetworkDataset` export came out with no
  `<NetworkDirections>` element at all (merged back in from the 2026-09-03 export on 2026-09-29), a real gap not caught until a later `/code-review`
  pass. Set it explicitly on the Directions tab: Base Name → `STR_NAME`, Suffix Type →
  `STR_TYPE`, Full Name → `FULL_NAME`.
- **`CreateTemplateFromNetworkDataset` needs a Network Dataset Layer, not a raw catalog
  path.** Passing the path string directly can fail with `ERROR 030033: Parameter does
  not contain a network dataset data element.` Make a layer first:

  ```python
  arcpy.na.MakeNetworkDatasetLayer(network_dataset_path, "nd_lyr")
  arcpy.na.CreateTemplateFromNetworkDataset("nd_lyr", output_template_xml)
  ```

  Two more things about the exported template, once you have it:
  - Its internal `<Name>`/`<CatalogPath>`/`<LogicalNetworkName>` fields are not reliably
    the live object's actual catalog name — one export named the network dataset
    `TRNLRS_network` instead of the real `TRNLRS_street_network`, even though the `DSID`
    inside the file matched the live object exactly (cause unconfirmed). Since
    `CreateNetworkDatasetFromTemplate` takes its **output name from inside the template
    file**, always check and correct these fields before committing or reusing an
    exported template, or a future automated rebuild creates a wrongly-named network
    dataset.
  - The scripted evaluators' `NetworkEvaluatorCLSID`
    (`{68055FC4-37D5-4BD0-81A5-CD177A29759C}`) is **not, by itself, a reliable signal of
    VBScript vs. Python.** A genuinely Python-evaluator template exported from a live,
    solve-tested network still carries this identical CLSID, same as the broken
    VBScript-era template does. Don't diagnose `ERROR 030386` by grepping for this CLSID
    alone — the only real test is whether `CreateNetworkDatasetFromTemplate` actually
    gets past evaluator validation with the template in question.

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

### Editing a Field Script evaluator's Code Block requires Force Full Build — otherwise the change silently does nothing
**This is the confirmed root cause behind a full day (2026-09-01/02) of `OneWay` appearing broken.**
`Build Network` on an *existing* network dataset stores precomputed per-edge attribute values in
internal weight tables (e.g. `N_<id>_EDGEWEIGHT` — see `network_dataset_sql_permissions.md`).
When only an evaluator's *definition* changes (the script text), not the underlying source
data, an incremental (non-forced) `Build Network` can leave those precomputed values stale —
the evaluator now reads correctly, but the solver keeps using old cached values as if nothing
changed. This fails **completely silently**: no build error, no warning, a clean "Build
succeeded" message, and the restriction just never fires. Diagnosed by hardcoding a Field
Script evaluator to unconditionally `return True` (should prohibit every edge in that
direction, network-wide) and observing zero effect on any solve — then re-running with **Force
Full Build** checked, which immediately made the same hardcoded evaluator produce
`ERROR 030212: Solve did not find a solution` as expected.

**Whenever you edit a Field Script (or any) evaluator's script content on an existing network
dataset, check "Force Full Build" before running Build Network, or the edit will not take
effect and there will be no indication anything is wrong.** A full rebuild of a
network this size (~37,700 edges) normally completes in under two minutes — if a forced build
runs far longer than that, it is very likely blocked on a lock from another session, not doing
legitimate work (see "Long-running Build Network = check for a blocking SQL session" below).

Separately, also confirmed while chasing this: `!FIELD!` token substitution works fine when the
whole evaluator is written as a function in the **Code Block** and called from the **Value**
line (`Value = oneway_restricted(!STR_DIR!)`), which is the standard ArcGIS Calculate-Field-style
convention and the form to use by default:

```python
# Code Block
def oneway_restricted(str_dir):
    return (str_dir or "").upper() in ("N", "FDTO", "T")

# Value
oneway_restricted(!STR_DIR!)
```

Whether `!STR_DIR!` written inline directly inside the Code Block (without the function/Value
split) *also* works once Force Full Build is used was never isolated — both changes were made
together. Use the function/Value form regardless; it's the documented pattern. Note it differs
from the legacy VBScript convention, where `[FIELD]` bracket tokens are substituted directly
inside the PreLogic block — a literal VBScript→Python transcription will look right and can
still behave wrong. **Always verify a restriction evaluator with a real two-direction solve
after a Force Full Build — never trust a clean build message alone.**

### Long-running Build Network = check for a blocking SQL session, don't just wait
A `Force Full Build` against this network (enterprise geodatabase, SQL Server) should complete
in under two minutes. If it runs for hours, Pro will still show it as "running" with no error —
it does not detect or surface a server-side block on its own, and Task Manager will show the
ArcGIS Pro process near-idle (~1-5% CPU), not churning. Confirmed 2026-09-02/03: a Force Full
Build was silently blocked server-side, ran for 18 hours, and was eventually killed by a DBA
directly on SQL Server (a `blocking session` alert, running an `UPDATE .SDE.GDB_ITEMS ...`
statement under the `SDEADM` login) — Pro's own dialog never reported anything wrong and had to
be cancelled manually client-side afterward, since it was left waiting on a session that no
longer existed. If a build is running far longer than its usual time: check Task Manager CPU
first (near-idle = stuck, not working), then check with whoever administers the SQL Server
instance for a blocking session before assuming it will eventually finish. Note that `Build
Status` in Network Dataset Properties can show a *successful* `Build Time` from earlier in the
same stuck session — the core rebuild may have already committed successfully in normal time,
with only a trailing client-side step left hanging, so check Properties before assuming a long
hang means total failure.

## Two networks: `HRM_NETWORK`
There are two networks built from the same LRS streets: `DISTANCE` (`TRNLRS_street_network`, the
default) and `HRFE` (`TRNLRS_street_network_HRFE` in its own feature dataset
`SDEADM.TRNLRS_network_HRFE`). `network_dataset/scripts/network_definitions.py` holds every name that
differs, and the `HRM_NETWORK` environment variable selects one for scripts 03, 05, the verifier and
`qa_refresh`. Unset means `DISTANCE`, and every path and name is unchanged from before, though DISTANCE's
exclusions did gain the transit access roads. The Prod edge sync (`04`) ignores the variable on purpose.
A mistyped variable name (for example `set HRM_NETWORK = HRFE`, whose spaces become part of the name)
stops the run instead of quietly meaning DISTANCE, and the delete and swap steps (`qa_refresh` 02 and 06)
also need `NETWORK_TO_DELETE` or `NETWORK_TO_BUILD` set in the script to match the run. Exclusions are per network (`network_exclusions.py` profiles `GENERAL` and
`HRFE`). SDE needs feature class names to be unique across the geodatabase, hence the `_HRFE` suffix.
The HRFE build is written but has not been run; see `network_dataset/docs/hrfe_network_runbook.md`.

## Project Purpose

This repository holds all data, scripts, and documentation for the **Halifax Regional Municipality (HRM) Linear Referencing System (LRS)** — a system for locating assets and events along road/route networks using route identifiers and measure values (e.g., kilometre points) rather than X/Y coordinates.

## Repository Structure

```
hrm_LRS/
├── scripts/                 # LRS refresh pipeline (LRS_updates.py)
└── network_dataset/         # Creating and maintaining the LRS network dataset
    ├── scripts/              # Build, sync, and turn-rebuild scripts
    │   └── qa_refresh/        # Ordered QA network-refresh workflow (see its README.md)
    ├── data/                 # Extracted config, XML template, schema diffs
    ├── docs/                 # Migration plan, build status, runbooks
    └── intermediate_results/ # Diagnostic CSVs from the turn rebuild
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
| `STR_DIR` | Text(4) | One-way direction; drives the `OneWay` network restriction evaluator. Known codes (recovered 2026-09-01 from the live network's evaluator, see below): `FDTO` blocks travel **along** the digitized direction, `FOTD` blocks travel **against** it, `N` and `T` block **both** (fully closed segment). Any other value (including blank) is unrestricted in both directions — the real two-way code in this data is `BOTH`. The domain was enumerated on 2026-09-03 and is complete: `BOTH` 15,812 rows, `FOTD` 2,792, `NULL` 7, `FDTO` 1. `N` and `T` appear in the evaluator but not in the data. **Known data issue (confirmed with HRM's GIS team, 2026-09-03):** at least one edge (Bishop St between Barrington St and Hollis St, `TRNLRS_TRN_STREET` OID 12002) has its line geometry digitized backwards relative to its real-world one-way sign — `STR_DIR='FOTD'` and the evaluator logic are both correct, but because the edge's digitized direction is flipped, "Along"/"Against Digitized" end up mapping to the wrong real-world compass direction for that one edge. Not a network-dataset bug; a source-geometry data-quality item, scope unknown (only this one edge has been checked). |
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

### TRNLRS_traffic_turn (SDE: `SDEADM.TRNLRS_traffic_turn`)

The live prohibited-turn source for the network dataset. **Its OBJECTID does not
correspond to the legacy `SDEADM.TRN_streets_routes\TRN_traffic_turn`'s OBJECTID**,
even though it was originally created by copying that table — it is itself the
product of an earlier turn-remap cycle (`network_dataset/scripts/05_rebuild_traffic_turns.py`),
carrying different `Edge{N}FID` references (and a different `Edge1FCID`) than the
true legacy source. Confirmed 2026-09-18: cross-referencing `TRNLRS_traffic_turn` by
OIDs pulled from a `05_rebuild_traffic_turns.py` skip-reason log gave actively wrong
edge references for 14 of 15 sampled turns — only one matched by coincidence. When
diagnosing turn-remap skip reasons, always query the real `TRN_traffic_turn`
(alongside `TRN_street`, same SDE), never `TRNLRS_traffic_turn`.
