"""Tests for BikeReg startlist integration."""

from __future__ import annotations

import responses

from raceanalyzer.startlists import fetch_startlist


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
