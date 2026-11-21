"""Warehouse order assignment, aisle-policy routing, and MIP benchmark."""

from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import product
from pathlib import Path
from typing import Iterable

import pandas as pd
import pyomo.environ as pyo


DEPOT = "DEPOT"
POLICIES = ("Return", "Traversal", "Largest Gap")
MAX_ASSIGNMENT_COMBINATIONS = 4096


@dataclass(frozen=True)
class DataBundle:
    inventory: pd.DataFrame
    orders: pd.DataFrame
    warehouse: pd.DataFrame
    distances: pd.DataFrame


@dataclass(frozen=True)
class RoutePlan:
    strategy: str
    distance: float
    selected_locations: dict[str, str]
    visit_order: tuple[str, ...]
    path: tuple[tuple[float, float], ...]
    optimal: bool = False


def load_data(data_dir: str | Path | None = None) -> DataBundle:
    project_dir = Path(__file__).resolve().parent
    directory = Path(data_dir) if data_dir is not None else project_dir / "data"
    inventory = pd.read_csv(directory / "inventory.csv")
    orders = pd.read_csv(directory / "orders.csv")
    distances = pd.read_csv(directory / "distance_matrix.csv", index_col=0)
    warehouse = pd.read_csv(project_dir / "phase2" / "data" / "warehouse.csv")

    required = {
        "inventory": (inventory, {"sku_id", "location_id", "available_qty"}),
        "orders": (orders, {"order_id", "sku_id", "demand_qty"}),
        "warehouse": (
            warehouse,
            {"location_id", "aisle_number", "position_number", "x", "y"},
        ),
    }
    for name, (frame, columns) in required.items():
        missing = columns - set(frame.columns)
        if missing:
            raise ValueError(f"{name} data is missing columns: {sorted(missing)}")

    for frame, column in (
        (inventory, "sku_id"),
        (inventory, "location_id"),
        (orders, "order_id"),
        (orders, "sku_id"),
        (warehouse, "location_id"),
    ):
        frame[column] = frame[column].astype(str).str.strip()

    inventory["available_qty"] = pd.to_numeric(
        inventory["available_qty"], errors="raise"
    )
    orders["demand_qty"] = pd.to_numeric(orders["demand_qty"], errors="raise")
    if (inventory["available_qty"] < 0).any():
        raise ValueError("Inventory quantities cannot be negative.")
    if (orders["demand_qty"] <= 0).any():
        raise ValueError("Order demand quantities must be positive.")
    if inventory.duplicated(["sku_id", "location_id"]).any():
        raise ValueError("Inventory contains duplicate SKU/location records.")
    if not set(inventory["location_id"]).issubset(set(warehouse["location_id"])):
        raise ValueError("Inventory references locations absent from the warehouse.")
    if not set(orders["sku_id"]).issubset(set(inventory["sku_id"])):
        raise ValueError("An order references a SKU absent from inventory.")

    distances.index = distances.index.astype(str).str.strip()
    distances.columns = distances.columns.astype(str).str.strip()
    if set(distances.index) != set(distances.columns):
        raise ValueError("Distance matrix row and column labels do not match.")
    if DEPOT not in distances.index:
        raise ValueError(f"Distance matrix must include {DEPOT}.")
    values = distances.apply(pd.to_numeric, errors="raise")
    if values.isna().any().any() or (values < 0).any().any():
        raise ValueError("Distance matrix values must be finite and non-negative.")
    if not values.index.equals(values.columns):
        values = values.loc[values.index, values.index]
    if not (values.to_numpy() == values.to_numpy().T).all():
        raise ValueError("Distance matrix must be symmetric.")
    if (values.values.diagonal() != 0).any():
        raise ValueError("Distance matrix diagonal must be zero.")
    if not set(warehouse["location_id"]).issubset(set(values.index)):
        raise ValueError("Distance matrix is missing warehouse locations.")

    return DataBundle(inventory, orders, warehouse, values)


