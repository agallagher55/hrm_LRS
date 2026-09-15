# HRM Linear Referencing System (LRS)

This repository holds all data, scripts, and documentation related to the **Halifax Regional Municipality (HRM) Linear Referencing System**.

## What is a Linear Referencing System?

A Linear Referencing System (LRS) is a method of storing and locating geospatial data relative to a measured position along a linear feature (e.g., a road, route, or network). Instead of using X/Y coordinates, locations are described using a route identifier and a measure value (e.g., kilometre point).

## Repository Structure

```
hrm_LRS/
├── scripts/                 # LRS refresh pipeline (LRS_updates.py)
└── network_dataset/         # Creating and maintaining the LRS network dataset
    ├── scripts/              # Build, sync, and turn-rebuild scripts
    ├── data/                 # Extracted config, XML template, schema diffs
    ├── docs/                 # Migration plan, build status, runbooks, roadmap
    │   └── meetings/         # "Road Network Check In" transcripts
    └── intermediate_results/ # Diagnostic CSVs from the turn rebuild
```

> Structure will evolve as the project develops. A `tests/` directory was advertised here
> previously but has never existed: there is currently **no automated regression coverage** of
> the LRS refresh or the network build. That gap is tracked in the roadmap.

## Where to start

| If you want | Read |
|---|---|
| The current picture, visually | [`network_dataset/docs/roadmap_lrs_network.html`](network_dataset/docs/roadmap_lrs_network.html) |
| A stakeholder-facing status summary | [`network_dataset/docs/street_network_meeting_overview.md`](network_dataset/docs/street_network_meeting_overview.md) |
| Detailed build status and open items | [`network_dataset/docs/network_build_status.md`](network_dataset/docs/network_build_status.md) |
| How to refresh the network in QA | [`network_dataset/docs/qa_network_refresh_runbook.html`](network_dataset/docs/qa_network_refresh_runbook.html) ([shareable version](https://claude.ai/artifact/T5J6zb7B8UUqa61Ns93v4P)) |
| The junction-network workflow and every error hit building it | [`network_dataset/docs/junction_network_workflow_esri_case.html`](network_dataset/docs/junction_network_workflow_esri_case.html) ([shareable version](https://claude.ai/artifact/NP2uxjdLuuRJr8uCzNJwgf)) |
| Architecture and phase-by-phase history | [`network_dataset/docs/network_dataset_migration_plan.md`](network_dataset/docs/network_dataset_migration_plan.md) |
| Known script defects and their diagnoses | [`network_dataset/docs/network_dataset_script_review.md`](network_dataset/docs/network_dataset_script_review.md) |

## Getting Started

See [CLAUDE.md](CLAUDE.md) for development guidelines and project context, including the arcpy
and enterprise-geodatabase gotchas this project has hit and confirmed.

## Contact

Halifax Regional Municipality — GIS / Asset Management Team
