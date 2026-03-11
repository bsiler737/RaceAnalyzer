"""Unified Race Feed -- the primary entry point for RaceAnalyzer (Sprint 010)."""

from __future__ import annotations

import streamlit as st

from raceanalyzer import queries
from raceanalyzer.ui.components import (
    render_empty_state,
    render_prediction_badge,
    render_terrain_badge,
)

FEED_PAGE_SIZE = 20


def render():
    session = st.session_state.db_session

    # --- Deep-link isolation: ?series_id=N ---
    isolated_series_id = st.query_params.get("series_id")
    if isolated_series_id:
        try:
            isolated_series_id = int(isolated_series_id)
        except (ValueError, TypeError):
            isolated_series_id = None

    # --- Search bar ---
    search_query = st.query_params.get("q", "")
    if not isolated_series_id:
        search_input = st.text_input(
            "Search races",
            value=search_query,
            placeholder="e.g. Banana Belt, Cherry Pie...",
            key="feed_search",
        )
        if search_input != search_query:
            search_query = search_input
            if search_query:
                st.query_params["q"] = search_query
            elif "q" in st.query_params:
                del st.query_params["q"]

    # --- Category filter (read global if set) ---
    category = st.session_state.get("global_category")

    # --- Fetch feed items ---
    if isolated_series_id:
        # Show only this series
        all_items = queries.get_feed_items(session, category=category)
        items = [i for i in all_items if i["series_id"] == isolated_series_id]
        if not items:
            render_empty_state(f"Series {isolated_series_id} not found.")
            return
    else:
        items = queries.get_feed_items(
            session, category=category, search_query=search_query or None,
        )

    if not items:
        if search_query:
            st.warning(f"No races matching '{search_query}'.")
            if st.button("Clear search"):
                if "q" in st.query_params:
                    del st.query_params["q"]
                st.rerun()
        else:
            render_empty_state(
                "No races found. Run `raceanalyzer scrape` to import data."
            )
        return

    # --- "Show all races" button for deep-link isolation ---
    if isolated_series_id:
        if st.button("Show all races"):
            if "series_id" in st.query_params:
                del st.query_params["series_id"]
            st.rerun()

    # --- Racing Soon section ---
    if not isolated_series_id and not search_query:
        racing_soon = [i for i in items if i["is_racing_soon"]]
        if racing_soon:
            st.subheader("Racing Soon")
            st.caption("Next 7 days")
            for item in racing_soon:
                _render_feed_expander(item, expanded=True, key_prefix="soon")
            st.divider()
        else:
            st.caption("No races in the next 7 days.")

    if search_query:
        st.caption(f"Showing all dates for '{search_query}'.")

    # --- Main feed ---
    st.subheader("All Races" if not isolated_series_id else "")

    # Pagination
    if "feed_page_size" not in st.session_state:
        st.session_state.feed_page_size = FEED_PAGE_SIZE
    visible_count = st.session_state.feed_page_size

    visible_items = items[:visible_count]
    for item in visible_items:
        expanded = isolated_series_id is not None
        _render_feed_expander(item, expanded=expanded, key_prefix="feed")

    # Show more button
    if visible_count < len(items):
        remaining = len(items) - visible_count
        if st.button(f"Show more ({remaining} remaining)"):
            st.session_state.feed_page_size = visible_count + FEED_PAGE_SIZE
            st.rerun()


def _render_feed_expander(item: dict, expanded: bool = False, key_prefix: str = "feed"):
    """Render a single feed card inside an st.expander."""
    # Build label
    date_str = ""
    if item["is_upcoming"] and item.get("upcoming_date"):
        date_str = f" \u2014 {item['upcoming_date']:%b %d, %Y}"
    elif item.get("most_recent_date"):
        date_str = f" \u2014 last raced {item['most_recent_date']:%b %Y}"

    upcoming_marker = ""
    if item["is_racing_soon"]:
        upcoming_marker = "SOON "
    elif item["is_upcoming"]:
        upcoming_marker = "UPCOMING "

    label = f"{upcoming_marker}{item['display_name']}{date_str}"

    # Dormant series: reduced opacity via container
    is_dormant = not item["is_upcoming"]

    with st.expander(label, expanded=expanded):
        if is_dormant:
            st.caption("No upcoming edition")

        # Row 1: Prediction + terrain + drop rate
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            if item.get("predicted_finish_type"):
                render_prediction_badge(
                    item["predicted_finish_type"], item["confidence"]
                )
        with col2:
            if item.get("course_type"):
                render_terrain_badge(item["course_type"])
        with col3:
            if item.get("drop_rate_pct") is not None:
                st.caption(f"{item['drop_rate_pct']}% drop rate")

        # Row 2: Narrative snippet
        if item.get("narrative_snippet"):
            st.write(item["narrative_snippet"])

        # Row 3: Location + editions
        loc_parts = []
        if item.get("location"):
            loc_parts.append(item["location"])
        if item.get("state_province"):
            loc_parts.append(item["state_province"])
        meta_parts = []
        if loc_parts:
            meta_parts.append(", ".join(loc_parts))
        if item.get("edition_count"):
            ed = item["edition_count"]
            meta_parts.append(f"{ed} edition{'s' if ed != 1 else ''}")
        if meta_parts:
            st.caption(" | ".join(meta_parts))

        # Row 4: Registration link
        if item.get("is_upcoming") and item.get("registration_url"):
            st.markdown(f"[Register]({item['registration_url']})")

        # Row 5: Historical editions popover
        editions = item.get("editions_summary", [])
        if editions and len(editions) > 1:
            with st.popover(f"{len(editions)} previous editions"):
                for ed in editions:
                    year_str = str(ed["year"]) if ed.get("year") else "?"
                    st.write(f"- {year_str}: {ed['finish_type_display']}")

        # Row 6: Navigation buttons
        btn_col, preview_col = st.columns(2)
        series_id = item["series_id"]
        with btn_col:
            if st.button(
                "View Series",
                key=f"{key_prefix}_series_{series_id}",
                use_container_width=True,
            ):
                st.session_state["selected_series_id"] = series_id
                st.query_params["series_id"] = str(series_id)
                st.switch_page("pages/series_detail.py")
        with preview_col:
            if st.button(
                "Race Preview",
                key=f"{key_prefix}_preview_{series_id}",
                use_container_width=True,
            ):
                st.session_state["preview_series_id"] = series_id
                st.query_params["series_id"] = str(series_id)
                st.switch_page("pages/race_preview.py")


render()
