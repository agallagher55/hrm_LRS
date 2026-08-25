import os

import arcpy
import time
import logging
import csv
import sys
import traceback

from configparser import ConfigParser
from datetime import datetime

from HRMutils import (
    setupLog,
    send_mail,
)

arcpy.env.overwriteOutput = True
arcpy.SetLogHistory(False)

config = ConfigParser()
config.read(r"E:\HRM\Scripts\Python\config.ini")

log_file = os.path.join(
    config.get('LOGGING', 'logDir'),
    "LRS_Updates",
    f"{datetime.today().date()}_LRS_updates.log"
)

logger = setupLog(log_file)
log_server = config.get('LOGGING', 'serverName')

console_handler = logging.StreamHandler()
log_formatter = logging.Formatter(
    '%(asctime)s | %(levelname)s | FUNCTION: %(funcName)s | Msgs: %(message)s', datefmt='%d-%b-%y %H:%M:%S'
)
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

SDEADM_RW = config.get('SDEADM_RW', 'sdeFile')
SDEADM_RO = config.get('SDEADM_RO', 'sdeFile')

LRS_DIR = r"\\msfs203.hrm.halifax.ca\GISData\Data Sharing\LRS_operational"
LRS_GDB = os.path.join(LRS_DIR, "lrs_view.gdb")

LRS_VIEW_NAME = "TRNLRS_TRN_street_VW"
SDE_DYN_SEG_FEATURE_NAME = "TRNLRS_segmented_street_events"

SDE_SPEED_LIMIT_DYN_SEG_FEATURE_NAME = "TRNLRS_segmented_speed_limit_events"
SPEED_LIMIT_NEIGHBOURHOOD_FEATURE_NAME = "TRNLRS_SpeedLimit_Neighbourhood_VW"

SDE_SAFE_SCHOOL_STREETS_DYN_SEG_FEATURE_NAME = "TRNLRS_segmented_safe_school_streets_events"
SAFE_SCHOOL_STREETS_FEATURE_NAME = "TRNLRS_TRN_Safe_School_Streets_VW"

# Network dataset sync — keeps TRNLRS_TRN_STREET (FD copy used by the network)
# in sync with TRNLRS_TRN_STREET_VW (standalone authoritative FC).
# When TRNLRS_TRN_STREET_VW is eventually moved into the feature dataset
# permanently, remove these constants and the sync_network_edge_source() call.
# TRNLRS_network is a dedicated feature dataset for the network source FCs,
# separate from SDEADM.TRNLRS (the LRS feature dataset holding LRSN_Route and
# the E_* event tables).
TRNLRS_NETWORK_FD           = "SDEADM.TRNLRS_network"
NETWORK_FD_EDGE_COPY_NAME   = "TRNLRS_TRN_STREET"
NETWORK_DATASET_NAME        = "TRNLRS_street_network"

MTM5_SPATIAL_REFERENCE = (
    'PROJCS["NAD_1983_CSRS_2010_MTM_5_Nova_Scotia",'
    'GEOGCS["GCS_North_American_1983_CSRS_2010",'
    'DATUM["D_North_American_1983_CSRS",'
    'SPHEROID["GRS_1980",6378137.0,298.257222101]],'
    'PRIMEM["Greenwich",0.0],'
    'UNIT["Degree",0.0174532925199433]],'
    'PROJECTION["Transverse_Mercator"],'
    'PARAMETER["False_Easting",25500000.0],'
    'PARAMETER["False_Northing",0.0],'
    'PARAMETER["Central_Meridian",-64.5],'
    'PARAMETER["Scale_Factor",0.9999],'
    'PARAMETER["Latitude_Of_Origin",0.0],'
    'UNIT["Meter",1.0]]'
    ';19877400 -10001100 10000;-100000 10000;-100000 10000;0.001;0.001;0.001;IsHighPrecision'
)


class LicenseError(Exception):
    pass

