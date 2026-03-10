"""Tests for baseline heuristic predictions."""

from __future__ import annotations

from datetime import datetime

from raceanalyzer.db.models import (
    FinishType,
    Race,
    RaceClassification,
    RaceSeries,
    Result,
    Rider,
    Startlist,
)
from raceanalyzer.predictions import predict_contenders, predict_series_finish_type


class TestPredictSeriesFinishType:
    def test_empty_series(self, session):
        """No editions -> unknown with low confidence."""
        series = RaceSeries(normalized_name="empty", display_name="Empty")
        session.add(series)
        session.commit()

        result = predict_series_finish_type(session, series.id)
        assert result["predicted_finish_type"] == "unknown"
        assert result["confidence"] == "low"
        assert result["edition_count"] == 0

    def test_single_edition_low_confidence(self, session):
        """1 edition -> prediction with low confidence."""
        series = RaceSeries(normalized_name="one_ed", display_name="One Edition")
        session.add(series)
        session.flush()

        race = Race(id=901, name="One Edition 2024", date=datetime(2024, 3, 1),
                    series_id=series.id)
        session.add(race)
        session.add(RaceClassification(
            race_id=901, category="Cat 3", finish_type=FinishType.BUNCH_SPRINT,
            num_finishers=15,
        ))
        session.commit()

        result = predict_series_finish_type(session, series.id)
        assert result["predicted_finish_type"] == "bunch_sprint"
        assert result["confidence"] == "low"
        assert result["edition_count"] == 1

    def test_unanimous_editions_high_confidence(self, session):
        """5 editions all bunch_sprint -> high confidence."""
        series = RaceSeries(normalized_name="consistent", display_name="Consistent")
        session.add(series)
        session.flush()

        for i in range(5):
            race = Race(id=800 + i, name=f"Consistent {2020 + i}",
                        date=datetime(2020 + i, 6, 1), series_id=series.id)
            session.add(race)
            session.add(RaceClassification(
                race_id=800 + i, category="Cat 3",
                finish_type=FinishType.BUNCH_SPRINT, num_finishers=20,
            ))
        session.commit()

        result = predict_series_finish_type(session, series.id)
        assert result["predicted_finish_type"] == "bunch_sprint"
        assert result["confidence"] == "high"
        assert result["edition_count"] == 5

    def test_mixed_editions_moderate_confidence(self, session):
        """3 editions with 2 bunch_sprint, 1 breakaway -> moderate."""
        series = RaceSeries(normalized_name="mixed", display_name="Mixed")
        session.add(series)
        session.flush()

        types = [FinishType.BUNCH_SPRINT, FinishType.BUNCH_SPRINT, FinishType.BREAKAWAY]
        for i, ft in enumerate(types):
            race = Race(id=700 + i, name=f"Mixed {2022 + i}",
                        date=datetime(2022 + i, 4, 1), series_id=series.id)
            session.add(race)
            session.add(RaceClassification(
                race_id=700 + i, category="Cat 3", finish_type=ft, num_finishers=15,
            ))
        session.commit()

        result = predict_series_finish_type(session, series.id)
        assert result["predicted_finish_type"] == "bunch_sprint"
        assert result["confidence"] == "moderate"

    def test_recency_weighting_breaks_ties(self, session):
        """Recent editions weighted 2x should break ties."""
        series = RaceSeries(normalized_name="recency", display_name="Recency")
        session.add(series)
        session.flush()

        # 3 old breakaway, 2 recent bunch_sprint
        # Without recency: breakaway wins (3 vs 2)
        # With recency: bunch_sprint wins (2*2=4 vs 3*1=3)
        types_dates = [
            (FinishType.BREAKAWAY, datetime(2020, 3, 1)),
            (FinishType.BREAKAWAY, datetime(2021, 3, 1)),
            (FinishType.BREAKAWAY, datetime(2022, 3, 1)),
            (FinishType.BUNCH_SPRINT, datetime(2023, 3, 1)),
            (FinishType.BUNCH_SPRINT, datetime(2024, 3, 1)),
        ]
        for i, (ft, dt) in enumerate(types_dates):
            race = Race(id=600 + i, name=f"Recency {dt.year}",
                        date=dt, series_id=series.id)
            session.add(race)
            session.add(RaceClassification(
                race_id=600 + i, category="Cat 3", finish_type=ft, num_finishers=15,
            ))
        session.commit()

        result = predict_series_finish_type(session, series.id)
        assert result["predicted_finish_type"] == "bunch_sprint"

    def test_category_filter(self, session):
        """Per-category prediction filters correctly."""
        series = RaceSeries(normalized_name="catfilt", display_name="Cat Filter")
        session.add(series)
        session.flush()

        race = Race(id=500, name="Cat Filter 2024", date=datetime(2024, 5, 1),
                    series_id=series.id)
        session.add(race)
        session.add(RaceClassification(
            race_id=500, category="Cat 3", finish_type=FinishType.BUNCH_SPRINT,
            num_finishers=20,
        ))
        session.add(RaceClassification(
            race_id=500, category="Cat 1/2", finish_type=FinishType.BREAKAWAY,
            num_finishers=15,
        ))
        session.commit()

        cat3 = predict_series_finish_type(session, series.id, category="Cat 3")
        assert cat3["predicted_finish_type"] == "bunch_sprint"

        cat12 = predict_series_finish_type(session, series.id, category="Cat 1/2")
        assert cat12["predicted_finish_type"] == "breakaway"


