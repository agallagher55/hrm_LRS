# Network Dataset Build Status & Action Plan
## TRNLRS_street_network

**Goal:** Replace the legacy `TRN_street_network` with a new LRS-based network dataset
(`TRNLRS_street_network`) whose edge source is `TRNLRS_TRN_STREET_VW`.

For full technical details see [`network_dataset_migration_plan.md`](network_dataset_migration_plan.md).

## Status at the end of 2026-09-29

- **QA's network was recreated and built by script** through the `qa_refresh` procedure, from
  Prod data re-extracted after the 11.5 upgrade: Edges 37,674, Junctions 16,187, **Turns 1,184**
  (the same five turns rejected as on 2026-09-18). Run details are in the table below.
- **Grants applied** (`N_3`, `ND_40986`; the source tables already had theirs). A non-admin login
  can add the network to a map. Recorded in `network_dataset_sql_permissions.md`.
- **Handed to Robbie Evans to retest.** Smoke tests, a check that the gaps are actually fixed,
  and Directions on the live network are still open.
- **The committed template now includes Directions** (merged from the 2026-09-03 export, not yet
  proven by a create). Test it with `qa_refresh/test_template_create.py`.
- **Review changes, later on 2026-09-29:** step 03 is now copy-only (`03_copy_sources.py`; the network is created
  and built once, in step 06); step 01 exports the sources to a file geodatabase outside SDE; safety checks in
  steps 00, 02 and 06; the `LRS_updates.py` edge sync delegates to `04_sync_and_rebuild_network.py`; diagnostics
  moved to `scripts/diagnostics/`. None of it has run against a live database yet.
- A wholesale QA-from-Prod database refresh was **not** done, so QA's legacy junction and turn
  classes are older than the Prod edge copy.

## Update 2026-09-29 (from the 2026-09-23 and 2026-09-24 meetings, then the QA run)

Source: [`meetings/2026-09-23_and_2026-09-24_check_in_notes.md`](meetings/2026-09-23_and_2026-09-24_check_in_notes.md).
The paragraphs below were written during the day, in order; the run table further down is the
authoritative record. **Confirmed by Alex
on 2026-09-29:** the Prod geodatabase upgrade to 11.5 **finished**; the QA network was **backed up**
and the QA-refresh heads-up was **sent** to QA users (later the same day); QA has **not** yet been
refreshed from Prod as far as this repository knows; the network-creation overview has **not** gone
to Ryan; the next check-in is 2026-09-30. Where the backup was written (path, counts, whether it
includes the grants snapshot committed in `network_dataset_sql_permissions.md`) is **not recorded**
here; add it below when known. (The backup was taken; the refresh itself was replaced by the
scripted network rebuild described next.)

**Later on 2026-09-29: QA network recreated from the template.** The QA refresh was deliberately
skipped (Alex is content with QA's freshness; the goal is to recreate the network after the Prod
11.5 upgrade). `qa_refresh` steps 00 to 03 ran. The first step 03 failed with `ERROR 030386`
because the T: copy of `network_template.xml` was the stale 2026-07-14 VBScript file. After
deploying the committed template, step 03 created and built `TRNLRS_street_network` with no
errors: **Edges 37,674, Junctions 16,187, Turns 0** (Turns 0 is expected until the remap). The
edge copy holds 18,583 of Prod's 18,644 features, with 61 WA streets excluded by
`network_exclusions.py`. Still to do: steps 04 to 07, grants under the new registration IDs
(object class IDs 40578 to 40581), smoke tests, Directions, template re-export. Junctions and
turns were copied from QA's legacy classes, which are older than the Prod edge copy. **Confirmed by
Alex later on 2026-09-29: Prod's `TRNLRS_TRN_STREET_VW` was re-loaded (the LRS re-extract) after
the upgrade to 11.5**, so this edge copy is post-upgrade data and the 2026-09-24 concern that the
network would inherit the pre-upgrade overhangs does not apply. The exact re-extract date and time
were not recorded. A forced manual rebuild then gave the same counts (Edges 37,674, Junctions
16,187, Turns 0, built 08:30:04). Its build-errors file held only the two expected message types:
1,238 `Cannot find edge element corresponding to turn identifier` (the raw legacy turns, fixed by
the remap) and 1,133 `Standalone user-defined junction is detected`. Whether the geometry gaps are
actually gone is still to be proven by checking Robbie's flagged locations after the final build.

**Full `qa_refresh` run completed 2026-09-29 (Alex, from the run logs).**

| Step | Result |
|---|---|
| 03, first attempt | Edge copy 18,583 of Prod's 18,644 features (61 WA streets excluded). `ERROR 030386` because the T: `network_template.xml` was the stale 2026-07-14 VBScript file. |
| 03, after deploying the committed template | Created in about 13 s, built in about 9 s, 0 errors. Edges 37,674, Junctions 16,187, Turns 0. |
| Manual forced rebuild | Same counts (built 08:30:04). Errors file: 1,238 `Cannot find edge element` (raw turns) plus 1,133 standalone-junction warnings, nothing else. |
| 04 remap | 1,238 in, **1,189 written, 49 skipped (4.0%)**: 33 `missing_old_geometry`, 11 `no_shared_endpoint`, 5 `unresolved_edge`. Edge1End agreement 1,190/1,194 (99.7%). Edge DSID 40578. Same figures as 2026-09-18. |
| 05 verify staging | All 10 checks passed. Edge1End N 138, Y 1,051. Every turn has exactly two edges (2,378 references). |
| Spatial review | Partly reported: staging OID 61 (the remap of raw OID 66, same 4.302219 m line) joins edge 9727 ROBIE ST (Shirley to Cogswell) to edge 9770 ROBIE ST (Cogswell to Pepperell), both `FOTD`, at the Cogswell hub. The step 01 backup `TRNLRS_traffic_turn_bak_20260928_230127` holds 1,189 records, equal to the 2026-09-18 remap, so no hand-authored turns existed (the Cogswell ramp question is closed by count; an identical-geometry comparison was suggested, not reported). Not yet reported: the 49-skip diff against 2026-09-18, attribute carryover, ETA turns, and the `Edge2FID = 9770` cross-check. |
| 06 swap and final build | First attempt failed instantly with `TypeError: main() takes 0 positional arguments` because the T: `run_full_network_rebuild.py` was stale; nothing had changed. After copying the repo version: old network and raw turn class deleted, staging renamed to `TRNLRS_traffic_turn`, network created and built from the template (built 08:55:04), 0 errors, 1 warning. Post-build: 18,583 edges, 15,424 user-defined junctions, 1,189 turn features. |
| Properties after 06 | **Edges 37,674, Junctions 16,187, Turns 1,184.** |
| Build errors after 06 (`BuildErrors_5cfc4bc3-6637-45c2-8a9a-7866b8bbfc00.txt`) | 1,133 standalone-junction warnings and **5 `Cannot find at junction`** on turn OIDs 686, 746, 747, 829, 830, the same five as the 2026-09-18 build and the Esri case. |
| 07 verify live turns | All 10 checks passed on 1,189 records (08:58). |

