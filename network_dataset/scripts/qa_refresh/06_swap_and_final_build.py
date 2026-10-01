"""Swap the reviewed staging turns and perform exactly one final build."""

import inspect

import config
from _shared import load_and_validate_core_scripts, load_script, require_exists, require_network


# Set this to True only after completing the staging verification and review.
CONFIRM_REVIEWED_STAGING = False

# The network this run swaps and rebuilds. It must match HRM_NETWORK (unset means DISTANCE, the live
# network), so set both on purpose: for HRFE, set this to "HRFE" and run with HRM_NETWORK=HRFE.
NETWORK_TO_BUILD = "DISTANCE"


def main():
    if not CONFIRM_REVIEWED_STAGING:
        raise RuntimeError(
            "Refusing swap while CONFIRM_REVIEWED_STAGING is False. Complete "
            "the staging review, then set the global to True before running this script."
        )

    load_and_validate_core_scripts()
    require_network(NETWORK_TO_BUILD, "NETWORK_TO_BUILD")
    require_exists(config.STAGING_TURN, "Reviewed staging turn feature class")
    orchestrator = load_script(config.FULL_REBUILD_SCRIPT, "qa_refresh_full_rebuild")

    if "argv" not in inspect.signature(orchestrator.main).parameters:
        raise RuntimeError(
            f"{config.FULL_REBUILD_SCRIPT} is a stale copy: its main() takes no arguments. "
            "Copy network_dataset/scripts/run_full_network_rebuild.py from the repo over it. "
            "Nothing has been changed."
        )

    orchestrator.main(["--use-existing-staging"])


if __name__ == "__main__":
    main()
