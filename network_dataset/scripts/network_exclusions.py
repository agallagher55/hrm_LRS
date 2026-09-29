"""
Street segments that are left out of the network dataset's edge source.

The exclusions are applied where the edge source is copied into the network
feature dataset (TRNLRS_TRN_STREET), by 03_create_network_dataset.py and
04_sync_and_rebuild_network.py. They are deliberately NOT applied to the
authoritative TRNLRS_TRN_STREET_VW, which is an org-wide product with
consumers this project has not audited (geocoding among them). Filtering only
the network copy leaves those consumers untouched.

Add to EXCLUDED_STR_TYPES / EXCLUDED_FDMIDS below, then re-run script 03 (after
deleting the existing edge copy) or script 04 so the change reaches the network.

Notes:
  - The exclusion is expressed as a "keep" clause with explicit NULL handling.
    A plain NOT IN (...) would silently drop rows whose STR_TYPE or FDMID is
    NULL, because NOT (NULL IN (...)) is unknown in SQL.
  - Turns that reference an excluded edge are skipped by the turn remap
    (05_rebuild_traffic_turns.py reads the edge copy), and user junctions that
    only touched excluded edges show up as extra standalone-junction warnings
    at build time. Both are expected.
  - arcpy is imported inside the functions that need it so the clause builders
    can be tested outside ArcGIS Pro.
"""

# STR_TYPE codes to drop. WA = water access roads. Robbie Evans and Melanie
# Parker asked for these to be removed (2026-09-23, confirmed 2026-09-29).
EXCLUDED_STR_TYPES = ["WA"]

# FDMIDs to drop (Long values). Island segments such as McNabs Island, which
# cannot route. Melanie Parker is supplying the list or filter (2026-09-24), so
# this is empty until she does.
EXCLUDED_FDMIDS = []


def _type_list():
    return ", ".join("'{}'".format(t.replace("'", "''")) for t in EXCLUDED_STR_TYPES)


def _id_list():
    return ", ".join(str(int(i)) for i in EXCLUDED_FDMIDS)


def build_exclude_clause():
    """Return a SQL where clause selecting the edges to drop, or None."""
    clauses = []

    if EXCLUDED_STR_TYPES:
        clauses.append("STR_TYPE IN ({})".format(_type_list()))

    if EXCLUDED_FDMIDS:
        clauses.append("FDMID IN ({})".format(_id_list()))

    if not clauses:
        return None

    return " OR ".join(clauses)


def build_keep_clause():
    """Return a SQL where clause selecting the edges to keep, or None if nothing is excluded."""
    clauses = []

    if EXCLUDED_STR_TYPES:
        clauses.append("(STR_TYPE IS NULL OR STR_TYPE NOT IN ({}))".format(_type_list()))

    if EXCLUDED_FDMIDS:
        clauses.append("(FDMID IS NULL OR FDMID NOT IN ({}))".format(_id_list()))

    if not clauses:
        return None

    return " AND ".join(clauses)


def _count(layer_or_fc):
    import arcpy

    return int(arcpy.management.GetCount(layer_or_fc)[0])


def make_filtered_layer(source_fc, layer_name, logger):
    """
    Return a feature layer over source_fc containing only the edges to keep, and
    log how many rows were kept and excluded.

    Raises RuntimeError if the filter would leave no edges at all, which means
    the clause or the source is wrong.
    """
    import arcpy

    keep_clause = build_keep_clause()
    total = _count(source_fc)

    if keep_clause is None:
        logger.info("No edge exclusions configured; using all {:,} edges.".format(total))
        return arcpy.management.MakeFeatureLayer(source_fc, layer_name)[0]

    layer = arcpy.management.MakeFeatureLayer(source_fc, layer_name, keep_clause)[0]
    kept = _count(layer)
    excluded = total - kept

    logger.info(
        "Edge exclusions applied (STR_TYPE {}, {} FDMIDs): {:,} of {:,} kept, {:,} excluded.".format(
            EXCLUDED_STR_TYPES, len(EXCLUDED_FDMIDS), kept, total, excluded
        )
    )

    if kept == 0:
        raise RuntimeError(
            "The edge exclusions removed every edge from {}. Check the clause: {}".format(
                source_fc, keep_clause
            )
        )

    if EXCLUDED_STR_TYPES and excluded == 0:
        logger.warning(
            "EXCLUDED_STR_TYPES is set but no rows matched in {}. Confirm the STR_TYPE code "
            "against the field's domain.".format(source_fc)
        )

    return layer


def count_excluded(fc, logger):
    """
    Count rows in an existing edge copy that match the exclusions. Used to warn when a
    copy is skipped because it already exists, since a stale copy may still hold them.
    Returns 0 when nothing is configured.
    """
    import arcpy

    exclude_clause = build_exclude_clause()

    if exclude_clause is None:
        return 0

    layer = arcpy.management.MakeFeatureLayer(fc, "existing_edge_copy_excluded", exclude_clause)[0]
    n = _count(layer)
    arcpy.management.Delete(layer)

    if n:
        logger.warning(
            "The existing edge copy {} still holds {:,} rows that match the current "
            "exclusions. Delete the network and the copy and re-run, or run script 04.".format(fc, n)
        )

    return n
