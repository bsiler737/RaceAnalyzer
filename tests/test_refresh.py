"""Tests for refresh-limiting logic (Sprint 009)."""

from __future__ import annotations

from datetime import datetime, timedelta

from raceanalyzer.db.models import Race, RaceSeries, RefreshLog, Rider, Startlist
from raceanalyzer.predictions import predict_contenders
from raceanalyzer.refresh import is_refreshable, record_refresh, should_refresh


class TestShouldRefresh:
    def test_first_call_returns_true(self, session):
        """No prior refresh -> should refresh."""
        assert should_refresh(session, race_id=1, refresh_type="startlist") is True

    def test_second_call_within_24h_returns_false(self, session):
        """Refreshed recently -> should not refresh."""
        record_refresh(session, race_id=1, refresh_type="startlist", status="success")
        session.commit()
        assert should_refresh(session, race_id=1, refresh_type="startlist") is False

    def test_after_24h_returns_true(self, session):
        """Refresh older than 24h -> should refresh again."""
        old_entry = RefreshLog(
            race_id=1,
            refresh_type="startlist",
            refreshed_at=datetime.utcnow() - timedelta(hours=25),
            status="success",
        )
        session.add(old_entry)
        session.commit()
        assert should_refresh(session, race_id=1, refresh_type="startlist") is True

    def test_different_types_independent(self, session):
        """Calendar and startlist refreshes are tracked independently."""
        record_refresh(session, race_id=1, refresh_type="calendar", status="success")
        session.commit()
        assert should_refresh(session, race_id=1, refresh_type="startlist") is True
        assert should_refresh(session, race_id=1, refresh_type="calendar") is False


class TestIsRefreshable:
    def test_future_date_refreshable(self, session):
        race = Race(id=1, name="Future Race", date=datetime.utcnow() + timedelta(days=7))
        assert is_refreshable(race) is True

    def test_past_date_not_refreshable(self, session):
        race = Race(id=2, name="Past Race", date=datetime(2020, 1, 1))
        assert is_refreshable(race) is False

    def test_none_date_not_refreshable(self, session):
        race = Race(id=3, name="No Date Race", date=None)
        assert is_refreshable(race) is False

    def test_today_is_refreshable(self, session):
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        race = Race(id=4, name="Today Race", date=today)
        assert is_refreshable(race) is True


class TestRecordRefresh:
    def test_creates_entry(self, session):
        record_refresh(
            session,
            race_id=1,
            refresh_type="startlist",
            status="success",
            entry_count=42,
            checksum="abc123",
            event_id=9999,
        )
        session.commit()

        stored = session.query(RefreshLog).first()
        assert stored is not None
        assert stored.race_id == 1
        assert stored.refresh_type == "startlist"
        assert stored.status == "success"
        assert stored.entry_count == 42
        assert stored.checksum == "abc123"
        assert stored.event_id == 9999
        assert stored.refreshed_at is not None

    def test_calendar_level_null_race_id(self, session):
        record_refresh(
            session,
            race_id=None,
            refresh_type="calendar",
            status="success",
            entry_count=10,
        )
        session.commit()

        stored = session.query(RefreshLog).first()
        assert stored.race_id is None
        assert stored.refresh_type == "calendar"


class TestCarriedPointsTruthiness:
    """Verify that carried_points=0.0 is treated as a valid value, not falsy."""

    def test_zero_points_not_treated_as_falsy(self, session):
        """Rider with carried_points=0.0 should have that value used, not ignored."""
        series = RaceSeries(normalized_name="pts_test", display_name="Points Test")
        session.add(series)
        session.flush()

        race = Race(
            id=9901,
            name="Points Test 2024",
            date=datetime(2024, 3, 1),
            series_id=series.id,
        )
        session.add(race)

        rider = Rider(name="Zero Points Rider", road_results_id=12345)
        session.add(rider)
        session.flush()

        from raceanalyzer.db.models import Result

        session.add(Result(
            race_id=race.id,
            rider_id=rider.id,
            name="Zero Points Rider",
            place=1,
            race_category_name="Men Cat 3",
            carried_points=0.0,
            field_size=10,
            dnf=False,
        ))

        session.add(Startlist(
            series_id=series.id,
            rider_name="Zero Points Rider",
            rider_id=rider.id,
            category="Men Cat 3",
            source="bikereg",
            scraped_at=datetime(2024, 6, 1),
        ))
        session.commit()

        contenders = predict_contenders(session, series.id, "Men Cat 3")
        assert not contenders.empty
        # carried_points should be 0.0 (the actual value), not some default
        assert contenders.iloc[0]["carried_points"] == 0.0
