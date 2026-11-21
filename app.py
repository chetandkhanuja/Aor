"""Streamlit decision-support prototype for warehouse order picking."""

from pathlib import Path
from dataclasses import replace

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from warehouse_optimizer import (
    POLICIES,
    RoutePlan,
    _path_distance,
    _shortest_network_path,
    compare_order,
    load_data,
    order_ids,
    solve_mip,
)


PROJECT_DIR = Path(__file__).resolve().parent


@st.cache_data(show_spinner=False)
def get_data():
    return load_data(PROJECT_DIR / "data")


@st.cache_data(show_spinner=False)
def get_comparison(order_id: str) -> list[RoutePlan]:
    return compare_order(order_id, get_data())


def _route_animation_frames(
    path: tuple[tuple[float, float], ...],
    progress_trace: int,
    picker_trace: int,
) -> list[go.Frame]:
    if len(path) < 2:
        return []

    segments = []
    total_distance = 0.0
    for first, second in zip(path, path[1:]):
        length = abs(second[0] - first[0]) + abs(second[1] - first[1])
        if length:
            segments.append((first, second, total_distance, length))
            total_distance += length
    if total_distance == 0:
        return []

    frame_distances = [index * 0.5 for index in range(int(total_distance * 2))]
    frame_distances.append(total_distance)
    frames = []
    for index, distance in enumerate(frame_distances):
        distance = min(distance, total_distance)
        position = path[0]
        traveled = [path[0]]
        for start, finish, start_distance, length in segments:
            end_distance = start_distance + length
            if distance >= end_distance:
                position = finish
                if traveled[-1] != finish:
                    traveled.append(finish)
                continue
            fraction = (distance - start_distance) / length
            position = (
                start[0] + (finish[0] - start[0]) * fraction,
                start[1] + (finish[1] - start[1]) * fraction,
            )
            if traveled[-1] != position:
                traveled.append(position)
            break
        frames.append(
            go.Frame(
                name=str(index),
                data=[
                    go.Scatter(
                        x=[point[0] for point in traveled],
                        y=[point[1] for point in traveled],
                    ),
                    go.Scatter(x=[position[0]], y=[position[1]]),
                ],
                traces=[progress_trace, picker_trace],
            )
        )
    return frames


