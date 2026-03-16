"""Unified Race Feed -- Sprint 013: Feed UX Overhaul."""

from __future__ import annotations

import html

import streamlit as st

from raceanalyzer import queries
from raceanalyzer.ui.components import (
    _init_filters_from_params,
    render_empty_state,
    render_racer_profile_filters,
)
from raceanalyzer.ui.feed_card import (
    build_row_html,
    generate_ics,
    generate_share_text,
    inject_feed_styles,
)


def feed_item_key(item: dict) -> str:
    """Unique widget key for a feed item (supports expanded stage/edition items)."""
    return item.get("occurrence_key") or f"{item['series_id']}:series"

FEED_PAGE_SIZE = 20


def render():
    from raceanalyzer.ui.app import ensure_db_session
    ensure_db_session()
    session = st.session_state.db_session

    # Sprint 018: Initialize filters from URL params
    _init_filters_from_params()

    # Inject CSS once at top
    inject_feed_styles()

    st.markdown(
        '<h1 style="font-size:2.4rem;font-weight:800;margin:0 0 0.3rem 0;">'
        "🚴 PNW Bike Races</h1>",
        unsafe_allow_html=True,
    )

    # --- Deep-link isolation: ?series_id=N ---
    isolated_series_id = st.query_params.get("series_id")
    if isolated_series_id:
        try:
            isolated_series_id = int(isolated_series_id)
        except (ValueError, TypeError):
            isolated_series_id = None

    # --- Sidebar: racer profile filters (includes team) ---
    racer_profile = {}
    if not isolated_series_id:
        racer_profile = render_racer_profile_filters(session)

    # Resolve category from global filter or legacy query param
    category = st.session_state.get("global_category")
    if not category:
        legacy_cat = st.query_params.get("category")
        if legacy_cat:
            category = legacy_cat

    matched_categories = []
    racer_profile_label = ""

    # Team name from profile dict
    team_name = racer_profile.get("team_name") if racer_profile else None

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

    # --- Filter chips (Sprint 018: type + state pills) ---
    chip_discipline = None
    state_filter = None
    if not isolated_series_id:
        chip_discipline, state_filter = _render_filter_chips(session)

    # --- Fetch feed items (batch) ---
    if isolated_series_id:
        all_items = queries.get_feed_items_batch(
            session, category=category,
            matched_categories=matched_categories or None,
            racer_profile_label=racer_profile_label,
            team_name=team_name,
        )
        items = [i for i in all_items if i["series_id"] == isolated_series_id]
        if not items:
            render_empty_state(f"Series {isolated_series_id} not found.")
            return
    else:
        items = queries.get_feed_items_batch(
            session,
            category=category,
            matched_categories=matched_categories or None,
            racer_profile_label=racer_profile_label,
            search_query=search_query or None,
            discipline_filter=chip_discipline,
            state_filter=state_filter,
            team_name=team_name,
        )

    if not items:
        if search_query:
            st.warning(f"No races matching '{search_query}'.")
            if st.button("Clear search"):
                if "q" in st.query_params:
                    del st.query_params["q"]
                st.rerun()
        elif chip_discipline or state_filter:
            st.warning("No races match your filters.")
            if st.button("Clear filters"):
                for p in ("chip_discipline", "states"):
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
            _render_container_row(
                item, session, category, key_prefix="deeplink", expanded=True
            )
        return

    # --- Search returning only past series: show preview cards ---
    if search_query and all_past_only and items:
        st.caption(f"Showing past editions for '{search_query}'")
        preview_items = items[:3]
        for item in preview_items:
            _render_container_row(
                item, session, category, key_prefix="search_past", expanded=True
            )
        if len(items) > 3:
            with st.expander(f"{len(items) - 3} more results"):
                for item in items[3:]:
                    _render_container_row(
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
        _render_rows(
            racing_soon, session, category,
            key_prefix="soon",
            expanded=isolated_series_id is not None,
        )

    # --- Month-grouped agenda view ---
    month_groups = queries.group_by_month(remaining_items)

    # Separate upcoming month groups from past races
    upcoming_groups = [(h, g) for h, g in month_groups if h != "Past Races"]
    past_groups = [(h, g) for h, g in month_groups if h == "Past Races"]

    # Render ALL upcoming races (no pagination)
    for header, group_items in upcoming_groups:
        st.markdown(
            f'<div class="feed-month-header" style="position:sticky;top:0;z-index:10;'
            f'background:linear-gradient(90deg, #FFF3E0, transparent);'
            f'padding:8px 12px;border-radius:8px;'
            f'border-left:4px solid #FFB74D;">'
            f'<span style="font-size:1.1em;font-weight:600;'
            f'color:var(--text-color,#333);">'
            f'{html.escape(header)}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        _render_rows(
            group_items, session, category,
            key_prefix="feed",
            expanded=isolated_series_id is not None,
        )

    # Past races: paginated, loaded on demand
    if past_groups:
        past_items = past_groups[0][1]
        if "past_page_size" not in st.session_state:
            st.session_state.past_page_size = 0

        past_visible = st.session_state.past_page_size
        if past_visible > 0:
            with st.expander(f"Past Races ({len(past_items)})", expanded=True):
                show = past_items[:past_visible]
                for item in show:
                    _render_container_row(
                        item, session, category, key_prefix="past"
                    )

        past_remaining = len(past_items) - past_visible
        if past_remaining > 0:
            if st.button(f"Load past races ({past_remaining} remaining)"):
                st.session_state.past_page_size = past_visible + FEED_PAGE_SIZE
                st.rerun()



def _render_filter_chips(session):
    """Render type + state/province filter pills (Sprint 018: FS-02)."""
    col_type, col_state = st.columns([3, 2])

    # --- Left: Race type pills ---
    with col_type:
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

    # --- Right: State/province pills ---
    with col_state:
        from raceanalyzer.ui.components import _cached_states

        all_states = _cached_states(session)
        current_states = st.query_params.get("states", "").split(",")
        current_states = [s for s in current_states if s in all_states]

        selected_states = st.pills(
            "State/Province",
            all_states,
            selection_mode="multi",
            default=current_states if current_states else None,
            key="filter_chips_states",
        )

        state_filter = None
        if selected_states:
            state_filter = selected_states
            new_val = ",".join(selected_states)
            if st.query_params.get("states") != new_val:
                st.query_params["states"] = new_val
        elif "states" in st.query_params:
            del st.query_params["states"]

    return discipline_filter, state_filter


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
    upcoming_count = sum(1 for i in items if i["is_upcoming"])
    teammate_count = sum(1 for i in items if i.get("teammate_names"))

    parts = []
    if upcoming_count:
        parts.append(f"{upcoming_count} upcoming")
    else:
        parts.append(f"{len(items)} races")
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


def _render_rows(
    items: list,
    session,
    category,
    key_prefix: str = "feed",
    expanded: bool = False,
):
    """Render feed items as single-column agenda rows (Sprint 019)."""
    for item in items:
        occ_kind = item.get("occurrence_kind")

        # Sprint 021: Stage race group header
        if occ_kind == "stage_header":
            parent_name = item.get("display_name", "Stage Race")
            stage_count = item.get("stage_count", 0)
            st.markdown(
                f'<div style="padding:8px 12px;margin:12px 0 4px 0;'
                f'font-weight:700;font-size:1.05rem;'
                f'border-left:4px solid #ff6b35;'
                f'background:rgba(255,107,53,0.08);border-radius:4px;">'
                f'{parent_name} &mdash; {stage_count} stages</div>',
                unsafe_allow_html=True,
            )
            continue

        _render_container_row(
            item, session, category,
            key_prefix=key_prefix, expanded=expanded,
        )


def _render_container_row(
    item: dict,
    session,
    category,
    key_prefix: str = "feed",
    expanded: bool = False,
):
    """Render a single feed row with HTML content + action buttons."""
    with st.container(border=True):
        # Single HTML block for all row content (Sprint 019 architecture)
        row_html = build_row_html(item)
        st.markdown(row_html, unsafe_allow_html=True)

        # --- Action row ---
        _render_action_row(item, session, category, key_prefix, expanded)


def _render_action_row(item, session, category, key_prefix, expanded):
    """Render action buttons below the card HTML (Sprint 018: simplified)."""
    series_id = item["series_id"]
    item_key = feed_item_key(item)

    cols = st.columns([2, 1, 1])

    # Preview — primary CTA
    with cols[0]:
        if st.button(
            "Preview",
            key=f"{key_prefix}_preview_{item_key}",
            use_container_width=True,
            type="primary",
        ):
            st.session_state["preview_series_id"] = series_id
            st.query_params["series_id"] = str(series_id)
            st.session_state["feed_scroll_index"] = st.session_state.get(
                "feed_page_size", 20
            )
            st.switch_page("pages/race_preview.py")

    # Register — secondary (hidden when not applicable)
    with cols[1]:
        reg_url = item.get("registration_url")
        if item.get("is_upcoming") and reg_url and reg_url.strip():
            st.link_button(
                "Register", reg_url, use_container_width=True
            )

    # Overflow menu — caret trigger (Sprint 018: CS-04)
    with cols[2]:
        with st.popover("", use_container_width=True):
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
                    key=f"{key_prefix}_cal_{item_key}",
                    use_container_width=True,
                )

            # Share
            if st.button(
                "\U0001f517 Share",
                key=f"{key_prefix}_share_{item_key}",
                use_container_width=True,
            ):
                _show_share_dialog(item, category)


# --- Dialogs (Sprint 013: AP-03, AP-04, AP-06) ---


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
