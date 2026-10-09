# QA street-network refresh scripts

This folder contains the ordered entry points for refreshing the QA network
from Prod's current `SDEADM.TRNLRS_TRN_STREET_VW`. The implementation delegates
the complicated network creation, turn remapping, and verification logic to the
maintained scripts in the parent `scripts` folder; these files provide one clearly numbered QA
workflow without duplicating that logic.

Run every command from an **ArcGIS Pro Python** prompt opened in this directory.
Do not continue when a step fails.

```bat
cd /d T:\work\giss\monthly\202607jul\gallaga\network_dataset\scripts\qa_refresh
```

**One command instead of ten.** `python run_qa_refresh.py` runs the whole refresh below (00 to 07, the
audits, the grants, the topology and the smoke tests) in order. It checks the deployed files against the repo first, asks you to
type a phrase at three points (before the delete, before the swap and build after your spatial review, and
before the grants) instead of you editing the `CONFIRM_*` flags, saves a transcript and a run report to
`output/`, and stops at the first failure with the phase to resume at (`START_AT`). Set `NETWORK` at the top of
it to match `HRM_NETWORK`. The step scripts still work on their own. Written 2026-10-09, not yet run on live QA.

**Check the deployed files.** `deploy_check.py` compares a hash of every script and the template on the T: drive
with `data/deploy_manifest.json`, and step 00 and the runner stop when a file is stale or missing (extra files in
`qa_refresh` only warn). After changing any script in `scripts` or `qa_refresh`, or the template, run
`make_deploy_manifest.py` and commit the manifest; a test fails if you forget. Copy the manifest to the T: drive
with the files.

| Order | Command | Purpose |
|---|---|---|
| 00 | `python 00_confirm_sources.py` | Read-only confirmation of the configured Prod input, QA target, live counts, and `MODDATE` ranges. Also prints the size and date of the deployed scripts and template and warns about stale copies. |
| 01 | `python 01_backup_and_baseline.py` | Save a timestamped QA turn backup and a JSON baseline report, and export the edge, junction and turn sources to a file geodatabase under `output/` that survives a database-level QA refresh (`OFFLINE_BACKUP` in `config.py`). |
| 02 | `python 02_delete_network_sources.py` | Delete the network dataset first, then its three source classes. This is the first destructive step. Refuses to run without a recent (24 hour) step 01 backup, and its export outside SDE, that still exist. Set `CONFIRM_DELETE_QA_NETWORK = True` in the script immediately before running it. |
| 03 | `python 03_copy_sources.py` | Copy the edge source from Prod (minus the WA and island exclusions, plus transit access roads, emergency access roads and ETAs for HRFE) and the junction and raw turn classes from QA's legacy classes into `SDEADM.TRNLRS_network`. **Creates and builds nothing**: the network is created and built once, in step 06, after the turn remap. It ends by printing the edge, junction and turn counts next to Prod's edge count and the last step 01 baseline, and stops if a class is empty or the edge copy is larger than Prod's. |
| 04 | `python 04_remap_turns.py` | Create `TRNLRS_traffic_turn_staging` against the fresh edge copy. Needs no network dataset. |
| 05 | `python 05_verify_staging_turns.py` | Run the independent staging-turn verifier. Also complete the spatial review checklist before continuing. |
| 06 | `python 06_swap_and_final_build.py` | Swap the exact reviewed staging class, then create the network from the template and build it once. Set `CONFIRM_REVIEWED_STAGING = True` in the script only after completing the review. Stops before changing anything if the deployed `run_full_network_rebuild.py` is a stale copy. |
| 07 | `python 07_verify_live_turns.py` | Re-run the independent verifier against the live turn class after the swap. |
| before 02 and after 06 | `python audit_grants.py` | Read only. Runs the registration table audit from `network_dataset_sql_permissions.md` (section 2b) through the QA connection and writes `grants_audit_<LABEL>_<time>.csv` and `network_ids_<LABEL>_<time>.csv` to `output/`. Set `LABEL` to `"before"` ahead of step 02 and `"after"` once step 06 has built the network, then use the after files to find the new registration IDs that need a grant. Written 2026-10-09, not yet run on live QA. |
| after 07 | `python smoke_test_network.py` | Route smoke tests using the network's own edges for stops, so no coordinates are needed. For a sample of two edge turns (and the named ones, `QUINPOOL RD -> ROBIE ST`) it checks that the route no longer goes straight through the prohibited turn, and for a sample of `FOTD`, `FDTO` and `BOTH` edges that the blocked direction detours while the other runs straight. A case is skipped, not passed, when the unrestricted route is not the direct one. Set `RO_SDE` to a normal login's connection file to also prove the grants. Read only. Written 2026-10-09, not yet run on live QA, and the `arcpy.na` calls may need a small fix on the first run. Directions are not covered. |
| after 06 | `python collect_build_errors.py` | Copies the BuildErrors file named in the script 03 log to `intermediate_results` before Windows cleans the temp folder, counts the errors by kind and compares them with the previous file, including whether the same turns were rejected. Read only. Written 2026-10-09, not yet run on live QA. |
| after 06 | `python grant_network_access.py` | Grants `PUBLIC SELECT` on the new network's `N_<id>` and `ND_<id>` tables and its four source tables, only where missing. **A dry run unless `APPLY = True`** in the script. It takes the `ND_` group from the network's DSID and the `N_` group as the only 6 table group with no grants (set `N_GROUP` if there are two), and re-checks every table after granting. Written 2026-10-09, not yet run on live QA. |
| after 07 | `python ..\07_create_topology.py` | Recreate the topology on the edge source, validate it and export the errors. Step 02 deletes the topology (it blocks deleting the edge source), so this is needed after every refresh. Written 2026-10-08, not yet run. |
| (inside 03) | | Step 03 also adds the empty `SPEED` and `TRAVEL_TIME` fields to the new edge copy (`edge_fields.py`). To add them to the existing edge class without a refresh, run `..\08_add_edge_fields.py`. |

