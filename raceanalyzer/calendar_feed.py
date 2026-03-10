"""Upcoming race calendar scraper (BikeReg/OBRA)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_BIKEREG_SEARCH_URL = "https://www.bikereg.com/api/search"


def search_upcoming_events(
    region: str = "WA",
    days_ahead: int = 60,
    *,
    delay: float = 2.0,
) -> list[dict]:
    """Search BikeReg for upcoming cycling events in a region.

    Returns: [{"name", "date", "url", "location", "categories": [...]}]
    Graceful: returns [] on any failure.
    """
    try:
        events = _search_bikereg(region, days_ahead, delay=delay)
        if events:
            return events
    except Exception:
        logger.debug("BikeReg search failed for region %s", region)

    return []


def _search_bikereg(
    region: str,
    days_ahead: int,
    *,
    delay: float = 2.0,
) -> list[dict]:
    """Search BikeReg API for upcoming cycling events."""
    time.sleep(delay)

    today = datetime.utcnow().date()
    end_date = today + timedelta(days=days_ahead)

    params = {
        "state": region,
        "sport": "cycling",
        "startdate": today.isoformat(),
        "enddate": end_date.isoformat(),
    }

    try:
        resp = requests.get(
            _BIKEREG_SEARCH_URL,
            params=params,
            headers={"User-Agent": "RaceAnalyzer/0.1"},
            timeout=15,
        )

        if resp.status_code == 429:
            # Rate limited — back off
            logger.warning("BikeReg rate limited, backing off")
            time.sleep(delay * 2)
            return []

        if not resp.ok:
            return []

        data = resp.json()
        events = []

        items = data if isinstance(data, list) else data.get("events", data.get("results", []))

        for item in items:
            event = {
                "name": item.get("name", item.get("title", "")),
                "date": _parse_date(item.get("date", item.get("start_date", ""))),
                "url": item.get("url", item.get("link", "")),
                "location": item.get("location", item.get("city", "")),
                "categories": item.get("categories", []),
            }
            if event["name"]:
                events.append(event)

        return events

    except Exception:
        logger.debug("BikeReg API request failed")
        return []


def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse a date string from BikeReg. Returns None on failure."""
    if not date_str:
        return None

    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    return None


def match_event_to_series(
    event_name: str,
    series_names: list[str],
    *,
    min_score: float = 0.5,
) -> Optional[str]:
    """Fuzzy-match a BikeReg event name to an existing series.

    Returns the matched series normalized_name, or None.
    """
    import re
    from difflib import SequenceMatcher

    # Clean event name
    cleaned = re.sub(r"\b(19|20)\d{2}\b", "", event_name).strip().lower()

    best_score = 0.0
    best_match = None

    for name in series_names:
        score = SequenceMatcher(None, cleaned, name.lower()).ratio()
        if score > best_score:
            best_score = score
            best_match = name

    if best_score >= min_score and best_match:
        return best_match

    return None
