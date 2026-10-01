# Building the HRFE network in QA

Written 2026-09-29. **None of this has been run.** The scripts were changed and tested without
ArcGIS Pro or SQL Server, so expect the first real run to turn something up. The distance
network's paths were checked to be identical to before; only the HRFE side is new.

The HRFE network is a second network dataset, `TRNLRS_street_network_HRFE`, in its own feature
dataset, `SDEADM.TRNLRS_network_HRFE`. It is built from the same LRS street data as the
distance network, minus the HRFE exclusions, with the same turn restrictions. Decisions
behind it (2026-09-29, Alex): a second network dataset in its own feature dataset; the same
turn restrictions as the distance network; Robbie Evans edits the extra roads himself in QA.

## What differs from the distance network

| | Distance | HRFE |
|---|---|---|
| Feature dataset | `SDEADM.TRNLRS_network` | `SDEADM.TRNLRS_network_HRFE` |
| Network dataset | `TRNLRS_street_network` | `TRNLRS_street_network_HRFE` |
| Edge copy | `TRNLRS_TRN_STREET` | `TRNLRS_TRN_STREET_HRFE` |
| Junctions | `TRNLRS_street_junction` | `TRNLRS_street_junction_HRFE` |
| Turns (live / staging) | `TRNLRS_traffic_turn` / `..._staging` | `TRNLRS_traffic_turn_HRFE` / `..._staging_HRFE` |
| Exclusion profile | `GENERAL`: WA, transit access, islands | `HRFE`: `GENERAL` plus emergency access roads and ETAs |
| Expected edge copy | 18,459 of 18,644 (WA 61 and transit 124 out) | 18,433 (those plus emergency access 4 and ETAs 22, 211 in all) |

The suffix is there because SDE needs feature class names to be unique across the whole
geodatabase. The template is not kept twice: `network_definitions.py` renders the HRFE one from
the committed template, so the two cannot drift apart. The rendered copy is written to
`data/generated/` and is not committed.

Everything else is shared: the Prod `TRNLRS_TRN_STREET_VW` edge input, the legacy junction and
turn sources, and the turn remap. **The same legacy turns are remapped onto the HRFE edge copy**,
which is how the two networks end up with the same restrictions. Turns on excluded edges
(ETAs, transit roads and so on) are skipped by the remap, so the skipped count may be higher than
the distance network's 49 (the excluded WA edges carried no turns, but the others are unchecked).

## Choosing the network

Every script picks its network from the `HRM_NETWORK` environment variable, read when the
script starts. Unset means `DISTANCE`, so nothing changes for the existing workflow.

```bat
set HRM_NETWORK=HRFE
```

Set it in the same prompt (or PyCharm run configuration) for every step, and check the
`Network: HRFE ...` line each step prints. Write it exactly as above, with no spaces around the `=`:
`set HRM_NETWORK = HRFE` makes a variable whose name ends in a space, and the scripts stop with an error
rather than quietly working on the distance network.

Unset means every path and name is the same as before the HRFE work. The distance network's
*exclusions* did change, though: it now drops the transit access roads as well as WA, from its next
rebuild. That includes the Prod edge sync, which uses the distance network (Prod has no network
dataset yet, so nothing there is affected today).

The two destructive steps need the network named in the script as well as in the environment:
set `NETWORK_TO_DELETE` in `02_delete_network_sources.py` and `NETWORK_TO_BUILD` in
`06_swap_and_final_build.py` to `"HRFE"` for an HRFE run (they default to `"DISTANCE"`). A mismatch
stops the step before it changes anything. Step 02 also only trusts a step 01 baseline written for
the same network, since both networks write to the same `output` folder. `python network_definitions.py` lists both
definitions and which one is active. An unknown value stops the run.

The Prod edge sync (`04_sync_and_rebuild_network.py`, called by `LRS_updates.py`) ignores the
variable on purpose and only ever syncs the distance network. There is no Prod HRFE network.

## Steps

Run from an ArcGIS Pro Python prompt in `network_dataset\scripts\qa_refresh`, with
`HRM_NETWORK=HRFE` set. Stop at the first failure.

0. **Create the feature dataset** `SDEADM.TRNLRS_network_HRFE` in QA, in Pro, with the same
   spatial reference as `SDEADM.TRNLRS_network`. Script 03 refuses to run without it.
1. **Deploy the current scripts and template** to the T: drive, and compare sizes or hashes with
   the repo first. Stale copies cost time on 2026-09-29. `network_definitions.py` is a new file
   that scripts 03, 05 and the verifier now import, so it has to be deployed too.
2. **Prove the rendered template** without touching QA: `python test_template_create.py`. With
   `HRM_NETWORK=HRFE` it copies the distance sources into a scratch geodatabase under the HRFE
   names and builds the HRFE template there. It has not been run for either network yet.
   It cannot show two things, because the scratch geodatabase is empty of other networks:
   whether SDE accepts the rendered template's leftover `<DSID>` (copied from the distance
   network's export) alongside the existing distance network, and whether the catalog path in
   the template matters to the create. Both were fine for the distance network, which is
   recreated from the same template; neither is proven for a second network in the same database.
3. `python 00_confirm_sources.py`: prints the paths and the Prod input. The HRFE sources show
   as MISSING at this point, which is expected.
4. **Skip steps 01 and 02.** They back up and delete an existing network, and the HRFE one does
   not exist yet.
