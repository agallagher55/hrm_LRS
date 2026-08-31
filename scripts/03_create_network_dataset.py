"""
Create the new TRN_street_network (LRS-based) from the modified XML template.

Prerequisites (run in order):
  1. scripts/01_extract_network_config.py  → data/network_template.xml
  2. scripts/02_compare_schemas.py         → data/evaluator_field_map.json
  3. Manually edit data/network_template.xml:
       - Replace all references to SDEADM.TRN_street with the new edge source name
       - Update any evaluator fieldName values flagged as ACTION REQUIRED
       - Confirm junction source name (TRN_street_junction → new junction FC if renamed)
       - Confirm turn source name (TRN_traffic_turn → TRNLRS_traffic_turn)
     See docs/network_dataset_migration_plan.md for the full XML editing checklist.

Note on TRNLRS_TRN_STREET_VW / TRNLRS_TRN_STREET:
  TRNLRS_TRN_STREET_VW is created by LRS_updates.py as a standalone SDE feature
  class (not inside a feature dataset), and it only exists in prod. Network
  datasets require all sources to live inside the target feature dataset, so
  this script always reads the standalone FC from PROD_SDE_CONNECTION and
  copies it into SDEADM.TRNLRS_network (in whichever environment
  SDE_CONNECTION_UPDATE points at) under the name TRNLRS_TRN_STREET (without
  _VW) to avoid an SDE name-uniqueness conflict.  The FD copy is what the
  network dataset references; the standalone _VW FC in prod remains the
  authoritative source updated by LRS_updates.py. After each LRS refresh,
  re-copy the standalone FC over the FD copy and rebuild (see
  scripts/04_sync_and_rebuild_network.py).

  SDEADM.TRNLRS_network is a dedicated feature dataset for the network source
  FCs (TRNLRS_TRN_STREET, TRNLRS_street_junction, TRNLRS_traffic_turn),
  separate from SDEADM.TRNLRS (the LRS feature dataset holding LRSN_Route and
  the E_* event tables). It must already exist -- this script verifies its
  presence but does not create it.

Note on TRNLRS_traffic_turn:
  copy_fc_to_fd() below skips copying a source FC if the destination already
  exists in the feature dataset. If TRNLRS_traffic_turn has previously been
  remapped and swapped in by scripts/05_rebuild_traffic_turns.py, re-running
  this script will correctly leave that remapped FC alone. But if the network
  dataset (and its FD contents) is ever deleted and recreated, this script
  will re-copy the raw, unremapped TRN_traffic_turn and silently undo the
  remap -- watch the log for "Copying into feature dataset" vs "Already
  present, skipping" on the turn FC specifically.

Run from ArcGIS Pro Python environment:
  > python scripts/03_create_network_dataset.py
"""

import os
import sys
from pathlib import Path

import arcpy

from log_utils import setup_logger

