"""Shared Streamlit UI components: sidebar filters, finish-type tiles, scary racers."""

from __future__ import annotations

import html

import streamlit as st

from raceanalyzer import queries
from raceanalyzer.queries import (
    FINISH_TYPE_DISPLAY_NAMES,
    FINISH_TYPE_TOOLTIPS,
)

# --- Finish type SVG icons (24x24) ---

FINISH_TYPE_ICONS: dict[str, str] = {
    "bunch_sprint": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="12" cy="10" r="2" fill="#E53935"/>'
        '<circle cx="9" cy="13" r="2" fill="#E53935"/>'
        '<circle cx="15" cy="13" r="2" fill="#E53935"/>'
        '<circle cx="7" cy="16" r="2" fill="#E53935" opacity="0.7"/>'
        '<circle cx="17" cy="16" r="2" fill="#E53935" opacity="0.7"/>'
        '<path d="M12 6 L14 8 L10 8 Z" fill="#E53935" opacity="0.5"/>'
        '</svg>'
    ),
    "small_group_sprint": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="7" cy="10" r="2" fill="#FF9800"/>'
        '<circle cx="11" cy="10" r="2" fill="#FF9800"/>'
        '<circle cx="15" cy="10" r="2" fill="#FF9800"/>'
        '<line x1="17" y1="12" x2="17" y2="12" stroke="#FF9800" stroke-width="0"/>'
        '<circle cx="7" cy="16" r="1.5" fill="#FF9800" opacity="0.4"/>'
        '<circle cx="10" cy="16" r="1.5" fill="#FF9800" opacity="0.4"/>'
        '<circle cx="13" cy="16" r="1.5" fill="#FF9800" opacity="0.4"/>'
        '<circle cx="16" cy="16" r="1.5" fill="#FF9800" opacity="0.4"/>'
        '<circle cx="19" cy="16" r="1.5" fill="#FF9800" opacity="0.4"/>'
        '<line x1="4" y1="13" x2="20" y2="13" stroke="#FF9800" stroke-width="0.5" '
        'stroke-dasharray="2,2" opacity="0.5"/>'
        '</svg>'
    ),
    "breakaway": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="6" cy="12" r="2.5" fill="#4CAF50"/>'
        '<line x1="10" y1="12" x2="14" y2="12" stroke="#4CAF50" stroke-width="1" '
        'stroke-dasharray="2,2"/>'
        '<circle cx="17" cy="11" r="1.5" fill="#4CAF50" opacity="0.4"/>'
        '<circle cx="19" cy="13" r="1.5" fill="#4CAF50" opacity="0.4"/>'
        '<circle cx="17" cy="15" r="1.5" fill="#4CAF50" opacity="0.4"/>'
        '<circle cx="20" cy="11" r="1.5" fill="#4CAF50" opacity="0.4"/>'
        '<circle cx="21" cy="14" r="1.5" fill="#4CAF50" opacity="0.4"/>'
        '</svg>'
    ),
    "breakaway_selective": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="5" cy="11" r="2" fill="#2E7D32"/>'
        '<circle cx="9" cy="12" r="2" fill="#2E7D32"/>'
        '<line x1="12" y1="12" x2="15" y2="12" stroke="#2E7D32" stroke-width="1" '
        'stroke-dasharray="2,2"/>'
        '<circle cx="17" cy="10" r="1.5" fill="#2E7D32" opacity="0.4"/>'
        '<circle cx="20" cy="13" r="1.5" fill="#2E7D32" opacity="0.4"/>'
        '<circle cx="18" cy="16" r="1.5" fill="#2E7D32" opacity="0.4"/>'
        '<circle cx="21" cy="9" r="1.5" fill="#2E7D32" opacity="0.4"/>'
        '</svg>'
    ),
    "reduced_sprint": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="6" cy="11" r="2" fill="#1E88E5"/>'
        '<circle cx="10" cy="11" r="2" fill="#1E88E5"/>'
        '<circle cx="8" cy="14" r="2" fill="#1E88E5"/>'
        '<circle cx="12" cy="13" r="2" fill="#1E88E5"/>'
        '<line x1="15" y1="12" x2="17" y2="12" stroke="#1E88E5" stroke-width="0.5" '
        'stroke-dasharray="1,1"/>'
        '<circle cx="19" cy="11" r="1.3" fill="#1E88E5" opacity="0.35"/>'
        '<circle cx="21" cy="14" r="1.3" fill="#1E88E5" opacity="0.35"/>'
        '<circle cx="20" cy="17" r="1.3" fill="#1E88E5" opacity="0.35"/>'
        '</svg>'
    ),
    "gc_selective": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="4" cy="8" r="1.5" fill="#7B1FA2"/>'
        '<circle cx="7" cy="9" r="1.5" fill="#7B1FA2"/>'
        '<circle cx="11" cy="11" r="1.5" fill="#7B1FA2" opacity="0.7"/>'
        '<circle cx="14" cy="10" r="1.5" fill="#7B1FA2" opacity="0.7"/>'
        '<circle cx="8" cy="14" r="1.5" fill="#7B1FA2" opacity="0.5"/>'
        '<circle cx="17" cy="13" r="1.5" fill="#7B1FA2" opacity="0.5"/>'
        '<circle cx="20" cy="15" r="1.5" fill="#7B1FA2" opacity="0.35"/>'
        '<circle cx="12" cy="17" r="1.5" fill="#7B1FA2" opacity="0.35"/>'
        '</svg>'
    ),
    "individual_tt": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="12" cy="12" r="9" fill="none" stroke="#00ACC1" stroke-width="2"/>'
        '<line x1="12" y1="12" x2="12" y2="6" stroke="#00ACC1" stroke-width="2" '
        'stroke-linecap="round"/>'
        '<line x1="12" y1="12" x2="16" y2="12" stroke="#00ACC1" stroke-width="1.5" '
        'stroke-linecap="round"/>'
        '<circle cx="12" cy="12" r="1.5" fill="#00ACC1"/>'
        '</svg>'
    ),
    "mixed": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="6" cy="8" r="2" fill="#78909C"/>'
        '<circle cx="14" cy="12" r="2" fill="#78909C" opacity="0.7"/>'
        '<circle cx="9" cy="16" r="2" fill="#78909C" opacity="0.5"/>'
        '</svg>'
    ),
    "unknown": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="12" cy="12" r="9" fill="none" stroke="#9E9E9E" stroke-width="2"/>'
        '<text x="12" y="16" text-anchor="middle" font-size="12" fill="#9E9E9E">?</text>'
        '</svg>'
    ),
}

