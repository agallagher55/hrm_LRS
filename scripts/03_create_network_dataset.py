"""
Create the new TRN_street_network (LRS-based) from the modified XML template.

Prerequisites (run in order):
  1. scripts/01_extract_network_config.py  → data/network_template.xml
  2. scripts/02_compare_schemas.py         → data/evaluator_field_map.json
  3. Manually edit data/network_template.xml:
       - Replace all references to SDEADM.TRN_street with the new edge source name
       - Update any evaluator fieldName values flagged as ACTION REQUIRED
       - Confirm junction source name (TRN_street_junction → new junction FC if renamed)
       - Confirm turn source name (TRN_traffic_turn → same or new)
     See docs/network_dataset_migration_plan.md for the full XML editing checklist.

Note on TRNLRS_TRN_STREET_VW / TRNLRS_TRN_STREET:
  TRNLRS_TRN_STREET_VW is created by LRS_updates.py as a standalone SDE feature
  class (not inside a feature dataset). Network datasets require all sources to
  live inside the target feature dataset, so this script copies the standalone FC
  into SDEADM.TRNLRS under the name TRNLRS_TRN_STREET (without _VW) to avoid an
  SDE name-uniqueness conflict.  The FD copy is what the network dataset references;
  the standalone _VW FC remains the authoritative source updated by LRS_updates.py.
  After each LRS refresh, re-copy the standalone FC over the FD copy and rebuild.

Run from ArcGIS Pro Python environment:
  > python scripts/03_create_network_dataset.py
"""

import os
import sys
from pathlib import Path

import arcpy

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SDE_CONNECTION = r"E:\HRM\Scripts\SDE\SQL\Dev\dev_RW_sdeadm.sde"

# Feature dataset that will contain the new network dataset.
# Network datasets must live inside a feature dataset in a geodatabase.
FEATURE_DATASET = os.path.join(SDE_CONNECTION, "SDEADM.TRNLRS")
NEW_ND_NAME     = "TRN_lrs_street_network"

# TRNLRS_TRN_STREET_VW is the authoritative standalone FC (outside any feature
# dataset), populated by LRS_updates.py.  It must be copied into FEATURE_DATASET
# before the network dataset can be created.  SDE enforces unique FC names across
# the entire geodatabase, so the copy is stored under a different name
# (TRNLRS_TRN_STREET, without the _VW suffix) to avoid a name collision.
# The XML template uses TRNLRS_TRN_STREET as the edge source name accordingly.
STANDALONE_EDGE_SOURCE = os.path.join(SDE_CONNECTION, "SDEADM.TRNLRS_TRN_STREET_VW")
EDGE_SOURCE_NAME       = "TRNLRS_TRN_STREET"

# Junction and turn FCs live in TRN_streets_routes (the old network FD).
# This script copies them into FEATURE_DATASET automatically if not already present.
SOURCE_JUNCTION = os.path.join(SDE_CONNECTION, "SDEADM.TRN_streets_routes", "SDEADM.TRN_street_junction")
SOURCE_TURN     = os.path.join(SDE_CONNECTION, "SDEADM.TRN_streets_routes", "SDEADM.TRN_traffic_turn")

REPO_ROOT    = Path(__file__).resolve().parents[1]
TEMPLATE_XML = REPO_ROOT / "data" / "network_template.xml"
# User or role to grant SELECT privilege to on all newly created SDE items.
PUBLIC_USER = "PUBLIC"
# ---------------------------------------------------------------------------


def grant_select(path, user=PUBLIC_USER):
    """Grant SELECT privilege on an SDE dataset so it is publicly viewable."""
    print(f"Granting SELECT to {user}: {os.path.basename(path)}")
    arcpy.management.ChangePrivileges(path, user, "GRANT")


def copy_fc_to_fd(source_path, feature_dataset, fc_name, error_hint=""):
    """Copy a feature class into the feature dataset, skipping if already present."""
    dest = os.path.join(feature_dataset, fc_name)
    if arcpy.Exists(dest):
        print(f"Already present in feature dataset, skipping: {fc_name}")
        return
    if not arcpy.Exists(source_path):
        sys.exit(
            f"ERROR: Source feature class not found: {source_path}"
            + (f"\n{error_hint}" if error_hint else "")
        )
    print(f"Copying into feature dataset:\n  {source_path}\n  → {dest}")
    arcpy.management.CopyFeatures(source_path, dest)
    grant_select(dest)
    print("Copy complete.")


def build_network(nd_path):
    """Build the network dataset after creation."""
    print(f"Building network dataset: {nd_path}")
    arcpy.na.BuildNetwork(nd_path)
    print("Build complete.")


def main():
    if not TEMPLATE_XML.exists():
        sys.exit(
            f"ERROR: Template XML not found at {TEMPLATE_XML}\n"
            "Run 01_extract_network_config.py and edit the template before proceeding."
        )

    if not arcpy.Exists(FEATURE_DATASET):
        sys.exit(
            f"ERROR: Feature dataset not found: {FEATURE_DATASET}\n"
            "Update FEATURE_DATASET to the correct path."
        )

    copy_fc_to_fd(
        STANDALONE_EDGE_SOURCE, FEATURE_DATASET, EDGE_SOURCE_NAME,
        error_hint="Run LRS_updates.py to populate TRNLRS_TRN_STREET_VW before proceeding.",
    )
    copy_fc_to_fd(SOURCE_JUNCTION, FEATURE_DATASET, "TRNLRS_street_junction")
    copy_fc_to_fd(SOURCE_TURN, FEATURE_DATASET, "TRNLRS_traffic_turn")

    new_nd_path = os.path.join(FEATURE_DATASET, NEW_ND_NAME)
    if arcpy.Exists(new_nd_path):
        sys.exit(
            f"ERROR: Network dataset already exists: {new_nd_path}\n"
            "Delete it first or choose a different name."
        )

    print(f"Creating network dataset from template: {TEMPLATE_XML}")
    arcpy.na.CreateNetworkDatasetFromTemplate(
        network_dataset_template=str(TEMPLATE_XML),
        output_feature_dataset=FEATURE_DATASET,
    )
    print(f"Network dataset created: {new_nd_path}")
    grant_select(new_nd_path)

    build_network(new_nd_path)
    print("\nDone. Validate the new network dataset by:")
    print("  1. Opening Network Dataset Properties in ArcGIS Pro and reviewing each tab.")
    print("  2. Running a test Route solve between two known points.")
    print("  3. Running a test Service Area solve.")
    print("  4. Comparing results against the old TRN_street_network.")


if __name__ == "__main__":
    main()
