"""Tests for baseline heuristic predictions."""

from __future__ import annotations

from datetime import datetime

from raceanalyzer.db.models import (
    Course,
    CourseType,
    FinishType,
    Race,
    RaceClassification,
    RaceSeries,
    RaceType,
    Result,
    Rider,
    Startlist,
)
from raceanalyzer.predictions import (
    calculate_drop_rate,
    calculate_typical_duration,
    calculate_typical_speeds,
    generate_narrative,
    predict_contenders,
    predict_series_finish_type,
    racer_type_description,
)


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

    def test_inline_carried_points_preferred(self, session):
        """When Startlist has carried_points, use them directly (no historical lookup)."""
        series = RaceSeries(normalized_name="inline_pts", display_name="Inline Pts")
        session.add(series)
        session.flush()

        rider = Rider(name="Predictor Rider", road_results_id=5555)
        session.add(rider)
        session.flush()

        # Historical result with carried_points=100
        race = Race(id=9801, name="Old Race", date=datetime(2024, 3, 1), series_id=series.id)
        session.add(race)
        session.add(Result(
            race_id=race.id, rider_id=rider.id, name="Predictor Rider",
            place=5, race_category_name="Cat 3", carried_points=100.0,
            field_size=10, dnf=False,
        ))

        # Startlist with inline carried_points=267.12 (from road-results predictor)
        session.add(Startlist(
            series_id=series.id, rider_name="Predictor Rider", rider_id=rider.id,
            category="Cat 3", source="road-results", scraped_at=datetime(2024, 6, 1),
            carried_points=267.12,
        ))
        session.commit()

        contenders = predict_contenders(session, series.id, "Cat 3")
        assert not contenders.empty
        # Should use 267.12 from startlist, NOT 100.0 from historical results
        assert contenders.iloc[0]["carried_points"] == 267.12

    def test_none_carried_points_falls_back(self, session):
        """When Startlist.carried_points is None, fall back to historical lookup."""
        series = RaceSeries(normalized_name="fallback_pts", display_name="Fallback Pts")
        session.add(series)
        session.flush()

        rider = Rider(name="History Rider", road_results_id=6666)
        session.add(rider)
        session.flush()

        race = Race(id=9802, name="Old Race", date=datetime(2024, 3, 1), series_id=series.id)
        session.add(race)
        session.add(Result(
            race_id=race.id, rider_id=rider.id, name="History Rider",
            place=1, race_category_name="Cat 3", carried_points=85.5,
            field_size=10, dnf=False,
        ))

        # Startlist WITHOUT carried_points (BikeReg source)
        session.add(Startlist(
            series_id=series.id, rider_name="History Rider", rider_id=rider.id,
            category="Cat 3", source="bikereg", scraped_at=datetime(2024, 6, 1),
        ))
        session.commit()

        contenders = predict_contenders(session, series.id, "Cat 3")
        assert not contenders.empty
        # Should fall back to historical 85.5
        assert contenders.iloc[0]["carried_points"] == 85.5

    def test_zero_carried_points_valid(self, session):
        """carried_points=0.0 on Startlist is treated as valid (not falsy)."""
        series = RaceSeries(normalized_name="zero_pts_sl", display_name="Zero Pts SL")
        session.add(series)
        session.flush()

        rider = Rider(name="Zero Rider")
        session.add(rider)
        session.flush()

        # Startlist with carried_points=0.0
        session.add(Startlist(
            series_id=series.id, rider_name="Zero Rider", rider_id=rider.id,
            category="Cat 3", source="road-results", scraped_at=datetime(2024, 6, 1),
            carried_points=0.0,
        ))
        session.commit()

        contenders = predict_contenders(session, series.id, "Cat 3")
        assert not contenders.empty
        assert contenders.iloc[0]["carried_points"] == 0.0


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


# --- Drop rate tests ---


def _create_drop_rate_fixture(session, series_name, editions_data):
    """Helper: create series with multiple editions and results.

    editions_data: list of (year, total_starters, num_dnf, num_dnp)
    """
    series = RaceSeries(normalized_name=series_name, display_name=series_name)
    session.add(series)
    session.flush()

    for i, (year, total, n_dnf, n_dnp) in enumerate(editions_data):
        race = Race(
            id=2000 + i * 100 + hash(series_name) % 100,
            name=f"{series_name} {year}",
            date=datetime(year, 6, 1),
            series_id=series.id,
        )
        session.add(race)

        for j in range(total):
            is_dnf = j < n_dnf
            is_dnp = not is_dnf and j < n_dnf + n_dnp
            session.add(Result(
                race_id=race.id,
                name=f"Rider {j}",
                place=None if (is_dnf or is_dnp) else j + 1,
                race_category_name="Cat 4/5",
                race_time_seconds=None if (is_dnf or is_dnp) else 3600.0 + j * 5,
                field_size=total,
                dnf=is_dnf,
                dnp=is_dnp,
            ))

    session.commit()
    return series


