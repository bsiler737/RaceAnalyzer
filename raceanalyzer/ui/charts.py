"""Plotly chart builders for RaceAnalyzer UI."""

from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from raceanalyzer.queries import finish_type_display_name

FINISH_TYPE_COLORS = {
    "bunch_sprint": "#2196F3",
    "small_group_sprint": "#03A9F4",
    "breakaway": "#FF9800",
    "breakaway_selective": "#FF5722",
    "reduced_sprint": "#4CAF50",
    "gc_selective": "#9C27B0",
    "individual_tt": "#00ACC1",
    "mixed": "#607D8B",
    "unknown": "#9E9E9E",
}


def _display_color_map() -> dict:
    """Color map keyed by display names for Plotly."""
    return {finish_type_display_name(k): v for k, v in FINISH_TYPE_COLORS.items()}


def build_distribution_pie_chart(dist_df: pd.DataFrame) -> go.Figure:
    """Pie chart of finish type distribution."""
    df = dist_df.copy()
    df["display_name"] = df["finish_type"].apply(finish_type_display_name)
    fig = px.pie(
        df,
        values="count",
        names="display_name",
        color="display_name",
        color_discrete_map=_display_color_map(),
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(showlegend=False, margin=dict(t=20, b=20, l=20, r=20),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    return fig


def build_distribution_bar_chart(dist_df: pd.DataFrame) -> go.Figure:
    """Horizontal bar chart of finish type counts."""
    df = dist_df.copy().sort_values("count", ascending=True)
    df["display_name"] = df["finish_type"].apply(finish_type_display_name)
    fig = px.bar(
        df,
        x="count",
        y="display_name",
        orientation="h",
        color="display_name",
        color_discrete_map=_display_color_map(),
    )
    fig.update_layout(
        showlegend=False,
        yaxis_title="",
        xaxis_title="Count",
        margin=dict(t=20, b=40, l=20, r=20),
        yaxis=dict(categoryorder="total ascending"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def build_trend_stacked_area_chart(trend_df: pd.DataFrame) -> go.Figure:
    """Stacked area chart of finish types over years."""
    df = trend_df.copy()
    df["display_name"] = df["finish_type"].apply(finish_type_display_name)
    fig = px.area(
        df,
        x="year",
        y="count",
        color="display_name",
        color_discrete_map=_display_color_map(),
        groupnorm="percent",
    )
    fig.update_layout(
        yaxis_title="Percentage",
        xaxis_title="Year",
        legend_title="Finish Type",
        margin=dict(t=20, b=40, l=60, r=20),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(dtick=1)
    return fig


def build_group_structure_chart(results_df: pd.DataFrame) -> Optional[go.Figure]:
    """Bar chart showing group sizes for a single race category.

    Returns None if no group data available.
    """
    if "gap_group_id" not in results_df.columns or results_df["gap_group_id"].isna().all():
        return None

    group_counts = (
        results_df[results_df["gap_group_id"].notna()]
        .groupby("gap_group_id")
        .size()
        .reset_index(name="riders")
    )
    if group_counts.empty:
        return None

    group_counts["group_label"] = "Group " + group_counts["gap_group_id"].astype(int).astype(str)

    fig = px.bar(
        group_counts,
        x="group_label",
        y="riders",
        color="riders",
        color_continuous_scale="Blues",
    )
    fig.update_layout(
        xaxis_title="Gap Group",
        yaxis_title="Riders",
        showlegend=False,
        margin=dict(t=20, b=40, l=40, r=20),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def build_series_classification_chart(trend_df: pd.DataFrame) -> Optional[go.Figure]:
    """Stacked bar chart: year (x) x finish_type counts (y) for a series."""
    if trend_df.empty:
        return None

    counts = (
        trend_df.groupby(["year", "finish_type"])
        .size()
        .reset_index(name="count")
    )
    counts["display_name"] = counts["finish_type"].apply(finish_type_display_name)

    fig = px.bar(
        counts,
        x="year",
        y="count",
        color="display_name",
        color_discrete_map=_display_color_map(),
        labels={"count": "Categories", "year": "Year"},
        barmode="stack",
    )
    fig.update_layout(
        legend_title="Finish Type",
        xaxis=dict(dtick=1),
        margin=dict(t=20, b=40, l=40, r=20),
        height=300,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig
