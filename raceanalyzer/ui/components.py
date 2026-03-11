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
    (80, "Apex Predator", "#dc3545"),
    (50, "Very Dangerous", "#fd7e14"),
    (25, "Dangerous", "#FFC107"),
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
    """Render the rich content of a feed card (Sprint 010 Phase 2)."""
    from raceanalyzer.queries import finish_type_plain_english

    # Row 1: Badges (plain-English finish type, terrain, drop rate)
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        if item.get("predicted_finish_type"):
            plain = finish_type_plain_english(item["predicted_finish_type"])
            if plain:
                st.write(plain)
            from raceanalyzer.queries import finish_type_display_name
            st.caption(finish_type_display_name(item["predicted_finish_type"]))
    with col2:
        if item.get("course_type"):
            render_terrain_badge(item["course_type"])
    with col3:
        if item.get("drop_rate_pct") is not None:
            st.caption(f"{item['drop_rate_pct']}% drop rate")

    # Row 2: Narrative snippet + sparkline
    text_col, spark_col = st.columns([3, 1])
    with text_col:
        if item.get("narrative_snippet"):
            st.write(item["narrative_snippet"])
        if item.get("racer_type_description"):
            st.caption(item["racer_type_description"])
    with spark_col:
        if item.get("elevation_sparkline_points"):
            render_elevation_sparkline(item["elevation_sparkline_points"])

    # Row 3: Duration + climb highlight
    if item.get("duration_minutes") or item.get("climb_highlight"):
        if item.get("duration_minutes"):
            winner_m = item["duration_minutes"]["winner_duration_minutes"]
            hours, mins = divmod(int(winner_m), 60)
            st.caption(f"Typical duration: ~{hours}h {mins:02d}m")
        if item.get("climb_highlight"):
            st.caption(item["climb_highlight"])

    # Row 4: Registration + full preview link
    if item.get("is_upcoming") and item.get("registration_url"):
        st.markdown(f"[Register]({item['registration_url']})")

    # Row 5: Historical editions
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