class TestCalculateDropRate:
    def test_known_fixture(self, session):
        """10 starters, 3 DNF -> 30% drop rate."""
        series = _create_drop_rate_fixture(
            session, "dropper", [(2024, 10, 3, 0)]
        )
        result = calculate_drop_rate(session, series.id)
        assert result is not None
        assert result["drop_rate"] == 0.3
        assert result["total_starters"] == 10
        assert result["total_dropped"] == 3
        assert result["label"] == "high"

    def test_no_history(self, session):
        """No results -> None."""
        series = RaceSeries(normalized_name="no_data", display_name="No Data")
        session.add(series)
        session.commit()

        result = calculate_drop_rate(session, series.id)
        assert result is None

    def test_multiple_editions_median(self, session):
        """Median across editions: 10%, 30%, 50% -> median 30%."""
        series = _create_drop_rate_fixture(
            session, "multi_ed",
            [
                (2022, 10, 1, 0),  # 10%
                (2023, 10, 3, 0),  # 30%
                (2024, 10, 5, 0),  # 50%
            ],
        )
        result = calculate_drop_rate(session, series.id)
        assert result is not None
        assert result["drop_rate"] == 0.3
        assert result["edition_count"] == 3
        assert result["confidence"] == "high"

    def test_dnp_handling(self, session):
        """DNP counted as dropped alongside DNF."""
        series = _create_drop_rate_fixture(
            session, "dnp_test", [(2024, 10, 1, 2)]  # 1 DNF + 2 DNP = 30%
        )
        result = calculate_drop_rate(session, series.id)
        assert result is not None
        assert result["drop_rate"] == 0.3
        assert result["total_dropped"] == 3

    def test_label_thresholds(self, session):
        """Verify label mapping: low/moderate/high/extreme."""
        # 5% -> low
        series = _create_drop_rate_fixture(
            session, "low_drop", [(2024, 20, 1, 0)]
        )
        result = calculate_drop_rate(session, series.id)
        assert result["label"] == "low"


# --- Speed tests ---


def _create_speed_fixture(session, series_name, race_type=None, distance_m=85000.0):
    """Helper: create series with course and timed results."""
    series = RaceSeries(normalized_name=series_name, display_name=series_name)
    session.add(series)
    session.flush()

    course = Course(
        series_id=series.id,
        distance_m=distance_m,
        total_gain_m=500.0,
        course_type=CourseType.ROLLING,
    )
    session.add(course)

    race = Race(
        id=3000 + hash(series_name) % 1000,
        name=f"{series_name} 2024",
        date=datetime(2024, 6, 1),
        series_id=series.id,
        race_type=race_type,
    )
    session.add(race)

    # 15 finishers with times
    for j in range(15):
        # ~85km in ~3h = ~28.3 kph
        time_sec = 10800.0 + j * 60  # 3h + 1min per place
        session.add(Result(
            race_id=race.id,
            name=f"Rider {j}",
            place=j + 1,
            race_category_name="Cat 3",
            race_time_seconds=time_sec,
            field_size=15,
            dnf=False,
        ))

    session.commit()
    return series


class TestCalculateTypicalSpeeds:
    def test_known_fixture(self, session):
        """85km in 3h = ~28.3 kph for winner."""
        series = _create_speed_fixture(session, "speedy")
        result = calculate_typical_speeds(session, series.id)
        assert result is not None
        assert 25 < result["median_winner_speed_kph"] < 35
        assert result["median_field_speed_kph"] > 0
        assert result["median_winner_speed_mph"] > 0

    def test_crit_suppression(self, session):
        """Criteriums should return None."""
        series = _create_speed_fixture(
            session, "crit_speed", race_type=RaceType.CRITERIUM
        )
        result = calculate_typical_speeds(session, series.id)
        assert result is None

    def test_missing_distance(self, session):
        """No distance -> None."""
        series = _create_speed_fixture(session, "no_dist", distance_m=None)
        # Fix: set distance to None on course
        course = session.query(Course).filter(
            Course.series_id == series.id
        ).first()
        course.distance_m = None
        session.commit()

        result = calculate_typical_speeds(session, series.id)
        assert result is None

    def test_short_distance_suppressed(self, session):
        """Distance < 5km (non-crit) -> None."""
        series = _create_speed_fixture(
            session, "short_dist", distance_m=3000.0
        )
        result = calculate_typical_speeds(session, series.id)
        assert result is None