class DynSegFeature:
    """Dynamic Segmentation Feature (result of overlay events GP tool)"""

    def __init__(self, sde_workspace: str=SDEADM_RW, feature_name: str=SDE_DYN_SEG_FEATURE_NAME):

        self.sde_workspace = sde_workspace
        self.feature_name = feature_name
        self.feature = os.path.join(sde_workspace, feature_name)

        self.event_tables = [
            rf'{self.sde_workspace}\SDEADM.TRNLRS\SDEADM.E_StreetDirection',
            rf'{self.sde_workspace}\SDEADM.TRNLRS\SDEADM.E_StreetClass',
            rf'{self.sde_workspace}\SDEADM.TRNLRS\SDEADM.E_AddressRange',
            rf'{self.sde_workspace}\SDEADM.TRNLRS\SDEADM.E_PSAB',
            rf'{self.sde_workspace}\SDEADM.TRNLRS\SDEADM.E_StreetOwnership',
            rf'{self.sde_workspace}\SDEADM.TRNLRS\SDEADM.E_StreetStatus',
            rf'{self.sde_workspace}\SDEADM.TRNLRS\SDEADM.E_WinterMaintenance',
        ]

        self.network_fields = "OBJECTID;FROMDATE;TODATE;ROUTEID;ROUTENAME;STR_NAME;STR_TYPE;MUN_CODE;GLOBALID"
        self.speed_limit_neighbourhood_event_tables = [
            rf'{self.sde_workspace}\SDEADM.TRNLRS\SDEADM.E_StreetClass',
            rf'{self.sde_workspace}\SDEADM.TRNLRS\SDEADM.E_SpeedLimit',
            rf'{self.sde_workspace}\SDEADM.TRNLRS\SDEADM.E_SpeedLimit_Neighbourhood',
        ]
        self.safe_school_streets_event_tables = [
            rf'{self.sde_workspace}\SDEADM.TRNLRS\SDEADM.E_SafeSchoolStreets',
            rf'{self.sde_workspace}\SDEADM.TRNLRS\SDEADM.E_District',
            rf'{self.sde_workspace}\SDEADM.TRNLRS\SDEADM.E_StreetClass',
        ]

    def _make_query_layer(self, query: str, layer_name: str = "out_layer"):
        """Create a polyline query layer using the standard spatial reference."""
        return arcpy.MakeQueryLayer_management(
            input_database=self.sde_workspace,
            out_layer_name=layer_name,
            query=query,
            oid_fields="OBJECTID",
            shape_type="POLYLINE",
            srid="0",
            spatial_reference=MTM5_SPATIAL_REFERENCE,
            m_values="DO_NOT_INCLUDE_M_VALUES",
            z_values="DO_NOT_INCLUDE_Z_VALUES",
        )[0]

    def update_dynamic_segmentation(self):
        """
        - Update LRS view by recreating the table that the view is derived from.
        :return:
        """

        try:

            logger.info(f"Overlaying events to create '{self.feature_name}'...")
            arcpy.locref.OverlayEvents(
                in_route_features=rf"{self.sde_workspace}\GISRW01.SDEADM.TRNLRS\GISRW01.SDEADM.LRSN_Route",
                event_layers=self.event_tables,
                output_dataset=self.feature,
                include_geometry="INCLUDE_GEOMETRY",
                network_fields=self.network_fields
            )
            logger.info(arcpy.GetMessages())

            logger.info(f"\tRecreated {self.feature}")

            arcpy.ChangePrivileges_management(
                in_dataset=self.feature,
                user="PUBLIC",
                View="GRANT",
            )

            return self.feature

        except arcpy.ExecuteError:
            run_error_processing(
                f"Error updating Dynamic Segmentation {self.feature_name}. Details: {str(arcpy.GetMessages(2))}"
            )


    def _update_streets(self, where_clause: str, out_feature: str):
        logger.info(f"Creating query layer with filter: '{where_clause}'")

        query = f"""
        SELECT
            e.OBJECTID,
            e.FCODE,
            e.STR_NAME,
            e.STR_TYPE,
            e.ROUTENAME AS FULL_NAME,
            e.MUN_CODE,
            e.FROM_STR,
            e.TO_STR,
            e.STR_DIR,
            e.STR_STATUS,
            e.ST_CLASS,
            e.OWN,
            e.MAINTENANCE,
            e.DATE_ACCEPT,
            e.COMMENT__2 AS STR_REM,
            e.FLAG AS FLAGS,
            e.PSAB_CODE,
            e.FDMID,
            e.SYS_DATE,
            e.ROUTE_ID,
            e.FROM_LEFT,
            e.TO_LEFT,
            e.FROM_RIGHT,
            e.TO_RIGHT,
            e.OLD_FDMID,
            e.GSA_LEFT,
            e.GSA_RIGHT,
            e.PAR_LEFT,
            e.PAR_RIGHT,
            e.STR_CODE_L,
            e.STR_CODE_R,
            e.ASSETID,
            e.ORIGIN_DATE,
            ea.MinAddDate AS ADDDATE,
            ea.MaxModDate AS MODDATE,
            e.SHAPE
        FROM {self.feature_name} e
        LEFT JOIN (
            SELECT
                FDMID,
                Min(ADDDATE) AS MinAddDate,
                MAX(MODDATE) AS MaxModDate
            FROM SDEADM.E_ADDRESSRANGE
            WHERE
                (GDB_IS_DELETE IS NULL OR GDB_IS_DELETE = 0)
            GROUP BY FDMID
        ) ea
        ON e.fdmid = ea.fdmid
        WHERE {where_clause}
        """

        query_layer = self._make_query_layer(query)

        record_count = int(arcpy.GetCount_management(query_layer)[0])
        logger.info(f"Row count: {record_count}")

        if record_count > 0:
            append_feature(query_layer, out_feature, self.sde_workspace)

    def _update_street_lanes(self, out_feature: str):

        # Lane data pulls from TRN_street. Hasn't been updated in a long time, and the geometry of the lane data isn't
        # perfect, so it causes duplicated FDMIDs and short segments if added to the dynamic segmentation

        logger.info("Creating street lanes query layer...")

        query = f"""
        SELECT
            lrs_streets.OBJECTID,
            lrs_streets.FCODE,
            lrs_streets.STR_NAME,
            lrs_streets.STR_TYPE,
            lrs_streets.FULL_NAME,
            lrs_streets.MUN_CODE,
            lrs_streets.FROM_STR,
            lrs_streets.TO_STR,
            lrs_streets.STR_DIR,
            lrs_streets.STR_STATUS,
            lrs_streets.ST_CLASS,
            lrs_streets.OWN,
            lrs_streets.MAINTENANCE,
            lrs_streets.DATE_ACCEPT,
            lrs_streets.STR_REM,
            lrs_streets.FLAGS,
            lrs_streets.PSAB_CODE,
            lrs_streets.FDMID,
            lrs_streets.ROUTE_ID,
            lrs_streets.FROM_LEFT,
            lrs_streets.TO_LEFT,
            lrs_streets.FROM_RIGHT,
            lrs_streets.TO_RIGHT,
            lrs_streets.OLD_FDMID,
            lrs_streets.GSA_LEFT,
            lrs_streets.GSA_RIGHT,
            lrs_streets.PAR_LEFT,
            lrs_streets.PAR_RIGHT,
            lrs_streets.STR_CODE_L,
            lrs_streets.STR_CODE_R,
            lrs_streets.ASSETID,
            lrs_streets.ADDDATE,
            lrs_streets.MODDATE,
            lrs_streets.SHAPE,
            LANECOUNT AS LANE
        FROM SDEADM.{LRS_VIEW_NAME} lrs_streets
        LEFT JOIN SDEADM.TRN_STREET trn_street
        ON lrs_streets.fdmid = trn_street.fdmid
        """

        query_layer = self._make_query_layer(query, layer_name="lanes_query_out_layer")

        record_count = int(arcpy.GetCount_management(query_layer)[0])
        logger.info(f"Row count: {record_count}")

        if record_count > 0:
            append_feature(query_layer, out_feature, self.sde_workspace)

        else:
            logger.info("Did not update.")
            return False

        return True

    def update_speed_limit_neighbourhood_segmentation(
            self,
            segmented_feature_name: str = SDE_SPEED_LIMIT_DYN_SEG_FEATURE_NAME    ):
        """Create a dynamic segmentation feature for speed limit neighbourhood review.

        The main street dynamic segmentation is intentionally left unchanged.
        This overlay uses only the events needed to expose speed, street class,
        and neighbourhood speed review status/effective date. If the source
        event class is named with Canadian spelling in a target database, pass
        ``neighbourhood_event_name="SDEADM.E_SpeedLimit_Neighbourhood"``.
        """

        segmented_feature = os.path.join(self.sde_workspace, segmented_feature_name)
        event_tables = self.speed_limit_neighbourhood_event_tables

        try:

            logger.info(f"Overlaying events to create '{segmented_feature_name}'...")
            arcpy.locref.OverlayEvents(
                in_route_features=rf"{self.sde_workspace}\GISRW01.SDEADM.TRNLRS\GISRW01.SDEADM.LRSN_Route",
                event_layers=event_tables,
                output_dataset=segmented_feature,
                include_geometry="INCLUDE_GEOMETRY",
                network_fields=self.network_fields
            )
            logger.info(arcpy.GetMessages())

            logger.info(f"\tRecreated {segmented_feature}")

            arcpy.ChangePrivileges_management(
                in_dataset=segmented_feature,
                user="PUBLIC",
                View="GRANT",
            )

            return segmented_feature

        except arcpy.ExecuteError:
            run_error_processing(
                f"Error updating Dynamic Segmentation {segmented_feature_name}. Details: {str(arcpy.GetMessages(2))}"
            )

    def update_speed_limit_neighbourhood(
            self,
            out_feature: str = SPEED_LIMIT_NEIGHBOURHOOD_FEATURE_NAME
    ):
        """Create the publishable speed-limit neighbourhood feature.

        ``out_feature`` should point to a feature class with the target fields
        ROUTEID, STR_NAME, FULL_NAME, ST_CLASS, SPEED, REVIEW_STAT,
        DATE_EFFECTIVE, ADDDATE, ADDBY, MODDATE, and MODBY. Audit fields are
        sourced from E_SpeedLimit_Neighbourhood (the defining event for this
        view), joined on ROUTEID, mirroring how the street view pulls audit
        dates from E_AddressRange. The source is the speed-limit-specific
        segmented feature generated by
        :meth:`update_speed_limit_neighbourhood_segmentation`.
        """

        logger.info("Creating speed limit neighbourhood query layer...")

        query = f"""
        SELECT
            e.OBJECTID,
            e.ROUTEID,
            e.STR_NAME,
            e.ROUTENAME AS FULL_NAME,
            e.ST_CLASS,
            e.SPEED,
            e.REVIEW_STAT,
            e.DATE_EFFECTIVE,
            sln.MinAddDate AS ADDDATE,
            sln.AddBy      AS ADDBY,
            sln.MaxModDate AS MODDATE,
            sln.ModBy      AS MODBY,
            e.SHAPE
        FROM {SDE_SPEED_LIMIT_DYN_SEG_FEATURE_NAME} e
        LEFT JOIN (
            SELECT
                ROUTEID,
                MIN(ADDDATE) AS MinAddDate,
                MIN(ADDBY)   AS AddBy,
                MAX(MODDATE) AS MaxModDate,
                MAX(MODBY)   AS ModBy
            FROM SDEADM.E_SpeedLimit
            WHERE TODATE IS NULL
              AND (GDB_IS_DELETE IS NULL OR GDB_IS_DELETE = 0)
            GROUP BY ROUTEID
        ) sln ON e.ROUTEID = sln.ROUTEID
        WHERE e.TO_DATE IS NULL
        """

        query_layer = self._make_query_layer(query, layer_name="speed_limit_neighbourhood_query_out_layer")

        record_count = int(arcpy.GetCount_management(query_layer)[0])
        logger.info(f"Row count: {record_count}")

        if record_count > 0:
            append_feature(query_layer, out_feature, self.sde_workspace)

        else:
            logger.info("Did not update.")
            return False

        return True

    def update_safe_school_streets_segmentation(
            self,
            segmented_feature_name: str = SDE_SAFE_SCHOOL_STREETS_DYN_SEG_FEATURE_NAME
    ):
        """Create a dynamic segmentation feature for safe school streets review.

        The main street dynamic segmentation is intentionally left unchanged.
        This overlay uses E_SafeSchoolStreets (the criteria fields), plus
        E_District and E_StreetClass to expose DIST_ID and ST_CLASS, along
        the route network. FROM_STR/TO_STR are route-level attributes on
        LRSN_Route itself, so they're pulled in via an extended
        ``network_fields`` local to this overlay rather than added to the
        shared ``self.network_fields`` used by the other dynamic
        segmentation views.
        """

        segmented_feature = os.path.join(self.sde_workspace, segmented_feature_name)
        event_tables = self.safe_school_streets_event_tables
        network_fields = f"{self.network_fields};FROM_STR;TO_STR"

        try:

            logger.info(f"Overlaying events to create '{segmented_feature_name}'...")
            arcpy.locref.OverlayEvents(
                in_route_features=rf"{self.sde_workspace}\GISRW01.SDEADM.TRNLRS\GISRW01.SDEADM.LRSN_Route",
                event_layers=event_tables,
                output_dataset=segmented_feature,
                include_geometry="INCLUDE_GEOMETRY",
                network_fields=network_fields
            )
            logger.info(arcpy.GetMessages())

            logger.info(f"\tRecreated {segmented_feature}")

            arcpy.ChangePrivileges_management(
                in_dataset=segmented_feature,
                user="PUBLIC",
                View="GRANT",
            )

            return segmented_feature

        except arcpy.ExecuteError:
            run_error_processing(
                f"Error updating Dynamic Segmentation {segmented_feature_name}. Details: {str(arcpy.GetMessages(2))}"
            )

    def update_safe_school_streets(
            self,
            out_feature: str = SAFE_SCHOOL_STREETS_FEATURE_NAME
    ):
        """Create the publishable safe school streets feature.

        ``out_feature`` should point to a feature class with the target fields
        ROUTEID, STR_NAME, FULL_NAME, FROM_STR, TO_STR, DIST_ID, ST_CLASS,
        PRESCREEN_CRIT, AAWT, TRANSIT_RTE, THROUGH_RD_ACCESS,
        ACTIVE_TRANS_INFRA_CONN, CRIT_STAT_COMMENT, LOCERROR, SDATE, SOURCE,
        SACC, ADDDATE, ADDBY, MODDATE, and MODBY. FROM_STR/TO_STR come from
        LRSN_Route (via network_fields), DIST_ID from E_District, and
        ST_CLASS from E_StreetClass — all carried through directly by
        OverlayEvents. LOCERROR, SDATE, SOURCE, SACC, and the audit fields
        are not carried through by OverlayEvents, so they're joined back
        from E_SafeSchoolStreets (the defining event for this view) on
        ROUTEID, mirroring how the speed limit neighbourhood view pulls
        audit dates from E_SpeedLimit. The source is the
        safe-school-streets-specific segmented feature generated by
        :meth:`update_safe_school_streets_segmentation`.
        """

        logger.info("Creating safe school streets query layer...")

        query = f"""
        SELECT
            e.OBJECTID,
            e.ROUTEID,
            e.STR_NAME,
            e.ROUTENAME AS FULL_NAME,
            e.FROM_STR,
            e.TO_STR,
            e.DIST_ID,
            e.ST_CLASS,
            e.PRESCREEN_CRIT,
            e.AAWT,
            e.TRANSIT_RTE,
            e.THROUGH_RD_ACCESS,
            e.ACTIVE_TRANS_INFRA_CONN,
            e.CRIT_STAT_COMMENT,
            sss.LocError    AS LOCERROR,
            sss.SDate       AS SDATE,
            sss.[Source]    AS [SOURCE],
            sss.Sacc        AS SACC,
            sss.MinAddDate  AS ADDDATE,
            sss.AddBy       AS ADDBY,
            sss.MaxModDate  AS MODDATE,
            sss.ModBy       AS MODBY,
            e.SHAPE
        FROM {SDE_SAFE_SCHOOL_STREETS_DYN_SEG_FEATURE_NAME} e
        LEFT JOIN (
            SELECT
                ROUTEID,
                MIN(LOCERROR)  AS LocError,
                MIN(SDATE)     AS SDate,
                MIN([SOURCE])  AS [Source],
                MIN(SACC)      AS Sacc,
                MIN(ADDDATE)   AS MinAddDate,
                MIN(ADDBY)     AS AddBy,
                MAX(MODDATE)   AS MaxModDate,
                MAX(MODBY)     AS ModBy
            FROM SDEADM.E_SafeSchoolStreets
            WHERE TODATE IS NULL
              AND (GDB_IS_DELETE IS NULL OR GDB_IS_DELETE = 0)
            GROUP BY ROUTEID
        ) sss ON e.ROUTEID = sss.ROUTEID
        WHERE e.TO_DATE IS NULL
        """

        query_layer = self._make_query_layer(query, layer_name="safe_school_streets_query_out_layer")

        record_count = int(arcpy.GetCount_management(query_layer)[0])
        logger.info(f"Row count: {record_count}")

        if record_count > 0:
            append_feature(query_layer, out_feature, self.sde_workspace)

        else:
            logger.info("Did not update.")
            return False

        return True

    def update_lrs_streets(self, lrs_streets_feature: str):
        self._update_streets("e.TO_DATE IS NULL", lrs_streets_feature)

    def update_nscaf_streets(self, nscaf_streets_feature: str):
        self._update_streets("e.TO_DATE IS NOT NULL AND e.FROM_DATE IS NOT NULL", nscaf_streets_feature)

    def update_street_lanes(self, street_lanes_feature: str):
        self._update_street_lanes(street_lanes_feature)


