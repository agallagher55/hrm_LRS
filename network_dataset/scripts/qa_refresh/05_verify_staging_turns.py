"""Independently verify the staging turn class before the destructive swap."""

import config
from _shared import load_and_validate_core_scripts


def main():
    _, _, verifier = load_and_validate_core_scripts()
    verifier.TURN_FC = config.STAGING_TURN
    verifier.main()
    print(
        "Programmatic staging verification passed. Complete the spatial review "
        "checklist before running step 06."
    )


if __name__ == "__main__":
    main()

