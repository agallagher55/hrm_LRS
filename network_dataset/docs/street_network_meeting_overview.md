# Street Network Build — Meeting Overview

**Prepared:** 2026-09-08 · **Updated:** 2026-09-15 for the 2026-09-16 check-in<br>
**Scope:** Repository-based status of the LRS-derived street network (`TRNLRS_street_network`)<br>
**Status date:** The latest network *execution* evidence committed to this repository is from
2026-09-03; the latest *acceptance-testing* evidence is from 2026-09-11. This is not a live
check of Dev, QA, or Prod.

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
good shape: 1,189 turn records passed the repository's ten pre-build checks, and 1,180 became
live network turn elements. Nine turns (0.76%) were rejected during the network build.

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
| **QA** | **Working and editable.** Rebuilt from scratch on 2026-09-01 with Python evaluators. 1,180 live traffic-turn elements. Current repository evidence includes successful service-area, traffic-turn, and one-way tests. | This is the reference implementation and the best environment for acceptance testing. |
| **Dev** | A June 2026 build still solves, but contains VBScript evaluators and is permanently read-only in ArcGIS Pro 3.4+. Its current SQL network-table grants are also recorded as pending. | It must be rebuilt from scratch using the corrected Python template; it cannot be upgraded in place. |
| **Prod** | No network dataset is recorded as built. The target feature-dataset layout, permissions, turn remap, deployment, and cutover still need to be completed. | Production rollout remains future work. Do not describe the new network as live. |

### QA evidence at a glance

| Area | Result | Qualification |
|---|---|---|
| Network configuration | Pass | Correct edge, junction, and turn sources; Length, OneWay, TrafficTurn, and directions configured. |
| Service area | Pass | A 50 km service-area solve completed with acceptable performance on 2026-06-29. This was a distance solve, not the still-documented 5-minute comparison test. |
| Traffic-turn remap | Pass | 1,189 records written; 99.7% `Edge1End` agreement; all ten independent verifier checks passed; five spatial spot checks passed. |
| Built turns | Mostly pass | 1,180 of 1,189 written turns became live elements. Nine (0.76%) failed with `Cannot find at junction`; seven are explained by 0.006–0.41 m geometry gaps, while two exact-coincidence cases remain unexplained. |
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
  `ND_<id>` backing-table identifiers. QA currently documents `N_3` and `ND_40171`; these values
  must not be assumed for Dev or Prod.
- **Treat a very long full build as a likely lock.** A normal full build is recorded as roughly
  90 seconds to under two minutes. An 18-hour QA operation was blocked on SQL Server, not doing
  useful build work.
- **Read the build-errors file.** Summary counts can hide record-level turn failures, and the
  build-error file must be matched to the current run's GUID.

## Remaining work, in recommended order

### 1. Establish the current live baseline before making decisions

The repository is five days newer than its latest network execution evidence, and some older
sections of the status documents are explicitly superseded. In QA, confirm the build date,
source counts, turn count, evaluator definitions, and a current build-error file. Record the
result in one concise run report.

### 2. Fix the LRS source geometry, refresh QA, then close acceptance testing

**Reordered 2026-09-15.** The first four items below are new and block everything after them.

- **Robbie** sends the roughly 500 flagged locations to Melanie Parker.
- **LRS team (Mel, Ryan)** correct the geometry at source. Volume and effort are unknown until
  the list lands.
- **Alex** confirms the corrections are actually present in Prod's `TRNLRS_TRN_STREET_VW` by
  spot-checking Robbie's own FDMIDs, not just by confirming a refresh ran.
- **Alex** refreshes QA per [`qa_network_refresh_runbook.html`](qa_network_refresh_runbook.html):
  sync the edge copy, re-remap turns, verify, swap, recreate, force full build, re-apply the SQL
  grants. Roughly half a day. This is not a truncate-and-load, for three separate reasons set
  out in that document.
- **Decide:** refresh QA once at the end, or in batches as corrections land? Each refresh is a
  half-day rebuild, so batching is much cheaper. But one early partial refresh would confirm
  that a fixed segment actually resolves the editing error, before the LRS team works through
  all 500 on that assumption.
- Check whether Robbie's roughly 500 overlap the seven sub-metre turn-build gaps and the four
  plain-street junction anomalies. If they do, the corrections may close some of the nine
  rejected turns for free.
- **Robbie retests** the refreshed network.
- Run side-by-side representative Route solves against the legacy network and compare path and
  length cost. Include ordinary streets, divided roads, bridges/underpasses, and rural roads.
- Perform the documented address-range/geocoding checks.
- Re-run a smaller service-area comparison framed consistently as distance. A five-minute test
  is not possible until a time cost exists.
- Decide whether the nine rejected turns are acceptable for cutover; investigate the two
  unexplained cases and document the seven geometry-gap cases as accepted defects or fixes.
