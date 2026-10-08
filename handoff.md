# Handoff: current status

**Last updated 2026-10-08 (after the Road Network meeting).** Read this first, then follow the links for detail. Update it whenever
status changes (what is done, what is waiting, what to do next). The detailed history lives in
`network_dataset/docs/network_build_status.md`; this file is the short version of where things are.

Nothing here has been run against ArcGIS Pro or SQL Server by Claude. Claude works in a Linux
container with no `arcpy` and no database access, so the code is tested against stand-ins only.
"Done" below means written and unit tested, or recorded by Alex, not proven on live data.

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
- Rebuilt by script on 2026-09-29 through `qa_refresh`: Edges 37,674, Junctions 16,187, Turns 1,184,
  five turns rejected at build. SQL grants applied (`N_3`, `ND_40986`).
- Handed to Robbie to retest.

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
  network is rebuilt (next steps, item 6). She is offline after 2:30 and said Ryan can look at anything found.
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

## Next steps, in order

1. **Inspect Robbie's geodatabase:** run `network_dataset/scripts/diagnostics/11_inspect_extra_roads.py`
   (check `EXTRA_GDB` first). It reports the schema and how each segment end meets the HRFE streets. Its
   geometry code has only been compiled, so expect to adjust it.
2. **Create `SDEADM.TRNLRS_network_HRFE` in QA** in Pro, with the same spatial reference as
   `SDEADM.TRNLRS_network`.
3. **Prove the rendered HRFE template** without touching QA: `HRM_NETWORK=HRFE` then
   `qa_refresh/test_template_create.py`.
4. **Build the HRFE network:** `qa_refresh` steps 00 and 03 to 07 with `HRM_NETWORK=HRFE` (skip 01 and
   02), then SQL grants for the new registration IDs and smoke tests. Check the step 03 log reads
   18,433 of 18,644 with per-rule counts WA 61, transit 124, emergency access 4, ETAs 22.
5. **Add Robbie's extra roads** as a second edge source: create the feature class from his data, add it
   to the template, grant him edit access. Not designed in detail yet.
6. **Rebuild the distance network.** Melanie's fixes are posted in Prod's LRS (2026-10-08). First confirm
   `TRNLRS_TRN_STREET_VW` in Prod has been refreshed from them (`LRS_updates.py`), then run `qa_refresh` so
   Robbie can retest against them. Expect the topology to be deleted by step 02, so rerun `07_create_topology.py`
   afterward and reapply its exceptions.
   Check the step 03 log reads 18,583 of 18,644 (WA 61 only).

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
