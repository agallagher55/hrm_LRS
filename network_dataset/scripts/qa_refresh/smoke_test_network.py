"""
Smoke test the QA network with real route solves, using the network's own data for the stops.

It checks the two restrictions that matter after a rebuild, and that ordinary turns still work:
  - TrafficTurn: for a sample of two edge turns (and the named ones below), it routes from the
    middle of the first edge to the middle of the second. Without restrictions the route goes
    straight through the junction. With TrafficTurn on it must not: it has to detour or find no
    route. A route as short as the direct one means the prohibited turn was driven.
  - Control: for a sample of pairs of ordinary two way edges that meet at a junction and have no
    turn record, it checks that the route through the junction still works with the restrictions
    on. Without this the other checks cannot tell a restriction that works from one that blocks
    every turn, because both end in "no route".
  - OneWay: for a sample of edges, it routes between the quarter and three quarter points of the
    edge in both directions. The direction the STR_DIR code blocks must detour or fail, and the
    other direction must run straight along the edge. BOTH edges must run in both directions.
    FOTD blocks travel against the digitized direction and FDTO blocks travel along it.

Because the stops come from the network's edges there are no coordinates to maintain. A case is
SKIPPED, not passed, when the unrestricted route is not the direct one (a short edge, a snapping
oddity), so a pass always means the restriction made the difference.

Set RO_SDE to the connection file of a login that is not SDEADM, pointing at the QA database
(ms-gis-sql-q21, GISRW01). Then the run also proves that the grants let a normal user open the
network and solve, which a SQL check cannot. With RO_SDE unset it uses the SDEADM connection and
says so, since an owner can open anything. If the network cannot be opened it says what the
connection can see, so a file for another server or database is easy to spot.

It reads QA and creates only temporary layers. The stops are written to the memory workspace.
Written 2026-10-09 and not yet run on live QA: the arcpy.na calls are the likeliest place for a
first run to need a small fix. Directions are not covered. Check them by hand with a route solve
in Pro.
"""

import csv
import datetime
import os
import random
from collections import Counter, defaultdict, namedtuple

import arcpy

import config


# Connection file of a login that is not SDEADM, for example one with Windows authentication.
# None uses the SDEADM connection.
RO_SDE = None

NETWORK_KEY = config.NETWORK_DEF.key
IMPEDANCE = "Length"
RESTRICTIONS = ["OneWay", "TrafficTurn"]

# How many cases to try. The sample is the same every run (SEED) so two runs can be compared.
SAMPLE_TURNS = 25
SAMPLE_ONEWAY_PER_CODE = 8
SEED = 20261009

# Turns to test by name: the first street is the one the turn starts on. Each pair has to be found
# in the data, or the run reports it.
NAMED_TURNS = [("QUINPOOL RD", "ROBIE ST")]

# How many ordinary junction pairs to use as controls, and how exactly two edge ends must meet
# (decimal places of a metre) to count as the same junction.
SAMPLE_CONTROLS = 8
ENDPOINT_PRECISION = 2

# Edges shorter than this are not used. Stops near an end could snap to the next street.
MIN_EDGE_LENGTH = 40.0

# Route lengths within this many metres count as the same route.
TOLERANCE = 3.0
SEARCH_TOLERANCE = "20 Meters"

Edge = namedtuple("Edge", "oid str_dir name length parts shape")
# outcome says how a blocked case ended: "detour", "no route" or, for a two way edge, "straight".
# message is what the solver said when it found no route.
Result = namedtuple("Result", "check case verdict detail outcome message", defaults=("", ""))


def network_paths(sde):
    definition = config.NETWORK_DEF
    folder = os.path.join(sde, definition.feature_dataset)

    return {
        "network": os.path.join(folder, "SDEADM." + definition.network_name),
        "edge": os.path.join(folder, "SDEADM." + definition.edge_name),
        "turn": os.path.join(folder, "SDEADM." + definition.turn_name),
    }


