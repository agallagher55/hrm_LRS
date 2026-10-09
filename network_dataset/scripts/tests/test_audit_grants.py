"""
Tests for qa_refresh/audit_grants.py. They need no ArcGIS or SQL Server: the script is imported
against a stand-in for arcpy.

Run from network_dataset/scripts:
  > python -m unittest discover -s tests -v
"""

import csv
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "tests"))

from test_network_definitions import load_script  # noqa: E402

# The result of the audit on QA on 2026-10-09, before step 02.
QA_ROWS = [
    ["N_1", 10, "N_1_DESC", 10],
    ["N_2", 6, "N_2_DESC", 6],
    ["N_3", 6, "N_3_DESC", 6],
    ["ND_12010", 1, "ND_12010_DIRTYOBJECTS", 1],
    ["ND_38752", 1, "ND_38752_DIRTYOBJECTS", 0],
    ["ND_40986", 2, "ND_40986_DIRTYAREAS", 2],
    ["ND_7293", 2, "ND_7293_DIRTYAREAS", 2],
]


def load_audit(rows, output_dir):
    """Import the script with a fake arcpy that returns rows from the SQL and DSIDs from Describe."""
    module = load_script("qa_refresh/audit_grants.py", None)
    executed = []

    class FakeExecutor:

        def __init__(self, connection):
            self.connection = connection

        def execute(self, sql):
            executed.append((self.connection, sql))

            return rows

    module.arcpy = types.SimpleNamespace(
        ArcSDESQLExecute=FakeExecutor,
        Exists=lambda path: not path.endswith("_Junctions"),
        Describe=lambda path: types.SimpleNamespace(DSID=40986),
    )
    module.OUTPUT_DIR = Path(output_dir)

    return module, executed


class NormalizeRowsTests(unittest.TestCase):

    def setUp(self):
        self.module = load_script("qa_refresh/audit_grants.py", None)

    def test_a_list_of_rows_is_kept(self):
        self.assertEqual(self.module.normalize_rows([["N_3", 6, "x", 6], ["N_2", 6, "y", 6]]),
                         [["N_3", 6, "x", 6], ["N_2", 6, "y", 6]])

    def test_a_single_flat_row_is_wrapped(self):
        self.assertEqual(self.module.normalize_rows(["N_3", 6, "x", 6]), [["N_3", 6, "x", 6]])

    def test_nothing_returned_gives_no_rows(self):
        self.assertEqual(self.module.normalize_rows([]), [])
        self.assertEqual(self.module.normalize_rows(None), [])
        self.assertEqual(self.module.normalize_rows(True), [])


class GrantStatusTests(unittest.TestCase):

    def setUp(self):
        self.module = load_script("qa_refresh/audit_grants.py", None)

    def test_each_status(self):
        self.assertEqual(self.module.grant_status(6, 6), "all granted")
        self.assertEqual(self.module.grant_status(6, 0), "none granted")
        self.assertEqual(self.module.grant_status(2, 1), "partial")


class MainTests(unittest.TestCase):

    def run_main(self, rows):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        module, executed = load_audit(rows, directory.name)

        with mock.patch("builtins.print"):
            module.main()

        return module, executed, Path(directory.name)

    def read_csv(self, directory, prefix):
        files = sorted(directory.glob(prefix + "_*.csv"))
        self.assertEqual(len(files), 1, prefix)

        with open(files[0], newline="", encoding="utf-8") as csv_file:
            return list(csv.reader(csv_file))

    def test_the_audit_runs_on_the_qa_connection_and_is_read_only(self):
        module, executed, _ = self.run_main(QA_ROWS)

        self.assertEqual(len(executed), 1)
        self.assertEqual(executed[0][0], module.config.QA_SDE)
        self.assertTrue(executed[0][1].lstrip().upper().startswith("SELECT"))

        for word in ("INSERT", "UPDATE", "DELETE", "GRANT", "DROP", "ALTER"):
            self.assertNotIn(word, executed[0][1].upper().split(), word)

    def test_the_audit_csv_has_a_status_for_every_group(self):
        _, _, directory = self.run_main(QA_ROWS)

        rows = self.read_csv(directory, "grants_audit_before")

        self.assertEqual(rows[0], ["reg_group", "table_count", "example_table",
                                   "tables_with_public_select", "status"])
        by_group = {row[0]: row for row in rows[1:]}
        self.assertEqual(len(by_group), len(QA_ROWS))
        self.assertEqual(by_group["N_3"][4], "all granted")
        self.assertEqual(by_group["ND_40986"][4], "all granted")
        self.assertEqual(by_group["ND_38752"][4], "none granted")

    def test_a_new_ungranted_pair_is_reported(self):
        rows = QA_ROWS + [["ND_41200", 2, "ND_41200_DIRTYAREAS", 0]]
        printed = []
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        module, _ = load_audit(rows, directory.name)

        with mock.patch("builtins.print", side_effect=lambda *a, **k: printed.append(" ".join(map(str, a)))):
            module.main()

        text = "\n".join(printed)
        self.assertIn("ND_41200", text.split("a missing grant:")[1])
        self.assertIn("DIRTYAREAS and DIRTYOBJECTS pair", text)

    def test_the_ids_csv_lists_the_network_and_its_sources(self):
        _, _, directory = self.run_main(QA_ROWS)

        rows = self.read_csv(directory, "network_ids_before")

        self.assertEqual(rows[0], ["item", "path", "dsid"])
        by_item = {row[0]: row for row in rows[1:]}
        self.assertEqual(set(by_item), {"network dataset", "edge source", "junction source",
                                        "turn source", "system junctions"})
        self.assertEqual(by_item["edge source"][2], "40986")
        self.assertEqual(by_item["system junctions"][2], "")

    def test_a_single_row_result_still_works(self):
        _, _, directory = self.run_main(["N_3", 6, "N_3_DESC", 6])

        rows = self.read_csv(directory, "grants_audit_before")

        self.assertEqual([row[0] for row in rows[1:]], ["N_3"])


if __name__ == "__main__":
    unittest.main()