- Spot-check the earlier degenerate-turn pairs against the current 1,189-record output.

### 3. Resolve routing/data-policy questions

- Decide whether transit access roads, water access roads, George's Island, and emergency
  turnarounds should participate in vehicle routing.
- Confirm and correct the Bishop Street source geometry that is digitized opposite to its
  real-world direction, and determine whether a wider direction-quality audit is warranted.
- Manually inspect the plain-street junction anomalies already identified (including
  Hemlock/High Timber, Wright/Countryview, Skreia/Sailview, and Massachusetts/Lady Hammond).
- Confirm whether lack of elevation modelling is acceptable for first release. Endpoint-only
  topology may mishandle grade-separated crossings if their geometry shares endpoints.

### 4. Prove the automated rebuild path

- Test `CreateNetworkDatasetFromTemplate` with the corrected Python template. The template is
  verified structurally, but the repository records no successful template-driven rebuild with it.
- Run the complete `run_full_network_rebuild.py` workflow in a non-production environment.
- Deploy the updated `LRS_updates.py` only after the Prod feature dataset and network exist.
- Execute one full LRS refresh end to end and confirm: source refresh, edge-copy sync, one network
  build, expected source/element counts, current build errors, permissions, and smoke solves.

### 5. Rebuild Dev, then plan Prod cutover

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
| **Esri Case #04248942** | Esri has reproduced the behaviour in-house and calls it data-specific. Two of the nine rejected turns are at exact 0.0000 m coincidence and remain unexplained on our side. | Alex sends the workflow write-up to Ryan. Team decides whether to push Esri on the two coincident-endpoint failures, and whether the Pro upgrade proceeds before the case closes. |
| **Turn OID stability** | Every edge refresh reassigns edge `OBJECTID`s and silently breaks all 1,180 turn references. This is what makes Robbie's retest a half-day rebuild rather than a ten-minute reload. | Pick one of the three options (remap every cycle, stable OBJECTIDs via keyed update, or turns stored against a stable street key) before Prod cutover, not after. |
| Production readiness | Core QA behavior works, but Prod does not exist and automation is unproven end to end. | Agree on entry/exit criteria and a target cutover sequence. |
| Nine missing turn restrictions | Up to 0.76% of migrated restrictions are not live; two failures are unexplained. | Accept for first release, fix source geometry, or block cutover. |
| No elevation model | Potential false connectivity at grade-separated crossings. | Confirm release acceptance and define test coverage/remediation. |
| No travel-time cost | Routing optimizes distance only; a “5-minute” service area is not currently supported. | Confirm whether distance-only routing meets the initial business need. |
| Road exclusions | Several classes/locations may not be valid for general vehicle routing. | GIS/transportation owner to approve inclusion rules. |
| Source data direction | At least one one-way edge is digitized backward. | Assign data-quality ownership and determine audit scope. |
| Refresh operations | Code is present but not deployed or proven through a full refresh. | Name deployment owner, schedule rehearsal, define monitoring and rollback. |
| Environment configuration | Several scripts still rely on manually edited connection constants. | Decide whether parameterization is required before Prod. |
| SQL permissions | Grants are network-instance-specific and Dev remains pending. | Assign DBA/GIS ownership and add grants to the cutover checklist. |

## Suggested meeting agenda (45 minutes, revised 2026-09-15)

1. **5 min, where we actually are:** the network works; the data underneath it is what stopped
   testing. State that plainly up front so the rest of the meeting is about the data, not the
   build.
2. **10 min, the roughly 500 errors:** what Robbie found, who corrects them, by when, and
   whether a dangle check belongs in the LRS refresh QC. This is the meeting's main decision.
3. **5 min, Esri case:** their finding that it is data-specific, what Alex is sending Ryan, the
   two unexplained coincident-endpoint failures, and whether the Pro upgrade waits.
4. **10 min, the QA refresh:** why it is a half-day rebuild rather than a reload, batch versus
   one-shot, and the turn-OID-stability decision this forces before Prod.
5. **5 min, evidence already banked:** one-way and prohibited-turn solves, 1,180 live turns,
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
   2026-09-09 and not yet answered.

*Carried forward from 2026-09-08:*

6. Is the first release expected to optimize **distance only**, or is travel time a requirement?
7. Is 1,180 of 1,189 migrated turn restrictions acceptable if the nine exceptions are listed and
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
- Every build warning is counted and dispositioned; the nine rejected turns are fixed or formally
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
  whether the corrections close any of the nine rejected turns) is unknown until the list lands.
- **Medium confidence:** the exact current state of QA and Dev, because it was not queried live for
  this overview.
- **Low/no evidence:** current Prod readiness beyond code and plans; the repository explicitly says
  Prod has not been built.
- Some long-lived documents retain historical or superseded checklist text. This overview resolves
  conflicts in favor of the latest dated updates and the latest committed implementation; use the
  current QA environment as the final authority at the meeting.
