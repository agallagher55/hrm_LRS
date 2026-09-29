"""Copy fresh sources and create and build the preliminary QA network.

The committed Python template creates and builds by script (first observed on
2026-09-29). If this fails with ERROR 030386, compare the deployed
data/network_template.xml with the repo copy first: the failure on 2026-09-29 was a stale
VBScript copy on the T: drive. See the README's step 03 troubleshooting section.
"""

from _shared import load_and_validate_core_scripts


def main():
    build, _, _ = load_and_validate_core_scripts()
    build.main()
    print(
        "Preliminary build complete. Missing-edge turn errors and Turns: 0 are "
        "expected here. Confirm the edge count equals Prod's minus the excluded WA/island "
        "rows (see the 'Edge exclusions applied' log line) before step 04."
    )


if __name__ == "__main__":
    main()