def sync_network_edge_source(sde_connection: str):
    """Sync the network edge source FC and rebuild the network dataset.

    Truncates TRNLRS_TRN_STREET (the FD copy referenced by the network dataset)
    and reloads it from TRNLRS_TRN_STREET_VW (the standalone authoritative FC
    maintained by LRS_updates.py), then rebuilds TRNLRS_street_network.

    This keeps the network dataset current after each LRS refresh without
    requiring a separate scheduled task.  Remove this function and its call
    once TRNLRS_TRN_STREET_VW is moved into the feature dataset permanently.
    """
    standalone = os.path.join(sde_connection, LRS_VIEW_NAME)
    fd_copy    = os.path.join(sde_connection, TRNLRS_NETWORK_FD, NETWORK_FD_EDGE_COPY_NAME)
    network    = os.path.join(sde_connection, TRNLRS_NETWORK_FD, NETWORK_DATASET_NAME)

    logger.info(f"Syncing network edge source: {LRS_VIEW_NAME} → {NETWORK_FD_EDGE_COPY_NAME}")
    append_feature(standalone, fd_copy, sde_connection)

    logger.info(f"Rebuilding network dataset: {NETWORK_DATASET_NAME}")
    arcpy.na.BuildNetwork(network)
    logger.info(arcpy.GetMessages())
    logger.info("Network rebuild complete.")


