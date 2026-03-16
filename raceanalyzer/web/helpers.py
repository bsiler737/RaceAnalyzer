"""Server-side helpers for feed card rendering.

Pre-compute SVG strings, countdown pill styles, chip data, etc.
so that Jinja2 templates receive simple strings rather than doing
complex math in template logic.
"""
from __future__ import annotations

import html
import json
from typing import Optional

from raceanalyzer.ui.feed_card import (
    RACE_TYPE_ICONS,
    RACE_TYPE_DISPLAY,
    _DROP_RATE_COLORS,
    countdown_pill_style,
    format_duration,
    render_distribution_sparkline,
    render_elevation_sparkline_svg,
    render_route_trace_svg,
    what_to_expect_text,
    _build_chip_row,
    _drop_rate_color,
    extract_key_climb,
)
from raceanalyzer.ui.components import FINISH_TYPE_COLORS, FINISH_TYPE_ICONS
from raceanalyzer.web.filters import is_metric


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
