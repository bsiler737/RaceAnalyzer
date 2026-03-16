"""Route handlers for RaceAnalyzer web app."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
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