FINISH_TYPE_COLORS = {
    "bunch_sprint": "#E53935",
    "small_group_sprint": "#FF9800",
    "breakaway": "#4CAF50",
    "breakaway_selective": "#2E7D32",
    "reduced_sprint": "#1E88E5",
    "gc_selective": "#7B1FA2",
    "individual_tt": "#00ACC1",
    "mixed": "#78909C",
    "unknown": "#9E9E9E",
}

# Keep old race type colors for backward compat in charts
RACE_TYPE_COLORS = {
    "criterium": "#E53935",
    "road_race": "#1E88E5",
    "hill_climb": "#43A047",
    "stage_race": "#FB8C00",
    "time_trial": "#8E24AA",
    "gravel": "#6D4C41",
}


def render_sidebar_filters(session) -> dict:
    """Render sidebar with category, year, and state filters.

    Returns dict with keys: year, states, category.
    """
    st.sidebar.title("Filters")

    years = _cached_years(session)
    states = _cached_states(session)
    categories = _cached_categories(session)

    year = st.sidebar.selectbox(
        "Year",
        options=[None] + years,
        format_func=lambda x: "All Years" if x is None else str(x),
    )
    selected_states = st.sidebar.multiselect(
        "State/Province",
        options=states,
        default=states,
    )
    category = st.sidebar.selectbox(
        "Category",
        options=[None] + categories,
        format_func=lambda x: "All Categories" if x is None else x,
    )

    return {"year": year, "states": selected_states or None, "category": category}


@st.cache_data(ttl=300)
def _cached_years(_session) -> list:
    return queries.get_available_years(_session)


@st.cache_data(ttl=300)
def _cached_states(_session) -> list:
    return queries.get_available_states(_session)


