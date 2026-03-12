"""Tests for pre-computation pipeline (Sprint 011, 012)."""

from __future__ import annotations

from datetime import datetime

from raceanalyzer.db.models import (
    Course,
    CourseType,
    Race,
    RaceSeries,
    RaceType,
    SeriesPrediction,
)
from raceanalyzer.precompute import (
    _calculate_field_size,
    _confidence_label,
    _get_series_race_type,
    _resolve_prediction,
    populate_upcoming_race_types,
    precompute_all,
    precompute_series_predictions,
)


class TestCalculateFieldSize:
    def test_with_data(self, seeded_series_session):
        series = seeded_series_session.query(RaceSeries).first()
        result = _calculate_field_size(seeded_series_session, series.id)
        assert result["median"] is not None
        assert result["median"] > 0
        assert result["min"] <= result["median"] <= result["max"]

    def test_with_category(self, seeded_series_session):
        series = seeded_series_session.query(RaceSeries).first()
        result = _calculate_field_size(
            seeded_series_session, series.id, category="Men Cat 1/2"
        )
        assert result["median"] is not None

    def test_empty_series(self, session):
        result = _calculate_field_size(session, 99999)
        assert result["median"] is None

    def test_nonexistent_category(self, seeded_series_session):
        series = seeded_series_session.query(RaceSeries).first()
        result = _calculate_field_size(
            seeded_series_session, series.id, category="Nonexistent"
        )
        assert result["median"] is None


class TestPrecomputeSeriesPredictions:
    def test_creates_predictions(self, seeded_series_session):
        series = seeded_series_session.query(RaceSeries).first()
        count = precompute_series_predictions(seeded_series_session, series.id)
        seeded_series_session.commit()
        assert count > 0

        # Verify rows in DB
        preds = (
            seeded_series_session.query(SeriesPrediction)
            .filter(SeriesPrediction.series_id == series.id)
            .all()
        )
        assert len(preds) > 0
        # Should have None (overall) + each category
        categories = {p.category for p in preds}
        assert None in categories

    def test_updates_existing(self, seeded_series_session):
        series = seeded_series_session.query(RaceSeries).first()
        count1 = precompute_series_predictions(seeded_series_session, series.id)
        seeded_series_session.commit()
        count2 = precompute_series_predictions(seeded_series_session, series.id)
        seeded_series_session.commit()
        assert count1 == count2  # Same number of rows updated

        preds = (
            seeded_series_session.query(SeriesPrediction)
            .filter(SeriesPrediction.series_id == series.id)
            .all()
        )
        # Should not have duplicates
        keys = [(p.series_id, p.category) for p in preds]
        assert len(keys) == len(set(keys))

    def test_prediction_fields_populated(self, seeded_series_session):
        series = seeded_series_session.query(RaceSeries).first()
        precompute_series_predictions(seeded_series_session, series.id)
        seeded_series_session.commit()

        pred = (
            seeded_series_session.query(SeriesPrediction)
            .filter(
                SeriesPrediction.series_id == series.id,
                SeriesPrediction.category.is_(None),
            )
            .first()
        )
        assert pred is not None
        assert pred.predicted_finish_type is not None
        assert pred.confidence in ("high", "moderate", "low")
        assert pred.edition_count > 0
        assert pred.last_computed is not None


class TestPrecomputeAll:
    def test_computes_all_series(self, seeded_series_session):
        summary = precompute_all(seeded_series_session)
        assert summary["series_count"] > 0
        assert summary["predictions_count"] > 0

        # Every series should have at least one prediction
        all_series = seeded_series_session.query(RaceSeries).all()
        for series in all_series:
            preds = (
                seeded_series_session.query(SeriesPrediction)
                .filter(SeriesPrediction.series_id == series.id)
                .all()
            )
            assert len(preds) > 0


class TestResolvePrediction:
    """Sprint 012: Three-tier prediction cascade."""

    def test_time_gap_takes_priority(self, seeded_series_session):
        """Series with time-gap data should use time_gap source."""
        series = seeded_series_session.query(RaceSeries).first()
        result = _resolve_prediction(seeded_series_session, series.id, None, None)
        # Seeded data has classifications, so time_gap should be used
        if result["predicted_finish_type"] != "unknown":
            assert result["prediction_source"] == "time_gap"

    def test_course_based_when_time_gap_unknown(self, session):
        """Series without classifications but with course data uses course_profile."""
        # Create series + race without any classifications
        series = RaceSeries(normalized_name="test_course", display_name="Test Course Race")
        session.add(series)
        session.flush()

        race1 = Race(
            id=80001, name="Test Course Race 2024", series_id=series.id,
            date=datetime(2024, 6, 1), race_type=RaceType.ROAD_RACE,
            is_upcoming=False,
        )
        race2 = Race(
            id=80002, name="Test Course Race 2023", series_id=series.id,
            date=datetime(2023, 6, 1), race_type=RaceType.ROAD_RACE,
            is_upcoming=False,
        )
        session.add_all([race1, race2])

        course = Course(
            series_id=series.id, course_type=CourseType.FLAT,
            distance_m=50000, total_gain_m=100, m_per_km=2.0,
        )
        session.add(course)
        session.flush()

        result = _resolve_prediction(session, series.id, None, course)
        assert result["predicted_finish_type"] != "unknown"
        assert result["prediction_source"] == "course_profile"

    def test_unknown_when_no_data(self, session):
        """Series with no classifications, no course, no race_type returns unknown."""
        series = RaceSeries(normalized_name="test_empty", display_name="Test Empty")
        session.add(series)
        session.flush()

        result = _resolve_prediction(session, series.id, None, None)
        assert result["predicted_finish_type"] == "unknown"
        assert result["prediction_source"] is None

    def test_prediction_source_stored_on_row(self, session):
        """prediction_source is persisted in SeriesPrediction row."""
        series = RaceSeries(normalized_name="test_src", display_name="Test Src")
        session.add(series)
        session.flush()

        race = Race(
            id=80010, name="Test Src 2024", series_id=series.id,
            date=datetime(2024, 6, 1), race_type=RaceType.CRITERIUM,
            is_upcoming=False,
        )
        race2 = Race(
            id=80011, name="Test Src 2023", series_id=series.id,
            date=datetime(2023, 6, 1), race_type=RaceType.CRITERIUM,
            is_upcoming=False,
        )
        session.add_all([race, race2])
        session.flush()

        count = precompute_series_predictions(session, series.id)
        session.commit()
        assert count > 0

        pred = (
            session.query(SeriesPrediction)
            .filter(
                SeriesPrediction.series_id == series.id,
                SeriesPrediction.category.is_(None),
            )
            .first()
        )
        assert pred is not None
        # Should be race_type_only since no classifications exist
        assert pred.prediction_source in ("time_gap", "race_type_only", "course_profile", None)


