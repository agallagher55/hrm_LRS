"""
Create the new TRN_street_network (LRS-based) from the modified XML template.

Prerequisites:
  - network_dataset/data/network_template.xml is committed and already edited for the
    TRNLRS_* sources (Python evaluators, no VBScript). The deployed copy must match the
    repo copy: this script stops early if it still contains VBScript ('Select Case').
    The original extraction steps (01_extract_network_config.py, 02_compare_schemas.py and
    the manual XML edits in network_dataset_migration_plan.md) are history.
  - For a QA rebuild, run this through network_dataset/scripts/qa_refresh (see its README).

Note on TRNLRS_TRN_STREET_VW / TRNLRS_TRN_STREET:
  TRNLRS_TRN_STREET_VW is created by LRS_updates.py as a standalone SDE feature
  class (not inside a feature dataset). Prod's copy is authoritative -- it is
  fed by prod's LRSN_Route/event tables and is what this script always reads
  from. A same-named standalone FC also exists in QA (confirmed via Pro
  Catalog 2026-09-16) -- QA is a one-to-one mirror of prod without scheduled
  updates, so LRS_updates.py gets run there manually and QA's copy's currency
  is never guaranteed. Nothing in this script or the wider network build
  reads from it -- PROD_SDE_CONNECTION below is hardcoded regardless of which
  environment SDE_CONNECTION_UPDATE targets, specifically so QA/Dev's copy
  (whatever its current staleness) is never accidentally used as the source.
  Network datasets require all sources to live inside the target feature
  dataset, so
  this script always reads the standalone FC from PROD_SDE_CONNECTION and
  copies it into SDEADM.TRNLRS_network (in whichever environment
  SDE_CONNECTION_UPDATE points at) under the name TRNLRS_TRN_STREET (without
  _VW) to avoid an SDE name-uniqueness conflict.  The FD copy is what the
  network dataset references; the standalone _VW FC in prod remains the
  authoritative source updated by LRS_updates.py. After each LRS refresh,
  re-copy the standalone FC over the FD copy and rebuild (see
  network_dataset/scripts/04_sync_and_rebuild_network.py).

  SDEADM.TRNLRS_network is a dedicated feature dataset for the network source
  FCs (TRNLRS_TRN_STREET, TRNLRS_street_junction, TRNLRS_traffic_turn),
  separate from SDEADM.TRNLRS (the LRS feature dataset holding LRSN_Route and
  the E_* event tables). It must already exist -- this script verifies its
  presence but does not create it.

Note on edge exclusions:
  The edge copy (TRNLRS_TRN_STREET) is loaded through network_exclusions.py,
  which drops the streets in its GENERAL profile: WA (water access) streets,
  transit access roads and any listed island FDMIDs. The authoritative
  TRNLRS_TRN_STREET_VW is not filtered, so the row count of the copy is expected
  to be lower than the source's. See network_exclusions.py.

Note on TRNLRS_traffic_turn:
  copy_fc_to_fd() below skips copying a source FC if the destination already
  exists in the feature dataset. If TRNLRS_traffic_turn has previously been
  remapped and swapped in by network_dataset/scripts/05_rebuild_traffic_turns.py, re-running
  this script will correctly leave that remapped FC alone. But if the network
  dataset (and its FD contents) is ever deleted and recreated, this script
  will re-copy the raw, unremapped TRN_traffic_turn and silently undo the
  remap -- watch the log for "Copying into feature dataset" vs "Already
  present, skipping" on the turn FC specifically.

Run from ArcGIS Pro Python environment:
  > python network_dataset/scripts/03_create_network_dataset.py
"""

import os
import sys
from pathlib import Path

import arcpy

import network_exclusions
from log_utils import setup_logger

