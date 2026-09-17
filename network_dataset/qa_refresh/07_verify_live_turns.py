"""Verify the live QA turn class after the staging swap and final build."""

import config
from _shared import load_and_validate_core_scripts, require_exists


def main():
    _, _, verifier = load_and_validate_core_scripts()
    require_exists(config.TURN, "Live QA turn feature class")
    verifier.TURN_FC = config.TURN
    verifier.main()
    print(
        "Live turn verification passed. Reapply SQL grants, inspect this run's "
        "BuildErrors file, and complete the route smoke tests in the runbook."
    )


if __name__ == "__main__":
    main()

