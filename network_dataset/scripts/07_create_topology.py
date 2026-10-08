"""
Build the geodatabase topology on the network's edge source (TRNLRS_TRN_STREET).

The topology lives in the same feature dataset as the network dataset and holds only the
edge source. Its rules are the set Robbie Evans uses on his street network, minus the
route-coverage rules he does not want here (bus, evacuation, ice and truck routes, speed
routes, restrictions and parking permits):

  Must Not Overlap (Line)
  Must Not Intersect (Line)
  Must Not Have Dangles (Line)
  Must Not Self Overlap (Line)
  Must Not Self Intersect (Line)
  Must Be Single Part (Line)

Optional extra, off by default (see OPTIONAL_RULES): Must Not Intersect Or Touch Interior,
which flags a street end that touches the middle of another street. The network uses End
Point connectivity, so such a touch does not connect without a split.

What this script does, in order:
  1. Creates the topology if it does not exist (an empty one made in Pro is reused).
  2. Adds the edge source and the rules, unless the edge source is already in the topology.
     Rules added by hand in Pro are never read back or duplicated: if the edge source is
     already a member, this script leaves the rules alone.
  3. Validates the topology (# True builds everything in a scratch file geodatabase copy instead of QA. QA is only read.
USE_SCRATCH = False

VALIDATE = True).
  4. Exports the errors to a file geodatabase under output/, one class per geometry type.

Marking errors as exceptions is not done here. Robbie's feature class of valid dangles and
intersections is applied in the Error Inspector in Pro.

Run it again after every edge refresh. The edge copy is reloaded (04_sync_and_rebuild_network.py
or qa_refresh), which makes the whole extent dirty, so the topology must be validated again.

The topology has to be deleted before the edge source is deleted or swapped: a topology
participant cannot be deleted while it is a member (qa_refresh step 02 does this).

Testing without touching QA: set USE_SCRATCH = True below. The edge source is copied into a scratch file
geodatabase under output/ and the whole sequence runs there. QA is only read, so it is safe
while the live network is in use, and it shows whether the rules and validation behave before
the topology goes on the live edge class. It cannot show whether the live class needs to be
registered as versioned, or whether a class can be in both a topology and the network dataset
in the enterprise geodatabase; only the QA run shows that.

Set HRM_NETWORK=HRFE to build the topology on the HRFE edge copy instead. See network_definitions.py.
"""

import os
from pathlib import Path

import arcpy

import network_definitions
from log_utils import setup_logger

logger = setup_logger("07_create_topology")

SDE_CONNECTION = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"

NETWORK = network_definitions.get_definition()
FEATURE_DATASET = os.path.join(SDE_CONNECTION, NETWORK.feature_dataset)
EDGE_FC = os.path.join(FEATURE_DATASET, "SDEADM." + NETWORK.edge_name)

# Named from the edge source, which is also how it was named by hand in Pro:
# TRNLRS_TRN_STREET_topology (and TRNLRS_TRN_STREET_HRFE_topology for HRFE).
TOPOLOGY_NAME = NETWORK.edge_name + "_topology"
TOPOLOGY = os.path.join(FEATURE_DATASET, "SDEADM." + TOPOLOGY_NAME)

# Metres. Matches what the topology made in Pro shows (0.001) and the usual tolerance of
# the feature dataset. Pass None to take the feature dataset's own value.
CLUSTER_TOLERANCE = 0.001
XY_RANK = 1

VALIDATE = True
EXPORT_ERRORS = True
ERROR_OUTPUT_DIR = Path(__file__).parent / "output"

# Rules on the edge source alone: arcpy rule keyword, then Pro's name for it.
RULES = [
    ("MUST_NOT_OVERLAP_LINE", "Must Not Overlap (Line)"),
    ("MUST_NOT_INTERSECT_LINE", "Must Not Intersect (Line)"),
    ("MUST_NOT_HAVE_DANGLES", "Must Not Have Dangles (Line)"),
    ("MUST_NOT_SELF_OVERLAP_LINE", "Must Not Self Overlap (Line)"),
    ("MUST_NOT_SELF_INTERSECT_LINE", "Must Not Self Intersect (Line)"),
    ("MUST_BE_SINGLE_PART", "Must Be Single Part (Line)"),
]

OPTIONAL_RULES = [
    ("MUST_NOT_INTERSECT_OR_TOUCH_INTERIOR", "Must Not Intersect Or Touch Interior (Line)"),
]
INCLUDE_OPTIONAL_RULES = False


def rules_to_add():
    """The (keyword, label) pairs this run adds."""
    if INCLUDE_OPTIONAL_RULES:
        return RULES + OPTIONAL_RULES

    return list(RULES)


