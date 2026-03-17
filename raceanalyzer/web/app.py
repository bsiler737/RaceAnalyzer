"""FastAPI application factory for RaceAnalyzer."""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from raceanalyzer.db.engine import get_session
from raceanalyzer.web.filters import register_filters
from raceanalyzer.web.routes import router

logger = logging.getLogger("raceanalyzer")

_BASE_DIR = Path(__file__).resolve().parent.parent
_STATIC_DIR = _BASE_DIR / "static"
_TEMPLATE_DIR = _BASE_DIR / "templates"

NAV_ITEMS = [
    {"label": "Feed", "href": "/"},
]


def _get_db_path() -> Path:
    return Path(os.environ.get("RACEANALYZER_DB_PATH", "data/raceanalyzer.db"))


def get_db():
    """Yield a SQLAlchemy session, closing it after the request."""
    session = get_session(_get_db_path())
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage scheduler lifecycle on startup/shutdown (Sprint 023)."""
    from raceanalyzer.config import Settings
    from raceanalyzer.scheduler import RefreshScheduler

    db_path = _get_db_path()
    settings = Settings(db_path=db_path)

    # Read scheduler_enabled from env var (supports "0", "false")
    env_val = os.environ.get("RACEANALYZER_SCHEDULER_ENABLED", "").strip().lower()
    if env_val in ("0", "false"):
        settings.scheduler_enabled = False

    scheduler = RefreshScheduler(db_path, settings)
    app.state.scheduler = scheduler

    background_task = None

    if settings.scheduler_enabled:
        async def _scheduler_loop():
            # Initial delay to let the server finish starting
            await asyncio.sleep(settings.scheduler_startup_delay_seconds)
            logger.info("[scheduler] Initial check after %ds startup delay.", settings.scheduler_startup_delay_seconds)
            try:
                await scheduler.check_and_run_overdue_async()
            except Exception:
                logger.exception("[scheduler] Error during initial check.")

            # Periodic rechecks
            interval = settings.scheduler_check_interval_hours * 3600
            while True:
                await asyncio.sleep(interval)
                if scheduler._shutting_down:
                    break
                logger.info("[scheduler] Periodic check (every %.0fh).", settings.scheduler_check_interval_hours)
                try:
                    await scheduler.check_and_run_overdue_async()
                except Exception:
                    logger.exception("[scheduler] Error during periodic check.")

        background_task = asyncio.create_task(_scheduler_loop())
        logger.info("[scheduler] Started (check interval: %.0fh).", settings.scheduler_check_interval_hours)
    else:
        logger.info("[scheduler] Disabled via configuration.")

    yield

    # Shutdown
    scheduler.shutdown(timeout=30.0)
    if background_task and not background_task.done():
        background_task.cancel()
        try:
            await background_task
        except asyncio.CancelledError:
            pass
    logger.info("[scheduler] Shutdown complete.")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="RaceAnalyzer", docs_url=None, redoc_url=None, lifespan=lifespan)

    # Mount static files
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Set up templates
    templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))
    register_filters(templates.env)
    app.state.templates = templates

    # Health check (enhanced for Sprint 023)
    @app.get("/health")
    def health(session=Depends(get_db)):
        result = session.execute(text("SELECT COUNT(*) FROM race_series"))
        count = result.scalar()

        response: dict = {"status": "ok", "series_count": count}

        # Add scheduler info if available
        scheduler = getattr(app.state, "scheduler", None)
        if scheduler is not None:
            response["last_refresh"] = scheduler.get_refresh_status()
            response["scheduler"] = scheduler.get_status()

            # Flag staleness in the body but always return 200 so
            # Fly.io health checks pass (503 causes machine to be
            # marked unhealthy and auto-stopped).
            if scheduler.is_stale():
                response["status"] = "stale"

        return JSONResponse(response)

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
