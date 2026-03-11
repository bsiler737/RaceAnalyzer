"""Tests for upcoming race calendar scraper."""

from __future__ import annotations

import responses

from raceanalyzer.calendar_feed import (
    match_event_to_series,
    search_upcoming_events,
    search_upcoming_events_rr,
)
from raceanalyzer.config import Settings


class TestSearchUpcomingEvents:
    @responses.activate
    def test_successful_search(self):
        """Successful API response returns parsed events."""
        responses.add(
            responses.GET,
            "https://www.bikereg.com/api/search",
            json=[
                {
                    "name": "Seward Park Crit",
                    "date": "2024-06-15",
                    "url": "https://www.bikereg.com/seward-park-crit",
                    "location": "Seattle, WA",
                    "categories": ["Cat 3", "Cat 1/2"],
                },
                {
                    "name": "Mason Lake RR",
                    "date": "2024-07-01",
                    "url": "https://www.bikereg.com/mason-lake-rr",
                    "location": "Mason Lake, WA",
                    "categories": ["Cat 3"],
                },
            ],
            status=200,
        )

        events = search_upcoming_events("WA", 60, delay=0)
        assert len(events) == 2
        assert events[0]["name"] == "Seward Park Crit"
        assert events[1]["location"] == "Mason Lake, WA"

    @responses.activate
    def test_empty_response(self):
        """Empty API response returns empty list."""
        responses.add(
            responses.GET,
            "https://www.bikereg.com/api/search",
            json=[],
            status=200,
        )

        events = search_upcoming_events("WA", 60, delay=0)
        assert events == []

    @responses.activate
    def test_http_error_graceful(self):
        """HTTP error returns empty list."""
        responses.add(
            responses.GET,
            "https://www.bikereg.com/api/search",
            status=500,
        )

        events = search_upcoming_events("WA", 60, delay=0)
        assert events == []

    @responses.activate
    def test_rate_limited(self):
        """429 response returns empty list gracefully."""
        responses.add(
            responses.GET,
            "https://www.bikereg.com/api/search",
            status=429,
        )

        events = search_upcoming_events("WA", 60, delay=0)
        assert events == []

    @responses.activate
    def test_network_error(self):
        """Network error returns empty list."""
        responses.add(
            responses.GET,
            "https://www.bikereg.com/api/search",
            body=ConnectionError("timeout"),
        )

        events = search_upcoming_events("WA", 60, delay=0)
        assert events == []

    @responses.activate
    def test_nested_response_format(self):
        """Handle {'events': [...]} response format."""
        responses.add(
            responses.GET,
            "https://www.bikereg.com/api/search",
            json={
                "events": [
                    {"name": "Test Race", "date": "2024-08-01", "url": "", "location": "Portland"},
                ]
            },
            status=200,
        )

        events = search_upcoming_events("OR", 60, delay=0)
        assert len(events) == 1


class TestSearchUpcomingEventsRR:
    """Tests for GraphQL-based calendar discovery (Sprint 009)."""

    @responses.activate
    def test_successful_graphql_response(self):
        """3 upcoming events from GraphQL are parsed correctly."""
        responses.add(
            responses.POST,
            "https://outsideapi.com/fed-gw/graphql",
            json={
                "data": {
                    "athleticEventCalendar": {
                        "nodes": [
                            {
                                "eventId": 12345,
                                "name": "Mason Lake RR 1",
                                "startDate": "2026-03-14",
                                "city": "Shelton",
                                "state": "WA",
                                "latitude": 47.2,
                                "longitude": -123.1,
                                "athleticEvent": {
                                    "eventTypes": [1],
                                    "eventUrl": "https://www.bikereg.com/mason-lake-1",
                                },
                            },
                            {
                                "eventId": 12346,
                                "name": "Seward Park Crit",
                                "startDate": "2026-04-05",
                                "city": "Seattle",
                                "state": "WA",
                                "latitude": 47.55,
                                "longitude": -122.25,
                                "athleticEvent": {
                                    "eventTypes": [1],
                                    "eventUrl": "https://www.bikereg.com/seward-park",
                                },
                            },
                            {
                                "eventId": 12347,
                                "name": "Cherry Pie Crit",
                                "startDate": "2026-02-21",
                                "city": "Niles",
                                "state": "OR",
                                "latitude": 44.0,
                                "longitude": -123.0,
                                "athleticEvent": {
                                    "eventTypes": [1],
                                    "eventUrl": "https://www.bikereg.com/cherry-pie",
                                },
                            },
                        ]
                    }
                }
            },
            status=200,
        )

        events = search_upcoming_events_rr()
        assert len(events) == 3
        assert events[0]["event_id"] == 12345
        assert events[0]["name"] == "Mason Lake RR 1"
        assert events[0]["city"] == "Shelton"
        assert events[0]["state"] == "WA"
        assert events[0]["registration_url"] == "https://www.bikereg.com/mason-lake-1"
        assert events[0]["date"] is not None

    @responses.activate
    def test_empty_graphql_response(self):
        """Empty nodes returns empty list."""
        responses.add(
            responses.POST,
            "https://outsideapi.com/fed-gw/graphql",
            json={"data": {"athleticEventCalendar": {"nodes": []}}},
            status=200,
        )

        events = search_upcoming_events_rr()
        assert events == []

    @responses.activate
    def test_graphql_http_error(self):
        """HTTP error returns empty list gracefully."""
        responses.add(
            responses.POST,
            "https://outsideapi.com/fed-gw/graphql",
            status=500,
        )

        events = search_upcoming_events_rr()
        assert events == []

    @responses.activate
    def test_graphql_network_error(self):
        """Network error returns empty list gracefully."""
        responses.add(
            responses.POST,
            "https://outsideapi.com/fed-gw/graphql",
            body=ConnectionError("timeout"),
        )

        events = search_upcoming_events_rr()
        assert events == []

    @responses.activate
    def test_custom_settings(self):
        """Settings control search parameters."""
        responses.add(
            responses.POST,
            "https://outsideapi.com/fed-gw/graphql",
            json={"data": {"athleticEventCalendar": {"nodes": []}}},
            status=200,
        )

        settings = Settings()
        settings.road_results_search_lat = 45.5
        settings.road_results_search_lon = -122.7
        events = search_upcoming_events_rr(settings)
        assert events == []

        # Verify the request was made
        assert len(responses.calls) == 1


class TestMatchEventToSeries:
    def test_exact_match(self):
        series_names = ["banana_belt_rr", "cherry_pie_crit", "pir_short_track"]
        result = match_event_to_series("Banana Belt RR", series_names)
        assert result == "banana_belt_rr"

    def test_fuzzy_match(self):
        series_names = ["banana_belt_rr", "cherry_pie_crit"]
        result = match_event_to_series("2024 Banana Belt Road Race", series_names)
        assert result == "banana_belt_rr"

    def test_no_match(self):
        series_names = ["banana_belt_rr", "cherry_pie_crit"]
        result = match_event_to_series("Completely Different Race", series_names)
        assert result is None

    def test_empty_series_list(self):
        result = match_event_to_series("Some Race", [])
        assert result is None
