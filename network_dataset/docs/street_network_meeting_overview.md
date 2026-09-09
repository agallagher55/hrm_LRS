# Street Network Build — Meeting Overview

**Prepared:** 2026-09-08<br>
**Scope:** Repository-based status of the LRS-derived street network (`TRNLRS_street_network`)<br>
**Status date:** The latest network evidence committed to this repository is from 2026-09-03.
This is not a live check of Dev, QA, or Prod.

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

**Suggested message for the meeting:** the QA proof of concept is successful and the difficult
turn/one-way problems have been solved, but the team should treat this as **late validation /
pre-production**, not production-ready.

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

### 2. Close QA acceptance testing

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
| Production readiness | Core QA behavior works, but Prod does not exist and automation is unproven end to end. | Agree on entry/exit criteria and a target cutover sequence. |
| Nine missing turn restrictions | Up to 0.76% of migrated restrictions are not live; two failures are unexplained. | Accept for first release, fix source geometry, or block cutover. |
| No elevation model | Potential false connectivity at grade-separated crossings. | Confirm release acceptance and define test coverage/remediation. |
| No travel-time cost | Routing optimizes distance only; a “5-minute” service area is not currently supported. | Confirm whether distance-only routing meets the initial business need. |
| Road exclusions | Several classes/locations may not be valid for general vehicle routing. | GIS/transportation owner to approve inclusion rules. |
| Source data direction | At least one one-way edge is digitized backward. | Assign data-quality ownership and determine audit scope. |
| Refresh operations | Code is present but not deployed or proven through a full refresh. | Name deployment owner, schedule rehearsal, define monitoring and rollback. |
| Environment configuration | Several scripts still rely on manually edited connection constants. | Decide whether parameterization is required before Prod. |
| SQL permissions | Grants are network-instance-specific and Dev remains pending. | Assign DBA/GIS ownership and add grants to the cutover checklist. |

## Suggested meeting agenda (45 minutes)

1. **5 min — Outcome and current position:** QA proof of concept works; project is in late
   validation/pre-production.
2. **10 min — Demo/evidence:** QA sources and properties, one-way route in both directions,
   prohibited-turn detour, and current build errors/turn count.
3. **10 min — Acceptance gaps:** legacy route comparisons, geocoding/address ranges, nine turn
   rejects, elevation limitation, and road exclusions.
4. **10 min — Operational readiness:** corrected template test, full refresh rehearsal, Prod
   feature-dataset setup, permissions, and rollback.
5. **10 min — Decisions and owners:** approve first-release scope, assign data-quality items,
   agree Dev/Prod sequence, and set evidence required for cutover.

## Questions to ask in the room

1. Is the first release expected to optimize **distance only**, or is travel time a requirement?
2. Is 1,180 of 1,189 migrated turn restrictions acceptable if the nine exceptions are listed and
   risk-assessed, or must all be resolved before Prod?
3. Who can approve routing exclusions for transit access, water access, island roads, and emergency
   turnarounds?
4. Who owns correction and validation of street geometry/digitized direction?
5. Is endpoint-only connectivity acceptable at launch, and which grade-separated locations must be
   included in acceptance tests?
6. Who owns the Prod build, SQL grants, deployment of `LRS_updates.py`, monitoring, and rollback?
7. Should environment selection be parameterized before anyone runs the rebuild tools in Prod?

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
  ArcGIS/SDE failure modes, and documented open checklist items.
- **Medium confidence:** the exact current state of QA and Dev, because it was not queried live for
  this overview.
- **Low/no evidence:** current Prod readiness beyond code and plans; the repository explicitly says
  Prod has not been built.
- Some long-lived documents retain historical or superseded checklist text. This overview resolves
  conflicts in favor of the latest dated updates and the latest committed implementation; use the
  current QA environment as the final authority at the meeting.
