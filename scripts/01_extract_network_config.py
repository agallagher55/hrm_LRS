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
            "name":         src.name,
            "source_id":    src.sourceID,
            "source_type":  src.sourceType,    # EdgeFeature | JunctionFeature | Turn | SystemJunction
            "element_type": src.elementType,   # Edge | Junction | Turn
        }
        # Elevation fields (edge sources carry from/to; junction sources carry a single field)
        if hasattr(src, "fromElevationFieldName"):
            s["from_elevation_field"] = src.fromElevationFieldName
        if hasattr(src, "toElevationFieldName"):
            s["to_elevation_field"] = src.toElevationFieldName
        if hasattr(src, "elevationFieldName"):
            s["elevation_field"] = src.elevationFieldName
        # Connectivity policies — indexed by subTypeConnCount (EndPoint | AnyVertex | Override)
        conn_count = getattr(src, "subTypeConnCount", 0)
        if conn_count:
            s["connectivity_policies"] = [
                {
                    "subtype": getattr(src, f"connSubtype{i}", None),
                    "policy":  getattr(src, f"connPolicy{i}", None),
                }
                for i in range(conn_count)
            ]
        # Connectivity group memberships — indexed by connGroupCount
        group_count = getattr(src, "connGroupCount", 0)
        if group_count:
            s["connectivity_groups"] = [
                getattr(src, f"connGroupIndex{i}", None) for i in range(group_count)
            ]
        sources.append(s)
    return sources


def describe_attributes(nd_desc):
    """Return a list of dicts for every network attribute (cost, restriction, descriptor, hierarchy)."""
    attributes = []
    for attr in nd_desc.attributes:
        a = {
            "name":           attr.name,
            "usage_type":     attr.usageType,     # Cost | Descriptor | Restriction | Hierarchy
            "data_type":      attr.dataType,      # Double | Integer | Float | Boolean
            "units":          attr.units,         # Meters | Feet | Minutes | Hours | Unknown …
            "default_value":  attr.defaultValue,
            "use_by_default": getattr(attr, "useByDefault", None),
            # Default evaluator types/data apply when no source-specific evaluator overrides
            "default_edge_evaluator_type":     getattr(attr, "defaultEdgeEvaluatorType", None),
            "default_edge_data":               getattr(attr, "defaultEdgeData", None),
            "default_junction_evaluator_type": getattr(attr, "defaultJunctionEvaluatorType", None),
            "default_junction_data":           getattr(attr, "defaultJunctionData", None),
            "default_turn_evaluator_type":     getattr(attr, "defaultTurnEvaluatorType", None),
            "default_turn_data":               getattr(attr, "defaultTurnData", None),
            "evaluators":  [],
            "parameters":  [],
        }
        # arcpy.Describe exposes evaluators as indexed dynamic properties, not a list.
        # evaluatorTypeN / sourceNameN / edgeDirectionN / dataN, gated by evaluatorCount.
        ev_count = getattr(attr, "evaluatorCount", 0)
        for i in range(ev_count):
            a["evaluators"].append({
                "source":         getattr(attr, f"sourceName{i}", None),
                "edge_direction": getattr(attr, f"edgeDirection{i}", None),  # FROM_TO | TO_FROM
                "evaluator_type": getattr(attr, f"evaluatorType{i}", None),  # Field | Constant | Script | Function | None
                # "data" carries field name for Field, constant for Constant, expression for Script
                "data":           getattr(attr, f"data{i}", None),
            })
        # Attribute parameters (used by parameterized restrictions/costs) — also indexed
        p_count = getattr(attr, "parameterCount", 0)
        for i in range(p_count):
            a["parameters"].append({
                "name":          getattr(attr, f"parameterName{i}", None),
                "type":          getattr(attr, f"parameterType{i}", None),
                "default_value": getattr(attr, f"parameterDefaultValue{i}", None),
            })
        attributes.append(a)
    return attributes


def describe_directions(nd_desc):
    """Return directions configuration if present."""
    if not getattr(nd_desc, "supportsDirections", False):
        return None
    d = getattr(nd_desc, "directions", None)
    if d is None:
        return None
    return {
        "length_attribute":      getattr(d, "lengthAttributeName", None),
        "time_attribute":        getattr(d, "timeAttributeName", None),
        "road_class_attribute":  getattr(d, "roadClassAttributeName", None),
        "reporting_units":       getattr(d, "reportingUnits", None),
        "directions_field_mappings": [
            {"field_type": fm.fieldType, "field_name": fm.fieldName}
            for fm in getattr(d, "fieldMappings", [])
        ],
    }


def describe_traffic(nd_desc):
    """Return traffic configuration if present."""
    if not getattr(nd_desc, "supportsHistoricalTrafficData", False):
        return None
    t = getattr(nd_desc, "trafficData", None)
    if t is None:
        return None
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
        "network_type":         getattr(desc, "networkType", None),      # GEODATABASE | SHAPEFILE | SDC
        "elevation_model":      getattr(desc, "elevationModel", None),   # NONE | Z_COORDINATE | ELEVATION_FIELDS
        "supports_turns":       getattr(desc, "supportsTurns", None),
        "supports_directions":  getattr(desc, "supportsDirections", None),
        "is_buildable":         getattr(desc, "isBuildable", None),
        "time_zone_attribute":  getattr(desc, "timeZoneAttributeName", None),
        "time_zone_table":      getattr(desc, "timeZoneTableName", None),
        "optimizations":        list(getattr(desc, "optimizations", None) or []),
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
