"""
Street segments that are left out of a network dataset's edge source.

The exclusions are applied where the edge source is copied into the network
feature dataset (TRNLRS_TRN_STREET), by 03_create_network_dataset.py and
04_sync_and_rebuild_network.py. They are deliberately NOT applied to the
authoritative TRNLRS_TRN_STREET_VW, which is an org-wide product with
consumers this project has not audited (geocoding among them). Filtering only
the network copy leaves those consumers untouched.

Profiles
--------
Each network has its own exclusion profile:

  GENERAL  the distance network (TRNLRS_street_network). WA streets and islands.
           Transit access roads stay in (decided 2026-10-08).
  HRFE     the fire and emergency network. Everything in GENERAL, plus the extra
           exclusions Robbie Evans listed (email thread "HRFE network dataset",
           2026-09-01 to 2026-09-29): emergency access roads and ETAs, and the
           transit access roads, which stay out of HRFE.

Each network in network_definitions.py names its profile, and scripts 03 and 04 read
it from there, so an HRFE build (HRM_NETWORK=HRFE) uses HRFE. DEFAULT_PROFILE (GENERAL)
applies only when a caller passes no profile.

To change what a profile leaves out, edit the lists below, then re-run script 03
(after deleting the existing edge copy) or script 04 so the change reaches the
network. Run this file to print the clauses each profile produces.

Rule types
----------
  str_types      STR_TYPE codes, matched exactly.
  fdmids         FDMID values (Long), matched exactly.
  name_patterns  FULL_NAME LIKE patterns. The % and _ wildcards (and the SQL
                 Server [0-9] range) are passed through unescaped on purpose.
                 Case sensitivity follows the database collation.

Notes:
  - Each rule is expressed as a "keep" clause with explicit NULL handling. A
    plain NOT IN (...) or NOT LIKE would silently drop rows whose STR_TYPE,
    FDMID or FULL_NAME is NULL, because NOT (NULL IN (...)) is unknown in SQL.
  - Turns that reference an excluded edge are skipped by the turn remap
    (05_rebuild_traffic_turns.py reads the edge copy), and user junctions that
    only touched excluded edges show up as extra standalone-junction warnings
    at build time. Both are expected.
  - A rule that matches no rows is logged as a warning, because it usually
    means a wrong code or pattern. A rule that matches too many rows is not
    detectable here; check the per-rule counts in the log against the diagnostic
    (diagnostics/10_find_candidate_exclusions.py).
  - arcpy is imported inside the functions that need it so the clause builders
    can be tested outside ArcGIS Pro.
"""

# Island segments (McNabs Island and George's Island), which cannot route. They apply
# to every network. Robbie Evans sent these 14 FDMIDs on 2026-10-08. Melanie Parker was
# also going to supply a list or filter (2026-09-24), so add any islands hers covers
# that these do not.
ISLAND_FDMIDS = [
    700000538,
    700000539,
    700000540,
    700000541,
    700000542,
    700000543,
    700000544,
    700000545,
    700000546,
    700000548,
    700000549,
    700002434,
    700002435,
    700009601,
]

# WA = water access roads. Robbie Evans and Melanie Parker asked for these to be
# removed (2026-09-23, confirmed 2026-09-29; Robbie confirmed STR_TYPE = 'WA' on
# 2026-09-17).
#
# Transit access roads are NOT excluded here. On 2026-09-29 they were removed from every
# network, but in the 2026-10-08 meeting the group decided to leave them in the distance
# network unless somebody complains, because some business units use them as roads. They
# stay out of the HRFE network (Alex, 2026-10-08), so the pattern lives in HRFE_EXTRA below.
#
# UNDER REVIEW streets (LRS placeholders named like "UNDER REVIEW 329", STR_TYPE 'UN')
# are deliberately NOT excluded: a requirement to drop them on 2026-09-29 was withdrawn
# the same day.
GENERAL_PROFILE = {
    "str_types": ["WA"],
    "fdmids": list(ISLAND_FDMIDS),
    "name_patterns": [],
}

# Extra HRFE exclusions, from Robbie Evans's 2026-09-01 and 2026-09-17 emails.
#
#   Transit access roads: named "TA# RD". Run against Prod on 2026-09-29, 'TA[0-9]%'
#   matches 124 rows (TA1 to TA52, all STR_TYPE RD); the looser 'TA%' adds 85 ordinary
#   streets. Robbie confirmed on 2026-09-29 that no transit road has another name. All
#   124 go from HRFE, with no exceptions. The distance network keeps them.
#
#   Emergency access roads: confirmed. He gave the query and says there are
#   exactly 4 (Highland Park, Buckingham Dr x2, Westwood Blvd, each "EMERGENCY
#   ACCESS 01").
#
#   ETAs (emergency turnarounds): small connectors between divided highways, 22
#   rows named "HIGHWAY nnn ETA n" ('% ETA [0-9]%'). Robbie confirmed on
#   2026-09-29 this is the full set and that HRFE routes are calculated without
#   them. Emergency access roads are evacuation only.
#
#   Expected effect on the HRFE edge copy: 211 rows from WA, transit, emergency
#   access and ETAs (61 + 124 + 4 + 22, no shared FDMIDs), leaving 18,433 of 18,644.
#   The general copy loses WA only (61 rows), leaving 18,583.
#
#   Record: docs/meetings/2026-09-29_HRFE_network_dataset_email_thread.md
HRFE_EXTRA = {
    "str_types": [],
    "fdmids": [],
    "name_patterns": ["TA[0-9]%", "%EMERGENCY ACCESS%", "% ETA [0-9]%"],
}

DEFAULT_PROFILE = "GENERAL"