logger = setup_logger("03_create_network_dataset")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Environment that will receive the new network dataset (and the FD copies of
# the edge/junction/turn sources it needs).
# QA: active. network_dataset/scripts/05_rebuild_traffic_turns.py must point at the SAME
# environment -- run_full_network_rebuild.py asserts that before it does
# anything, since it takes the turn/edge paths from 05 and the feature dataset
# from here, and a mismatch would remap turns in one environment and build the
# network dataset in another.
SDE_CONNECTION_UPDATE = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"
# Dev: uncomment to point this script at Dev instead of QA (and change SDE in
# 05_rebuild_traffic_turns.py to match).
# SDE_CONNECTION_UPDATE = r"E:\HRM\Scripts\SDE\SQL\Dev\dev_RW_sdeadm.sde"

# Prod is always the read source for the edge FC: TRNLRS_TRN_STREET_VW's
# Prod copy is the authoritative one, refreshed by LRS_updates.py from prod's
# own LRS tables. A copy of the same name also exists in QA (confirmed via
# Pro Catalog 2026-09-16) -- unconfirmed whether it is fresh, and not read by
# this script or any other tracked script. This script pulls from Prod
# regardless of which environment SDE_CONNECTION_UPDATE points at above, so a
# stale or divergent QA/Dev copy is never accidentally used instead.
PROD_SDE_CONNECTION = r"E:\HRM\Scripts\SDE\SQL\Prod\prod_RW_sdeadm.sde"

# Feature dataset that will contain the new network dataset. This is a
# dedicated feature dataset for the network source FCs, separate from
# SDEADM.TRNLRS (the LRS feature dataset holding LRSN_Route, event tables,
# etc.). Network datasets must live inside a feature dataset in a geodatabase.
FEATURE_DATASET = os.path.join(SDE_CONNECTION_UPDATE, "SDEADM.TRNLRS_network")
NEW_ND_NAME     = "TRNLRS_street_network"

# TRNLRS_TRN_STREET_VW is the authoritative standalone FC (outside any feature
# dataset) in Prod, populated by LRS_updates.py from prod's own LRS tables.
# (A same-named FC also exists in QA -- see the note above; it is not this
# constant's source and is not read anywhere in this script.)  It must
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


def copy_fc_to_fd(source_path, feature_dataset, fc_name, error_hint="", apply_exclusions=False):
    """
    Copy a feature class into the feature dataset, skipping if already present.

    apply_exclusions loads only the edges that network_exclusions.py keeps. Use it
    for the edge source only.
    """
    dest = os.path.join(feature_dataset, fc_name)
    if arcpy.Exists(dest):
        logger.info(
            f"Already present in feature dataset, skipping copy: {fc_name} "
            f"(existing data at {dest} was NOT refreshed)"
        )
        if apply_exclusions:
            network_exclusions.count_excluded(dest, logger)
        return
    if not arcpy.Exists(source_path):
        msg = f"Source feature class not found: {source_path}" + (f" {error_hint}" if error_hint else "")
        logger.error(msg)
        sys.exit(f"ERROR: {msg}")
    logger.info(f"Copying into feature dataset: {source_path} -> {dest}")
    if apply_exclusions:
        source = network_exclusions.make_filtered_layer(source_path, f"{fc_name}_keep", logger)
    else:
        source = source_path
    arcpy.management.CopyFeatures(source, dest)
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


def check_template_is_not_stale():
    """Stop before copying anything if the deployed template is the old VBScript one.

    On 2026-09-29 a July copy of the template on the T: drive made
    CreateNetworkDatasetFromTemplate fail with ERROR 030386, after the sources had
    already been copied. The committed template is Python.
    """
    template_text = TEMPLATE_XML.read_text(encoding="utf-8")

    if "Select Case" in template_text:
        msg = (
            f"The template at {TEMPLATE_XML} contains VBScript source ('Select Case'), "
            "so it is a stale copy, not the committed Python template. Copy "
            "network_dataset/data/network_template.xml from the repo over it and re-run."
        )
        logger.error(msg)
        sys.exit(f"ERROR: {msg}")


def main(copy_only=False):
    """Copy the sources into the feature dataset, then create and build the network.

    With copy_only=True it stops after the copies and creates nothing. The QA refresh
    uses that: the network is created and built once, in step 06, after the turn remap.
    """
    if not TEMPLATE_XML.exists():
        msg = (
            f"Template XML not found at {TEMPLATE_XML}. "
            "Copy network_dataset/data/network_template.xml from the repo to that path."
        )
        logger.error(msg)
        sys.exit(f"ERROR: {msg}")

    check_template_is_not_stale()

    if not arcpy.Exists(FEATURE_DATASET):
        msg = f"Feature dataset not found: {FEATURE_DATASET}. Update FEATURE_DATASET to the correct path."
        logger.error(msg)
        sys.exit(f"ERROR: {msg}")

    copy_fc_to_fd(
        STANDALONE_EDGE_SOURCE, FEATURE_DATASET, EDGE_SOURCE_NAME,
        error_hint="Run LRS_updates.py to populate TRNLRS_TRN_STREET_VW before proceeding.",
        apply_exclusions=True,
    )
    copy_fc_to_fd(SOURCE_JUNCTION, FEATURE_DATASET, "TRNLRS_street_junction")
    copy_fc_to_fd(SOURCE_TURN, FEATURE_DATASET, "TRNLRS_traffic_turn")

    if copy_only:
        logger.info("Copy-only mode: the sources are in place. No network dataset was created or built.")
        return

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
        if "ERROR 030386" in msgs:
            msg = (
                "ArcGIS rejected the network template because it identifies one or more "
                "Field Script evaluators as VBScript, even though the template passed the "
                "up-front VBScript check. That would be a new problem with the committed "
                "template. The source feature classes were copied before network creation "
                "was attempted, so do not delete or recopy them. Create "
                "TRNLRS_street_network interactively with Python evaluators, then "
                "continue the QA workflow. See scripts/qa_refresh/README.md, "
                "'Step 03: ERROR 030386', for the exact evaluator settings.\n\n"
                f"ArcGIS geoprocessing messages:\n{msgs}"
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