@st.cache_data(ttl=300)
def _cached_categories(_session) -> list:
    return queries.get_categories(_session)


TERRAIN_COLORS = {
    "flat": "#2196F3",
    "rolling": "#FF9800",
    "hilly": "#F44336",
    "mountainous": "#9C27B0",
    "unknown": "#9E9E9E",
}


def render_terrain_badge(course_type_value: str):
    """Render a colored terrain classification badge."""
    from raceanalyzer.elevation import course_type_display

    display = course_type_display(course_type_value)
    color = TERRAIN_COLORS.get(course_type_value, "#9E9E9E")
    st.markdown(
        f'<span style="background-color:{color};color:white;padding:2px 8px;'
        f'border-radius:4px;font-size:0.85em;">{display}</span>',
        unsafe_allow_html=True,
    )


def render_prediction_badge(predicted_finish_type: str, confidence: str):
    """Render a predicted finish type badge with confidence level."""
    from raceanalyzer.queries import finish_type_display_name

    ft_display = finish_type_display_name(predicted_finish_type)
    ft_color = FINISH_TYPE_COLORS.get(predicted_finish_type, "#9E9E9E")

    conf_labels = {"high": "Likely", "moderate": "Probable", "low": "Possible"}
    qualifier = conf_labels.get(confidence, "")

    st.markdown(
        f'<span style="background-color:{ft_color};color:white;padding:2px 8px;'
        f'border-radius:4px;font-size:0.85em;" '
        f'title="{qualifier}">{ft_display}</span>',
        unsafe_allow_html=True,
    )


def render_confidence_badge(label: str, color: str):
    """Render a colored confidence badge using inline CSS."""
    color_map = {
        "green": "#28a745",
        "orange": "#fd7e14",
        "red": "#dc3545",
        "gray": "#6c757d",
    }
    hex_color = color_map.get(color, "#6c757d")
    st.markdown(
        f'<span style="background-color:{hex_color};color:white;padding:2px 8px;'
        f'border-radius:4px;font-size:0.85em;">{label}</span>',
        unsafe_allow_html=True,
    )


def render_empty_state(message: str = "No data available."):
    """Render a friendly empty state message."""
    st.info(message)


# --- CSS Grid tile rendering ---

def _inject_tile_css():
    """Inject CSS Grid styles for race tiles."""
    st.markdown('''
    <style>
    .race-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 16px;
        margin-bottom: 16px;
    }
    .race-tile {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 12px;
        background: white;
        cursor: pointer;
        transition: box-shadow 0.2s, transform 0.2s;
    }
    .race-tile:hover {
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        transform: translateY(-2px);
    }
    .race-tile a {
        text-decoration: none;
        color: inherit;
        display: block;
    }
    .tile-header {
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .tile-meta {
        margin-top: 8px;
        font-size: 0.85em;
        color: #666;
    }
    .tile-badge {
        display: inline-block;
        margin-top: 6px;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.8em;
        color: white;
        cursor: help;
    }
    @media (max-width: 768px) {
        .race-grid { grid-template-columns: repeat(2, 1fr); }
    }
    @media (max-width: 480px) {
        .race-grid { grid-template-columns: 1fr; }
    }
    </style>
    ''', unsafe_allow_html=True)
    _TILE_CSS_INJECTED = True


