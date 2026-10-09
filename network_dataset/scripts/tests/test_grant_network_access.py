"""
Tests for qa_refresh/grant_network_access.py. They need no ArcGIS or SQL Server: the script is
imported against a stand-in for arcpy whose SQL executor keeps the tables in a small dict.

Run from network_dataset/scripts:
  > python -m unittest discover -s tests -v
"""

import re
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "tests"))

from test_network_definitions import load_script  # noqa: E402

N_TABLES = ["DESC", "EDGEWEIGHT", "JUNCTIONWEIGHT", "PROPS", "TOPOLOGY", "TURNWEIGHT"]
SOURCES = ["TRNLRS_TRN_STREET", "TRNLRS_STREET_JUNCTION", "TRNLRS_TRAFFIC_TURN", "TRNLRS_STREET_NETWORK_JUNCTIONS"]


def qa_tables(granted_sources=True, extra=None):
    """Tables on QA after step 06, as on 2026-10-09: name -> PUBLIC has SELECT."""
    tables = {}

    for number, granted in ((1, True), (2, True)):
        for name in N_TABLES:
            tables[f"N_{number}_{name}"] = granted

    for name in N_TABLES:
        tables[f"N_3_{name}"] = False

    tables["ND_41025_DIRTYAREAS"] = True
    tables["ND_41025_DIRTYOBJECTS"] = False
    tables["ND_7293_DIRTYAREAS"] = True
    tables["ND_7293_DIRTYOBJECTS"] = True
    tables["ND_38752_DIRTYOBJECTS"] = False

    for name in SOURCES:
        tables[name] = granted_sources

    tables.update(extra or {})

    return tables


class FakeSql:
    """Answers the queries the scripts send from a dict of tables, and records the grants."""

    def __init__(self, tables, grant_works=True):
        self.tables = tables
        self.statements = []
        self.grant_works = grant_works

    def execute(self, sql):
        text = " ".join(sql.split())

        if text.startswith("GRANT SELECT ON"):
            name = re.search(r"\[(\w+)\]", text).group(1)
            self.statements.append(text)

            if self.grant_works:
                self.tables[name] = True

            return True

        if "reg_group" in text:
            return self.audit()

        if "LIKE" in text and "SELECT name FROM sys.tables" in text:
            prefix = re.search(r"LIKE '([^']+)%'", text).group(1).replace("\\_", "_")

            return [[name] for name in sorted(self.tables) if name.startswith(prefix)]

        if "has_select" in text:
            wanted = re.search(r"t\.name IN \((.*)\)", text).group(1)
            names = [part.strip().strip("'").upper() for part in wanted.split(",")]

            return [[name, int(granted)] for name, granted in self.tables.items() if name.upper() in names]

        raise AssertionError("Unexpected SQL: " + text[:80])

    def audit(self):
        groups = {}

        for name, granted in self.tables.items():
            match = re.match(r"(ND_\d+|N_\d+)_", name)

            if not match:
                continue

            group = groups.setdefault(match.group(1), [name, 0, 0])
            group[1] += 1
            group[2] += int(granted)

        return [[group, count, example, granted] for group, (example, count, granted) in sorted(groups.items())]


def load(tables, apply=False, grant_works=True, dsid=41025, n_group=None):
    module = load_script("qa_refresh/grant_network_access.py", None)
    sql = FakeSql(tables, grant_works)
    module.arcpy = types.SimpleNamespace(
        ArcSDESQLExecute=lambda connection: sql,
        Describe=lambda path: types.SimpleNamespace(DSID=dsid),
    )
    module.audit_grants.arcpy = module.arcpy
    module.APPLY = apply
    module.N_GROUP = n_group

    return module, sql


