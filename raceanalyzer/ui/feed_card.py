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
    return (f"in {weeks} weeks", "var(--secondary-background-color, #f0f2f6)", "inherit")


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
    """Return a future-tense one-liner (<=120 chars) for the collapsed card."""
    if not finish_type or finish_type == "unknown":
        if race_type == "criterium":
            return "Fast laps on a short circuit — expect close racing"
        if race_type == "time_trial":
            return "Solo effort against the clock"
        return ""

    lines = {
        "bunch_sprint": "The group will stay together for a field sprint",
        "small_group_sprint": "A select group will contest the sprint",
        "breakaway": "An early move will likely stay away",
        "breakaway_selective": "The climbs will shatter the field — only the strong survive",
        "reduced_sprint": "Attrition will thin the pack before a reduced sprint",
        "gc_selective": "Expect a war of attrition on the hardest terrain",
        "individual_tt": "Solo effort against the clock",
        "mixed": "This race could go several ways — come prepared for anything",
    }
    return lines.get(finish_type, "")


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


def is_beginner_friendly(item: dict) -> tuple[bool, list[str]]:
    """Determine if a race is beginner-friendly. Returns (bool, reasons[])."""
    reasons = []
    drop_rate = item.get("drop_rate_pct")
    finish_type = item.get("predicted_finish_type")
    distance_m = item.get("distance_m")

    # Drop rate check
    if drop_rate is not None and drop_rate <= 25:
        reasons.append("Low drop rate")
    elif drop_rate is not None and drop_rate > 25:
        return (False, [])

    # Non-selective finish types
    non_selective = {
        "bunch_sprint", "small_group_sprint", "reduced_sprint", "mixed", "individual_tt"
    }
    if finish_type and finish_type in non_selective:
        reasons.append("Non-selective finish")
    elif finish_type and finish_type not in non_selective:
        return (False, [])

    # Moderate distance (under 100 km)
    if distance_m is not None and distance_m <= 100_000:
        reasons.append("Moderate distance")
    elif distance_m is not None and distance_m > 100_000:
        return (False, [])

    # Need at least one positive signal
    if reasons:
        return (True, reasons)
    return (False, [])


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
    profile_points: list, width: int = 140, height: int = 30
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
    encoded_polyline: Optional[str], width: int = 120, height: int = 60
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
    """Inject CSS styles for feed cards. Call once at top of render."""
    import streamlit as st

    st.markdown(
        """
    <style>
    /* Feed card v2 styles (Sprint 013) */

    /* Card press micro-animation (VD-02) */
    div[data-testid="stVerticalBlock"] > div:has(.feed-card-inner) {
        transition: transform 150ms ease, opacity 150ms ease;
    }
    div[data-testid="stVerticalBlock"] > div:has(.feed-card-inner):active {
        transform: scale(0.98);
        opacity: 0.9;
    }

    /* Prediction highlight glow (VD-09) */
    .feed-card-prediction {
        animation: feed-pred-glow 1.5s ease-out;
    }
    @keyframes feed-pred-glow {
        0% { background: rgba(255, 193, 7, 0.15); }
        100% { background: transparent; }
    }

    /* Chip icon sizing (Sprint 014: VR-01, 14->16) */
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

    /* Beginner-friendly badge */
    .feed-card-beginner {
        animation: feed-beginner-pop 0.3s ease-out;
    }
    @keyframes feed-beginner-pop {
        0% { transform: scale(0.9); opacity: 0.5; }
        100% { transform: scale(1); opacity: 1; }
    }

    /* Dark mode surface differentiation (VD-05) */
    @media (prefers-color-scheme: dark) {
        .feed-card-inner {
            color: var(--text-color, #e0e0e0);
        }
        .feed-card-chip {
            background: var(--secondary-background-color, #2d2d2d) !important;
            color: var(--text-color, #e0e0e0) !important;
        }
        .feed-card-date-pill {
            box-shadow: 0 1px 3px rgba(0,0,0,0.3);
        }
    }

    /* Expand/collapse transition (VD-08) */
    div[data-testid="stExpander"] {
        transition: max-height 300ms ease, opacity 200ms ease;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )





def build_card_html(item: dict) -> str:
    """Build the full collapsed-card HTML for a feed item.

    Returns a single HTML string to be rendered via st.markdown(unsafe_allow_html=True).
    All user strings are HTML-escaped.
    """
    parts = []

    # --- Finish type accent color ---
    ft = item.get("predicted_finish_type") or "unknown"
    accent_color = FINISH_TYPE_COLORS.get(ft, "#9E9E9E")
    ft_icon = FINISH_TYPE_ICONS.get(ft, FINISH_TYPE_ICONS.get("unknown", ""))
    # Scale icon to 20x20
    ft_icon_20 = ft_icon.replace('width="24"', 'width="20"').replace('height="24"', 'height="20"')

    parts.append(
        f'<div class="feed-card-inner" style="border-left:4px solid '
        f'{accent_color};padding-left:12px;">'
    )

    # --- Row 1: Name + Date pill ---
    name = html.escape(str(item.get("display_name", "")))
    date_pill = ""
    if item.get("is_upcoming") and item.get("upcoming_date"):
        try:
            date_str = html.escape(f"{item['upcoming_date']:%b %d, %Y}")
        except (TypeError, ValueError):
            date_str = ""
        if date_str:
            pill_label, pill_bg, pill_text = countdown_pill_style(item.get("days_until"))
            if pill_label:
                date_pill = (
                    f'<span class="feed-card-date-pill" '
                    f'style="background:{pill_bg};color:{pill_text};'
                    f'padding:2px 8px;border-radius:12px;'
                    f'font-size:0.8em;font-weight:500;'
                    f'white-space:nowrap;">{html.escape(pill_label)}</span>'
                )
            else:
                date_pill = (
                    '<span style="color:var(--text-color,#666);'
                    f'font-size:0.85em;">{date_str}</span>'
                )
    elif item.get("most_recent_date"):
        try:
            date_str = html.escape(f"last raced {item['most_recent_date']:%b %Y}")
            date_pill = (
                '<span style="color:var(--text-color,#888);'
                f'font-size:0.8em;">{date_str}</span>'
            )
        except (TypeError, ValueError):
            pass

    parts.append(
        f'<div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px;'
        f'flex-wrap:wrap;">'
        f'<span style="font-weight:600;font-size:1.05em;">{name}</span>'
        f'{date_pill}'
        f'</div>'
    )

    # --- Registration urgency badge (VD-07) ---
    days = item.get("days_until")
    if item.get("is_upcoming") and days is not None and days <= 7:
        if days <= 3:
            urg_bg = "#D32F2F"
            urg_text = f"Race in {days} day{'s' if days != 1 else ''}!"
        else:
            urg_bg = "#F57C00"
            urg_text = f"Race in {days} days"
        parts.append(
            f'<div style="margin-top:2px;">'
            f'<span style="background:{urg_bg};color:#fff;'
            f'padding:1px 8px;border-radius:4px;'
            f'font-size:0.75em;font-weight:600;">'
            f'{html.escape(urg_text)}</span></div>'
        )

    # --- Row 2: Location + Race type badge ---
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
            f'border-radius:4px;font-size:0.8em;">'
            f'{rt_icon} {rt_name}</span>'
        )

    if loc_str or rt_badge:
        parts.append(
            f'<div style="display:flex;align-items:center;gap:8px;margin-top:2px;'
            f'font-size:0.85em;color:var(--text-color,#666);flex-wrap:wrap;">'
            f'{loc_str}'
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
        else:
            team_text = f"{len(teammates)} teammates registered"
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
    chips = []
    is_upcoming = item.get("is_upcoming", False)

    # Distance chip
    _DIST_ICON = (
        '<svg width="14" height="14" viewBox="0 0 14 14">'
        '<line x1="1" y1="7" x2="13" y2="7"'
        ' stroke="currentColor" stroke-width="1.5"/>'
        '<line x1="1" y1="5" x2="1" y2="9"'
        ' stroke="currentColor" stroke-width="1.5"/>'
        '<line x1="13" y1="5" x2="13" y2="9"'
        ' stroke="currentColor" stroke-width="1.5"/></svg>'
    )
    if item.get("distance_m") is not None:
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

    # Elevation chip
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

    # Terrain chip
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

    # Field size chip
    if item.get("field_size_median"):
        chips.append(_chip(
            "field_size",
            '<svg width="14" height="14" viewBox="0 0 14 14">'
            '<circle cx="5" cy="5" r="2" fill="currentColor"/>'
            '<circle cx="10" cy="5" r="2" fill="currentColor"'
            ' opacity="0.6"/>'
            '<circle cx="7" cy="10" r="2" fill="currentColor"'
            ' opacity="0.4"/></svg>',
            f"{item['field_size_median']} riders",
        ))

    # Duration chip
    dur_text = format_duration(
        item.get("typical_field_duration_min")
    )
    if dur_text:
        chips.append(_chip(
            "duration",
            '<svg width="14" height="14" viewBox="0 0 14 14">'
            '<circle cx="7" cy="7" r="5.5"'
            ' fill="none" stroke="currentColor"'
            ' stroke-width="1.2"/>'
            '<line x1="7" y1="7" x2="7" y2="4"'
            ' stroke="currentColor" stroke-width="1.2"'
            ' stroke-linecap="round"/>'
            '<line x1="7" y1="7" x2="10" y2="7"'
            ' stroke="currentColor" stroke-width="1"'
            ' stroke-linecap="round"/></svg>',
            dur_text,
        ))
    elif is_upcoming:
        chips.append(
            '<span class="feed-card-chip" style="opacity:0.5;'
            'display:inline-flex;align-items:center;gap:3px;'
            'background:var(--secondary-background-color,#f0f2f6);'
            'padding:2px 8px;border-radius:4px;'
            'color:var(--text-color,#444);">'
            '\U0001f550 ~? min</span>'
        )

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

    # --- Prediction section ---
    pred_parts_html = []

    # What to expect
    wte = what_to_expect_text(
        ft if ft != "unknown" else None,
        prediction_source=item.get("prediction_source"),
        race_type=race_type,
    )
    if wte:
        pred_parts_html.append(
            f'<div class="feed-card-prediction" style="margin-top:6px;font-weight:500;'
            f'font-size:0.92em;display:flex;align-items:center;gap:6px;">'
            f'{ft_icon_20}'
            f'<span>{html.escape(wte)}</span>'
            f'</div>'
        )

    # Confidence indicator
    conf = confidence_text(
        item.get("confidence"),
        item.get("edition_count", 0),
        prediction_source=item.get("prediction_source"),
    )
    if conf:
        pred_parts_html.append(
            f'<div style="font-size:0.75em;color:var(--text-color,#888);margin-top:2px;">'
            f'{html.escape(conf)}</div>'
        )

    # Pack survival odds
    survival = pack_survival_text(drop_pct, ft if ft != "unknown" else None)
    if survival:
        pred_parts_html.append(
            f'<div style="font-size:0.8em;color:var(--text-color,#666);margin-top:2px;">'
            f'{html.escape(survival)}</div>'
        )

    if pred_parts_html:
        parts.append("".join(pred_parts_html))

    # --- Beginner-friendly badge ---
    friendly, reasons = is_beginner_friendly(item)
    if friendly:
        parts.append(
            '<div style="margin-top:4px;">'
            '<span class="feed-card-beginner"'
            ' style="display:inline-block;background:#E8F5E9;'
            'color:#2E7D32;padding:2px 8px;border-radius:4px;'
            'font-size:0.78em;font-weight:500;">'
            '\u2705 Beginner-friendly</span></div>'
        )

    # --- Who does well here ---
    racer_label = racer_type_short_label(item.get("course_type"), ft if ft != "unknown" else None)
    if racer_label:
        parts.append(
            '<div style="font-size:0.78em;color:var(--text-color,#888);'
            f'margin-top:2px;">Suits: {html.escape(racer_label)}</div>'
        )

    # --- Climb highlight ---
    climb_text = item.get("climb_highlight") or extract_key_climb(item.get("climbs_json"))
    if climb_text:
        parts.append(
            '<div style="font-size:0.78em;color:var(--text-color,#666);'
            'margin-top:2px;display:flex;align-items:center;gap:4px;">'
            '<svg width="12" height="12" viewBox="0 0 12 12">'
            '<path d="M1 10 L6 2 L11 10"'
            ' fill="none" stroke="#F57C00" stroke-width="1.5"/></svg>'
            f'{html.escape(climb_text)}</div>'
        )

    # --- Bottom row: sparkline + route trace ---
    sparkline_html = ""
    route_html = ""
    dist_sparkline_html = ""

    profile_points = item.get("elevation_sparkline_points")
    if profile_points:
        sparkline_html = render_elevation_sparkline_svg(profile_points)

    encoded_poly = item.get("rwgps_encoded_polyline")
    if encoded_poly:
        route_html = render_route_trace_svg(encoded_poly)

    dist_json = item.get("distribution_json")
    if dist_json:
        dist_sparkline_html = render_distribution_sparkline(dist_json)

    visuals = [v for v in [sparkline_html, route_html, dist_sparkline_html] if v]
    if visuals:
        parts.append(
            '<div style="display:flex;gap:12px;align-items:center;'
            'margin-top:6px;flex-wrap:wrap;">'
            + "".join(f"<div>{v}</div>" for v in visuals)
            + "</div>"
        )

    parts.append("</div>")  # close feed-card-inner

    return "\n".join(parts)


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
