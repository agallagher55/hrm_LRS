"""
Smoke test the QA network with real route solves, using the network's own data for the stops.

It checks the two restrictions that matter after a rebuild:
  - TrafficTurn: for a sample of two edge turns (and the named ones below), it routes from the
    middle of the first edge to the middle of the second. Without restrictions the route goes
    straight through the junction. With TrafficTurn on it must not: it has to detour or find no
    route. A route as short as the direct one means the prohibited turn was driven.
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
from collections import namedtuple

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

# Edges shorter than this are not used. Stops near an end could snap to the next street.
MIN_EDGE_LENGTH = 40.0

# Route lengths within this many metres count as the same route.
TOLERANCE = 3.0
SEARCH_TOLERANCE = "20 Meters"

Edge = namedtuple("Edge", "oid str_dir name length parts shape")
Result = namedtuple("Result", "check case verdict detail")


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
    """Solves a two stop route with or without the restrictions and returns its length."""

    def __init__(self, network, spatial_reference):
        self.network = network
        self.spatial_reference = spatial_reference
        self.stops = None

    def make_stops(self, points):
        if self.stops is None:
            self.stops = arcpy.management.CreateFeatureclass(
                "memory", "smoke_stops", "POINT", spatial_reference=self.spatial_reference
            ).getOutput(0)

        arcpy.management.DeleteRows(self.stops)

        with arcpy.da.InsertCursor(self.stops, ["SHAPE@"]) as cursor:
            for point in points:
                cursor.insertRow([point])

    def length(self, points, restricted):
        """Route length in metres between the points in order, or None when there is no route."""
        self.make_stops(points)
        layer_name = "smoke_route"
        options = {"find_best_order": "USE_INPUT_ORDER", "hierarchy": "NO_HIERARCHY"}

        if restricted:
            options["restriction_attribute_name"] = RESTRICTIONS

        layer = arcpy.na.MakeRouteLayer(self.network, layer_name, IMPEDANCE, **options).getOutput(0)

        try:
            names = arcpy.na.GetNAClassNames(layer)
            arcpy.na.AddLocations(
                layer, names["Stops"], self.stops, "", SEARCH_TOLERANCE,
                append="CLEAR", snap_to_position_along_network="SNAP", exclude_restricted_elements="INCLUDE",
            )

            try:
                arcpy.na.Solve(layer, "SKIP", "TERMINATE")
            except arcpy.ExecuteError:
                if "030212" in arcpy.GetMessages() or "no solution" in arcpy.GetMessages().lower():
                    return None

                raise

            routes = layer.listLayers(names["Routes"])[0]
            lengths = [row[0] for row in arcpy.da.SearchCursor(routes, ["Total_" + IMPEDANCE])]

            return lengths[0] if lengths else None
        finally:
            arcpy.management.Delete(layer_name)


def run_turn_checks(solver, chosen, edges, not_found):
    results = [Result("turn", name, "ERROR", "no turn between these streets was found in the data") for name in not_found]

    for label, first, second in chosen:
        try:
            a, b = edges[first], edges[second]
            points = [a.shape.positionAlongLine(0.5, True), b.shape.positionAlongLine(0.5, True)]
            direct = a.length / 2 + b.length / 2
            unrestricted = solver.length(points, False)
            restricted = solver.length(points, True) if same(unrestricted, direct) else None
            verdict, detail = judge_turn(direct, unrestricted, restricted)
        except Exception as error:  # noqa: BLE001 one odd case must not stop the others
            verdict, detail = "ERROR", f"{type(error).__name__}: {error}"

        results.append(Result("turn", label, verdict, detail))

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
                backward = solver.length([b, a], True)

                if code == "FOTD":
                    allowed, blocked, blocked_points = forward, backward, [b, a]
                elif code == "FDTO":
                    allowed, blocked, blocked_points = backward, forward, [a, b]
                else:
                    allowed, blocked, blocked_points = forward, backward, None

                unrestricted = solver.length(blocked_points, False) if blocked_points else None
                verdict, detail = judge_oneway(code, half, allowed, blocked, unrestricted)
            except Exception as error:  # noqa: BLE001
                verdict, detail = "ERROR", f"{type(error).__name__}: {error}"

            results.append(Result("oneway", label, verdict, detail))

        if not edges:
            results.append(Result("oneway", code, "ERROR", f"no usable {code} edge to test"))

    return results


def summarise(results):
    counts = {}

    for result in results:
        key = (result.check, result.verdict)
        counts[key] = counts.get(key, 0) + 1

    return counts


def write_csv(path, results):
    with open(path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["check", "case", "verdict", "detail"])

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
    chosen, not_found = choose_turns(load_turns(paths["turn"]), edges, NAMED_TURNS, SAMPLE_TURNS, SEED)
    by_code = choose_oneway(edges, SAMPLE_ONEWAY_PER_CODE, SEED)
    spatial_reference = arcpy.Describe(paths["edge"]).spatialReference
    solver = RouteSolver(paths["network"], spatial_reference)
    print(f"{len(edges):,} edges; testing {len(chosen)} turns and "
          f"{sum(len(items) for items in by_code.values())} one way edges.")
    results = run_turn_checks(solver, chosen, edges, not_found) + run_oneway_checks(solver, by_code)

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