Still open after this run: SQL grants were applied later on 2026-09-29 (`N_3` and `ND_40986`; the
source tables already had theirs, see `network_dataset_sql_permissions.md`), with the audit re-run
and an OS-auth add-to-map still to confirm; route smoke tests (one-way both directions, prohibited turn on and off), a check that
Robbie's flagged gap locations are actually fixed, Directions (missing from the network and the
template), a re-exported template with corrected names, and syncing the T: scripts folder with the
repo (two files were stale: `network_template.xml` and `run_full_network_rebuild.py`). Junctions
and turns were copied from QA's legacy classes, which were not refreshed from Prod.

- **Acceptance testing restarted and paused again.** Robbie tested the distance network after
  the LRS corrections and got errors back. Melanie and Ryan are looking at **57 new issues** they
  cannot trace (islands such as McNabs, a newly added street that had been snapped correctly, an
  overshoot, overlaps visible in the address range event, no revision dates). They are in Prod,
  not caused by testing in QA. The earlier ~500 from 2026-09-11 is not the same list, and Ryan's
  "3000" almost certainly refers to the July overlap/gap cleanup table, not to the 500.
- **A second explanation for at least some errors: a Pro / geodatabase version mismatch.**
  Robbie's ArcGIS Pro is now 3.5.8 while the Prod enterprise geodatabase is still 11.3.0. Melanie
  has seen gaps and overlaps appear in that combination and expects them to clear when Prod is
  upgraded to 11.5, planned for the weekend of **2026-09-26/27**. This is unproven. Robbie saw
  the same errors in QA, whose geodatabase was already 11.5.0, and that is not explained by the
  mismatch theory. The 2026-09-11 conclusion below ("upstream LRS defects, not network defects")
  therefore stands for the network dataset, but the **cause** of the geometry errors is now
  open: real source defects, a version artefact, or both.
- **The Pro upgrade question is answered.** Jillian asked on 2026-09-09 whether the Pro upgrade
  proceeds while the Esri case is open. It did: Robbie is already on 3.5.8, and the Prod
  geodatabase upgrade was scheduled regardless. (Whether LRS editors were held back was not
  discussed.)
- **Esri case #04248942.** On 2026-09-22 Esri said they found no workaround and may file a
  data-specific defect report covering the three scenarios. They asked to share HRM's file
  geodatabase with Esri Inc.; the team agreed verbally, and Ryan replies. Alex is sending Ryan
  the network-creation overview (written up in `junction_network_workflow_esri_case.html`).
- **There are two planned networks, not one.** The current `TRNLRS_street_network` is the
  **distance network**. A second **HRFE network** will add speed and additional inclusions and
  exclusions (2026-09-09 and 2026-09-24). The "Travel time cost attribute" section below still
  frames travel time as an addition to this network; whether it becomes a second network dataset
  is undecided. Nobody has identified the users of the distance network or how to announce it.
- **Planned QA refresh, and a risk nobody raised.** Alex will refresh all of QA from Prod over
  the upgrade weekend, after notifying QA users. Prod has **no** `SDEADM.TRNLRS_network` feature
  dataset and no network dataset, so a wholesale refresh would remove QA's network dataset, its
  remapped `TRNLRS_traffic_turn`, the turn backup that `qa_refresh/01_backup_and_baseline.py`
  writes inside that feature dataset, and all SQL grants on it. It would also discard any
  hand-authored turns (see the Cogswell ramp item in the runbook). After such a refresh the
  network must be rebuilt through the full `qa_refresh` procedure (about half a day) before
  Robbie can retest. **Depends on the refresh method** (database restore versus copying data
  in); Alex knows which was used.
- **Island segments and WA (water access) streets** are to be filtered out of the network.
  Melanie will supply the island filter. Robbie says islands cannot route and are caught in QC
  anyway; on WA streets, he has asked for their removal repeatedly (confirmed by Alex on
  2026-09-29 that "the WAs" in the 2026-09-23 transcript means WA streets). This revisits the
  June position that WA needed care because civic addresses are coded to them. The older plan in
  `network_dataset_migration_plan.md` says to filter in the SQL that populates
  `TRNLRS_TRN_STREET_VW`; that would remove WA from an org-wide product and any geocoding built
  on it, so filtering only the network's edge copy is safer. **Implemented 2026-09-29** in
  `scripts/network_exclusions.py`, called by scripts 03 and 04: `STR_TYPE = 'WA'` is excluded
  now; the island FDMID list is empty until Melanie supplies it. Not yet run against any
  environment. Consequences: the edge copy has fewer rows than `TRNLRS_TRN_STREET_VW` by design;
  turns on excluded edges are skipped by the remap; `LRS_updates.py`'s
  `sync_network_edge_source()` does **not** apply the exclusions.
- **Correction to earlier status text.** The 2026-09-18 QA rebuild superseded the 2026-09-01
  numbers still quoted in older sections: **Edges 37,788, Junctions 16,185, Turns 1,184** (not
  1,180), **5** turns rejected at build (not 9), SQL registration `N_3` / **`ND_40192`** (not
  `ND_40171`). Also, the live QA network has **no Directions configuration** (the 2026-09-18
  interactive rebuild skipped it) and `network_dataset/data/network_template.xml` has no
  `<NetworkDirections>` element. Both were open on 2026-09-18. **Template half fixed 2026-09-29:** the
  `<NetworkDirections>` block and the edge source's `<NetworkSourceDirections>` (`STR_NAME`,
  `STR_TYPE`, `FULL_NAME`) were merged in from the 2026-09-03 export, unchanged; the merge is not
  yet proven by a scripted create. The **live QA network still has no Directions**.
