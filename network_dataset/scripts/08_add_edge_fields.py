"""
Add the empty speed and travel time fields to the edge source that already exists in QA.

Script 03 adds them on a fresh copy, so after the next qa_refresh they are there without this
script. Use this one to add them now, to the live edge class. See edge_fields.py.

The edge class is a network source and a topology member. Adding a field to such a class has not
been tried here, so run it while nobody is using the network, then check the network
dataset properties still show Built, and rerun 07_create_topology.py to confirm the topology
is still valid.

Set HRM_NETWORK=HRFE to work on the HRFE edge copy instead.
"""

import os

import arcpy

import edge_fields
import network_definitions
from log_utils import setup_logger

logger = setup_logger("08_add_edge_fields")

SDE_CONNECTION = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"

NETWORK = network_definitions.get_definition()
EDGE_FC = os.path.join(SDE_CONNECTION, NETWORK.feature_dataset, "SDEADM." + NETWORK.edge_name)


def main():
    logger.info(f"Network: {NETWORK.key} ({NETWORK.description}); edge source {EDGE_FC}")

    if not arcpy.Exists(EDGE_FC):
        raise RuntimeError(f"Cannot find the edge source: {EDGE_FC}")

    added = edge_fields.add_travel_fields(EDGE_FC, logger)
    logger.info(f"Added: {', '.join(added) if added else 'nothing, both fields were already there'}")


if __name__ == "__main__":
    main()
