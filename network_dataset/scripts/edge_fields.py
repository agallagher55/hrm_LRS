"""
The empty speed and travel time fields on the network's edge source.

Robbie Evans asked for a speed field and a travel time field on the edge class, left blank for
now (2026-10-08). Both networks are meant to have travel time eventually; E_SpeedLimit cannot
yet be segmented into TRNLRS_TRN_STREET_VW (see docs/network_build_status.md, "Travel time cost
attribute"), so nothing fills them. No network attribute uses them either.

The names follow E_SpeedLimit (SPEED, km/h). If SPEED and TRAVEL_TIME are later added to the
standalone TRNLRS_TRN_STREET_VW, the edge sync matches fields by name, so they will line up.

The edge copy is rebuilt from the standalone class on every QA refresh, which drops fields
that are not in it. Script 03 therefore adds these after the copy, and 08_add_edge_fields.py
adds them to an edge copy that already exists.
"""

import arcpy

# (name, arcpy field type, alias)
TRAVEL_FIELDS = [
    ("SPEED", "SHORT", "Speed (km/h)"),
    ("TRAVEL_TIME", "DOUBLE", "Travel time (min)"),
]


def missing_fields(existing_names, wanted=None):
    """The (name, type, alias) entries of wanted that are not in existing_names, ignoring case."""
    existing = {str(name).lower() for name in existing_names}

    return [field for field in (wanted or TRAVEL_FIELDS) if field[0].lower() not in existing]


def add_travel_fields(edge_fc, logger):
    """Add whichever of the speed and travel time fields the edge class lacks. Returns the names added."""
    existing = [f.name for f in arcpy.ListFields(edge_fc)]
    to_add = missing_fields(existing)

    if not to_add:
        logger.info(f"Speed and travel time fields already present on {edge_fc}")
        return []

    for name, field_type, alias in to_add:
        logger.info(f"Adding field {name} ({field_type}) to {edge_fc}")
        arcpy.management.AddField(edge_fc, name, field_type, field_alias=alias)

    return [name for name, _, _ in to_add]
