"""Tests for time parsing utility."""

from __future__ import annotations

import pytest

from raceanalyzer.utils.time_parsing import parse_race_time


class TestParseRaceTime:
    def test_hours_minutes_seconds(self):
        assert parse_race_time("1:23:45.67") == pytest.approx(5025.67)

    def test_minutes_seconds(self):
        assert parse_race_time("23:45.67") == pytest.approx(1425.67)

    def test_seconds_only(self):
        assert parse_race_time("45.67") == pytest.approx(45.67)

    def test_integer_seconds(self):
        assert parse_race_time("120") == pytest.approx(120.0)

    def test_zero(self):
        assert parse_race_time("0:00:00.00") == pytest.approx(0.0)

    def test_dnf(self):
        assert parse_race_time("DNF") is None

    def test_dq(self):
        assert parse_race_time("DQ") is None

    def test_dns(self):
        assert parse_race_time("DNS") is None

    def test_dnp(self):
        assert parse_race_time("DNP") is None

    def test_empty_string(self):
        assert parse_race_time("") is None

    def test_none(self):
        assert parse_race_time(None) is None

    def test_whitespace(self):
        assert parse_race_time("   ") is None

    def test_whitespace_around_time(self):
        assert parse_race_time("  1:23:45.67  ") == pytest.approx(5025.67)

    def test_unparseable(self):
        assert parse_race_time("abc") is None

    def test_otl(self):
        assert parse_race_time("OTL") is None

    def test_mixed_case_dnf(self):
        assert parse_race_time("dnf") is None
