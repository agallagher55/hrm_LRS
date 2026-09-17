"""Swap the reviewed staging turns and perform exactly one final build."""

import argparse

import config
from _shared import load_and_validate_core_scripts, load_script, require_exists


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-reviewed-staging", action="store_true")
    args = parser.parse_args()
    if not args.confirm_reviewed_staging:
        parser.error("refusing swap without --confirm-reviewed-staging")

    load_and_validate_core_scripts()
    require_exists(config.STAGING_TURN, "Reviewed staging turn feature class")
    orchestrator = load_script(config.FULL_REBUILD_SCRIPT, "qa_refresh_full_rebuild")
    orchestrator.main(["--use-existing-staging"])


if __name__ == "__main__":
    main()

