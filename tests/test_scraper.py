"""Tests for scraper components: parsers, client, and pipeline."""

from __future__ import annotations

import json

import pytest
import responses

from raceanalyzer.config import Settings
from raceanalyzer.scraper.client import RoadResultsClient
from raceanalyzer.scraper.errors import NoResultsError, RaceNotFoundError
from raceanalyzer.scraper.parsers import RacePageParser, RaceResultParser
from raceanalyzer.scraper.pipeline import ScrapeOrchestrator


SAMPLE_HTML = '''<html><body>
<div class="resultstitle" >Banana Belt RR &bull; Mar 2 2024 &bull; Hillsboro, OR
</div></body></html>'''

SAMPLE_JSON = [
    {
        "Place": "1",
        "Name": "Alice Speed",
        "Team": "FastTeam",
        "Age": "28",
        "City": "Portland",
        "State": "OR",
        "License": "123456",
        "RaceCategoryName": "Women P/1/2",
        "RaceTime": "2:30:00.00",
        "FieldSize": "25",
        "Points": "50.0",
        "CarriedPoints": "0",
        "RacerID": "99001",
    },
    {
        "Place": "2",
        "Name": "Bob Climb",
        "Team": "HillTeam",
        "Age": "35",
        "City": "Seattle",
        "State": "WA",
        "License": "654321",
        "RaceCategoryName": "Women P/1/2",
        "RaceTime": "2:30:02.50",
        "FieldSize": "25",
        "Points": "40.0",
        "CarriedPoints": "5.0",
        "RacerID": "99002",
    },
    {
        "Place": "",
        "Name": "Charlie DNF",
        "Team": "",
        "Age": "30",
        "City": "",
        "State": "",
        "License": "",
        "RaceCategoryName": "Women P/1/2",
        "RaceTime": "DNF",
        "FieldSize": "25",
        "Points": "",
        "CarriedPoints": "",
        "RacerID": "99003",
    },
]


class TestRacePageParser:
    def test_parse_name(self):
        parser = RacePageParser(1000, SAMPLE_HTML)
        assert parser.name() == "Banana Belt RR"

    def test_parse_date(self):
        parser = RacePageParser(1000, SAMPLE_HTML)
        d = parser.date()
        assert d is not None
        assert d.year == 2024
        assert d.month == 3
        assert d.day == 2

    def test_parse_location(self):
        parser = RacePageParser(1000, SAMPLE_HTML)
        assert parser.location() is not None
        assert "Hillsboro" in parser.location()

    def test_parse_state(self):
        parser = RacePageParser(1000, SAMPLE_HTML)
        assert parser.state_province() == "OR"

    def test_parse_all(self):
        parser = RacePageParser(1000, SAMPLE_HTML)
        result = parser.parse()
        assert result["race_id"] == 1000
        assert result["name"] == "Banana Belt RR"


class TestRaceResultParser:
    def test_parse_results(self):
        parser = RaceResultParser(1000, SAMPLE_JSON)
        results = parser.results()
        assert len(results) == 3

    def test_first_result_fields(self):
        parser = RaceResultParser(1000, SAMPLE_JSON)
        results = parser.results()
        first = results[0]
        assert first["name"] == "Alice Speed"
        assert first["place"] == 1
        assert first["race_time_seconds"] == pytest.approx(9000.0)
        assert first["racer_id"] == 99001
        assert first["dnf"] is False

    def test_dnf_result(self):
        parser = RaceResultParser(1000, SAMPLE_JSON)
        results = parser.results()
        dnf = results[2]
        assert dnf["name"] == "Charlie DNF"
        assert dnf["dnf"] is True
        assert dnf["race_time_seconds"] is None
        assert dnf["place"] is None

    def test_categories(self):
        parser = RaceResultParser(1000, SAMPLE_JSON)
        cats = parser.categories()
        assert cats == ["Women P/1/2"]

    def test_empty_json_raises(self):
        parser = RaceResultParser(1000, [])
        with pytest.raises(NoResultsError):
            parser.results()


