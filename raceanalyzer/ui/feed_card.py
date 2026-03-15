"""Feed card v2: single-block HTML card renderer for Sprint 013.

Renders all collapsed-card content as a single st.markdown(unsafe_allow_html=True)
block to avoid widget-count explosion. Only action buttons use native Streamlit widgets.
"""

from __future__ import annotations

import html
import json
from typing import Optional

from raceanalyzer.ui.components import FINISH_TYPE_COLORS, FINISH_TYPE_ICONS

# --- Race type icons (SVG, 20x20) ---

RACE_TYPE_ICONS: dict[str, str] = {
    "criterium": (
        '<svg width="20" height="20" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="10" cy="10" r="7" fill="none" stroke="#E53935" stroke-width="2"/>'
        '<path d="M7 10 L10 7 L13 10 L10 13 Z" fill="#E53935"/>'
        "</svg>"
    ),
    "road_race": (
        '<svg width="20" height="20" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">'
        '<path d="M2 14 Q6 6 10 10 Q14 14 18 6" fill="none" stroke="#1E88E5" stroke-width="2"'
        ' stroke-linecap="round"/>'
        "</svg>"
    ),
    "hill_climb": (
        '<svg width="20" height="20" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">'
        '<path d="M2 16 L10 4 L18 16" fill="none" stroke="#43A047" stroke-width="2"'
        ' stroke-linejoin="round" stroke-linecap="round"/>'
        "</svg>"
    ),
    "time_trial": (
        '<svg width="20" height="20" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="10" cy="10" r="7" fill="none" stroke="#8E24AA" stroke-width="1.5"/>'
        '<line x1="10" y1="10" x2="10" y2="5" stroke="#8E24AA" stroke-width="1.5"'
        ' stroke-linecap="round"/>'
        '<line x1="10" y1="10" x2="14" y2="10" stroke="#8E24AA" stroke-width="1"'
        ' stroke-linecap="round"/>'
        "</svg>"
    ),
    "gravel": (
        '<svg width="20" height="20" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="6" cy="14" r="1.5" fill="#6D4C41"/>'
        '<circle cx="10" cy="12" r="1.5" fill="#6D4C41"/>'
        '<circle cx="14" cy="15" r="1.5" fill="#6D4C41"/>'
        '<circle cx="8" cy="8" r="1" fill="#6D4C41" opacity="0.6"/>'
        '<circle cx="13" cy="9" r="1" fill="#6D4C41" opacity="0.6"/>'
        '<path d="M2 16 Q10 4 18 16" fill="none" stroke="#6D4C41" stroke-width="1.5"'
        ' stroke-linecap="round"/>'
        "</svg>"
    ),
    "stage_race": (
        '<svg width="20" height="20" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">'
        '<rect x="3" y="6" width="4" height="10" rx="1" fill="#FB8C00" opacity="0.5"/>'
        '<rect x="8" y="4" width="4" height="12" rx="1" fill="#FB8C00" opacity="0.7"/>'
        '<rect x="13" y="2" width="4" height="14" rx="1" fill="#FB8C00"/>'
        "</svg>"
    ),
}

RACE_TYPE_DISPLAY = {
    "criterium": "Criterium",
    "road_race": "Road Race",
    "hill_climb": "Hill Climb",
    "time_trial": "Time Trial",
    "gravel": "Gravel",
    "stage_race": "Stage Race",
}

# --- Chip tooltip explanations (beginner-friendly) ---

CHIP_TOOLTIPS: dict[str, str] = {
    "distance": "Total race distance. Crits are usually 20-50 km, road races 50-150 km.",
    "elevation": "Total meters climbed. Under 300m is mostly flat, 500m+ is hilly.",
    "terrain": "Course profile classification based on climbing per kilometer.",
    "field_size": "How many riders typically start. Bigger fields mean more drafting options.",
    "drop_rate": (
        "Percentage of starters who don't finish. "
        "Lower is better for beginners — most riders complete the race."
    ),
    "duration": (
        "Estimated race duration based on distance, terrain, and "
        "historical finishing times for Cat 4/5 fields."
    ),
    "finish_type": "How the race typically ends — sprint, breakaway, or selection.",
    "climb": "The hardest climb on the course. Grade % tells you how steep it is.",
}

# --- Drop rate color ramp ---

_DROP_RATE_COLORS = [
    (15, "#4CAF50"),   # green — low
    (25, "#8BC34A"),   # light green
    (35, "#FFC107"),   # amber
    (45, "#FF9800"),   # orange
    (100, "#F44336"),  # red — extreme
]


def _drop_rate_color(pct: float) -> str:
    for threshold, color in _DROP_RATE_COLORS:
        if pct <= threshold:
            return color
    return "#F44336"


# --- Countdown pill colors ---


def countdown_pill_style(days_until: Optional[int]) -> tuple[str, str, str]:
    """Return (label, bg_color, text_color) for countdown pill."""
    if days_until is None:
        return ("", "transparent", "inherit")
    if days_until == 0:
        return ("Today", "#D32F2F", "#fff")
    if days_until == 1:
        return ("Tomorrow", "#D32F2F", "#fff")
    if days_until <= 3:
        return (f"in {days_until} days", "#D32F2F", "#fff")
    if days_until <= 14:
        return (f"in {days_until} days", "#F57C00", "#fff")
    weeks = days_until // 7
    bg = "var(--secondary-background-color, #f0f2f6)"
    fg = "var(--text-color, #555)"
    return (f"in {weeks} weeks", bg, fg)


# --- Pack survival text ---


