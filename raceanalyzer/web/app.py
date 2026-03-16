"""FastAPI application factory for RaceAnalyzer."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from raceanalyzer.db.engine import get_session
from raceanalyzer.web.filters import register_filters
from raceanalyzer.web.routes import router

_BASE_DIR = Path(__file__).resolve().parent.parent
_STATIC_DIR = _BASE_DIR / "static"
_TEMPLATE_DIR = _BASE_DIR / "templates"

NAV_ITEMS = [
    {"label": "Feed", "href": "/"},
]


def get_db():
    """Yield a SQLAlchemy session, closing it after the request."""
    db_path = Path(os.environ.get("RACEANALYZER_DB_PATH", "data/raceanalyzer.db"))
    session = get_session(db_path)
    try:
        yield session
    finally:
        session.close()


def base_context(request: Request) -> dict:
    """Return base template context with nav items and current path."""
    return {
        "request": request,
        "nav_items": NAV_ITEMS,
        "current_path": request.url.path,
    }


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="RaceAnalyzer", docs_url=None, redoc_url=None)

    # Mount static files
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Set up templates
    templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))
    register_filters(templates.env)
    app.state.templates = templates

    # Health check
    @app.get("/health")
    def health(session=Depends(get_db)):
        result = session.execute(text("SELECT COUNT(*) FROM race_series"))
        count = result.scalar()
        return JSONResponse({"status": "ok", "series_count": count})

    # Include routes
    app.include_router(router)

    # Custom exception handlers
    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        ctx = base_context(request)
        return templates.TemplateResponse("errors/404.html", ctx, status_code=404)

    @app.exception_handler(500)
    async def server_error_handler(request: Request, exc):
        ctx = base_context(request)
        return templates.TemplateResponse("errors/500.html", ctx, status_code=500)

    return app
