"""Server-side helpers for feed card rendering.

Pre-compute SVG strings, countdown pill styles, chip data, etc.
so that Jinja2 templates receive simple strings rather than doing
complex math in template logic.

All functions previously imported from raceanalyzer.ui.feed_card and
raceanalyzer.ui.components are inlined here so that this module has
NO transitive dependency on ``streamlit``.
"""
from __future__ import annotations

import html
import json
from datetime import timedelta
from typing import Optional

from raceanalyzer.web.filters import FINISH_TYPE_COLORS, is_metric

# ---------------------------------------------------------------------------
# FINISH_TYPE_ICONS  (originally raceanalyzer.ui.components)
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# RACE_TYPE_ICONS / RACE_TYPE_DISPLAY  (originally raceanalyzer.ui.feed_card)
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Drop rate color ramp
# ---------------------------------------------------------------------------

_DROP_RATE_COLORS = [
    (15, "#4CAF50"),   # green -- low
    (25, "#8BC34A"),   # light green
    (35, "#FFC107"),   # amber
    (45, "#FF9800"),   # orange
    (100, "#F44336"),  # red -- extreme
]


def _drop_rate_color(pct: float) -> str:
    for threshold, color in _DROP_RATE_COLORS:
        if pct <= threshold:
            return color
    return "#F44336"


# ---------------------------------------------------------------------------
# Countdown pill
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# What to expect text
# ---------------------------------------------------------------------------


def what_to_expect_text(
    finish_type: Optional[str],
    prediction_source: Optional[str] = None,
    race_type: Optional[str] = None,
) -> str:
    """Return a future-tense one-liner for the collapsed card."""
    from raceanalyzer.predictions import finish_type_teaser

    return finish_type_teaser(
        finish_type,
        prediction_source=prediction_source,
        race_type=race_type,
    )


# ---------------------------------------------------------------------------
# Elevation sparkline SVG
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Route trace SVG
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Distribution sparkline
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Duration format
# ---------------------------------------------------------------------------


def format_duration(minutes: Optional[float]) -> str:
    """Format minutes as '~Xh Ym'."""
    if not minutes or minutes <= 0:
        return ""
    hours = int(minutes) // 60
    mins = int(minutes) % 60
    if hours > 0:
        return f"~{hours}h {mins:02d}m"
    return f"~{mins}m"


# ---------------------------------------------------------------------------
# Key climb extract
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Chip row builder  (+ private _chip helper)
# ---------------------------------------------------------------------------


def _chip(chip_type: str, icon_svg: str, label: str) -> str:
    """Build a single stat chip with icon + label."""
    return (
        f'<span class="feed-card-chip"'
        f' style="display:inline-flex;align-items:center;gap:3px;'
        f'background:var(--secondary-background-color,#2d2d2d);'
        f'padding:2px 8px;'
        f'border-radius:4px;color:var(--text-color,#ccc);">'
        f'{icon_svg} {label}</span>'
    )


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
    # Distance: prefer registration data
    dist_range = item.get("distance_range")
    if dist_range:
        chips.append(_chip("distance", _DIST_ICON, html.escape(dist_range)))

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

    # Duration chip
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
                'background:var(--secondary-background-color,#2d2d2d);'
                'padding:2px 8px;border-radius:4px;'
                'color:var(--text-color,#ccc);">'
                '\U0001f550 ~? min</span>'
            )

    return chips


# ---------------------------------------------------------------------------
# ICS calendar export
# ---------------------------------------------------------------------------


def generate_ics(
    race_name: str,
    start_date,
    location: str = "",
    duration_minutes: int = 120,
) -> str:
    """Generate a minimal ICS string for calendar export.

    Uses floating time (no timezone) for simplicity. Proper CRLF line endings.
    """
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


# ===================================================================
# Template enrichment (the original purpose of this module)
# ===================================================================