def pack_survival_text(drop_rate_pct: Optional[float], finish_type: Optional[str]) -> str:
    """Return beginner-friendly pack survival odds text."""
    if drop_rate_pct is None:
        return ""
    if drop_rate_pct <= 10:
        return "Nearly everyone finishes together"
    if drop_rate_pct <= 20:
        return "Most riders finish with the group"
    if drop_rate_pct <= 35:
        return "About two-thirds of the field stays together"
    if drop_rate_pct <= 50:
        return "About half get dropped"
    return "Only the strongest survive — expect heavy attrition"


# --- What to expect text ---


def what_to_expect_text(
    finish_type: Optional[str],
    prediction_source: Optional[str] = None,
    race_type: Optional[str] = None,
) -> str:
    """Return a future-tense one-liner (<=120 chars) for the collapsed card.

    Thin wrapper over predictions.finish_type_teaser() for backward
    compatibility (used by generate_share_text etc).
    """
    from raceanalyzer.predictions import finish_type_teaser

    return finish_type_teaser(
        finish_type,
        prediction_source=prediction_source,
        race_type=race_type,
    )


# --- Racer type short label ---


def racer_type_short_label(
    course_type: Optional[str], finish_type: Optional[str]
) -> str:
    """Return a one-word label: 'Sprinters', 'Diesel', 'Climbers', etc."""
    if not course_type or not finish_type:
        return ""
    labels = {
        ("flat", "bunch_sprint"): "Sprinters",
        ("flat", "small_group_sprint"): "Sprinters",
        ("flat", "breakaway"): "Diesel",
        ("flat", "reduced_sprint"): "All-rounders",
        ("rolling", "bunch_sprint"): "Punchy sprinters",
        ("rolling", "small_group_sprint"): "Tactical riders",
        ("rolling", "reduced_sprint"): "Punchy riders",
        ("rolling", "breakaway"): "Diesel",
        ("rolling", "breakaway_selective"): "Diesel",
        ("rolling", "gc_selective"): "All-rounders",
        ("hilly", "breakaway"): "Climbers",
        ("hilly", "breakaway_selective"): "Climbers",
        ("hilly", "gc_selective"): "Climbers",
        ("hilly", "reduced_sprint"): "Climbers",
        ("hilly", "small_group_sprint"): "Punchy climbers",
        ("hilly", "bunch_sprint"): "All-rounders",
        ("mountainous", "gc_selective"): "Climbers",
        ("mountainous", "breakaway_selective"): "Climbers",
        ("mountainous", "breakaway"): "Climbers",
        ("mountainous", "reduced_sprint"): "Climbers",
    }
    return labels.get((course_type, finish_type), "")


# --- Beginner-friendly logic ---


# --- Key climb extract ---


def extract_key_climb(climbs_json: Optional[str]) -> Optional[str]:
    """Extract 'Key climb: X km at Y%' from climbs_json string."""
    if not climbs_json:
        return None
    try:
        climbs = json.loads(climbs_json) if isinstance(climbs_json, str) else climbs_json
    except (json.JSONDecodeError, TypeError):
        return None
    if not climbs:
        return None
    hardest = max(climbs, key=lambda c: c.get("avg_grade", 0))
    length_km = hardest.get("length_m", 0) / 1000.0
    grade = hardest.get("avg_grade", 0)
    if length_km <= 0 or grade <= 0:
        return None
    return f"Key climb: {length_km:.1f} km at {grade:.1f}%"


# --- Elevation sparkline SVG ---


def render_elevation_sparkline_svg(
    profile_points: list, width: int = 160, height: int = 46
) -> str:
    """Return tiny SVG sparkline string from profile points."""
    if not profile_points or len(profile_points) < 2:
        return ""

    elevations = [p.get("e", 0) for p in profile_points]
    min_e = min(elevations)
    max_e = max(elevations)
    e_range = max_e - min_e
    if e_range <= 0:
        e_range = 1.0

    n = len(profile_points)
    x_step = width / max(n - 1, 1)

    points_str = ""
    for i, e in enumerate(elevations):
        x = round(i * x_step, 1)
        y = round(height - ((e - min_e) / e_range) * (height - 2) - 1, 1)
        if i == 0:
            points_str += f"M{x},{y}"
        else:
            points_str += f" L{x},{y}"

    fill_path = points_str + f" L{width},{height} L0,{height} Z"

    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}"'
        f' xmlns="http://www.w3.org/2000/svg" style="vertical-align:middle;">'
        f'<path d="{fill_path}" fill="#4CAF50" opacity="0.2"/>'
        f'<path d="{points_str}" fill="none" stroke="#4CAF50" stroke-width="1.5"/>'
        f"</svg>"
    )


# --- Route trace SVG ---


def render_route_trace_svg(
    encoded_polyline: Optional[str], width: int = 160, height: int = 58
) -> str:
    """Generate a tiny SVG route trace from encoded polyline. Returns '' if missing."""
    if not encoded_polyline:
        return ""
    try:
        import polyline as pl

        coords = pl.decode(encoded_polyline)
    except Exception:
        return ""
    if not coords or len(coords) < 2:
        return ""

    # Downsample to ~50 points
    step = max(1, len(coords) // 50)
    sampled = coords[::step]
    if sampled[-1] != coords[-1]:
        sampled.append(coords[-1])

    lats = [c[0] for c in sampled]
    lons = [c[1] for c in sampled]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    lat_range = max_lat - min_lat or 0.001
    lon_range = max_lon - min_lon or 0.001

    padding = 4
    w = width - 2 * padding
    h = height - 2 * padding

    points = []
    for lat, lon in sampled:
        x = round(padding + ((lon - min_lon) / lon_range) * w, 1)
        y = round(padding + (1.0 - (lat - min_lat) / lat_range) * h, 1)
        points.append(f"{x},{y}")

    points_str = " ".join(points)
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}"'
        f' xmlns="http://www.w3.org/2000/svg"'
        f' style="vertical-align:middle;opacity:0.7;">'
        f'<polyline points="{points_str}" fill="none" stroke="#78909C"'
        f' stroke-width="1.5" stroke-linejoin="round"/>'
        f'<circle cx="{points[0].split(",")[0]}" cy="{points[0].split(",")[1]}"'
        f' r="2" fill="#4CAF50"/>'
        f'<circle cx="{points[-1].split(",")[0]}" cy="{points[-1].split(",")[1]}"'
        f' r="2" fill="#E53935"/>'
        f"</svg>"
    )


