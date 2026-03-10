"""HTTP client for road-results.com with retry, rate limiting, and backoff."""

from __future__ import annotations

import logging
import re
import time

import cloudscraper
import requests

from raceanalyzer.config import Settings
from raceanalyzer.scraper.errors import RaceNotFoundError

logger = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class RoadResultsClient:
    """HTTP client with shared session, retry, exponential backoff, and rate limiting."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or Settings()
        self._session = cloudscraper.create_scraper()
        self._session.headers.update(BROWSER_HEADERS)
        self._last_request_time = 0.0

    def _rate_limit(self):
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self._settings.min_request_delay:
            time.sleep(self._settings.min_request_delay - elapsed)
        self._last_request_time = time.monotonic()

    def _request_with_retry(self, url: str) -> requests.Response:
        last_error = None
        for attempt in range(self._settings.retry_count):
            try:
                self._rate_limit()
                response = self._session.get(url, timeout=self._settings.request_timeout)

                if response.status_code == 200:
                    return response
                if response.status_code == 404:
                    raise RaceNotFoundError(f"Race not found: {url}")
                if response.status_code in (403, 429) or response.status_code >= 500:
                    wait = self._settings.retry_backoff_base**attempt
                    logger.warning(
                        "HTTP %d for %s, retry in %.1fs", response.status_code, url, wait
                    )
                    time.sleep(wait)
                    continue
                response.raise_for_status()
            except RaceNotFoundError:
                raise
            except requests.RequestException as e:
                last_error = e
                if attempt == self._settings.retry_count - 1:
                    raise
                wait = self._settings.retry_backoff_base**attempt
                logger.warning("Request error: %s, retry in %.1fs", e, wait)
                time.sleep(wait)

        raise ConnectionError(
            f"Failed after {self._settings.retry_count} retries: {url}"
        ) from last_error

    def fetch_race_page(self, race_id: int) -> str:
        """GET /race/{race_id} -> HTML string."""
        url = f"{self._settings.base_url}/race/{race_id}"
        return self._request_with_retry(url).text

    def fetch_race_json(self, race_id: int) -> list[dict]:
        """GET /downloadrace.php?raceID={race_id}&json=1 -> list of result dicts."""
        url = f"{self._settings.base_url}/downloadrace.php?raceID={race_id}&json=1"
        response = self._request_with_retry(url)
        data = response.json()
        if not isinstance(data, list):
            return []
        return data

    def discover_region_race_ids(self, region: int) -> list[int]:
        """Scrape the all-results page for a region and return race IDs.

        Known regions: 4=Pacific Northwest, 12=British Columbia.
        """
        url = f"{self._settings.base_url}/?n=results&sn=all&region={region}"
        response = self._request_with_retry(url)
        entries = re.findall(r'/race/(\d+)" >', response.text)
        return sorted(set(int(rid) for rid in entries), reverse=True)