def connection_summary(connection):
    """What the connection file says about itself: instance, database and login."""
    properties = getattr(arcpy.Describe(connection), "connectionProperties", None)
    parts = []

    for name in ("instance", "database", "authentication_mode", "user"):
        value = getattr(properties, name, None)

        if value:
            parts.append(f"{name}: {value}")

    return ", ".join(parts) or "the connection file does not say (operating system login?)"


def explain_missing_network(connection, paths):
    """Say why the network cannot be opened, from what the connection can see."""
    arcpy.env.workspace = connection
    datasets = arcpy.ListDatasets() or []
    feature_dataset = config.NETWORK_DEF.feature_dataset
    message = [
        f"Cannot open the network dataset through this connection: {paths['network']}",
        f"The connection is: {connection_summary(connection)}",
        f"QA is {config.QA_SDE}. If the instance or database above is not the QA one, the file points somewhere else.",
    ]

    if not datasets:
        message.append(
            "This login sees no feature datasets at all: the wrong database, or no SELECT permission on them."
        )
    elif feature_dataset.upper() not in [name.upper() for name in datasets]:
        message.append(
            f"It sees {len(datasets)} feature datasets but not {feature_dataset}: probably a different or "
            "older copy of the database that does not have the rebuilt network (for example a read only copy). "
            f"Seen: {', '.join(datasets[:10])}"
        )
    else:
        message.append(
            f"It sees {feature_dataset} but cannot open the network inside it: the grants are the likely cause. "
            "Run audit_grants.py and grant_network_access.py against QA."
        )

    return "\n".join(message)


def load_edges(edge_fc):
    """Return {object id: Edge} for every edge."""
    edges = {}
    fields = ["OID@", "STR_DIR", "FULL_NAME", "SHAPE@LENGTH", "SHAPE@"]

    for oid, str_dir, name, length, shape in arcpy.da.SearchCursor(edge_fc, fields):
        parts = shape.partCount if shape is not None else 0
        edges[oid] = Edge(oid, (str_dir or "").upper(), (name or "").upper(), length or 0.0, parts, shape)

    return edges


def load_turns(turn_fc):
    """Return the edge object ids of each turn, in order, as a list of tuples."""
    names = [field.name.upper() for field in arcpy.ListFields(turn_fc)]
    slots = [f"Edge{n}FID" for n in range(1, 6) if f"EDGE{n}FID" in names]
    turns = []

    for row in arcpy.da.SearchCursor(turn_fc, slots):
        ids = tuple(value for value in row if value)
        turns.append(ids)

    return turns


def choose_turns(turns, edges, named, sample_size, seed):
    """Pick the turns to test: every named match, then a random sample of two edge turns.

    Returns (chosen list of (label, e1, e2), names that were not found).
    """
    two_edge = [turn for turn in turns if len(turn) == 2 and turn[0] in edges and turn[1] in edges]
    chosen = []
    not_found = []

    for first, second in named:
        matches = [
            turn for turn in two_edge
            if edges[turn[0]].name == first.upper() and edges[turn[1]].name == second.upper()
        ]

        if not matches:
            not_found.append(f"{first} -> {second}")

        for turn in matches:
            chosen.append((f"{first} -> {second} (edges {turn[0]} -> {turn[1]})", turn[0], turn[1]))

    usable = [turn for turn in two_edge if min(edges[turn[0]].length, edges[turn[1]].length) >= MIN_EDGE_LENGTH]
    picked = random.Random(seed).sample(usable, min(sample_size, len(usable)))

    for turn in picked:
        label = f"{edges[turn[0]].name} -> {edges[turn[1]].name} (edges {turn[0]} -> {turn[1]})"

        if not any(item[1:] == turn for item in chosen):
            chosen.append((label, turn[0], turn[1]))

    return chosen, not_found


def endpoint_key(point):
    return (round(point.X, ENDPOINT_PRECISION), round(point.Y, ENDPOINT_PRECISION))