# --- Distribution sparkline ---


def render_distribution_sparkline(
    distribution_json: Optional[str], width: int = 100, height: int = 12,
) -> str:
    """Render a tiny stacked bar from distribution_json."""
    if not distribution_json:
        return ""
    try:
        dist = (
            json.loads(distribution_json)
            if isinstance(distribution_json, str)
            else distribution_json
        )
    except (json.JSONDecodeError, TypeError):
        return ""
    if not dist:
        return ""

    total = sum(dist.values())
    if total <= 0:
        return ""

    bars = ""
    x = 0
    for ft, count in sorted(dist.items(), key=lambda kv: -kv[1]):
        w = round((count / total) * width, 1)
        if w < 1:
            w = 1
        color = FINISH_TYPE_COLORS.get(ft, "#9E9E9E")
        bars += (
            f'<rect x="{x}" y="0" width="{w}" height="{height}" '
            f'fill="{color}" rx="1"/>'
        )
        x += w

    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}"'
        f' xmlns="http://www.w3.org/2000/svg" style="vertical-align:middle;">'
        f"{bars}</svg>"
    )


# --- Duration format ---


def format_duration(minutes: Optional[float]) -> str:
    """Format minutes as '~Xh Ym'."""
    if not minutes or minutes <= 0:
        return ""
    hours = int(minutes) // 60
    mins = int(minutes) % 60
    if hours > 0:
        return f"~{hours}h {mins:02d}m"
    return f"~{mins}m"


# --- Confidence badge text ---


def confidence_text(
    confidence: Optional[str],
    edition_count: int,
    prediction_source: Optional[str] = None,
) -> str:
    """Return confidence indicator text."""
    if not confidence:
        return ""
    if confidence == "high" and edition_count >= 3:
        return f"High confidence \u00b7 Based on {edition_count} editions"
    if confidence == "moderate":
        plural = "s" if edition_count != 1 else ""
        return f"Moderate confidence \u00b7 {edition_count} edition{plural}"
    if confidence == "low" or edition_count <= 1:
        if prediction_source == "course_profile":
            return "Estimate \u2014 based on course profile"
        if prediction_source == "race_type_only":
            return "Estimate \u2014 based on race type"
        return "Estimate \u2014 first year"
    return f"Based on {edition_count} editions"


# ============================================================
# CSS injection (called once per page render)
# ============================================================


def inject_feed_styles():
    """Inject CSS styles for feed rows. Call once at top of render."""
    import streamlit as st

    st.markdown(
        """
    <style>
    /* Feed row styles (Sprint 019) */

    /* Constrain feed content to consistent width */
    section[data-testid="stMain"] .block-container {
        max-width: 1060px !important;
    }

    /* Row press micro-animation */
    div[data-testid="stVerticalBlock"] > div:has(.feed-row) {
        transition: transform 150ms ease, opacity 150ms ease;
    }
    div[data-testid="stVerticalBlock"] > div:has(.feed-row):active {
        transform: scale(0.98);
        opacity: 0.9;
    }

    /* Prediction highlight glow */
    .feed-row-ai {
        animation: feed-pred-glow 1.5s ease-out;
    }
    @keyframes feed-pred-glow {
        0% { background: rgba(255, 193, 7, 0.15); }
        100% { background: transparent; }
    }

    /* Chip icon sizing */
    .feed-card-chip svg {
        width: 16px;
        height: 16px;
    }

    /* Chip hover */
    .feed-card-chip:hover {
        filter: brightness(0.95);
    }

    /* Racing Soon header */
    .feed-racing-soon-header {
        animation: feed-soon-pulse 2s ease-in-out;
    }
    @keyframes feed-soon-pulse {
        0% { background: linear-gradient(90deg, #FFE0B2, transparent); }
        50% { background: linear-gradient(90deg, #FFF3E0, transparent); }
        100% { background: linear-gradient(90deg, #FFF3E0, transparent); }
    }

    /* Sticky month headers (FO-02) */
    .feed-month-header {
        position: sticky;
        top: 0;
        z-index: 10;
        backdrop-filter: blur(8px);
    }

    /* Teammate accent warmth */
    .feed-card-teammate {
        animation: feed-team-glow 1s ease-out;
    }
    @keyframes feed-team-glow {
        0% { background: rgba(255, 111, 0, 0.2); }
        100% { background: rgba(255, 111, 0, 0.08); }
    }

    /* Dark mode surface differentiation */
    @media (prefers-color-scheme: dark) {
        .feed-row {
            color: var(--text-color, #e0e0e0);
        }
        .feed-row span {
            color: var(--text-color, #e0e0e0);
        }
        .feed-card-chip {
            background: var(--secondary-background-color, #2d2d2d) !important;
            color: var(--text-color, #e0e0e0) !important;
        }
        .feed-card-date-pill {
            box-shadow: 0 1px 3px rgba(0,0,0,0.3);
        }
        .feed-row-date .feed-row-month,
        .feed-row-date .feed-row-day {
            color: var(--text-color, #e0e0e0);
            opacity: 0.55;
        }
    }

    /* Expand/collapse transition */
    div[data-testid="stExpander"] {
        transition: max-height 300ms ease, opacity 200ms ease;
    }

    /* Sprint 019: Row responsive collapse at 700px */
    @media (max-width: 700px) {
        .feed-row {
            grid-template-columns: 56px 1fr !important;
        }
        .feed-row-visuals {
            grid-column: 1 / -1;
            flex-direction: row !important;
            justify-content: center;
        }
    }

    </style>
    """,
        unsafe_allow_html=True,
    )





