"""Unified Race Feed -- Sprint 013: Feed UX Overhaul."""

from __future__ import annotations

import html

import streamlit as st

from raceanalyzer import queries
from raceanalyzer.ui.components import (
    render_empty_state,
    render_feed_card,
    render_feed_filters,
    render_global_category_filter,
    render_team_setting,
)
from raceanalyzer.ui.feed_card import (
    CHIP_TOOLTIPS,
    _card_has_chip,
    build_card_html,
    generate_ics,
    generate_share_text,
    inject_feed_styles,
)

FEED_PAGE_SIZE = 20


def render():
    session = st.session_state.db_session

    # Inject CSS once at top
    inject_feed_styles()

    # --- Deep-link isolation: ?series_id=N ---
    isolated_series_id = st.query_params.get("series_id")
    if isolated_series_id:
        try:
            isolated_series_id = int(isolated_series_id)
        except (ValueError, TypeError):
            isolated_series_id = None

    # --- Sidebar: global category, feed filters, team setting ---
    render_global_category_filter(session)
    category = st.session_state.get("global_category")

    filters = {}
    team_name = None
    if not isolated_series_id:
        filters = render_feed_filters(session)
        team_name = render_team_setting()

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

    # --- Filter chips (Sprint 013: FO-03, FO-04) ---
    chip_discipline = None
    can_finish_filter = False
    if not isolated_series_id:
        chip_discipline, can_finish_filter = _render_filter_chips()

    # --- Fetch feed items (batch) ---
    # Merge chip filters with sidebar filters
    discipline_filter = filters.get("discipline")
    if chip_discipline:
        discipline_filter = chip_discipline

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
            discipline_filter=discipline_filter,
            race_type_filter=filters.get("race_type"),
            state_filter=filters.get("states"),
            team_name=team_name,
        )

    # Apply "Can I finish?" filter
    if can_finish_filter:
        from raceanalyzer.ui.feed_card import is_beginner_friendly

        items = [i for i in items if is_beginner_friendly(i)[0]]

    if not items:
        if search_query:
            st.warning(f"No races matching '{search_query}'.")
            if st.button("Clear search"):
                if "q" in st.query_params:
                    del st.query_params["q"]
                st.rerun()
        elif can_finish_filter:
            st.info("No beginner-friendly races found with current filters.")
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

    # --- View toggle: List / Map (Sprint 013: FO-05) ---
    view_mode = "List"
    if not isolated_series_id:
        view_mode = _render_view_toggle()

    if view_mode == "Map":
        _render_map_view(items)
        return

    # --- Summary stats header (Sprint 013: FO-08) ---
    if not isolated_series_id:
        _render_summary_stats(items, team_name)

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

    # --- "Racing Soon" section (Sprint 013: FO-01) ---
    racing_soon = [
        i for i in items
        if i["is_upcoming"]
        and i.get("days_until") is not None
        and i["days_until"] <= 7
    ]
    remaining_items = [i for i in items if i not in racing_soon]

    if racing_soon:
        st.markdown(
            '<div class="feed-racing-soon-header" style="'
            'background:linear-gradient(90deg, #FFF3E0, transparent);'
            'padding:8px 12px;border-radius:8px;margin-bottom:8px;'
            'border-left:4px solid #FF6F00;">'
            '<span style="font-weight:600;font-size:1.05em;color:#BF360C;">Racing Soon</span>'
            f' <span style="font-size:0.85em;color:#E65100;">'
            f'{len(racing_soon)} race{"s" if len(racing_soon) != 1 else ""} this week</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        for item in racing_soon:
            expanded = isolated_series_id is not None
            _render_container_card(
                item, session, category, key_prefix="soon", expanded=expanded
            )

    # --- Month-grouped agenda view ---
    month_groups = queries.group_by_month(remaining_items)

    # Pagination state
    if "feed_page_size" not in st.session_state:
        st.session_state.feed_page_size = FEED_PAGE_SIZE
    visible_count = st.session_state.feed_page_size

    rendered = len(racing_soon)
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
            # Sticky month header (Sprint 013: FO-02)
            st.markdown(
                f'<div class="feed-month-header" style="position:sticky;top:0;z-index:10;'
                f'background:var(--background-color,#fff);padding:8px 12px;'
                f'border-bottom:1px solid var(--secondary-background-color,#e0e0e0);">'
                f'<span style="font-size:1.1em;font-weight:600;'
                f'color:var(--text-color,#333);">'
                f'{html.escape(header)}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            for item in group_items:
                if rendered >= visible_count:
                    break
                expanded = isolated_series_id is not None
                _render_container_card(
                    item, session, category, key_prefix="feed", expanded=expanded
                )
                rendered += 1

    # Show more button
    total_items = len(racing_soon) + sum(len(g[1]) for g in month_groups)
    if visible_count < total_items:
        remaining = total_items - visible_count
        if st.button(f"Show more ({remaining} remaining)"):
            st.session_state.feed_page_size = visible_count + FEED_PAGE_SIZE
            st.rerun()

    # --- Compare mode floating button (Sprint 013: AP-04) ---
    compare_ids = st.session_state.get("compare_ids", set())
    if len(compare_ids) >= 2:
        if st.button(f"Compare {len(compare_ids)} races", type="primary"):
            _show_comparison(compare_ids, items, session, category)


def _render_filter_chips():
    """Render filter chips above feed using st.pills (Sprint 013: FO-03, FO-04)."""
    col1, col2 = st.columns([3, 1])
    with col1:
        # Read current from query params
        current_disc = st.query_params.get("chip_discipline", "").split(",")
        current_disc = [d for d in current_disc if d]

        disc_options = ["Criterium", "Road Race", "Gravel", "TT", "Hill Climb"]
        selected = st.pills(
            "Filter by type",
            disc_options,
            selection_mode="multi",
            default=(
                current_disc
                if current_disc and all(d in disc_options for d in current_disc)
                else None
            ),
            key="filter_chips_discipline",
        )

        # Map display names to query values
        chip_to_value = {
            "Criterium": "criterium",
            "Road Race": "road_race",
            "Gravel": "gravel",
            "TT": "time_trial",
            "Hill Climb": "hill_climb",
        }
        discipline_filter = None
        if selected:
            discipline_filter = [chip_to_value[s] for s in selected if s in chip_to_value]

    with col2:
        sub1, sub2 = st.columns([3, 1])
        with sub1:
            can_finish = st.pills(
                "Approachability",
                ["Can I finish?"],
                selection_mode="single",
                key="filter_can_finish",
            )
            can_finish_active = can_finish == "Can I finish?"
        with sub2:
            with st.popover("\u2139\ufe0f"):
                st.markdown(
                    "**Can I finish?** filters to races where:\n"
                    "- Drop rate \u2264 25%\n"
                    "- Non-selective finish type\n"
                    "- Distance \u2264 100 km"
                )

    return discipline_filter, can_finish_active


def _render_view_toggle():
    """Render List/Map toggle (Sprint 013: FO-05)."""
    current = st.query_params.get("view", "list").title()
    if current not in ("List", "Map"):
        current = "List"
    view = st.segmented_control(
        "View",
        ["List", "Map"],
        default=current,
        key="feed_view_toggle",
    )
    if view and view.lower() != st.query_params.get("view", "list"):
        st.query_params["view"] = view.lower()
    return view or "List"


def _render_summary_stats(items, team_name):
    """Render feed summary stats header (Sprint 013: FO-08)."""
    from raceanalyzer.ui.feed_card import is_beginner_friendly

    upcoming_count = sum(1 for i in items if i["is_upcoming"])
    friendly_count = sum(
        1 for i in items if i["is_upcoming"] and is_beginner_friendly(i)[0]
    )
    teammate_count = sum(1 for i in items if i.get("teammate_names"))

    parts = []
    if upcoming_count:
        parts.append(f"{upcoming_count} upcoming")
    else:
        parts.append(f"{len(items)} races")
    if friendly_count:
        parts.append(f"{friendly_count} beginner-friendly")
    if teammate_count and team_name:
        parts.append(f"{teammate_count} with teammates")

    joined = " \u00b7 ".join(parts)
    st.markdown(
        f'<div style="font-size:0.9em;color:var(--text-color,#666);'
        f'padding:4px 0;margin-bottom:8px;">{joined}</div>',
        unsafe_allow_html=True,
    )


def _render_map_view(items):
    """Render feed map view with Folium (Sprint 013: FO-05)."""
    try:
        from raceanalyzer.ui.maps import render_feed_map

        render_feed_map(items)
    except Exception as e:
        st.warning(f"Map view unavailable: {e}")
        st.info("Showing list view instead.")


def _render_container_card(
    item: dict,
    session,
    category,
    key_prefix: str = "feed",
    expanded: bool = False,
):
    """Render a single feed card with HTML content + action buttons."""
    with st.container(border=True):
        # Single HTML block for all card content (Sprint 013 architecture)
        card_html = build_card_html(item)
        st.markdown(card_html, unsafe_allow_html=True)

        # Card info popover (Sprint 014: TT-01)
        with st.popover(
            "\u2139\ufe0f Card info",
            use_container_width=False,
        ):
            for chip_key, explanation in CHIP_TOOLTIPS.items():
                if _card_has_chip(item, chip_key):
                    st.markdown(
                        f"**{chip_key.replace('_', ' ').title()}**: "
                        f"{explanation}"
                    )

        # --- Action row ---
        _render_action_row(item, session, category, key_prefix, expanded)


def _render_action_row(item, session, category, key_prefix, expanded):
    """Render action buttons below the card HTML (Sprint 014: overflow menu)."""
    series_id = item["series_id"]

    # Initialize expanded state
    if "expanded_ids" not in st.session_state:
        st.session_state.expanded_ids = set()
    if "compare_ids" not in st.session_state:
        st.session_state.compare_ids = set()

    is_expanded = series_id in st.session_state.expanded_ids or expanded

    cols = st.columns([2, 1, 1])

    # Preview — primary CTA
    with cols[0]:
        if st.button(
            "Preview",
            key=f"{key_prefix}_preview_{series_id}",
            use_container_width=True,
            type="primary",
        ):
            _show_race_detail(series_id, session, category)

    # Register — secondary (hidden when not applicable)
    with cols[1]:
        reg_url = item.get("registration_url")
        if item.get("is_upcoming") and reg_url and reg_url.strip():
            st.link_button(
                "Register", reg_url, use_container_width=True
            )

    # Overflow menu — "⋯" popover
    with cols[2]:
        with st.popover("⋯", use_container_width=True):
            # Calendar export
            if item.get("is_upcoming") and item.get("upcoming_date"):
                loc = item.get("location", "")
                state = item.get("state_province", "")
                full_loc = f"{loc}, {state}" if state else loc
                duration = int(
                    item.get("typical_field_duration_min") or 120
                )
                ics = generate_ics(
                    item["display_name"],
                    item["upcoming_date"],
                    location=full_loc,
                    duration_minutes=duration,
                )
                safe_name = item["display_name"].replace(" ", "_")[:30]
                try:
                    date_str = item["upcoming_date"].strftime("%Y-%m-%d")
                except Exception:
                    date_str = "race"
                st.download_button(
                    "\U0001f4c5 Add to calendar",
                    data=ics,
                    file_name=f"{safe_name}-{date_str}.ics",
                    mime="text/calendar",
                    key=f"{key_prefix}_cal_{series_id}",
                    use_container_width=True,
                )

            # Share
            if st.button(
                "\U0001f517 Share",
                key=f"{key_prefix}_share_{series_id}",
                use_container_width=True,
            ):
                _show_share_dialog(item, category)

            # Compare
            is_compared = series_id in st.session_state.compare_ids
            cmp_label = (
                "\u2696\ufe0f Compare \u2713"
                if is_compared
                else "\u2696\ufe0f Compare"
            )
            if st.button(
                cmp_label,
                key=f"{key_prefix}_compare_{series_id}",
                use_container_width=True,
            ):
                if is_compared:
                    st.session_state.compare_ids.discard(series_id)
                elif len(st.session_state.compare_ids) < 3:
                    st.session_state.compare_ids.add(series_id)
                else:
                    st.toast("Compare limit: 3 races maximum")
                st.rerun()

            # More/Less details
            detail_label = (
                "\U0001f4c4 Less details"
                if is_expanded
                else "\U0001f4c4 More details"
            )
            if st.button(
                detail_label,
                key=f"{key_prefix}_detail_{series_id}",
                use_container_width=True,
            ):
                if is_expanded:
                    st.session_state.expanded_ids.discard(series_id)
                else:
                    st.session_state.expanded_ids.add(series_id)
                st.rerun()

    # Tier 2 content (on demand)
    if is_expanded:
        detail = queries.get_feed_item_detail(
            session, series_id, category=category
        )
        if detail:
            render_feed_card(detail)


# --- Dialogs (Sprint 013: AP-03, AP-04, AP-06) ---


@st.dialog("Race Details", width="large")
def _show_race_detail(series_id, session, category):
    """Bottom sheet / dialog with full Tier 2 content (Sprint 013: AP-03)."""
    detail = queries.get_feed_item_detail(session, series_id, category=category)
    if not detail:
        st.warning("Race details not available.")
        return

    render_feed_card(detail)

    # Previous editions timeline (Sprint 013: AP-05)
    editions = detail.get("editions_summary", [])
    if editions and len(editions) > 1:
        st.markdown("**Previous editions**")
        from raceanalyzer.ui.components import render_finish_pattern

        render_finish_pattern(editions)

    # Course map (if available)
    if detail.get("elevation_sparkline_points"):
        from raceanalyzer.ui.components import render_elevation_sparkline

        st.markdown("**Elevation profile**")
        render_elevation_sparkline(detail["elevation_sparkline_points"])


@st.dialog("Compare Races", width="large")
def _show_comparison(compare_ids, all_items, session, category):
    """Side-by-side race comparison (Sprint 013: AP-04)."""
    selected = [i for i in all_items if i["series_id"] in compare_ids]
    if not selected:
        st.warning("No races selected for comparison.")
        return

    cols = st.columns(len(selected))
    for col, item in zip(cols, selected):
        with col:
            _render_compare_column(item)

    if st.button("Clear comparison"):
        st.session_state.compare_ids = set()
        st.rerun()


def _render_compare_column(item):
    """Render a single column in comparison view."""
    from raceanalyzer.ui.feed_card import (
        format_duration,
        is_beginner_friendly,
        pack_survival_text,
        what_to_expect_text,
    )

    st.markdown(f"**{html.escape(item['display_name'])}**")
    if item.get("location"):
        st.caption(html.escape(item["location"]))

    # Key stats
    if item.get("distance_m"):
        st.write(f"Distance: {item['distance_m'] / 1000:.0f} km")
    if item.get("total_gain_m"):
        st.write(f"Elevation: {item['total_gain_m']:.0f}m")
    if item.get("drop_rate_pct") is not None:
        st.write(f"Drop rate: {item['drop_rate_pct']}%")
    if item.get("field_size_median"):
        st.write(f"Field size: {item['field_size_median']} riders")

    dur = format_duration(item.get("typical_field_duration_min"))
    if dur:
        st.write(f"Duration: {dur}")

    ft = item.get("predicted_finish_type")
    if ft:
        wte = what_to_expect_text(ft)
        if wte:
            st.write(wte)

    survival = pack_survival_text(item.get("drop_rate_pct"), ft)
    if survival:
        st.caption(survival)

    friendly, reasons = is_beginner_friendly(item)
    if friendly:
        st.success("Beginner-friendly")


@st.dialog("Share Race")
def _show_share_dialog(item, category):
    """Share deep link dialog (Sprint 014: SH-01, SH-02)."""
    import json as _json

    share_text = generate_share_text(item, category)
    st.write("Share this race with a friend:")
    st.code(share_text, language=None)

    # Clipboard copy via JS with toast feedback
    safe_text = _json.dumps(share_text)
    copy_js = (
        f"<script>navigator.clipboard.writeText({safe_text})"
        ".then(()=>{{}})"
        ".catch(()=>{{}});</script>"
    )
    if st.button(
        "\U0001f4cb Copy to clipboard",
        key="share_copy_btn",
        use_container_width=True,
    ):
        import streamlit.components.v1 as components

        components.html(copy_js, height=0)
        st.toast("Link copied!")


render()
