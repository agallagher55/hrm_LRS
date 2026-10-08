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
  3. Validates the topology (VALIDATE = True).
  4. Exports the errors to a file geodatabase under output/, one class per geometry type.

Marking errors as exceptions is not done here. Robbie's feature class of valid dangles and
intersections is applied in the Error Inspector in Pro.

Run it again after every edge refresh. The edge copy is reloaded (04_sync_and_rebuild_network.py
or qa_refresh), which makes the whole extent dirty, so the topology must be validated again.

The topology has to be deleted before the edge source is deleted or swapped: a topology
participant cannot be deleted while it is a member (qa_refresh step 02 does this).

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
    logger.info(f"Exporting topology errors to {gdb} as {basename}_point / _line / _poly")
    arcpy.management.ExportTopologyErrors(TOPOLOGY, gdb, basename)

    for suffix in ("point", "line", "poly"):
        path = os.path.join(gdb, f"{basename}_{suffix}")

        if arcpy.Exists(path):
            count = int(arcpy.management.GetCount(path)[0])
            logger.info(f"  {basename}_{suffix}: {count:,} errors")


def main():
    logger.info(
        f"Network: {NETWORK.key} ({NETWORK.description}); topology {TOPOLOGY}"
    )

    for path, label in [(FEATURE_DATASET, "feature dataset"), (EDGE_FC, "edge source")]:

        if not arcpy.Exists(path):
            raise RuntimeError(f"Cannot find {label}: {path}")

    create_or_reuse_topology()
    add_edge_source_and_rules()

    if VALIDATE:
        validate()

    if EXPORT_ERRORS:
        export_errors()


if __name__ == "__main__":
    main()