def build_card_html(item: dict) -> str:
    """Build the full collapsed-card HTML for a feed item.

    Sprint 015: Two-column CSS Grid layout (text left, visuals right).
    Prediction details below fold in <details>. Info icon as <details> in upper-right.
    Returns a single HTML string to be rendered via st.markdown(unsafe_allow_html=True).
    All user strings are HTML-escaped.
    """
    parts = []

    # --- Finish type accent color ---
    ft = item.get("predicted_finish_type") or "unknown"
    accent_color = FINISH_TYPE_COLORS.get(ft, "#9E9E9E")
    ft_icon = FINISH_TYPE_ICONS.get(ft, FINISH_TYPE_ICONS.get("unknown", ""))
    ft_icon_20 = ft_icon.replace('width="24"', 'width="20"').replace('height="24"', 'height="20"')

    # --- Build right-column visuals ---
    sparkline_html = ""
    route_html = ""

    profile_points = item.get("elevation_sparkline_points")
    if profile_points:
        sparkline_html = render_elevation_sparkline_svg(profile_points)

    encoded_poly = item.get("rwgps_encoded_polyline")
    if encoded_poly:
        route_html = render_route_trace_svg(encoded_poly)

    has_visuals = bool(sparkline_html or route_html)

    # --- Grid template: two-column if visuals, single if not ---
    if has_visuals:
        grid_cols = "grid-template-columns:1fr auto;"
    else:
        grid_cols = "grid-template-columns:1fr;"

    parts.append(
        f'<div class="feed-card-inner" style="position:relative;border-left:4px solid '
        f'{accent_color};padding-left:12px;display:grid;{grid_cols}gap:12px;">'
    )

    # === LEFT COLUMN ===
    parts.append('<div class="feed-card-left">')

    # --- Row 1: Name + countdown pill inline (CL-02) ---
    name = html.escape(str(item.get("display_name", "")))
    countdown_pill = ""
    if item.get("is_upcoming") and item.get("upcoming_date"):
        pill_label, pill_bg, pill_text = countdown_pill_style(item.get("days_until"))
        if pill_label:
            countdown_pill = (
                f'<span class="feed-card-date-pill" '
                f'style="background:{pill_bg};color:{pill_text};'
                f'padding:2px 8px;border-radius:12px;'
                f'font-size:0.8em;font-weight:500;'
                f'white-space:nowrap;margin-left:6px;">{html.escape(pill_label)}</span>'
            )
        else:
            try:
                date_str = html.escape(f"{item['upcoming_date']:%b %d, %Y}")
                countdown_pill = (
                    f'<span style="color:var(--text-color,#666);'
                    f'font-size:0.85em;margin-left:6px;">{date_str}</span>'
                )
            except (TypeError, ValueError):
                pass
    elif item.get("most_recent_date"):
        try:
            date_str = html.escape(f"last raced {item['most_recent_date']:%b %Y}")
            countdown_pill = (
                f'<span style="color:var(--text-color,#888);'
                f'font-size:0.8em;margin-left:6px;">{date_str}</span>'
            )
        except (TypeError, ValueError):
            pass

    parts.append(
        f'<div style="display:flex;align-items:baseline;gap:4px;flex-wrap:wrap;'
        f'max-width:calc(100% - 30px);">'
        f'<span style="font-weight:700;font-size:1.3em;line-height:1.2;'
        f'overflow:hidden;text-overflow:ellipsis;">{name}</span>'
        f'{countdown_pill}'
        f'</div>'
    )

    # --- Row 2: Location ---
    loc_parts = []
    if item.get("location"):
        loc_parts.append(html.escape(str(item["location"])))
    state = item.get("state_province", "")
    if state and state not in item.get("location", ""):
        loc_parts.append(html.escape(str(state)))
    loc_str = ", ".join(loc_parts) if loc_parts else ""

    race_type = item.get("race_type")
    rt_badge = ""
    if race_type:
        rt_icon = RACE_TYPE_ICONS.get(race_type, "")
        rt_name = html.escape(RACE_TYPE_DISPLAY.get(race_type, race_type.replace("_", " ").title()))
        rt_badge = (
            f'<span style="display:inline-flex;align-items:center;gap:3px;'
            f'background:var(--secondary-background-color,#f0f2f6);padding:1px 8px;'
            f'border-radius:4px;font-size:0.8em;'
            f'color:var(--text-color,#333);">'
            f'{rt_icon} {rt_name}</span>'
        )

    if loc_str:
        parts.append(
            f'<div style="margin-top:2px;'
            f'font-size:0.85em;color:var(--text-color,#666);">'
            f'{loc_str}'
            f'</div>'
        )
    if rt_badge:
        parts.append(
            f'<div style="margin-top:3px;">'
            f'{rt_badge}'
            f'</div>'
        )

    # --- Teammate presence accent ---
    teammates = item.get("teammate_names", [])
    if teammates:
        team_icon = (
            '<svg width="16" height="16" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg"'
            ' style="vertical-align:middle;">'
            '<circle cx="6" cy="6" r="3" fill="#FF6F00"/>'
            '<circle cx="11" cy="6" r="3" fill="#FF6F00" opacity="0.7"/>'
            '<path d="M1 14 Q3 10 6 10 Q8 10 9 11 Q10 10 11 10 '
            'Q14 10 15 14" fill="#FF6F00" opacity="0.3"/>'
            "</svg>"
        )
        if len(teammates) <= 2:
            names = ", ".join(html.escape(n) for n in teammates)
            team_text = f"{names} registered"
        elif len(teammates) <= 4:
            first_two = ", ".join(html.escape(n) for n in teammates[:2])
            team_text = (
                f"{first_two} + {len(teammates) - 2} more registered"
            )
        else:
            first_two = ", ".join(html.escape(n) for n in teammates[:2])
            team_text = (
                f"{first_two} + {len(teammates) - 2} more registered"
            )
        parts.append(
            '<div class="feed-card-teammate" '
            'style="display:inline-flex;align-items:center;'
            'gap:4px;margin-top:4px;padding:2px 8px;'
            'border-radius:4px;font-size:0.8em;'
            f'background:rgba(255,111,0,0.08);color:#E65100;">'
            f'{team_icon} {team_text}'
            f'</div>'
        )

    # --- Chip row ---
    chips = _build_chip_row(item)
    if chips:
        parts.append(
            '<div class="feed-card-chips" style="display:flex;flex-wrap:wrap;gap:6px;'
            'margin-top:6px;font-size:0.82em;">'
            + "".join(chips)
            + "</div>"
        )

    # --- Drop rate meter ---
    drop_pct = item.get("drop_rate_pct")
    if drop_pct is not None:
        bar_color = _drop_rate_color(drop_pct)
        drop_label = item.get("drop_rate_label", "")
        bar_bg = (
            "#E8F5E9"
            if drop_pct < 15
            else "var(--secondary-background-color,#e0e0e0)"
        )
        parts.append(
            '<div style="margin-top:6px;display:flex;align-items:center;'
            'gap:6px;">'
            '<span style="font-size:0.78em;'
            'color:var(--text-color,#666);min-width:70px;">'
            'Drop rate</span>'
            '<div style="flex:1;max-width:120px;height:8px;'
            f'background:{bar_bg};'
            'border-radius:4px;overflow:hidden;">'
            f'<div style="width:{min(drop_pct, 100)}%;height:100%;'
            f'background:{bar_color};'
            'border-radius:4px;"></div></div>'
            f'<span style="font-size:0.78em;font-weight:500;">'
            f'{drop_pct}%</span>'
            '<span style="font-size:0.72em;'
            f'color:var(--text-color,#888);">'
            f'({html.escape(drop_label)})</span>'
            '</div>'
        )

    # --- "What to expect" one-liner stays above the fold ---
    wte = what_to_expect_text(
        ft if ft != "unknown" else None,
        prediction_source=item.get("prediction_source"),
        race_type=race_type,
    )
    if wte:
        parts.append(
            f'<div class="feed-card-prediction" style="margin-top:6px;font-weight:500;'
            f'font-size:0.92em;display:flex;align-items:center;gap:6px;">'
            f'{ft_icon_20}'
            f'<span style="color:var(--text-color,#888);font-weight:400;'
            f'font-size:0.85em;">AI sez:</span> '
            f'<span>{html.escape(wte)}</span>'
            f'</div>'
        )

    parts.append('</div>')  # close feed-card-left

    # === RIGHT COLUMN (CL-01, CL-04) ===
    if has_visuals:
        parts.append(
            '<div class="feed-card-right" style="min-width:130px;display:flex;'
            'flex-direction:column;align-items:center;gap:6px;'
            'justify-content:center;">'
        )
        if route_html:
            parts.append(f'<div>{route_html}</div>')
        if sparkline_html:
            parts.append(f'<div>{sparkline_html}</div>')
        parts.append('</div>')  # close feed-card-right

    parts.append('</div>')  # close feed-card-inner (grid)

    return "\n".join(parts)