def order_ids(data: DataBundle) -> list[str]:
    return sorted(data.orders["order_id"].unique().tolist())


def _order_candidates(
    order_id: str, data: DataBundle
) -> tuple[dict[str, list[str]], dict[str, int]]:
    order = data.orders[data.orders["order_id"] == order_id]
    if order.empty:
        raise ValueError(f"Order {order_id} was not found.")
    demand = (
        order.groupby("sku_id", as_index=True)["demand_qty"]
        .sum()
        .astype(int)
        .to_dict()
    )
    if any(quantity <= 0 for quantity in demand.values()):
        raise ValueError("Order demand quantities must be positive.")
    candidates: dict[str, list[str]] = {}
    for sku, quantity in demand.items():
        rows = data.inventory[
            (data.inventory["sku_id"] == sku)
            & (data.inventory["available_qty"] >= quantity)
        ]
        locations = sorted(rows["location_id"].tolist())
        if not locations:
            raise ValueError(
                f"No single location has enough stock for {sku}, "
                f"demand={quantity}. Split picking is not supported."
            )
        candidates[sku] = locations
    return candidates, demand


def _append_point(
    points: list[tuple[float, float]], point: tuple[float, float]
) -> None:
    normalized = (float(point[0]), float(point[1]))
    if not points or points[-1] != normalized:
        points.append(normalized)


def _path_distance(points: Iterable[tuple[float, float]]) -> float:
    path = list(points)
    distance = 0.0
    for first, second in zip(path, path[1:]):
        dx = abs(first[0] - second[0])
        dy = abs(first[1] - second[1])
        if dx and dy:
            raise ValueError("Route path contains a non-orthogonal segment.")
        distance += dx + dy
    return distance


def _group_locations(
    locations: Iterable[str], data: DataBundle
) -> tuple[pd.DataFrame, dict[int, list[pd.Series]]]:
    unique = sorted(set(locations))
    layout = data.warehouse.set_index("location_id")
    unknown = set(unique) - set(layout.index)
    if unknown:
        raise ValueError(f"Unknown picking locations: {sorted(unknown)}")
    rows = layout.loc[unique].reset_index()
    groups: dict[int, list[pd.Series]] = {}
    for _, row in rows.iterrows():
        groups.setdefault(int(row["aisle_number"]), []).append(row)
    for aisle_rows in groups.values():
        aisle_rows.sort(key=lambda row: (int(row["position_number"]), row["location_id"]))
    return rows, groups


def _largest_gap_groups(
    groups: dict[int, list[pd.Series]],
) -> tuple[dict[int, list[pd.Series]], dict[int, list[pd.Series]]]:
    front: dict[int, list[pd.Series]] = {}
    rear: dict[int, list[pd.Series]] = {}
    for aisle, rows in groups.items():
        positions = sorted({int(row["position_number"]) for row in rows})
        boundaries = [0, *positions, 11]
        gaps = [
            (boundaries[index + 1] - boundaries[index], boundaries[index], boundaries[index + 1])
            for index in range(len(boundaries) - 1)
        ]
        _, low_boundary, high_boundary = max(
            gaps, key=lambda gap: (gap[0], -gap[1])
        )
        low_rows = [row for row in rows if int(row["position_number"]) <= low_boundary]
        high_rows = [row for row in rows if int(row["position_number"]) >= high_boundary]
        if low_rows:
            front[aisle] = low_rows
        if high_rows:
            rear[aisle] = high_rows
    return front, rear