def _render_single_tile(tile_row: dict, key_prefix: str = "tile"):
    """Render a single race tile with finish-type icon, badge, and tooltip."""
    finish_type = tile_row.get("overall_finish_type", "unknown")
    color = FINISH_TYPE_COLORS.get(finish_type, "#9E9E9E")
    icon_svg = FINISH_TYPE_ICONS.get(finish_type, FINISH_TYPE_ICONS["unknown"])
    display_name = html.escape(
        FINISH_TYPE_DISPLAY_NAMES.get(finish_type, "Unknown")
    )
    tooltip = html.escape(FINISH_TYPE_TOOLTIPS.get(finish_type, ""))
    name = html.escape(str(tile_row.get("name", "")))

    # Date
    date_str = ""
    if tile_row.get("date"):
        try:
            date_str = f"{tile_row['date']:%b %d, %Y}"
        except (TypeError, ValueError):
            date_str = str(tile_row["date"])

    loc = html.escape(str(tile_row.get("location", "") or ""))
    state = html.escape(str(tile_row.get("state_province", "") or ""))
    loc_str = f"{loc}, {state}" if state else loc

    with st.container(border=True):
        # Icon + name
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:8px;">'
            f'{icon_svg} <strong>{name}</strong></div>',
            unsafe_allow_html=True,
        )

        # Date and location
        st.markdown(
            f'<div style="font-size:0.85em;color:#666;">'
            f'{date_str} &middot; {loc_str}</div>',
            unsafe_allow_html=True,
        )

        # Classification badge with tooltip
        st.markdown(
            f'<div style="margin-top:4px;">'
            f'<span style="background:{color};color:white;padding:2px 8px;'
            f'border-radius:4px;font-size:0.8em;cursor:help;" '
            f'title="{tooltip}">{display_name}</span></div>',
            unsafe_allow_html=True,
        )

        # Navigation button
        race_id = int(tile_row["id"])
        if st.button(
            "View Details", key=f"{key_prefix}_btn_{race_id}",
            use_container_width=True,
        ):
            st.session_state["selected_race_id"] = race_id
            st.query_params["race_id"] = str(race_id)
            st.switch_page("pages/race_detail.py")


def render_tile_grid(tiles_df, key_prefix: str = "cal"):
    """Render race tiles in a 3-wide grid using st.columns."""
    _inject_tile_css()

    for row_start in range(0, len(tiles_df), 3):
        cols = st.columns(3)
        for col_idx in range(3):
            idx = row_start + col_idx
            if idx < len(tiles_df):
                with cols[col_idx]:
                    tile_data = tiles_df.iloc[idx].to_dict()
                    _render_single_tile(tile_data, key_prefix=f"{key_prefix}_{idx}")


# --- Series tile rendering ---


def _render_series_tile(tile_row: dict, key_prefix: str = "stile"):
    """Render a single series tile with finish-type icon, badge, and edition count."""
    finish_type = tile_row.get("overall_finish_type", "unknown")
    color = FINISH_TYPE_COLORS.get(finish_type, "#9E9E9E")
    icon_svg = FINISH_TYPE_ICONS.get(finish_type, FINISH_TYPE_ICONS["unknown"])
    display_name = html.escape(
        FINISH_TYPE_DISPLAY_NAMES.get(finish_type, "Unknown")
    )
    tooltip = html.escape(FINISH_TYPE_TOOLTIPS.get(finish_type, ""))
    name = html.escape(str(tile_row.get("display_name", "")))
    edition_count = tile_row.get("edition_count", 1)

    # Date range
    date_str = ""
    latest = tile_row.get("latest_date")
    earliest = tile_row.get("earliest_date")
    if latest and earliest and edition_count > 1:
        try:
            date_str = f"{earliest:%Y} -- {latest:%Y}"
        except (TypeError, ValueError):
            date_str = ""
    elif latest:
        try:
            date_str = f"{latest:%b %d, %Y}"
        except (TypeError, ValueError):
            date_str = str(latest)

    loc = html.escape(str(tile_row.get("location", "") or ""))
    state = html.escape(str(tile_row.get("state_province", "") or ""))
    loc_str = f"{loc}, {state}" if state else loc

    with st.container(border=True):
        # Icon + name + edition badge
        edition_badge = ""
        if edition_count > 1:
            edition_badge = (
                f' <span style="background:#6c757d;color:white;padding:1px 6px;'
                f'border-radius:3px;font-size:0.75em;margin-left:4px;">'
                f'{edition_count} ed</span>'
            )
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:8px;">'
            f'{icon_svg} <strong>{name}</strong>{edition_badge}</div>',
            unsafe_allow_html=True,
        )

        # Date and location
        st.markdown(
            f'<div style="font-size:0.85em;color:#666;">'
            f'{date_str} &middot; {loc_str}</div>',
            unsafe_allow_html=True,
        )

        # Classification badge with tooltip
        st.markdown(
            f'<div style="margin-top:4px;">'
            f'<span style="background:{color};color:white;padding:2px 8px;'
            f'border-radius:4px;font-size:0.8em;cursor:help;" '
            f'title="{tooltip}">{display_name}</span></div>',
            unsafe_allow_html=True,
        )

        # Navigation button
        series_id = int(tile_row["series_id"])
        if edition_count == 1:
            # Single edition: go directly to race detail
            # Need to find the race_id for this series
            btn_label = "View Details"
        else:
            btn_label = f"View {edition_count} Editions"

        btn_col, preview_col = st.columns(2)
        with btn_col:
            if st.button(btn_label, key=f"{key_prefix}_btn_{series_id}",
                         use_container_width=True):
                st.session_state["selected_series_id"] = series_id
                st.query_params["series_id"] = str(series_id)
                st.switch_page("pages/series_detail.py")
        with preview_col:
            if st.button("Preview", key=f"{key_prefix}_preview_{series_id}",
                         use_container_width=True):
                st.session_state["preview_series_id"] = series_id
                st.query_params["series_id"] = str(series_id)
                st.switch_page("pages/race_preview.py")


