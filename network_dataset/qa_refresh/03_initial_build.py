"""Copy fresh sources and perform the preliminary QA network build."""

from _shared import load_and_validate_core_scripts


def main():
    build, _, _ = load_and_validate_core_scripts()
    build.main()
    print(
        "Preliminary build complete. Missing-edge turn errors and Turns: 0 are "
        "expected here. Confirm the edge count matches Prod before step 04."
    )


if __name__ == "__main__":
    main()