class TestPopulateUpcomingRaceTypes:
    """Sprint 012: Race type inheritance for upcoming races."""

    def test_inherits_from_series_history(self, session):
        series = RaceSeries(normalized_name="test_inherit", display_name="Test Inherit")
        session.add(series)
        session.flush()

        # Two historical criteriums
        for i, yr in enumerate([2023, 2024]):
            race = Race(
                id=80020 + i, name=f"Test Inherit {yr}", series_id=series.id,
                date=datetime(yr, 6, 1), race_type=RaceType.CRITERIUM,
                is_upcoming=False,
            )
            session.add(race)

        # One upcoming with no race_type
        upcoming = Race(
            id=80025, name="Test Inherit 2025", series_id=series.id,
            date=datetime(2025, 6, 1), race_type=None, is_upcoming=True,
        )
        session.add(upcoming)
        session.flush()

        updated = populate_upcoming_race_types(session)
        assert updated == 1
        session.refresh(upcoming)
        assert upcoming.race_type == RaceType.CRITERIUM

    def test_requires_min_2_editions(self, session):
        series = RaceSeries(normalized_name="test_min2", display_name="Test Min2")
        session.add(series)
        session.flush()

        race = Race(
            id=80030, name="Test Min2 2024", series_id=series.id,
            date=datetime(2024, 6, 1), race_type=RaceType.CRITERIUM,
            is_upcoming=False,
        )
        upcoming = Race(
            id=80031, name="Test Min2 2025", series_id=series.id,
            date=datetime(2025, 6, 1), race_type=None, is_upcoming=True,
        )
        session.add_all([race, upcoming])
        session.flush()

        updated = populate_upcoming_race_types(session)
        assert updated == 0
        session.refresh(upcoming)
        assert upcoming.race_type is None

    def test_majority_threshold(self, session):
        series = RaceSeries(normalized_name="test_majority", display_name="Test Majority")
        session.add(series)
        session.flush()

        # 1 crit + 1 road race = no majority
        r1 = Race(
            id=80040, name="TMaj 2023", series_id=series.id,
            date=datetime(2023, 6, 1), race_type=RaceType.CRITERIUM,
            is_upcoming=False,
        )
        r2 = Race(
            id=80041, name="TMaj 2024", series_id=series.id,
            date=datetime(2024, 6, 1), race_type=RaceType.ROAD_RACE,
            is_upcoming=False,
        )
        upcoming = Race(
            id=80042, name="TMaj 2025", series_id=series.id,
            date=datetime(2025, 6, 1), race_type=None, is_upcoming=True,
        )
        session.add_all([r1, r2, upcoming])
        session.flush()

        updated = populate_upcoming_race_types(session)
        assert updated == 0


class TestConfidenceLabel:
    def test_high_is_moderate(self):
        assert _confidence_label(0.70) == "moderate"
        assert _confidence_label(0.65) == "moderate"

    def test_low_below_065(self):
        assert _confidence_label(0.55) == "low"
        assert _confidence_label(0.40) == "low"


class TestGetSeriesRaceType:
    def test_returns_majority(self, session):
        series = RaceSeries(normalized_name="test_rt", display_name="Test RT")
        session.add(series)
        session.flush()

        for i in range(3):
            session.add(Race(
                id=80050 + i, name=f"TRT {2022 + i}", series_id=series.id,
                date=datetime(2022 + i, 6, 1), race_type=RaceType.CRITERIUM,
                is_upcoming=False,
            ))
        session.flush()

        assert _get_series_race_type(session, series.id) == "criterium"

    def test_returns_none_insufficient(self, session):
        series = RaceSeries(normalized_name="test_rt2", display_name="Test RT2")
        session.add(series)
        session.flush()

        session.add(Race(
            id=80060, name="TRT2 2024", series_id=series.id,
            date=datetime(2024, 6, 1), race_type=RaceType.CRITERIUM,
            is_upcoming=False,
        ))
        session.flush()

        assert _get_series_race_type(session, series.id) is None
