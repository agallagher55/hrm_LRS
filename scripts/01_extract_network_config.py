"""
Extract all configuration and properties from the old TRN_street_network dataset.

Outputs:
  - data/network_config.json   : human-readable summary of every ND property
  - data/network_template.xml  : ArcGIS XML template (used later to create the new ND)

Run from ArcGIS Pro Python environment:
  > python scripts/01_extract_network_config.py
"""

import json
import os
import sys
from pathlib import Path

import arcpy

# ---------------------------------------------------------------------------
# Configuration — update these paths before running
# ---------------------------------------------------------------------------
SDE_CONNECTION = r"E:\HRM\Scripts\SDE\SQL\qa_RW_sdeadm.sde"
NETWORK_DATASET = os.path.join(SDE_CONNECTION, "SDEADM.TRN_streets_routes")

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_JSON = REPO_ROOT / "data" / "network_config.json"
OUTPUT_XML  = REPO_ROOT / "data" / "network_template.xml"
# ---------------------------------------------------------------------------


def describe_sources(nd_desc):
    """Return a list of dicts describing each network source."""
    sources = []
    for src in nd_desc.sources:
        s = {
            "name":        src.name,
            "source_type": src.sourceType,    # EdgeFeature | JunctionFeature | TurnFeature | SystemJunction
            "element_type": src.elementType,  # Edge | Junction | Turn
        }
        # Edge-specific connectivity policy
        if hasattr(src, "fromToConnectivityPolicy"):
            s["from_to_connectivity_policy"] = src.fromToConnectivityPolicy
        if hasattr(src, "connectivity"):
            # connectivity is a list of NetworkEdgeConnectivity objects
            groups = []
            for c in src.connectivity:
                groups.append({
                    "group":  c.connectivityGroup,
                    "policy": c.edgeConnectivityPolicy,  # EndPoint | AnyVertex
                })
            s["connectivity_groups"] = groups
        sources.append(s)
    return sources


def describe_attributes(nd_desc):
    """Return a list of dicts for every network attribute (cost, restriction, descriptor, hierarchy)."""
    attributes = []
    for attr in nd_desc.attributes:
        a = {
            "name":          attr.name,
            "usage_type":    attr.usageType,    # Cost | Descriptor | Restriction | Hierarchy
            "data_type":     attr.dataType,     # Double | Integer | Float | Boolean | String
            "units":         attr.units,        # Meters | Feet | Minutes | Hours | Unknown …
            "default_value": getattr(attr, "defaultValue", None),
            "use_by_default": getattr(attr, "useByDefault", None),
            "evaluators":    [],
        }
        for ev in attr.evaluators:
            evaluator = {
                "source":         ev.source.name,
                "element_type":   ev.elementType,   # Edge | Junction | Turn
                "evaluator_type": ev.evaluatorType, # Field | Constant | Script | NetworkEdge …
            }
            # Field evaluator → capture field name and any Python expression
            if ev.evaluatorType == "Field":
                evaluator["field_name"] = getattr(ev, "fieldName", None)
                evaluator["expression"] = getattr(ev, "expression", None)
                evaluator["pre_logic"]  = getattr(ev, "preLogicScriptCode", None)
            elif ev.evaluatorType == "Constant":
                evaluator["constant_value"] = getattr(ev, "constantValue", None)
            elif ev.evaluatorType == "Script":
                evaluator["expression"] = getattr(ev, "expression", None)
                evaluator["pre_logic"]  = getattr(ev, "preLogicScriptCode", None)
            a["evaluators"].append(evaluator)
        attributes.append(a)
    return attributes


