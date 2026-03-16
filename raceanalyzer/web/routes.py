"""Route handlers for RaceAnalyzer web app."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from raceanalyzer.db.engine import get_session

router = APIRouter()


def get_db():
    """Yield a SQLAlchemy session, closing it after the request."""
    db_path = Path(os.environ.get("RACEANALYZER_DB_PATH", "data/raceanalyzer.db"))
    session = get_session(db_path)
    try:
        yield session
    finally:
        session.close()


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _templates(request: Request):
    return request.app.state.templates


def _base_context(request: Request) -> dict:
    from raceanalyzer.web.app import base_context
    return base_context(request)


# ---------------------------------------------------------------------------
# Chart / map data builders (Plotly.js / Leaflet.js compatible JSON)
# ---------------------------------------------------------------------------

def build_elevation_chart_data(profile_points, climbs):
    """Return (traces_list, layout_dict) for Plotly.js elevation profile."""
    if not profile_points or len(profile_points) < 2:
        return [], {}

    distances = [p["d"] / 1000 for p in profile_points]
    elevations = [p["e"] for p in profile_points]

    min_e = min(elevations)
    max_e = max(elevations)
    e_range = max_e - min_e
    padding = max(e_range * 0.2, 5)
    y_min = max(0, min_e - padding)
    y_min = int(y_min // 10) * 10
    y_max = max_e + padding

    traces = [
        {
            "x": distances, "y": [y_min] * len(distances),
            "mode": "lines", "line": {"width": 0},
            "showlegend": False, "type": "scatter",
        },
        {
            "x": distances, "y": elevations,
            "mode": "lines", "fill": "tonexty",
            "fillcolor": "rgba(37, 99, 235, 0.12)",
            "line": {"color": "#2563EB", "width": 2},
            "name": "Elevation", "type": "scatter",
        },
    ]

    layout = {
        "xaxis": {"title": "Distance (km)"},
        "yaxis": {"title": "Elevation (m)", "range": [y_min, y_max]},
        "margin": {"l": 40, "r": 10, "t": 10, "b": 40},
        "height": 400,
        "showlegend": False,
        "plot_bgcolor": "rgba(0,0,0,0)",
        "paper_bgcolor": "rgba(0,0,0,0)",
    }

    shapes = []
    for climb in (climbs or []):
        shapes.append({
            "type": "rect",
            "x0": climb["start_d"] / 1000,
            "x1": climb["end_d"] / 1000,
            "y0": 0, "y1": 1,
            "yref": "paper",
            "fillcolor": climb.get("color", "#FFC107"),
            "opacity": 0.35,
            "line": {"width": 0},
        })
    if shapes:
        layout["shapes"] = shapes

    return traces, layout


def build_distribution_chart_data(distribution):
    """Return (traces_list, layout_dict) for finish type distribution bar chart."""
    if not distribution:
        return [], {}

    from raceanalyzer.queries import finish_type_display_name

    sorted_items = sorted(distribution.items(), key=lambda x: x[1])
    colors_map = {
        "bunch_sprint": "#2196F3", "small_group_sprint": "#03A9F4",
        "breakaway": "#FF9800", "breakaway_selective": "#FF5722",
        "reduced_sprint": "#4CAF50", "gc_selective": "#9C27B0",
        "individual_tt": "#00ACC1", "mixed": "#607D8B", "unknown": "#9E9E9E",
    }

    labels = [finish_type_display_name(k) for k, v in sorted_items]
    values = [v for k, v in sorted_items]
    colors = [colors_map.get(k, "#9E9E9E") for k, v in sorted_items]

    traces = [{
        "x": values, "y": labels,
        "orientation": "h", "type": "bar",
        "marker": {"color": colors},
        "text": values, "textposition": "outside",
    }]

    layout = {
        "showlegend": False,
        "yaxis": {"title": ""},
        "xaxis": {"title": "Count"},
        "margin": {"l": 120, "r": 40, "t": 20, "b": 40},
        "height": max(200, len(sorted_items) * 40),
        "plot_bgcolor": "rgba(0,0,0,0)",
        "paper_bgcolor": "rgba(0,0,0,0)",
    }

    return traces, layout


def build_map_data(profile_points, climbs):
    """Return (coords_list, climbs_with_coords) for Leaflet.js."""
    if not profile_points or len(profile_points) < 2:
        return [], []

    coords = [[p["y"], p["x"]] for p in profile_points]

    climb_data = []
    for climb in (climbs or []):
        start_d = climb.get("start_d", 0)
        end_d = climb.get("end_d", start_d)
        grade = climb.get("avg_grade", 0)
        segment = [
            [p["y"], p["x"]] for p in profile_points
            if start_d <= p.get("d", 0) <= end_d
        ]
        if len(segment) >= 2:
            climb_data.append({
                "coords": segment,
                "grade": grade,
                "name": f"Climb: {climb.get('length_m', 0)/1000:.1f}km at {grade:.1f}%",
            })

    return coords, climb_data


# ---------------------------------------------------------------------------
# Feed route
# ---------------------------------------------------------------------------

@router.get("/")
@router.get("/feed")
def feed(
    request: Request,
    series_id: Optional[int] = None,
    cat: Optional[str] = None,
    gender: Optional[str] = None,
    cat_level: Optional[int] = None,
    masters: Optional[int] = None,
    team: Optional[str] = None,
    q: Optional[str] = None,
    race_type: Optional[str] = None,
    states: Optional[str] = None,
    page: int = 1,
    session: Session = Depends(get_db),
):
    """Feed page -- list of upcoming races with filters."""
    from raceanalyzer import queries
    from raceanalyzer.web.helpers import enrich_items

    # Build filter params
    discipline_filter = None
    if race_type:
        discipline_filter = [rt.strip() for rt in race_type.split(",") if rt.strip()]

    state_filter = None
    if states:
        state_filter = [s.strip() for s in states.split(",") if s.strip()]

    items = queries.get_feed_items_batch(
        session,
        category=cat,
        search_query=q or None,
        discipline_filter=discipline_filter,
        state_filter=state_filter,
        team_name=team if team and len(team.strip()) >= 3 else None,
    )

    # Deep-link isolation
    if series_id:
        items = [i for i in items if i["series_id"] == series_id]

    # Group by month
    month_groups = queries.group_by_month(items)

    # Separate racing-soon items
    racing_soon = [
        i for i in items
        if i["is_upcoming"]
        and i.get("days_until") is not None
        and i["days_until"] <= 7
    ]

    # Enrich all items with pre-computed template fields
    enrich_items(items)
    # Also enrich month_groups (they reference the same dicts, but be safe)
    for _header, group_items in month_groups:
        enrich_items(group_items)

    # Available states for filter pills
    available_states = queries.get_available_states(session)

    # Pagination
    page_size = 20
    total_items = len(items)

    ctx_data = {
        "items": items,
        "racing_soon": racing_soon,
        "month_groups": month_groups,
        "series_id": series_id,
        "cat": cat,
        "gender": gender,
        "cat_level": cat_level,
        "masters": masters,
        "team": team or "",
        "q": q or "",
        "race_type": race_type or "",
        "states": states or "",
        "page": page,
        "page_size": page_size,
        "total_items": total_items,
        "available_states": available_states,
    }

    if _is_htmx(request):
        ctx_data["request"] = request
        return _templates(request).TemplateResponse(
            "partials/_feed_cards.html", ctx_data,
        )

    ctx = _base_context(request)
    ctx.update(ctx_data)
    return _templates(request).TemplateResponse("feed.html", ctx)


# ---------------------------------------------------------------------------
# Preview route
# ---------------------------------------------------------------------------

@router.get("/preview/{series_id}")
def preview(
    request: Request,
    series_id: int,
    cat: Optional[str] = None,
    field: Optional[str] = None,
    cat_level: Optional[int] = None,
    gender: Optional[str] = None,
    masters: Optional[int] = None,
    team: Optional[str] = None,
    session: Session = Depends(get_db),
):
    """Race preview page with full analysis for a series."""
    from raceanalyzer import queries
    from raceanalyzer.db.models import Race
    from raceanalyzer.elevation import COURSE_TYPE_DESCRIPTIONS, course_type_display
    from raceanalyzer.predictions import climb_context_line
    from raceanalyzer.queries import (
        deduplicate_field_names,
        finish_type_display_name,
        normalize_field_name,
    )
    from raceanalyzer.web.filters import is_metric

    # Initial fetch (no field filter) to get categories
    preview_data = queries.get_race_preview(
        session, series_id,
        category=cat,
        matched_categories=None,
        racer_profile_label="",
    )
    if preview_data is None:
        return Response(status_code=404)

    series = preview_data["series"]
    raw_categories = preview_data["categories"]

    # --- Smart field picker with deduplication ---
    chosen_field = field  # from query param
    canon_to_raws: dict[str, list[str]] = {}
    fields_list: list[str] = []
    query_category = None
    query_category_variants: list[str] = []

    if raw_categories:
        fields_list, canon_to_raws = deduplicate_field_names(raw_categories)

        # If a field was specified, resolve it
        if chosen_field and chosen_field in canon_to_raws:
            query_category_variants = list(canon_to_raws[chosen_field])
            query_category = query_category_variants[0]

            # Pick the variant with actual predictions
            from raceanalyzer.db.models import SeriesPrediction
            for variant in query_category_variants:
                has_pred = (
                    session.query(SeriesPrediction)
                    .filter(
                        SeriesPrediction.series_id == series_id,
                        SeriesPrediction.category == variant,
                    )
                    .first()
                )
                if has_pred:
                    query_category = variant
                    break

        elif len(fields_list) == 1:
            # Single field: auto-select
            chosen_field = fields_list[0]
            query_category_variants = list(canon_to_raws[chosen_field])
            query_category = query_category_variants[0]

    # Re-fetch with specific field if chosen
    if query_category:
        preview_data = queries.get_race_preview(
            session, series_id,
            category=query_category,
            matched_categories=None,
            racer_profile_label="",
        )
        if preview_data is None:
            return Response(status_code=404)

    is_field_mode = chosen_field is not None

    # --- Extract preview data ---
    profile_points = preview_data.get("profile_points")
    climbs = preview_data.get("climbs")
    pred = preview_data.get("prediction")
    course = preview_data.get("course")
    drop_rate = preview_data.get("drop_rate")
    typical_speed = preview_data.get("typical_speed")
    narrative = preview_data.get("narrative", "")
    ai_context = preview_data.get("ai_context", {})
    field_forecasts = preview_data.get("field_forecasts", [])
    cat_distance = preview_data.get("category_distance")
    cat_distance_unit = preview_data.get("category_distance_unit")
    distance_range = preview_data.get("distance_range")
    preview_race_type = preview_data.get("race_type")
    is_tt = preview_race_type == "time_trial"
    reg_url = preview_data.get("registration_url")
    state_province = preview_data.get("state_province")
    startlist_source_id = preview_data.get("startlist_source_id", series_id)

    pred_ft = pred["predicted_finish_type"] if pred else None

    # Unit system
    _metric = is_metric({"state_province": state_province or ""})

    def _fmt_dist(m):
        if _metric:
            return f"{m/1000:.1f} km"
        return f"{m/1609.34:.1f} mi"

    def _fmt_elev(m):
        if _metric:
            return f"{m:.0f}m gain"
        return f"{m * 3.28084:.0f} ft gain"

    # --- Build chart data ---
    elevation_traces, elevation_layout = build_elevation_chart_data(
        profile_points, climbs,
    )
    elevation_chart_data = json.dumps(elevation_traces) if elevation_traces else ""
    elevation_chart_layout = json.dumps(elevation_layout) if elevation_layout else ""

    # Distribution chart
    dist_traces, dist_layout = [], {}
    if pred and pred.get("distribution"):
        dist_traces, dist_layout = build_distribution_chart_data(pred["distribution"])
    distribution_chart_data = json.dumps(dist_traces) if dist_traces else ""
    distribution_chart_layout = json.dumps(dist_layout) if dist_layout else ""

    # Map data
    map_coords, map_climbs = build_map_data(profile_points, climbs)
    map_coords_json = json.dumps(map_coords) if map_coords else ""
    map_climbs_json = json.dumps(map_climbs) if map_climbs else ""

    # --- Course metrics ---
    course_terrain = ""
    course_terrain_desc = ""
    course_elevation_str = ""
    course_distance_str = ""
    if course:
        ct = course.get("course_type", "unknown")
        course_terrain = course_type_display(ct)
        course_terrain_desc = COURSE_TYPE_DESCRIPTIONS.get(ct, "")
        if course.get("total_gain_m"):
            course_elevation_str = _fmt_elev(course["total_gain_m"])
        if is_field_mode and cat_distance is not None:
            from raceanalyzer.queries import _format_unit_label
            unit_label = _format_unit_label(cat_distance_unit)
            dist_val = int(cat_distance) if cat_distance == int(cat_distance) else f"{cat_distance:.1f}"
            course_distance_str = f"{dist_val} {unit_label}"
        elif distance_range:
            course_distance_str = distance_range
        elif course.get("distance_m"):
            course_distance_str = _fmt_dist(course["distance_m"])

    # --- Climb breakdown ---
    climb_lines = []
    if climbs:
        distance_m = course["distance_m"] if course else None
        for i, climb in enumerate(climbs):
            context = climb_context_line(
                climb, total_distance_m=distance_m,
                finish_type=pred_ft, drop_rate=drop_rate,
            )
            climb_lines.append({"index": i + 1, "context": context})

    # --- Prediction display ---
    pred_display = None
    if pred:
        ft_display = finish_type_display_name(pred["predicted_finish_type"])
        confidence = pred.get("confidence", "low")
        conf_color_map = {"high": "green", "moderate": "yellow", "low": "red"}
        conf_tw_map = {
            "high": "bg-green-600 text-white",
            "moderate": "bg-yellow-500 text-gray-900",
            "low": "bg-red-600 text-white",
        }
        conf_label_map = {
            "high": "High confidence",
            "moderate": "Moderate confidence",
            "low": "Low confidence",
        }
        pred_display = {
            "ft_display": ft_display,
            "confidence": confidence,
            "conf_badge_class": conf_tw_map.get(confidence, "bg-gray-500 text-white"),
            "conf_label": conf_label_map.get(confidence, confidence),
            "edition_count": pred.get("edition_count", 0),
        }

    # --- Historical pattern (editions summary) ---
    detail = queries.get_feed_item_detail(
        session, series_id,
        category=query_category if is_field_mode else cat,
    )
    editions_summary = detail.get("editions_summary", []) if detail else []

    # --- Spooky riders ---
    spooky_riders = []
    spooky_source = None
    if is_field_mode:
        first_upcoming = (
            session.query(Race)
            .filter(
                Race.series_id == series_id,
                Race.is_upcoming.is_(True),
            )
            .order_by(Race.date.asc())
            .first()
        )
        spooky_race = first_upcoming or queries.get_latest_race_for_series(
            session, series_id,
        )
        if spooky_race:
            scary_df = queries.get_scary_racers(
                session, spooky_race.id,
                categories=query_category_variants or None,
            )
            if not scary_df.empty:
                spooky_source = scary_df["source"].iloc[0]
                spooky_riders = scary_df.to_dict("records")

    # Threat level helper for spooky riders
    _THREAT_LEVELS = [
        (500, "Apex Predator", "bg-red-600 text-white"),
        (400, "Very Dangerous", "bg-orange-500 text-white"),
        (300, "Dangerous", "bg-yellow-500 text-gray-900"),
        (0, "One to Watch", "bg-gray-500 text-white"),
    ]
    for racer in spooky_riders:
        pts = racer.get("carried_points", 0) or 0
        for threshold, label, tw_class in _THREAT_LEVELS:
            if pts >= threshold:
                racer["_threat_label"] = label
                racer["_threat_class"] = tw_class
                break

    # --- Startlist ---
    team_blocks = queries.get_startlist_team_blocks(
        session, startlist_source_id,
        categories=query_category_variants if is_field_mode else None,
        team_name=team,
    )

    # --- Similar races ---
    similar_races = queries.get_similar_series(session, series_id)

    # --- Stage navigation ---
    siblings = series.get("siblings", [])

    # --- TT narrative ---
    tt_narrative = ""
    if is_tt:
        ct = course["course_type"] if course else None
        tt_parts = ["It's a time trial -- a solo effort against the clock."]
        if course and course.get("distance_m") and course.get("total_gain_m"):
            dist_str = _fmt_dist(course["distance_m"]).replace(" gain", "")
            elev_str = _fmt_elev(course["total_gain_m"]).replace(" gain", "")
            tt_parts.append(
                f"The {dist_str} course has {elev_str} of climbing."
            )
        if ct == "mountainous":
            tt_parts.append(
                "This is a mountain TT -- strong climbers with good pacing will dominate."
            )
        elif ct == "hilly":
            tt_parts.append(
                "The hills make this a climber's TT -- riders who can sustain power uphill have the edge."
            )
        elif ct == "rolling":
            tt_parts.append(
                "A steady-state effort on rolling terrain. Power-to-weight matters less than raw watts here."
            )
        elif ct == "flat":
            tt_parts.append(
                "Flat and fast -- aero position and sustained power are everything."
            )
        tt_narrative = " ".join(tt_parts)

    # --- Who does well here? ---
    who_does_well = ""
    if is_tt:
        who_does_well = (
            "Strong time trialists who can pace evenly and sustain "
            "threshold power for the full distance."
        )
    elif not is_field_mode and pred:
        from raceanalyzer.predictions import racer_type_long_form
        ct = course["course_type"] if course else None
        edition_count = pred["edition_count"] if pred else 0
        long_desc = racer_type_long_form(
            ct, pred_ft, drop_rate=drop_rate, edition_count=edition_count,
        )
        who_does_well = long_desc or ""

    # --- Field forecasts display ---
    field_forecast_display = []
    if field_forecasts:
        for ff in field_forecasts:
            field_forecast_display.append({
                "category": ff["category"],
                "ft_display": finish_type_display_name(ff["finish_type"]),
                "teaser": ff["teaser"],
            })

    # --- Date info ---
    latest_upcoming = (
        session.query(Race)
        .filter(
            Race.series_id == series_id,
            Race.is_upcoming.is_(True),
        )
        .order_by(Race.date.asc())
        .first()
    )
    race_date = latest_upcoming.date if latest_upcoming else None
    race_location = ""
    if latest_upcoming:
        loc_parts = []
        if latest_upcoming.location:
            loc_parts.append(latest_upcoming.location)
        if latest_upcoming.state_province and latest_upcoming.state_province not in (latest_upcoming.location or ""):
            loc_parts.append(latest_upcoming.state_province)
        race_location = ", ".join(loc_parts)

    # --- Build template context ---
    ctx_data = {
        "series_id": series_id,
        "series": series,
        "race_date": race_date,
        "race_location": race_location,
        "race_type": preview_race_type,
        "reg_url": reg_url,
        "siblings": siblings,
        # Field picker
        "fields_list": fields_list,
        "chosen_field": chosen_field,
        "is_field_mode": is_field_mode,
        # Filter params for back link
        "cat": cat or "",
        "team": team or "",
        # What to Expect
        "is_tt": is_tt,
        "tt_narrative": tt_narrative,
        "narrative": narrative,
        "ai_context": ai_context,
        "who_does_well": who_does_well,
        # Prediction
        "pred": pred,
        "pred_display": pred_display,
        # Course
        "course": course,
        "course_terrain": course_terrain,
        "course_terrain_desc": course_terrain_desc,
        "course_elevation_str": course_elevation_str,
        "course_distance_str": course_distance_str,
        "profile_points": profile_points,
        "climbs": climbs,
        "climb_lines": climb_lines,
        # Charts
        "elevation_chart_data": elevation_chart_data,
        "elevation_chart_layout": elevation_chart_layout,
        "distribution_chart_data": distribution_chart_data,
        "distribution_chart_layout": distribution_chart_layout,
        # Map
        "map_coords_json": map_coords_json,
        "map_climbs_json": map_climbs_json,
        # Historical
        "editions_summary": editions_summary,
        "drop_rate": drop_rate,
        "typical_speed": typical_speed,
        # Field forecasts
        "field_forecasts": field_forecast_display,
        # Spooky riders
        "spooky_riders": spooky_riders,
        "spooky_source": spooky_source,
        # Startlist
        "team_blocks": team_blocks,
        # Similar races
        "similar_races": similar_races,
    }

    if _is_htmx(request):
        ctx_data["request"] = request
        return _templates(request).TemplateResponse(
            "partials/_preview_sections.html", ctx_data,
        )

    ctx = _base_context(request)
    ctx.update(ctx_data)
    return _templates(request).TemplateResponse("preview.html", ctx)


# ---------------------------------------------------------------------------
# ICS download route
# ---------------------------------------------------------------------------

@router.get("/api/ics/{series_id}")
def ics_download(series_id: int, session: Session = Depends(get_db)):
    """ICS calendar file download for a series."""
    from raceanalyzer import queries
    from raceanalyzer.ui.feed_card import generate_ics

    # Get the series info
    items = queries.get_feed_items_batch(session)
    item = next((i for i in items if i["series_id"] == series_id), None)
    if not item:
        return Response(status_code=404)

    loc = item.get("location", "")
    state = item.get("state_province", "")
    full_loc = f"{loc}, {state}" if state else loc
    duration = int(item.get("typical_field_duration_min") or 120)

    ics_content = generate_ics(
        item["display_name"],
        item.get("upcoming_date"),
        location=full_loc,
        duration_minutes=duration,
    )

    safe_name = item["display_name"].replace(" ", "_")[:30]
    try:
        date_str = item["upcoming_date"].strftime("%Y-%m-%d")
    except Exception:
        date_str = "race"

    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}-{date_str}.ics"'
        },
    )