def build_row_html(item: dict) -> str:
    """Build a single-column agenda row for a feed item (Sprint 019).

    Three-column CSS Grid: date | text | visuals.
    Visuals column omitted when neither course map nor elevation exists.
    All user strings are HTML-escaped.
    """
    parts = []

    # --- Finish type accent color ---
    ft = item.get("predicted_finish_type") or "unknown"
    accent_color = FINISH_TYPE_COLORS.get(ft, "#9E9E9E")
    ft_icon = FINISH_TYPE_ICONS.get(ft, FINISH_TYPE_ICONS.get("unknown", ""))
    ft_icon_20 = ft_icon.replace('width="24"', 'width="20"').replace(
        'height="24"', 'height="20"'
    )

    # --- Build visuals ---
    sparkline_html = ""
    route_html = ""

    profile_points = item.get("elevation_sparkline_points")
    if profile_points:
        sparkline_html = render_elevation_sparkline_svg(profile_points)

    encoded_poly = item.get("rwgps_encoded_polyline")
    if encoded_poly:
        route_html = render_route_trace_svg(encoded_poly)

    has_visuals = bool(sparkline_html or route_html)

    # --- Grid template: three-column if visuals, two-column if not ---
    if has_visuals:
        grid_cols = "grid-template-columns:72px minmax(0,1fr) 168px;"
    else:
        grid_cols = "grid-template-columns:72px 1fr;"

    parts.append(
        f'<div class="feed-row" style="display:grid;{grid_cols}gap:14px;'
        f'align-items:center;border-left:4px solid {accent_color};'
        f'padding-left:12px;padding-bottom:8px;">'
    )

    # === DATE COLUMN ===
    date_obj = item.get("upcoming_date") or item.get("most_recent_date")
    date_opacity = ""
    if not item.get("is_upcoming") and item.get("most_recent_date"):
        date_opacity = "opacity:0.45;"

    month_str = ""
    day_str = ""
    if date_obj:
        try:
            month_str = html.escape(f"{date_obj:%b}".upper())
            day_str = html.escape(f"{date_obj.day}")
        except (TypeError, ValueError, AttributeError):
            pass

    parts.append(
        f'<div class="feed-row-date" style="text-align:center;{date_opacity}">'
        f'<div class="feed-row-month" style="font-size:0.75em;font-weight:600;'
        f'text-transform:uppercase;line-height:1.1;'
        f'color:color-mix(in srgb, var(--text-color) 55%, transparent);">'
        f'{month_str}</div>'
        f'<div class="feed-row-day" style="font-size:1.9em;font-weight:700;'
        f'line-height:1.1;'
        f'color:color-mix(in srgb, var(--text-color) 55%, transparent);">'
        f'{day_str}</div>'
        f'</div>'
    )

    # === TEXT COLUMN ===
    parts.append('<div class="feed-row-main" style="min-width:0;">')

    # --- Title + countdown pill ---
    name = html.escape(str(item.get("display_name", "")))
    countdown_pill = ""
    if item.get("is_upcoming") and item.get("upcoming_date"):
        pill_label, pill_bg, pill_text = countdown_pill_style(item.get("days_until"))
        if pill_label:
            countdown_pill = (
                f'<span class="feed-card-date-pill" '
                f'style="background:{pill_bg};color:{pill_text};'
                f'padding:2px 8px;border-radius:12px;'
                f'font-size:0.8em;font-weight:500;'
                f'white-space:nowrap;margin-left:6px;">'
                f'{html.escape(pill_label)}</span>'
            )

    parts.append(
        f'<div style="display:flex;align-items:baseline;gap:4px;flex-wrap:wrap;">'
        f'<span style="font-weight:700;font-size:1.3em;line-height:1.2;'
        f'overflow:hidden;text-overflow:ellipsis;">{name}</span>'
        f'{countdown_pill}'
        f'</div>'
    )

    # --- Location ---
    loc_parts = []
    if item.get("location"):
        loc_parts.append(html.escape(str(item["location"])))
    state = item.get("state_province", "")
    if state and state not in item.get("location", ""):
        loc_parts.append(html.escape(str(state)))
    loc_str = ", ".join(loc_parts) if loc_parts else ""

    if loc_str:
        parts.append(
            f'<div style="font-size:0.85em;color:var(--text-color,#666);">'
            f'{loc_str}</div>'
        )

    # --- Race type badge ---
    race_type = item.get("race_type")
    if race_type:
        rt_icon = RACE_TYPE_ICONS.get(race_type, "")
        rt_name = html.escape(
            RACE_TYPE_DISPLAY.get(race_type, race_type.replace("_", " ").title())
        )
        parts.append(
            f'<div style="margin-top:2px;">'
            f'<span style="display:inline-flex;align-items:center;gap:3px;'
            f'background:var(--secondary-background-color,#f0f2f6);padding:1px 8px;'
            f'border-radius:4px;font-size:0.8em;'
            f'color:var(--text-color,#333);">'
            f'{rt_icon} {rt_name}</span></div>'
        )

    # --- AI sez (moved up, under location, larger) ---
    ai_sez_text = ""
    ai_context = item.get("ai_context")
    if ai_context and ai_context.get("ai_sez_text"):
        ai_sez_text = ai_context["ai_sez_text"]
    else:
        # Fallback to legacy what_to_expect_text
        wte = what_to_expect_text(
            ft if ft != "unknown" else None,
            prediction_source=item.get("prediction_source"),
            race_type=race_type,
        )
        ai_sez_text = wte

    if ai_sez_text:
        parts.append(
            f'<div class="feed-row-ai" style="margin-top:10px;font-weight:500;'
            f'font-size:1.0rem;display:flex;align-items:center;gap:6px;">'
            f'{ft_icon_20}'
            f'<span style="color:var(--text-color,#888);font-weight:400;'
            f'font-size:0.85em;">AI sez:</span> '
            f'<span>{html.escape(ai_sez_text)}</span>'
            f'</div>'
        )

    # --- Teammate presence accent ---
    teammates = item.get("teammate_names", [])
    if teammates:
        team_icon = (
            '<svg width="16" height="16" viewBox="0 0 16 16"'
            ' xmlns="http://www.w3.org/2000/svg" style="vertical-align:middle;">'
            '<circle cx="6" cy="6" r="3" fill="#FF6F00"/>'
            '<circle cx="11" cy="6" r="3" fill="#FF6F00" opacity="0.7"/>'
            '<path d="M1 14 Q3 10 6 10 Q8 10 9 11 Q10 10 11 10 '
            'Q14 10 15 14" fill="#FF6F00" opacity="0.3"/>'
            "</svg>"
        )
        if len(teammates) <= 2:
            names = ", ".join(html.escape(n) for n in teammates)
            team_text = f"{names} registered"
        else:
            first_two = ", ".join(html.escape(n) for n in teammates[:2])
            team_text = f"{first_two} + {len(teammates) - 2} more registered"
        parts.append(
            '<div class="feed-card-teammate" '
            'style="display:inline-flex;align-items:center;'
            'gap:4px;margin-top:4px;padding:2px 8px;'
            'border-radius:4px;font-size:0.8em;'
            f'background:rgba(255,111,0,0.08);color:#E65100;">'
            f'{team_icon} {team_text}'
            f'</div>'
        )

    # --- Chip row ---
    chips = _build_chip_row(item)
    if chips:
        parts.append(
            '<div class="feed-card-chips" style="display:flex;flex-wrap:wrap;gap:6px;'
            'margin-top:10px;font-size:0.82em;">'
            + "".join(chips)
            + "</div>"
        )

    # --- Drop rate meter ---
    drop_pct = item.get("drop_rate_pct")
    if drop_pct is not None:
        bar_color = _drop_rate_color(drop_pct)
        drop_label = item.get("drop_rate_label", "")
        bar_bg = (
            "#E8F5E9"
            if drop_pct < 15
            else "var(--secondary-background-color,#e0e0e0)"
        )
        parts.append(
            '<div style="margin-top:10px;display:flex;align-items:center;'
            'gap:6px;">'
            '<span style="font-size:0.78em;'
            'color:var(--text-color,#666);min-width:70px;">'
            'Drop rate</span>'
            '<div style="flex:1;max-width:120px;height:8px;'
            f'background:{bar_bg};'
            'border-radius:4px;overflow:hidden;">'
            f'<div style="width:{min(drop_pct, 100)}%;height:100%;'
            f'background:{bar_color};'
            'border-radius:4px;"></div></div>'
            f'<span style="font-size:0.78em;font-weight:500;">'
            f'{drop_pct}%</span>'
            '<span style="font-size:0.72em;'
            f'color:var(--text-color,#888);">'
            f'({html.escape(drop_label)})</span>'
            '</div>'
        )

    parts.append('</div>')  # close feed-row-main

    # === VISUALS COLUMN ===
    if has_visuals:
        parts.append(
            '<div class="feed-row-visuals" style="min-width:168px;display:flex;'
            'flex-direction:column;align-items:center;gap:6px;'
            'justify-content:center;">'
        )
        if route_html:
            parts.append(f'<div>{route_html}</div>')
        if sparkline_html:
            parts.append(f'<div>{sparkline_html}</div>')
        parts.append('</div>')  # close feed-row-visuals

    parts.append('</div>')  # close feed-row

    return "\n".join(parts)


