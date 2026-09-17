"""Configuration shared by the ordered QA network-refresh entry points."""

from pathlib import Path


HERE = Path(__file__).resolve().parent
NETWORK_DATASET_DIR = HERE.parent
CORE_SCRIPTS_DIR = NETWORK_DATASET_DIR / "scripts"
OUTPUT_DIR = HERE / "output"

QA_SDE = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"
QA_NETWORK_FD_NAME = r"SDEADM.TRNLRS_network"
QA_NETWORK_FD = QA_SDE + "\\" + QA_NETWORK_FD_NAME

NETWORK = QA_NETWORK_FD + r"\SDEADM.TRNLRS_street_network"
EDGE = QA_NETWORK_FD + r"\SDEADM.TRNLRS_TRN_STREET"
JUNCTION = QA_NETWORK_FD + r"\SDEADM.TRNLRS_street_junction"
TURN = QA_NETWORK_FD + r"\SDEADM.TRNLRS_traffic_turn"
STAGING_TURN = QA_NETWORK_FD + r"\SDEADM.TRNLRS_traffic_turn_staging"
QA_STANDALONE_VIEW = QA_SDE + r"\SDEADM.TRNLRS_TRN_STREET_VW"

SCRIPT_03 = CORE_SCRIPTS_DIR / "03_create_network_dataset.py"
SCRIPT_05 = CORE_SCRIPTS_DIR / "05_rebuild_traffic_turns.py"
VERIFY_SCRIPT = CORE_SCRIPTS_DIR / "verify_turn_rebuild.py"
FULL_REBUILD_SCRIPT = CORE_SCRIPTS_DIR / "run_full_network_rebuild.py"

