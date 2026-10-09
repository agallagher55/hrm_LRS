# Handoff: current status

**Last updated 2026-10-09 (QA refresh checklist added; before that, the 2026-10-08 Road Network meeting).** Read this first, then follow the links for detail. Update it whenever
status changes (what is done, what is waiting, what to do next). The detailed history lives in
`network_dataset/docs/network_build_status.md`; this file is the short version of where things are.

Claude has not run anything against ArcGIS Pro or SQL Server. Claude works in a Linux container with no
`arcpy` and no database access, so its code is tested against stand-ins only. Alex has run some of it in QA
(the topology script and the edge fields, 2026-10-08). "Done" below means written and unit tested, or
recorded by Alex, not proven on live data unless it says Alex ran it.

## The two networks

| | Distance network | HRFE network |
|---|---|---|
| Purpose | Distance routing, tested by Robbie Evans | Fire and emergency routing for HRFE |
| Network dataset | `TRNLRS_street_network` | `TRNLRS_street_network_HRFE` |
| Feature dataset (QA) | `SDEADM.TRNLRS_network` | `SDEADM.TRNLRS_network_HRFE` (**not created yet**) |
| State | Built in QA on 2026-09-29 | Scripts written, never run |
| Excluded from it | WA streets and islands (list pending). Transit access roads (`TA[0-9]%`) **stay in** (decided 2026-10-08) | The same, plus transit access roads (**stay out**, Alex 2026-10-08, HRFE is for fire), emergency access roads and ETAs |

`UNDER REVIEW` streets are deliberately **kept** in both. A requirement to drop them was added and
withdrawn on 2026-09-29, and a test guards against them being excluded.

## Distance network (QA)

Done:
- **Rebuilt again by script on 2026-10-09** through `qa_refresh` steps 00 to 07, from Prod's view with
  Melanie's 2026-10-08 fixes (Alex ran it, the figures are from his output). Edge copy 18,595 of Prod's 18,670
  (WA 61, islands 14, no transit rule), junctions 15,424, raw turns 1,238 remapped to 1,189 (49 skipped, 4.0%,
  the same as 2026-09-18 and 09-29). New class IDs: edge 41020, junction 41021, turn 41023, system junctions
  41024. Created in 13 s and built in 13 s from the committed template, **so the template with Directions now
  creates and builds in SDE** (the scratch file geodatabase test cannot prove that). Built 2026-10-09 10:14:24:
  Edges 37,698, Junctions 16,190, Turns 1,184 (the same 5 turns rejected: 686, 746, 747, 829 and 830).
  Directions is now on (Base Name `STR_NAME`, Suffix Type `STR_TYPE`, Full Name `FULL_NAME`); it was off on the
  2026-09-29 network. Step 07 passed all 10 checks. BuildErrors saved as
  `intermediate_results\BuildErrors_203adcb2-cc6f-40b3-9e26-72b6f7f029ca.txt`: 1,158 lines, 5 `Cannot find at
  junction` (the same turns) and 1,153 `Standalone user-defined junction` warnings (1,133 on 2026-09-29), nothing
  else. Topology rebuilt: points 4,332 (dangles 4,089, Must Not Intersect 241, Self-Intersect 2), lines 255
  (single part 253, overlap 1, intersect 1). **Melanie's fixes moved the dangles only from 4,101 to 4,089 and left
  the 5 rejected turns and the multipart count unchanged**, so ask her whether her fixes should have changed
  geometry (event behaviours alone would not close gaps), and whether Prod's view was refreshed after she posted.
- Rebuilt by script on 2026-09-29 through `qa_refresh`: Edges 37,674, Junctions 16,187, Turns 1,184,
  five turns rejected at build. SQL grants applied (`N_3`, `ND_40986`).