def _build_chip_row(item: dict) -> list[str]:
    """Build the list of chip HTML strings for a feed card."""
    chips = []
    is_upcoming = item.get("is_upcoming", False)

    _DIST_ICON = (
        '<svg width="14" height="14" viewBox="0 0 14 14">'
        '<line x1="1" y1="7" x2="13" y2="7"'
        ' stroke="currentColor" stroke-width="1.5"/>'
        '<line x1="1" y1="5" x2="1" y2="9"'
        ' stroke="currentColor" stroke-width="1.5"/>'
        '<line x1="13" y1="5" x2="13" y2="9"'
        ' stroke="currentColor" stroke-width="1.5"/></svg>'
    )
    # Sprint 020: Always show cross-field range, then Course.distance_m fallback
    dist_range = item.get("distance_range")
    if dist_range:
        chips.append(_chip("distance", _DIST_ICON, html.escape(dist_range)))
    elif item.get("distance_m") is not None:
        km = item["distance_m"] / 1000
        chips.append(_chip("distance", _DIST_ICON, f"{km:.0f} km"))
    elif is_upcoming:
        chips.append(
            '<span class="feed-card-chip" style="opacity:0.5;'
            'display:inline-flex;align-items:center;gap:3px;'
            'background:var(--secondary-background-color,#f0f2f6);'
            'padding:2px 8px;border-radius:4px;'
            'color:var(--text-color,#444);">'
            '\U0001f4cf -- km</span>'
        )

    _ELEV_ICON = (
        '<svg width="14" height="14" viewBox="0 0 14 14">'
        '<path d="M1 12 L7 3 L13 12"'
        ' fill="none" stroke="currentColor" stroke-width="1.5"'
        ' stroke-linejoin="round"/></svg>'
    )
    if item.get("total_gain_m") is not None:
        chips.append(
            _chip("elevation", _ELEV_ICON, f"{item['total_gain_m']:.0f}m")
        )
    elif is_upcoming:
        chips.append(
            '<span class="feed-card-chip" style="opacity:0.5;'
            'display:inline-flex;align-items:center;gap:3px;'
            'background:var(--secondary-background-color,#f0f2f6);'
            'padding:2px 8px;border-radius:4px;'
            'color:var(--text-color,#444);">'
            '\u26f0\ufe0f -- m \u2191</span>'
        )

    if item.get("course_type"):
        from raceanalyzer.elevation import course_type_display

        terrain = course_type_display(item["course_type"])
        chips.append(_chip(
            "terrain",
            '<svg width="14" height="14" viewBox="0 0 14 14">'
            '<path d="M1 11 Q4 5 7 8 Q10 11 13 5"'
            ' fill="none" stroke="currentColor"'
            ' stroke-width="1.5"/></svg>',
            html.escape(terrain),
        ))

    if item.get("field_size_median"):
        fs_label = f"{item['field_size_median']} riders"
        chips.append(_chip(
            "field_size",
            '<svg width="14" height="14" viewBox="0 0 14 14">'
            '<circle cx="5" cy="5" r="2" fill="currentColor"/>'
            '<circle cx="10" cy="5" r="2" fill="currentColor"'
            ' opacity="0.6"/>'
            '<circle cx="7" cy="10" r="2" fill="currentColor"'
            ' opacity="0.4"/></svg>',
            fs_label,
        ))

    # Sprint 018: Hide estimated time for crits and duration-based races
    _DUR_ICON = (
        '<svg width="14" height="14" viewBox="0 0 14 14">'
        '<circle cx="7" cy="7" r="5.5"'
        ' fill="none" stroke="currentColor"'
        ' stroke-width="1.2"/>'
        '<line x1="7" y1="7" x2="7" y2="4"'
        ' stroke="currentColor" stroke-width="1.2"'
        ' stroke-linecap="round"/>'
        '<line x1="7" y1="7" x2="10" y2="7"'
        ' stroke="currentColor" stroke-width="1"'
        ' stroke-linecap="round"/></svg>'
    )
    if not item.get("hide_estimated_time"):
        est_range = item.get("estimated_time_range")
        dur_text = est_range or format_duration(item.get("typical_field_duration_min"))
        if dur_text:
            chips.append(_chip("duration", _DUR_ICON, html.escape(dur_text)))
        elif is_upcoming:
            chips.append(
                '<span class="feed-card-chip" style="opacity:0.5;'
                'display:inline-flex;align-items:center;gap:3px;'
                'background:var(--secondary-background-color,#f0f2f6);'
                'padding:2px 8px;border-radius:4px;'
                'color:var(--text-color,#444);">'
                '\U0001f550 ~? min</span>'
            )

    return chips


