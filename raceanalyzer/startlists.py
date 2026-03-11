"""Startlist integration: road-results predictor (primary) + BikeReg (fallback)."""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests
from sqlalchemy.orm import Session

from raceanalyzer.refresh import is_refreshable, should_refresh

logger = logging.getLogger(__name__)


def fetch_startlist_rr(client, race, session: Session) -> list[dict]:
    """Fetch pre-registered riders ranked by power points from road-results predictor.

    Args:
        client: RoadResultsClient instance.
        race: Race ORM object (must have event_id).
        session: SQLAlchemy session for refresh checks and rider lookup.

    Returns: [{"name", "team", "category", "racer_id", "rider_id", "carried_points", "rank"}]
    """
    from raceanalyzer.db.models import Rider
    from raceanalyzer.scraper.parsers import PredictorCategoryParser, PredictorRiderParser

    if not is_refreshable(race):
        logger.info("Skipping %s: race date in the past or None", race.name)
        return []

    if not should_refresh(session, race.id, "startlist"):
        logger.info("Skipping %s: refreshed within last 24h", race.name)
        return []

    event_id = race.event_id
    if not event_id:
        logger.warning("Skipping %s: no event_id", race.name)
        return []

    try:
        # Step 1: Discover categories
        cat_html = client.fetch_predictor_categories(event_id)
        cat_parser = PredictorCategoryParser(cat_html)
        categories = cat_parser.categories()

        if not categories:
            logger.info("No categories found for %s (event_id=%d)", race.name, event_id)
            return []

        all_riders = []

        # Step 2: Fetch ranked riders per category
        for cat in categories:
            try:
                rider_html = client.fetch_predictor_category(event_id, cat["cat_id"])
                rider_parser = PredictorRiderParser(rider_html)
                riders = rider_parser.riders()

                for rider in riders:
                    # Match racer_id to existing Rider row
                    rider_id = None
                    if rider.get("racer_id"):
                        existing_rider = (
                            session.query(Rider)
                            .filter(Rider.road_results_id == rider["racer_id"])
                            .first()
                        )
                        if existing_rider:
                            rider_id = existing_rider.id

                    all_riders.append({
                        "name": rider["name"],
                        "team": rider.get("team", ""),
                        "category": cat["cat_name"],
                        "racer_id": rider.get("racer_id"),
                        "rider_id": rider_id,
                        "carried_points": rider.get("points"),
                        "rank": rider.get("rank"),
                    })

            except Exception:
                logger.warning(
                    "Failed to fetch category %s for %s",
                    cat["cat_name"], race.name,
                )
                continue

        return all_riders

    except Exception:
        logger.warning("Failed to fetch predictor data for %s", race.name, exc_info=True)
        return []


def fetch_startlist(
    event_url: str,
    category: str,
    *,
    delay: float = 2.0,
) -> list[dict]:
    """Fetch registered riders for a BikeReg event + category.

    .. deprecated:: Sprint 009
        Use :func:`fetch_startlist_rr` instead. Retained for ``--source bikereg`` fallback.

    Returns: [{"name": str, "team": str, "registration_date": datetime}]
    Graceful: returns [] on any failure. Respects rate limit.
    """
    time.sleep(delay)

    try:
        # Try CSV download first (BikeReg's "Confirmed Riders" export)
        csv_url = _build_csv_url(event_url)
        if csv_url:
            riders = _parse_bikereg_csv(csv_url, category)
            if riders:
                return riders

        # Fallback: try scraping the confirmed riders page
        riders = _parse_bikereg_html(event_url, category)
        if riders:
            return riders

    except Exception:
        logger.debug("Failed to fetch startlist from %s", event_url)

    return []


def _build_csv_url(event_url: str) -> Optional[str]:
    """Convert a BikeReg event URL to the CSV download URL."""
    # BikeReg event URLs: https://www.bikereg.com/some-event
    # CSV export (if available): https://www.bikereg.com/some-event/confirmed-riders.csv
    if not event_url:
        return None
    base = event_url.rstrip("/")
    return f"{base}/confirmed-riders.csv"


def _parse_bikereg_csv(csv_url: str, category: str) -> list[dict]:
    """Parse BikeReg confirmed riders CSV, filtering by category."""
    try:
        resp = requests.get(
            csv_url,
            headers={"User-Agent": "RaceAnalyzer/0.1"},
            timeout=15,
        )
        if not resp.ok:
            return []

        import csv
        import io

        reader = csv.DictReader(io.StringIO(resp.text))
        riders = []
        for row in reader:
            row_cat = row.get("Category", row.get("category", ""))
            if category.lower() not in row_cat.lower():
                continue

            name = row.get("Name", row.get("name", "")).strip()
            if not name:
                first = row.get("First Name", row.get("first_name", "")).strip()
                last = row.get("Last Name", row.get("last_name", "")).strip()
                name = f"{first} {last}".strip()

            if name:
                riders.append({
                    "name": name,
                    "team": row.get("Team", row.get("team", "")).strip(),
                    "registration_date": None,
                })

        return riders

    except Exception:
        logger.debug("CSV parse failed for %s", csv_url)
        return []


def _parse_bikereg_html(event_url: str, category: str) -> list[dict]:
    """Fallback: parse BikeReg confirmed riders HTML page."""
    # This is intentionally minimal — BikeReg HTML parsing is fragile
    # and may require updates. Returns [] if parsing fails.
    try:
        confirmed_url = f"{event_url.rstrip('/')}/confirmed-riders"
        resp = requests.get(
            confirmed_url,
            headers={"User-Agent": "RaceAnalyzer/0.1"},
            timeout=15,
        )
        if not resp.ok:
            return []

        # Simple regex-based extraction — not a full HTML parser
        # BikeReg lists riders in table rows with category headers
        # This is deliberately conservative: returns [] if structure is unexpected
        return []

    except Exception:
        logger.debug("HTML parse failed for %s", event_url)
        return []
