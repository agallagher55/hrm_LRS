# Street Network Build — Meeting Overview

**Prepared:** 2026-09-08 · **Updated:** 2026-09-29 after the 2026-09-23/24 meetings<br>
**Scope:** Repository-based status of the LRS-derived street network (`TRNLRS_street_network`)<br>
**Status date:** The latest network *execution* evidence committed to this repository is from
2026-09-03; the latest *acceptance-testing* evidence is from 2026-09-11. This is not a live
check of Dev, QA, or Prod.

## What changed since 2026-09-15

Source: [`meetings/2026-09-23_and_2026-09-24_check_in_notes.md`](meetings/2026-09-23_and_2026-09-24_check_in_notes.md).
The repository has no live evidence newer than the 2026-09-18 QA rebuild, so the upgrade weekend
(2026-09-26/27) and the planned QA refresh are treated as **planned, not confirmed**.

- **Testing restarted and found 57 new, untraceable issues** (islands, a freshly snapped street,
  an overshoot, address-range overlaps, no revision dates). Melanie and Ryan expect the Prod
  upgrade to help but cannot say why they appeared.
- **A version mismatch may explain some of the errors.** Robbie's Pro is 3.5.8; the Prod
  geodatabase is 11.3.0 until the planned upgrade to 11.5. It does not explain errors seen in QA
  (already 11.5.0), so the cause is open.
- **Esri (2026-09-22): no workaround, may file a data-specific defect report,** and asked to share
  the file geodatabase with Esri Inc. The team agreed verbally. This changes how the case reads:
  it is heading toward an Esri-side defect rather than a data fix on our side.
- **Two networks are planned:** the distance network (this one) and an HRFE network with speed
  and extra inclusions/exclusions. Earlier text below treats travel time as an add-on to this
  network; that is undecided.
- **A wholesale QA refresh from Prod would erase QA's network work** (Prod has no
  `TRNLRS_network`). Nobody raised this in the meeting.
- **Corrected QA figures (2026-09-18 rebuild):** 37,788 edges, 16,185 junctions, **1,184** live
  turns, **5** rejected at build (not 1,180 and 9), grants `N_3` / `ND_40192`. The live QA network
  has **no Directions configuration**, and neither does the committed template.
- **Answered:** the Pro upgrade did proceed while the Esri case was open (Q5 below).

## What changed since 2026-09-08

Two things, both external to the repository, and between them they reset the near-term plan.

**1. Acceptance testing stopped on day one (2026-09-11).** Robbie Evans began the expert
testing requested on 2026-09-09 and within the first two minutes found streets "that aren't
getting calculated due to dangles in the segments when editing." By end of day **roughly 500
were flagged**. His characterisation: *"Most of the ones I'm looked at are just simple fixes
though. The segment is extended past the intersection."* Jillian Landry's direction was to
identify all of them rather than keep testing, since the corrected version has to be retested
anyway, and to loop Ryan in because the fixing will likely be shared. The list goes to
Melanie Parker.

This is **paused, not failed**. These are defects in the LRS source data, upstream of
everything the network build does. Nothing found contradicts the restriction and turn evidence
below; Robbie never got far enough to exercise it. But it does mean:

- QA acceptance testing has a new, earlier blocker that is not an engineering task.
- QA has to be **refreshed** before Robbie can retest, and that refresh is a half-day rebuild
  (sync, re-remap turns, verify, swap, recreate, force full build, re-grant), not a reload.
  This promotes the turn-OID-stability question from a theoretical design gap to a live
  operational cost. See [`qa_network_refresh_runbook.html`](qa_network_refresh_runbook.html).
- The roughly 500 are the **same class of defect** as the 7 sub-metre turn-build gaps and the
  4 plain-street junction anomalies already tracked here, at much larger scale. Worth checking
  the overlap once Mel has the list.