def _policy_route(
    locations: Iterable[str], policy: str, data: DataBundle
) -> tuple[float, tuple[str, ...], tuple[tuple[float, float], ...]]:
    if policy not in POLICIES:
        raise ValueError(f"Unknown routing policy: {policy}")
    _, groups = _group_locations(locations, data)
    aisle_x = (
        data.warehouse[["aisle_number", "x"]]
        .drop_duplicates()
        .set_index("aisle_number")["x"]
        .astype(float)
        .to_dict()
    )
    points: list[tuple[float, float]] = [(0.0, 0.0)]
    visits: list[str] = []

    if policy == "Return":
        for aisle in sorted(groups):
            x = aisle_x[aisle]
            _append_point(points, (x, 0))
            for row in groups[aisle]:
                _append_point(points, (x, int(row["y"])))
                visits.append(str(row["location_id"]))
            _append_point(points, (x, 0))
        _append_point(points, (0, 0))

    elif policy == "Traversal":
        aisles = sorted(groups)
        for index, aisle in enumerate(aisles):
            x = aisle_x[aisle]
            forward = index % 2 == 0
            entry_y, exit_y = (0, 11) if forward else (11, 0)
            _append_point(points, (x, entry_y))
            rows = groups[aisle] if forward else list(reversed(groups[aisle]))
            for row in rows:
                _append_point(points, (x, int(row["y"])))
                visits.append(str(row["location_id"]))
            _append_point(points, (x, exit_y))
            if index + 1 < len(aisles):
                next_x = aisle_x[aisles[index + 1]]
                _append_point(points, (next_x, exit_y))
        if aisles and len(aisles) % 2:
            bridge_x = min(float(value) for value in aisle_x.values())
            _append_point(points, (bridge_x, 11))
            _append_point(points, (bridge_x, 0))
        _append_point(points, (0, 0))

    else:
        front_groups, rear_groups = _largest_gap_groups(groups)
        front_aisles = sorted(front_groups)
        rear_aisles = sorted(rear_groups)
        for aisle in front_aisles:
            x = aisle_x[aisle]
            _append_point(points, (x, 0))
            for row in front_groups[aisle]:
                _append_point(points, (x, int(row["y"])))
                visits.append(str(row["location_id"]))
            _append_point(points, (x, 0))
        if not rear_aisles:
            _append_point(points, (0, 0))
            return _path_distance(points), tuple(visits), tuple(points)
        front_end_x = aisle_x[front_aisles[-1]] if front_aisles else 0.0
        bridges = sorted({float(value) for value in aisle_x.values()})
        candidates: list[
            tuple[float, float, list[tuple[float, float]], list[str]]
        ] = []
        for bridge_x in bridges:
            candidate_points = list(points)
            candidate_visits = list(visits)
            _append_point(candidate_points, (bridge_x, 0))
            _append_point(candidate_points, (bridge_x, 11))
            for aisle in rear_aisles:
                x = aisle_x[aisle]
                _append_point(candidate_points, (x, 11))
                for row in reversed(rear_groups[aisle]):
                    _append_point(candidate_points, (x, int(row["y"])))
                    candidate_visits.append(str(row["location_id"]))
                _append_point(candidate_points, (x, 11))
            _append_point(candidate_points, (bridge_x, 11))
            _append_point(candidate_points, (bridge_x, 0))
            _append_point(candidate_points, (0, 0))
            candidates.append(
                (
                    _path_distance(candidate_points),
                    abs(front_end_x - bridge_x),
                    candidate_points,
                    candidate_visits,
                )
            )
        _, _, points, visits = min(candidates, key=lambda item: (item[0], item[1]))

    return _path_distance(points), tuple(visits), tuple(points)


def _assignments(
    candidates: dict[str, list[str]],
) -> Iterable[dict[str, str]]:
    skus = list(candidates)
    combinations = 1
    for locations in candidates.values():
        combinations *= len(locations)
    if combinations > MAX_ASSIGNMENT_COMBINATIONS:
        raise ValueError(
            f"Heuristic location search has {combinations} combinations; "
            f"the supported maximum is {MAX_ASSIGNMENT_COMBINATIONS}."
        )
    for selected in product(*(candidates[sku] for sku in skus)):
        yield dict(zip(skus, selected))


