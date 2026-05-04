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
SDE_CONNECTION = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"

# Feature dataset that will contain the new network dataset.
# Network datasets must live inside a feature dataset in a geodatabase.
FEATURE_DATASET    = os.path.join(SDE_CONNECTION, "SDEADM.TRNLRS")   # adjust owner/name as needed
NEW_ND_NAME        = "TRN_lrs_street_network"                      # name of the new ND

REPO_ROOT          = Path(__file__).resolve().parents[1]
TEMPLATE_XML       = REPO_ROOT / "data" / "network_template.xml"   # edited copy
# ---------------------------------------------------------------------------


def verify_sources_exist(feature_dataset):
    """Check that all source FCs referenced by the template exist inside the feature dataset.

    CreateNetworkDatasetFromTemplate requires sources to live inside the target
    feature dataset, not just anywhere in the geodatabase.
    """
    # Short (unqualified) names as they appear in the XML <Name> elements.
    # Update this list whenever the XML template source names change.
    expected_sources = [
        "TRNLRS_TRN_STREET_VW",   # edge source — replaces old TRN_street
        "TRN_street_junction",    # junction FC — update name if renamed in TRNLRS
        "TRN_traffic_turn",       # turn FC — update name if renamed in TRNLRS
    ]
    missing = []
    for src in expected_sources:
        path = os.path.join(feature_dataset, src)
        if not arcpy.Exists(path):
            missing.append(src)
    return missing


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

    missing = verify_sources_exist(FEATURE_DATASET)
    if missing:
        sys.exit(
            f"ERROR: The following source feature classes are missing:\n"
            + "\n".join(f"  - {m}" for m in missing)
            + "\nUpdate FEATURE_DATASET / source names in this script and the XML template."
        )

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

    build_network(new_nd_path)
    print("\nDone. Validate the new network dataset by:")
    print("  1. Opening Network Dataset Properties in ArcGIS Pro and reviewing each tab.")
    print("  2. Running a test Route solve between two known points.")
    print("  3. Running a test Service Area solve.")
    print("  4. Comparing results against the old TRN_street_network.")


if __name__ == "__main__":
    main()