**2. Esri Canada has reproduced the intersection behaviour in-house (Esri Case #04248942).**
Sukhjit P. at Esri Canada confirms the behaviour is **data-specific, not ArcGIS Pro
version-specific**, and has twice asked for the high-level workflow used to create the
junction network plus any error messages with screenshots. Written up, with a draft reply to
Ryan Lowe, in
[`junction_network_workflow_esri_case.html`](junction_network_workflow_esri_case.html). Two of
Esri's questions are still open on our side: whether a datum warning appears in the editing
map (nobody has checked), and whether all three of Ryan's scenarios still reproduce on Pro
3.5.8. Jillian also raised on 2026-09-09 whether the Pro upgrade proceeds before this case
closes.

## Executive summary

The project has a **working, editable QA network**, but it is not ready for production cutover.
QA was rebuilt from scratch on 2026-09-01 with Python evaluators and subsequently passed
service-area, prohibited-turn, and one-way routing tests. Its traffic-turn migration is also in
good shape: 1,189 turn records passed the repository's ten pre-build checks. On the 2026-09-01
build 1,180 became live network turn elements (nine rejected); the 2026-09-18 rebuild reached
**1,184 live with five (0.42%) rejected during the network build**.

The main remaining work is operationalization and broader acceptance testing rather than proving
the core concept. Dev still uses the obsolete, permanently read-only VBScript-based network;
Prod has not been built; the automated post-LRS-refresh sync/rebuild code is in this repository
but has not been deployed or exercised end to end; and comparison routing, address-range checks,
permissions, and several data-policy decisions remain open.

**Suggested message for the meeting (updated 2026-09-15):** the QA proof of concept is
successful and the difficult turn and one-way problems have been solved. The project is now
blocked on something else entirely: **the quality of the underlying LRS street geometry**.
Roughly 500 streets with overshooting or dangling segments stopped acceptance testing on
2026-09-11, Esri has independently reproduced the same class of problem and calls it
data-specific, and the repository's own diagnostics were already pointing at it from a
different direction (7 sub-metre gaps failing turn creation, 4 plain-street junction offsets of
6 to 9 metres). That is one problem showing up in three places, and it needs a data owner and a
correction plan, not more engineering on the network dataset.

## What is being built

The objective is to replace the legacy `TRN_street_network` with
`TRNLRS_street_network`, using the LRS-derived streets as its edge source.

```text
LRSN_Route + street event tables
        |
        | OverlayEvents / dynamic segmentation (LRS_updates.py)
        v
TRNLRS_TRN_STREET_VW                authoritative standalone edge feature class
        |
        | copy/sync into the network feature dataset
        v
SDEADM.TRNLRS_network/
  TRNLRS_TRN_STREET                 edge source
  TRNLRS_street_junction            user junction source
  TRNLRS_traffic_turn               remapped prohibited-turn source
  TRNLRS_street_network             network dataset
```

The copy is necessary because all network sources must be in the same feature dataset and SDE
feature-class names must be unique across the geodatabase. The standalone `_VW` feature class
remains authoritative; the network's copy therefore has to be refreshed and the network rebuilt
after each LRS update.

The initial network intentionally reproduces the legacy network's limited routing model:

- **Cost:** length in metres.
- **Restrictions:** one-way streets (from `STR_DIR`) and prohibited traffic turns.
- **Connectivity:** endpoints only, with no elevation fields.
- **Directions:** street name, type, and full-name mappings.
- **Not included:** travel-time cost based on speed limits.

## Environment snapshot

| Environment | Repository-supported status | What it means |
|---|---|---|
| **QA** | **Working and editable.** Rebuilt from scratch on 2026-09-01 with Python evaluators. 1,184 live traffic-turn elements after the 2026-09-18 rebuild. No Directions configured. Current repository evidence includes successful service-area, traffic-turn, and one-way tests. | This is the reference implementation and the best environment for acceptance testing. |
| **Dev** | A June 2026 build still solves, but contains VBScript evaluators and is permanently read-only in ArcGIS Pro 3.4+. Its current SQL network-table grants are also recorded as pending. | It must be rebuilt from scratch using the corrected Python template; it cannot be upgraded in place. |
| **Prod** | No network dataset is recorded as built. The target feature-dataset layout, permissions, turn remap, deployment, and cutover still need to be completed. | Production rollout remains future work. Do not describe the new network as live. |

### QA evidence at a glance

| Area | Result | Qualification |
|---|---|---|
| Network configuration | Pass | Correct edge, junction, and turn sources; Length, OneWay, TrafficTurn, and directions configured. |
| Service area | Pass | A 50 km service-area solve completed with acceptable performance on 2026-06-29. This was a distance solve, not the still-documented 5-minute comparison test. |
| Traffic-turn remap | Pass | 1,189 records written; 99.7% `Edge1End` agreement; all ten independent verifier checks passed; five spatial spot checks passed. |
| Built turns | Mostly pass | 1,184 of 1,189 written turns became live elements (2026-09-18; was 1,180 of 1,189 on 2026-09-01). Five (0.42%) failed with `Cannot find at junction`; three are real sub-metre geometry gaps, while two exact 0.0000 m coincidences on one edge (18393) remain unexplained. |
| Prohibited-turn solve | Pass | A known `QUINPOOL RD -> ROBIE ST` prohibited movement detoured correctly once the Route layer's Travel Mode enabled the custom restrictions. |
| One-way solve | Pass | Confirmed on 2026-09-02/03 after a forced full build, including a two-way control test that ruled out an accidentally always-true evaluator. |
| Legacy route comparison | Pending | No documented side-by-side route/path and cost comparison against `TRN_street_network`. |
| Address ranges/geocoding | Pending | `FROM_LEFT`, `TO_LEFT`, `FROM_RIGHT`, and `TO_RIGHT` have not received the documented acceptance check. |
| **Expert acceptance testing** | **Paused 2026-09-11** | Robbie Evans stopped after roughly 500 LRS source-geometry errors. Not a pass or a fail; the restriction tests were never reached. Resumes after the source corrections land and QA is refreshed. |

## What has been accomplished

1. **Configuration and schema discovery are complete.** The legacy sources, attributes,
   evaluators, and directions were extracted; the old and LRS-derived edge schemas were compared.
   Missing elevation fields were deliberately removed from the new topology configuration.
2. **The network source layout was separated from the LRS feature dataset.** Dev and QA use
   `SDEADM.TRNLRS_network`. Older duplicate source feature classes remain in `SDEADM.TRNLRS` and
   have not yet been cleaned up.
3. **Traffic turns were remapped to the new edge ObjectIDs.** The remap now uses geometry and
   tangent-based tie-breaking, writes the new edge dataset ID, derives `Edge1End` from the new
   geometry, stages changes before swap, and has an independent ten-check verifier.
4. **QA was rebuilt with supported Python evaluators.** This removed the ArcGIS Pro 3.4+
   VBScript read-only problem. A corrected Python-evaluator XML template was exported and committed.
5. **The hardest restrictions have functional solve evidence.** Both prohibited traffic turns
   and one-way restrictions work when the Travel Mode enables them.
6. **Refresh automation has been coded.** `LRS_updates.py` now includes the edge-copy sync and
   network rebuild after a successful LRS refresh; a standalone sync/rebuild script also exists.
7. **A repeatable rebuild path exists.** The full-rebuild orchestrator checks that scripts target
   the same environment, remaps and swaps turns, creates/builds the network once, and reports
   source counts.

## Important lessons already incorporated

- **Use the current template, not an older export.** The repository template was corrected on
  2026-09-03 and contains Python `Length` and `OneWay` evaluators. Earlier templates can preserve
  VBScript or a no-op/incorrect one-way evaluator.
- **Force a full build after evaluator edits.** An incremental build can silently retain stale
  edge-weight values even though ArcGIS reports a successful build.
- **Enable restrictions in the Travel Mode.** Merely defining `OneWay` and `TrafficTurn` on the
  network does not make a Route layer honor them.
- **Delete the network before replacing a registered source.** Edge, junction, and turn sources
  are controller-dataset participants; delete/rename/truncate operations are restricted while the
  network exists. Routine edge refresh uses `DeleteRows` rather than `TruncateTable`.
- **Reapply SQL grants after recreation.** Recreating the network changes its `N_<id>` and
  `ND_<id>` backing-table identifiers. QA currently documents `N_3` and `ND_40192` (2026-09-18); these values
  must not be assumed for Dev or Prod.
- **Treat a very long full build as a likely lock.** A normal full build is recorded as roughly
  90 seconds to under two minutes. An 18-hour QA operation was blocked on SQL Server, not doing
  useful build work.
- **Read the build-errors file.** Summary counts can hide record-level turn failures, and the
  build-error file must be matched to the current run's GUID.

## Remaining work, in recommended order

**Rewritten 2026-09-29.** Steps 1 to 5 are new or replace the 2026-09-15 versions. The old steps
3 to 5 are unchanged and renumbered 6 to 8.

### 1. Establish what actually happened over the upgrade weekend (Alex, first thing)

The repository cannot answer these, and every later step depends on the answers.

- ~~Did the Prod geodatabase upgrade to 11.5 happen?~~ **Yes** (Alex, 2026-09-29). Still open:
  which Pro version is on each machine.
- ~~Was QA refreshed from Prod?~~ **No** (Alex, 2026-09-29), so QA's network is intact. Still
  open: whether and how it will be refreshed (database restore or data copy).
- ~~Did the network-creation overview go to Ryan?~~ **No, not yet** (Alex, 2026-09-29). Still
  open: whether Ryan has replied to Esri about sharing the file geodatabase.
- ~~Which check-in?~~ **Tuesday morning, 2026-09-29** ("tomorrow", per Alex on the evening of 2026-09-28). Still open: when Alex
  does the post-upgrade re-extract (Friday 2026-10-02 was the leaning).
- Record the QA baseline as one dated run report (build date, source counts, turn count,
  evaluator definitions, current build-errors file).

### 2. Protect QA's network work from the refresh

Prod has no network feature dataset, so a wholesale QA-from-Prod refresh removes QA's network.
If the refresh has not happened yet, first: export `TRNLRS_traffic_turn` and the other network
sources to a file geodatabase outside SDE, record the current grants, keep the committed
template, and note any hand-authored turns (the Cogswell ramp item in the refresh runbook). If it
has happened, assess what survived and go straight to the `qa_refresh` procedure (about half a
day: fresh edge copy, turn remap, verify, swap, create, force full build, re-grant). Either way,
tell Robbie the retest waits for that rebuild.

### 3. Re-baseline the geometry errors after the upgrade (Melanie, Ryan, Robbie)

The errors now have three possible causes: real source defects, a Pro/geodatabase version
artefact, and edits nobody can attribute. Separate them instead of fixing blind:

- Re-run Robbie's check once Prod is on 11.5 and everyone is on the same Pro. Sort every hit
  into: gone after the upgrade, real defect (fix), still unexplained.
- For the unexplained 57, take a handful of FDMIDs and compare their geometry across three
  copies: current Prod, the file geodatabase Ryan uploaded to Esri on 2026-09-04, and the QA copy
  Alex compared after loading. A segment that differs from the 2026-09-04 copy was edited since
  then, which turns "ghost" into a dated change window. The address range event is where the
  overlaps show up, so start there.
- Test the version theory directly: the mismatch predicts the QA errors should not exist
  (QA is 11.5.0). If they exist in QA anyway, the theory is incomplete.
- Add a dangle/overshoot check to the LRS refresh QC in `LRS_updates.py`; it currently catches
  none of this.

### 4. Re-extract, filter islands, refresh, rebuild, retest (Alex, then Robbie)

- Re-run the LRS extraction so `TRNLRS_TRN_STREET_VW` reflects the corrected data, and confirm by
  spot-checking Robbie's own FDMIDs, not just that a run completed.
- Implement the island exclusion (McNabs and similar; Melanie supplies the filter). **Coded
  2026-09-29 in `scripts/network_exclusions.py`** (used by scripts 03 and 04) with WA active and
  the island FDMID list empty. It is untested against a live database, and
  `LRS_updates.py`'s sync path bypasses it. Applied to
  the network's edge copy, **not** to `TRNLRS_TRN_STREET_VW`: the standalone class is an org-wide
  product with unaudited consumers (see the impact-assessment item), and Robbie only wants the
  islands out of routing.
- Also exclude **WA (water access) streets**. Robbie says he has asked for this "45 times" (the
  transcript reads "the was"; Alex confirmed it means WA on 2026-09-29). Melanie agrees because
  some overlap roads. The June concern was that civic addresses are coded to WA streets, which
  matters for geocoding but not for a network-only exclusion. Before applying, count
  `STR_TYPE = 'WA'` rows in the edge source and confirm nothing (locator, service) is built on the
  network's edge copy. The migration plan's older advice to filter in the SQL that feeds
  `TRNLRS_TRN_STREET_VW` should not be followed for WA.
- Rebuild the network per the refresh runbook, then Robbie retests the distance network.

### 5. Close the loop with Esri and decide the two-network structure

- **Ryan** replies to Esri (OK to share the file geodatabase). **Alex** sends the creation
  overview if not already sent.
- After the upgrade, re-run Ryan's three scenarios and tell Esri the result **before** they file a
  defect report. Esri reproduced the behaviour on a file geodatabase copy, so it is independent of
  the enterprise version; a change in our results after the upgrade is exactly what they should
  hear about.
- **Jillian, Alex, Robbie** decide: is the HRFE network (speed plus extra inclusions and
  exclusions) a second network dataset or an added cost attribute? Who are the distance network's
  users, and how do they get told once Robbie signs off? (Unanswered on 2026-09-09; Kirk Mills'
  own network analysis was mentioned and not followed up.)

### Engineering hygiene, in parallel

- Configure **Directions** on the live QA network (Base Name `STR_NAME`, Suffix Type `STR_TYPE`,
  Full Name `FULL_NAME`), then re-export and re-commit `network_template.xml`. Both currently
  lack it.
- Fix `append_feature()` in `LRS_updates.py` to use `DeleteRows`. As written,
  `sync_network_edge_source()` fails with `ERROR 001395` on the first real run.
- Prove `CreateNetworkDatasetFromTemplate` end to end (create and build) on the next rebuild.
- Decide the turn-OID-stability approach before Prod. Every refresh, including the one planned
  now, forces a turn remap because of it.

### 6. Resolve routing/data-policy questions

- Decide whether transit access roads, water access roads, George's Island, and emergency
  turnarounds should participate in vehicle routing.
- Confirm and correct the Bishop Street source geometry that is digitized opposite to its
  real-world direction, and determine whether a wider direction-quality audit is warranted.
- Manually inspect the plain-street junction anomalies already identified (including
  Hemlock/High Timber, Wright/Countryview, Skreia/Sailview, and Massachusetts/Lady Hammond).
- Confirm whether lack of elevation modelling is acceptable for first release. Endpoint-only
  topology may mishandle grade-separated crossings if their geometry shares endpoints.

### 7. Prove the automated rebuild path

- Test `CreateNetworkDatasetFromTemplate` with the corrected Python template. The template is
  verified structurally, but the repository records no successful template-driven rebuild with it.
- Run the complete `run_full_network_rebuild.py` workflow in a non-production environment.
- Deploy the updated `LRS_updates.py` only after the Prod feature dataset and network exist.
- Execute one full LRS refresh end to end and confirm: source refresh, edge-copy sync, one network
  build, expected source/element counts, current build errors, permissions, and smoke solves.

### 8. Rebuild Dev, then plan Prod cutover

- Rebuild Dev from scratch with Python evaluators and apply current read/editor permissions.
- Parameterize environment selection (or at minimum add the missing explicit Prod connection in
  the turn-remap script) to reduce the risk of editing the wrong hard-coded connection.
- In Prod: create/confirm `SDEADM.TRNLRS_network`, populate/remap sources, build from the tested
  template, apply grants using Prod's actual registration IDs, run acceptance checks, deploy the
  refresh integration, and define rollback/ownership.
- Clean up duplicate source classes in the old feature dataset only after cutover validation.

## Risks and decisions for the meeting

| Topic | Current risk | Decision or owner needed |
|---|---|---|
| **LRS source geometry quality** | Roughly 500 streets with overshooting or dangling segments stopped acceptance testing. Upstream of everything this project builds, and the same defect class as the seven sub-metre turn gaps and four junction offsets already tracked. | Confirm who corrects them and by when. Decide whether QA is refreshed once or in batches. Decide whether a source-geometry check belongs in the LRS refresh QC, which today checks duplicate and null FDMID, null GSA, and short segments, but not dangles. |
| **Esri Case #04248942** | Esri has reproduced the behaviour in-house and calls it data-specific. Two of the five rejected turns (nine on 2026-09-01) are at exact 0.0000 m coincidence and remain unexplained on our side. Esri said on 2026-09-22 it has no workaround and may file a defect report. | Alex sends the workflow write-up to Ryan. Team decides whether to push Esri on the two coincident-endpoint failures, and whether the Pro upgrade proceeds before the case closes. |
| **Turn OID stability** | Every edge refresh reassigns edge `OBJECTID`s and silently breaks every turn reference (1,184 live turns today). This is what makes Robbie's retest a half-day rebuild rather than a ten-minute reload. | Pick one of the three options (remap every cycle, stable OBJECTIDs via keyed update, or turns stored against a stable street key) before Prod cutover, not after. |
| Production readiness | Core QA behavior works, but Prod does not exist and automation is unproven end to end. | Agree on entry/exit criteria and a target cutover sequence. |
| Five missing turn restrictions | Up to 0.42% of migrated restrictions are not live; two failures are unexplained. | Accept for first release, fix source geometry, or block cutover. |
| No elevation model | Potential false connectivity at grade-separated crossings. | Confirm release acceptance and define test coverage/remediation. |
| No travel-time cost | Routing optimizes distance only; a “5-minute” service area is not currently supported. | Confirm whether distance-only routing meets the initial business need. |
| Road exclusions | Several classes/locations may not be valid for general vehicle routing. | GIS/transportation owner to approve inclusion rules. |
| Source data direction | At least one one-way edge is digitized backward. | Assign data-quality ownership and determine audit scope. |
| Refresh operations | Code is present but not deployed or proven through a full refresh. | Name deployment owner, schedule rehearsal, define monitoring and rollback. |
| Environment configuration | Several scripts still rely on manually edited connection constants. | Decide whether parameterization is required before Prod. |
| SQL permissions | Grants are network-instance-specific and Dev remains pending. | Assign DBA/GIS ownership and add grants to the cutover checklist. |

## Suggested meeting agenda (45 minutes, revised 2026-09-15, written for the 2026-09-16 check-in)

1. **5 min, where we actually are:** the network works; the data underneath it is what stopped
   testing. State that plainly up front so the rest of the meeting is about the data, not the
   build.
2. **10 min, the roughly 500 errors:** what Robbie found, who corrects them, by when, and
   whether a dangle check belongs in the LRS refresh QC. This is the meeting's main decision.
3. **5 min, Esri case:** their finding that it is data-specific, what Alex is sending Ryan, the
   two unexplained coincident-endpoint failures, and whether the Pro upgrade waits.
4. **10 min, the QA refresh:** why it is a half-day rebuild rather than a reload, batch versus
   one-shot, and the turn-OID-stability decision this forces before Prod.
5. **5 min, evidence already banked:** one-way and prohibited-turn solves, 1,184 live turns,
   service area. Short, because none of it is in dispute.
6. **10 min, decisions and owners:** data-quality ownership, refresh cadence, first-release
   scope, and what evidence is required for cutover.

## Questions to ask in the room

*Added 2026-09-15, in priority order for this meeting:*

1. Who owns correcting Robbie's roughly 500 flagged segments, and what is a realistic timeline?
   Does that change the HRFE dependency?
2. Should a dangle / overshoot check be added to the LRS refresh QC in `LRS_updates.py`? It
   currently catches duplicate and null FDMID, null GSA, and short segments, and would not have
   caught any of these.
3. Do we refresh QA once when the corrections are complete, or in batches so Robbie can confirm
   early that a fixed segment actually resolves the editing error?
4. Are these roughly 500 defects new, or did they predate the LRS migration? Nobody has compared
   a sample against the legacy `TRN_street` geometry, and the answer changes whether this is a
   pipeline problem or an inherited one.
5. Does the ArcGIS Pro upgrade proceed before Esri Case #04248942 closes? Raised by Jillian on
   2026-09-09. **Answered by events (2026-09-23/24):** yes, Robbie is already on Pro 3.5.8 and the
   Prod geodatabase upgrade to 11.5 was scheduled for 2026-09-26/27.

*Carried forward from 2026-09-08:*

6. Is the first release expected to optimize **distance only**, or is travel time a requirement?
7. Is 1,184 of 1,189 migrated turn restrictions acceptable if the five exceptions are listed and
   risk-assessed, or must all be resolved before Prod?
8. Who can approve routing exclusions for transit access, water access, island roads, and emergency
   turnarounds?
9. Who owns correction and validation of street geometry/digitized direction?
10. Is endpoint-only connectivity acceptable at launch, and which grade-separated locations must be
    included in acceptance tests?
11. Who owns the Prod build, SQL grants, deployment of `LRS_updates.py`, monitoring, and rollback?
12. Should environment selection be parameterized before anyone runs the rebuild tools in Prod?

## Definition of “ready for Prod” proposed for discussion

- Corrected Python template successfully creates and fully builds a fresh non-Prod network.
- Agreed representative Route and distance Service Area comparisons pass.
- One-way and prohibited-turn smoke tests pass with restrictions enabled in the Travel Mode.
- Address-range/geocoding checks pass.
- Every build warning is counted and dispositioned; the five rejected turns are fixed or formally
  accepted.
- Grade-separation and road-exclusion decisions are recorded.
- Full LRS refresh plus edge sync/rebuild passes in rehearsal.
- Prod feature dataset, remapped turns, permissions, monitoring, and rollback steps are documented,
  with named owners.

## Repository map for follow-up

| Need | Primary file |
|---|---|
| Visual roadmap, milestones, open decisions | `network_dataset/docs/roadmap_lrs_network.html` |
| How to refresh QA, and why it is not a reload | `network_dataset/docs/qa_network_refresh_runbook.html` |
| Junction-network workflow and errors, for Esri Case #04248942 | `network_dataset/docs/junction_network_workflow_esri_case.html` |
| Detailed status and open items | `network_dataset/docs/network_build_status.md` |
| Migration architecture/history | `network_dataset/docs/network_dataset_migration_plan.md` |
| QA execution procedure and evidence | `network_dataset/docs/turn_rebuild_qa_test_runbook.md` |
| Detailed script/defect review | `network_dataset/docs/network_dataset_script_review.md` |
| SQL grants and registration-ID procedure | `network_dataset/docs/network_dataset_sql_permissions.md` |
| Corrected network template | `network_dataset/data/network_template.xml` |
| Create/build | `network_dataset/scripts/03_create_network_dataset.py` |
| Routine Prod edge sync/build | `network_dataset/scripts/04_sync_and_rebuild_network.py` |
| Turn remap/staging/swap | `network_dataset/scripts/05_rebuild_traffic_turns.py` |
| Independent turn validation | `network_dataset/scripts/verify_turn_rebuild.py` |
| End-to-end rebuild orchestration | `network_dataset/scripts/run_full_network_rebuild.py` |
| LRS refresh integration | `scripts/LRS_updates.py` |

## Confidence and caveats

- **High confidence:** repository implementation, QA results recorded through 2026-09-03, known
  ArcGIS/SDE failure modes, and documented open checklist items. The 2026-09-11 and 2026-09-10
  updates above are quoted directly from the email threads.
- **Not yet seen by this repository:** Robbie's roughly 500 flagged locations. There is no list,
  no FDMIDs, and no overlap analysis against the defects already tracked here. The
  characterisation above is his, from the email. Everything downstream of it (effort, timeline,
  whether the corrections close any of the five rejected turns) is unknown until the list lands.
- **Medium confidence:** the exact current state of QA and Dev, because it was not queried live for
  this overview.
- **Low/no evidence:** current Prod readiness beyond code and plans; the repository explicitly says
  Prod has not been built.
- Some long-lived documents retain historical or superseded checklist text. This overview resolves
  conflicts in favor of the latest dated updates and the latest committed implementation; use the
  current QA environment as the final authority at the meeting.
