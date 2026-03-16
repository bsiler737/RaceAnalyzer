"""Race Calendar page -- visual tile grid of classified PNW races grouped by series."""

from __future__ import annotations

import streamlit as st

from raceanalyzer import queries
from raceanalyzer.db.models import Race
from raceanalyzer.ui.components import (
    render_empty_state,
    render_prediction_badge,
    render_series_tile_grid,
    render_sidebar_filters,
    render_tile_grid,
)

TILES_PER_PAGE = 12


def render():
    from raceanalyzer.ui.app import ensure_db_session
    ensure_db_session()
    session = st.session_state.db_session
    filters = render_sidebar_filters(session)

    st.title("PNW Race Calendar")

    # Upcoming races section
    upcoming = (
        session.query(Race)
        .filter(Race.is_upcoming.is_(True))
        .order_by(Race.date)
        .all()
    )
    if upcoming:
        st.subheader("Upcoming Races")
        for race in upcoming:
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 1, 1])
                date_str = f"{race.date:%b %d, %Y}" if race.date else "TBD"
                col1.write(f"**{race.name}** -- {date_str}")
                if race.registration_url:
                    col2.markdown(f"[Register]({race.registration_url})")
                if race.series_id:
                    # Show prediction badge
                    from raceanalyzer.predictions import predict_series_finish_type
                    pred = predict_series_finish_type(session, race.series_id)
                    if pred["predicted_finish_type"] != "unknown":
                        with col3:
                            render_prediction_badge(
                                pred["predicted_finish_type"],
                                pred["confidence"],
                            )
        st.divider()

    # Try series tiles first; fall back to individual race tiles if no series exist
    df = queries.get_series_tiles(session, year=filters["year"], states=filters["states"])
    use_series = not df.empty

    if df.empty:
        # Fallback: no series built yet, show individual race tiles
        df = queries.get_race_tiles(session, year=filters["year"], states=filters["states"])

    if df.empty:
        render_empty_state(
            "No races found. Try adjusting your filters or run "
            "`raceanalyzer scrape` to import data."
        )
        return

    # Count unknown races before filtering
    unknown_count = len(df[df["overall_finish_type"] == "unknown"])
    total_count = len(df)

    # UNKNOWN toggle
    show_unknown = st.toggle(
        f"Show races without timing data ({unknown_count} of {total_count})",
        value=False,
    )
    if not show_unknown:
        df = df[df["overall_finish_type"] != "unknown"]

    if df.empty:
        render_empty_state(
            "No classified races found. Toggle 'Show races without timing data' to see all."
        )
        return

    # Metrics row
    col1, col2, col3 = st.columns(3)
    col1.metric("Showing", len(df))
    col2.metric("States/Provinces", df["state_province"].nunique())

    if use_series:
        dated = df[df["latest_date"].notna()]
        if not dated.empty:
            col3.metric(
                "Date Range",
                f"{dated['latest_date'].min():%b %Y} -- {dated['latest_date'].max():%b %Y}",
            )
    else:
        dated = df[df["date"].notna()]
        if not dated.empty:
            col3.metric(
                "Date Range",
                f"{dated['date'].min():%b %Y} -- {dated['date'].max():%b %Y}",
            )

    # Pagination state
    if "tile_page_size" not in st.session_state:
        st.session_state.tile_page_size = TILES_PER_PAGE
    visible_count = st.session_state.tile_page_size

    visible_df = df.head(visible_count)

    if use_series:
        render_series_tile_grid(visible_df, key_prefix="cal")
    else:
        render_tile_grid(visible_df, key_prefix="cal")

    # Show more button
    if visible_count < len(df):
        remaining = len(df) - visible_count
        if st.button(f"Show more ({remaining} remaining)"):
            st.session_state.tile_page_size = visible_count + TILES_PER_PAGE
            st.rerun()


render()