After step 07, follow Phase 6 and Phase 7 in
`../../docs/qa_network_refresh_runbook.html`: reapply SQL grants using
`../../docs/network_dataset_sql_permissions.md`, inspect the current
`BuildErrors_<guid>.txt`, and perform the one-way and prohibited-turn smoke
tests. Those DBA and interactive route checks are intentionally not automated
here.

## Which network

The steps work on the distance network unless the `HRM_NETWORK` environment variable says
otherwise. `set HRM_NETWORK=HRFE` before a step makes it work on the HRFE network instead, in
`SDEADM.TRNLRS_network_HRFE`. Set it for every step of a run; each step prints the network it
is on, and stops if the scripts disagree. The first HRFE build skips steps 01 and 02 (nothing to
back up or delete). See `../../docs/hrfe_network_runbook.md`.

## Testing a template change without touching QA

`python test_template_create.py` (run it before step 02 after any template edit, since step 03 no longer creates a network) copies the three QA network sources into a scratch file
geodatabase, creates and builds the network there from `data\network_template.xml`, exports a
template back out, and checks the Directions settings survived. QA is only read, so it is safe
while the live network is in use. Run it after any template edit, before relying on the edit in a
rebuild. It was written on 2026-09-29 and had not yet been run at the time of writing.

## Safety and configuration

- **Check the deployed scripts and template against the repo before a run.** On 2026-09-29 two
  stale copies on the T: drive each cost time: `data\network_template.xml` (July, VBScript) made
  step 03 fail with `ERROR 030386`, and `scripts\run_full_network_rebuild.py` (old `main()` with
  no arguments) made step 06 fail with a `TypeError`. Neither had changed anything, but compare
  file sizes or hashes first.
- Close Pro map layers, attribute tables and Properties dialogs that hold the QA network or its
  sources before steps 02 and 06, which delete them.