- **Smoke test passed 52 of 52 on 2026-10-09 at 14:34, after fixing a template defect it found**
  (`smoke_test_network.py`, through an OS authentication login to `ms-gis-sql-q21` / `GISRW01`, so the grants are
  proven for a non-owner too). Saved as `intermediate_results\smoke_test_20261009_143441.csv`. The story:
  - 11:39 first run: 44 of 44 passed, but all 36 blocked cases ended in "no route" and none in a detour.
  - 12:02 rerun with the no-detour report: the same, all `ERROR 030212`.
  - 12:29 rerun with the positive control: 0 of 8 ordinary T junction moves worked with the restrictions on.
    The `TrafficTurn` Turn default evaluator was restricted (true) with no turn source evaluator, from the
    template re-exported on 2026-09-18, so no route could turn a corner. The original design (and the July
    template) was Constant True on `TRNLRS_traffic_turn` and Constant False on every default. Both the 09-29 and
    10-09 networks had the defect.
  - Fix: the template was corrected and guarded by `tests/test_network_template.py` (PR #99), and the live QA
    network was fixed in Properties (turn source True, default False) with a Force Full Build.
  - 14:34 rerun: 8 of 8 controls work, 35 of 36 blocked cases found a detour (for example `QUINPOOL RD ->
    ROBIE ST`, 799 m against 194 m direct) and 1 found no route (`KAYE ST -> AGRICOLA ST`, edges 9839 -> 9983,
    plausibly a spur or dead end, not looked at), and all 18 one way edges behave (`BISHOP ST` included).
  - The rebuild's BuildErrors file is `intermediate_results\BuildErrors_9bf10ace-c5e5-488f-85b1-15af29dd41fc.txt`:
    the same 5 turns rejected and 1,155 standalone junction warnings (two more than the earlier build: junction
    OIDs 14552 and 14973; cause unknown).
- **Still to do after the 2026-10-09 rebuild:** the SQL grants are done (`N_3` 6/6, `ND_41025` 2/2) and the smoke
  tests pass. Left: export the live network's template and check its `TrafficTurn` assignments match the committed
  one (the committed edit has not been proven by a create from the template, and do not commit the export, since
  exports lose Directions and can carry the wrong name), a route solve with directions on, Robbie's topology
  exceptions, and telling Robbie QA is ready (and that `TrafficTurn` was broken before today).

Open:
- Smoke tests, a check that the LRS gap corrections really are in Prod's `TRNLRS_TRN_STREET_VW`, and
  Directions on the live network. The committed template includes Directions but a create from it has
  not been proven (`qa_refresh/test_template_create.py` has never been run).
- **Transit access roads (decision 2026-10-08):** the distance network leaves them in unless somebody
  complains. The QA network already contains them, because it was built before the filter. The exclusion
  profiles now match: `GENERAL` drops WA only, and the `TA[0-9]%` pattern (124 rows) moved to `HRFE`
  (written and tested, in the open PR, not run). Expected distance edge copy at the next build: 18,583 of
  Prod's 18,644 before the island rows come off.
- Islands: Robbie sent the 14 McNabs and George's FDMIDs on 2026-10-08 and they are now in `ISLAND_FDMIDS` in
  `network_exclusions.py` (written and tested, not run), so both networks exclude them from the next build.
  The edge copy will lose the rows with those FDMIDs, so the expected 18,583 and 18,433 fall by that many.
  Check the per-rule count in the step 03 log. Melanie Parker replied on 2026-10-08 that about 99% of
  the islands are already removed by the WA street type filter and the rest are covered by Robbie's FDMIDs
  (McNabs and George's have named roads inland), so no other island list is coming.
- **Melanie's LRS fixes are done (her email, 2026-10-08):** she reviewed the network error file and made every
  edit that could be made, applied event behaviours, and the changes are reconciled and posted. She did them in
  **Prod**, not QA, so QA only gets them after Prod's `TRNLRS_TRN_STREET_VW` is refreshed from the LRS and QA's
  network is rebuilt (next steps, item 1). She is offline after 2:30 and said Ryan can look at anything found.
- The 57 new untraceable LRS issues (Melanie and Ryan Lowe). Melanie's email does not say whether her fixes
  covered these 57, so ask. The Prod 11.5 upgrade is confirmed finished
  (Alex, 2026-09-29), so the version-mismatch theory can now be tested from a matching client and database.
- Esri case #04248942: Esri asked (2026-09-01 and 09-09) for the high-level workflow for creating the network and any
  error messages with screenshots. **Alex answered Ryan by email on 2026-10-08** with the five-step workflow, the
  environment, the errors (5 `Cannot find at junction` turns 686, 746, 747, 829 and 830 of 1,189, and 1,133
  `Standalone user-defined junction` warnings) and the dangling segments found in testing. He attached the
  2026-09-29 BuildErrors file (saved in `intermediate_results`) and a screenshot of the `WARNING 030116` line. The
  sent email asks whether Melanie thinks her LRS fixes may answer Esri's questions, and does not ask Ryan to hold
  his reply or to confirm sharing the file geodatabase. Still open:
  - Ryan to answer Esri. In the 2026-10-08 meeting Melanie said she told him to hold off until she double checks
    whether her fixes answer Esri (the transcript lists Ryan as the "Unknown user" and garbles his name).
  - Ryan to reply that Esri Canada may share the file geodatabase copy of the LRS he uploaded on 2026-09-04
    with Esri Inc. Jillian and Melanie agreed verbally on 2026-09-24. Nobody needs to send a new file.
- Turn OID stability: every edge-source refresh breaks every turn reference and needs a remap. Decide
  the approach before Prod (`network_dataset_script_review.md` section D).

## HRFE network

Decisions (Alex, 2026-09-29):
- A second network dataset in its own feature dataset, named as above.
- The **same turn restrictions** as the distance network: the same legacy turns remapped onto its own edge copy.
- Robbie edits the extra roads himself in QA, after Alex creates the feature class from what he sends.

Done (written and tested, not run):
- Exclusion profiles `GENERAL` and `HRFE` in `network_exclusions.py`. Expected edge copies, to check on
  the first build: distance 18,583 of Prod's 18,644 (WA 61), HRFE 18,433 (WA 61, transit 124, emergency
  access 4, ETAs 22; the four sets share no FDMIDs).
- `network_definitions.py` holds each network's names and renders the HRFE template from the committed
  one. The `HRM_NETWORK` environment variable picks the network in scripts 03, 05, the verifier, the
  orchestrator and `qa_refresh`. Unset means distance, with every path unchanged (its exclusions now drop WA only; transit stays in for distance and out for HRFE). A mistyped variable name stops a run, and steps 02 and 06 also need `NETWORK_TO_DELETE` / `NETWORK_TO_BUILD` set in the script to match. The Prod edge sync
  (`04`, called by `LRS_updates.py`) ignores the variable on purpose.
- `docs/hrfe_network_runbook.md` has the build steps.

Robbie's answers (record: `network_dataset/docs/meetings/2026-09-29_HRFE_network_dataset_email_thread.md`):
- 2026-09-29: ETAs (22, complete set) and emergency access roads (4) are removed from HRFE routing.
  Transit `TA[0-9]%` (124) has no other names; Alex then decided all 124 go in both networks.
- 2026-10-01: numbers reconfirmed. **The bridge is dropped** (he will use a point barrier himself).
  The **Station 2 segment is in his monthly folder**
  (`monthly\202610oct\evansr\Network_Segments_For_Alex\Network_Segments.gdb`) and has not been
  inspected. He will add driveways and routes outside HRM to the same layer (an interpretation of his
  numbering, which is one off from Alex's list). He agreed to the splits approach.

## Safe School Streets view (2026-10-05)

`TRNLRS_TRN_Safe_School_Streets_VW` per the updated Appendix A: `FROM_STR`/`TO_STR` now come from
`E_AddressRange` (no longer from `LRSN_Route`), and a new `OWN` field comes from `E_StreetOwnership`.
Both event tables were added to the segmentation overlay in `scripts/LRS_updates.py`, and `OWN` was added to the
query. Written only, not run (no `arcpy` here). Before the next run:
- Add `OWN` (Text 4, domain `SNF_own`, alias Ownership) to the existing target feature class, because
  `Append` with `NO_TEST` matches by field name and would leave it empty.
- Expect more, shorter segments, since the overlay now also splits at address range and ownership breaks.
- Checked in Pro: `E_District` has `DISTRICT` (Short), so the query's `e.DISTRICT` is right even though
  Appendix A says `DIST_ID`. The target field's type should be Short to match.

## Topology (2026-10-08)

Robbie asked for a topology on the network feature dataset. `network_dataset/scripts/07_create_topology.py`
builds `SDEADM.TRNLRS_TRN_STREET_topology` in QA: the edge source plus six rules (Must Not Overlap, Must
Not Intersect, Must Not Have Dangles, Must Not Self-Overlap, Must Not Self-Intersect, Must Be Single Part),
validated, with errors exported and counted per rule. Settings are globals (`USE_SCRATCH` runs it on a
scratch copy, `RESET_EDGE_SOURCE` removes and re-adds the edge source; leave the latter `False` normally).

Done and verified on live QA (Alex, 2026-10-08):
- The edge class sits in both the topology and the network dataset with no versioning error. The network
  still shows Built (2026-09-29 08:55:04, Edges 37,674, Junctions 16,187, Turns 1,184) and a route solve
  passes, so the topology does not disturb the network.
- Errors (a scratch copy gave the same numbers):
  - Points 4,345: Must Not Have Dangles 4,101, Must Not Intersect 242, Must Not Self-Intersect 2.
  - Lines 255: **Must Be Single Part 253 (multipart edges)**, Must Not Overlap 1, Must Not Intersect 1.
- Blank `SPEED` (Short) and `TRAVEL_TIME` (Double) fields were added to the live edge class with
  `08_add_edge_fields.py`, as Robbie suggested, and the network and topology were unchanged afterward.
  Script 03 adds them after the edge copy, so every refresh keeps them. Nothing fills them yet and no
  network attribute uses them.

Waiting on Robbie (questions emailed by Alex 2026-10-08; the meeting that day answered only items 2 and 5, in part):
1. **His valid dangles and intersections class** (the exceptions): where it lives, one class or two, geometry
   type, whether it carries an FDMID or street ID or is only points and whether it still lines up with the
   new LRS-based edges (it was probably built against the old street network). Exceptions are marked in the
   Error Inspector in Pro. Not discussed in the meeting.
2. **The 253 multipart edges:** discussed 2026-10-08, see the meeting section below. Melanie says they are
   valid LRS construction. Robbie has not tested whether they affect a route solve and will do so.
3. **The optional rule Must Not Intersect Or Touch Interior** (`INCLUDE_OPTIONAL_RULES`, off): his old setup
   had it. It catches a street end touching the middle of another street, which matters for connecting his
   extra roads under End Point connectivity. Not discussed.
4. **His speed times distance method:** the path on the T: drive (not recorded), his units (ours are km/h and
   minutes, chosen by Claude) and how he treats streets with no posted speed. Robbie asked in the meeting
   about next steps with speed and Alex said filling the fields is one of them, with no detail.
5. His retest of the distance network. He plans to retest on 2026-10-08 in the afternoon, once Melanie's
   dangle fixes are in (see below).
6. Whether his extra roads class must be registered as versioned for him to edit it. Not discussed.

Other open items:
- Exceptions are lost when `qa_refresh` step 02 deletes the topology, so reapply them after each refresh
  (rerun `07_create_topology.py` after step 06). OBJECTIDs change on every reload, so they cannot be carried over.
- `qa_refresh` step 02 now deletes the topology first. `DeleteRows` in script 04 on a topology member is untested.
- SQL grants for the topology tables: unknown whether Robbie's login needs them.
- Nothing fills `SPEED` and `TRAVEL_TIME` yet; `E_SpeedLimit` does not segment like the other event tables.

## Meeting 2026-10-08 (Robbie, Melanie, Ryan, Jillian, Alex)

From the transcript `2026-10-08_Road_Network_Analysis_txt.txt` (uploaded, not committed). Speaker names and some
words are garbled in it, so check anything that matters.
- **Multipart edges.** Robbie ran the topology on his own offline copy of the LRS (on the T: drive, newest
  data, because he did not know whether QA was updated) and found many multipart features. Many are cul-de-sac
  bulbs, where two segments meet at an end point. Melanie: that is how the LRS is built (the end point of an
  address event, merged into one feature), so they are valid and technically two segments. Robbie: exploding one
  gives two parts, and dragging them together and resnapping merges them again. He does not expect them to break
  the network and said he cares only that the network works. Open: whether they need fixing in the LRS for
  other uses, and whether they affect routing. Alex suggested a route solve test. Robbie's first test run flagged
  only dangles, not these.
- **Dangles.** Melanie found what causes them and is about halfway through the fixes, hoping to finish the
  afternoon of 2026-10-08. Some will remain and are valid: roads that start in another county and continue into
  HRM, and island roads such as McNabs. Robbie said that is expected.
- **Retest.** Robbie wants Melanie's dangle fixes in first, then will test the network on 2026-10-08 in the
  afternoon. Open: the fixes land in the LRS and Prod, so QA's edge copy needs a refresh (`qa_refresh`) before
  QA reflects them. Robbie asked whether the new QA is built, and the transcript's reply is unclear.
- **Alex's update.** Speed and travel time fields are added to the edge class in QA and not filled yet.
  WA streets are out.
- **Transit access roads, decision.** Robbie: the exclusion might just be a fire thing, and the main network
  should probably keep them rather than remove and re-add. Melanie: some business units use them as roads
  (through routes and parking lots, for example in Sackville and Downsview, and the ones at the transit
  facility and garage), and whether to exclude is a business unit decision. Alex: leave them in unless somebody
  complains, and he can add explicit exceptions. Alex later confirmed HRFE still needs transit out, since
  HRFE is for fire. The code was changed to match (see the Distance network bullet).
- **Islands.** Robbie: McNabs and George's can go. He sent the FDMIDs the same day (see Distance network).
  Robbie noted that once non-HRM roads are added, some floating segments will connect.
- **Esri.** See the Esri bullet under Distance network.
- **Next meeting** in two weeks, set by Jillian (no calendar time next week). Melanie will email when her
  fixes are done.

## QA refresh checklist (distance network, written 2026-10-09)

`qa_refresh` reads the edge source straight from **Prod's** `TRNLRS_TRN_STREET_VW`, so QA's own copy of the
view needs no refresh first. Prod's view is refreshed daily, so Melanie's 2026-10-08 fixes are in it. Still
spot-check a few FDMIDs she changed. Leave `HRM_NETWORK` unset. Run every step from an ArcGIS Pro Python prompt
in `qa_refresh`, and stop on any failure.

**New 2026-10-09, not yet run on live QA:** `qa_refresh\run_qa_refresh.py` runs this whole checklist in order
(preflight, backup, audit, delete, copy, remap, verify, build, verify, BuildErrors, grants, audit, topology). It
asks you to type a phrase at three gates (before the delete, before the swap and build after your spatial review,
before the grants) instead of editing `CONFIRM_*` flags, writes a transcript and a run report to
`qa_refresh\output`, and stops at the first failure with the phase to resume at. `collect_build_errors.py`
copies the BuildErrors file out of the temp folder and compares it with the last one. Step 00 and the runner now
check every deployed script and the template against `data\deploy_manifest.json` (hashes, so line endings do not
matter). **Copy `data\deploy_manifest.json` and the whole `scripts` and `qa_refresh` folders to T: first**, and
delete `_test_template_create.py` and any `03_initial_build.py` from `qa_refresh` there. After editing any script
or the template, run `make_deploy_manifest.py` and commit the manifest (a test fails if it is stale). The manual
steps below still work and say what each phase does.

**Before the run**
- [ ] **Redeploy the T: drive files.** A check of the screenshots against the repo on 2026-10-09 found:
  - `data\network_template.xml` on T: is dated 9/29/2026 8:17 AM and 20 KB. The repo's is 21 KB, committed
    2026-09-29 after the Directions block was merged back in (commit `162aa76`). The T: copy is the version
    from before that merge, so **it has no Directions. Replace it.**
  - `scripts\network_exclusions.py` on T: is dated 10/1/2026. The island FDMIDs and the transit change
    landed 2026-10-08 (commits `42cfca5` and `261ecd2`). Explorer rounds sizes up to the KB, so the size
    looks right whichever version it is. **Replace it.**
  - `03_create_network_dataset.py`, `edge_fields.py` and `07_create_topology.py` on T: are dated 10/8, but
    the island commit came after. Replace the whole `scripts` folder, `qa_refresh` and `data\network_template.xml`
    from the repo rather than file by file, then compare sizes in bytes (`dir` in a command prompt), not Explorer's KB.
  - `qa_refresh` was not in the screenshots, so check it too.
- [ ] Close Pro map layers, attribute tables and Properties dialogs that hold the QA network.
- [x] **Before-state recorded 2026-10-09** (steps 00 and 01 done, step 02 not yet run). SQL audit on QA: `N_1`
  10 of 10, `N_2` 6 of 6, `N_3` 6 of 6 (the network), `ND_40986` 2 of 2 (the network's dirty area pair) and
  `ND_7293` 2 of 2 (legacy), `ND_12010` and `ND_21268` 1 of 1, and three single table groups with no grant that
  belong to other networks or leftovers (`ND_38752`, `ND_39207`, `ND_396`). Network properties: built
  2026-09-29 08:55:04, Edges 37,674, Junctions 16,187, Turns 1,184, class IDs edge 40578, junction 40579, turn
  40984, system junctions 40985. **Support Directions was unchecked on the live network**, because it was built
  from the pre-Directions template, so Directions is a real change to look for after step 06.
  `qa_refresh\audit_grants.py` now does the SQL part (below).
- [x] `test_template_create.py` was run on 2026-10-09 (Pro 3.5.8, same machine since July). It reads QA only and
  **cannot prove the template**: `CreateNetworkDatasetFromTemplate` failed with `ERROR 030168` (the `Length`
  evaluator, `Shape.STLength()`, "field that cannot be found") in its scratch file geodatabase, with the new
  committed template and also with the 9/18 `network_template_3_5_8_Sep2026.xml`. The `Length` block is
  identical in both and in the template that created fine in SDE on 2026-09-29, so the likely cause is the file
  geodatabase (that expression may only resolve against SQL Server), not the template. Unconfirmed.
  What it did show: the template has Directions and no VBScript, and the sources copied (18,583 edges,
  15,424 junctions, 1,189 turns).
- [ ] If step 06's create fails the same way in SDE, the sources and swapped turns are already in place. Fix the
  template, then run `03_create_network_dataset.py` directly (it creates and builds), then step 07. Do not
  rerun step 06: its staging class was renamed by the swap. Fallback template: the 9/18 Sep2026 file, then
  set Directions by hand.

**The steps, with what to check at each**

| Step | Command | What to check |
|---|---|---|
| 00 | `python 00_confirm_sources.py` | Read-only. Prints Prod and QA counts and `MODDATE` ranges. The Prod count should be about 18,644 (it moves daily). Read any stale-copy warning about the deployed scripts or template and fix it before going on. |
| 01 | `python 01_backup_and_baseline.py` | Mandatory in practice. Check it reports the turn backup, the baseline JSON and the file geodatabase export under `output/` (all three sources). Step 02 refuses to run without a backup under 24 hours old. |
| 02 | `python 02_delete_network_sources.py` | First destructive step. Set `CONFIRM_DELETE_QA_NETWORK = True` first and reset it to `False` afterward. It deletes the topology, then the network, then the edge, junction and turn classes. Nothing should be open in Pro. |
| 03 | `python 03_copy_sources.py` | Find the "Edge exclusions applied" line in the log. Expect **18,583 minus the island FDMID rows** (Prod 18,644 less WA 61, and transit stays in). Check the per-rule counts: WA 61 and a count for the islands (Robbie's 14 McNabs and George's FDMIDs), with no transit rule. Check the junction and turn copies match QA's legacy classes (turns were 1,189 last time). Check `SPEED` and `TRAVEL_TIME` were added. It creates and builds nothing. |
| 04 | `python 04_remap_turns.py` | Creates `TRNLRS_traffic_turn_staging`. The skip rate was about 4% last time. **If it jumps well above that, read the skip categories before going on**: Melanie's fixes may have moved geometry more than expected. Skip reasons refer to the legacy `TRN_traffic_turn`, not `TRNLRS_traffic_turn`. |
| 05 | `python 05_verify_staging_turns.py` | The verifier needs 95% agreement or more. Check that the edge source FCID in the staging turns equals `Describe(edge).DSID` (a new number, since step 02 and 03 recreated the edge class). Then do the spatial review of the skipped turns. This is the gate for step 06. |
| 06 | `python 06_swap_and_final_build.py` | Set `CONFIRM_REVIEWED_STAGING = True` only after the step 05 review, and reset it afterward. It stops before changing anything if `run_full_network_rebuild.py` on T: is stale. The only network build, and it should take **under two minutes**. If it runs for hours, check Task Manager CPU (near idle means stuck) and ask the DBA for a blocking SQL session. Check the log for edges, junctions and turns (2026-09-29: Edges 37,674, Junctions 16,187, Turns 1,184, 5 turns rejected). Expect slightly fewer edges now (the island rows are gone). Find the `WARNING 030116` line for the BuildErrors path and **copy that file out the same day**. |
| 07 | `python 07_verify_live_turns.py` | Same verifier, against the live turn class after the swap. It should agree with step 05. |

**After step 07**
- [x] **Done 2026-10-09 10:42:** `grant_network_access.py` granted 7 tables (`N_3` all 6 and `ND_41025_DIRTYOBJECTS`);
  the four source tables already had the grant; `audit_grants.py` shows `N_3` 6/6 and `ND_41025` 2/2. Tested
  from an OS-auth account on 2026-10-09 by the smoke test (opened the network and solved). Original step: **Re-apply the SQL grants** under the new registration IDs. The IDs come from step 06's build, so grant only
  now. Without them nobody can open the network. Run `qa_refresh\audit_grants.py` with `LABEL = "after"`: it
  runs the section 2b audit of `network_dataset_sql_permissions.md` through the QA connection and writes
  `grants_audit_after_<time>.csv` and `network_ids_after_<time>.csv` to `qa_refresh\output`. Expect `N_3` 6 of 6
  and a new `ND_<id>` pair (2 tables) with no grant yet, which is the one to grant (the new class IDs in the
  second file sit just below it). Grant per `network_dataset_sql_permissions.md`, or run
  `qa_refresh\grant_network_access.py` (a dry run until `APPLY = True`; it grants only what is missing and
  re-checks), then run `audit_grants.py` again to confirm. Both are untested on live QA (written 2026-10-09).
  Result on 2026-10-09: the audit showed `N_3` 0 of 6 and `ND_41025` 1 of 2, and the network dataset's DSID is
  41025, so `ND_41025` is the network's pair.
- [x] Ran `python ..\07_create_topology.py` on 2026-10-09 (numbers above). [ ] Still to do: reapply Robbie's
  exceptions (step 02 deleted the topology).
- [x] BuildErrors file saved and read on 2026-10-09: 5 `Cannot find at junction` (the same 5 turns) and 1,153
  `Standalone user-defined junction` warnings (up from 1,133), nothing else. Fewer was the hoped-for result.
- [x] Smoke tests: `qa_refresh\smoke_test_network.py` passed 52 of 52 on 2026-10-09 at 14:34 (after fixes to a wrong
  server connection, a route layer name clash and the `TrafficTurn` template defect it found; see the top of this
  file). It is the last phase of `run_qa_refresh.py`. Still by hand: a route solve with directions on, and an
  add-to-map in Pro.
- [x] Directions checked on the live network on 2026-10-09: Support Directions ticked, Base Name `STR_NAME`,
  Suffix Type `STR_TYPE`, Full Name `FULL_NAME`, Default Length Attribute `Length`. The Directions create from
  the committed template is now proven in SDE. A route solve that returns directions is still to be tried.
- [ ] Tell Robbie QA is ready, and ask Melanie whether her fixes covered the 57 untraceable issues.
- [ ] Update this file and `network_dataset/docs/network_build_status.md` with the real counts.

## Next steps, in order

1. **Finish the 2026-10-09 rebuild** (the network is built and step 07 passed): SQL grants first, then smoke tests,
   Robbie's exceptions and telling him. The rest of this item is the original plan, kept for the next refresh.
   Follow the QA refresh checklist above. Melanie's fixes are in Prod's view
   (it is refreshed daily). Expect the topology to be deleted by step 02, so rerun `07_create_topology.py`
   afterward and reapply its exceptions. Check the step 03 log: WA 61 plus the island FDMID rows come off
   18,644, so expect 18,583 minus those rows. Transit roads now stay in this network. Then tell Robbie QA is ready.
2. **Follow up with people.**
   - Ryan: confirm Esri may share the file geodatabase copy of the LRS (uploaded 2026-09-04) with Esri Inc,
     and answer Esri once Melanie has double checked her fixes against Esri's questions.
   - Melanie: do her fixes cover the 57 untraceable LRS issues, and has she double checked Esri's questions.
   - Robbie: his retest result, plus the four questions still open (exceptions class, the optional topology
     rule, his speed method and whether his extra roads must be versioned).
3. **Inspect Robbie's geodatabase:** run `network_dataset/scripts/diagnostics/11_inspect_extra_roads.py`
   (check `EXTRA_GDB` first). It reports the schema and how each segment end meets the HRFE streets. Its
   geometry code has only been compiled, so expect to adjust it.
4. **Create `SDEADM.TRNLRS_network_HRFE` in QA** in Pro, with the same spatial reference as
   `SDEADM.TRNLRS_network`.
5. **Prove the rendered HRFE template** without touching QA: `HRM_NETWORK=HRFE` then
   `qa_refresh/test_template_create.py` (never run yet, so expect small fixes). Set `KEEP_SCRATCH = True`
   if you also want a fresh BuildErrors file.
6. **Build the HRFE network:** `qa_refresh` steps 00 and 03 to 07 with `HRM_NETWORK=HRFE` (skip 01 and
   02), then SQL grants for the new registration IDs and smoke tests. Check the step 03 log reads
   18,433 of 18,644 less the island rows, with per-rule counts WA 61, transit 124, emergency access 4, ETAs 22.
7. **Add Robbie's extra roads** as a second edge source: create the feature class from his data, add it
   to the template, grant him edit access. Not designed in detail yet.
8. **Later:** fill `SPEED` and `TRAVEL_TIME` (needs Robbie's method and a source for speeds), and decide how to
   sync the HRFE edge copy after an LRS update.

## Open questions

- Who rebuilds the HRFE network after Robbie edits the extra roads, and how often.
- Whether the extra roads class must be registered as versioned for him to edit it.
- Connectivity: the network uses End Point connectivity, so an added road that meets a street
  mid-segment will not connect without a split. Step 1 above shows whether Station 2 has this problem.
- Whether weak bridges on the routes outside HRM are handled by his point barriers too.
- **Nothing syncs the HRFE edge copy after an LRS update.** `04` (called by `LRS_updates.py`) reloads only
  the distance edge copy, so HRFE goes stale until `qa_refresh` is rerun by hand. Decide how to sync both
  before HRFE exists in Prod.
- Whether the rendered HRFE template's leftover `<DSID>` is accepted for a second network in the same
  database. The scratch test cannot show it.
- The HRFE network also needs travel time (speed). Deferred: `E_SpeedLimit` does not segment like the
  other event tables, and Robbie has a speed times distance method he has used for years.

## Working notes

- **Tests:** `python -m unittest discover -s tests` from `network_dataset/scripts` (76 tests, no ArcGIS
  needed). They import the scripts against a stand-in for `arcpy`.
- **Deploy to the T: drive** before a run, and compare sizes or hashes with the repo. Stale copies cost
  time on 2026-09-29. `network_definitions.py` and `connectivity_check.py` are new files the scripts import.
- **Branch and PR:** work on `claude/bold-dirac-65wvnr` and open a draft PR into
  `claude/setup-lrs-repo-0S4rJ` (the repo's default branch). PRs #70, #71 and #72 are merged (#72 on
  2026-10-01, the HRFE scaffolding and Robbie's replies), so start the branch afresh from the base before
  new work.
- **BuildErrors files:** `Build Network` writes `BuildErrors_<guid>.txt` to the client's temp folder, in a numbered
  subfolder, for example `C:\Users\ALEX~1.GAL\AppData\Local\Temp\3\`, not the top level of `%TEMP%`. Windows
  cleans these up, so copy the file out the same day. The exact path is in the DEBUG log line `WARNING 030116: The
  network was built, but with some errors. Error details are at ...`, in the script 03 log under
  `network_dataset\logs\`. The 2026-09-29 file is saved in `intermediate_results` (1,138 lines: 5 `Cannot find at
  junction` for turns 686, 746, 747, 829 and 830, and 1,133 `Standalone user-defined junction` warnings, nothing
  else).
- **Emails arrive as `.msg` uploads.** Parse with `olefile`. Robbie once answered with reaction images
  (approve, reject) placed under each bullet; the RTF body shows which image sits where.
- **Tone:** Robbie Evans is a friend of Alex's, so emails to him stay casual. Draft emails in Alex's voice,
  as text in chat. Do not create Gmail drafts: the connected account is Alex's personal address, and
  these go from his work account.
- **Style:** pep8, a blank line after a `for` line, no em dashes and no Oxford commas.

## Where things are

| | |
|---|---|
| Status and history | `network_dataset/docs/network_build_status.md` |
| HRFE build steps | `network_dataset/docs/hrfe_network_runbook.md` |
| Robbie thread record | `network_dataset/docs/meetings/2026-09-29_HRFE_network_dataset_email_thread.md` |
| QA refresh workflow | `network_dataset/scripts/qa_refresh/README.md` |
| SQL grants | `network_dataset/docs/network_dataset_sql_permissions.md` |
| Roadmap | `network_dataset/docs/roadmap_lrs_network.html` |
| Exclusion rules | `network_dataset/scripts/network_exclusions.py` |
| Network names and template rendering | `network_dataset/scripts/network_definitions.py` |
| Diagnostic output from Prod (2026-09-29) | `network_dataset/intermediate_results/candidate_exclusions_20260929.csv` |
| Build errors from the 2026-09-29 QA build | `network_dataset/intermediate_results/BuildErrors_5cfc4bc3-6637-45c2-8a9a-7866b8bbfc00.txt` |
