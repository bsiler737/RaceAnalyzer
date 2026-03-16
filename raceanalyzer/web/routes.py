"""Route handlers for RaceAnalyzer web app."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, Request
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
def feed(request: Request, session: Session = Depends(get_db)):
    """Feed page — list of upcoming races."""
    from raceanalyzer import queries

    items = queries.get_feed_items_batch(session)

    if _is_htmx(request):
        return _templates(request).TemplateResponse(
            "partials/_feed_cards.html",
            {"request": request, "items": items},
        )

    ctx = _base_context(request)
    ctx["items"] = items
    return _templates(request).TemplateResponse("feed.html", ctx)
