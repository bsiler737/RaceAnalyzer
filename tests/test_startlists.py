"""Tests for startlist integration (BikeReg + road-results predictor)."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import responses

from raceanalyzer.db.models import Race, RaceSeries, Rider
from raceanalyzer.startlists import fetch_startlist, fetch_startlist_rr


class TestFetchStartlist:
    @responses.activate
    def test_csv_parse_success(self):
        """Successful CSV parse returns rider list."""
        csv_content = (
            "Name,Category,Team\n"
            "John Smith,Cat 3,Team Fast\n"
            "Jane Doe,Cat 3,Speed Demons\n"
            "Bob Jones,Cat 1/2,Pro Team\n"
        )
        responses.add(
            responses.GET,
            "https://www.bikereg.com/test-race/confirmed-riders.csv",
            body=csv_content,
            status=200,
        )

        result = fetch_startlist(
            "https://www.bikereg.com/test-race",
            "Cat 3",
            delay=0,
        )
        assert len(result) == 2
        assert result[0]["name"] == "John Smith"
        assert result[0]["team"] == "Team Fast"

    @responses.activate
    def test_csv_empty_response(self):
        """Empty CSV returns empty list."""
        responses.add(
            responses.GET,
            "https://www.bikereg.com/empty-race/confirmed-riders.csv",
            body="Name,Category,Team\n",
            status=200,
        )

        result = fetch_startlist(
            "https://www.bikereg.com/empty-race",
            "Cat 3",
            delay=0,
        )
        assert result == []

    @responses.activate
    def test_http_error_graceful(self):
        """HTTP error returns empty list, not exception."""
        responses.add(
            responses.GET,
            "https://www.bikereg.com/bad-race/confirmed-riders.csv",
            status=404,
        )
        # Also mock the HTML fallback
        responses.add(
            responses.GET,
            "https://www.bikereg.com/bad-race/confirmed-riders",
            status=404,
        )

        result = fetch_startlist(
            "https://www.bikereg.com/bad-race",
            "Cat 3",
            delay=0,
        )
        assert result == []

    @responses.activate
    def test_network_error_graceful(self):
        """Network error returns empty list."""
        responses.add(
            responses.GET,
            "https://www.bikereg.com/timeout-race/confirmed-riders.csv",
            body=ConnectionError("timeout"),
        )
        responses.add(
            responses.GET,
            "https://www.bikereg.com/timeout-race/confirmed-riders",
            body=ConnectionError("timeout"),
        )

        result = fetch_startlist(
            "https://www.bikereg.com/timeout-race",
            "Cat 3",
            delay=0,
        )
        assert result == []

    @responses.activate
    def test_first_last_name_columns(self):
        """CSV with First Name/Last Name columns instead of Name."""
        csv_content = (
            "First Name,Last Name,Category,Team\n"
            "Alice,Wonder,Cat 3,Fast Team\n"
        )
        responses.add(
            responses.GET,
            "https://www.bikereg.com/alt-race/confirmed-riders.csv",
            body=csv_content,
            status=200,
        )

        result = fetch_startlist(
            "https://www.bikereg.com/alt-race",
            "Cat 3",
            delay=0,
        )
        assert len(result) == 1
        assert result[0]["name"] == "Alice Wonder"


PREDICTOR_CATEGORIES_HTML = """
<html><body>
<div class='predictorheader'>
  <span class='categoryname' raceid='74287-1'>Men Cat 1/2</span>
</div>
<p>This race has 5 racers preregistered</p>
</body></html>
"""

PREDICTOR_RIDERS_HTML = """
<html><body>
<table class='datatable1'>
<tr><td>1. <a href="?n=racers&sn=r&rID=1162">Brian Breach</a></td>
    <td>Stages by Cuore</td><td>267.12</td></tr>
<tr><td>2. <a href="?n=racers&sn=r&rID=2045">Carlos Climb</a></td>
    <td>Fast Team</td><td>312.50</td></tr>
</table>
</body></html>
"""


class TestFetchStartlistRR:
    def _make_race(self, session, future=True, event_id=12345):
        series = RaceSeries(normalized_name="test_rr", display_name="Test RR")
        session.add(series)
        session.flush()

        date = datetime.utcnow() + timedelta(days=7) if future else datetime(2020, 1, 1)
        race = Race(
            id=8001,
            name="Test Race",
            date=date,
            series_id=series.id,
            is_upcoming=True,
            event_id=event_id,
        )
        session.add(race)
        session.commit()
        return race

    def test_returns_riders(self, session):
        """Predictor returns ranked riders with points."""
        race = self._make_race(session)

        client = MagicMock()
        client.fetch_predictor_categories.return_value = PREDICTOR_CATEGORIES_HTML
        client.fetch_predictor_category.return_value = PREDICTOR_RIDERS_HTML

        riders = fetch_startlist_rr(client, race, session)
        assert len(riders) == 2
        assert riders[0]["name"] == "Brian Breach"
        assert riders[0]["carried_points"] == 267.12
        assert riders[0]["category"] == "Men Cat 1/2"
        assert riders[0]["racer_id"] == 1162

    def test_past_date_skipped(self, session):
        """Past-dated race is skipped."""
        race = self._make_race(session, future=False)

        client = MagicMock()
        riders = fetch_startlist_rr(client, race, session)
        assert riders == []
        client.fetch_predictor_categories.assert_not_called()

    def test_no_event_id_skipped(self, session):
        """Race without event_id is skipped."""
        race = self._make_race(session, event_id=None)

        client = MagicMock()
        riders = fetch_startlist_rr(client, race, session)
        assert riders == []

    def test_empty_categories(self, session):
        """Empty predictor response returns empty list."""
        race = self._make_race(session)

        client = MagicMock()
        client.fetch_predictor_categories.return_value = "<html></html>"

        riders = fetch_startlist_rr(client, race, session)
        assert riders == []

    def test_links_to_existing_rider(self, session):
        """Rider with matching road_results_id gets rider_id linked."""
        race = self._make_race(session)

        rider = Rider(name="Brian Breach", road_results_id=1162)
        session.add(rider)
        session.commit()

        client = MagicMock()
        client.fetch_predictor_categories.return_value = PREDICTOR_CATEGORIES_HTML
        client.fetch_predictor_category.return_value = PREDICTOR_RIDERS_HTML

        riders = fetch_startlist_rr(client, race, session)
        assert riders[0]["rider_id"] == rider.id
        assert riders[1]["rider_id"] is None  # No matching rider for racer_id 2045

    def test_refresh_limit_blocks_second_call(self, session):
        """After successful fetch, second call within 24h is blocked."""
        race = self._make_race(session)

        client = MagicMock()
        client.fetch_predictor_categories.return_value = PREDICTOR_CATEGORIES_HTML
        client.fetch_predictor_category.return_value = PREDICTOR_RIDERS_HTML

        # First call succeeds
        riders1 = fetch_startlist_rr(client, race, session)
        assert len(riders1) == 2

        # Record a refresh entry to simulate the CLI behavior
        from raceanalyzer.refresh import record_refresh

        record_refresh(session, race_id=race.id, refresh_type="startlist", status="success")
        session.commit()

        # Second call should be blocked
        riders2 = fetch_startlist_rr(client, race, session)
        assert riders2 == []
