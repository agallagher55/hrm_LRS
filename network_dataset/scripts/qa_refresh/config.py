"""Configuration shared by the ordered QA network-refresh entry points."""

import os
import sys
from pathlib import Path


# Derive the layout from this file without calling resolve(). When the entry
# point is launched from T:, __file__ retains T: rather than expanding to the
# backing UNC path. qa_refresh is inside scripts, so its parent is already the
# core scripts directory -- do not append a second "scripts" component.
QA_REFRESH_DIR = Path(__file__).parent
CORE_SCRIPTS_DIR = QA_REFRESH_DIR.parent
NETWORK_DATASET_DIR = CORE_SCRIPTS_DIR.parent
OUTPUT_DIR = Path(os.path.join(QA_REFRESH_DIR, "output"))

if str(CORE_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_SCRIPTS_DIR))

import network_definitions  # noqa: E402

# Which network the whole workflow runs on: DISTANCE by default, HRFE with HRM_NETWORK=HRFE
# set before the run. Scripts 03, 05 and the verifier read the same variable, so every step
# agrees. See ../network_definitions.py.
NETWORK_DEF = network_definitions.get_definition()

QA_SDE = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"
QA_NETWORK_FD_NAME = NETWORK_DEF.feature_dataset
QA_NETWORK_FD = os.path.join(QA_SDE, QA_NETWORK_FD_NAME)

NETWORK = os.path.join(QA_NETWORK_FD, "SDEADM." + NETWORK_DEF.network_name)
EDGE = os.path.join(QA_NETWORK_FD, "SDEADM." + NETWORK_DEF.edge_name)
JUNCTION = os.path.join(QA_NETWORK_FD, "SDEADM." + NETWORK_DEF.junction_name)
TURN = os.path.join(QA_NETWORK_FD, "SDEADM." + NETWORK_DEF.turn_name)
# Built by 07_create_topology.py. It holds the edge source, so it has to go before the edge does.
TOPOLOGY = os.path.join(QA_NETWORK_FD, "SDEADM." + NETWORK_DEF.edge_name + "_topology")
STAGING_TURN = os.path.join(
    QA_NETWORK_FD, "SDEADM." + NETWORK_DEF.staging_turn_name
)
QA_STANDALONE_VIEW = os.path.join(QA_SDE, "SDEADM.TRNLRS_TRN_STREET_VW")

# Step 01 also exports the network sources to a file geodatabase in OUTPUT_DIR. A
# database-level refresh of QA from Prod removes the whole network feature dataset,
# the in-SDE turn backup included; the file geodatabase survives it.
OFFLINE_BACKUP = True

SCRIPT_03 = Path(os.path.join(CORE_SCRIPTS_DIR, "03_create_network_dataset.py"))
SCRIPT_05 = Path(os.path.join(CORE_SCRIPTS_DIR, "05_rebuild_traffic_turns.py"))
VERIFY_SCRIPT = Path(os.path.join(CORE_SCRIPTS_DIR, "verify_turn_rebuild.py"))
FULL_REBUILD_SCRIPT = Path(
    os.path.join(CORE_SCRIPTS_DIR, "run_full_network_rebuild.py")
)