def _chip(chip_type: str, icon_svg: str, label: str) -> str:
    """Build a single stat chip with icon + label (no title tooltip)."""
    return (
        f'<span class="feed-card-chip"'
        f' style="display:inline-flex;align-items:center;gap:3px;'
        f'background:var(--secondary-background-color,#f0f2f6);'
        f'padding:2px 8px;'
        f'border-radius:4px;color:var(--text-color,#444);">'
        f'{icon_svg} {label}</span>'
    )


# ============================================================
# Card chip detection helper (Sprint 014: TT-01)
# ============================================================


def _card_has_chip(item: dict, chip_type: str) -> bool:
    """Return True if the given chip_type would be rendered for this item."""
    checks = {
        "distance": lambda i: i.get("distance_m") is not None,
        "elevation": lambda i: i.get("total_gain_m") is not None,
        "terrain": lambda i: bool(i.get("course_type")),
        "field_size": lambda i: bool(i.get("field_size_median")),
        "duration": lambda i: bool(
            format_duration(i.get("typical_field_duration_min"))
        ),
        "drop_rate": lambda i: i.get("drop_rate_pct") is not None,
        "finish_type": lambda i: bool(
            i.get("predicted_finish_type")
            and i["predicted_finish_type"] != "unknown"
        ),
        "climb": lambda i: bool(
            i.get("climb_highlight")
            or extract_key_climb(i.get("climbs_json"))
        ),
    }
    check = checks.get(chip_type)
    return check(item) if check else False


