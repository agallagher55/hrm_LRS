"""
Compare the schema of the old edge source (TRN_street) against the new LRS
view (TRNLRS_TRN_STREET_VW) and cross-reference with the network attribute
evaluators captured in data/network_config.json.

Outputs:
  - data/schema_comparison.json   : full field-level diff
  - data/evaluator_field_map.json : which evaluator field references need
                                    updating (or confirming) in the new source

Run from ArcGIS Pro Python environment:
  > python scripts/02_compare_schemas.py
"""

import json
from pathlib import Path

import arcpy

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SDE_CONNECTION = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"

OLD_EDGE_SOURCE = "SDEADM.TRN_street"
NEW_EDGE_SOURCE = "SDEADM.TRNLRS_TRN_STREET_VW"

REPO_ROOT        = Path(__file__).resolve().parents[1]
INPUT_JSON       = REPO_ROOT / "data" / "network_config.json"
OUTPUT_SCHEMA    = REPO_ROOT / "data" / "schema_comparison.json"
OUTPUT_FIELD_MAP = REPO_ROOT / "data" / "evaluator_field_map.json"
# ---------------------------------------------------------------------------

# Fields automatically managed by ArcGIS — skip in comparison
SYSTEM_FIELDS = {
    "OBJECTID", "SHAPE", "SHAPE.STLENGTH()", "SHAPE_LENGTH",
    "GLOBALID", "CREATED_USER", "CREATED_DATE", "LAST_EDITED_USER", "LAST_EDITED_DATE",
}


def get_fields(fc_path):
    """Return {field_name_upper: Field object} for a feature class."""
    fields = {}
    for f in arcpy.ListFields(fc_path):
        if f.name.upper() not in SYSTEM_FIELDS:
            fields[f.name.upper()] = {
                "name":       f.name,
                "alias":      f.aliasName,
                "type":       f.type,
                "length":     f.length,
                "precision":  f.precision,
                "scale":      f.scale,
                "nullable":   f.isNullable,
                "domain":     f.domain,
            }
    return fields


def compare_schemas(old_fields, new_fields):
    """Return three groups: shared, only-in-old, only-in-new."""
    old_keys = set(old_fields)
    new_keys = set(new_fields)

    shared     = sorted(old_keys & new_keys)
    only_old   = sorted(old_keys - new_keys)
    only_new   = sorted(new_keys - old_keys)

    type_changes = {}
    for key in shared:
        o, n = old_fields[key], new_fields[key]
        diffs = {}
        if o["type"] != n["type"]:
            diffs["type"] = {"old": o["type"], "new": n["type"]}
        if o["length"] != n["length"]:
            diffs["length"] = {"old": o["length"], "new": n["length"]}
        if o["domain"] != n["domain"]:
            diffs["domain"] = {"old": o["domain"], "new": n["domain"]}
        if diffs:
            type_changes[key] = diffs

    return {
        "shared_fields":        [{"key": k, "old": old_fields[k], "new": new_fields[k]} for k in shared],
        "only_in_old_source":   [old_fields[k] for k in only_old],
        "only_in_new_source":   [new_fields[k] for k in only_new],
        "attribute_differences": type_changes,
    }


def map_evaluator_fields(config, old_fields, new_fields):
    """
    For every Field-type evaluator in the network config that references the
    edge source, determine whether the referenced field exists in the new source.
    Returns a list of evaluator field mapping records.
    """
    mappings = []
    for attr in config["attributes"]:
        for ev in attr["evaluators"]:
            if ev.get("evaluator_type") != "Field":
                continue
            field_ref = (ev.get("field_name") or "").upper()
            if not field_ref:
                continue
            record = {
                "attribute":      attr["name"],
                "usage_type":     attr["usage_type"],
                "source":         ev["source"],
                "element_type":   ev["element_type"],
                "field_name":     ev.get("field_name"),
                "expression":     ev.get("expression"),
                "in_old_source":  field_ref in old_fields,
                "in_new_source":  field_ref in new_fields,
                "status":         None,
            }
            if record["in_old_source"] and record["in_new_source"]:
                record["status"] = "OK — field exists in new source"
            elif record["in_old_source"] and not record["in_new_source"]:
                record["status"] = "ACTION REQUIRED — field missing from new source"
            elif not record["in_old_source"]:
                record["status"] = "WARNING — field not found in old source either (check manually)"
            mappings.append(record)
    return mappings


def main():
    old_path = f"{SDE_CONNECTION}\\{OLD_EDGE_SOURCE}"
    new_path = f"{SDE_CONNECTION}\\{NEW_EDGE_SOURCE}"

    for path, label in [(old_path, "old"), (new_path, "new")]:
        if not arcpy.Exists(path):
            raise FileNotFoundError(f"Cannot find {label} feature class: {path}")

    print(f"Reading fields: {OLD_EDGE_SOURCE}")
    old_fields = get_fields(old_path)
    print(f"Reading fields: {NEW_EDGE_SOURCE}")
    new_fields = get_fields(new_path)

    comparison = compare_schemas(old_fields, new_fields)

    with open(OUTPUT_SCHEMA, "w") as f:
        json.dump(comparison, f, indent=2)
    print(f"Schema comparison written → {OUTPUT_SCHEMA}")

    # Cross-reference evaluators
    if not INPUT_JSON.exists():
        print(f"WARNING: {INPUT_JSON} not found — run 01_extract_network_config.py first.")
        print("Skipping evaluator field mapping.")
        return

    with open(INPUT_JSON) as f:
        config = json.load(f)

    mappings = map_evaluator_fields(config, old_fields, new_fields)
    with open(OUTPUT_FIELD_MAP, "w") as f:
        json.dump(mappings, f, indent=2)
    print(f"Evaluator field map written → {OUTPUT_FIELD_MAP}")

    # Console summary
    print("\n--- Schema Comparison Summary ---")
    print(f"  Shared fields       : {len(comparison['shared_fields'])}")
    print(f"  Only in old source  : {len(comparison['only_in_old_source'])}")
    for f in comparison["only_in_old_source"]:
        print(f"    - {f['name']} ({f['type']})")
    print(f"  Only in new source  : {len(comparison['only_in_new_source'])}")
    for f in comparison["only_in_new_source"]:
        print(f"    + {f['name']} ({f['type']})")
    if comparison["attribute_differences"]:
        print(f"  Type/length changes : {len(comparison['attribute_differences'])}")
        for key, diffs in comparison["attribute_differences"].items():
            print(f"    ~ {key}: {diffs}")

    print("\n--- Evaluator Field Status ---")
    needs_action = [m for m in mappings if "ACTION REQUIRED" in (m["status"] or "")]
    ok_count     = sum(1 for m in mappings if "OK" in (m["status"] or ""))
    print(f"  OK                  : {ok_count}")
    print(f"  Action required     : {len(needs_action)}")
    for m in needs_action:
        print(f"    [{m['attribute']}] references '{m['field_name']}' — not in new source")



if __name__ == "__main__":
    main()