def enrich_item_for_template(item: dict) -> dict:
    """Add pre-computed template-ready fields to a feed item dict.

    Mutates and returns the item for convenience.
    """
    # Finish type accent color and icon
    ft = item.get("predicted_finish_type") or "unknown"
    item["_accent_color"] = FINISH_TYPE_COLORS.get(ft, "#9E9E9E")
    ft_icon = FINISH_TYPE_ICONS.get(ft, FINISH_TYPE_ICONS.get("unknown", ""))
    item["_ft_icon_20"] = ft_icon.replace('width="24"', 'width="20"').replace(
        'height="24"', 'height="20"'
    )

    # SVG sparklines
    profile_points = item.get("elevation_sparkline_points")
    item["_sparkline_svg"] = render_elevation_sparkline_svg(profile_points) if profile_points else ""

    encoded_poly = item.get("rwgps_encoded_polyline")
    item["_route_svg"] = render_route_trace_svg(encoded_poly) if encoded_poly else ""

    item["_has_visuals"] = bool(item["_sparkline_svg"] or item["_route_svg"])

    # Distribution sparkline
    item["_distribution_svg"] = render_distribution_sparkline(
        item.get("distribution_json")
    )

    # Countdown pill
    days = item.get("days_until")
    pill_label, pill_bg, pill_text = countdown_pill_style(days)
    item["_pill_label"] = pill_label
    item["_pill_bg"] = pill_bg
    item["_pill_text"] = pill_text

    # Date display
    date_obj = item.get("upcoming_date") or item.get("most_recent_date")
    item["_date_obj"] = date_obj
    if date_obj:
        try:
            item["_month_str"] = f"{date_obj:%b}".upper()
            item["_day_str"] = str(date_obj.day)
        except (TypeError, ValueError, AttributeError):
            item["_month_str"] = ""
            item["_day_str"] = ""
    else:
        item["_month_str"] = ""
        item["_day_str"] = ""

    # Date opacity for past races
    item["_date_dim"] = not item.get("is_upcoming") and item.get("most_recent_date")

    # Location string
    loc_parts = []
    if item.get("location"):
        loc_parts.append(str(item["location"]))
    state = item.get("state_province", "")
    if state and state not in item.get("location", ""):
        loc_parts.append(str(state))
    item["_location_str"] = ", ".join(loc_parts) if loc_parts else ""

    # Race type badge
    race_type = item.get("race_type")
    if race_type:
        item["_rt_icon"] = RACE_TYPE_ICONS.get(race_type, "")
        item["_rt_name"] = RACE_TYPE_DISPLAY.get(
            race_type, race_type.replace("_", " ").title()
        )
    else:
        item["_rt_icon"] = ""
        item["_rt_name"] = ""

    # AI sez text
    ai_context = item.get("ai_context")
    if ai_context and ai_context.get("ai_sez_text"):
        item["_ai_sez"] = ai_context["ai_sez_text"]
    else:
        item["_ai_sez"] = what_to_expect_text(
            ft if ft != "unknown" else None,
            prediction_source=item.get("prediction_source"),
            race_type=race_type,
        )

    # Chip row (pre-built HTML strings)
    item["_chips"] = _build_chip_row(item)

    # Drop rate meter
    drop_pct = item.get("drop_rate_pct")
    if drop_pct is not None:
        item["_drop_color"] = _drop_rate_color(drop_pct)
        item["_drop_width"] = min(drop_pct, 100)
    else:
        item["_drop_color"] = ""
        item["_drop_width"] = 0

    # Teammate display
    teammates = item.get("teammate_names", [])
    if teammates:
        if len(teammates) <= 2:
            item["_team_text"] = ", ".join(teammates) + " registered"
        else:
            item["_team_text"] = (
                ", ".join(teammates[:2]) + f" + {len(teammates) - 2} more registered"
            )
    else:
        item["_team_text"] = ""

    # Key climb
    item["_key_climb"] = extract_key_climb(item.get("climbs_json"))

    # Metric flag
    item["_is_metric"] = is_metric(item)

    return item


def enrich_items(items: list[dict]) -> list[dict]:
    """Enrich all items in a list for template rendering."""
    for item in items:
        enrich_item_for_template(item)
        # Also enrich child stages if present
        for stage in item.get("stages", []):
            enrich_item_for_template(stage)
    return items