def render_series_tile_grid(tiles_df, key_prefix: str = "cal"):
    """Render series tiles in a 3-wide grid using st.columns."""
    _inject_tile_css()

    for row_start in range(0, len(tiles_df), 3):
        cols = st.columns(3)
        for col_idx in range(3):
            idx = row_start + col_idx
            if idx < len(tiles_df):
                with cols[col_idx]:
                    tile_data = tiles_df.iloc[idx].to_dict()
                    _render_series_tile(tile_data, key_prefix=f"{key_prefix}_{idx}")


# --- Scary Racer rendering ---

_THREAT_LEVELS = [
    (500, "Apex Predator", "#dc3545"),
    (400, "Very Dangerous", "#fd7e14"),
    (300, "Dangerous", "#FFC107"),
    (0, "One to Watch", "#6c757d"),
]


def render_scary_racer_card(racer: dict):
    """Render a single scary racer card with threat level badge."""
    points = racer.get("carried_points", 0) or 0
    threat_label = "One to Watch"
    threat_color = "#6c757d"
    for threshold, label, color in _THREAT_LEVELS:
        if points >= threshold:
            threat_label = label
            threat_color = color
            break

    badge_html = (
        f'<span style="background-color:{threat_color};color:white;padding:2px 8px;'
        f'border-radius:4px;font-size:0.8em;">{threat_label}</span>'
    )

    name = racer.get("name", "Unknown")
    team = racer.get("team", "")
    team_str = f" ({team})" if team else ""

    st.markdown(
        f"**{name}**{team_str} {badge_html}",
        unsafe_allow_html=True,
    )
    wins = racer.get("wins", 0)
    st.caption(f"Points: {points:.1f} | Wins: {wins}")


# --- Selectivity badge ---

_SELECTIVITY_COLORS = {
    "low": "#28a745",
    "moderate": "#fd7e14",
    "high": "#dc3545",
    "extreme": "#B71C1C",
}

_SELECTIVITY_LABELS = {
    "low": "Low attrition",
    "moderate": "Moderate attrition",
    "high": "High attrition",
    "extreme": "Extreme attrition",
}


def render_selectivity_badge(label: str):
    """Render a colored selectivity/drop rate badge."""
    color = _SELECTIVITY_COLORS.get(label, "#6c757d")
    display = _SELECTIVITY_LABELS.get(label, label.title())
    st.markdown(
        f'<span style="background-color:{color};color:white;padding:2px 8px;'
        f'border-radius:4px;font-size:0.85em;">{display}</span>',
        unsafe_allow_html=True,
    )


# --- Climb legend ---

_CLIMB_LEGEND_ITEMS = [
    ("Moderate (3-5%)", "#FFC107"),
    ("Steep (5-8%)", "#FF5722"),
    ("Brutal (8%+)", "#B71C1C"),
]


def render_dormant_badge():
    """Render a 'No upcoming edition' badge with reduced opacity."""
    st.markdown(
        '<span style="background:#9E9E9E;color:white;padding:2px 8px;'
        'border-radius:4px;font-size:0.8em;">No upcoming edition</span>',
        unsafe_allow_html=True,
    )


