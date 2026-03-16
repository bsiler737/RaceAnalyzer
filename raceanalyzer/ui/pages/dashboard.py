"""Finish Type Dashboard -- distribution charts and trend analysis."""

from __future__ import annotations

import streamlit as st

from raceanalyzer import queries
from raceanalyzer.ui.charts import (
    build_distribution_bar_chart,
    build_distribution_pie_chart,
    build_trend_stacked_area_chart,
)
from raceanalyzer.ui.components import render_empty_state, render_sidebar_filters


def render():
    from raceanalyzer.ui.app import ensure_db_session
    ensure_db_session()
    session = st.session_state.db_session
    filters = render_sidebar_filters(session)

    st.title("Finish Type Dashboard")

    # Distribution
    dist_df = queries.get_finish_type_distribution(
        session,
        category=filters["category"],
        year=filters["year"],
        states=filters["states"],
    )

    if dist_df.empty:
        render_empty_state(
            "No classification data available. "
            "Run `raceanalyzer scrape` then `raceanalyzer classify` first."
        )
        return

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Distribution (Proportions)")
        fig_pie = build_distribution_pie_chart(dist_df)
        st.plotly_chart(fig_pie, use_container_width=True)
    with col2:
        st.subheader("Distribution (Counts)")
        fig_bar = build_distribution_bar_chart(dist_df)
        st.plotly_chart(fig_bar, use_container_width=True)

    st.divider()

    # Trend
    st.subheader("Finish Type Trend Over Time")
    trend_df = queries.get_finish_type_trend(
        session,
        category=filters["category"],
        states=filters["states"],
    )

    if trend_df.empty or trend_df["year"].nunique() < 2:
        render_empty_state("Need at least 2 years of data to show trends.")
    else:
        fig_trend = build_trend_stacked_area_chart(trend_df)
        st.plotly_chart(fig_trend, use_container_width=True)

    # Summary
    st.divider()
    st.subheader("Summary")
    most_common = dist_df.loc[dist_df["count"].idxmax()]
    display = queries.finish_type_display_name(most_common["finish_type"])
    st.write(
        f"Most common finish type: **{display}** "
        f"({most_common['percentage']:.1f}% of classified races)"
    )


render()