def topology_members(topology):
    """Names of the feature classes already in the topology, without owner prefix, lower case."""
    names = arcpy.Describe(topology).featureClassNames or []

    return {str(name).split(".")[-1].lower() for name in names}


def use_scratch_copy():
    """Point the script at a copy of the edge source in a file geodatabase."""
    global FEATURE_DATASET, EDGE_FC, TOPOLOGY

    ERROR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    gdb_name = f"topology_scratch_{NETWORK.key}.gdb"
    gdb = str(ERROR_OUTPUT_DIR / gdb_name)

    if arcpy.Exists(gdb):
        arcpy.management.Delete(gdb)

    arcpy.management.CreateFileGDB(str(ERROR_OUTPUT_DIR), gdb_name)
    spatial_reference = arcpy.Describe(EDGE_FC).spatialReference
    arcpy.management.CreateFeatureDataset(gdb, "scratch_network", spatial_reference)
    scratch_fd = os.path.join(gdb, "scratch_network")
    logger.info(f"Scratch run: copying {EDGE_FC} into {scratch_fd}")
    arcpy.management.CopyFeatures(EDGE_FC, os.path.join(scratch_fd, NETWORK.edge_name))

    FEATURE_DATASET = scratch_fd
    EDGE_FC = os.path.join(scratch_fd, NETWORK.edge_name)
    TOPOLOGY = os.path.join(scratch_fd, TOPOLOGY_NAME)


def create_or_reuse_topology():
    if arcpy.Exists(TOPOLOGY):
        logger.info(f"Topology already exists, reusing it: {TOPOLOGY}")
        return

    logger.info(f"Creating topology {TOPOLOGY_NAME} in {FEATURE_DATASET}")

    if CLUSTER_TOLERANCE is None:
        arcpy.management.CreateTopology(FEATURE_DATASET, TOPOLOGY_NAME)

    else:
        arcpy.management.CreateTopology(FEATURE_DATASET, TOPOLOGY_NAME, CLUSTER_TOLERANCE)


def add_edge_source_and_rules():
    members = topology_members(TOPOLOGY)

    if NETWORK.edge_name.lower() in members:
        logger.warning(
            f"{NETWORK.edge_name} is already in the topology, so its rules are left as they are. "
            "Check them in Pro (Topology Properties, Rules)."
        )
        return

    logger.info(f"Adding {EDGE_FC} to the topology (XY rank {XY_RANK})")
    arcpy.management.AddFeatureClassToTopology(TOPOLOGY, EDGE_FC, XY_RANK)

    for keyword, label in rules_to_add():
        logger.info(f"Adding rule: {label}")
        arcpy.management.AddRuleToTopology(TOPOLOGY, keyword, EDGE_FC)


def validate():
    logger.info("Validating the topology over its full extent")
    arcpy.management.ValidateTopology(TOPOLOGY)
    logger.info("Validation complete")


def export_errors():
    ERROR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    gdb_name = f"topology_errors_{NETWORK.key}.gdb"
    gdb = str(ERROR_OUTPUT_DIR / gdb_name)

    if not arcpy.Exists(gdb):
        arcpy.management.CreateFileGDB(str(ERROR_OUTPUT_DIR), gdb_name)

    basename = f"{NETWORK.edge_name}_errors"
    suffixes = ("point", "line", "poly")

    # The export fails if its output classes exist, which they do on every run after the first.
    for suffix in suffixes:
        path = os.path.join(gdb, f"{basename}_{suffix}")

        if arcpy.Exists(path):
            arcpy.management.Delete(path)

    logger.info(f"Exporting topology errors to {gdb} as {basename}_point / _line / _poly")
    arcpy.management.ExportTopologyErrors(TOPOLOGY, gdb, basename)

    for suffix in suffixes:
        path = os.path.join(gdb, f"{basename}_{suffix}")

        if arcpy.Exists(path):
            count = int(arcpy.management.GetCount(path)[0])
            logger.info(f"  {basename}_{suffix}: {count:,} errors")


def main():
    for path, label in [(FEATURE_DATASET, "feature dataset"), (EDGE_FC, "edge source")]:

        if not arcpy.Exists(path):
            raise RuntimeError(f"Cannot find {label}: {path}")

    if USE_SCRATCH:
        use_scratch_copy()

    logger.info(
        f"Network: {NETWORK.key} ({NETWORK.description}); topology {TOPOLOGY}"
    )

    create_or_reuse_topology()
    add_edge_source_and_rules()

    if VALIDATE:
        validate()

    if EXPORT_ERRORS:
        export_errors()


if __name__ == "__main__":
    main()
