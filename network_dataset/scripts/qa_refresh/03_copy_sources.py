"""Copy fresh sources into the QA network feature dataset. Creates and builds nothing.

The edge source comes from Prod's TRNLRS_TRN_STREET_VW (minus the edge exclusions); the
junction and raw turn classes come from QA's legacy TRN_street_junction and
TRN_traffic_turn. The network dataset is created and built once, in step 06, after the
turn remap, so there is no throwaway build in between. To prove the template creates
and builds without touching QA, run test_template_create.py.
"""

from _shared import load_and_validate_core_scripts


def main():
    build, _, _ = load_and_validate_core_scripts()
    build.main(copy_only=True)
    print(
        "Sources copied. Confirm the edge count equals Prod's minus the excluded WA "
        "and island rows (see the 'Edge exclusions applied' log line) before step 04."
    )


if __name__ == "__main__":
    main()