def run_error_processing(error_message):

    logger.info("Handling Error...")

    tb = sys.exc_info()[2]
    tbinfo = traceback.format_tb(tb)[0]

    pymsg = "PYTHON ERRORS:\nTraceback Info:\n" + tbinfo + "\nError Info:\n    " + \
            str(sys.exc_info()[0]) + ": " + str(sys.exc_info()[1]) + "\n"

    logger.error(pymsg)
    logger.info(error_message)

    msgs = "GP ERRORS:\n" + arcpy.GetMessages(2) + "\n"
    logger.error(msgs)

    send_mail(
        to=str(config.get('EMAIL', 'recipients')).split(','),
        subject='ERROR - LRS Updates Failed',
        text=log_server + " / LRS_Updates.py\n" + error_message
    )


def _write_csv_report(report_path: str, records: list[dict]):
    """Write a list of dicts to a CSV file."""
    with open(report_path, "w", newline='') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)


def _cleanup_or_write_report(report_path: str, records: list[dict], error_label: str) -> bool:
    """Write records to report if any exist, otherwise remove stale report file.

    Returns True if records were written (i.e. errors found).
    """

    if records:
        logger.info(f"DYN SEG ERROR: {error_label}")
        _write_csv_report(report_path, records)
        return True

    else:
        if os.path.exists(report_path):
            os.remove(report_path)

        return False


