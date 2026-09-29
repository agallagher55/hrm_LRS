# network_dataset/scripts

| Folder or file | What it is |
|---|---|
| `01_extract_network_config.py`, `02_compare_schemas.py` | One-off extraction and schema comparison from the original migration. History. |
| `03_create_network_dataset.py` | Copies the edge, junction and turn sources into `SDEADM.TRNLRS_network`, then creates and builds the network from `data/network_template.xml`. Takes a copy-only mode. |
| `04_sync_and_rebuild_network.py` | Prod steady state: reload the edge copy after an LRS refresh (through `network_exclusions.py`) and rebuild. Called from `scripts/LRS_updates.py`. |
| `05_rebuild_traffic_turns.py`, `verify_turn_rebuild.py` | Remap turn edge references onto the current edge copy, and independently verify the result. |
| `06_migrate_network_fd.py` | Dev pilot that moves the network sources into `SDEADM.TRNLRS_network`. Written, never run on QA or Prod. |
| `run_full_network_rebuild.py` | Orchestrator: swap the reviewed turn class, recreate the network, build once. |
| `network_definitions.py` | The two networks (`DISTANCE`, `HRFE`) and every name that differs between them. The `HRM_NETWORK` environment variable picks the one a run works on; unset means `DISTANCE`. Renders the HRFE template from the committed one. See `../docs/hrfe_network_runbook.md`. |
| `network_exclusions.py`, `log_utils.py` | Shared helpers: which streets are left out of each network (profiles `GENERAL` and `HRFE`; run the file to print their clauses), and logging. |
| `tests/` | Unit tests for `network_exclusions.py` and `network_definitions.py`, no ArcGIS needed. From this folder: `python -m unittest discover -s tests -v`. |
| `qa_refresh/` | The ordered QA refresh workflow. Start with its `README.md`. |
| `diagnostics/` | Read-only investigation scripts from the turn-rebuild work, plus `10_find_candidate_exclusions.py` for choosing exclusion filters. CSV outputs are written to the current directory. |
| `archive/` | Finished one-offs kept for the record. Do not run. |