def describe_directions(nd_desc):
    """Return directions configuration if present."""
    if not hasattr(nd_desc, "directions"):
        return None
    d = nd_desc.directions
    return {
        "length_attribute":    getattr(d, "lengthAttributeName", None),
        "time_attribute":      getattr(d, "timeAttributeName", None),
        "road_class_attribute": getattr(d, "roadClassAttributeName", None),
        "reporting_units":     getattr(d, "reportingUnits", None),
        "directions_field_mappings": [
            {"field_type": fm.fieldType, "field_name": fm.fieldName}
            for fm in getattr(d, "fieldMappings", [])
        ],
    }


def describe_traffic(nd_desc):
    """Return traffic configuration if present."""
    if not hasattr(nd_desc, "trafficData"):
        return None
    t = nd_desc.trafficData
    return {
        "type":                    getattr(t, "type", None),
        "speed_profiles_table":    getattr(t, "speedProfilesTableName", None),
        "traffic_feed_locations":  getattr(t, "trafficFeedLocations", None),
        "historical_traffic_attr": getattr(t, "historicalTrafficAttributeNames", None),
        "live_traffic_attr":       getattr(t, "liveTrafficAttributeNames", None),
    }


def extract_config(network_dataset_path):
    """Describe the network dataset and return a config dict."""
    print(f"Describing: {network_dataset_path}")
    desc = arcpy.Describe(network_dataset_path)
    if desc.dataType != "NetworkDataset":
        sys.exit(
            f"ERROR: '{network_dataset_path}' is a {desc.dataType!r}, not a NetworkDataset.\n"
            "Update NETWORK_DATASET to point to the network dataset itself, not its source feature class."
        )

    config = {
        "network_dataset_name": desc.name,
        "catalog_path":         desc.catalogPath,
        "network_type":         getattr(desc, "networkType", None),  # Geodatabase | Shapefile | SDC
        "elevation_model":      getattr(desc, "elevationModel", None),
        "supports_turns":       getattr(desc, "supportsTurns", None),
        "time_zone_attribute":  getattr(desc, "timeZoneAttributeName", None),
        "time_zone_table":      getattr(desc, "timeZoneTableName", None),
        "sources":              describe_sources(desc),
        "attributes":           describe_attributes(desc),
        "directions":           describe_directions(desc),
        "traffic":              describe_traffic(desc),
    }
    return config


def export_xml_template(network_dataset_path, output_xml):
    """
    Export the network dataset as an XML template.
    This is the authoritative source for recreating the dataset — it captures
    everything including connectivity rules, evaluators, and directions config.
    """
    print(f"Exporting XML template → {output_xml}")
    arcpy.na.CreateTemplateFromNetworkDataset(
        network_dataset=network_dataset_path,
        output_network_dataset_template=str(output_xml),
    )
    print("XML template exported.")


def main():
    if not arcpy.Exists(NETWORK_DATASET):
        sys.exit(f"ERROR: Cannot find network dataset at:\n  {NETWORK_DATASET}\nCheck SDE_CONNECTION and NETWORK_DATASET paths.")

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    # 1. Programmatic describe → JSON
    config = extract_config(NETWORK_DATASET)
    with open(OUTPUT_JSON, "w") as f:
        json.dump(config, f, indent=2, default=str)
    print(f"Config written → {OUTPUT_JSON}")

    # 2. XML template export
    export_xml_template(NETWORK_DATASET, OUTPUT_XML)

    # 3. Quick summary to console
    print("\n--- Summary ---")
    print(f"  Sources    : {len(config['sources'])}")
    for s in config["sources"]:
        print(f"    [{s['source_type']:20s}] {s['name']}")

    print(f"  Attributes : {len(config['attributes'])}")

    for a in config["attributes"]:
        ev_count = len(a["evaluators"])
        print(f"    [{a['usage_type']:12s}] {a['name']} ({a['units']}) — {ev_count} evaluator(s)")

    if config["directions"]:
        print(f"  Directions : length={config['directions']['length_attribute']}, "
              f"time={config['directions']['time_attribute']}")

    if config["traffic"]:
        print(f"  Traffic    : {config['traffic']['type']}")


if __name__ == "__main__":
    main()
