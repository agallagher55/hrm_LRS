"""Configuration shared by the ordered QA network-refresh entry points."""

import os
from pathlib import Path


# Derive the layout from this file without calling resolve(). When the entry
# point is launched from T:, __file__ retains T: rather than expanding to the
# backing UNC path. qa_refresh is inside scripts, so its parent is already the
# core scripts directory -- do not append a second "scripts" component.
QA_REFRESH_DIR = Path(__file__).parent
CORE_SCRIPTS_DIR = QA_REFRESH_DIR.parent
NETWORK_DATASET_DIR = CORE_SCRIPTS_DIR.parent
OUTPUT_DIR = Path(os.path.join(QA_REFRESH_DIR, "output"))

QA_SDE = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"
QA_NETWORK_FD_NAME = r"SDEADM.TRNLRS_network"
QA_NETWORK_FD = os.path.join(QA_SDE, QA_NETWORK_FD_NAME)

NETWORK = os.path.join(QA_NETWORK_FD, "SDEADM.TRNLRS_street_network")
EDGE = os.path.join(QA_NETWORK_FD, "SDEADM.TRNLRS_TRN_STREET")
JUNCTION = os.path.join(QA_NETWORK_FD, "SDEADM.TRNLRS_street_junction")
TURN = os.path.join(QA_NETWORK_FD, "SDEADM.TRNLRS_traffic_turn")
STAGING_TURN = os.path.join(
    QA_NETWORK_FD, "SDEADM.TRNLRS_traffic_turn_staging"
)
QA_STANDALONE_VIEW = os.path.join(QA_SDE, "SDEADM.TRNLRS_TRN_STREET_VW")

SCRIPT_03 = Path(os.path.join(CORE_SCRIPTS_DIR, "03_create_network_dataset.py"))
SCRIPT_05 = Path(os.path.join(CORE_SCRIPTS_DIR, "05_rebuild_traffic_turns.py"))
VERIFY_SCRIPT = Path(os.path.join(CORE_SCRIPTS_DIR, "verify_turn_rebuild.py"))
FULL_REBUILD_SCRIPT = Path(
    os.path.join(CORE_SCRIPTS_DIR, "run_full_network_rebuild.py")
)