- **Correction to Step 5 below, fixed 2026-09-29.** `sync_network_edge_source()` in `LRS_updates.py`
  used to call `append_feature()`, which calls `TruncateTable` and would have failed with
  `ERROR 001395` against the controller-dataset edge source (and would have reloaded WA streets,
  bypassing the exclusions). It now calls `04_sync_and_rebuild_network.sync_and_rebuild()`, which
  uses `DeleteRows` and the exclusions. Tested only with a stub (no arcpy); the first real run is
  the test. The sync still leaves every turn's edge references stale.

Recommended next steps are in
[`street_network_meeting_overview.md`](street_network_meeting_overview.md#remaining-work-in-recommended-order).

---

**Where this stands as of 2026-09-15:** QA's network dataset is built, editable, and both
restriction types are proven with real solves. Independent acceptance testing by Robbie Evans
started 2026-09-09 and **stopped on 2026-09-11 after roughly 500 source-geometry errors**
(segments extended past intersections) were found in the LRS data. Those are upstream defects,
not network dataset defects, but they block sign-off. Testing resumes after the LRS
corrections land and QA is refreshed. Two documents were added for the 2026-09-16 check-in:

| Document | Answers | Shareable link |
|---|---|---|
| [`junction_network_workflow_esri_case.html`](junction_network_workflow_esri_case.html) | Ryan Lowe / Esri Case #04248942: the high-level workflow for creating the junction network, every error encountered, and a draft reply | [Junction Network Workflow](https://claude.ai/artifact/NP2uxjdLuuRJr8uCzNJwgf) |
| [`qa_network_refresh_runbook.html`](qa_network_refresh_runbook.html) | Robbie Evans / Jillian Landry: how to refresh QA, and why it is not a simple truncate-and-load | [QA Network Refresh](https://claude.ai/artifact/T5J6zb7B8UUqa61Ns93v4P) |

The shareable links are the same documents published as standalone web pages for people who
do not have this repository. The repository copies are the source of truth; if a document
changes here, the published page has to be republished to match.

**Feature dataset separation (in progress, 2026-07-14):** the network source FCs and
`TRNLRS_street_network` are being moved out of `SDEADM.TRNLRS` (the LRS feature
dataset) into a dedicated `SDEADM.TRNLRS_network` feature dataset.
`SDEADM.TRNLRS_network` now has `TRNLRS_street_network` built in **both Dev and
QA** -- prod is still on the original layout described throughout most of this
document (FCs living inside `SDEADM.TRNLRS`). In both Dev and QA, script 03 was
run before `network_dataset/scripts/06_migrate_network_fd.py` (which was meant to move the
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
  re-remapped via `network_dataset/scripts/05_rebuild_traffic_turns.py` and swapped in
  (delete network dataset → swap turn FCs → re-run script 03 to recreate and
  rebuild) -- see Step 3 below.
- The original three FCs are still sitting untouched in `SDEADM.TRNLRS` in
  **both** Dev and QA -- `network_dataset/scripts/06_migrate_network_fd.py` (the intended
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
| 1 | Extract old network configuration | ✅ Complete — but `network_dataset/data/network_template.xml` is **stale**, see 2026-09-01 update |
| 2 | Schema comparison (old vs. new edge source) | ✅ Complete |
| 3 | Edit XML template | ✅ Complete (elevation fields cleared — see below) |
| 4 | Create & build new network dataset | ✅ **QA rebuilt from scratch 2026-09-01** (interactive wizard, Python evaluators). Dev still on its original 2026-06-26 build — VBScript, permanently read-only, not rebuilt. Prod: nothing built. |
| 5 | Validation | 🔄 Properties ✅; service area ✅; **turn-restriction solve ✅ (2026-09-01)**; **one-way solve ✅ (2026-09-02/03, after a real multi-day debugging saga — see below)**; route comparison / address-range pending. **Robbie Evans's expert acceptance testing is PAUSED (2026-09-11)**: ~500 source-geometry errors found in the first minutes; QA must be refreshed after the LRS fixes land before he can retest. |
| 5a | Traffic turn rebuild | ✅ **Re-verified 2026-09-01** — 1,189 turns written, 99.7% Edge1End agreement, all 10 verifier checks clean, 5 spatial spot checks correct, **1,180 built as live turn elements** (9 rejected at build, see the 2026-09-01 update). **Superseded by the 2026-09-18 rebuild: 1,184 live turns, 5 rejected** (3 real sub-metre gaps, 2 exact 0.0000 m coincidences on one edge, 18393). **Repeated 2026-09-29: 1,189 written, 1,184 live, the same 5 rejected** (staging turn OIDs 686, 746, 747, 829, 830). |

### Update 2026-09-01 — QA network dataset rebuilt from scratch

QA's `TRNLRS_street_network` was **deleted and rebuilt from scratch** on 2026-09-01. This was
not a routine rebuild — the delete happened as part of the normal turn-FC swap, and then
recreating it from `network_dataset/data/network_template.xml` proved **impossible** at the time (superseded: the
re-exported Python template creates and builds by script since 2026-09-29): `ERROR 030386`, because
that template's `Length`/`OneWay` evaluators are VBScript, which ArcGIS Pro 3.5 refuses to
build from. The documented fix (convert evaluators to Python via Properties) is itself blocked,
because a network dataset carrying VBScript evaluators opens **permanently read-only** in Pro
3.4+ by design. Full diagnosis, including the four hypotheses tested and ruled out:
[`network_dataset_script_review.md` §F2](network_dataset_script_review.md#f2-error-030386--vbscript-evaluators-make-the-network-dataset-permanently-read-only-qas-nd-must-be-rebuilt-from-scratch-not-from-this-template-confirmed-2026-09-01).

What this means for the state of each environment:

| Environment | Network dataset | Evaluator language | Editable? |
|---|---|---|---|
| **QA** | Rebuilt 2026-09-01 and 2026-09-18, and again 2026-09-29 from the template by script (Edges 37,674, Junctions 16,187, Turns 1,184; grants re-applied and non-admin add-to-map confirmed). **No Directions configured** on the live network; the committed template now has them. | **Python** | ✅ Yes |
| **Dev** | Original 2026-06-26 build, still functional for solves | VBScript | ❌ **Permanently read-only.** Cannot be edited or rebuilt. Will need the same from-scratch rebuild treatment. |
| **Prod** | Not built | n/a | n/a |

**`network_dataset/data/network_template.xml` is stale and must not be trusted.** Beyond the VBScript problem,
it was found to be missing logic that the live networks actually had: its `OneWay` evaluator is
a hardcoded no-op (`restricted = False`, never reads `STR_DIR`), while Dev's *live* network
carries a real `STR_DIR`-driven `Select Case`. The template was evidently captured in Phase 1
before someone fixed `OneWay` directly in Pro's Properties dialog, and was never re-exported
afterward. The real logic was recovered on 2026-09-01 by running
`CreateTemplateFromNetworkDataset` against Dev (which succeeded on a Pro 3.5.8 machine despite
Esri's KB claiming that operation fails on VBScript-bearing networks — a documented inaccuracy
worth knowing). See [Step 6](#step-6--rebuild-and-re-export-the-network-template-2026-09-01).

**2026-09-16 correction — `TRNLRS_TRN_STREET_VW` is not prod-only.** Every doc and script in
this repository stated flatly that this standalone FC "only exists in prod." That was wrong:
Pro Catalog against `qa_RW_sdeadm.sde` shows a live `SDEADM.TRNLRS_TRN_STREET_VW` in QA as well
(caught while reviewing the QA refresh runbook, whose central answer partly rested on this
claim). Alex confirms it is created by `LRS_updates.py` run against QA.

What is and isn't known:
- **Confirmed:** the FC exists in QA. Its Prod counterpart remains the one every tracked
  script (03, 04, `sync_network_edge_source()`) is hardcoded to read from, regardless of which
  environment they build into -- so this does not change how the network dataset gets built.
- **Confirmed (Alex, 2026-09-16): QA is a one-to-one mirror of prod, just without scheduled
  updates.** QA is meant to be a like-for-like environment to test changes against before they
  reach prod -- it isn't independent QA-only data. `LRS_updates.py` runs against it manually
  (or on request), not on a fixed cadence, which is why its `TRNLRS_TRN_STREET_VW` can be
  arbitrarily stale relative to prod's at any given moment: it reflects whenever someone last
  ran the script there, not the current state. This confirms (rather than just motivates)
  every script's decision to always read Prod's copy specifically -- QA's own copy isn't a
  usable substitute, since its currency isn't guaranteed by anything.
- **Still not confirmed:** whether anything besides the network build (another script, a map
  service, ad-hoc QA work) currently reads QA's copy of `TRNLRS_TRN_STREET_VW` directly.
- **Practical risk:** anyone doing the QA rebuild by hand in Pro Catalog rather than via the
  scripts could pick QA's own `_VW` by mistake instead of Prod's -- worth a specific callout in
  the rebuild procedure, not just a note here.

Every "prod only" claim in this repository's docs and script docstrings has been corrected to
reflect this (`network_dataset_migration_plan.md`, `network_dataset_script_review.md`,
`roadmap_lrs_network.html`, `qa_network_refresh_runbook.html`, and scripts 03/04). See
[`qa_network_refresh_runbook.html`](qa_network_refresh_runbook.html) for the corrected,
verified rebuild procedure -- it also turned out to need two full build cycles, not one, once
this was worked through against the actual script logic (see that document's Phase 3/4 note).

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

**Outputs:** `network_dataset/data/schema_comparison.json`, `network_dataset/data/evaluator_field_map.json`

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

**Script:** `network_dataset/scripts/03_create_network_dataset.py`

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
tables again. Then **superseded again on 2026-09-18**: current IDs are **`N_3`** and **`ND_40192`**
(replacing `ND_40171`, which no longer exists; see `network_dataset_sql_permissions.md`).
*Historical, 2026-09-01:* **`N_3`** (reused the same number a third time) and **`ND_40171`**
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
`network_dataset/scripts/05_rebuild_traffic_turns.py`. Per the script's swap step, the remapped output
was renamed to `TRNLRS_traffic_turn` and left in the `SDEADM.TRNLRS` feature dataset --
matching the `TRNLRS_` prefix used by the other two sources and what
`network_template.xml` already expects. This was marked complete after the 2026-06-26 QA build.

**Regression found 2026-07-07:** a fresh QA build (`ms-gis-sql-q21`, Build Time Jul 7 17:55:29)
again showed all 1,209 `TRNLRS_traffic_turn` records failing with
`Cannot find edge element corresponding to turn identifier 1` -- i.e. `TRNLRS_traffic_turn`
is back to referencing the old, unremapped `TRN_street` OIDs, and Turns shows `0` in
Network Dataset Properties.

Most likely cause: `network_dataset/scripts/03_create_network_dataset.py`'s `copy_fc_to_fd()` only copies
`TRN_traffic_turn` → `TRNLRS_traffic_turn` if the destination doesn't already exist. If the
network dataset (and its feature dataset contents) was deleted and recreated at some point
after 2026-06-26, re-running script 03 would have silently re-copied the raw, unremapped
turn FC over the previously-remapped one. Script 03 and `05_rebuild_traffic_turns.py` now
log this distinction explicitly (copy vs. skip) via `network_dataset/scripts/log_utils.py` to make this
easier to catch going forward.

**Same regression hit again in Dev and QA (2026-07-14):** during the `SDEADM.TRNLRS_network`
feature-dataset-separation pilot, `network_dataset/scripts/03_create_network_dataset.py` was run against
both Dev and QA before `network_dataset/scripts/06_migrate_network_fd.py` (which was supposed to move the
already-remapped `TRNLRS_traffic_turn` out of `SDEADM.TRNLRS` first). Since
`SDEADM.TRNLRS_network` was still empty in both environments, `copy_fc_to_fd()`'s "skip if
destination exists" check didn't fire, and script 03 fell back to copying fresh from the
raw, unremapped `SDEADM.TRN_streets_routes\TRN_traffic_turn` in each -- confirmed in Dev by
inspecting the new `SDEADM.TRNLRS_network\TRNLRS_traffic_turn` attribute table: every row
has `EDGE1FCID = 7134`, the old `TRN_street` source's registration ID (also the value baked
into `network_template.xml`'s original `<ClassID>` from the Phase 1 extraction), not the
new `TRNLRS_TRN_STREET` copy's freshly assigned ID. `network_dataset/scripts/05_rebuild_traffic_turns.py`
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
`network_dataset/scripts/03_create_network_dataset.py` to recreate and rebuild the network dataset. The
staging FC (`TRNLRS_traffic_turn_staging`) is also now created via `in_template_feature_class`
instead of `in_network_dataset`, so it isn't registered as a live source and stays freely
deletable/renameable before it's swapped in.

See [`network_traffic_turns.md`](network_traffic_turns.md) for the original diagnosis and remapping script.

- [x] Run `network_dataset/scripts/05_rebuild_traffic_turns.py` to spatially remap turns to new edge OIDs (2026-06-26, QA)
- [x] Verify written/skipped counts from script output
- [x] Rebuild network after turn FC is replaced
- [x] Re-run `network_dataset/scripts/05_rebuild_traffic_turns.py` against Dev + `SDEADM.TRNLRS_network` (2026-07-14 regression)
- [x] Re-run `network_dataset/scripts/05_rebuild_traffic_turns.py` against QA + `SDEADM.TRNLRS_network` (2026-07-14 regression; 1,209/1,238 written, 2.3% skipped)
- [x] Complete the swap in Dev (delete network dataset → swap turn FCs → re-run script 03)
- [x] Complete the swap in QA (delete network dataset → swap turn FCs → re-run script 03)
- [x] QA: nonzero turns confirmed (1,184 on 2026-09-18). Dev still unconfirmed
- [ ] (superseded, kept for history) Confirm rebuilt Dev and QA networks show nonzero turns in Network Dataset Properties
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
- [x] ✅ **Confirm one-way restriction is enforced** — confirmed working 2026-09-03, after a
      multi-day debugging saga (root cause: `Force Full Build` not checked after an evaluator
      script edit, plus an earlier inline `!STR_DIR!` token-substitution bug along the way).
      Full blow-by-blow in [Step 6](#step-6--rebuild-and-re-export-the-network-template-2026-09-01).
- [x] ✅ **Confirm turn restriction logic works** against `TRNLRS_traffic_turn` — 2026-09-01.
      Turn OID 2 (`QUINPOOL RD → ROBIE ST`, a genuine prohibited movement) solved straight
      through at first (51 ft) because the Route layer's **Travel Mode** did not have
      `TrafficTurn`/`OneWay` checked. After enabling both, the same stops produced a correct
      411 ft loop-around detour. **Restriction attributes do nothing unless the Travel Mode
      enables them** — now recorded in `CLAUDE.md`.
- [ ] Check address range fields (`FROM_LEFT`, `TO_LEFT`, `FROM_RIGHT`, `TO_RIGHT`) for geocoding

**2026-09-09 — Robbie Evans notified QA is ready for expert testing.** Alex emailed Robbie
(cc Jillian Landry, subject "LRS Network dataset") confirming
`SDEADM.TRNLRS_network\SDEADM.TRNLRS_street_network` in QA is ready for his expert network
testing, requested by end of week (~2026-09-11), ahead of the HRFE kickoff meeting the
following Tuesday (2026-09-15, derived from the 2026-09-09 send date — not stated explicitly
in the email). Suggested focus: turn and one-way restrictions — both already confirmed working
above, so this is Robbie's independent sign-off on top of the checks already run here.

**2026-09-11, Robbie's testing stopped early: ~500 source-geometry errors.** Within the first
two minutes of testing, Robbie found streets "that aren't getting calculated due to dangles in
the segments when editing." He asked whether to keep testing or identify all of them for the
LRS folks to fix and then rebuild; Jillian Landry's answer was to identify all of them, since
the corrected version has to be retested anyway. By the end of the day **about 500 were
flagged**. Robbie's own characterisation of what he had looked at so far:

> Most of the ones I'm looked at are just simple fixes though. The segment is extended past
> the intersection.

The list is going to Melanie Parker. Jillian's direction (2026-09-11, to Robbie and Alex):
*"no sense in your continuing on until these are fixed. Can you also send to Ryan as they most
likely will share the fixing."*

**What this means for this project.** These are defects in the **LRS source data**, upstream of
everything the network build does, not network dataset defects. Three consequences:

1. **QA acceptance testing is paused**, not failed. Nothing found so far contradicts the
   restriction and turn evidence recorded above; Robbie never got far enough to exercise it.
2. **This is the same class of defect as the 7 sub-metre turn-build gaps** (0.006–0.41 m,
   see the runbook's §3.3) and the 4 plain-street junction anomalies from the 2026-08-31
   alignment check, seen at editing scale and much higher volume. Worth checking the overlap
   once Mel has the list, since the corrections may close some of the 9 `Cannot find at junction`
   turn failures for free.
3. **A QA refresh is required before Robbie can retest**, and it is not a simple truncate/load.
   Procedure, and why, in [`qa_network_refresh_runbook.html`](qa_network_refresh_runbook.html).

**2026-09-10, Ryan Lowe asked for the junction-network workflow for Esri Case #04248942.**
Esri Canada (Sukhjit P.) has reproduced HRM's LRS intersection behaviour in-house and reports
it as **data-specific, not ArcGIS Pro version-specific**. Esri asked twice (2026-09-01 and
2026-09-09) for the high-level workflow the "coworker" (Alex) follows to create the junction
network, plus any error messages with screenshots. Written up in
[`junction_network_workflow_esri_case.html`](junction_network_workflow_esri_case.html),
including a draft reply to Ryan. Two Esri questions remain for others to answer: whether a
datum warning appears in the editing map (nobody has checked), and whether all three of Ryan's
scenarios still reproduce on Pro 3.5.8.

- [x] Robbie's expert network testing results (requested 2026-09-09): **stopped 2026-09-11
      after ~500 source-geometry errors; not a pass or fail, testing is paused**
- [x] Robbie sends the ~500 flagged locations to Melanie Parker (implied done: Melanie and Ryan
      "spent weeks" fixing, per 2026-09-23)
- [~] LRS team corrects the flagged geometry; confirm the fixes land in prod's
      `TRNLRS_TRN_STREET_VW` before refreshing QA. **Largely done; 57 new, unexplained issues
      found 2026-09-24, see the 2026-09-29 update above**
- [ ] Refresh QA per [`qa_network_refresh_runbook.html`](qa_network_refresh_runbook.html),
      then hand back to Robbie for a retest
- [ ] Check whether Robbie's ~500 overlap the 7 sub-metre turn-build gaps and the 4 plain-street
      junction anomalies
- [ ] Send the junction-network workflow write-up to Ryan for Esri Case #04248942 (Alex committed
      to sending it 2026-09-24; not confirmed sent)
- [ ] Ryan replies to Esri: OK to share the file geodatabase with Esri Inc.; Esri may file a
      data-specific defect report
- [ ] Configure Directions on the live QA network, then re-export and re-commit the template
      (both the live network and `network_template.xml` currently lack it)
- [ ] Before any wholesale QA-from-Prod refresh: back up QA's `TRNLRS_network` contents and
      confirm the refresh method (see the 2026-09-29 update)
- [x] WA exclusion coded in `network_exclusions.py` (scripts 03 and 04), untested against a live
      database
- [ ] Island exclusion: Melanie supplies the FDMID list, then add it to `ISLAND_FDMIDS`
- [x] Exclusion profiles in `network_exclusions.py`: `GENERAL` (WA, transit access roads `TA[0-9]%`,
      islands; what scripts 03 and 04 use) and `HRFE` (GENERAL plus emergency access roads and ETAs
      `% ETA [0-9]%`). Per-rule counts are logged. Unit tests in `scripts/tests` (25), including
      the patterns run against the saved Prod diagnostic. Not run against a live database.
- **Decided 2026-09-29: UNDER REVIEW streets stay in every network.** A requirement to drop them
  (names like "UNDER REVIEW 329", `STR_TYPE` `UN`, seen in a `Network_Error_Segments` table of 57
  rows) was withdrawn the same day, and a test guards against them being excluded. Nothing about
  them is coded.
- [ ] **Transit access roads are removed from every network** (decided 2026-09-29, so they are in
      `GENERAL` next to WA and HRFE inherits them). This changes the distance network too, at its
      next rebuild; the QA network built on 2026-09-29 (37,674 edges) still contains them. **All 124
      go, no exceptions** (decided 2026-09-29; this closes Robbie's ambiguous answer on whether to
      keep any, so no follow-up to him is needed). Nothing is left to code; the change waits on the
      next edge-copy rebuild.
- [ ] HRFE exclusions from Robbie's 2026-09-01 and 2026-09-17 emails: **Robbie replied 2026-09-29**
      (inline approve/reject images and one typed answer): ETAs (22, complete set) and emergency
      access roads are to be removed from HRFE routing; transit `TA[0-9]%` has no other names. The
      ETA and emergency access patterns are in `HRFE_EXTRA`. Record: [`meetings/2026-09-29_HRFE_network_dataset_email_thread.md`](meetings/2026-09-29_HRFE_network_dataset_email_thread.md).
      Diagnostic run against Prod on 2026-09-29 (18,644 rows; output in
      `intermediate_results/candidate_exclusions_20260929.csv`): **transit access roads**
      `FULL_NAME LIKE 'TA[0-9]%'` = 124 rows (TA1 to TA52, all `STR_TYPE` `RD`; the looser `TA%` adds
      85 ordinary streets; `STR_TYPE` `ATA` = 0); **ETAs** `FULL_NAME LIKE '% ETA [0-9]%'` = 22 rows
      ("HIGHWAY nnn ETA n", Expressway class, `STR_TYPE` null, a guessed search); emergency access = 4
      and WA = 61, as expected. Expected edge copies (counts to check on the first build): general
      18,459 of 18,644 (WA 61 + transit 124 out); HRFE 18,433 (those plus emergency access 4 and ETAs
      22, 211 in all; the four sets share no FDMIDs).
- [x] **HRFE build scaffolding written 2026-09-29, not run.** Decisions (Alex): a second network
      dataset in its own feature dataset `SDEADM.TRNLRS_network_HRFE` (network
      `TRNLRS_street_network_HRFE`), the **same turn restrictions** as the distance network (the
      same legacy turns remapped onto its own edge copy), and Robbie edits the extra roads himself
      in QA once Alex has created the feature class from what he drops in the monthly folder.
      `scripts/network_definitions.py` holds both networks' names and renders the HRFE template
      from the committed one; `HRM_NETWORK=HRFE` selects it in scripts 03, 05, the verifier and
      `qa_refresh`. Unset behaves as before (checked: every path the scripts build is identical to
      the baseline). Steps to run it: [`hrfe_network_runbook.md`](hrfe_network_runbook.md). Still to
      do: create the feature dataset, run `test_template_create.py` for HRFE, then `qa_refresh`
      steps 3 to 8 with grants; then the extra roads (open questions in the runbook).
- [ ] **HRFE additions, updated 2026-10-01 after Robbie's reply.** The **bridge is dropped**: he will use a
      point barrier on it himself. The **Station 2 segment has arrived** in
      `monthly\202610oct\evansr\Network_Segments_For_Alex\Network_Segments.gdb` and was inspected on 2026-10-01
      with `scripts/diagnostics/11_inspect_extra_roads.py`: 8 segments, all four network fields present, and 7
      ends on a street mid-segment (both ends of the Station 2 connector are on University Ave), so those streets
      need splitting before anything connects (see the runbook). He will add the **driveways and routes outside HRM** to the same
      layer (interpretation). He agreed to the **splits** approach (split points in their own layer,
      re-applied after each sync). Still to do: create the extra-roads feature class in
      `SDEADM.TRNLRS_network_HRFE`, add it to the template as a second edge source, grant Robbie edit access, and
      settle who rebuilds after his edits. Open questions are in the runbook.
- [ ] Decide whether the HRFE (speed) network is a second network dataset or an added cost
- [ ] Decide the turn-OID-stability question before prod cutover (see
      [`network_dataset_script_review.md` §D](network_dataset_script_review.md#d-turn-references-do-not-survive-an-lrs-refresh-structural))

---

### Step 5 — Automate sync and rebuild in `LRS_updates.py` ✅

**Script:** `network_dataset/scripts/04_sync_and_rebuild_network.py`

`TRNLRS_TRN_STREET` (FD copy used by the network) must be kept in sync with
`TRNLRS_TRN_STREET_VW` (standalone authoritative FC) after every LRS refresh.

**Known defect (verified against the code 2026-09-29):** `sync_network_edge_source()` calls
`append_feature()`, which calls `arcpy.TruncateTable_management()` on the existing target. That
fails with `ERROR 001395` on `TRNLRS_TRN_STREET`, a controller-dataset member, so the automated
sync has never been able to work against a live network. It also runs `BuildNetwork` straight
after the reload without remapping turns, which leaves every turn pointing at stale OBJECTIDs
(see the turn-OID-stability decision). Only `04_sync_and_rebuild_network.py` uses `DeleteRows`.

**Implemented in `scripts/LRS_updates.py`:**
- Network Analyst extension checked out at startup (alongside LocationReferencing); raises
  `LicenseError` if unavailable
- `sync_network_edge_source(sde_connection)` function added — calls `append_feature()` to
  truncate/reload `TRNLRS_TRN_STREET` from `TRNLRS_TRN_STREET_VW`, then calls `BuildNetwork`
- Called after the `street_features` loop, inside the QC-pass `else` block
- Both extensions checked in the `finally` block

`network_dataset/scripts/04_sync_and_rebuild_network.py` also exists as a standalone script if a one-off
sync/rebuild is needed outside of a full LRS refresh cycle.

- [x] Check out Network Analyst extension in `LRS_updates.py`
- [x] Add `sync_network_edge_source()` call to `LRS_updates.py` after the `street_features` loop
- [ ] Deploy updated `LRS_updates.py` to `E:\HRM\Scripts\Python\LRS_updates.py`
- [ ] Run a full LRS refresh cycle end-to-end and confirm the network rebuilds cleanly

**Feature dataset separation note:** `sync_network_edge_source()` and
`network_dataset/scripts/04_sync_and_rebuild_network.py` now target `SDEADM.TRNLRS_network`
instead of `SDEADM.TRNLRS` for the FD copy and network dataset path. Since
`LRS_updates.py` has not been deployed to prod yet (see checklist above), this
hasn't caused a live failure -- but prod's FCs must be moved into
`SDEADM.TRNLRS_network` (mirroring the Dev pilot) before this deploys,
otherwise the sync step will fail to find `TRNLRS_TRN_STREET` at its new
expected path.

---

### Step 6 — Rebuild and re-export the network template (2026-09-01)

The VBScript deprecation (see [the 2026-09-01 update](#update-2026-09-01--qa-network-dataset-rebuilt-from-scratch))
means the template-driven rebuild path in `network_dataset/scripts/03_create_network_dataset.py` is broken
until a **Python-evaluator template** replaces `network_dataset/data/network_template.xml`. Until then, any
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
2026-09-01 — this is the authoritative original, which `network_dataset/data/network_template.xml` never had):

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
8. **The exported template still had the bug — caught before committing, not after.** A fresh
   `CreateTemplateFromNetworkDataset` export, read directly rather than trusted from the solve
   test alone, showed `Against Digitized`'s Code Block was still `return True` unconditionally
   — the isolation-test hardcode from step 5/6 had never actually been reverted to the real
   `FOTD` check. The OID 12002 solve test in step 7 could not have caught this: `FOTD` is one
   of the values `return True` also blocks, so a "no solution" result there is consistent with
   either the correct logic or the still-broken hardcode. Fixed the Code Block for real this
   time, Force Full Build again.
9. **Real-world cross-check surfaced a second, unrelated finding.** Testing the corrected
   network against Bishop St (`STR_DIR='FOTD'`) showed westbound allowed / eastbound blocked —
   the *opposite* of the real-world sign. Confirmed with HRM's GIS team: **this specific
   edge's line geometry is digitized backwards** (a pre-existing data issue, unrelated to this
   evaluator work) — `STR_DIR`/the evaluator logic are both correct, but "Along Digitized" and
   "Against Digitized" map to the wrong real-world compass direction on this one edge because
   the underlying line runs the wrong way. Not something to fix in the network dataset; a data
   quality item to track separately (see the note under `STR_DIR` in `CLAUDE.md`).
10. **Final, decisive verification: a discriminating two-way-street test.** Testing a one-way
    street alone (Hollis St) could not distinguish "the real `FOTD`/`FDTO` logic is working"
    from "Against Digitized is still hardcoded to always restrict" — both predict the same
    result on a street that's genuinely one-way. Tested Barrington St (ordinary two-way)
    instead: solved cleanly at 272 ft in **both** directions, no restriction either way. This
    is the result that actually rules out the hardcoded-`True` bug, and it passed. `OneWay` is
    confirmed correctly implemented as of 2026-09-03.

**Checklist:**

- [x] Rebuild QA's network dataset with Python evaluators (interactive wizard)
- [x] Recover the authoritative `OneWay` logic from Dev before it becomes unrecoverable
- [x] Apply the corrected `OneWay` Python evaluator to QA and re-run Build Network (with Force
      Full Build — required, see above)
- [x] Re-run the one-way solve test — confirmed working 2026-09-03, including the
      discriminating two-way-street check (step 10 above) that actually rules out the
      hardcoded-`True` regression
- [x] Reply to the DBA (Sylvie Blanchard) who killed the blocking session, confirming it was
      this ArcGIS Pro Build Network operation and not a rogue process
- [x] **Export the corrected template and commit it over `network_dataset/data/network_template.xml` —
      done 2026-09-03.** A first export attempt was caught still containing the `return True`
      bug (step 8 above) before being committed; the second, verified export (both `FDTO` and
      `FOTD` present and correctly placed, confirmed against a fresh `xml.etree.ElementTree`
      parse) is what's now committed.
- [ ] Confirm `network_dataset/scripts/03_create_network_dataset.py` can rebuild from that new template
      (`CreateNetworkDatasetFromTemplate` with Python evaluators is untested in this project)
- [ ] Apply the same from-scratch rebuild to **Dev** (still VBScript, still read-only)
- [ ] Apply to **prod** as part of cutover
- [ ] Report the Bishop St digitizing-direction issue (step 9 above) to whoever owns
      `TRNLRS_TRN_STREET` data quality, if not already captured by the GIS team conversation
      that confirmed it

---

## Open Questions / Future Work

### Route Intersection Class (`INT_RouteOnRoute`) — origin, external consumer, and a deployment discrepancy to verify

`SDEADM.INT_RouteOnRoute` (the Route Intersection Class used throughout this project as a
junction-alignment QA input — see [`network_dataset_script_review.md` §A0b](network_dataset_script_review.md#a0b-junction-alignment-check-run-2026-08-31----grade-separation-not-a-transform-bug-a-handful-of-real-anomalies))
is generated by `generate_intersections()` in `scripts/LRS_updates.py`, which calls
`arcpy.locref.GenerateIntersections` against `LRSN_Route`. Per the 2026-07-22 and 2026-07-30
"Road Network Check In" meeting notes:

- The `GenerateIntersections` call was originally commented out in `LRS_updates.py`, believed to
  have been added for a one-off need and then left disabled. Around 2026-07-22, Alex Gallagher
  uncommented it so it runs as part of the regular LRS refresh.
- It feeds a **net-new external application**: police enter collision information and need it
  snapped to the nearest intersection, and `INT_RouteOnRoute` is intended to support that lookup.
  Justin reviewed the output feature class, confirmed the attribute data looked reasonable, and
  took it to the design authority (per the 2026-07-30 meeting) rather than closing the request
  outright, to confirm it meets the wider business unit's needs.
- As of 2026-07-30, Alex described it as already updating nightly in prod.

**This doesn't match the current repository state.** `scripts/LRS_updates.py`'s `__main__` block
still has the call commented out:

```python
# generate_intersections(sde_branch=r"E:\HRM\Scripts\SDE\SQL\prod_RW_sdeadm_branch.sde")
```

(note it also takes a dedicated `sde_branch` connection — the function's own docstring requires
a branch-versioned connection, unlike the plain `SDEADM_RW`/`SDEADM_RO` connections the rest of
the script uses) — and the "Automate sync and rebuild" section above notes `LRS_updates.py`
**has not been deployed** to `E:\HRM\Scripts\Python\LRS_updates.py`. Both statements can't be
true at once: either the deployed prod copy of `LRS_updates.py` has since diverged from what's
tracked in this repo (plausible, given the script's own deployment gap noted elsewhere in this
doc), or the "live in prod" status described in the meeting refers to something other than this
tracked script (a manual run, a different job). Worth confirming directly against the deployed
prod script and a fresh look at `INT_RouteOnRoute`'s edit dates before relying on either source.

- [ ] Confirm whether `INT_RouteOnRoute` is actually refreshing nightly in prod today, and if so,
      by what mechanism — the tracked `LRS_updates.py` doesn't currently call
      `generate_intersections()`
- [ ] If prod's deployed `LRS_updates.py` has diverged from this repo, reconcile the two before
      the next deploy — see the "Deploy updated `LRS_updates.py`" item under Step 5
- [ ] Confirm with Justin / the design authority whether the intersections feature class is
      considered final, or still under review as of the 2026-07-30 meeting

### Prod cutover — SDE connection gap

`TRNLRS_TRN_STREET` has now been created against a **prod** SDE connection
(`E:\HRM\Scripts\SDE\SQL\Prod\prod_RW_sdeadm.sde`). Scripts 01/03/04/05 (see
[Key Paths Reference](#key-paths-reference)) only defined `SDE_CONNECTION` / `SDE`
constants pointing at `dev_RW_sdeadm.sde` or `qa_RW_sdeadm.sde` -- none of them had a
prod path wired in. (`LRS_updates.py` is the exception: it already reads
`SDEADM_RW`/`SDEADM_RO` from `config.ini`, which is presumably the real prod config.)

This has since been resolved differently for each script, based on where each
one's data actually needs to live:

- **`network_dataset/scripts/03_create_network_dataset.py`** always reads `TRNLRS_TRN_STREET_VW`
  from a dedicated `PROD_SDE_CONNECTION` (using the confirmed path above),
  since prod's copy is authoritative. (A same-named standalone FC also exists
  in QA, confirmed via Pro Catalog 2026-09-16 -- origin and freshness
  unconfirmed; not read by any tracked script, which hardcode Prod
  specifically to avoid depending on it.) `SDE_CONNECTION_UPDATE` (Dev/QA/prod,
  still a manually-edited constant) controls where the FD copy, junction/turn
  sources, and new network dataset get created.
- **`network_dataset/scripts/04_sync_and_rebuild_network.py`** is now prod-only -- there's no
  Dev/QA target at all. Dev/QA builds are one-off snapshots created by script 03;
  only prod's copy of `TRNLRS_TRN_STREET` needs continuous re-syncing after every
  LRS refresh, since that's the copy live routing actually uses. See the script's
  docstring for the reasoning.
- **`network_dataset/scripts/05_rebuild_traffic_turns.py`** still has a manually-edited `SDE`
  constant (Dev/QA/prod) with no dedicated prod constant yet -- see the open item
  below.

**Still open:**
- [ ] Add a dedicated `PROD_SDE_CONNECTION` to `network_dataset/scripts/05_rebuild_traffic_turns.py`
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

**Sequencing confirmed (2026-07-30 "Road Network Check In"):** Robbie Evans confirmed the
network can be built and exercised with the standard Network Analyst tools on connectivity
(distance) alone first — junctions, traffic turns, and a "stop network"-style solve don't need
`TravelTime` to exist — and travel time should be added only once connectivity is known good.
That's the order this project has actually followed (Phases 4/5a/5 before this section), so no
change needed here, just confirmation the sequencing is right.

**Don't design the field calculation from scratch.** Per the same meeting, Robbie has computed
travel time from `SPEED` and segment distance this way for roughly 12 years and has screen
captures of his existing field-calculation setup (location: T-drive, exact path not yet
confirmed — ask Robbie). The calculation needs a travel-time field added to the **street
segment input** (i.e. computed before/alongside `TRNLRS_TRN_STREET_VW`, not on the network
edges directly), consistent with the "Preferred approach" above.

**Caveat on default speeds:** per Robbie/Melanie in the same meeting, HRM's existing speed data
is based on **regular vehicle speeds, not fire-apparatus speeds** — fire trucks carry speed
limiters and can't reach the same speeds. Keep that distinction in mind if this network is ever
used for emergency-response ETA estimates rather than general routing; the proposed defaults
below are not validated for that use case.

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
- [ ] Pull Robbie Evans's existing speed/distance → travel-time field-calculation reference
      from the T-drive before designing a new one
- [ ] Add `SPEED` to SQL in `_update_streets` and to the edge source
- [ ] Add `TravelTime` cost attribute to `network_template.xml` with a **Python** evaluator
      (not VBScript — see [Step 6](#step-6--rebuild-and-re-export-the-network-template-2026-09-01)
      for why VBScript evaluators are no longer viable on this network dataset)
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
| Standalone edge source (authoritative) | `SDEADM.TRNLRS_TRN_STREET_VW` (outside any feature dataset; Prod's copy is authoritative and is what every script reads -- a same-named FC also exists in QA, confirmed 2026-09-16, origin/freshness unconfirmed, see the 2026-09-16 note below) |
| FD copy of edge source (used by ND) | `SDEADM.TRNLRS_network\TRNLRS_TRN_STREET` in Dev/QA; `SDEADM.TRNLRS\TRNLRS_TRN_STREET` in prod |
| Turn source (used by ND) | `SDEADM.TRNLRS_network\TRNLRS_traffic_turn` in Dev/QA -- both re-remapped via script 05 and swapped in (2026-07-14); `SDEADM.TRNLRS\TRNLRS_traffic_turn` in prod |
| XML template | `network_dataset/data/network_template.xml` |
| Old network dataset | `SDEADM.TRN_street_network` (in `TRN_streets_routes`) |