# ============================================================
# Share text generation (Sprint 014: SH-01)
# ============================================================


def generate_share_text(item: dict, category: Optional[str] = None) -> str:
    """Build a formatted share summary for a race card."""
    lines = []
    lines.append(item.get("display_name", ""))

    # Date + location line
    date_loc_parts = []
    if item.get("upcoming_date"):
        try:
            date_loc_parts.append(f"{item['upcoming_date']:%b %d, %Y}")
        except (TypeError, ValueError):
            pass
    loc = item.get("location", "")
    state = item.get("state_province", "")
    if loc and state:
        date_loc_parts.append(f"{loc}, {state}")
    elif loc:
        date_loc_parts.append(loc)
    if date_loc_parts:
        lines.append(" \u00b7 ".join(date_loc_parts))

    # What to expect
    ft = item.get("predicted_finish_type")
    wte = what_to_expect_text(
        ft if ft and ft != "unknown" else None,
        race_type=item.get("race_type"),
    )
    if wte:
        lines.append(wte)

    # Duration
    dur = format_duration(item.get("typical_field_duration_min"))
    if dur:
        lines.append(f"Duration: {dur}")

    # Deep link
    series_id = item.get("series_id")
    if series_id is not None:
        params = [f"series_id={series_id}"]
        if category:
            params.append(f"category={category}")
        lines.append(f"Link: ?{'&'.join(params)}")

    return "\n".join(lines)


# ============================================================
# ICS calendar export
# ============================================================


def generate_ics(
    race_name: str,
    start_date,
    location: str = "",
    duration_minutes: int = 120,
) -> str:
    """Generate a minimal ICS string for calendar export.

    Uses floating time (no timezone) for simplicity. Proper CRLF line endings.
    """
    from datetime import timedelta

    # Sanitize ICS fields: escape commas, semicolons, backslashes, newlines
    def _ics_escape(s: str) -> str:
        return (
            s.replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\n", "\\n")
        )

    name_safe = _ics_escape(race_name)
    loc_safe = _ics_escape(location)

    # Format dates
    try:
        dtstart = start_date.strftime("%Y%m%dT%H%M%S")
    except AttributeError:
        dtstart = start_date.strftime("%Y%m%dT080000") if hasattr(start_date, "strftime") else ""

    try:
        end = start_date + timedelta(minutes=duration_minutes)
        dtend = end.strftime("%Y%m%dT%H%M%S")
    except Exception:
        dtend = dtstart

    # Use start date as fallback for time
    if "T000000" in dtstart:
        dtstart = dtstart.replace("T000000", "T080000")
        end_h = 8 + duration_minutes // 60
        end_m = duration_minutes % 60
        dtend = dtend.replace(
            "T000000", f"T{end_h:02d}{end_m:02d}00"
        )

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//RaceAnalyzer//Race Calendar//EN",
        "BEGIN:VEVENT",
        f"DTSTART:{dtstart}",
        f"DTEND:{dtend}",
        f"SUMMARY:{name_safe}",
        f"LOCATION:{loc_safe}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"
