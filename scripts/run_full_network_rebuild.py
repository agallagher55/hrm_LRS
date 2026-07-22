"""
run_full_network_rebuild.py

Orchestrates the full cycle that has been run manually, multiple times, across
this project: remap turns, swap the turn FC in, delete and recreate the
network dataset, build it once, and verify the result. Wraps
05_rebuild_traffic_turns.py and 03_create_network_dataset.py rather than
duplicating their logic, so a fix to either script is automatically picked up
here too.

Why this exists
----------------
Two real bugs came out of running this cycle by hand:

1. 05 used to read the edge source's FCID from a LIVE network dataset, which
   meant it could not run during a clean rebuild (05 needs the FCID, but 03
   needs a remapped turn FC to be worth building). 05 has since been patched
   to read the FCID from network_template.xml instead, which is deterministic
   and does not require a network dataset to already exist. This script
   depends on that fix being in place.

2. The network dataset got built twice in one cycle at least once (likely a
   manual "Build Network" in Pro run in addition to a script-driven build),
   which stacked two generations of system junctions and edges on top of each
   other (16,334 junctions and 37,728 edges observed, both roughly double
   sane values). This script guarantees BuildNetwork is called exactly once
   per run by deleting any existing network dataset first and never calling
   build logic more than once.

What this does NOT do
----------------------
- Does not decide FOR you whether to review the remapped turn FC before
  swapping it in. It swaps automatically, matching the "trusted, repeatable
  cycle" use case. If you want to eyeball the remap first, run
  05_rebuild_traffic_turns.py directly with AUTO_SWAP_AND_REBUILD left False,
  review TRNLRS_traffic_turn_staging, then run this script, which will find
  the staging FC already correct and skip re-remapping... actually it does
  NOT currently support that skip path, see the note in main() below. Run
  05 fresh here for now; this is a known simplification, not a bug.
- Does not touch Mel's manually-authored Cogswell ramp turns, which live in
  the OLD turn table this script reads from and get carried through the
  remap like any other turn (see traffic_turns.md).

Usage
-----
Run from an ArcGIS Pro Python environment, from the scripts/ directory (or
adjust SCRIPTS_DIR below):
    > python run_full_network_rebuild.py
"""

import importlib.util
import sys
from pathlib import Path

import arcpy

from log_utils import setup_logger

logger = setup_logger("run_full_network_rebuild")

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

# Directory containing 03_create_network_dataset.py and
# 05_rebuild_traffic_turns.py. Defaults to this script's own directory.
SCRIPTS_DIR = Path(__file__).resolve().parent

SCRIPT_05_PATH = SCRIPTS_DIR / "05_rebuild_traffic_turns.py"
SCRIPT_03_PATH = SCRIPTS_DIR / "03_create_network_dataset.py"


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def load_module(path, module_name):
    """Import a numerically-prefixed script (e.g. 05_rebuild_traffic_turns.py)
    as a module by file path, since its filename is not a valid Python
    identifier for a normal import statement."""
    if not path.exists():
        logger.error(f"Script not found: {path}")
        sys.exit(1)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def report_source_counts(network_dataset, edge_fc, junction_fc, turn_fc):
    """Print feature counts for a quick sanity check after a rebuild.

    This is NOT a substitute for opening the actual BuildErrors_<guid>.txt
    file. It catches gross problems (doubled counts, zero turns) at a
    glance; it does not catch per-record resolution failures, which only
    show up in the error file. Always check that file directly too.
    """
    logger.info("=" * 60)
    logger.info("Post-build source counts")
    for label, fc in [("Edges (source)", edge_fc), ("Junctions (user-defined)", junction_fc), ("Turns (source)", turn_fc)]:
        if arcpy.Exists(fc):
            count = int(arcpy.management.GetCount(fc)[0])
            logger.info(f"  {label:28s}: {count:,}")
        else:
            logger.info(f"  {label:28s}: NOT FOUND ({fc})")

    if arcpy.Exists(network_dataset):
        desc = arcpy.Describe(network_dataset)
        logger.info(f"  Network dataset sources:")
        for src in desc.sources:
            logger.info(f"    {src.name}: FCID {src.sourceID}")
    logger.info("=" * 60)
    logger.info(
        "This is a quick sanity check only. Always open the actual "
        "BuildErrors_<guid>.txt file referenced in 03's DEBUG log line "
        "and confirm its GUID matches this run before trusting a clean build."
    )


# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------

def main():

    logger.info("Step 1/4: Load scripts 05 and 03 as modules")
    mod05 = load_module(SCRIPT_05_PATH, "rebuild_traffic_turns")
    mod03 = load_module(SCRIPT_03_PATH, "create_network_dataset")

    # Known simplification: this always re-runs the full remap. If you want
    # to review TRNLRS_traffic_turn_staging before swapping it in, run 05
    # directly first and skip this orchestrator for that cycle.
    logger.info("Step 2/4: Remap turns (05_rebuild_traffic_turns.py)")
    mod05.main()

    if not arcpy.Exists(mod05.NEW_TURN_FC):
        logger.error(
            f"Expected staging turn FC not found after remap: {mod05.NEW_TURN_FC}. "
            "05 did not complete successfully -- stopping before touching the "
            "network dataset."
        )
        sys.exit(1)

    logger.info("Step 3/4: Swap turn FC and delete network dataset (single pass)")

    if arcpy.Exists(mod05.NEW_NETWORK):
        logger.info(f"  Deleting existing network dataset: {mod05.NEW_NETWORK}")
        arcpy.management.Delete(mod05.NEW_NETWORK)
    else:
        logger.info("  No existing network dataset to delete.")

    if arcpy.Exists(mod05.OLD_TURN_FC_FINAL):
        logger.info(f"  Deleting old turn FC: {mod05.OLD_TURN_FC_FINAL}")
        arcpy.management.Delete(mod05.OLD_TURN_FC_FINAL)

    staging_name = Path(mod05.NEW_TURN_FC).name
    final_name = Path(mod05.OLD_TURN_FC_FINAL).name
    logger.info(f"  Renaming {staging_name} -> {final_name}")
    arcpy.management.Rename(mod05.NEW_TURN_FC, final_name)

    logger.info("Step 4/4: Create and build the network dataset (03_create_network_dataset.py)")
    # 03's own logic already refuses to proceed if the network dataset still
    # exists (raises a clear error rather than silently rebuilding on top of
    # it), which combined with the delete above guarantees exactly one
    # CreateNetworkDatasetFromTemplate + BuildNetwork pair this run.
    mod03.main()

    junction_fc = mod05.SDE + rf"\{mod05.NETWORK_FD}\SDEADM.TRNLRS_street_junction"
    report_source_counts(
        network_dataset=mod05.NEW_NETWORK,
        edge_fc=mod05.NEW_EDGE_FC,
        junction_fc=junction_fc,
        turn_fc=mod05.OLD_TURN_FC_FINAL,
    )

    logger.info("Full rebuild cycle complete.")


if __name__ == "__main__":
    main()
