"""Copy fresh sources and attempt the preliminary QA network build.

ArcGIS Pro 3.5.8 may reject the committed template with ERROR 030386 because
its scripted evaluators retain a legacy VBScript evaluator identity. See the
README's step 03 troubleshooting section before rerunning a failed build.
"""

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