# --- Narrative tests ---


class TestGenerateNarrative:
    def test_full_data(self):
        """All data present -> multi-sentence narrative."""
        narrative = generate_narrative(
            course_type="hilly",
            predicted_finish_type="breakaway",
            drop_rate={"drop_rate": 0.25, "label": "moderate"},
            typical_speed={
                "median_winner_speed_mph": 24.1,
                "median_winner_speed_kph": 38.8,
            },
            distance_km=85.0,
            total_gain_m=1200.0,
            climbs=[{
                "length_m": 2000, "avg_grade": 6, "category": "steep",
                "end_d": 70000,
            }],
            edition_count=5,
        )
        assert "85 km" in narrative
        assert "1200m" in narrative
        assert "steep" in narrative
        assert "breakaway" in narrative
        assert "25%" in narrative
        assert "24.1 mph" in narrative
        assert "None" not in narrative

    def test_no_data_new_event(self):
        """No data -> new event message."""
        narrative = generate_narrative()
        assert "new event" in narrative.lower()
        assert "None" not in narrative

    def test_partial_data_no_speed(self):
        """Course data but no speed -> narrative without pacing sentence."""
        narrative = generate_narrative(
            course_type="rolling",
            distance_km=60.0,
            total_gain_m=400.0,
        )
        assert "60 km" in narrative
        assert "mph" not in narrative

    def test_flat_course(self):
        """Flat course narrative."""
        narrative = generate_narrative(
            course_type="flat",
            distance_km=50.0,
        )
        assert "flat" in narrative.lower()
        assert "positioning" in narrative.lower()

    def test_no_climbs(self):
        """No climbs -> no climb sentence."""
        narrative = generate_narrative(
            course_type="flat",
            distance_km=50.0,
            climbs=[],
        )
        assert "hardest climb" not in narrative.lower()

    def test_single_edition_caveat(self):
        """Single edition -> caveat sentence."""
        narrative = generate_narrative(
            course_type="rolling",
            predicted_finish_type="bunch_sprint",
            distance_km=60.0,
            edition_count=1,
        )
        assert "limited history" in narrative.lower()
        assert "grain of salt" in narrative.lower()


# --- Sprint 010: Racer type description ---


class TestRacerTypeDescription:
    def test_known_combination(self):
        result = racer_type_description("flat", "bunch_sprint")
        assert result is not None
        assert "sprinter" in result.lower()

    def test_hilly_gc(self):
        result = racer_type_description("hilly", "gc_selective")
        assert result is not None
        assert "climber" in result.lower()

    def test_unknown_combination(self):
        result = racer_type_description("flat", "gc_selective")
        assert result is None

    def test_none_inputs(self):
        assert racer_type_description(None, "bunch_sprint") is None
        assert racer_type_description("flat", None) is None
        assert racer_type_description(None, None) is None


# --- Sprint 010: Typical duration ---


class TestCalculateTypicalDuration:
    def test_known_fixture(self, session):
        """Fixture with known times should return durations."""
        series = _create_speed_fixture(session, "duration_test")
        result = calculate_typical_duration(session, series.id)
        assert result is not None
        # 15 riders, winner time = 10800s = 180min
        assert result["winner_duration_minutes"] == 180.0
        assert result["field_duration_minutes"] > 0
        assert result["edition_count"] == 1

    def test_tt_suppressed(self, session):
        """Time trials should return None."""
        series = _create_speed_fixture(
            session, "tt_duration", race_type=RaceType.TIME_TRIAL
        )
        result = calculate_typical_duration(session, series.id)
        assert result is None

    def test_no_data(self, session):
        """No editions -> None."""
        series = RaceSeries(normalized_name="no_dur", display_name="No Duration")
        session.add(series)
        session.commit()
        result = calculate_typical_duration(session, series.id)
        assert result is None

    def test_with_category(self, session):
        """Category filter should work."""
        series = _create_speed_fixture(session, "dur_cat")
        result = calculate_typical_duration(session, series.id, category="Cat 3")
        assert result is not None
        assert result["winner_duration_minutes"] > 0

    def test_wrong_category_returns_none(self, session):
        """Non-existent category -> None."""
        series = _create_speed_fixture(session, "dur_nocat")
        result = calculate_typical_duration(session, series.id, category="Nonexistent")
        assert result is None
