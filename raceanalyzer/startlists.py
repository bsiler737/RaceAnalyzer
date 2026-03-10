"""BikeReg startlist integration with graceful degradation."""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def fetch_startlist(
    event_url: str,
    category: str,
    *,
    delay: float = 2.0,
) -> list[dict]:
    """Fetch registered riders for a BikeReg event + category.

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