def _merge(*specs):
    """Combine profile specs, keeping order and dropping repeated values."""
    merged = {"str_types": [], "fdmids": [], "name_patterns": []}

    for spec in specs:

        for key in merged:

            for value in spec.get(key, []):

                if value not in merged[key]:
                    merged[key].append(value)

    return merged


PROFILES = {
    "GENERAL": _merge(GENERAL_PROFILE),
    "HRFE": _merge(GENERAL_PROFILE, HRFE_EXTRA),
}


def _get_profile(profile):
    try:
        return PROFILES[profile]

    except KeyError:
        raise ValueError(
            "Unknown exclusion profile {!r}. Choose one of: {}".format(
                profile, ", ".join(sorted(PROFILES))
            )
        )


def _quote(value):
    return "'{}'".format(str(value).replace("'", "''"))


def get_rules(profile=DEFAULT_PROFILE):
    """
    Return the profile's rules as a list of (label, exclude_clause, keep_clause).

    exclude_clause selects the rows the rule drops. keep_clause selects the rest,
    NULL-safe. A rule is one STR_TYPE list, one FDMID list, or one name pattern.
    """
    spec = _get_profile(profile)
    rules = []

    if spec["str_types"]:
        values = ", ".join(_quote(t) for t in spec["str_types"])
        rules.append((
            "STR_TYPE in {}".format(spec["str_types"]),
            "STR_TYPE IN ({})".format(values),
            "(STR_TYPE IS NULL OR STR_TYPE NOT IN ({}))".format(values),
        ))

    if spec["fdmids"]:
        values = ", ".join(str(int(i)) for i in spec["fdmids"])
        rules.append((
            "FDMID list ({} ids)".format(len(spec["fdmids"])),
            "FDMID IN ({})".format(values),
            "(FDMID IS NULL OR FDMID NOT IN ({}))".format(values),
        ))

    for pattern in spec["name_patterns"]:
        rules.append((
            "FULL_NAME like {}".format(_quote(pattern)),
            "FULL_NAME LIKE {}".format(_quote(pattern)),
            "(FULL_NAME IS NULL OR FULL_NAME NOT LIKE {})".format(_quote(pattern)),
        ))

    return rules


def build_exclude_clause(profile=DEFAULT_PROFILE):
    """Return a SQL where clause selecting the edges to drop, or None."""
    rules = get_rules(profile)

    if not rules:
        return None

    return " OR ".join(exclude for _, exclude, _ in rules)


def build_keep_clause(profile=DEFAULT_PROFILE):
    """Return a SQL where clause selecting the edges to keep, or None if nothing is excluded."""
    rules = get_rules(profile)

    if not rules:
        return None

    return " AND ".join(keep for _, _, keep in rules)


def _count(layer_or_fc):
    import arcpy

    return int(arcpy.management.GetCount(layer_or_fc)[0])


def _count_matches(source_fc, layer_name, where_clause):
    """Count the rows of source_fc that match where_clause, without leaving a layer behind."""
    import arcpy

    layer = arcpy.management.MakeFeatureLayer(source_fc, layer_name, where_clause)[0]
    n = _count(layer)
    arcpy.management.Delete(layer)

    return n


def make_filtered_layer(source_fc, layer_name, logger, profile=DEFAULT_PROFILE):
    """
    Return a feature layer over source_fc containing only the edges to keep, and
    log how many rows were kept and excluded, overall and per rule.

    Raises RuntimeError if the filter would leave no edges at all, which means
    the clause or the source is wrong.
    """
    import arcpy

    keep_clause = build_keep_clause(profile)
    total = _count(source_fc)

    if keep_clause is None:
        logger.info("No edge exclusions configured; using all {:,} edges.".format(total))
        return arcpy.management.MakeFeatureLayer(source_fc, layer_name)[0]

    layer = arcpy.management.MakeFeatureLayer(source_fc, layer_name, keep_clause)[0]
    kept = _count(layer)
    excluded = total - kept

    logger.info(
        "Edge exclusions applied (profile {}): {:,} of {:,} kept, {:,} excluded.".format(
            profile, kept, total, excluded
        )
    )

    # Rules can overlap, so the per-rule counts may add up to more than the total.
    for i, (label, exclude_clause, _) in enumerate(get_rules(profile)):
        matched = _count_matches(source_fc, "{}_rule{}".format(layer_name, i), exclude_clause)
        logger.info("  {}: {:,} rows".format(label, matched))

        if matched == 0:
            logger.warning(
                "  {} matched no rows in {}. Confirm the code or pattern against the "
                "data.".format(label, source_fc)
            )

    if kept == 0:
        raise RuntimeError(
            "The edge exclusions removed every edge from {}. Check the clause: {}".format(
                source_fc, keep_clause
            )
        )

    return layer


def count_excluded(fc, logger, profile=DEFAULT_PROFILE):
    """
    Count rows in an existing edge copy that match the exclusions. Used to warn when a
    copy is skipped because it already exists, since a stale copy may still hold them.
    Returns 0 when nothing is configured.
    """
    exclude_clause = build_exclude_clause(profile)

    if exclude_clause is None:
        return 0

    n = _count_matches(fc, "existing_edge_copy_excluded", exclude_clause)

    if n:
        logger.warning(
            "The existing edge copy {} still holds {:,} rows that match the {} "
            "exclusions. Delete the network and the copy and re-run, or run script 04.".format(
                fc, n, profile
            )
        )

    return n


if __name__ == "__main__":

    for name in sorted(PROFILES):
        print("{}:".format(name))

        for label, exclude_clause, keep_clause in get_rules(name):
            print("  {}".format(label))
            print("    exclude: {}".format(exclude_clause))
            print("    keep:    {}".format(keep_clause))