def trnlrs_street_view_checks(dyn_seg_feature: str, short_segment_threshold: float) -> dict:
    """Run QA/QC checks on a dynamic segmentation feature.

    Parameters
    ----------
    dyn_seg_feature : str
        Path to the feature class containing dynamic segmentation results.
    short_segment_threshold : float
        Minimum length (in the units of ``SHAPE@LENGTH``) that a segment must
        exceed in order to pass the short segment check.

    Returns
    -------
    dict
        Dictionary containing the generated report file names and boolean flags
        indicating whether critical or warning errors were found.

    The checks performed are:
        - duplicate ``FDMID`` values
        - null ``FDMID`` values
        - segments shorter than ``short_segment_threshold``
    """

    import pandas as pd

    null_gsa_report = "null_gsas.csv"
    duplicate_fdmids_report = "duplicate_fdmids.txt"
    null_fdmids_report = "null_fdmids.csv"
    short_segments_report = "short_segments.csv"

    critical_errors_found = False
    warning_errors_found = False

    dyn_seg_fields = [
        "ROUTE_ID", "FDMID", "SHAPE@LENGTH", "GSA_LEFT", "GSA_RIGHT"
    ]

    dyn_seg_data = [
        row for row in arcpy.da.SearchCursor(
            dyn_seg_feature,
            dyn_seg_fields,
            "TO_DATE IS NULL"
        )
    ]

    df = pd.DataFrame(dyn_seg_data, columns=dyn_seg_fields).sort_values(by=["SHAPE@LENGTH", "ROUTE_ID", "GSA_LEFT"])

    df['FDMID'] = pd.to_numeric(df['FDMID'], errors='coerce').round().astype('Int64')

    # CRITICAL ERROR CHECKS
    # Check for null GSA
    null_gsa_df = df[df['GSA_LEFT'].isna() | df['GSA_RIGHT'].isna()]

    # Check for duplicate FDMIDs

    # Keep nullable Int64, just drop NA for duplicate logic
    non_null_fdmids = df['FDMID'].dropna()

    duplicate_fdmids = (
        non_null_fdmids[non_null_fdmids.duplicated(keep=False)]
        .unique()
        .tolist()
    )
    duplicate_fdmids.sort()

    # Check for null FDMID records
    null_fdmid_df = df[df['FDMID'].isnull()].drop_duplicates()

    # Check for short segments
    short_segments_df = df[(df['SHAPE@LENGTH'] < short_segment_threshold) | (df['SHAPE@LENGTH'].isnull())]
    short_segments = short_segments_df.to_dict('records')

    # WARNING CHECKS
    # communities, overlapping ranges, blank street type, NSCAF, locators
    # TODO: Check for warnings

    if _cleanup_or_write_report(
        null_gsa_report, null_gsa_df[['ROUTE_ID']].to_dict('records') if not null_gsa_df.empty else [],
        "Null GSAs found!"
    ):
        critical_errors_found = True

    if duplicate_fdmids:

        critical_errors_found = True

        logger.info("DYN SEG ERROR: Duplicate FDMIDs found!")

        with open(duplicate_fdmids_report, "w") as txt_file:
            for fdmid in duplicate_fdmids:
                txt_file.write(f"{fdmid}\n")

    else:
        if os.path.exists(duplicate_fdmids_report):
            os.remove(duplicate_fdmids_report)

    if _cleanup_or_write_report(
        null_fdmids_report, null_fdmid_df[['ROUTE_ID']].to_dict('records') if not null_fdmid_df.empty else [],
        "Records with null FDMIDs found!"
    ):
        critical_errors_found = True

    if _cleanup_or_write_report(
        short_segments_report, short_segments,
        f"Segments shorter than {short_segment_threshold}m found!"
    ):
        critical_errors_found = True

    return {
        "duplicate_fdmids_report": duplicate_fdmids_report,
        "null_fdmids_report": null_fdmids_report,
        "null_gsa_report": null_gsa_report,
        "short_segments_report": short_segments_report,

        "critical_errors_found": critical_errors_found,
        "warning_errors_found": warning_errors_found
    }


