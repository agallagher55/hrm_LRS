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

| Order | Command | Purpose |
|---|---|---|
| 00 | `python 00_confirm_sources.py` | Read-only confirmation of the configured Prod input, QA target, live counts, and `MODDATE` ranges. |
| 01 | `python 01_backup_and_baseline.py` | Save a timestamped QA turn backup and a JSON baseline report. |
| 02 | `python 02_delete_network_sources.py --confirm-delete-qa-network` | Delete the network dataset first, then its three source classes. This is the first destructive step. |
| 03 | `python 03_initial_build.py` | Copy a fresh Prod edge snapshot into QA and perform the expected preliminary build. Turn errors are expected in this build. |
| 04 | `python 04_remap_turns.py` | Create `TRNLRS_traffic_turn_staging` against the fresh edge copy. |
| 05 | `python 05_verify_staging_turns.py` | Run the independent staging-turn verifier. Also complete the spatial review checklist before continuing. |
| 06 | `python 06_swap_and_final_build.py --confirm-reviewed-staging` | Swap the exact reviewed staging class and perform the one final build. |
| 07 | `python 07_verify_live_turns.py` | Re-run the independent verifier against the live turn class after the swap. |

After step 07, follow Phase 6 and Phase 7 in
`../../docs/qa_network_refresh_runbook.html`: reapply SQL grants using
`../../docs/network_dataset_sql_permissions.md`, inspect the current
`BuildErrors_<guid>.txt`, and perform the one-way and prohibited-turn smoke
tests. Those DBA and interactive route checks are intentionally not automated
here.

## Safety and configuration

- `config.py` derives the repository folders from its own mapped `T:` path and
  holds the expected QA paths. Review it before every refresh. It deliberately
  avoids `Path.resolve()`, which would replace `T:` with the backing server name.
- `_shared.py` verifies that scripts 03, 05, and the verifier still point at the
  same QA feature dataset before any delegated operation runs.
- Step 00 cannot prove historical provenance. It confirms current code paths
  and compares live metadata; spot-check known changed `FDMID` geometries in
  Prod and the QA network edge source.
- Step 01 writes the turn backup inside the QA network feature dataset and a
  baseline JSON file under `output/`. Copy the backup to independent storage if
  required by the change plan.
- Steps 02 and 06 require explicit command-line confirmation flags so they
  cannot be launched destructively by an accidental double-click.
- Never manually click **Build Network** after steps 03 or 06.

## Troubleshooting

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
