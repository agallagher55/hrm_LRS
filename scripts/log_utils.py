"""
Shared logging setup for the standalone scripts in this repo (network dataset
build/rebuild scripts, etc).

Not used by LRS_updates.py, which has its own logging via HRMutils.setupLog
and config.ini.
"""

import logging
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"


def setup_logger(name):
    """
    Configure a logger that writes INFO+ to the console and DEBUG+ to a
    timestamped file under logs/. Use in place of print() so each run leaves
    a persistent record of what actually happened (e.g. whether a feature
    class was freshly copied or skipped because it already existed).
    """
    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{name}.log"

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.info(f"Logging to {log_file}")
    return logger