def append_feature(input_feature, target_feature, sde_conn):

    # TODO: Create parameter for user to decide if they want the feature created or not

    logger.info(f"Updating '{target_feature}' from '{input_feature}'...")

    with arcpy.EnvManager(preserveGlobalIds=True, workspace=sde_conn):

        if not arcpy.Exists(target_feature):
            logger.info(f"'{target_feature}' does not exist — creating from source...")
            arcpy.CopyFeatures_management(input_feature, target_feature)
            logger.info(arcpy.GetMessages())
            arcpy.ChangePrivileges_management(target_feature, user="PUBLIC", View="GRANT")
            logger.info(f"Granted PUBLIC VIEW on {target_feature}")
        else:
            feature_name = arcpy.Describe(target_feature).name
            target_feature = os.path.join(sde_conn, feature_name)

            arcpy.TruncateTable_management(target_feature)
            logger.info(f"Truncated {target_feature}.")

            arcpy.Append_management(
                inputs=input_feature,
                target=target_feature,
                schema_type="NO_TEST"
            )

        return True


def generate_intersections(sde_branch):

    """
    - Requires location referencing extension
    - Requires branch versioned connection
    """

    logger.info("Generating intersections...")

    lrs_feature_dataset = "SDEADM.TRNLRS"
    intersection_fc = os.path.join(lrs_feature_dataset, "SDEADM.INT_RouteOnRoute")
    network_layer = os.path.join(lrs_feature_dataset, "SDEADM.LRSN_Route")

    with arcpy.EnvManager(workspace=sde_branch):

        arcpy.locref.GenerateIntersections(
            in_intersection_feature_class=intersection_fc,
            in_network_layer=network_layer,
            start_date=None,
            edited_by_current_user="ALL_USERS"
        )

        logger.info(arcpy.GetMessages())

        return True


