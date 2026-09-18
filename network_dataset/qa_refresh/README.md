# QA street-network refresh scripts

This folder contains the ordered entry points for refreshing the QA network
from Prod's current `SDEADM.TRNLRS_TRN_STREET_VW`. The implementation delegates
the complicated network creation, turn remapping, and verification logic to the
maintained scripts in `../scripts`; these files provide one clearly numbered QA
workflow without duplicating that logic.

Run every command from an **ArcGIS Pro Python** prompt opened in this directory.
Do not continue when a step fails.

| Order | Command | Purpose |
|---|---|---|
| 00 | `python 00_confirm_sources.py` | Read-only confirmation of the configured Prod input, QA target, live counts, and `MODDATE` ranges. |
| 01 | `python 01_backup_and_baseline.py` | Save a timestamped QA turn backup and a JSON baseline report. |
| 02 | `python 02_delete_network_sources.py` | Delete the network dataset first, then its three source classes. This is the first destructive step. Set `CONFIRM_DELETE_QA_NETWORK = True` in the script immediately before running it. |
| 03 | `python 03_initial_build.py` | Copy a fresh Prod edge snapshot into QA and attempt the preliminary build. Turn errors are expected if the network is created, but ArcGIS Pro 3.5.8 may stop first with `ERROR 030386`; see below. |
| 04 | `python 04_remap_turns.py` | Create `TRNLRS_traffic_turn_staging` against the fresh edge copy. |
| 05 | `python 05_verify_staging_turns.py` | Run the independent staging-turn verifier. Also complete the spatial review checklist before continuing. |
| 06 | `python 06_swap_and_final_build.py` | Swap the exact reviewed staging class and perform the one final build. Set `CONFIRM_REVIEWED_STAGING = True` in the script only after completing the review. |
| 07 | `python 07_verify_live_turns.py` | Re-run the independent verifier against the live turn class after the swap. |

After step 07, follow Phase 6 and Phase 7 in
`../docs/qa_network_refresh_runbook.html`: reapply SQL grants using
`../docs/network_dataset_sql_permissions.md`, inspect the current
`BuildErrors_<guid>.txt`, and perform the one-way and prohibited-turn smoke
tests. Those DBA and interactive route checks are intentionally not automated
here.

## Safety and configuration

- `config.py` holds the expected QA paths. Review it before every refresh.
- `_shared.py` verifies that scripts 03, 05, and the verifier still point at the
  same QA feature dataset before any delegated operation runs.
- Step 00 cannot prove historical provenance. It confirms current code paths
  and compares live metadata; spot-check known changed `FDMID` geometries in
  Prod and the QA network edge source.
- Step 01 writes the turn backup inside the QA network feature dataset and a
  baseline JSON file under `output/`. Copy the backup to independent storage if
  required by the change plan.
- Steps 02 and 06 use confirmation globals, which default to `False`, so they
  cannot be launched destructively by an accidental double-click. Review the
  applicable prerequisites, set the global at the top of the script to `True`,
  run the step without arguments, and reset the global to `False` afterward.
- Never manually click **Build Network** after steps 03 or 06.

## Troubleshooting

### Step 03: `ERROR 030386` about VBScript evaluators in ArcGIS Pro 3.5.8

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
trap in this repository: the committed `../data/network_template.xml` contains
`Language = Python` text, but its scripted `Length` and `OneWay` assignments
still carry the legacy Field Script evaluator CLSID
`{68055FC4-37D5-4BD0-81A5-CD177A29759C}`. ArcGIS therefore still identifies
the template as VBScript-backed. Changing only the `Language` values in the
XML is not a reliable conversion.

When this happens, **do not rerun step 02**: step 03 copies the edge, junction,
and raw turn sources before it attempts to create the network, so those fresh
copies should already be present. Confirm their counts, then create
`TRNLRS_street_network` interactively in ArcGIS Pro from the
`SDEADM.TRNLRS_network` feature dataset:

1. Add `TRNLRS_TRN_STREET` as the edge source,
   `TRNLRS_street_junction` as the junction source, and
   `TRNLRS_traffic_turn` as the turn source. Use endpoint connectivity and no
   elevation model.
2. Configure `Length` as a Python Field Script using `!Shape!` for both edge
   directions.
3. Configure `OneWay` as a Python Field Script calling
   `oneway_restricted(!STR_DIR!)`. Return `True` for `N`, `FDTO`, and `T` in
   the Along direction, and for `N`, `FOTD`, and `T` in the Against direction.
4. Configure `TrafficTurn` with the constant evaluators recorded in the
   template, and build with **Force Full Build** selected.
5. Treat missing-edge errors for the raw turn class and a turn count of zero as
   expected at this preliminary stage. Confirm the edge count, then continue
   with step 04.

After the network passes the later one-way and prohibited-turn solve tests,
export a new template with `arcpy.na.CreateTemplateFromNetworkDataset` and
compare it with the committed template. Do not treat a hand-edited
`Language = Python` value as proof that the evaluator was converted.