def choose_control_pairs(edges, turns, sample_size, seed):
    """Pick pairs of ordinary edges that meet at a junction, as (label, first oid, second oid).

    Both edges must be two way, long enough, one part and in no turn record, and every edge at the
    junction must be like that, so nothing in the data prohibits the move between them. A junction
    of two edges is a straight through move and one of three is a T junction.
    """
    in_a_turn = {oid for turn in turns for oid in turn}
    at_node = defaultdict(list)

    for edge in edges.values():
        if edge.shape is None:
            continue

        for point in (edge.shape.firstPoint, edge.shape.lastPoint):
            at_node[endpoint_key(point)].append(edge)

    pairs = []

    for node in sorted(at_node):
        meeting = {edge.oid: edge for edge in at_node[node]}

        if len(meeting) not in (2, 3) or len(at_node[node]) != len(meeting):
            continue

        if any(
            edge.str_dir != "BOTH" or edge.length < MIN_EDGE_LENGTH or edge.parts != 1 or edge.oid in in_a_turn
            for edge in meeting.values()
        ):
            continue

        kind = "straight through" if len(meeting) == 2 else "T junction"
        ordered = sorted(meeting)

        for index, first in enumerate(ordered):
            for second in ordered[index + 1:]:
                pairs.append((f"{kind}: {meeting[first].name} -> {meeting[second].name} (edges {first} -> {second})", first, second))

    return random.Random(seed).sample(pairs, min(sample_size, len(pairs)))


def choose_oneway(edges, per_code, seed):
    """Pick edges by one way code: {code: [edges]}. Multipart and short edges are left out."""
    chosen = {}

    for code in ("FOTD", "FDTO", "BOTH"):
        usable = sorted(
            (edge for edge in edges.values()
             if edge.str_dir == code and edge.length >= MIN_EDGE_LENGTH and edge.parts == 1),
            key=lambda edge: edge.oid,
        )
        chosen[code] = random.Random(seed).sample(usable, min(per_code, len(usable)))

    return chosen


def same(first, second):
    return first is not None and second is not None and abs(first - second) <= TOLERANCE


def judge_turn(direct, unrestricted, restricted):
    """The verdict for one turn from the three lengths. None means no route was found."""
    if not same(unrestricted, direct):
        return "SKIP", f"the unrestricted route ({unrestricted}) is not the direct one ({direct:.0f} m)"

    if restricted is None:
        return "PASS", f"no route with the turn prohibited (direct was {direct:.0f} m)"

    if restricted > direct + TOLERANCE:
        return "PASS", f"detour of {restricted:.0f} m against {direct:.0f} m direct"

    return "FAIL", f"the route went straight through the prohibited turn ({restricted:.0f} m)"


def judge_control(direct, unrestricted, restricted):
    """The verdict for an ordinary junction move, which has to stay possible with the restrictions on."""
    if not same(unrestricted, direct):
        return "SKIP", f"the unrestricted route ({unrestricted}) is not the direct one ({direct:.0f} m)"

    if same(restricted, direct):
        return "PASS", f"the move through the junction still works ({direct:.0f} m)"

    if restricted is None:
        return "FAIL", "an ordinary move through a junction was blocked, so the restrictions block turns that have no turn record"

    return "FAIL", f"an ordinary move took {restricted:.0f} m instead of {direct:.0f} m"


def judge_oneway(code, half, allowed, blocked, blocked_unrestricted):
    """The verdict for one edge. Lengths are the restricted solves unless stated.

    For BOTH, allowed and blocked are the two directions and both must run straight.
    """
    if code == "BOTH":
        if same(allowed, half) and same(blocked, half):
            return "PASS", f"both directions run straight ({half:.0f} m)"

        return "FAIL", f"a two way edge was blocked or detoured ({allowed}, {blocked})"

    if not same(blocked_unrestricted, half):
        return "SKIP", f"unrestricted, the blocked direction is not the direct route ({blocked_unrestricted})"

    if not same(allowed, half):
        return "FAIL", f"the allowed direction was blocked or detoured ({allowed}, direct is {half:.0f} m)"

    if blocked is None:
        return "PASS", "the blocked direction has no route"

    if blocked > half + TOLERANCE:
        return "PASS", f"the blocked direction detours {blocked:.0f} m against {half:.0f} m direct"

    return "FAIL", f"the route ran the blocked way along the edge ({blocked:.0f} m)"


