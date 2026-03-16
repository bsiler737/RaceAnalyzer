"""Jinja2 custom filters for RaceAnalyzer templates."""
from __future__ import annotations

from datetime import date, datetime

from raceanalyzer.queries import FINISH_TYPE_DISPLAY_NAMES

_CANADIAN_PROVINCES = {
    "BC", "AB", "SK", "MB", "ON", "QC", "NB", "NS", "PE", "NL", "YT", "NT", "NU",
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

RACE_TYPE_DISPLAY = {
    "criterium": "Criterium",
    "road_race": "Road Race",
    "hill_climb": "Hill Climb",
    "stage_race": "Stage Race",
    "time_trial": "Time Trial",
    "gravel": "Gravel",
    "unknown": "Unknown",
}


def is_metric(item: dict) -> bool:
    """Return True if the item's state/province is Canadian (metric units)."""
    sp = (item.get("state_province") or "").strip().upper().replace(".", "")
    if sp.startswith("US-"):
        return False
    return sp in _CANADIAN_PROVINCES


def format_distance(distance_m: float, metric: bool = False) -> str:
    """Format a distance in meters to km or mi."""
    if not distance_m:
        return ""
    if metric:
        km = distance_m / 1000
        return f"{km:.0f} km"
    else:
        mi = distance_m / 1609.34
        return f"{mi:.0f} mi"


def format_elevation(gain_m: float, metric: bool = False) -> str:
    """Format elevation gain in meters to m or ft."""
    if not gain_m:
        return ""
    if metric:
        return f"{gain_m:.0f}m"
    else:
        ft = gain_m * 3.28084
        return f"{ft:.0f} ft"


def finish_type_display(finish_type: str) -> str:
    """Convert finish type enum to human-readable name."""
    if not finish_type:
        return "Unknown"
    return FINISH_TYPE_DISPLAY_NAMES.get(
        finish_type, finish_type.replace("_", " ").title()
    )


def finish_type_color(finish_type: str) -> str:
    """Return the color hex code for a finish type."""
    if not finish_type:
        return FINISH_TYPE_COLORS["unknown"]
    return FINISH_TYPE_COLORS.get(finish_type, FINISH_TYPE_COLORS["unknown"])


def race_type_display(race_type: str) -> str:
    """Convert race type enum to human-readable name."""
    if not race_type:
        return "Unknown"
    return RACE_TYPE_DISPLAY.get(race_type, race_type.replace("_", " ").title())


def countdown_label(dt: str | date | datetime | None) -> str:
    """Return a human-readable countdown label relative to today."""
    if dt is None:
        return ""
    if isinstance(dt, str):
        try:
            dt = datetime.strptime(dt, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return ""
    if isinstance(dt, datetime):
        dt = dt.date()

    today = date.today()
    delta = (dt - today).days

    if delta == 0:
        return "Today"
    elif delta == 1:
        return "Tomorrow"
    elif delta > 1:
        return f"In {delta} days"
    elif delta == -1:
        return "1 day ago"
    else:
        return f"{abs(delta)} days ago"


def register_filters(env) -> None:
    """Register all custom filters on a Jinja2 Environment."""
    env.filters["is_metric"] = is_metric
    env.filters["format_distance"] = format_distance
    env.filters["format_elevation"] = format_elevation
    env.filters["finish_type_display"] = finish_type_display
    env.filters["finish_type_color"] = finish_type_color
    env.filters["race_type_display"] = race_type_display
    env.filters["countdown_label"] = countdown_label