5. `python 03_copy_sources.py`: copies the edge input from Prod through the `HRFE` exclusions, and
   the junction and raw turn classes from QA's legacy classes. Check the log:
   `Edge exclusions applied (profile HRFE): 18,433 of 18,644 kept, 211 excluded`, with a row
   count for each rule: WA 61, transit 124, emergency access 4, ETAs 22, and no
   "matched no rows" warning. A different count means a filter is wrong or the data has moved.
6. `python 04_remap_turns.py`, then `python 05_verify_staging_turns.py`, then the spatial review
   checklist (`traffic_turn_staging_review_checklist.txt`).
7. Set `CONFIRM_REVIEWED_STAGING = True` and `NETWORK_TO_BUILD = "HRFE"` in
   `06_swap_and_final_build.py`, then run it. It
   creates `TRNLRS_street_network_HRFE` from the rendered template and builds it once.
8. `python 07_verify_live_turns.py`.
9. **SQL grants.** The new network has its own registration IDs (`N_<id>` and `ND_<id>`), so the
   distance network's grants do not cover it. Follow `network_dataset_sql_permissions.md` for
   the new IDs, and check all the HRFE source tables, including
   `TRNLRS_street_network_HRFE_Junctions`.
10. **Smoke tests**, as for the distance network: add the network to a map from a non-admin login,
    then a one-way street and a prohibited turn, with the travel mode's restrictions ticked.
    Check by eye that the removed roads (water and transit access, emergency access, ETAs) are gone.

After an LRS update the HRFE edge copy goes stale like the distance one, and nothing syncs it
automatically: the Prod sync (`04`, called by `LRS_updates.py`) only reloads the distance edge copy. In QA, rerun steps 3 to
8 (the copy skips a class that already exists, so delete the old sources first, as step 02 does
for the distance network). There is no Prod HRFE network yet.

## Robbie's extra roads (the Station 2 segment has arrived, nothing is loaded)

What Robbie said on 2026-10-01 (record: `meetings/2026-09-29_HRFE_network_dataset_email_thread.md`):

- **The bridge is dropped.** He will block it himself with a point barrier at solve time, so the
  network needs no break there and Alex needs no barrier class.
- **Station 2:** a tiny segment, now in `monthly\202610oct\evansr\Network_Segments_For_Alex\Network_Segments.gdb`.
  It has not been inspected yet.
- **Driveways and the routes outside HRM:** he will add them to the same layer as the Station 2
  segment (an interpretation of "these segments").
- **Splits:** he agreed that split points live in their own layer and are re-applied after each
  LRS update.

Inspected on 2026-10-01 (details in the thread record): one class, `Segments`, 8 polylines, same
spatial reference as the streets, all four network fields present. **Seven of its ends lie
exactly on a street but not at a street end**, so under End Point connectivity none of them
connects until the street is split there: both ends of the 22 m Station 2 connector (University Ave,
two different street segments) and one end each of OIDs 3, 4, 5, 6 and 9 (Ketch Harbour Rd, Church St,
Highway 224, Old Guysborough Rd, Highway 2). OIDs 7 and 8 meet no street within 25 m.

The plan:

1. **Split the streets where the extra roads meet them.** Not written yet. The design: derive the
   split points from the extra roads on every rebuild (every end that lies mid-street, and every
   place a road crosses a street away from its ends) rather than keep a hand-edited layer, so Robbie
   never maintains split points and an LRS update cannot lose them. Run the split on the HRFE edge
   copy as it is loaded, with `SplitLineAtPoint`, before the network is created. Script 11 already
   finds these points and writes them to `extra_roads_split_points.csv`. Robbie agreed to the
   splits approach on 2026-10-01. Things to check on the first real run: that the turn remap still
   matches (it matches by edge end points, not FDMID, so duplicated FDMIDs should not matter, but
   it is unproven), and that a split exactly at an intersection does not create a duplicate edge.
2. Alex creates a feature class in `SDEADM.TRNLRS_network_HRFE` from what Robbie sends, with the
   same spatial reference as the feature dataset, then Robbie edits it himself in QA. Its rows
   survive LRS updates because the edge sync only reloads the LRS edge copy. If he moves a road, the
   derived splits follow on the next rebuild.
3. It becomes a second edge source in the template. The evaluators read only `STR_DIR`, and
   Directions needs `STR_NAME`, `STR_TYPE` and `FULL_NAME`, so the schema can be small.
4. Robbie's edit access is granted per table, following "Write access for editor roles" in
   `network_dataset_sql_permissions.md`.

Open before that can be built:

1. **Splits** (see the plan above). Confirmed needed. Alternatives rejected: setting the streets
   to Any Vertex connectivity would connect every crossing pair of streets that shares a vertex,
   including grade-separated ones, and End Point was chosen deliberately.
2. **Who rebuilds.** An edit to a network source only reaches routes after a build. Decide whether
   Robbie or Alex builds, and how often.
3. **Versioning.** Check whether the extra roads class has to be registered as versioned for
   Robbie to edit it, and what that does to the build. The existing sources are never edited by hand.
4. **Weak bridges on the routes outside HRM.** His point barrier covers "that bridge"; whether the
   others on outside routes are handled the same way is unanswered.
5. **Datum.** If his geodatabase and the streets use different datums, check the transformation
   before trusting any connectivity result.
