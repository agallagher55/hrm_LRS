# Handoff: current status

**Last updated 2026-10-01 (after PR #72 merged).** Read this first, then follow the links for detail. Update it whenever
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
| Excluded from it | WA streets, transit access roads (`TA[0-9]%`), islands (list pending) | The same, plus emergency access roads and ETAs |

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
- **The QA network still contains the transit access roads**, because it was built before that filter.
  The next rebuild drops them.
- Island FDMID list from Melanie Parker (`ISLAND_FDMIDS` in `network_exclusions.py` is empty).
- The 57 new untraceable LRS issues (Melanie and Ryan Lowe). The Prod 11.5 upgrade is confirmed finished
  (Alex, 2026-09-29), so the version-mismatch theory can now be tested from a matching client and database.
- Esri case #04248942: Ryan is replying about sharing the file geodatabase. The network-creation
  overview for Ryan had not been sent as of 2026-09-29.
- Turn OID stability: every edge-source refresh breaks every turn reference and needs a remap. Decide
  the approach before Prod (`network_dataset_script_review.md` section D).

## HRFE network

Decisions (Alex, 2026-09-29):
- A second network dataset in its own feature dataset, named as above.
- The **same turn restrictions** as the distance network: the same legacy turns remapped onto its own edge copy.
- Robbie edits the extra roads himself in QA, after Alex creates the feature class from what he sends.

Done (written and tested, not run):
- Exclusion profiles `GENERAL` and `HRFE` in `network_exclusions.py`. Expected edge copies, to check on
  the first build: distance 18,459 of Prod's 18,644, HRFE 18,433 (WA 61, transit 124, emergency access 4,
  ETAs 22; the four sets share no FDMIDs).
- `network_definitions.py` holds each network's names and renders the HRFE template from the committed
  one. The `HRM_NETWORK` environment variable picks the network in scripts 03, 05, the verifier, the
  orchestrator and `qa_refresh`. Unset means distance, with every path unchanged (its exclusions did gain transit). A mistyped variable name stops a run, and steps 02 and 06 also need `NETWORK_TO_DELETE` / `NETWORK_TO_BUILD` set in the script to match. The Prod edge sync
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
- Open: the sheet names the district field `DIST_ID`, but the query selects `e.DISTRICT`. Confirm which
  one `E_District` really has.

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
6. **Rebuild the distance network** so the transit exclusion takes effect, then have Robbie retest.

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
- **Emails arrive as `.msg` uploads.** Parse with `olefile`. Robbie once answered with reaction images
  (approve, reject) placed under each bullet; the RTF body shows which image sits where.
- **Tone:** Robbie Evans is a friend of Alex's, so emails to him stay casual. Draft emails in Alex's voice,
  as text in chat. Do not create Gmail drafts: the connected account is Alex's personal address, and
  these go from his work account.
- **Style:** pep8, a blank line after a `for` line, and no em dashes.

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
