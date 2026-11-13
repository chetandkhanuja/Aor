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

overview_tab, route_tab, picks_tab = st.tabs(
    ["Strategy comparison", "Route visualization", "Pick list"]
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
                line={"color": "#e1e8ef", "width": 18},
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
                line={"color": "#7b8fa3", "width": 4},
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
                line={"color": "#168aad", "width": 5},
                name=f"{strategy} route",
                hoverinfo="skip",
            )
        )
    figure.add_trace(
        go.Scatter(
            x=data.warehouse["x"],
            y=data.warehouse["y"],
            mode="markers",
            marker={
                "color": "#aab7c4",
                "size": 8,
                "line": {"color": "white", "width": 1},
            },
            text=data.warehouse["location_id"],
            name="Storage location",
            hovertemplate="%{text}<extra></extra>",
        )
    )
    chosen = sorted(set(plan.selected_locations.values()))
    chosen_rows = data.warehouse[data.warehouse["location_id"].isin(chosen)]
    figure.add_trace(
        go.Scatter(
            x=chosen_rows["x"],
            y=chosen_rows["y"],
            mode="markers+text",
            marker={
                "color": "#f28c28",
                "size": 15,
                "symbol": "circle",
                "line": {"color": "white", "width": 2},
            },
            text=chosen_rows["location_id"],
            textposition="top center",
            textfont={"size": 10, "color": "#7c3f00"},
            name="Selected pick",
            hovertemplate="<b>Pick</b><br>%{text}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[0],
            y=[0],
            mode="markers+text",
            marker={
                "color": "#2a9d8f",
                "size": 18,
                "symbol": "diamond",
                "line": {"color": "white", "width": 2},
            },
            text=["DEPOT"],
            textposition="bottom right",
            name="Depot",
            hovertemplate="%{text}<extra></extra>",
        )
    )
    figure.update_layout(
        height=620,
        margin={"l": 10, "r": 10, "t": 15, "b": 10},
        xaxis_title="Warehouse width",
        yaxis_title="Aisle position",
        yaxis={"range": [-1, 12], "scaleanchor": "x", "scaleratio": 1},
        xaxis={"range": [-1, 20], "gridcolor": "#edf1f5"},
        plot_bgcolor="white",
        paper_bgcolor="white",
        font={"color": "#334e68"},
        legend={"orientation": "h", "y": -0.15},
        hovermode="closest",
    )
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
    st.markdown(
        "**Visit sequence:** DEPOT → "
        + " → ".join(plan.visit_order)
        + " → DEPOT"
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

st.info(
    "Prototype scope: one picker, one order at a time, complete demand from "
    "one stocked location per SKU, and synthetic data."
)