def solve_heuristic(
    order_id: str, policy: str, data: DataBundle
) -> RoutePlan:
    candidates, _ = _order_candidates(order_id, data)
    best: RoutePlan | None = None
    for assignment in _assignments(candidates):
        distance, visits, path = _policy_route(
            assignment.values(), policy, data
        )
        result = RoutePlan(
            strategy=policy,
            distance=distance,
            selected_locations=assignment,
            visit_order=visits,
            path=path,
        )
        if best is None or (
            result.distance,
            tuple(result.selected_locations.values()),
        ) < (
            best.distance,
            tuple(best.selected_locations.values()),
        ):
            best = result
    if best is None:
        raise RuntimeError(f"No feasible location assignment for order {order_id}.")
    return best


def _shortest_network_path(
    start: tuple[float, float],
    finish: tuple[float, float],
    data: DataBundle,
) -> list[tuple[float, float]]:
    x_values = sorted({0.0, *data.warehouse["x"].astype(float).tolist()})
    y_values = sorted({0.0, 11.0, *data.warehouse["y"].astype(float).tolist()})
    nodes = {(x, y) for x in x_values for y in y_values if x != 0 or y == 0}
    if start not in nodes or finish not in nodes:
        raise ValueError("Route endpoint is not on the warehouse travel network.")
    adjacency: dict[tuple[float, float], list[tuple[tuple[float, float], float]]] = {
        node: [] for node in nodes
    }

    def connect(first: tuple[float, float], second: tuple[float, float]) -> None:
        distance = abs(first[0] - second[0]) + abs(first[1] - second[1])
        adjacency[first].append((second, distance))
        adjacency[second].append((first, distance))

    for x in x_values:
        if x == 0:
            continue
        for lower, upper in zip(y_values, y_values[1:]):
            connect((x, lower), (x, upper))
    for y in (0.0, 11.0):
        cross_aisle_x = x_values if y == 0 else x_values[1:]
        for left, right in zip(cross_aisle_x, cross_aisle_x[1:]):
            connect((left, y), (right, y))

    distances = {start: 0.0}
    previous: dict[tuple[float, float], tuple[float, float]] = {}
    queue = [(0.0, start)]
    while queue:
        current_distance, current = heappop(queue)
        if current == finish:
            break
        if current_distance != distances[current]:
            continue
        for neighbor, edge_distance in adjacency[current]:
            next_distance = current_distance + edge_distance
            if next_distance < distances.get(neighbor, float("inf")):
                distances[neighbor] = next_distance
                previous[neighbor] = current
                heappush(queue, (next_distance, neighbor))
    if finish not in distances:
        raise ValueError(f"No route between network nodes {start} and {finish}.")
    path = [finish]
    while path[-1] != start:
        path.append(previous[path[-1]])
    return list(reversed(path))


def _mip_path(
    route: Iterable[str], data: DataBundle
) -> tuple[tuple[float, float], ...]:
    layout = data.warehouse.set_index("location_id")
    labels = list(route)

    def coordinate(location: str) -> tuple[float, float]:
        if location == DEPOT:
            return (0.0, 0.0)
        row = layout.loc[location]
        return (float(row["x"]), float(row["y"]))

    points: list[tuple[float, float]] = []
    for origin, destination in zip(labels, labels[1:]):
        segment = _shortest_network_path(
            coordinate(origin), coordinate(destination), data
        )
        for point in segment:
            _append_point(points, point)
    return tuple(points)


