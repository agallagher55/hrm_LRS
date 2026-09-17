"""Delete the QA network dataset and its three registered source classes."""

import argparse

import arcpy

import config
from _shared import load_and_validate_core_scripts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-delete-qa-network", action="store_true")
    args = parser.parse_args()
    if not args.confirm_delete_qa_network:
        parser.error("refusing destructive step without --confirm-delete-qa-network")

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

