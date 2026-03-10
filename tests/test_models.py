"""Tests for database models and constraints."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from raceanalyzer.db.models import (
    FinishType,
    Race,
    RaceClassification,
    Result,
    Rider,
    ScrapeLog,
)


class TestRaceModel:
    def test_create_race(self, session):
        race = Race(id=1000, name="Banana Belt RR")
        session.add(race)
        session.commit()

        fetched = session.get(Race, 1000)
        assert fetched.name == "Banana Belt RR"

    def test_race_results_relationship(self, session):
        race = Race(id=1000, name="Test Race")
        session.add(race)
        session.flush()

        result = Result(race_id=1000, name="John Doe", place=1)
        session.add(result)
        session.commit()

        assert len(race.results) == 1
        assert race.results[0].name == "John Doe"


class TestRiderModel:
    def test_create_rider_with_racer_id(self, session):
        rider = Rider(name="Jane Smith", road_results_id=12345)
        session.add(rider)
        session.commit()

        assert rider.id is not None
        assert rider.road_results_id == 12345

    def test_unique_road_results_id(self, session):
        r1 = Rider(name="Rider A", road_results_id=100)
        r2 = Rider(name="Rider B", road_results_id=100)
        session.add(r1)
        session.commit()
        session.add(r2)
        with pytest.raises(IntegrityError):
            session.commit()


class TestResultModel:
    def test_create_result_with_times(self, session):
        race = Race(id=1, name="Test")
        session.add(race)
        session.flush()

        result = Result(
            race_id=1,
            name="Test Rider",
            place=1,
            race_time="1:23:45.00",
            race_time_seconds=5025.0,
            field_size=40,
            dnf=False,
        )
        session.add(result)
        session.commit()

        assert result.race_time_seconds == 5025.0
        assert result.dnf is False

    def test_result_without_rider(self, session):
        race = Race(id=1, name="Test")
        session.add(race)
        session.flush()

        result = Result(race_id=1, name="No Rider Link", rider_id=None)
        session.add(result)
        session.commit()
        assert result.rider_id is None


class TestRaceClassification:
    def test_unique_race_category(self, session):
        race = Race(id=1, name="Test")
        session.add(race)
        session.flush()

        c1 = RaceClassification(
            race_id=1, category="Men P/1/2", finish_type=FinishType.BUNCH_SPRINT
        )
        c2 = RaceClassification(
            race_id=1, category="Men P/1/2", finish_type=FinishType.BREAKAWAY
        )
        session.add(c1)
        session.commit()
        session.add(c2)
        with pytest.raises(IntegrityError):
            session.commit()

    def test_different_categories_same_race(self, session):
        race = Race(id=1, name="Test")
        session.add(race)
        session.flush()

        c1 = RaceClassification(
            race_id=1, category="Men P/1/2", finish_type=FinishType.BUNCH_SPRINT
        )
        c2 = RaceClassification(
            race_id=1, category="Women 3/4", finish_type=FinishType.BREAKAWAY
        )
        session.add_all([c1, c2])
        session.commit()

        assert len(race.classifications) == 2


class TestScrapeLog:
    def test_create_log_entry(self, session):
        log = ScrapeLog(race_id=5000, status="success", result_count=42)
        session.add(log)
        session.commit()

        assert log.race_id == 5000
        assert log.result_count == 42

    def test_unique_race_id(self, session):
        l1 = ScrapeLog(race_id=5000, status="success")
        l2 = ScrapeLog(race_id=5000, status="error")
        session.add(l1)
        session.commit()
        session.add(l2)
        with pytest.raises(IntegrityError):
            session.commit()
