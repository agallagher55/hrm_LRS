# HRM Linear Referencing System (LRS)

This repository holds all data, scripts, and documentation related to the **Halifax Regional Municipality (HRM) Linear Referencing System**.

## What is a Linear Referencing System?

A Linear Referencing System (LRS) is a method of storing and locating geospatial data relative to a measured position along a linear feature (e.g., a road, route, or network). Instead of using X/Y coordinates, locations are described using a route identifier and a measure value (e.g., kilometre point).

## Repository Structure

```
hrm_LRS/
├── scripts/                 # LRS refresh pipeline (LRS_updates.py)
├── tests/                   # Data validation and regression tests
└── network_dataset/         # Creating and maintaining the LRS network dataset
    ├── scripts/              # Build, sync, and turn-rebuild scripts
    ├── data/                 # Extracted config, XML template, schema diffs
    ├── docs/                 # Migration plan, build status, runbooks
    └── intermediate_results/ # Diagnostic CSVs from the turn rebuild
```

> Structure will evolve as the project develops.

## Getting Started

See [CLAUDE.md](CLAUDE.md) for development guidelines and project context.

## Contact

Halifax Regional Municipality — GIS / Asset Management Team
