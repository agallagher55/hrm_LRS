"""Swap the reviewed staging turns and perform exactly one final build."""

import config
from _shared import load_and_validate_core_scripts, load_script, require_exists


# Set this to True only after completing the staging verification and review.
CONFIRM_REVIEWED_STAGING = False


def main():
    if not CONFIRM_REVIEWED_STAGING:
        raise RuntimeError(
            "Refusing swap while CONFIRM_REVIEWED_STAGING is False. Complete "
            "the staging review, then set the global to True before running this script."
        )

    load_and_validate_core_scripts()
    require_exists(config.STAGING_TURN, "Reviewed staging turn feature class")
    orchestrator = load_script(config.FULL_REBUILD_SCRIPT, "qa_refresh_full_rebuild")
    orchestrator.main(["--use-existing-staging"])


if __name__ == "__main__":
    main()