class TestRoadResultsClient:
    @responses.activate
    def test_fetch_race_page(self):
        responses.add(
            responses.GET,
            "https://www.road-results.com/race/1000",
            body=SAMPLE_HTML,
            status=200,
        )
        client = RoadResultsClient(Settings(min_request_delay=0))
        html = client.fetch_race_page(1000)
        assert "Banana Belt" in html

    @responses.activate
    def test_fetch_race_json(self):
        responses.add(
            responses.GET,
            "https://www.road-results.com/downloadrace.php?raceID=1000&json=1",
            json=SAMPLE_JSON,
            status=200,
        )
        client = RoadResultsClient(Settings(min_request_delay=0))
        data = client.fetch_race_json(1000)
        assert len(data) == 3

    @responses.activate
    def test_404_raises_race_not_found(self):
        responses.add(
            responses.GET,
            "https://www.road-results.com/race/99999",
            status=404,
        )
        client = RoadResultsClient(Settings(min_request_delay=0))
        with pytest.raises(RaceNotFoundError):
            client.fetch_race_page(99999)


class TestScrapeOrchestrator:
    @responses.activate
    def test_scrape_single_race(self, session, tmp_path):
        responses.add(
            responses.GET,
            "https://www.road-results.com/race/1000",
            body=SAMPLE_HTML,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://www.road-results.com/downloadrace.php?raceID=1000&json=1",
            json=SAMPLE_JSON,
            status=200,
        )

        settings = Settings(
            min_request_delay=0,
            raw_data_dir=tmp_path / "raw",
        )
        client = RoadResultsClient(settings)
        orchestrator = ScrapeOrchestrator(client, session, settings)

        log_entry = orchestrator.scrape_race(1000)
        assert log_entry.status == "success"
        assert log_entry.result_count == 3

        # Verify data persisted
        from raceanalyzer.db.models import Race, Result, Rider

        race = session.get(Race, 1000)
        assert race is not None
        assert race.name == "Banana Belt RR"
        assert len(race.results) == 3

        # Verify rider dedup via RacerID
        riders = session.query(Rider).all()
        assert len(riders) == 3  # All 3 sample results have RacerID

    @responses.activate
    def test_scrape_not_found(self, session, tmp_path):
        responses.add(
            responses.GET,
            "https://www.road-results.com/race/99999",
            status=404,
        )

        settings = Settings(min_request_delay=0, raw_data_dir=tmp_path / "raw")
        client = RoadResultsClient(settings)
        orchestrator = ScrapeOrchestrator(client, session, settings)

        log_entry = orchestrator.scrape_race(99999)
        assert log_entry.status == "not_found"

    @responses.activate
    def test_scrape_resumes(self, session, tmp_path):
        """Already-scraped races are skipped."""
        from raceanalyzer.db.models import ScrapeLog

        existing = ScrapeLog(race_id=1, status="success")
        session.add(existing)
        session.commit()

        settings = Settings(min_request_delay=0, raw_data_dir=tmp_path / "raw")
        client = RoadResultsClient(settings)
        orchestrator = ScrapeOrchestrator(client, session, settings)

        results = orchestrator.scrape_range(1, 1, skip_existing=True)
        assert len(results) == 0  # Skipped

    @responses.activate
    def test_raw_files_archived(self, session, tmp_path):
        responses.add(
            responses.GET,
            "https://www.road-results.com/race/1000",
            body=SAMPLE_HTML,
            status=200,
        )
        responses.add(
            responses.GET,
            "https://www.road-results.com/downloadrace.php?raceID=1000&json=1",
            json=SAMPLE_JSON,
            status=200,
        )

        raw_dir = tmp_path / "raw"
        settings = Settings(min_request_delay=0, raw_data_dir=raw_dir)
        client = RoadResultsClient(settings)
        orchestrator = ScrapeOrchestrator(client, session, settings)

        orchestrator.scrape_race(1000)

        assert (raw_dir / "1000.json").exists()
        assert (raw_dir / "1000.html").exists()

        saved_json = json.loads((raw_dir / "1000.json").read_text())
        assert len(saved_json) == 3
