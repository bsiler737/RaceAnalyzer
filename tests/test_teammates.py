"""Tests for team matching (Sprint 011 Phase 4)."""

from __future__ import annotations

from datetime import datetime

from raceanalyzer import queries
from raceanalyzer.db.models import RaceSeries, Startlist


class TestTeamMatching:
    def _add_startlist(self, session, series_id, riders):
        """Helper to add startlist entries."""
        for rider in riders:
            session.add(Startlist(
                series_id=series_id,
                rider_name=rider["name"],
                team=rider.get("team", ""),
                category=rider.get("category"),
                source="test",
                scraped_at=datetime.utcnow(),
            ))
        session.commit()

    def test_finds_teammates(self, seeded_series_session):
        series = seeded_series_session.query(RaceSeries).first()
        self._add_startlist(seeded_series_session, series.id, [
            {"name": "Alice", "team": "Audi Cycling", "category": "Women Cat 1/2/3"},
            {"name": "Bob", "team": "Audi Cycling Team", "category": "Men Cat 1/2"},
            {"name": "Charlie", "team": "Team Rapha", "category": "Men Cat 1/2"},
        ])

        result = queries.get_teammates_by_series(
            seeded_series_session, [series.id], None, "Audi Cycling"
        )
        assert series.id in result
        names = result[series.id]
        assert "Alice" in names
        assert "Bob" in names
        assert "Charlie" not in names

    def test_case_insensitive(self, seeded_series_session):
        series = seeded_series_session.query(RaceSeries).first()
        self._add_startlist(seeded_series_session, series.id, [
            {"name": "Alice", "team": "AUDI CYCLING"},
        ])

        result = queries.get_teammates_by_series(
            seeded_series_session, [series.id], None, "audi cycling"
        )
        assert series.id in result

    def test_short_name_rejected(self, seeded_series_session):
        result = queries.get_teammates_by_series(
            seeded_series_session, [1], None, "AB"
        )
        assert result == {}

    def test_empty_name(self, seeded_series_session):
        result = queries.get_teammates_by_series(
            seeded_series_session, [1], None, ""
        )
        assert result == {}

    def test_none_name(self, seeded_series_session):
        result = queries.get_teammates_by_series(
            seeded_series_session, [1], None, None
        )
        assert result == {}

    def test_no_match(self, seeded_series_session):
        series = seeded_series_session.query(RaceSeries).first()
        self._add_startlist(seeded_series_session, series.id, [
            {"name": "Alice", "team": "Team Rapha"},
        ])

        result = queries.get_teammates_by_series(
            seeded_series_session, [series.id], None, "Audi Cycling"
        )
        assert series.id not in result

    def test_multiple_series(self, seeded_series_session):
        series_list = seeded_series_session.query(RaceSeries).all()
        assert len(series_list) >= 2

        self._add_startlist(seeded_series_session, series_list[0].id, [
            {"name": "Alice", "team": "Audi Cycling"},
        ])
        self._add_startlist(seeded_series_session, series_list[1].id, [
            {"name": "Bob", "team": "Audi Racing"},
        ])

        ids = [s.id for s in series_list]
        result = queries.get_teammates_by_series(
            seeded_series_session, ids, None, "Audi"
        )
        assert series_list[0].id in result
        assert series_list[1].id in result

    def test_with_category_filter(self, seeded_series_session):
        series = seeded_series_session.query(RaceSeries).first()
        self._add_startlist(seeded_series_session, series.id, [
            {"name": "Alice", "team": "Audi Cycling", "category": "Women Cat 1/2/3"},
            {"name": "Bob", "team": "Audi Cycling", "category": "Men Cat 1/2"},
        ])

        result = queries.get_teammates_by_series(
            seeded_series_session, [series.id], "Women Cat 1/2/3", "Audi"
        )
        assert series.id in result
        names = result[series.id]
        assert "Alice" in names
        assert "Bob" not in names