class RouteSolver:
    """Solves a two stop route with or without the restrictions and returns its length.

    It makes one route layer for each mode, the first time it is needed, and reuses it for every
    solve. Making and deleting a layer for each solve left layers behind: Delete does not remove a
    layer by name in a standalone run, and the next MakeRouteLayer then failed with ERROR 030036.
    """

    LAYER_NAMES = {True: "smoke_route_restricted", False: "smoke_route_unrestricted"}

    def __init__(self, network, spatial_reference):
        self.network = network
        self.spatial_reference = spatial_reference
        self.stops = None
        self.layers = {}
        self.last_message = ""

    def make_stops(self, points):
        if self.stops is None:
            self.stops = arcpy.management.CreateFeatureclass(
                "memory", "smoke_stops", "POINT", spatial_reference=self.spatial_reference
            ).getOutput(0)

        arcpy.management.DeleteRows(self.stops)

        with arcpy.da.InsertCursor(self.stops, ["SHAPE@"]) as cursor:
            for point in points:
                cursor.insertRow([point])

    def layer_for(self, restricted):
        """The route layer for this mode, made on first use. A leftover of the same name is removed."""
        if restricted not in self.layers:
            name = self.LAYER_NAMES[restricted]
            options = {"find_best_order": "USE_INPUT_ORDER", "hierarchy": "NO_HIERARCHY"}

            if restricted:
                options["restriction_attribute_name"] = RESTRICTIONS

            if arcpy.Exists(name):
                arcpy.management.Delete(name)

            self.layers[restricted] = arcpy.na.MakeRouteLayer(self.network, name, IMPEDANCE, **options).getOutput(0)

        return self.layers[restricted]

    def length(self, points, restricted):
        """Route length in metres between the points in order, or None when there is no route.

        When there is none, last_message holds what the solver said.
        """
        self.last_message = ""
        self.make_stops(points)
        layer = self.layer_for(restricted)
        names = arcpy.na.GetNAClassNames(layer)
        arcpy.na.AddLocations(
            layer, names["Stops"], self.stops, "", SEARCH_TOLERANCE,
            append="CLEAR", snap_to_position_along_network="SNAP", exclude_restricted_elements="INCLUDE",
        )

        try:
            arcpy.na.Solve(layer, "SKIP", "TERMINATE")
        except arcpy.ExecuteError:
            messages = arcpy.GetMessages()

            if "030212" in messages or "no solution" in messages.lower():
                self.last_message = condense_messages(messages)

                return None

            raise

        routes = layer.listLayers(names["Routes"])[0]
        lengths = [row[0] for row in arcpy.da.SearchCursor(routes, ["Total_" + IMPEDANCE])]

        return lengths[0] if lengths else None

    def close(self):
        """Remove the layers. Failing to is harmless, since they go when the process ends."""
        for name in self.LAYER_NAMES.values():
            try:
                if arcpy.Exists(name):
                    arcpy.management.Delete(name)
            except arcpy.ExecuteError:
                pass


def condense_messages(messages):
    """Only the ERROR and WARNING lines of a geoprocessing message, on one line."""
    lines = [line.strip() for line in str(messages).splitlines() if line.strip().upper().startswith(("ERROR", "WARNING"))]

    return " | ".join(lines) or str(messages).strip().replace("\n", " | ")


def solver_message(solver):
    """What the solver said about its last solve. Fakes in the tests may not have it."""
    return getattr(solver, "last_message", "") or ""


def one_line(error):
    """An exception as one line, so a multi line arcpy message does not swamp the output."""
    lines = [line.strip() for line in str(error).splitlines() if line.strip()]

    return f"{type(error).__name__}: " + " | ".join(lines)


def blocked_outcome(verdict, restricted_length):
    """How a passing blocked case ended: a detour was found, or there was no route at all."""
    if verdict != "PASS":
        return ""

    return "no route" if restricted_length is None else "detour"


