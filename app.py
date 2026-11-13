"""Streamlit decision-support prototype for warehouse order picking."""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from warehouse_optimizer import (
    POLICIES,
    RoutePlan,
    compare_order,
    load_data,
    order_ids,
)


PROJECT_DIR = Path(__file__).resolve().parent


@st.cache_data(show_spinner=False)
def get_data():
    return load_data(PROJECT_DIR / "data")


@st.cache_data(show_spinner=False)
def get_comparison(order_id: str) -> list[RoutePlan]:
    return compare_order(order_id, get_data())


st.set_page_config(
    page_title="Warehouse Picker Route Optimizer",
    page_icon="📦",
    layout="wide",
)

st.title("Warehouse Picker Route Optimizer")
st.caption(
    "Compare storage-location assignments and picker routes for the supplied "
    "five-aisle warehouse."
)

data = get_data()
with st.sidebar:
    st.header("Order setup")
    selected_order = st.selectbox("Customer order", order_ids(data))

with st.spinner("Solving the MIP benchmark and routing policies..."):
    plans = get_comparison(selected_order)

plan_by_strategy = {plan.strategy: plan for plan in plans}
comparison = pd.DataFrame(
    [
        {
            "Strategy": plan.strategy,
            "Travel distance": plan.distance,
            "Gap vs. MIP": (
                0.0
                if plan.optimal
                else (plan.distance / plan_by_strategy["MIP benchmark"].distance - 1)
                * 100
            ),
            "Status": "Optimal" if plan.optimal else "Heuristic",
        }
        for plan in plans
    ]
)

left, right = st.columns([1, 2])
with left:
    st.subheader("Routing comparison")
    st.dataframe(
        comparison.style.format(
            {"Travel distance": "{:.1f}", "Gap vs. MIP": "{:.1f}%"}
        ),
        hide_index=True,
        width="stretch",
    )
    strategy = st.selectbox(
        "Route to visualize",
        ["MIP benchmark", *POLICIES],
    )
    plan = plan_by_strategy[strategy]
    st.metric("Selected route distance", f"{plan.distance:.1f} units")
    st.caption(
        "The MIP is optimal for the supplied distance-matrix model. "
        "Routing policies are constructive heuristics."
    )

    order_lines = data.orders[data.orders["order_id"] == selected_order].copy()
    order_lines = (
        order_lines.groupby("sku_id", as_index=False)["demand_qty"]
        .sum()
        .rename(columns={"sku_id": "SKU", "demand_qty": "Demand"})
    )
    order_lines["Selected location"] = order_lines["SKU"].map(
        plan.selected_locations
    )
    st.subheader("Pick list")
    st.dataframe(order_lines, hide_index=True, width="stretch")
    st.markdown("**Visit sequence**")
    st.write("DEPOT → " + " → ".join(plan.visit_order) + " → DEPOT")

with right:
    st.subheader("Warehouse layout and route")
    figure = go.Figure()
    aisle_lines = (
        data.warehouse[["aisle_number", "x"]]
        .drop_duplicates()
        .sort_values("aisle_number")
    )
    for row in aisle_lines.itertuples(index=False):
        figure.add_trace(
            go.Scatter(
                x=[row.x, row.x],
                y=[0, 11],
                mode="lines",
                line={"color": "#cbd5e1", "width": 9},
                hoverinfo="skip",
                showlegend=False,
            )
        )
    for y in (0, 11):
        figure.add_trace(
            go.Scatter(
                x=[0, 20],
                y=[y, y],
                mode="lines",
                line={"color": "#64748b", "width": 3},
                name="Cross aisle",
                legendgroup="cross-aisle",
                showlegend=y == 0,
                hoverinfo="skip",
            )
        )

    if plan.path:
        figure.add_trace(
            go.Scatter(
                x=[point[0] for point in plan.path],
                y=[point[1] for point in plan.path],
                mode="lines",
                line={"color": "#2563eb", "width": 4},
                name=f"{strategy} route",
                hoverinfo="skip",
            )
        )

    figure.add_trace(
        go.Scatter(
            x=data.warehouse["x"],
            y=data.warehouse["y"],
            mode="markers",
            marker={"color": "#94a3b8", "size": 7},
            text=data.warehouse["location_id"],
            name="Storage location",
            hovertemplate="%{text}<extra></extra>",
        )
    )
    chosen = sorted(set(plan.selected_locations.values()))
    chosen_rows = data.warehouse[
        data.warehouse["location_id"].isin(chosen)
    ]
    figure.add_trace(
        go.Scatter(
            x=chosen_rows["x"],
            y=chosen_rows["y"],
            mode="markers+text",
            marker={
                "color": "#dc2626",
                "size": 14,
                "symbol": "star",
                "line": {"color": "white", "width": 1},
            },
            text=chosen_rows["location_id"],
            textposition="top center",
            name="Selected pick",
            hovertemplate="%{text}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[0],
            y=[0],
            mode="markers+text",
            marker={"color": "#16a34a", "size": 15, "symbol": "diamond"},
            text=["DEPOT"],
            textposition="bottom right",
            name="Depot",
            hovertemplate="%{text}<extra></extra>",
        )
    )
    figure.update_layout(
        height=560,
        margin={"l": 10, "r": 10, "t": 15, "b": 10},
        xaxis_title="Aisle x-coordinate",
        yaxis_title="Position along aisle",
        yaxis={"range": [-1, 12], "scaleanchor": "x", "scaleratio": 1},
        xaxis={"range": [-1, 20]},
        legend={"orientation": "h", "y": -0.2},
    )
    st.plotly_chart(figure, width="stretch")

st.info(
    "Prototype scope: one picker, one order, complete demand from one stocked "
    "location per SKU, and a synthetic warehouse dataset. See the project "
    "documentation for model assumptions and policy definitions."
)
