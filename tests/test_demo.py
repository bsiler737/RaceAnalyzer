"""Tests for synthetic demo data generation."""

from __future__ import annotations

from raceanalyzer.db.models import (
    Base,
    FinishType,
    Race,
    RaceClassification,
    RaceType,
    Result,
    ScrapeLog,
)
from raceanalyzer.demo import (
    DEMO_ID_BASE,
    DEMO_SCRAPE_STATUS,
    _compute_classification_metrics,
    _coords_to_text,
    _generate_course_coords,
    _generate_times,
    clear_demo_data,
    generate_demo_data,
)


class TestGenerateTimes:
    """Verify time distributions match expected patterns per finish type."""

    def test_bunch_sprint_tight_spread(self):
        results = _generate_times(FinishType.BUNCH_SPRINT, 20, 3600.0)
        finishers = [r for r in results if not r["dnf"]]
        spread = finishers[-1]["gap_to_leader"]
        assert spread < 10.0

    def test_breakaway_has_gap(self):
        results = _generate_times(FinishType.BREAKAWAY, 20, 3600.0)
        finishers = [r for r in results if not r["dnf"]]
        groups = {r["gap_group_id"] for r in finishers}
        assert len(groups) >= 2

    def test_gc_selective_spread_out(self):
        results = _generate_times(FinishType.GC_SELECTIVE, 15, 3600.0)
        finishers = [r for r in results if not r["dnf"]]
        spread = finishers[-1]["gap_to_leader"]
        assert spread > 30.0

    def test_dnf_count_reasonable(self):
        results = _generate_times(FinishType.BUNCH_SPRINT, 30, 3600.0)
        dnf_count = sum(1 for r in results if r["dnf"])
        assert dnf_count <= 3

    def test_all_finish_types_produce_results(self):
        for ft in FinishType:
            results = _generate_times(ft, 15, 3600.0)
            assert len(results) == 15


class TestComputeMetrics:
    def test_single_group_metrics(self):
        results = _generate_times(FinishType.BUNCH_SPRINT, 10, 3600.0)
        metrics = _compute_classification_metrics(results, FinishType.BUNCH_SPRINT)
        assert metrics["num_groups"] >= 1
        assert metrics["cv_of_times"] is not None
        assert metrics["cv_of_times"] < 0.005

    def test_multi_group_has_gap(self):
        results = _generate_times(FinishType.BREAKAWAY, 15, 3600.0)
        metrics = _compute_classification_metrics(results, FinishType.BREAKAWAY)
        assert metrics["num_groups"] >= 2
        assert metrics["gap_to_second_group"] > 0.0


class TestGenerateDemoData:
    def test_creates_expected_counts(self, session):
        summary = generate_demo_data(session, num_races=50, seed=42)
        assert 40 <= summary["races"] <= 60  # ~50 with per-year variance
        assert summary["riders"] == 80
        assert summary["results"] > 0
        assert summary["classifications"] > 0

    def test_races_use_demo_id_range(self, session):
        generate_demo_data(session, num_races=5, seed=42)
        races = session.query(Race).all()
        for race in races:
            assert race.id >= DEMO_ID_BASE

    def test_scrape_logs_marked_demo(self, session):
        generate_demo_data(session, num_races=5, seed=42)
        logs = session.query(ScrapeLog).all()
        for log in logs:
            assert log.status == DEMO_SCRAPE_STATUS

    def test_all_finish_types_represented(self, session):
        generate_demo_data(session, num_races=50, seed=42)
        classifications = session.query(RaceClassification).all()
        found_types = {c.finish_type for c in classifications}
        assert len(found_types) >= 6

    def test_all_states_represented(self, session):
        generate_demo_data(session, num_races=50, seed=42)
        races = session.query(Race).all()
        states = {r.state_province for r in races}
        assert states == {"WA", "OR", "ID", "BC"}

    def test_spans_five_years(self, session):
        generate_demo_data(session, num_races=50, seed=42)
        races = session.query(Race).all()
        years = {r.date.year for r in races}
        assert years == {2020, 2021, 2022, 2023, 2024}

    def test_deterministic_with_same_seed(self, session, engine):
        """Same seed produces identical data."""
        summary1 = generate_demo_data(session, num_races=10, seed=99)
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        summary2 = generate_demo_data(session, num_races=10, seed=99)
        assert summary1 == summary2

    def test_cv_spans_confidence_levels(self, session):
        """CV values should span green/orange/red thresholds."""
        generate_demo_data(session, num_races=50, seed=42)
        classifications = session.query(RaceClassification).all()
        cvs = [c.cv_of_times for c in classifications if c.cv_of_times is not None]
        has_green = any(cv < 0.005 for cv in cvs)
        has_orange = any(0.005 <= cv < 0.015 for cv in cvs)
        has_red = any(cv >= 0.015 for cv in cvs)
        assert has_green, "No high-confidence (green) classifications"
        assert has_orange, "No moderate-confidence (orange) classifications"
        assert has_red, "No low-confidence (red) classifications"

    def test_idempotent_reseed(self, session):
        """Running seed twice doesn't duplicate data."""
        generate_demo_data(session, num_races=10, seed=42)
        count1 = session.query(Race).count()
        generate_demo_data(session, num_races=10, seed=42)
        count2 = session.query(Race).count()
        assert count1 == count2


