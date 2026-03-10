"""Tests for upcoming race calendar scraper."""

from __future__ import annotations

import responses

from raceanalyzer.calendar_feed import match_event_to_series, search_upcoming_events


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
