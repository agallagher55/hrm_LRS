"""
Tests for qa_refresh/smoke_test_network.py. They need no ArcGIS: the route solver is replaced by a
fake that answers from a small model of the network.

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


class FakeShape:

    def positionAlongLine(self, fraction, as_fraction):
        return (id(self), fraction)


def codes_of(edges):
    """{id of each edge's shape: its STR_DIR code}, which is how the fake solver knows the codes."""
    return {id(edge.shape): edge.str_dir for edge in edges.values()}


def make_edges(module, rows):
    """rows: (oid, str_dir, name, length, parts)."""
    return {
        oid: module.Edge(oid, str_dir, name, length, parts, FakeShape())
        for oid, str_dir, name, length, parts in rows
    }


class FakeSolver:
    """Routes from a model. turn_restricted and blocked_direction set what the network does."""

    def __init__(self, detour=300.0, drives_through=False, one_way_leaks=False, none_when_blocked=False, codes=None):
        self.codes = codes or {}
        self.detour = detour
        self.drives_through = drives_through
        self.one_way_leaks = one_way_leaks
        self.none_when_blocked = none_when_blocked
        self.calls = []

    def close(self):
        self.closed = True

    NO_SOLUTION = "ERROR 030212: Solve did not find a solution."

    def length(self, points, restricted):
        self.calls.append((points, restricted))
        self.last_message = ""
        a, b = points

        if a[0] == b[0]:
            # Two stops on one edge: a quarter to three quarter run is half the edge, 50 m here.
            going_back = a[1] > b[1]
            code = self.codes.get(a[0], "FOTD")
            blocked = (code == "FOTD" and going_back) or (code == "FDTO" and not going_back)

            if restricted and blocked and not self.one_way_leaks:
                self.last_message = self.NO_SOLUTION if self.none_when_blocked else ""

                return None if self.none_when_blocked else 400.0

            return 50.0

        # Two stops on different edges: the direct route through the junction is 100 m here.
        if restricted and not self.drives_through:
            self.last_message = self.NO_SOLUTION if self.none_when_blocked else ""

            return None if self.none_when_blocked else self.detour

        return 100.0


class JudgeTests(unittest.TestCase):

    def setUp(self):
        self.module = load_script("qa_refresh/smoke_test_network.py", None)

    def test_turn_passes_on_a_detour_or_no_route(self):
        self.assertEqual(self.module.judge_turn(100, 100, 300)[0], "PASS")
        self.assertEqual(self.module.judge_turn(100, 100, None)[0], "PASS")

    def test_turn_fails_when_the_prohibited_turn_is_driven(self):
        self.assertEqual(self.module.judge_turn(100, 100, 100)[0], "FAIL")
        self.assertEqual(self.module.judge_turn(100, 100, 101.5)[0], "FAIL")

    def test_turn_is_skipped_when_the_unrestricted_route_is_not_direct(self):
        self.assertEqual(self.module.judge_turn(100, 250, 400)[0], "SKIP")
        self.assertEqual(self.module.judge_turn(100, None, None)[0], "SKIP")

    def test_oneway_pass_cases(self):
        self.assertEqual(self.module.judge_oneway("FOTD", 50, 50, 400, 50)[0], "PASS")
        self.assertEqual(self.module.judge_oneway("FOTD", 50, 50, None, 50)[0], "PASS")
        self.assertEqual(self.module.judge_oneway("BOTH", 50, 50, 50, None)[0], "PASS")

    def test_oneway_fails_when_the_blocked_way_is_driven(self):
        self.assertEqual(self.module.judge_oneway("FOTD", 50, 50, 50, 50)[0], "FAIL")

    def test_oneway_fails_when_the_allowed_way_is_blocked(self):
        self.assertEqual(self.module.judge_oneway("FOTD", 50, None, None, 50)[0], "FAIL")
        self.assertEqual(self.module.judge_oneway("BOTH", 50, 50, None, None)[0], "FAIL")

    def test_oneway_is_skipped_when_the_blocked_way_is_not_direct_unrestricted(self):
        self.assertEqual(self.module.judge_oneway("FOTD", 50, 50, 400, 300)[0], "SKIP")

    def test_tolerance_is_applied(self):
        self.assertTrue(self.module.same(100.0, 102.9))
        self.assertFalse(self.module.same(100.0, 104.0))
        self.assertFalse(self.module.same(None, 100.0))


class ChooseTests(unittest.TestCase):

    def setUp(self):
        self.module = load_script("qa_refresh/smoke_test_network.py", None)
        rows = [
            (1, "BOTH", "QUINPOOL RD", 100.0, 1),
            (2, "BOTH", "ROBIE ST", 100.0, 1),
            (3, "BOTH", "OTHER ST", 100.0, 1),
            (4, "BOTH", "SHORT ST", 10.0, 1),
            (5, "FOTD", "ONE WAY ST", 100.0, 1),
            (6, "FOTD", "MULTI ST", 100.0, 2),
            (7, "FDTO", "FDTO ST", 100.0, 1),
        ]
        self.edges = make_edges(self.module, rows)

    def test_named_turns_are_found_whatever_the_case(self):
        turns = [(1, 2), (3, 1), (2, 1)]

        chosen, missing = self.module.choose_turns(turns, self.edges, [("quinpool rd", "Robie St")], 0, 1)

        self.assertEqual([item[1:] for item in chosen], [(1, 2)])
        self.assertEqual(missing, [])

    def test_a_named_turn_that_is_not_in_the_data_is_reported(self):
        chosen, missing = self.module.choose_turns([(3, 1)], self.edges, [("QUINPOOL RD", "ROBIE ST")], 0, 1)

        self.assertEqual(chosen, [])
        self.assertEqual(missing, ["QUINPOOL RD -> ROBIE ST"])

    def test_the_sample_uses_two_edge_turns_on_long_edges_only(self):
        turns = [(1, 2), (1, 3), (1, 4), (1, 2, 3), (1, 99)]

        chosen, _ = self.module.choose_turns(turns, self.edges, [], 10, 1)

        self.assertEqual(sorted(item[1:] for item in chosen), [(1, 2), (1, 3)])

    def test_the_sample_is_repeatable(self):
        turns = [(1, 2), (1, 3), (2, 3), (3, 1), (2, 1)]

        first, _ = self.module.choose_turns(turns, self.edges, [], 2, 7)
        second, _ = self.module.choose_turns(turns, self.edges, [], 2, 7)

        self.assertEqual(first, second)

    def test_a_named_turn_is_not_picked_twice(self):
        chosen, _ = self.module.choose_turns([(1, 2)], self.edges, [("QUINPOOL RD", "ROBIE ST")], 5, 1)

        self.assertEqual(len(chosen), 1)

    def test_oneway_choice_skips_short_and_multipart_edges(self):
        chosen = self.module.choose_oneway(self.edges, 10, 1)

        self.assertEqual([edge.oid for edge in chosen["FOTD"]], [5])
        self.assertEqual([edge.oid for edge in chosen["FDTO"]], [7])
        self.assertEqual(sorted(edge.oid for edge in chosen["BOTH"]), [1, 2, 3])


class RunTests(unittest.TestCase):

    def setUp(self):
        self.module = load_script("qa_refresh/smoke_test_network.py", None)
        rows = [
            (1, "BOTH", "QUINPOOL RD", 100.0, 1),
            (2, "BOTH", "ROBIE ST", 100.0, 1),
            (5, "FOTD", "ONE WAY ST", 100.0, 1),
            (7, "FDTO", "FDTO ST", 100.0, 1),
            (8, "BOTH", "TWO WAY ST", 100.0, 1),
        ]
        self.edges = make_edges(self.module, rows)

    def verdicts(self, results):
        return [result.verdict for result in results]

    def turn_results(self, solver, not_found=()):
        chosen = [("QUINPOOL RD -> ROBIE ST", 1, 2)]

        return self.module.run_turn_checks(solver, chosen, self.edges, list(not_found))

    def test_a_working_turn_restriction_passes(self):
        self.assertEqual(self.verdicts(self.turn_results(FakeSolver())), ["PASS"])

    def test_a_turn_that_is_driven_through_fails(self):
        self.assertEqual(self.verdicts(self.turn_results(FakeSolver(drives_through=True))), ["FAIL"])

    def test_no_route_counts_as_blocked(self):
        self.assertEqual(self.verdicts(self.turn_results(FakeSolver(none_when_blocked=True))), ["PASS"])

    def test_a_name_that_was_not_found_is_an_error(self):
        results = self.module.run_turn_checks(FakeSolver(), [], self.edges, ["A -> B"])

        self.assertEqual(self.verdicts(results), ["ERROR"])

    def test_a_solver_failure_is_an_error_for_that_case_only(self):
        class Broken(FakeSolver):
            def length(self, points, restricted):
                raise RuntimeError("ERROR 030024")

        chosen = [("one", 1, 2), ("two", 1, 2)]

        results = self.module.run_turn_checks(Broken(), chosen, self.edges, [])

        self.assertEqual(self.verdicts(results), ["ERROR", "ERROR"])
        self.assertIn("030024", results[0].detail)

    def test_the_restricted_solve_is_not_run_when_the_case_is_skipped(self):
        solver = FakeSolver()
        solver.length = lambda points, restricted: 250.0 if not restricted else (_ for _ in ()).throw(AssertionError("solved"))

        results = self.turn_results(solver)

        self.assertEqual(self.verdicts(results), ["SKIP"])

    def test_oneway_edges_pass_when_the_codes_are_enforced(self):
        by_code = {"FOTD": [self.edges[5]], "FDTO": [self.edges[7]], "BOTH": [self.edges[8]]}

        results = self.module.run_oneway_checks(FakeSolver(codes=codes_of(self.edges)), by_code)

        self.assertEqual(self.verdicts(results), ["PASS", "PASS", "PASS"])

    def test_the_blocked_direction_follows_the_code(self):
        solver = FakeSolver()
        by_code = {"FOTD": [self.edges[5]], "FDTO": [], "BOTH": []}

        self.module.run_oneway_checks(solver, by_code)

        # For FOTD the unrestricted check is on the against digitized run, which is three quarter to quarter.
        unrestricted = [points for points, restricted in solver.calls if not restricted]
        self.assertEqual(len(unrestricted), 1)
        self.assertGreater(unrestricted[0][0][1], unrestricted[0][1][1])

    def test_a_one_way_that_leaks_fails(self):
        by_code = {"FOTD": [self.edges[5]], "FDTO": [], "BOTH": []}

        results = self.module.run_oneway_checks(FakeSolver(one_way_leaks=True), by_code)

        self.assertEqual([r.verdict for r in results if r.check == "oneway" and "FOTD edge" in r.case], ["FAIL"])

    def test_a_code_with_no_usable_edge_is_reported(self):
        results = self.module.run_oneway_checks(FakeSolver(), {"FOTD": [], "FDTO": [], "BOTH": []})

        self.assertEqual(self.verdicts(results), ["ERROR", "ERROR", "ERROR"])


class ExplainTests(unittest.TestCase):

    def explain(self, datasets, properties=None):
        module = load_script("qa_refresh/smoke_test_network.py", None)
        properties = properties or types.SimpleNamespace(instance="ms-gis-sql-q22", database="GISRO01")
        module.arcpy = types.SimpleNamespace(
            Describe=lambda path: types.SimpleNamespace(connectionProperties=properties),
            ListDatasets=lambda: datasets,
            env=types.SimpleNamespace(workspace=None),
        )

        return module.explain_missing_network("RO.sde", {"network": "RO.sde\\net"})

    def test_a_login_that_sees_nothing_is_the_wrong_database_or_no_permission(self):
        text = self.explain([])

        self.assertIn("instance: ms-gis-sql-q22", text)
        self.assertIn("database: GISRO01", text)
        self.assertIn("sees no feature datasets", text)

    def test_a_database_without_the_feature_dataset_is_a_different_copy(self):
        text = self.explain(["SDEADM.TRNLRS", "SDEADM.TRN_streets_routes"])

        self.assertIn("not SDEADM.TRNLRS_network", text)
        self.assertIn("different or older copy", text)
        self.assertIn("SDEADM.TRN_streets_routes", text)

    def test_the_feature_dataset_without_the_network_points_at_the_grants(self):
        text = self.explain(["sdeadm.trnlrs_network"])

        self.assertIn("grants are the likely cause", text)

    def test_a_connection_with_no_properties_still_explains(self):
        text = self.explain([], properties=types.SimpleNamespace())

        self.assertIn("operating system login", text)

    def test_main_stops_with_that_explanation_when_the_network_is_missing(self):
        module = load_script("qa_refresh/smoke_test_network.py", None)
        module.arcpy = types.SimpleNamespace(
            Describe=lambda path: types.SimpleNamespace(
                connectionProperties=types.SimpleNamespace(instance="q22", database="GISRO01")),
            Exists=lambda path: False,
            ListDatasets=lambda: [],
            env=types.SimpleNamespace(workspace=None),
        )

        with mock.patch.object(module, "RO_SDE", "RO.sde"), mock.patch("builtins.print"):
            with self.assertRaises(RuntimeError) as error:
                module.main()

        self.assertIn("sees no feature datasets", str(error.exception))


class OutcomeTests(unittest.TestCase):

    def setUp(self):
        self.module = load_script("qa_refresh/smoke_test_network.py", None)
        self.edges = make_edges(self.module, [
            (1, "BOTH", "QUINPOOL RD", 100.0, 1), (2, "BOTH", "ROBIE ST", 100.0, 1),
            (5, "FOTD", "ONE WAY ST", 100.0, 1), (7, "FDTO", "FDTO ST", 100.0, 1), (8, "BOTH", "TWO WAY ST", 100.0, 1),
        ])

    def turn(self, solver):
        return self.module.run_turn_checks(solver, [("t", 1, 2)], self.edges, [])[0]

    def oneway(self, solver, code="FOTD", edge=5):
        return self.module.run_oneway_checks(solver, {code: [self.edges[edge]]})[0]

    def test_a_detour_is_labelled_a_detour(self):
        result = self.turn(FakeSolver())

        self.assertEqual((result.verdict, result.outcome, result.message), ("PASS", "detour", ""))

    def test_no_route_is_labelled_with_the_solvers_message(self):
        result = self.turn(FakeSolver(none_when_blocked=True))

        self.assertEqual((result.verdict, result.outcome), ("PASS", "no route"))
        self.assertIn("030212", result.message)

    def test_a_failed_case_has_no_outcome(self):
        result = self.turn(FakeSolver(drives_through=True))

        self.assertEqual((result.verdict, result.outcome), ("FAIL", ""))

    def test_one_way_outcomes(self):
        self.assertEqual(self.oneway(FakeSolver(codes=codes_of(self.edges))).outcome, "detour")
        self.assertEqual(self.oneway(FakeSolver(codes=codes_of(self.edges), none_when_blocked=True)).outcome, "no route")
        self.assertEqual(self.oneway(FakeSolver(codes=codes_of(self.edges)), "BOTH", 8).outcome, "straight")

    def test_the_message_for_a_one_way_is_the_blocked_directions(self):
        solver = FakeSolver(codes=codes_of(self.edges), none_when_blocked=True)

        result = self.oneway(solver, "FDTO", 7)

        self.assertEqual(result.outcome, "no route")
        self.assertIn("030212", result.message)

    def test_no_blocked_cases_gives_no_report(self):
        self.assertEqual(self.module.detour_report([]), [])
        self.assertEqual(self.module.detour_report([self.module.Result("oneway", "x", "PASS", "d", "straight")]), [])

    def test_the_report_counts_detours_and_no_routes(self):
        Result = self.module.Result
        results = [
            Result("turn", "a", "PASS", "", "detour"),
            Result("turn", "b", "PASS", "", "no route", "ERROR 030212: x"),
            Result("turn", "c", "PASS", "", "no route", "ERROR 030212: x"),
        ]

        text = "\n".join(self.module.detour_report(results))

        self.assertIn("1 found a detour, 2 found no route at all", text)
        self.assertIn("2 x solver said: ERROR 030212: x", text)
        self.assertNotIn("WARNING", text)

    def test_the_report_warns_when_no_case_found_a_detour(self):
        Result = self.module.Result
        results = [Result("turn", str(n), "PASS", "", "no route", "ERROR 030212: x") for n in range(3)]

        text = "\n".join(self.module.detour_report(results))

        self.assertIn("WARNING: no case found a detour", text)
        self.assertIn("QUINPOOL RD -> ROBIE ST", text)

    def test_a_missing_solver_message_is_said_so(self):
        Result = self.module.Result

        text = "\n".join(self.module.detour_report([Result("turn", "a", "PASS", "", "no route")]))

        self.assertIn("the solver gave no message", text)

    def test_condense_keeps_only_error_and_warning_lines(self):
        messages = "Start Time: Friday\nERROR 030212: Solve did not find a solution.\nWARNING 030158: x\nSucceeded"

        self.assertEqual(
            self.module.condense_messages(messages),
            "ERROR 030212: Solve did not find a solution. | WARNING 030158: x",
        )


class FakeNetworkAnalyst:
    """A stand-in for arcpy that behaves like the real one about layer names and route layers."""

    def __init__(self, route_length=50.0, no_route=False):
        self.layers = {}
        self.made = []
        self.solves = 0
        self.route_length = route_length
        self.no_route = no_route
        self.deleted = []
        self.messages = ""

    def namespace(self):
        outer = self

        class ExecuteError(Exception):
            pass

        class Layer:
            def __init__(self, name, options):
                self.name = name
                self.options = options

            def listLayers(self, name):
                return [types.SimpleNamespace(name=name)]

        def make_route_layer(network, name, impedance, **options):
            if name in outer.layers:
                raise ExecuteError("ERROR 030036: A layer with this name exists.")

            layer = Layer(name, options)
            outer.layers[name] = layer
            outer.made.append((name, options))

            return types.SimpleNamespace(getOutput=lambda index: layer)

        def solve(layer, *args):
            outer.solves += 1

            if outer.no_route:
                outer.messages = "ERROR 030212: Solve did not find a solution."
                raise ExecuteError(outer.messages)

        def delete(name):
            outer.deleted.append(name)
            outer.layers.pop(name, None)

        class Cursor:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return types.SimpleNamespace(insertRow=lambda row: None)

            def __exit__(self, *args):
                return False

        return types.SimpleNamespace(
            ExecuteError=ExecuteError,
            GetMessages=lambda: outer.messages,
            Exists=lambda name: name in outer.layers,
            management=types.SimpleNamespace(
                CreateFeatureclass=lambda *a, **k: types.SimpleNamespace(getOutput=lambda index: "memory\\smoke_stops"),
                DeleteRows=lambda fc: None,
                Delete=delete,
            ),
            na=types.SimpleNamespace(
                MakeRouteLayer=make_route_layer,
                GetNAClassNames=lambda layer: {"Stops": "Stops", "Routes": "Routes"},
                AddLocations=lambda *a, **k: None,
                Solve=solve,
            ),
            da=types.SimpleNamespace(
                InsertCursor=Cursor,
                SearchCursor=lambda layer, fields: iter([[outer.route_length]]),
            ),
        )


class RouteSolverTests(unittest.TestCase):

    def make(self, **kwargs):
        module = load_script("qa_refresh/smoke_test_network.py", None)
        fake = FakeNetworkAnalyst(**kwargs)
        module.arcpy = fake.namespace()

        return module, fake, module.RouteSolver("network", "sr")

    def test_many_solves_make_one_layer_per_mode(self):
        module, fake, solver = self.make()

        for _ in range(5):
            self.assertEqual(solver.length(["a", "b"], True), 50.0)
            self.assertEqual(solver.length(["a", "b"], False), 50.0)

        self.assertEqual(sorted(name for name, _ in fake.made), ["smoke_route_restricted", "smoke_route_unrestricted"])
        self.assertEqual(fake.solves, 10)

    def test_only_the_restricted_layer_has_the_restrictions(self):
        module, fake, solver = self.make()

        solver.length(["a", "b"], True)
        solver.length(["a", "b"], False)

        options = dict(fake.made)
        self.assertEqual(options["smoke_route_restricted"]["restriction_attribute_name"], module.RESTRICTIONS)
        self.assertNotIn("restriction_attribute_name", options["smoke_route_unrestricted"])

    def test_a_leftover_layer_of_the_same_name_is_removed_first(self):
        module, fake, solver = self.make()
        fake.layers["smoke_route_restricted"] = object()

        self.assertEqual(solver.length(["a", "b"], True), 50.0)
        self.assertIn("smoke_route_restricted", fake.deleted)

    def test_no_solution_is_no_route_and_other_errors_are_raised(self):
        module, fake, solver = self.make(no_route=True)

        self.assertIsNone(solver.length(["a", "b"], True))
        self.assertIn("030212", solver.last_message)

        fake.messages = "ERROR 000000: something else"
        fake.no_route = False

        def other_error(layer, *args):
            fake.messages = "ERROR 000000: something else"
            raise module.arcpy.ExecuteError("boom")

        module.arcpy.na.Solve = other_error

        with self.assertRaises(module.arcpy.ExecuteError):
            solver.length(["a", "b"], True)

    def test_the_message_is_cleared_by_the_next_solve(self):
        module, fake, solver = self.make(no_route=True)
        solver.length(["a", "b"], True)
        fake.no_route = False

        self.assertEqual(solver.length(["a", "b"], True), 50.0)
        self.assertEqual(solver.last_message, "")

    def test_close_removes_the_layers(self):
        module, fake, solver = self.make()
        solver.length(["a", "b"], True)

        solver.close()

        self.assertIn("smoke_route_restricted", fake.deleted)

    def test_one_line_joins_a_multi_line_message(self):
        module = load_script("qa_refresh/smoke_test_network.py", None)

        text = module.one_line(RuntimeError("Failed to execute.\nERROR 030036: A layer with this name exists.\n"))

        self.assertEqual(text, "RuntimeError: Failed to execute. | ERROR 030036: A layer with this name exists.")


class MainTests(unittest.TestCase):

    def run_main(self, solver, ro_sde="RO.sde", user="gisuser"):
        module = load_script("qa_refresh/smoke_test_network.py", None)
        edges = make_edges(module, [
            (1, "BOTH", "QUINPOOL RD", 100.0, 1), (2, "BOTH", "ROBIE ST", 100.0, 1),
            (5, "FOTD", "ONE WAY ST", 100.0, 1), (7, "FDTO", "FDTO ST", 100.0, 1), (8, "BOTH", "TWO WAY ST", 100.0, 1),
        ])
        solver.codes = codes_of(edges)
        module.arcpy = types.SimpleNamespace(
            Describe=lambda path: types.SimpleNamespace(
                connectionProperties=types.SimpleNamespace(user=user), spatialReference="sr"),
            Exists=lambda path: True,
            CheckOutExtension=lambda name: "CheckedOut",
        )
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        printed = []

        with mock.patch.object(module, "RO_SDE", ro_sde), \
                mock.patch.object(module, "load_edges", lambda path: edges), \
                mock.patch.object(module, "load_turns", lambda path: [(1, 2)]), \
                mock.patch.object(module, "RouteSolver", lambda network, sr: solver), \
                mock.patch.object(module.config, "OUTPUT_DIR", Path(directory.name)), \
                mock.patch("builtins.print", side_effect=lambda *a, **k: printed.append(" ".join(map(str, a)))):
            error = None

            try:
                module.main()
            except RuntimeError as caught:
                error = caught

        return error, "\n".join(printed), Path(directory.name)

    def test_a_passing_run_writes_a_csv_and_says_so(self):
        error, text, directory = self.run_main(FakeSolver())

        self.assertIsNone(error)
        self.assertIn("testable cases passed", text)
        files = list(directory.glob("smoke_test_*.csv"))
        self.assertEqual(len(files), 1)

        with open(files[0], newline="", encoding="utf-8") as csv_file:
            rows = list(csv.reader(csv_file))

        self.assertEqual(rows[0], ["check", "case", "verdict", "detail", "outcome", "message"])
        self.assertTrue(all(row[2] in ("PASS", "SKIP") for row in rows[1:]))
        self.assertEqual(sum(row[2] == "PASS" for row in rows[1:]), 6)

    def test_the_summary_warns_when_every_blocked_case_had_no_route(self):
        error, text, directory = self.run_main(FakeSolver(none_when_blocked=True))

        self.assertIsNone(error)
        self.assertIn("Blocked cases: 0 found a detour", text)
        self.assertIn("WARNING: no case found a detour", text)

        with open(next(directory.glob("smoke_test_*.csv")), newline="", encoding="utf-8") as csv_file:
            rows = list(csv.reader(csv_file))

        self.assertIn("no route", [row[4] for row in rows[1:]])
        self.assertTrue(any("030212" in row[5] for row in rows[1:]))

    def test_the_summary_does_not_warn_when_detours_are_found(self):
        _, text, _ = self.run_main(FakeSolver())

        self.assertIn("found a detour", text)
        self.assertNotIn("WARNING: no case found a detour", text)

    def test_a_failure_raises_after_listing_the_cases(self):
        error, text, _ = self.run_main(FakeSolver(drives_through=True))

        self.assertIsNotNone(error)
        self.assertIn("failed or could not run", str(error))
        self.assertIn("FAIL", text)

    def test_the_owner_connection_is_warned_about(self):
        _, text, _ = self.run_main(FakeSolver(), ro_sde=None, user="SDEADM")

        self.assertIn("WARNING: this is the owner's connection", text)

    def test_a_normal_login_is_not_warned_about(self):
        _, text, _ = self.run_main(FakeSolver(), ro_sde="RO.sde", user="HRM\\someone")

        self.assertNotIn("WARNING", text)

    def test_all_skipped_is_an_error(self):
        class AllIndirect(FakeSolver):
            def length(self, points, restricted):
                return 999.0

        error, _, _ = self.run_main(AllIndirect())

        self.assertIsNotNone(error)


if __name__ == "__main__":
    unittest.main()
