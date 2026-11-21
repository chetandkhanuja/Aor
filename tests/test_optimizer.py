"""User-facing test cases using supplied and modified warehouse inputs."""

from dataclasses import replace

import pandas as pd
import pytest

from warehouse_optimizer import (
    _path_distance,
    _shortest_network_path,
    load_data,
    solve_mip,
)


@pytest.fixture(scope="module")
def data():
    return load_data()


def test_tc01_new_order_picks_nearest_stock_location(data):
    orders = pd.DataFrame(
        [{"order_id": "TEST-NEAREST", "sku_id": "SKU01", "demand_qty": 1}]
    )
    plan = solve_mip("TEST-NEAREST", replace(data, orders=orders))
    assert plan.selected_locations["SKU01"] == "A1-L3"
    assert plan.distance == pytest.approx(10.0)


def test_tc02_new_order_aggregates_duplicate_demand_lines(data):
    orders = pd.DataFrame(
        [
            {"order_id": "TEST-SUM", "sku_id": "SKU01", "demand_qty": 1},
            {"order_id": "TEST-SUM", "sku_id": "SKU01", "demand_qty": 2},
        ]
    )
    plan = solve_mip("TEST-SUM", replace(data, orders=orders))
    assert plan.selected_locations["SKU01"] == "A1-L3"
    assert set(plan.visit_order) == {"A1-L3"}


def test_tc03_insufficient_total_stock_is_rejected(data):
    orders = pd.DataFrame(
        [{"order_id": "TEST-STOCK", "sku_id": "SKU01", "demand_qty": 4}]
    )
    with pytest.raises(ValueError, match="No single location has enough stock"):
        solve_mip("TEST-STOCK", replace(data, orders=orders))


def test_tc04_unknown_order_is_rejected(data):
    with pytest.raises(ValueError, match="Order TEST-UNKNOWN was not found"):
        solve_mip("TEST-UNKNOWN", data)


def test_tc05_zero_demand_is_rejected(data):
    orders = pd.DataFrame(
        [{"order_id": "TEST-BAD", "sku_id": "SKU01", "demand_qty": 0}]
    )
    with pytest.raises(ValueError, match="demand quantities must be positive"):
        solve_mip("TEST-BAD", replace(data, orders=orders))


def test_tc06_depot_to_nearest_location_uses_shortest_distance(data):
    segment = _shortest_network_path((0.0, 0.0), (2.0, 1.0), data)
    assert segment == [(0.0, 0.0), (2.0, 0.0), (2.0, 1.0)]
    assert _path_distance(segment) == pytest.approx(3.0)


def test_tc07_same_aisle_positions_use_vertical_distance(data):
    segment = _shortest_network_path((2.0, 1.0), (2.0, 10.0), data)
    assert segment[0] == (2.0, 1.0)
    assert segment[-1] == (2.0, 10.0)
    assert _path_distance(segment) == pytest.approx(9.0)


def test_tc08_cross_aisle_picker_chooses_shorter_front_route(data):
    segment = _shortest_network_path((2.0, 3.0), (18.0, 3.0), data)
    assert _path_distance(segment) == pytest.approx(22.0)


def test_tc09_unknown_sku_is_rejected(data):
    orders = pd.DataFrame(
        [{"order_id": "TEST-UNKNOWN-SKU", "sku_id": "SKU999", "demand_qty": 1}]
    )
    with pytest.raises(ValueError, match="No single location has enough stock"):
        solve_mip("TEST-UNKNOWN-SKU", replace(data, orders=orders))


def test_tc10_negative_inventory_is_rejected(tmp_path, data):
    inventory = data.inventory.copy()
    inventory.loc[0, "available_qty"] = -1
    inventory.to_csv(tmp_path / "inventory.csv", index=False)
    data.orders.to_csv(tmp_path / "orders.csv", index=False)
    data.distances.to_csv(tmp_path / "distance_matrix.csv")

    with pytest.raises(ValueError, match="Inventory quantities cannot be negative"):
        load_data(tmp_path)


def test_tc11_missing_distance_location_is_rejected(tmp_path, data):
    data.inventory.to_csv(tmp_path / "inventory.csv", index=False)
    data.orders.to_csv(tmp_path / "orders.csv", index=False)
    incomplete_matrix = pd.DataFrame(
        [[0.0, 3.0], [3.0, 0.0]],
        index=["DEPOT", "A1-L1"],
        columns=["DEPOT", "A1-L1"],
    )
    incomplete_matrix.to_csv(tmp_path / "distance_matrix.csv")

    with pytest.raises(ValueError, match="missing warehouse locations"):
        load_data(tmp_path)
