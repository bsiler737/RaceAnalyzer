"""Upcoming race calendar discovery (road-results GraphQL + BikeReg fallback)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import requests

from raceanalyzer.config import Settings

logger = logging.getLogger(__name__)

_BIKEREG_SEARCH_URL = "https://www.bikereg.com/api/search"
_GRAPHQL_URL = "https://outsideapi.com/fed-gw/graphql"

_GRAPHQL_QUERY = """
query AR_SearchUpcomingCX($first: Int, $searchParameters: SearchEventQueryParamsInput) {
  athleticEventCalendar(first: $first, searchParameters: $searchParameters) {
    nodes {
      name
      startDate
      endDate
      latitude
      longitude
      city
      state
      eventId
      athleticEvent {
        eventTypes
        eventUrl
      }
    }
  }
}
"""


def search_upcoming_events_rr(settings: Optional[Settings] = None) -> list[dict]:
    """Discover upcoming PNW races from the GraphQL API (outsideapi.com).

    Returns: [{"event_id": int, "name": str, "date": datetime, "city": str,
               "state": str, "registration_url": str}]
    Graceful: returns [] on any failure.
    """
    if settings is None:
        settings = Settings()

    try:
        today = datetime.utcnow().date()
        variables = {
            "first": 50,
            "searchParameters": {
                "eventTypes": [1],
                "appTypes": "BIKEREG",
                "minDate": today.isoformat(),
                "userDistanceFilter": {
                    "lat": settings.road_results_search_lat,
                    "lon": settings.road_results_search_lon,
                    "radius": settings.road_results_search_radius_miles,
                },
            },
        }

        headers = {
            "Content-Type": "application/json",
            "apollographql-client-name": "crossresults",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }

        resp = requests.post(
            _GRAPHQL_URL,
            json={"query": _GRAPHQL_QUERY, "variables": variables},
            headers=headers,
            timeout=15,
        )

        if not resp.ok:
            logger.warning("GraphQL API returned %d", resp.status_code)
            return []

        data = resp.json()
        nodes = (
            data.get("data", {})
            .get("athleticEventCalendar", {})
            .get("nodes", [])
        )

        events = []
        for node in nodes:
            event_id = node.get("eventId")
            name = node.get("name", "")
            if not event_id or not name:
                continue

            date = _parse_date(node.get("startDate", ""))
            athletic_event = node.get("athleticEvent") or {}
            registration_url = athletic_event.get("eventUrl", "")

            events.append({
                "event_id": int(event_id),
                "name": name,
                "date": date,
                "city": node.get("city", ""),
                "state": node.get("state", ""),
                "registration_url": registration_url,
            })

        logger.info("GraphQL discovered %d upcoming events", len(events))
        return events

    except Exception:
        logger.warning("GraphQL calendar discovery failed", exc_info=True)
        return []


def search_upcoming_events(
    region: str = "WA",
    days_ahead: int = 60,
    *,
    delay: float = 2.0,
) -> list[dict]:
    """Search BikeReg for upcoming cycling events in a region.

    .. deprecated:: Sprint 009
        Use :func:`search_upcoming_events_rr` instead. Retained for ``--source bikereg`` fallback.

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