class TestClearDemoData:
    def test_removes_all_demo_data(self, session):
        generate_demo_data(session, num_races=10, seed=42)
        assert session.query(Race).count() > 0
        clear_demo_data(session)
        assert session.query(Race).count() == 0
        assert session.query(ScrapeLog).count() == 0

    def test_preserves_non_demo_data(self, session):
        """Real data should not be deleted."""
        session.add(Race(id=1, name="Real Race", state_province="WA"))
        session.add(ScrapeLog(race_id=1, status="success"))
        session.commit()

        generate_demo_data(session, num_races=5, seed=42)
        clear_demo_data(session)

        assert session.query(Race).count() == 1
        assert session.query(Race).first().name == "Real Race"

    def test_clear_empty_db_is_noop(self, session):
        summary = clear_demo_data(session)
        assert summary["races"] == 0


class TestCourseCoords:
    def test_generates_coords_for_all_types(self):
        import random
        rng = random.Random(42)
        for rt in RaceType:
            lats, lons = _generate_course_coords("Seattle", rt, rng)
            assert len(lats) >= 5
            assert len(lons) >= 5
            assert len(lats) == len(lons)

    def test_coords_near_city_center(self):
        import random
        rng = random.Random(42)
        lats, lons = _generate_course_coords("Seattle", RaceType.ROAD_RACE, rng)
        assert all(46.0 < lat < 49.0 for lat in lats)
        assert all(-124.0 < lon < -120.0 for lon in lons)

    def test_coords_to_text_roundtrip(self):
        coords = [47.61, 47.62, 47.63]
        text = _coords_to_text(coords)
        parsed = [float(x) for x in text.split(",")]
        for orig, parsed_val in zip(coords, parsed):
            assert abs(orig - parsed_val) < 0.0001


class TestRaceTypeAssignment:
    def test_demo_races_have_race_type(self, session):
        generate_demo_data(session, num_races=10, seed=42)
        races = session.query(Race).all()
        for race in races:
            assert race.race_type is not None
            assert isinstance(race.race_type, RaceType)

    def test_demo_races_have_course_coords(self, session):
        generate_demo_data(session, num_races=10, seed=42)
        races = session.query(Race).all()
        for race in races:
            assert race.course_lat is not None
            assert race.course_lon is not None
            assert "," in race.course_lat
            assert "," in race.course_lon


class TestCarriedPoints:
    def test_some_riders_have_points(self, session):
        generate_demo_data(session, num_races=50, seed=42)
        results_with_points = (
            session.query(Result)
            .filter(Result.carried_points.isnot(None), Result.carried_points > 0)
            .count()
        )
        assert results_with_points > 0

    def test_points_vary_across_riders(self, session):
        generate_demo_data(session, num_races=50, seed=42)
        points = (
            session.query(Result.carried_points)
            .filter(Result.carried_points.isnot(None), Result.carried_points > 0)
            .distinct()
            .all()
        )
        assert len(points) >= 5