def render_elevation_sparkline(
    profile_points: list, width: int = 200, height: int = 40
):
    """Render a tiny elevation sparkline as inline SVG."""
    if not profile_points or len(profile_points) < 2:
        return

    elevations = [p.get("e", 0) for p in profile_points]
    min_e = min(elevations)
    max_e = max(elevations)
    e_range = max_e - min_e
    if e_range <= 0:
        e_range = 1.0

    n = len(profile_points)
    x_step = width / max(n - 1, 1)

    # Build SVG path
    points_str = ""
    for i, e in enumerate(elevations):
        x = round(i * x_step, 1)
        y = round(height - ((e - min_e) / e_range) * height, 1)
        if i == 0:
            points_str += f"M{x},{y}"
        else:
            points_str += f" L{x},{y}"

    # Close path for fill
    fill_path = points_str + f" L{width},{height} L0,{height} Z"

    svg = (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}"'
        f' xmlns="http://www.w3.org/2000/svg">'
        f'<path d="{fill_path}" fill="#4CAF50" opacity="0.3"/>'
        f'<path d="{points_str}" fill="none" stroke="#4CAF50" stroke-width="1.5"/>'
        f'</svg>'
    )
    st.markdown(svg, unsafe_allow_html=True)


def render_feed_card(item: dict):
    """Render Tier 2 detail content inside an expanded feed card (Sprint 011)."""
    # Narrative + racer type
    text_col, spark_col = st.columns([3, 1])
    with text_col:
        if item.get("narrative_snippet"):
            st.write(item["narrative_snippet"])
        if item.get("racer_type_description"):
            st.caption(item["racer_type_description"])
    with spark_col:
        if item.get("elevation_sparkline_points"):
            render_elevation_sparkline(item["elevation_sparkline_points"])

    # Duration + climb highlight
    if item.get("duration_minutes") or item.get("climb_highlight"):
        if item.get("duration_minutes"):
            winner_m = item["duration_minutes"]["winner_duration_minutes"]
            hours, mins = divmod(int(winner_m), 60)
            st.caption(f"Typical duration: ~{hours}h {mins:02d}m")
        if item.get("climb_highlight"):
            st.caption(item["climb_highlight"])

    # Historical editions
    editions = item.get("editions_summary", [])
    if editions and len(editions) > 1:
        with st.popover(f"{len(editions)} previous editions"):
            for ed in editions:
                year_str = str(ed["year"]) if ed.get("year") else "?"
                st.write(f"- {year_str}: {ed['finish_type_display']}")


def render_global_category_filter(session) -> None:
    """Render a persistent global category filter in the sidebar.

    Reads/writes st.session_state.global_category.
    Syncs to st.query_params['category'] for URL persistence (Sprint 010).
    """
    categories = _cached_categories(session)
    current = st.session_state.get("global_category")

    cat_options = [None] + categories
    default_idx = 0
    if current and current in categories:
        default_idx = categories.index(current) + 1

    chosen = st.sidebar.selectbox(
        "Your Category",
        options=cat_options,
        index=default_idx,
        format_func=lambda x: "All Categories" if x is None else x,
        key="global_category_selector",
    )

    if chosen != current:
        st.session_state["global_category"] = chosen
        if chosen:
            st.query_params["category"] = chosen
        elif "category" in st.query_params:
            del st.query_params["category"]


def render_climb_legend():
    """Render a horizontal climb severity legend."""
    items_html = ""
    for label, color in _CLIMB_LEGEND_ITEMS:
        items_html += (
            f'<span style="display:inline-block;margin-right:12px;">'
            f'<span style="display:inline-block;width:12px;height:12px;'
            f'background:{color};border-radius:2px;vertical-align:middle;'
            f'margin-right:4px;"></span>{label}</span>'
        )
    st.markdown(
        f'<div style="font-size:0.85em;color:#666;margin-top:4px;">'
        f'{items_html}</div>',
        unsafe_allow_html=True,
    )


def render_feed_filters(session) -> dict:
    """Render state/province filter pills in the top chip bar area.

    Sprint 018: Advanced Filters expander removed entirely.
    State/province filtering now handled by _render_filter_chips in feed.py.
    Returns empty dict for backward compatibility.
    """
    return {}