def run_turn_checks(solver, chosen, edges, not_found):
    results = [Result("turn", name, "ERROR", "no turn between these streets was found in the data") for name in not_found]

    for label, first, second in chosen:
        try:
            a, b = edges[first], edges[second]
            points = [a.shape.positionAlongLine(0.5, True), b.shape.positionAlongLine(0.5, True)]
            direct = a.length / 2 + b.length / 2
            unrestricted = solver.length(points, False)
            restricted = solver.length(points, True) if same(unrestricted, direct) else None
            message = solver_message(solver) if restricted is None else ""
            verdict, detail = judge_turn(direct, unrestricted, restricted)
            outcome = blocked_outcome(verdict, restricted)
        except Exception as error:  # noqa: BLE001 one odd case must not stop the others
            verdict, detail, outcome, message = "ERROR", one_line(error), "", ""

        results.append(Result("turn", label, verdict, detail, outcome, message))

    return results


def run_control_checks(solver, pairs, edges):
    if not pairs:
        return [Result("control", "none", "ERROR", "no pair of ordinary edges was found to use as a control")]

    results = []

    for label, first, second in pairs:
        try:
            a, b = edges[first], edges[second]
            points = [a.shape.positionAlongLine(0.5, True), b.shape.positionAlongLine(0.5, True)]
            direct = a.length / 2 + b.length / 2
            unrestricted = solver.length(points, False)
            restricted = solver.length(points, True) if same(unrestricted, direct) else None
            message = solver_message(solver) if restricted is None else ""
            verdict, detail = judge_control(direct, unrestricted, restricted)
            outcome = "allowed" if verdict == "PASS" else ""
        except Exception as error:  # noqa: BLE001
            verdict, detail, outcome, message = "ERROR", one_line(error), "", ""

        results.append(Result("control", label, verdict, detail, outcome, message))

    return results


def run_oneway_checks(solver, by_code):
    results = []

    for code, edges in by_code.items():
        for edge in edges:
            label = f"{code} edge {edge.oid} {edge.name}"

            try:
                a = edge.shape.positionAlongLine(0.25, True)
                b = edge.shape.positionAlongLine(0.75, True)
                half = edge.length / 2
                forward = solver.length([a, b], True)
                forward_message = solver_message(solver)
                backward = solver.length([b, a], True)
                backward_message = solver_message(solver)

                if code == "FOTD":
                    allowed, blocked, blocked_points, message = forward, backward, [b, a], backward_message
                elif code == "FDTO":
                    allowed, blocked, blocked_points, message = backward, forward, [a, b], forward_message
                else:
                    allowed, blocked, blocked_points, message = forward, backward, None, ""

                unrestricted = solver.length(blocked_points, False) if blocked_points else None
                verdict, detail = judge_oneway(code, half, allowed, blocked, unrestricted)
                outcome = "straight" if code == "BOTH" and verdict == "PASS" else blocked_outcome(verdict, blocked)
                message = message if blocked is None else ""
            except Exception as error:  # noqa: BLE001
                verdict, detail, outcome, message = "ERROR", one_line(error), "", ""

            results.append(Result("oneway", label, verdict, detail, outcome, message))

        if not edges:
            results.append(Result("oneway", code, "ERROR", f"no usable {code} edge to test"))

    return results


def summarise(results):
    counts = {}

    for result in results:
        key = (result.check, result.verdict)
        counts[key] = counts.get(key, 0) + 1

    return counts