class GrantScriptTests(unittest.TestCase):

    def run_main(self, module):
        printed = []
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)

        with mock.patch.object(module.config, "OUTPUT_DIR", Path(directory.name)), \
                mock.patch("builtins.print", side_effect=lambda *a, **k: printed.append(" ".join(map(str, a)))):
            module.main()

        return "\n".join(printed), Path(directory.name)

    def test_a_dry_run_lists_the_grants_and_changes_nothing(self):
        module, sql = load(qa_tables())

        text, _ = self.run_main(module)

        self.assertEqual(sql.statements, [])
        self.assertIn("Dry run only", text)
        self.assertIn("would run: GRANT SELECT ON SDEADM.[N_3_PROPS] TO PUBLIC", text)
        self.assertIn("ND_41025_DIRTYOBJECTS", text)
        self.assertNotIn("ND_41025_DIRTYAREAS", text)

    def test_apply_grants_only_what_is_missing_and_verifies(self):
        module, sql = load(qa_tables(), apply=True)

        text, directory = self.run_main(module)

        granted = sorted(re.search(r"\[(\w+)\]", s).group(1) for s in sql.statements)
        self.assertEqual(granted, sorted([f"N_3_{n}" for n in N_TABLES] + ["ND_41025_DIRTYOBJECTS"]))
        self.assertIn("Verified", text)
        self.assertEqual(len(list(directory.glob("grants_applied_*.csv"))), 1)

    def test_other_networks_tables_are_never_granted(self):
        module, sql = load(qa_tables(), apply=True)

        self.run_main(module)

        for statement in sql.statements:
            for other in ("ND_38752", "ND_7293", "N_1_", "N_2_"):
                self.assertNotIn(other, statement)

    def test_ungranted_source_tables_are_granted_too(self):
        module, sql = load(qa_tables(granted_sources=False), apply=True)

        self.run_main(module)

        granted = [re.search(r"\[(\w+)\]", s).group(1) for s in sql.statements]
        self.assertIn("TRNLRS_TRN_STREET", granted)
        self.assertIn("TRNLRS_STREET_NETWORK_JUNCTIONS", granted)

    def test_nothing_to_grant_when_everything_is_granted(self):
        tables = {name: True for name in qa_tables()}
        module, sql = load(tables, apply=True)

        text, _ = self.run_main(module)

        self.assertEqual(sql.statements, [])
        self.assertIn("Nothing to grant", text)

    def test_a_grant_that_does_not_take_is_an_error(self):
        module, _ = load(qa_tables(), apply=True, grant_works=False)

        with self.assertRaises(RuntimeError) as error:
            self.run_main(module)

        self.assertIn("still have no PUBLIC SELECT", str(error.exception))

    def test_a_missing_nd_group_stops_before_any_grant(self):
        module, sql = load(qa_tables(), apply=True, dsid=99999)

        with self.assertRaises(RuntimeError) as error:
            self.run_main(module)

        self.assertIn("ND_99999", str(error.exception))
        self.assertEqual(sql.statements, [])

    def test_two_candidate_n_groups_stop_and_the_override_resolves_it(self):
        extra = {f"N_9_{name}": False for name in N_TABLES}
        module, sql = load(qa_tables(extra=extra), apply=True)

        with self.assertRaises(RuntimeError) as error:
            self.run_main(module)

        self.assertIn("N_GROUP", str(error.exception))
        self.assertEqual(sql.statements, [])

        module, sql = load(qa_tables(extra=extra), apply=True, n_group="N_3")
        self.run_main(module)

        self.assertTrue(all("N_9_" not in s for s in sql.statements))
        self.assertTrue(any("N_3_PROPS" in s for s in sql.statements))

    def test_a_missing_source_table_stops_the_run(self):
        tables = qa_tables()
        del tables["TRNLRS_TRAFFIC_TURN"]
        module, sql = load(tables, apply=True)

        with self.assertRaises(RuntimeError) as error:
            self.run_main(module)

        self.assertIn("does not exist", str(error.exception))
        self.assertEqual(sql.statements, [])

    def test_unexpected_table_names_are_refused(self):
        module, _ = load(qa_tables())

        for bad in ("N_3'; DROP TABLE x;--", "a b", "x]"):
            with self.assertRaises(RuntimeError):
                module.safe_name(bad)

        self.assertEqual(module.safe_name("N_3_PROPS"), "N_3_PROPS")

    def test_apply_defaults_to_a_dry_run(self):
        module = load_script("qa_refresh/grant_network_access.py", None)

        self.assertFalse(module.APPLY)
        self.assertIsNone(module.N_GROUP)


if __name__ == "__main__":
    unittest.main()
