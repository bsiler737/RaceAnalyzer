"""Tests for pre-computation pipeline (Sprint 011)."""

from __future__ import annotations

from raceanalyzer.db.models import RaceSeries, SeriesPrediction
from raceanalyzer.precompute import (
    _calculate_field_size,
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