def detour_report(results):
    """Lines about how the blocked cases ended, with a warning when no case found a detour.

    A prohibited turn or one way edge normally has a way round, so a route that was never found in
    any case may mean the solver is failing for another reason, not that the restriction works.
    """
    blocked = [result for result in results if result.outcome in ("detour", "no route")]
    controls = [result for result in results if result.check == "control" and result.verdict in ("PASS", "FAIL")]

    if not blocked:
        return []

    detours = [result for result in blocked if result.outcome == "detour"]
    none = [result for result in blocked if result.outcome == "no route"]
    lines = [f"\nBlocked cases: {len(detours)} found a detour, {len(none)} found no route at all."]
    messages = Counter(result.message or "(the solver gave no message)" for result in none)

    for message, number in messages.most_common():
        lines.append(f"  {number:>3} x solver said: {message}")

    if controls:
        allowed = [result for result in controls if result.verdict == "PASS"]
        lines.append(f"Controls: {len(allowed)} of {len(controls)} ordinary junction moves still worked with the restrictions on.")

    if none and not detours:
        if controls and not [result for result in controls if result.verdict == "PASS"]:
            lines.append(
                "WARNING: no ordinary turn works with the restrictions on, so every blocked case ended with no route "
                "because turns in general are blocked, not because of the prohibited turn. Look at the TrafficTurn "
                "evaluators (the default turn evaluator is restricted in the template)."
            )
        else:
            lines.append(
                "WARNING: no case found a detour. Every blocked case ended with no route, so these results cannot tell "
                "a working restriction from a solver that fails for another reason. Solve one case by hand in Pro with "
                "OneWay and TrafficTurn ticked, for example the QUINPOOL RD -> ROBIE ST turn, and compare."
            )

    return lines


def write_csv(path, results):
    with open(path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["check", "case", "verdict", "detail", "outcome", "message"])

        for result in results:
            writer.writerow(list(result))


def main():
    connection = RO_SDE or config.QA_SDE
    paths = network_paths(connection)
    user = getattr(getattr(arcpy.Describe(connection), "connectionProperties", None), "user", "")
    print(f"Network: {NETWORK_KEY}; connection: {connection}")
    print(f"Connection details: {connection_summary(connection)}")

    if not RO_SDE or str(user).upper() == "SDEADM":
        print("WARNING: this is the owner's connection, so it does not prove the grants work for other users. "
              "Set RO_SDE to a connection file for a normal login.")

    if not arcpy.Exists(paths["network"]):
        raise RuntimeError(explain_missing_network(connection, paths))

    arcpy.CheckOutExtension("Network")
    edges = load_edges(paths["edge"])
    turns = load_turns(paths["turn"])
    chosen, not_found = choose_turns(turns, edges, NAMED_TURNS, SAMPLE_TURNS, SEED)
    by_code = choose_oneway(edges, SAMPLE_ONEWAY_PER_CODE, SEED)
    controls = choose_control_pairs(edges, turns, SAMPLE_CONTROLS, SEED)
    spatial_reference = arcpy.Describe(paths["edge"]).spatialReference
    solver = RouteSolver(paths["network"], spatial_reference)
    print(f"{len(edges):,} edges; testing {len(chosen)} turns, {len(controls)} control junctions and "
          f"{sum(len(items) for items in by_code.values())} one way edges.")

    try:
        results = (
            run_turn_checks(solver, chosen, edges, not_found)
            + run_control_checks(solver, controls, edges)
            + run_oneway_checks(solver, by_code)
        )
    finally:
        solver.close()

    for result in results:
        print(f"  {result.verdict:<5} {result.check:<7} {result.case}: {result.detail}")

    config.OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = config.OUTPUT_DIR / f"smoke_test_{stamp}.csv"
    write_csv(path, results)
    counts = summarise(results)
    print("\nSummary")

    for (check, verdict), number in sorted(counts.items()):
        print(f"  {check:<7} {verdict:<5} {number}")

    for line in detour_report(results):
        print(line)

    print(f"\nWrote {path}")
    bad = [result for result in results if result.verdict in ("FAIL", "ERROR")]
    passed = [result for result in results if result.verdict == "PASS"]

    if bad:
        raise RuntimeError(f"{len(bad)} smoke test cases failed or could not run. See the lines above.")

    if not passed:
        raise RuntimeError("No case could be tested: every one was skipped.")

    print(f"All {len(passed)} testable cases passed ({len(results) - len(passed)} skipped).")


if __name__ == "__main__":
    main()
