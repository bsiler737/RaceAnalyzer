"""Unified Race Feed -- the primary entry point for RaceAnalyzer (Sprint 011)."""

from __future__ import annotations

import streamlit as st

from raceanalyzer import queries
from raceanalyzer.ui.components import (
    render_empty_state,
    render_feed_card,
    render_feed_filters,
    render_global_category_filter,
    render_team_setting,
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

    # --- Sidebar: global category, feed filters, team setting ---
    render_global_category_filter(session)
    category = st.session_state.get("global_category")

    filters = {}
    team_name = None
    if not isolated_series_id:
        filters = render_feed_filters(session)
        team_name = render_team_setting()

    # --- Fetch feed items (batch) ---
    if isolated_series_id:
        all_items = queries.get_feed_items_batch(
            session, category=category, team_name=team_name
        )
        items = [i for i in all_items if i["series_id"] == isolated_series_id]
        if not items:
            render_empty_state(f"Series {isolated_series_id} not found.")
            return
    else:
        items = queries.get_feed_items_batch(
            session,
            category=category,
            search_query=search_query or None,
            discipline_filter=filters.get("discipline"),
            race_type_filter=filters.get("race_type"),
            state_filter=filters.get("states"),
            team_name=team_name,
        )

    if not items:
        if search_query:
            st.warning(f"No races matching '{search_query}'.")
            if st.button("Clear search"):
                if "q" in st.query_params:
                    del st.query_params["q"]
                st.rerun()
        elif any(
            filters.get(k) is not None for k in ("discipline", "race_type", "states")
        ):
            st.warning("No races match your filters.")
            if st.button("Clear filters"):
                for p in ("discipline", "race_type", "states"):
                    if p in st.query_params:
                        del st.query_params[p]
                st.rerun()
        elif category:
            st.warning(f"No races found for '{category}'. Try 'All Categories'.")
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

    if search_query:
        st.caption(f"Showing all dates for '{search_query}'.")

    # --- Check if all results are past-only ---
    all_past_only = all(not item["is_upcoming"] for item in items)

    # --- Deep-link to past-only series: render expanded at top level ---
    if isolated_series_id and all_past_only:
        for item in items:
            _render_container_card(
                item, session, category, key_prefix="deeplink", expanded=True
            )
        return

    # --- Search returning only past series: show preview cards ---
    if search_query and all_past_only and items:
        st.caption(f"Showing past editions for '{search_query}'")
        preview_items = items[:3]
        for item in preview_items:
            _render_container_card(
                item, session, category, key_prefix="search_past", expanded=True
            )
        if len(items) > 3:
            with st.expander(f"{len(items) - 3} more results"):
                for item in items[3:]:
                    _render_container_card(
                        item, session, category, key_prefix="search_past_more"
                    )
        return

    # --- Month-grouped agenda view ---
    month_groups = queries.group_by_month(items)

    # Pagination state
    if "feed_page_size" not in st.session_state:
        st.session_state.feed_page_size = FEED_PAGE_SIZE
    visible_count = st.session_state.feed_page_size

    rendered = 0
    for header, group_items in month_groups:
        if rendered >= visible_count:
            break

        # Past Races section is collapsed
        if header == "Past Races":
            with st.expander(f"Past Races ({len(group_items)})", expanded=False):
                for item in group_items:
                    if rendered >= visible_count:
                        break
                    _render_container_card(
                        item, session, category, key_prefix="past"
                    )
                    rendered += 1
        else:
            st.subheader(header)
            for item in group_items:
                if rendered >= visible_count:
                    break
                expanded = isolated_series_id is not None
                _render_container_card(
                    item, session, category, key_prefix="feed", expanded=expanded
                )
                rendered += 1

    # Show more button
    total_items = sum(len(g[1]) for g in month_groups)
    if visible_count < total_items:
        remaining = total_items - visible_count
        if st.button(f"Show more ({remaining} remaining)"):
            st.session_state.feed_page_size = visible_count + FEED_PAGE_SIZE
            st.rerun()


def _render_container_card(
    item: dict,
    session,
    category,
    key_prefix: str = "feed",
    expanded: bool = False,
):
    """Render a single feed card as st.container(border=True)."""
    series_id = item["series_id"]

    with st.container(border=True):
        # Header: name + date + location + countdown
        header_parts = [f"**{item['display_name']}**"]

        if item["is_upcoming"] and item.get("upcoming_date"):
            date_str = f"{item['upcoming_date']:%b %d, %Y}"
            countdown = item.get("countdown_label", "")
            if countdown:
                header_parts.append(f"{date_str} ({countdown})")
            else:
                header_parts.append(date_str)
        elif item.get("most_recent_date"):
            header_parts.append(f"last raced {item['most_recent_date']:%b %Y}")

        loc_parts = []
        if item.get("location"):
            loc_parts.append(item["location"])
        if item.get("state_province") and item["state_province"] not in item.get("location", ""):
            loc_parts.append(item["state_province"])
        if loc_parts:
            header_parts.append(", ".join(loc_parts))

        st.markdown(" \u2014 ".join(header_parts))

        # Quick-scan badges row
        badge_parts = []

        # Teammate badge
        teammates = item.get("teammate_names", [])
        if teammates:
            if len(teammates) <= 2:
                badge_parts.append(f"Teammates: {', '.join(teammates)}")
            else:
                badge_parts.append(f"{len(teammates)} teammates")

        # Terrain + distance + gain
        if item.get("course_type"):
            from raceanalyzer.elevation import course_type_display

            terrain = course_type_display(item["course_type"])
            badge_parts.append(terrain)

        if item.get("distance_m"):
            badge_parts.append(f"{item['distance_m'] / 1000:.0f} km")

        if item.get("total_gain_m"):
            badge_parts.append(f"{item['total_gain_m']:.0f}m gain")

        # Field size
        if item.get("field_size_display"):
            badge_parts.append(item["field_size_display"])

        # Drop rate
        if item.get("drop_rate_pct") is not None and item.get("drop_rate_label"):
            badge_parts.append(
                f"{item['drop_rate_pct']}% drop rate ({item['drop_rate_label']})"
            )

        if badge_parts:
            st.caption(" \u00b7 ".join(badge_parts))

        # Finish type prediction + race type (source-aware language, Sprint 012)
        pred_parts = []
        if item.get("predicted_finish_type"):
            from raceanalyzer.queries import (
                finish_type_plain_english_with_source,
            )

            plain = finish_type_plain_english_with_source(
                item["predicted_finish_type"],
                prediction_source=item.get("prediction_source"),
                race_type=item.get("race_type"),
            )
            if plain:
                pred_parts.append(plain)

        if item.get("race_type"):
            from raceanalyzer.queries import race_type_display_name

            pred_parts.append(race_type_display_name(item["race_type"]))

        if pred_parts:
            st.write(" \u00b7 ".join(pred_parts))

        # Action row: Details toggle + Register + Preview
        detail_key = f"{key_prefix}_detail_{series_id}"

        # Initialize expanded state
        if "expanded_ids" not in st.session_state:
            st.session_state.expanded_ids = set()

        is_expanded = series_id in st.session_state.expanded_ids or expanded

        cols = st.columns([1, 1, 1, 3])
        with cols[0]:
            btn_label = "Less" if is_expanded else "Details"
            if st.button(btn_label, key=detail_key, use_container_width=True):
                if is_expanded:
                    st.session_state.expanded_ids.discard(series_id)
                else:
                    st.session_state.expanded_ids.add(series_id)
                st.rerun()
        with cols[1]:
            reg_url = item.get("registration_url")
            if item.get("is_upcoming") and reg_url and reg_url.strip():
                st.link_button(
                    "Register", reg_url, use_container_width=True
                )
        with cols[2]:
            if st.button(
                "Preview",
                key=f"{key_prefix}_preview_{series_id}",
                use_container_width=True,
            ):
                st.session_state["preview_series_id"] = series_id
                st.query_params["series_id"] = str(series_id)
                st.switch_page("pages/race_preview.py")

        # Tier 2 content (on demand)
        if is_expanded:
            detail = queries.get_feed_item_detail(
                session, series_id, category=category
            )
            if detail:
                render_feed_card(detail)


render()