def _init_filters_from_params():
    """On page load, seed session state from URL params if not already set.

    Sprint 020: Also seed widget keys (racer_cat_pills, racer_gender_pills,
    racer_masters_toggle, racer_masters_age, team_name_input) so that
    st.pills/st.toggle/st.text_input can own their state via key= without
    needing default=/value= (fixes double-click race condition).
    """
    for key in ("cat", "gender", "masters", "age", "team", "states"):
        if key not in st.session_state and key in st.query_params:
            st.session_state[key] = st.query_params[key]

    # Seed widget keys from URL params (only when absent in session state)
    if "racer_cat_pills" not in st.session_state:
        param_cat = st.query_params.get("cat")
        st.session_state["racer_cat_pills"] = (
            param_cat if param_cat in ("1", "2", "3", "4", "5") else "All"
        )
    if "racer_gender_pills" not in st.session_state:
        param_gender = st.query_params.get("gender")
        st.session_state["racer_gender_pills"] = (
            param_gender if param_gender in ("M", "W") else "All"
        )
    if "racer_masters_toggle" not in st.session_state:
        st.session_state["racer_masters_toggle"] = (
            st.query_params.get("masters") == "1"
        )
    if "racer_masters_age" not in st.session_state:
        try:
            st.session_state["racer_masters_age"] = int(
                st.query_params.get("age", "")
            )
        except (ValueError, TypeError):
            pass  # leave unset; number_input will use its own default
    if "team_name_input" not in st.session_state:
        param_team = st.query_params.get("team", "")
        if param_team:
            st.session_state["team_name_input"] = param_team


def resolve_effective_category(categories: list[str]) -> tuple:
    """Read racer profile from session state, resolve to best-matching category.

    Returns (category_string | None, is_exact_match).
    """
    cat_level = st.session_state.get("cat")
    gender = st.session_state.get("gender")
    masters_on = st.session_state.get("masters") == "1"
    masters_age = int(st.session_state.get("age", "0") or "0") or None
    return queries.resolve_racer_profile(
        categories,
        cat_level=cat_level,
        gender=gender,
        masters_on=masters_on,
        masters_age=masters_age,
    )


def render_racer_profile_filters(session) -> dict:
    """Render cohesive racer profile filters in a bordered sidebar container.

    Returns dict with keys: cat_level, gender, masters_on, masters_age, team_name.
    Syncs to URL params: cat, gender, masters, age, team.
    """
    with st.sidebar.container(border=True):
        # Sprint 020: "My Info" header
        st.markdown("**My Info**")

        # Sprint 020: Team search at top (before category pills)
        team_name = st.text_input(
            "My Team",
            placeholder="e.g. Hagens Berman",
            key="team_name_input",
        )
        current_team = st.query_params.get("team", "")
        if team_name != current_team:
            if team_name:
                st.query_params["team"] = team_name
            elif "team" in st.query_params:
                del st.query_params["team"]
        if team_name:
            st.session_state["team"] = team_name
        else:
            st.session_state.pop("team", None)

        team_result = None
        if team_name and len(team_name.strip()) >= 3:
            team_result = team_name.strip()
        elif team_name and len(team_name.strip()) < 3:
            st.caption("Enter at least 3 characters")

        # Sprint 020: Category pills — NO default= (widget key owns state)
        cat_options = ["All", "1", "2", "3", "4", "5"]
        chosen_cat = st.pills(
            "Category",
            cat_options,
            key="racer_cat_pills",
        )
        cat_level = chosen_cat if chosen_cat and chosen_cat != "All" else None

        # Sync cat to URL and session state
        if cat_level:
            if st.query_params.get("cat") != cat_level:
                st.query_params["cat"] = cat_level
            st.session_state["cat"] = cat_level
        else:
            if "cat" in st.query_params:
                del st.query_params["cat"]
            st.session_state.pop("cat", None)

        # Sprint 020: Gender pills — NO default=
        gender_options = ["All", "M", "W"]
        chosen_gender = st.pills(
            "Gender",
            gender_options,
            key="racer_gender_pills",
        )
        gender = chosen_gender if chosen_gender and chosen_gender != "All" else None

        # Sync gender to URL and session state
        if gender:
            if st.query_params.get("gender") != gender:
                st.query_params["gender"] = gender
            st.session_state["gender"] = gender
        else:
            if "gender" in st.query_params:
                del st.query_params["gender"]
            st.session_state.pop("gender", None)

        # Sprint 020: Masters toggle — NO value= (widget key owns state)
        masters_on = st.toggle("Masters", key="racer_masters_toggle")

        masters_age = None
        if masters_on:
            masters_age = st.number_input(
                "Age",
                min_value=30,
                max_value=99,
                value=45,
                key="racer_masters_age",
            )

        # Sync masters/age to URL and session state
        if masters_on:
            if st.query_params.get("masters") != "1":
                st.query_params["masters"] = "1"
            st.session_state["masters"] = "1"
            if masters_age and st.query_params.get("age") != str(masters_age):
                st.query_params["age"] = str(masters_age)
            if masters_age:
                st.session_state["age"] = str(masters_age)
        else:
            if "masters" in st.query_params:
                del st.query_params["masters"]
            if "age" in st.query_params:
                del st.query_params["age"]
            st.session_state.pop("masters", None)
            st.session_state.pop("age", None)

    return {
        "cat_level": cat_level,
        "gender": gender,
        "masters_on": masters_on,
        "masters_age": masters_age,
        "team_name": team_result,
    }


