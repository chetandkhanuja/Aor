from dataclasses import replace

import pandas as pd
import pytest

from warehouse_optimizer import (
    POLICIES,
    _path_distance,
    _shortest_network_path,
    compare_order,
    load_data,
    order_ids,
    solve_heuristic,
    solve_mip,
)


@pytest.fixture(scope="module")
def data():
    return load_data()


def test_source_data_is_consistent(data):
    assert len(data.warehouse) == 100
    assert data.distances.shape == (101, 101)
    assert order_ids(data) == ["ORD001", "ORD002"]
    assert (data.distances.values.diagonal() == 0).all()


@pytest.mark.parametrize(
    "order_id", ["ORD001", "ORD002"]
)
@pytest.mark.parametrize("policy", POLICIES)
def test_policy_routes_cover_each_selected_location(data, order_id, policy):
    plan = solve_heuristic(order_id, policy, data)
    assert set(plan.visit_order) == set(plan.selected_locations.values())
    assert len(plan.visit_order) == len(set(plan.visit_order))
    assert _path_distance(plan.path) == pytest.approx(plan.distance)
    assert all(
        first[0] == second[0] or first[1] == second[1]
        for first, second in zip(plan.path, plan.path[1:])
    )


@pytest.mark.parametrize(
    "order_id", ["ORD001", "ORD002"]
)
def test_mip_is_optimal_and_uses_a_feasible_route(data, order_id):
    plan = solve_mip(order_id, data)
    assert plan.optimal
    assert set(plan.visit_order) == set(plan.selected_locations.values())
    assert _path_distance(plan.path) == pytest.approx(plan.distance)
    assert plan.path[0] == (0.0, 0.0)
    assert plan.path[-1] == (0.0, 0.0)


@pytest.mark.parametrize(
    "order_id", ["ORD001", "ORD002"]
)
def test_mip_benchmarks_all_policy_results(data, order_id):
    plans = compare_order(order_id, data)
    mip = plans[0]
    assert [plan.strategy for plan in plans[1:]] == list(POLICIES)
    assert all(mip.distance <= plan.distance for plan in plans[1:])


def test_rejects_order_demand_without_single_location_supply(data):
    orders = data.orders.copy()
    orders.loc[
        (orders["order_id"] == "ORD001") & (orders["sku_id"] == "SKU01"),
        "demand_qty",
    ] = 100
    invalid_data = replace(data, orders=orders)
    with pytest.raises(ValueError, match="No single location has enough stock"):
        solve_heuristic("ORD001", "Return", invalid_data)


def test_largest_gap_does_not_visit_rear_when_no_rear_picks(data):
    orders = data.orders[
        (data.orders["order_id"] == "ORD001") & (data.orders["sku_id"] == "SKU01")
    ].copy()
    front_only_data = replace(data, orders=orders)
    plan = solve_heuristic("ORD001", "Largest Gap", front_only_data)
    assert max(y for _, y in plan.path) < 11
    assert plan.distance == pytest.approx(10)


# The following cases use new or modified order, inventory, and stock inputs.
# They test behavior, not only the values shipped with the original dataset.

def test_tc08_new_order_picks_nearest_stock_location(data):
    orders = pd.DataFrame(
        [{"order_id": "TEST-NEAREST", "sku_id": "SKU01", "demand_qty": 1}]
    )
    inventory = data.inventory.copy()
    test_data = replace(data, orders=orders, inventory=inventory)
    plan = solve_mip("TEST-NEAREST", test_data)
    assert plan.selected_locations["SKU01"] == "A1-L3"
    assert plan.distance == pytest.approx(10.0)


def test_tc09_new_order_aggregates_duplicate_demand_lines(data):
    orders = pd.DataFrame(
        [
            {"order_id": "TEST-SUM", "sku_id": "SKU01", "demand_qty": 1},
            {"order_id": "TEST-SUM", "sku_id": "SKU01", "demand_qty": 2},
        ]
    )
    test_data = replace(data, orders=orders)
    plan = solve_mip("TEST-SUM", test_data)
    assert plan.selected_locations["SKU01"] == "A1-L3"
    assert set(plan.visit_order) == {"A1-L3"}


def test_tc10_insufficient_total_stock_is_rejected(data):
    orders = pd.DataFrame(
        [{"order_id": "TEST-STOCK", "sku_id": "SKU01", "demand_qty": 4}]
    )
    test_data = replace(data, orders=orders)
    with pytest.raises(ValueError, match="No single location has enough stock"):
        solve_mip("TEST-STOCK", test_data)


def test_tc11_unknown_order_is_rejected(data):
    with pytest.raises(ValueError, match="Order TEST-UNKNOWN was not found"):
        solve_mip("TEST-UNKNOWN", data)


def test_tc12_zero_or_negative_demand_is_rejected_by_input_validation(tmp_path):
    inventory = pd.DataFrame(
        [{"sku_id": "SKU-X", "location_id": "A1-L1", "available_qty": 5}]
    )
    orders = pd.DataFrame(
        [{"order_id": "TEST-BAD", "sku_id": "SKU-X", "demand_qty": 0}]
    )
    inventory.to_csv(tmp_path / "inventory.csv", index=False)
    orders.to_csv(tmp_path / "orders.csv", index=False)
    pd.DataFrame(
        [
            {
                "location_id": "A1-L1",
                "aisle_number": 1,
                "position_number": 1,
                "x": 2,
                "y": 1,
            }
        ]
    ).to_csv(tmp_path / "warehouse.csv", index=False)
    distance_matrix = pd.DataFrame(
        [[0.0, 3.0], [3.0, 0.0]],
        index=["DEPOT", "A1-L1"],
        columns=["DEPOT", "A1-L1"],
    )
    distance_matrix.to_csv(tmp_path / "distance_matrix.csv")
    with pytest.raises(ValueError, match="demand quantities must be positive"):
        load_data(tmp_path)


def test_tc13_depot_to_nearest_location_uses_shortest_distance(data):
    segment = _shortest_network_path((0.0, 0.0), (2.0, 1.0), data)
    assert segment == [(0.0, 0.0), (2.0, 0.0), (2.0, 1.0)]
    assert _path_distance(segment) == pytest.approx(3.0)


def test_tc14_same_aisle_positions_use_vertical_distance(data):
    segment = _shortest_network_path((2.0, 1.0), (2.0, 10.0), data)
    assert segment[0] == (2.0, 1.0)
    assert segment[-1] == (2.0, 10.0)
    assert all(
        first[0] == second[0] or first[1] == second[1]
        for first, second in zip(segment, segment[1:])
    )
    assert _path_distance(segment) == pytest.approx(9.0)


def test_tc15_cross_aisle_picker_chooses_shorter_front_route(data):
    segment = _shortest_network_path((2.0, 3.0), (18.0, 3.0), data)
    assert _path_distance(segment) == pytest.approx(22.0)
