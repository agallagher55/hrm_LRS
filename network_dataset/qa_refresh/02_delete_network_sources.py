"""Delete the QA network dataset and its three registered source classes."""

import arcpy

import config
from _shared import load_and_validate_core_scripts


# Set this to True only after reviewing the configured QA paths in config.py.
CONFIRM_DELETE_QA_NETWORK = True


def main():
    if not CONFIRM_DELETE_QA_NETWORK:
        raise RuntimeError(
            "Refusing destructive step while CONFIRM_DELETE_QA_NETWORK is False. "
            "Review config.py, then set the global to True before running this script."
        )

    load_and_validate_core_scripts()
    for label, path in [
        ("network dataset", config.NETWORK),
        ("edge source", config.EDGE),
        ("junction source", config.JUNCTION),
        ("turn source", config.TURN),
    ]:
        if arcpy.Exists(path):
            print(f"Deleting {label}: {path}")
            arcpy.management.Delete(path)
        else:
            print(f"Already absent, skipping {label}: {path}")


if __name__ == "__main__":
    main()