- `config.py` derives the repository folders from its own mapped `T:` path and
  holds the expected QA paths. Review it before every refresh. It deliberately
  avoids `Path.resolve()`, which would replace `T:` with the backing server name.
- `_shared.py` verifies that scripts 03, 05, and the verifier still point at the
  same QA feature dataset before any delegated operation runs.
- The QA edge copy now has **fewer rows than Prod's `TRNLRS_TRN_STREET_VW`** by design:
  `network_exclusions.py` drops WA streets (and any listed island FDMIDs; HRFE also drops transit access roads, emergency access roads and ETAs) when scripts 03 and
  04 load it. Step 00 prints both counts; the difference should equal the rows matching the
  exclusions, not be zero. Check the "Edge exclusions applied" line in the script 03 log.
- Step 00 cannot prove historical provenance. It confirms current code paths
  and compares live metadata; spot-check known changed `FDMID` geometries in
  Prod and the QA network edge source.
- Step 01 writes the turn backup inside the QA network feature dataset, a baseline JSON file
  under `output/`, and a file geodatabase export of the three sources under `output/`
  (git-ignored). The in-SDE backup is lost in a database-level QA refresh; the export is not.
  Record the current SQL grants separately (see `network_dataset_sql_permissions.md`).
- Steps 02 and 06 use confirmation globals, which default to `False`, so they
  cannot be launched destructively by an accidental double-click. Review the
  applicable prerequisites, set the global at the top of the script to `True`,
  run the step without arguments, and reset the global to `False` afterward.
- Do not click **Build Network** by hand after step 06 unless you tick **Force Full
  Build**. A forced manual rebuild after step 03 on 2026-09-29 did not stack system junctions
  (the counts were identical). The earlier doubling (16,334 junctions and 37,728 edges) was seen
  with plain builds, and its cause is unconfirmed. Whether the scripted `BuildNetwork` call
  forces a full build is also unconfirmed.

## Troubleshooting

### Step 06 or `test_template_create.py`: `ERROR 030386` about VBScript evaluators in ArcGIS Pro 3.5.8

> Step 03 used to create and build a preliminary network, so this error surfaced there. Since 2026-09-29 step 03 only copies sources, and the network is first created in step 06 (or in `test_template_create.py`). The account below is written around the old step 03.

> **Resolved 2026-09-29: check the deployed template first.** The 2026-09-29 failure was a
> stale copy of `network_template.xml` on the T: drive (dated 2026-07-14, still VBScript
> `Select Case`, no `Language` key). After copying the committed template over it,
> the old step 03 (now `03_copy_sources.py`) created the network in about 13 seconds and built it in about 9 with
> 0 errors (Edges 37,674, Junctions 16,187, Turns 0). The committed template therefore works
> under Pro 3.5.8, and steps 03 and 06 no longer need the interactive procedure. Script 03
> now says so in its error text when the deployed template contains `Select Case`. Everything
> below is the fallback, and the 2026-09-18 account of it is kept for history.

This is a confirmed issue for this workflow, not a PyCharm or Python-launcher
problem. On September 18, 2026, step 03 successfully copied all three source
feature classes and then ArcGIS Pro 3.5.8 rejected
`CreateNetworkDatasetFromTemplate` with:

```text
ERROR 030386: Cannot create a network dataset from a template that uses Field
Script or Element Script evaluators configured with the VBScript language.
```