logger = setup_logger("03_create_network_dataset")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Environment that will receive the new network dataset (and the FD copies of
# the edge/junction/turn sources it needs).
# QA: active. scripts/05_rebuild_traffic_turns.py must point at the SAME
# environment -- run_full_network_rebuild.py asserts that before it does
# anything, since it takes the turn/edge paths from 05 and the feature dataset
# from here, and a mismatch would remap turns in one environment and build the
# network dataset in another.
SDE_CONNECTION_UPDATE = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"
# Dev: uncomment to point this script at Dev instead of QA (and change SDE in
# 05_rebuild_traffic_turns.py to match).
# SDE_CONNECTION_UPDATE = r"E:\HRM\Scripts\SDE\SQL\Dev\dev_RW_sdeadm.sde"

# Prod is always the read source for the edge FC: TRNLRS_TRN_STREET_VW (the
# authoritative standalone FC refreshed by LRS_updates.py) only exists in prod,
# so this script pulls from here regardless of which environment
# SDE_CONNECTION_UPDATE points at above.
PROD_SDE_CONNECTION = r"E:\HRM\Scripts\SDE\SQL\Prod\prod_RW_sdeadm.sde"

# Feature dataset that will contain the new network dataset. This is a
# dedicated feature dataset for the network source FCs, separate from
# SDEADM.TRNLRS (the LRS feature dataset holding LRSN_Route, event tables,
# etc.). Network datasets must live inside a feature dataset in a geodatabase.
FEATURE_DATASET = os.path.join(SDE_CONNECTION_UPDATE, "SDEADM.TRNLRS_network")
NEW_ND_NAME     = "TRNLRS_street_network"

# TRNLRS_TRN_STREET_VW is the authoritative standalone FC (outside any feature
# dataset), populated by LRS_updates.py, and it only exists in prod.  It must
# be copied into FEATURE_DATASET before the network dataset can be created.
# SDE enforces unique FC names across the entire geodatabase, so the copy is
# stored under a different name (TRNLRS_TRN_STREET, without the _VW suffix)
# to avoid a name collision.  The XML template uses TRNLRS_TRN_STREET as the
# edge source name accordingly.
STANDALONE_EDGE_SOURCE = os.path.join(PROD_SDE_CONNECTION, "SDEADM.TRNLRS_TRN_STREET_VW")
EDGE_SOURCE_NAME       = "TRNLRS_TRN_STREET"

# Junction and turn FCs live in TRN_streets_routes (the old network FD), in the
# same environment as SDE_CONNECTION_UPDATE. This script copies them into
# FEATURE_DATASET automatically if not already present.
SOURCE_JUNCTION = os.path.join(SDE_CONNECTION_UPDATE, "SDEADM.TRN_streets_routes", "SDEADM.TRN_street_junction")
SOURCE_TURN     = os.path.join(SDE_CONNECTION_UPDATE, "SDEADM.TRN_streets_routes", "SDEADM.TRN_traffic_turn")

REPO_ROOT    = Path(__file__).resolve().parents[1]
TEMPLATE_XML = REPO_ROOT / "data" / "network_template.xml"
# ---------------------------------------------------------------------------


def copy_fc_to_fd(source_path, feature_dataset, fc_name, error_hint=""):
    """Copy a feature class into the feature dataset, skipping if already present."""
    dest = os.path.join(feature_dataset, fc_name)
    if arcpy.Exists(dest):
        logger.info(
            f"Already present in feature dataset, skipping copy: {fc_name} "
            f"(existing data at {dest} was NOT refreshed)"
        )
        return
    if not arcpy.Exists(source_path):
        msg = f"Source feature class not found: {source_path}" + (f" {error_hint}" if error_hint else "")
        logger.error(msg)
        sys.exit(f"ERROR: {msg}")
    logger.info(f"Copying into feature dataset: {source_path} -> {dest}")
    arcpy.management.CopyFeatures(source_path, dest)
    logger.info(f"Copy complete: {fc_name}")


def build_network(nd_path):
    """Build the network dataset after creation, and log the geoprocessing messages."""
    logger.info(f"Building network dataset: {nd_path}")
    arcpy.na.BuildNetwork(nd_path)
    logger.info("Build complete.")

    message_count = arcpy.GetMessageCount()
    severity_counts = {0: 0, 1: 0, 2: 0}  # 0=info, 1=warning, 2=error
    for i in range(message_count):
        severity = arcpy.GetSeverity(i)
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
    logger.info(
        f"BuildNetwork messages: {message_count} total "
        f"({severity_counts.get(2, 0)} errors, {severity_counts.get(1, 0)} warnings) "
        "-- full detail in the log file"
    )
    logger.debug(f"BuildNetwork full messages:\n{arcpy.GetMessages()}")


def main():
    if not TEMPLATE_XML.exists():
        msg = (
            f"Template XML not found at {TEMPLATE_XML}. "
            "Run 01_extract_network_config.py and edit the template before proceeding."
        )
        logger.error(msg)
        sys.exit(f"ERROR: {msg}")

    if not arcpy.Exists(FEATURE_DATASET):
        msg = f"Feature dataset not found: {FEATURE_DATASET}. Update FEATURE_DATASET to the correct path."
        logger.error(msg)
        sys.exit(f"ERROR: {msg}")

    copy_fc_to_fd(
        STANDALONE_EDGE_SOURCE, FEATURE_DATASET, EDGE_SOURCE_NAME,
        error_hint="Run LRS_updates.py to populate TRNLRS_TRN_STREET_VW before proceeding.",
    )
    copy_fc_to_fd(SOURCE_JUNCTION, FEATURE_DATASET, "TRNLRS_street_junction")
    copy_fc_to_fd(SOURCE_TURN, FEATURE_DATASET, "TRNLRS_traffic_turn")

    new_nd_path = os.path.join(FEATURE_DATASET, NEW_ND_NAME)

    logger.info(f"Creating network dataset from template: {TEMPLATE_XML}")
    try:
        arcpy.na.CreateNetworkDatasetFromTemplate(
            network_dataset_template=str(TEMPLATE_XML),
            output_feature_dataset=FEATURE_DATASET,
        )
    except arcpy.ExecuteError:
        msgs = arcpy.GetMessages()
        if "already exists" in msgs:
            msg = (
                f"Network dataset already exists: {new_nd_path}. "
                "Delete it in ArcGIS Pro (Catalog pane → right-click → Delete) and re-run."
            )
            logger.error(msg)
            sys.exit(f"ERROR: {msg}")
        logger.error(f"CreateNetworkDatasetFromTemplate failed:\n{msgs}")
        sys.exit(f"ERROR: CreateNetworkDatasetFromTemplate failed:\n{msgs}")
    logger.info(f"Network dataset created: {new_nd_path}")

    build_network(new_nd_path)
    logger.info(
        "Done. Validate the new network dataset by: "
        "1) Opening Network Dataset Properties in ArcGIS Pro and reviewing each tab. "
        "2) Running a test Route solve between two known points. "
        "3) Running a test Service Area solve. "
        "4) Comparing results against the old TRN_street_network."
    )


if __name__ == "__main__":
    main()