def solve_mip(order_id: str, data: DataBundle) -> RoutePlan:
    candidates, _ = _order_candidates(order_id, data)
    skus = list(candidates)
    locations = sorted({location for options in candidates.values() for location in options})
    nodes = [DEPOT, *locations]
    arcs = [(i, j) for i in nodes for j in nodes if i != j]
    distance = {
        (i, j): float(data.distances.loc[i, j]) for i, j in arcs
    }
    location_skus = {
        location: [sku for sku in skus if location in candidates[sku]]
        for location in locations
    }
    big_m = max(1, len(locations))

    model = pyo.ConcreteModel()
    model.S = pyo.Set(initialize=skus)
    model.N = pyo.Set(initialize=locations)
    model.V = pyo.Set(initialize=nodes)
    model.x = pyo.Var(
        [(sku, location) for sku in skus for location in candidates[sku]],
        domain=pyo.Binary,
    )
    model.z = pyo.Var(model.N, domain=pyo.Binary)
    model.y = pyo.Var(arcs, domain=pyo.Binary)
    model.u = pyo.Var(
        model.N, domain=pyo.NonNegativeIntegers, bounds=(0, big_m)
    )
    model.objective = pyo.Objective(
        expr=sum(distance[arc] * model.y[arc] for arc in arcs),
        sense=pyo.minimize,
    )
    model.fulfil = pyo.Constraint(
        model.S,
        rule=lambda m, sku: sum(m.x[sku, location] for location in candidates[sku]) == 1,
    )
    model.visit_link_lower = pyo.Constraint(
        model.N,
        rule=lambda m, location: m.z[location]
        <= sum(m.x[sku, location] for sku in location_skus[location]),
    )
    model.visit_link_upper = pyo.Constraint(
        model.N,
        rule=lambda m, location: sum(
            m.x[sku, location] for sku in location_skus[location]
        )
        <= len(location_skus[location]) * m.z[location],
    )
    model.outgoing = pyo.Constraint(
        model.N,
        rule=lambda m, i: sum(m.y[i, j] for j in nodes if j != i) == m.z[i],
    )
    model.incoming = pyo.Constraint(
        model.N,
        rule=lambda m, i: sum(m.y[j, i] for j in nodes if j != i) == m.z[i],
    )
    model.depot_out = pyo.Constraint(
        expr=sum(model.y[DEPOT, j] for j in locations) == 1
    )
    model.depot_in = pyo.Constraint(
        expr=sum(model.y[i, DEPOT] for i in locations) == 1
    )
    model.mtz = pyo.Constraint(
        model.N,
        model.N,
        rule=lambda m, i, j: pyo.Constraint.Skip
        if i == j
        else m.u[i] - m.u[j] + big_m * m.y[i, j] <= big_m - 1,
    )
    model.order_lower = pyo.Constraint(
        model.N, rule=lambda m, i: m.u[i] >= m.z[i]
    )
    model.order_upper = pyo.Constraint(
        model.N, rule=lambda m, i: m.u[i] <= big_m * m.z[i]
    )

    solver = pyo.SolverFactory("appsi_highs")
    if not solver.available(exception_flag=False):
        solver = pyo.SolverFactory("highs")
    if not solver.available(exception_flag=False):
        raise RuntimeError(
            "HiGHS was not found. Install project dependencies with "
            "`python -m pip install -r requirements.txt`."
        )
    results = solver.solve(model, tee=False)
    termination = results.solver.termination_condition
    if termination != pyo.TerminationCondition.optimal:
        raise RuntimeError(f"MIP did not prove optimality: {termination}.")

    selected = {
        sku: next(
            location
            for location in candidates[sku]
            if pyo.value(model.x[sku, location]) > 0.5
        )
        for sku in skus
    }
    next_node = {
        i: j for i, j in arcs if pyo.value(model.y[i, j]) > 0.5
    }
    route = [DEPOT]
    current = DEPOT
    for _ in range(len(locations) + 1):
        current = next_node[current]
        route.append(current)
        if current == DEPOT:
            break
    if route[-1] != DEPOT or len(route) != len(set(route)) + 1:
        raise RuntimeError("Could not reconstruct a valid depot-to-depot MIP route.")
    visits = tuple(location for location in route if location != DEPOT)
    return RoutePlan(
        strategy="MIP benchmark",
        distance=float(pyo.value(model.objective)),
        selected_locations=selected,
        visit_order=visits,
        path=_mip_path(route, data),
        optimal=True,
    )


def compare_order(order_id: str, data: DataBundle) -> list[RoutePlan]:
    plans = [solve_mip(order_id, data)]
    plans.extend(solve_heuristic(order_id, policy, data) for policy in POLICIES)
    return plans