if __name__ == "__main__":

    start_time = time.asctime(time.localtime(time.time()))
    logger.info(f"Start: {start_time}")
    logger.info("-----------------------")

    try:

        if arcpy.CheckExtension("LocationReferencing") == "Available":
            arcpy.CheckOutExtension("LocationReferencing")
            logger.info("Checked out LocationReferencing Extension.")
        else:
            raise LicenseError("Unable to checkout Location Referencing License.")

        if arcpy.CheckExtension("Network") == "Available":
            arcpy.CheckOutExtension("Network")
            logger.info("Checked out Network Analyst Extension.")
        else:
            raise LicenseError("Unable to checkout Network Analyst License.")

        # generate_intersections(sde_branch=r"E:\HRM\Scripts\SDE\SQL\prod_RW_sdeadm_branch.sde")

        sde_lrs_trn_streets_feature = os.path.join(SDEADM_RW, LRS_VIEW_NAME)
        sde_lrs_speed_limit_feature = os.path.join(SDEADM_RW, SPEED_LIMIT_NEIGHBOURHOOD_FEATURE_NAME)
        sde_lrs_safe_school_streets_feature = os.path.join(SDEADM_RW, SAFE_SCHOOL_STREETS_FEATURE_NAME)

        retired_streets_nscaf = os.path.join(SDEADM_RW, "SDEADM.TRNLRS_TRN_street_retired")
        street_lanes_feature = os.path.join(SDEADM_RW, "SDEADM.TRNLRS_TRN_street_lanes")

        dyn_seg_feature_new = DynSegFeature(SDEADM_RW, SDE_DYN_SEG_FEATURE_NAME)

        logger.info(f"Updating dynamic segmentation in '{dyn_seg_feature_new.feature_name}'...")

        dyn_seg_feature_new.update_dynamic_segmentation()
        dyn_seg_feature_new.update_speed_limit_neighbourhood_segmentation()
        dyn_seg_feature_new.update_safe_school_streets_segmentation()

        ###################################################################################
        # DYN SEG Feature Checks
        ###################################################################################

        lrs_email_recipents = [
            'tr33177@halifax.ca',
            'me24191@halifax.ca',
            'coville@halifax.ca',
            'ry51347@halifax.ca',
            'ma18333@halifax.ca',
        ]

        short_segment_threshold = 3.174511
        view_checks_info = trnlrs_street_view_checks(dyn_seg_feature_new.feature, short_segment_threshold)

        if view_checks_info["critical_errors_found"] or view_checks_info["warning_errors_found"]:

            reports = (
                view_checks_info['duplicate_fdmids_report'],
                view_checks_info['null_fdmids_report'],
                view_checks_info['null_gsa_report'],
                view_checks_info['short_segments_report'],
            )

            written_reports = [x for x in reports if os.path.exists(x)]

            send_mail(
                to=lrs_email_recipents,
                subject="TRNLRS_street_view Errors & Warnings Report (from PROD)",
                text="Uh oh, we have a small problem - attached is some information regarding some issues feeding the TRNLRS_steet_VW, for your VIEWing pleasure."
                     f"\n\t(The shortest segment threshold used was '{short_segment_threshold}')"
                     f"\nCheck out geometry information here: '{SDE_DYN_SEG_FEATURE_NAME}'"
                     "\n\nGodspeed.",
                files=written_reports,
                cc=['gallaga@halifax.ca'],
                bcc=['evansr@halifax.ca']
            )

            logger.error(f"Critical errors found in {SDE_DYN_SEG_FEATURE_NAME} to prevent {LRS_VIEW_NAME} from updating")

        else:

            ###################################################################################
            # Update TRNLRS_TRN_street_VW
            ###################################################################################

            street_features = {
                sde_lrs_trn_streets_feature: {"update_method": dyn_seg_feature_new.update_lrs_streets},
                street_lanes_feature: {"update_method": dyn_seg_feature_new.update_street_lanes},
                retired_streets_nscaf: {"update_method": dyn_seg_feature_new.update_nscaf_streets},
                sde_lrs_speed_limit_feature: {"update_method": dyn_seg_feature_new.update_speed_limit_neighbourhood},
                sde_lrs_safe_school_streets_feature: {"update_method": dyn_seg_feature_new.update_safe_school_streets},
            }

            for feature, feature_info in street_features.items():

                logger.info(f"Processing {feature}")

                update = feature_info.get('update_method')

                if update:

                    rw_tbl = feature
                    ro_tbl = os.path.join(SDEADM_RO, os.path.basename(feature))

                    update(rw_tbl)

                    # Manually update RO features
                    logger.info("Updating RO features (outside of replication)...")
                    append_feature(rw_tbl, ro_tbl, SDEADM_RO)

            ###################################################################################
            # Sync network edge source and rebuild TRNLRS_street_network
            ###################################################################################

            sync_network_edge_source(SDEADM_RW)

    except LicenseError:
        run_error_processing(
            "Unable to checkout Location Referencing License."
        )

    except Exception:
        run_error_processing("Error updating LRS data...")

    finally:
        arcpy.CheckInExtension("Network")
        arcpy.CheckInExtension('LocationReferencing')
        logger.info("Checked in LocationReferencing and Network Analyst extensions")

    end_time = time.asctime(time.localtime(time.time()))
    logger.info("-----------------------")
    logger.info(f"End: {end_time}")