def render_climb_breakdown(climbs, distance_m=None, finish_type=None, drop_rate=None):
    """Render climb-by-climb breakdown with race context narratives."""
    from raceanalyzer.predictions import climb_context_line

    if not climbs:
        st.info("No significant climbs detected on this course.")
        return

    for i, climb in enumerate(climbs):
        context = climb_context_line(
            climb, total_distance_m=distance_m,
            finish_type=finish_type, drop_rate=drop_rate,
        )
        st.markdown(f"**Climb {i + 1}:** {context}")


def render_finish_pattern(editions_summary):
    """Render historical finish type icons per edition year."""
    if not editions_summary:
        return

    icons_html = ""
    for ed in editions_summary:
        year = ed.get("year", "?")
        ft = ed.get("finish_type", "unknown")
        ft_display = ed.get("finish_type_display", "Unknown")
        icon = FINISH_TYPE_ICONS.get(ft, FINISH_TYPE_ICONS["unknown"])
        icons_html += (
            f'<span style="display:inline-block;text-align:center;margin-right:12px;" '
            f'title="{html.escape(str(year))}: {html.escape(ft_display)}">'
            f'{icon}<br><span style="font-size:0.75em;color:#666;">'
            f'{html.escape(str(year))}</span>'
            f'</span>'
        )

    st.markdown(icons_html, unsafe_allow_html=True)


def render_similar_races(similar_items):
    """Render similar races as deep links."""
    if not similar_items:
        st.info("No similar races found.")
        return

    for score, item in similar_items:
        col1, col2 = st.columns([3, 1])
        with col1:
            name = item["display_name"]
            loc = item.get("location", "")
            # Build similarity reason tags
            reasons = []
            ct = item.get("course_type")
            if ct:
                reasons.append(ct.replace("_", " ").title() + " terrain")
            ft = item.get("predicted_finish_type")
            if ft:
                reasons.append(ft.replace("_", " ").title())
            reason_text = f" · {', '.join(reasons)}" if reasons else ""
            st.write(f"**{name}** — {loc}{reason_text}")
        with col2:
            sid = item["series_id"]
            if st.button("View", key=f"similar_{sid}", use_container_width=True):
                st.query_params["series_id"] = str(sid)
                st.rerun()


def render_team_startlist(team_blocks, user_team_name=None):
    """Render startlist grouped by team with user's team highlighted."""
    if not team_blocks:
        st.info("No startlist data available.")
        return

    for block in team_blocks:
        team = block["team"]
        riders = block["riders"]
        count = block["count"]

        # Highlight user's team
        is_user_team = (
            user_team_name
            and len(user_team_name) >= 3
            and user_team_name.lower() in team.lower()
        )

        header = f"**{html.escape(team)}** ({count})"
        if is_user_team:
            header = f"⭐ {header}"

        st.markdown(header)
        for rider in riders:
            pts = rider.get("carried_points")
            pts_str = f" — {pts:.0f} pts" if pts else ""
            st.caption(f"  {rider['name']}{pts_str}")
