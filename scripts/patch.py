"""
patch_turn_edge1end.py

Fast-path fix for the total turn build failure. Confirmed root cause:
05_rebuild_traffic_turns.py never wrote Edge1End (it is not in that
script's insert_fields list), so every remapped turn record got the schema
default of "N" ("turn passes through the beginning of Edge1"). Many records
have Edge1Pos near 1 (the end of the edge), directly contradicting the "N"
flag. This mismatch is present across most records and is consistent with
BuildNetwork failing to resolve nearly every turn.

Per Esri's turn feature class schema: Edge1End = "Y" means the turn passes
through the end of Edge1; "N" means it passes through the beginning. This
script recomputes Edge1End directly from the position already stored in
Edge1Pos, using the standard threshold (>= 0.5 is closer to the end).

This is an in-place UPDATE on the live TRNLRS_traffic_turn, not a re-remap.
No OID or FCID values are touched, only Edge1End.

Usage
-----
1. Review PATCH_TURN_FC and NETWORK_DATASET below.
2. Run from an ArcGIS Pro Python environment (arcpy required).
3. Re-run scripts/03_create_network_dataset.py afterward to recreate and
   rebuild the network (the turn FC will be "already present", no re-copy
   needed -- it only needs recreating, not re-copying).

Note on editing SDEADM.TRNLRS_network
--------------------------------------
TRNLRS_traffic_turn is a registered turn source of TRNLRS_street_network
(a "controller dataset" participant), the same relationship already known
to block Delete/Rename on it directly (ERROR 001919) until the network
dataset is deleted. Deleting the network dataset and then patching the
field in the SAME interpreter session raised "RuntimeError: cannot open"
-- deleting a network dataset is a schema-level change to the whole
feature dataset, and arcpy can hold stale connection/lock state from
earlier calls in the same process. This script therefore splits the two
steps: run it once with DELETE_NETWORK_ONLY = True (deletes the network
dataset and exits), then run it AGAIN as a fresh process with
DELETE_NETWORK_ONLY = False (patches the field). Running each step in its
own process avoids the stale-connection issue.
"""


import sys

try:
    import arcpy
except ImportError:
    print("ERROR: arcpy is required. Run this from an ArcGIS Pro Python environment.")
    sys.exit(1)


# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

SDE        = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"
NETWORK_FD = r"SDEADM.TRNLRS_network"

PATCH_TURN_FC = SDE + rf"\{NETWORK_FD}\SDEADM.TRNLRS_traffic_turn"
NETWORK_DATASET = SDE + rf"\{NETWORK_FD}\SDEADM.TRNLRS_street_network"

# Set to False to preview the counts without writing any changes.
APPLY_UPDATE = True

# Run this script TWICE, each as a separate process:
#   1) DELETE_NETWORK_ONLY = True  -> deletes the network dataset, exits.
#   2) DELETE_NETWORK_ONLY = False -> patches Edge1End (network dataset
#      must already be deleted from step 1; this step does NOT delete it).
# Running both in one process raised "RuntimeError: cannot open" on the
# turn FC, so they are kept as separate runs.
DELETE_NETWORK_ONLY = False

# Try a bare UpdateCursor with NO arcpy.da.Editor wrapper at all. The
# Editor wrapper was added to work around "Objects in this class cannot
# be updated outside an edit session", but that error happened while the
# network dataset still existed (a controller-dataset lock reason). Now
# that the network dataset has been deleted (via DELETE_NETWORK_ONLY),
# that lock reason no longer applies, and wrapping in Editor may itself
# be causing "RuntimeError: cannot open". Try True first; if it raises
# the original "outside an edit session" error, set this back to False.
USE_BARE_CURSOR = True


# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------