st.set_page_config(
    page_title="Warehouse Picker Route Optimizer",
    page_icon="📦",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 3rem; max-width: 1440px;}
    [data-testid="stSidebar"] {background: #f5f7fb;}
    .hero {
        padding: 1.5rem 1.8rem; border-radius: 18px; margin-bottom: 1.2rem;
        background: linear-gradient(115deg, #102a43 0%, #145374 65%, #1c7890 100%);
        color: #fff;
    }
    .hero h1 {margin: 0 0 .4rem 0; color: #fff; font-size: 2rem;}
    .hero p {margin: 0; color: #d9eaf2; font-size: 1rem;}
    .eyebrow {
        color: #94d2df; font-size: .75rem; font-weight: 700;
        letter-spacing: .12em; text-transform: uppercase; margin-bottom: .4rem;
    }
    div[data-testid="stMetric"] {
        background: #fff; border: 1px solid #e6ebf2; border-radius: 14px;
        padding: 1rem 1.1rem; box-shadow: 0 3px 12px rgba(16, 42, 67, .04);
    }
    div[data-testid="stMetricLabel"] {color: #526579;}
    div[data-testid="stMetricValue"] {color: #102a43;}
    h2, h3 {color: #102a43;}
    </style>
    """,
    unsafe_allow_html=True,
)

data = get_data()
with st.sidebar:
    st.markdown("## Order setup")
    selected_order = st.selectbox("Customer order", order_ids(data))
    st.caption("Choose an order to compare feasible pick assignments and routes.")

with st.spinner("Solving the MIP benchmark and routing policies..."):
    plans = get_comparison(selected_order)

plan_by_strategy = {plan.strategy: plan for plan in plans}
mip_distance = plan_by_strategy["MIP benchmark"].distance
comparison = pd.DataFrame(
    [
        {
            "Strategy": plan.strategy,
            "Travel distance": plan.distance,
            "Gap vs. MIP": (
                0.0
                if plan.optimal
                else (plan.distance / mip_distance - 1) * 100
            ),
        }
        for plan in plans
    ]
)

st.markdown(
    f"""
    <section class="hero">
      <div class="eyebrow">Warehouse operations · Route planning</div>
      <h1>Picker Route Optimizer</h1>
      <p>Compare the optimal benchmark with aisle-routing strategies for {selected_order}.</p>
    </section>
    """,
    unsafe_allow_html=True,
)

order_lines = data.orders[data.orders["order_id"] == selected_order].copy()
order_lines = (
    order_lines.groupby("sku_id", as_index=False)["demand_qty"]
    .sum()
    .rename(columns={"sku_id": "SKU", "demand_qty": "Demand"})
)
metric_columns = st.columns(4)
metric_columns[0].metric("Order lines", f"{len(order_lines)} SKUs")
metric_columns[1].metric("Total units", f"{int(order_lines['Demand'].sum())}")
metric_columns[2].metric("Optimal distance", f"{mip_distance:.1f} units")
metric_columns[3].metric(
    "Best heuristic",
    min(
        (plan for plan in plans if not plan.optimal),
        key=lambda plan: plan.distance,
    ).strategy,
    delta=(
        f"{min(plan.distance for plan in plans if not plan.optimal) - mip_distance:.1f}"
        " units vs MIP"
    ),
    delta_color="off",
)

overview_tab, route_tab, picks_tab, test_tab = st.tabs(
    [
        "Strategy comparison",
        "Route visualization",
        "Pick list",
        "Test cases",
    ]
)
with overview_tab:
    comparison_column, note_column = st.columns([1.7, 1])
    with comparison_column:
        st.subheader("Distance by strategy")
        chart = go.Figure()
        colors = ["#168aad" if plan.optimal else "#86a8b8" for plan in plans]
        chart.add_trace(
            go.Bar(
                x=[plan.distance for plan in plans],
                y=[plan.strategy for plan in plans],
                orientation="h",
                marker={"color": colors, "line": {"color": "white", "width": 1}},
                text=[f"{plan.distance:.1f} units" for plan in plans],
                textposition="outside",
                customdata=[
                    0
                    if plan.optimal
                    else (plan.distance / mip_distance - 1) * 100
                    for plan in plans
                ],
                hovertemplate=(
                    "<b>%{y}</b><br>Distance: %{x:.1f} units"
                    "<br>Gap vs. MIP: %{customdata:.1f}%<extra></extra>"
                ),
            )
        )
        chart.update_layout(
            height=330,
            margin={"l": 10, "r": 90, "t": 10, "b": 35},
            xaxis_title="Travel distance (layout units)",
            yaxis={"autorange": "reversed"},
            plot_bgcolor="white",
            paper_bgcolor="white",
            font={"color": "#334e68"},
            showlegend=False,
        )
        chart.update_xaxes(showgrid=True, gridcolor="#edf1f5", zeroline=False)
        chart.update_yaxes(showgrid=False)
        st.plotly_chart(chart, width="stretch", config={"displayModeBar": False})
    with note_column:
        st.subheader("How to read this")
        st.markdown(
            f"""
            - **MIP benchmark** is the optimal result for the supplied distance-matrix model: **{mip_distance:.1f} units**.
            - **Return, Traversal, and Largest Gap** are aisle-routing heuristics.
            - The distance gap is measured against the MIP benchmark.
            """
        )
        st.info(
            "Distances use abstract layout units. The data is synthetic and "
            "the MIP is an adapted project benchmark, not a replication of "
            "the research paper's computational results."
        )
    st.subheader("Strategy results")
    results = comparison.copy()
    results["Status"] = ["Optimal" if plan.optimal else "Heuristic" for plan in plans]
    st.dataframe(
        results.style.format(
            {"Travel distance": "{:.1f}", "Gap vs. MIP": "{:.1f}%"}
        ),
        hide_index=True,
        width="stretch",
    )

with route_tab:
    strategy = st.radio(
        "Select a route",
        ["MIP benchmark", *POLICIES],
        horizontal=True,
        key="route_strategy",
    )
    plan = plan_by_strategy[strategy]
    st.caption(
        f"**{strategy}** · {plan.distance:.1f} layout units · "
        + (
            "Optimal benchmark"
            if plan.optimal
            else f"{(plan.distance / mip_distance - 1) * 100:.1f}% above MIP"
        )
    )
    st.caption(
        "Press ▶ Play picker to follow the route. Numbered bays are the pick "
        "stops; arrows show the travel direction."
    )

    demand_by_sku = dict(zip(order_lines["SKU"], order_lines["Demand"]))
    skus_by_location: dict[str, list[str]] = {}
    for sku, location in plan.selected_locations.items():
        skus_by_location.setdefault(location, []).append(
            f"{sku} × {demand_by_sku[sku]}"
        )
    location_order = {
        location: index for index, location in enumerate(plan.visit_order, start=1)
    }

    figure = go.Figure()
    aisle_lines = (
        data.warehouse[["aisle_number", "x"]]
        .drop_duplicates()
        .sort_values("aisle_number")
    )
    figure.add_shape(
        type="rect",
        x0=0,
        x1=20,
        y0=-0.38,
        y1=0.38,
        fillcolor="#d8eef0",
        line={"width": 0},
        layer="below",
    )
    figure.add_shape(
        type="rect",
        x0=0,
        x1=20,
        y0=10.62,
        y1=11.38,
        fillcolor="#d8eef0",
        line={"width": 0},
        layer="below",
    )
    for row in aisle_lines.itertuples(index=False):
        for side_offset in (-0.52, 0.52):
            figure.add_shape(
                type="rect",
                x0=row.x + side_offset - 0.22,
                x1=row.x + side_offset + 0.22,
                y0=0.5,
                y1=10.5,
                fillcolor="#e8edf2",
                line={"color": "#d2dbe4", "width": 1},
                layer="below",
            )
            for position in range(1, 11):
                figure.add_shape(
                    type="line",
                    x0=row.x + side_offset - 0.22,
                    x1=row.x + side_offset + 0.22,
                    y0=position + 0.5,
                    y1=position + 0.5,
                    line={"color": "#c7d2dc", "width": 1},
                    layer="below",
                )
        figure.add_shape(
            type="rect",
            x0=row.x - 0.2,
            x1=row.x + 0.2,
            y0=0,
            y1=11,
            fillcolor="#f9fbfc",
            line={"width": 0},
            layer="below",
        )
        figure.add_annotation(
            x=row.x,
            y=11.72,
            text=f"AISLE {int(row.aisle_number)}",
            showarrow=False,
            font={"size": 11, "color": "#526579"},
            bgcolor="white",
            bordercolor="#dce4eb",
            borderpad=3,
        )

    layout_by_location = data.warehouse.set_index("location_id")
    storage_x = [
        float(row.x) + (-0.52 if row.side == "L" else 0.52)
        for row in data.warehouse.itertuples(index=False)
    ]
    figure.add_trace(
        go.Scatter(
            x=storage_x,
            y=data.warehouse["y"],
            mode="markers",
            marker={
                "color": "#b7c3ce",
                "size": 7,
                "line": {"color": "white", "width": 1},
            },
            text=data.warehouse["location_id"],
            name="Storage bay",
            hovertemplate="Storage bay %{text}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[0, 20, None, 0, 20],
            y=[0, 0, None, 11, 11],
            mode="lines",
            line={"color": "#80aeb4", "width": 2},
            name="Cross aisle",
            hoverinfo="skip",
        )
    )
    if plan.path:
        figure.add_trace(
            go.Scatter(
                x=[point[0] for point in plan.path],
                y=[point[1] for point in plan.path],
                mode="lines",
                line={"color": "#168aad", "width": 4},
                name="Planned route",
                hoverinfo="skip",
            )
        )

    corners = [plan.path[0]]
    previous_direction = None
    for first, second in zip(plan.path, plan.path[1:]):
        direction = (
            0 if second[0] == first[0] else (1 if second[0] > first[0] else -1),
            0 if second[1] == first[1] else (1 if second[1] > first[1] else -1),
        )
        if previous_direction is not None and direction != previous_direction:
            corners.append(first)
        previous_direction = direction
    if plan.path:
        corners.append(plan.path[-1])
    arrow_x = []
    arrow_y = []
    arrow_symbols = []
    for first, second in zip(corners, corners[1:]):
        dx, dy = second[0] - first[0], second[1] - first[1]
        arrow_x.append((first[0] + second[0]) / 2)
        arrow_y.append((first[1] + second[1]) / 2)
        arrow_symbols.append(
            "triangle-right"
            if dx > 0
            else "triangle-left"
            if dx < 0
            else "triangle-up"
            if dy > 0
            else "triangle-down"
        )
    if arrow_x:
        figure.add_trace(
            go.Scatter(
                x=arrow_x,
                y=arrow_y,
                mode="markers",
                marker={
                    "symbol": arrow_symbols,
                    "size": 12,
                    "color": "#075985",
                    "line": {"color": "white", "width": 1},
                },
                name="Travel direction",
                hoverinfo="skip",
            )
        )

    chosen = list(plan.visit_order)
    chosen_rows = layout_by_location.loc[chosen].copy()
    chosen_rows["plot_x"] = [
        float(row.x) + (-0.52 if row.side == "L" else 0.52)
        for row in chosen_rows.itertuples()
    ]
    chosen_rows["step"] = [
        location_order[location] for location in chosen_rows.index
    ]
    chosen_rows["pick_description"] = [
        ", ".join(skus_by_location[location]) for location in chosen_rows.index
    ]
    figure.add_trace(
        go.Scatter(
            x=chosen_rows["plot_x"],
            y=chosen_rows["y"],
            mode="markers+text",
            marker={
                "color": "#f59e0b",
                "size": 25,
                "symbol": "circle",
                "line": {"color": "white", "width": 3},
            },
            text=chosen_rows["step"].astype(str),
            textposition="middle center",
            textfont={"size": 11, "color": "white", "family": "Arial Black"},
            customdata=[
                [location, description]
                for location, description in zip(
                    chosen_rows.index, chosen_rows["pick_description"]
                )
            ],
            name="Pick stop",
            hovertemplate=(
                "<b>Stop %{text}: %{customdata[0]}</b>"
                "<br>Pick %{customdata[1]}<extra></extra>"
            ),
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[0],
            y=[0],
            mode="markers+text",
            marker={
                "color": "#0f766e",
                "size": 20,
                "symbol": "diamond",
                "line": {"color": "white", "width": 2},
            },
            text=["DEPOT / START"],
            textposition="bottom left",
            name="Depot / start & finish",
            hovertemplate="%{text}<extra></extra>",
        )
    )
    progress_trace = len(figure.data)
    figure.add_trace(
        go.Scatter(
            x=[plan.path[0][0]],
            y=[plan.path[0][1]],
            mode="lines",
            line={"color": "#2a9d8f", "width": 7},
            name="Picker's completed path",
            hoverinfo="skip",
        )
    )
    picker_trace = len(figure.data)
    figure.add_trace(
        go.Scatter(
            x=[plan.path[0][0]],
            y=[plan.path[0][1]],
            mode="markers+text",
            marker={
                "color": "#102a43",
                "size": 25,
                "symbol": "circle",
                "line": {"color": "white", "width": 3},
            },
            text=["🧍"],
            textposition="top center",
            textfont={"size": 22},
            name="Picker",
            hovertemplate="<b>Picker</b><br>Moving along the route<extra></extra>",
        )
    )
    figure.frames = _route_animation_frames(
        plan.path, progress_trace, picker_trace
    )
    figure.update_layout(
        height=720,
        margin={"l": 25, "r": 25, "t": 80, "b": 70},
        title={
            "text": f"{selected_order} · {strategy} picker route",
            "x": 0.02,
            "y": 0.98,
            "xanchor": "left",
            "font": {"size": 20, "color": "#102a43"},
        },
        xaxis_title="Warehouse width",
        yaxis_title="Aisle position · picker travels vertically",
        yaxis={"range": [-0.9, 12.35], "scaleanchor": "x", "scaleratio": 1},
        xaxis={"range": [-1.4, 21], "dtick": 2, "showgrid": False, "zeroline": False},
        plot_bgcolor="#f8fafc",
        paper_bgcolor="white",
        font={"color": "#334e68"},
        legend={
            "orientation": "h",
            "y": -0.16,
            "x": 0.5,
            "xanchor": "center",
        },
        hovermode="closest",
        updatemenus=[
            {
                "type": "buttons",
                "direction": "left",
                "x": 0.02,
                "y": 1.13,
                "showactive": False,
                "buttons": [
                    {
                        "label": "▶ Play picker",
                        "method": "animate",
                        "args": [
                            None,
                            {
                                "frame": {"duration": 80, "redraw": True},
                                "fromcurrent": True,
                                "transition": {"duration": 0},
                            },
                        ],
                    },
                    {
                        "label": "Ⅱ Pause",
                        "method": "animate",
                        "args": [
                            [None],
                            {
                                "mode": "immediate",
                                "frame": {"duration": 0, "redraw": False},
                                "transition": {"duration": 0},
                            },
                        ],
                    },
                ],
            }
        ],
    )
    st.plotly_chart(
        figure,
        width="stretch",
        config={"displayModeBar": False},
        key=f"route_{selected_order}_{strategy}",
    )
    itinerary = []
    for location in plan.visit_order:
        row = layout_by_location.loc[location]
        itinerary.append(
            {
                "Stop": location_order[location],
                "Aisle": f"A{int(row['aisle_number'])}",
                "Bay": location,
                "Pick": ", ".join(skus_by_location[location]),
            }
        )
    st.subheader("Picker itinerary")
    st.dataframe(pd.DataFrame(itinerary), hide_index=True, width="stretch")
    st.caption(
        f"Start at depot → {len(itinerary)} pick stops → return to depot. "
        f"Route distance: {plan.distance:.1f} layout units."
    )

with picks_tab:
    plan = plan_by_strategy[
        st.selectbox(
            "Pick assignment strategy",
            ["MIP benchmark", *POLICIES],
            key="pick_strategy",
        )
    ]
    order_lines = data.orders[data.orders["order_id"] == selected_order].copy()
    order_lines = (
        order_lines.groupby("sku_id", as_index=False)["demand_qty"]
        .sum()
        .rename(columns={"sku_id": "SKU", "demand_qty": "Demand"})
    )
    order_lines["Selected location"] = order_lines["SKU"].map(
        plan.selected_locations
    )
    st.subheader(f"Pick list · {plan.strategy}")
    st.dataframe(order_lines, hide_index=True, width="stretch")
    st.caption(
        f"{len(order_lines)} SKUs · {int(order_lines['Demand'].sum())} total units · "
        f"{len(set(plan.selected_locations.values()))} pick locations"
    )

with test_tab:
    st.subheader("Model test cases")
    st.caption(
        "The first seven cases cover the supplied data and route feasibility. "
        "The final eight cases use new or modified input data."
    )

    test_definitions = [
        ("TC-01", "Load packaged inputs", "100 locations, 101x101 matrix"),
        ("TC-02", "Cover both supplied orders with every route policy", "Complete and orthogonal routes"),
        ("TC-03", "Solve both supplied MIP orders", "HiGHS returns optimal"),
        ("TC-04", "Compare MIP and policy distances", "MIP is no worse"),
        ("TC-05", "Demand exceeds all available stock", "Clear insufficient-stock error"),
        ("TC-06", "Largest Gap with no rear picks", "No unnecessary rear traversal"),
        ("TC-07", "Streamlit route rendering", "Dashboard renders without exceptions"),
        ("TC-08", "TEST-NEAREST: SKU01, quantity 1", "Select A1-L3; distance 10"),
        ("TC-09", "TEST-SUM: duplicate SKU01 demand 1 + 2", "Aggregate to 3; one unique visit"),
        ("TC-10", "TEST-STOCK: SKU01, quantity 4", "Insufficient-stock error"),
        ("TC-11", "TEST-UNKNOWN: unknown order", "Order-not-found error"),
        ("TC-12", "TEST-BAD: demand quantity 0", "Positive-demand error"),
        ("TC-13", "Shortest path: DEPOT to A1-L1", "Distance 3"),
        ("TC-14", "Shortest path: A1-L1 to A1-L10", "Distance 9"),
        ("TC-15", "Shortest path: A1-L3 to A5-L3", "Distance 22"),
    ]

    test_state = st.session_state.get("test_results", {})

    def run_new_data_tests() -> dict[str, dict[str, str]]:
        results: dict[str, dict[str, str]] = {}

        def add(test_id: str, passed: bool, evidence: str) -> None:
            results[test_id] = {
                "Status": "PASS" if passed else "FAIL",
                "Evidence": evidence,
            }

        nearest_orders = pd.DataFrame(
            [{"order_id": "TEST-NEAREST", "sku_id": "SKU01", "demand_qty": 1}]
        )
        nearest_plan = solve_mip(
            "TEST-NEAREST", replace(data, orders=nearest_orders)
        )
        add(
            "TC-08",
            nearest_plan.selected_locations["SKU01"] == "A1-L3"
            and abs(nearest_plan.distance - 10.0) < 1e-9,
            f"A1-L3; distance {nearest_plan.distance:.1f}",
        )

        sum_orders = pd.DataFrame(
            [
                {"order_id": "TEST-SUM", "sku_id": "SKU01", "demand_qty": 1},
                {"order_id": "TEST-SUM", "sku_id": "SKU01", "demand_qty": 2},
            ]
        )
        sum_plan = solve_mip("TEST-SUM", replace(data, orders=sum_orders))
        add(
            "TC-09",
            sum_plan.selected_locations["SKU01"] == "A1-L3"
            and len(set(sum_plan.visit_order)) == 1,
            f"A1-L3; {len(set(sum_plan.visit_order))} unique visit",
        )

        stock_orders = pd.DataFrame(
            [{"order_id": "TEST-STOCK", "sku_id": "SKU01", "demand_qty": 4}]
        )
        try:
            solve_mip("TEST-STOCK", replace(data, orders=stock_orders))
            add("TC-10", False, "Expected insufficient stock, but a route was returned")
        except ValueError as error:
            add("TC-10", "No single location" in str(error), str(error))

        try:
            solve_mip("TEST-UNKNOWN", data)
            add("TC-11", False, "Expected order-not-found, but a route was returned")
        except ValueError as error:
            add("TC-11", "TEST-UNKNOWN" in str(error), str(error))

        bad_orders = pd.DataFrame(
            [{"order_id": "TEST-BAD", "sku_id": "SKU01", "demand_qty": 0}]
        )
        bad_data = replace(data, orders=bad_orders)
        try:
            solve_mip("TEST-BAD", bad_data)
            add("TC-12", False, "Expected positive-demand rejection, but a route was returned")
        except ValueError as error:
            add(
                "TC-12",
                "demand quantities must be positive" in str(error),
                str(error),
            )

        depot_segment = _shortest_network_path((0.0, 0.0), (2.0, 1.0), data)
        add(
            "TC-13",
            abs(_path_distance(depot_segment) - 3.0) < 1e-9,
            f"DEPOT -> A1-L1 distance {_path_distance(depot_segment):.1f}",
        )

        vertical_segment = _shortest_network_path((2.0, 1.0), (2.0, 10.0), data)
        add(
            "TC-14",
            abs(_path_distance(vertical_segment) - 9.0) < 1e-9,
            f"A1-L1 -> A1-L10 distance {_path_distance(vertical_segment):.1f}",
        )

        cross_segment = _shortest_network_path((2.0, 3.0), (18.0, 3.0), data)
        add(
            "TC-15",
            abs(_path_distance(cross_segment) - 22.0) < 1e-9,
            f"A1-L3 -> A5-L3 distance {_path_distance(cross_segment):.1f}",
        )
        return results

    if st.button("Run TC-08 to TC-15", type="primary"):
        test_state = run_new_data_tests()
        st.session_state["test_results"] = test_state

    rows = []
    for test_id, name, expected in test_definitions:
        result = test_state.get(test_id)
        rows.append(
            {
                "Test": test_id,
                "Input / action": name,
                "Expected": expected,
                "Status": result["Status"] if result else "Not run",
                "Evidence": result["Evidence"] if result else "",
            }
        )
    test_table = pd.DataFrame(rows)
    styled = test_table.style.apply(
        lambda column: [
            "background-color: #dcfce7; color: #166534"
            if value == "PASS"
            else "background-color: #fee2e2; color: #991b1b"
            if value == "FAIL"
            else ""
            for value in column
        ],
        subset=["Status"],
    )
    st.dataframe(styled, hide_index=True, width="stretch")

st.info(
    "Prototype scope: one picker, one order at a time, complete demand from "
    "one stocked location per SKU, and synthetic data."
)