ArcGIS Pro 3.4 and later no longer allow creation from a template containing
VBScript Field Script or Element Script evaluators. There is an additional
trap in this repository: `Language = Python` text alone in a template's
scripted `Length`/`OneWay` assignments is not proof the evaluator is
genuinely Python-backed -- both a broken, VBScript-rejected template and a
solve-tested, working one have carried the identical legacy Field Script
evaluator CLSID (`{68055FC4-37D5-4BD0-81A5-CD177A29759C}`) under
`Language = Python` (confirmed 2026-09-18, see `CLAUDE.md`'s "Recreating the
network dataset by hand" section). Changing only the `Language` value, or
grepping for this CLSID, does not reliably tell you whether a template will
hit `ERROR 030386` -- the only real test is running
`CreateNetworkDatasetFromTemplate` against it. `../../data/network_template.xml`
was re-exported and committed 2026-09-18 from a network that passed both the
one-way and prohibited-turn smoke tests, and separately confirmed (via a
disposable test network dataset) to clear evaluator validation. Full
create-and-build success was then observed end to end on 2026-09-29 (see the
note at the top of this section).

The script recognizes this error and prints this recovery direction in its
terminal and log output, and it now checks up front whether the deployed
template still contains VBScript. The interactive procedure below is only
needed if the committed template itself is ever rejected.

When this happens, **do not rerun step 02**: step 03 copies the edge, junction,
and raw turn sources before it attempts to create the network, so those fresh
copies should already be present. Confirm their counts, then create
`TRNLRS_street_network` interactively in ArcGIS Pro from the
`SDEADM.TRNLRS_network` feature dataset:

1. Add `TRNLRS_TRN_STREET` as the edge source,
   `TRNLRS_street_junction` as the junction source, and
   `TRNLRS_traffic_turn` as the turn source. Use endpoint connectivity and no
   elevation model. **The Elevation Model dropdown defaults to "Elevation
   fields", not "None"** -- confirmed 2026-09-18 -- change it explicitly or
   the network builds elevation-aware connectivity it isn't meant to have.
2. `Length` is auto-populated by the Create Network Dataset tool as a Python
   Field Script, `!Shape.STLength()!`, for both edge directions -- confirmed
   2026-09-18 against the currently committed `network_template.xml`. Verify
   it, don't retype it; a hand-typed `!Shape!` also works but no longer
   matches the validated template.
3. Configure `OneWay` as a Python Field Script calling
   `oneway_restricted(!STR_DIR!)`. Return `True` for `N`, `FDTO`, and `T` in
   the Along direction, and for `N`, `FOTD`, and `T` in the Against direction.
4. Configure `TrafficTurn` with the constant evaluators recorded in the
   template, and build with **Force Full Build** selected.
5. Configure Directions: Base Name &rarr; `STR_NAME`, Suffix Type &rarr;
   `STR_TYPE`, Full Name &rarr; `FULL_NAME` (Network Dataset Properties &rarr;
   Directions tab). **Not optional** -- the 2026-09-18 rebuild skipped this
   step, and the template exported from that network came out with no
   Directions configuration at all as a result (see `LESSONS_LEARNED.md`).
6. Treat missing-edge errors for the raw turn class and a turn count of zero as
   expected at this preliminary stage. Confirm the edge count, then continue
   with step 04.

After the network passes the later one-way and prohibited-turn solve tests,
export a new template with `arcpy.na.CreateTemplateFromNetworkDataset` and
compare it with the committed template. Do not treat a hand-edited
`Language = Python` value as proof that the evaluator was converted.

### `scripts\scripts\03_create_network_dataset.py` not found

That path means `config.py` is from the older folder layout: it treated
`qa_refresh`'s parent as `network_dataset` and then appended another `scripts`
folder. In the current layout, `qa_refresh` is already inside `scripts`.

Confirm that `config.py` contains:

```python
QA_REFRESH_DIR = Path(__file__).parent
CORE_SCRIPTS_DIR = QA_REFRESH_DIR.parent
NETWORK_DATASET_DIR = CORE_SCRIPTS_DIR.parent
```

Then rerun `00_confirm_sources.py`. Its first core-script lookup should be:

```text
T:\work\giss\monthly\202607jul\gallaga\network_dataset\scripts\03_create_network_dataset.py
```

There should be exactly one `scripts` component. The loader intentionally keeps
the mapped `T:` path in error messages instead of resolving it to the backing
file-server UNC path.

### `module 'datetime' has no attribute 'now'`

Update `01_backup_and_baseline.py` and confirm it imports the module with
`import datetime`, then calls `datetime.datetime.now()`. This explicit form
works consistently and avoids confusing the `datetime` module with its
same-named class.