def main():

    if DELETE_NETWORK_ONLY:
        if arcpy.Exists(NETWORK_DATASET):
            print(f"Deleting network dataset: {NETWORK_DATASET}")
            arcpy.management.Delete(NETWORK_DATASET)
            print("Done. Now run this script again with DELETE_NETWORK_ONLY = False")
            print("in a FRESH process (new PyCharm run / new interpreter), not this")
            print("same session, to patch Edge1End.")
        else:
            print(f"Network dataset not present, nothing to delete: {NETWORK_DATASET}")
            print("Proceed to run this script with DELETE_NETWORK_ONLY = False.")
        return

    if not arcpy.Exists(PATCH_TURN_FC):
        print(f"ERROR: turn FC not found: {PATCH_TURN_FC}")
        sys.exit(1)

    fields = [f.name for f in arcpy.ListFields(PATCH_TURN_FC)]
    if "Edge1End" not in fields:
        print("ERROR: Edge1End field not found on this turn FC. Nothing to patch.")
        sys.exit(1)
    if "Edge1Pos" not in fields:
        print("ERROR: Edge1Pos field not found on this turn FC. Cannot compute Edge1End.")
        sys.exit(1)

    total = 0
    changed_to_y = 0
    changed_to_n = 0
    already_correct = 0
    null_pos = 0

    if not APPLY_UPDATE:
        print("APPLY_UPDATE is False -- previewing counts only, no changes will be written.\n")

    fields_to_read = ["Edge1End", "Edge1Pos"]

    def run_pass(cur):
        nonlocal total, already_correct, changed_to_y, changed_to_n, null_pos
        for row in cur:
            total += 1
            current_end = row[0]
            pos = row[1]

            if pos is None:
                null_pos += 1
                continue

            correct_end = "Y" if pos >= 0.5 else "N"

            if current_end == correct_end:
                already_correct += 1
                continue

            if correct_end == "Y":
                changed_to_y += 1
            else:
                changed_to_n += 1

            if APPLY_UPDATE:
                row = (correct_end, pos)
                cur.updateRow(row)

    if APPLY_UPDATE:
        if arcpy.Exists(NETWORK_DATASET):
            print(f"WARNING: {NETWORK_DATASET} still exists. This may re-trigger the")
            print("controller-dataset lock or stale-connection issue. Run this script")
            print("with DELETE_NETWORK_ONLY = True first, in its own process, then run")
            print("this patch step in a fresh process.")

        if USE_BARE_CURSOR:
            print("Using a bare UpdateCursor, no arcpy.da.Editor session.")
            with arcpy.da.UpdateCursor(PATCH_TURN_FC, fields_to_read) as cur:
                run_pass(cur)
        else:
            # multiuser_mode must match this workspace's actual versioning
            # state, rather than being guessed. isVersioned tells us directly.
            is_versioned = arcpy.Describe(PATCH_TURN_FC).isVersioned
            print(f"Detected isVersioned = {is_versioned} for {PATCH_TURN_FC}")
            print(f"Using multiuser_mode = {is_versioned}")

            editor = arcpy.da.Editor(SDE)
            editor.startEditing(False, is_versioned)
            editor.startOperation()
            try:
                with arcpy.da.UpdateCursor(PATCH_TURN_FC, fields_to_read) as cur:
                    run_pass(cur)
                editor.stopOperation()
                editor.stopEditing(True)
            except Exception:
                editor.stopOperation()
                editor.stopEditing(False)
                raise
    else:
        with arcpy.da.SearchCursor(PATCH_TURN_FC, fields_to_read) as cur:
            run_pass(cur)

    print("=" * 50)
    print(f"Total turn records:           {total}")
    print(f"Already correct:              {already_correct}")
    print(f"Corrected to 'Y':             {changed_to_y}")
    print(f"Corrected to 'N':             {changed_to_n}")
    print(f"Null Edge1Pos (left as-is):   {null_pos}")
    print("=" * 50)

    if APPLY_UPDATE:
        print(f"\nEdge1End patched on {changed_to_y + changed_to_n} records.")
        print("Next step: run scripts/03_create_network_dataset.py to recreate and")
        print("rebuild TRNLRS_street_network (it will skip re-copying the three")
        print("source FCs since they already exist, and go straight to create + build).")
    else:
        print(f"\nWould patch {changed_to_y + changed_to_n} records. Set APPLY_UPDATE = True to apply.")


if __name__ == "__main__":
    main()