class TestPredictContenders:
    def test_tier2_series_history(self, seeded_course_session):
        """With series history but no startlist, returns series_history source."""
        session = seeded_course_session
        series = session.query(RaceSeries).first()

        contenders = predict_contenders(session, series.id, "Men Cat 1/2")
        assert not contenders.empty
        assert contenders["source"].iloc[0] == "series_history"

    def test_tier3_category_fallback(self, seeded_course_session):
        """With no series history for category, falls back to category-wide."""
        session = seeded_course_session
        series = session.query(RaceSeries).first()

        # Give riders some carried_points
        results = session.query(Result).filter(
            Result.carried_points.is_(None),
            Result.rider_id.isnot(None),
        ).all()
        for i, r in enumerate(results[:5]):
            r.carried_points = float(50 + i * 10)
        session.commit()

        contenders = predict_contenders(session, series.id, "Nonexistent Cat")
        # Should fall back to category tier (empty since no results for this cat)
        assert contenders.empty

    def test_tier1_startlist(self, seeded_course_session):
        """With startlist present, uses startlist source."""
        session = seeded_course_session
        series = session.query(RaceSeries).first()

        # Add startlist entries
        rider = session.query(Rider).first()
        session.add(Startlist(
            series_id=series.id,
            rider_name=rider.name,
            rider_id=rider.id,
            category="Men Cat 1/2",
            source="bikereg",
            scraped_at=datetime(2024, 6, 1),
        ))
        session.commit()

        contenders = predict_contenders(session, series.id, "Men Cat 1/2")
        assert not contenders.empty
        assert contenders["source"].iloc[0] == "startlist"

    def test_empty_series(self, session):
        """No data at all -> empty DataFrame."""
        series = RaceSeries(normalized_name="empty_c", display_name="Empty C")
        session.add(series)
        session.commit()

        contenders = predict_contenders(session, series.id, "Cat 3")
        assert contenders.empty


class TestHeuristicAccuracy:
    def test_beats_random_baseline(self, session):
        """Heuristic predictor should beat 'most common type for category' baseline."""
        # Create 5 series with consistent finish types
        series_types = [
            ("Crit A", FinishType.BUNCH_SPRINT, 5),
            ("Crit B", FinishType.BUNCH_SPRINT, 4),
            ("Hill A", FinishType.BREAKAWAY, 6),
            ("Hill B", FinishType.BREAKAWAY, 3),
            ("Mixed", FinishType.REDUCED_SPRINT, 4),
        ]

        category = "Cat 3"
        all_series_ids = []

        for idx, (name, ft, editions) in enumerate(series_types):
            series = RaceSeries(normalized_name=name.lower().replace(" ", "_"),
                                display_name=name)
            session.add(series)
            session.flush()
            all_series_ids.append(series.id)

            for i in range(editions):
                race = Race(id=1000 + idx * 10 + i, name=f"{name} {2020 + i}",
                            date=datetime(2020 + i, 3, 1), series_id=series.id)
                session.add(race)
                session.add(RaceClassification(
                    race_id=race.id, category=category, finish_type=ft,
                    num_finishers=20,
                ))

        session.commit()

        # Heuristic predictions
        heuristic_correct = 0
        for sid, (name, actual_ft, _) in zip(all_series_ids, series_types):
            pred = predict_series_finish_type(session, sid, category=category)
            if pred["predicted_finish_type"] == actual_ft.value:
                heuristic_correct += 1

        # Random baseline: predict most common type for category
        # Most common is bunch_sprint (9 editions) out of 22 total
        # Baseline accuracy = fraction of series whose type matches most-common
        most_common = "bunch_sprint"
        baseline_correct = sum(
            1 for _, ft, _ in series_types if ft.value == most_common
        )

        assert heuristic_correct >= baseline_correct
        # Heuristic should get all 5 right since each series is consistent
        assert heuristic_correct == 5
