"""Scrape orchestrator: fetch, parse, persist, archive."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from raceanalyzer.config import Settings
from raceanalyzer.db.models import Race, Result, Rider, ScrapeLog
from raceanalyzer.scraper.client import RoadResultsClient
from raceanalyzer.scraper.errors import ExpectedParsingError, UnexpectedParsingError
from raceanalyzer.scraper.parsers import RacePageParser, RaceResultParser

logger = logging.getLogger(__name__)


class ScrapeOrchestrator:
    """Coordinates fetching, parsing, rider dedup, persistence, and archival."""

    def __init__(
        self,
        client: RoadResultsClient,
        session: Session,
        settings: Settings | None = None,
    ):
        self._client = client
        self._session = session
        self._settings = settings or Settings()

    def scrape_race(self, race_id: int) -> ScrapeLog:
        """Scrape a single race: fetch HTML + JSON, parse, persist, archive."""
        try:
            # Fetch HTML for metadata
            html = self._client.fetch_race_page(race_id)
            page_parser = RacePageParser(race_id, html)
            metadata = page_parser.parse()

            # Fetch JSON for results
            raw_json = self._client.fetch_race_json(race_id)
            result_parser = RaceResultParser(race_id, raw_json)
            results = result_parser.results()

            # Archive raw data
            self._archive_raw(race_id, html, raw_json)

            # Persist to database
            race = self._persist_race(metadata, results)

            log_entry = ScrapeLog(
                race_id=race_id,
                status="success",
                scraped_at=datetime.utcnow(),
                result_count=len(results),
            )
            self._session.add(log_entry)
            self._session.commit()

            logger.info(
                "Scraped race %d: %s (%d results)",
                race_id,
                metadata.get("name", "Unknown"),
                len(results),
            )
            return log_entry

        except ExpectedParsingError as e:
            log_entry = ScrapeLog(
                race_id=race_id,
                status="not_found",
                scraped_at=datetime.utcnow(),
                error_message=str(e),
            )
            self._session.add(log_entry)
            self._session.commit()
            logger.debug("Expected error for race %d: %s", race_id, e)
            return log_entry

        except (UnexpectedParsingError, Exception) as e:
            log_entry = ScrapeLog(
                race_id=race_id,
                status="error",
                scraped_at=datetime.utcnow(),
                error_message=str(e),
            )
            self._session.add(log_entry)
            self._session.commit()

            if isinstance(e, UnexpectedParsingError):
                logger.error("Unexpected parsing error for race %d: %s", race_id, e)
                raise
            logger.warning("Error scraping race %d: %s", race_id, e)
            return log_entry

    def scrape_range(
        self,
        start_id: int,
        end_id: int,
        skip_existing: bool = True,
    ) -> list[ScrapeLog]:
        """Scrape a range of race IDs with resumability."""
        ids_to_scrape = list(range(start_id, end_id + 1))

        if skip_existing:
            scraped = self._get_scraped_ids()
            ids_to_scrape = [i for i in ids_to_scrape if i not in scraped]
            if scraped:
                logger.info(
                    "Skipping %d already-scraped IDs, %d remaining",
                    len(scraped),
                    len(ids_to_scrape),
                )

        if not ids_to_scrape:
            logger.info("Nothing to scrape.")
            return []

        logger.info("Scraping %d races (%d to %d)...", len(ids_to_scrape), start_id, end_id)

        results = []
        # Use sequential scraping with rate limiting for respectful behavior.
        # Parallel fetching is available via ThreadPoolExecutor but we serialize
        # DB writes to avoid SQLite contention.
        for race_id in ids_to_scrape:
            log_entry = self.scrape_race(race_id)
            results.append(log_entry)

        return results

    def _persist_race(self, metadata: dict, results: list[dict]) -> Race:
        """Insert or update a Race and its Results, deduplicating Riders via RacerID."""
        race_id = metadata["race_id"]

        # Upsert race
        race = self._session.get(Race, race_id)
        if race is None:
            race = Race(id=race_id)
            self._session.add(race)

        race.name = metadata.get("name", "Unknown")
        race.date = metadata.get("date")
        race.location = metadata.get("location")
        race.state_province = metadata.get("state_province")
        race.url = f"{self._settings.base_url}/race/{race_id}"

        # Clear existing results for this race (idempotent re-scrape)
        for existing in race.results[:]:
            self._session.delete(existing)
        self._session.flush()

        # Insert results with rider dedup
        for row in results:
            rider = self._find_or_create_rider(row)

            result = Result(
                race_id=race_id,
                rider_id=rider.id if rider else None,
                place=row["place"],
                name=row["name"],
                team=row.get("team"),
                age=row.get("age"),
                city=row.get("city"),
                state_province=row.get("state_province"),
                license=row.get("license"),
                race_category_name=row.get("race_category_name"),
                race_time=row.get("race_time"),
                race_time_seconds=row.get("race_time_seconds"),
                field_size=row.get("field_size"),
                dnf=row.get("dnf", False),
                dq=row.get("dq", False),
                dnp=row.get("dnp", False),
                points=row.get("points"),
                carried_points=row.get("carried_points"),
            )
            self._session.add(result)

        self._session.flush()
        return race

    def _find_or_create_rider(self, row: dict) -> Rider | None:
        """Find existing rider by RacerID or create a new one."""
        racer_id = row.get("racer_id")
        name = row.get("name", "")

        if not name:
            return None

        # Try exact match on road_results_id first
        if racer_id:
            rider = (
                self._session.query(Rider)
                .filter(Rider.road_results_id == racer_id)
                .first()
            )
            if rider:
                return rider

            # Create new rider with RacerID
            rider = Rider(
                name=name,
                road_results_id=racer_id,
                license_number=row.get("license"),
            )
            self._session.add(rider)
            self._session.flush()
            return rider

        # No RacerID — skip rider linking for now (defer to Sprint 002)
        return None

    def _get_scraped_ids(self) -> set[int]:
        """Query scrape_log for already-processed race IDs."""
        rows = self._session.query(ScrapeLog.race_id).all()
        return {r[0] for r in rows}

    def _archive_raw(self, race_id: int, html: str, raw_json: list[dict]):
        """Save raw HTML and JSON to data/raw/ for re-parsing later."""
        raw_dir = Path(self._settings.raw_data_dir)
        raw_dir.mkdir(parents=True, exist_ok=True)

        json_path = raw_dir / f"{race_id}.json"
        html_path = raw_dir / f"{race_id}.html"

        json_path.write_text(json.dumps(raw_json, indent=2), encoding="utf-8")
        html_path.write_text(html, encoding="utf-8")
