"""Configuration shared by the ordered QA network-refresh entry points."""

import os
from pathlib import Path


# Working copy shown in ArcGIS Pro. Use the mapped T: drive rather than the
# backing file-server UNC name so every operator sees the same readable paths.
WORK_ROOT = r"T:\work\giss\monthly\202607jul\gallaga"
NETWORK_DATASET_DIR = Path(os.path.join(WORK_ROOT, "network_dataset"))
CORE_SCRIPTS_DIR = Path(os.path.join(NETWORK_DATASET_DIR, "scripts"))
QA_REFRESH_DIR = Path(os.path.join(CORE_SCRIPTS_DIR, "qa_refresh"))
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
