"""Tests for stage race preview behavior (Sprint 021 PP-01 through PP-08)."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from raceanalyzer.db.models import (
    Base,
    Course,
    CourseType,
    Race,
    RaceSeries,
    RaceType,
    Startlist,
)
from raceanalyzer.queries import get_race_preview


@pytest.fixture
def session():
    """Create an in-memory DB with parent + child stage series."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sess = sessionmaker(bind=engine)()

    # Parent stage race
    parent = RaceSeries(
        normalized_name="tour de bloom",
        display_name="Tour de Bloom",
    )
    sess.add(parent)
    sess.flush()

    parent_race = Race(
        name="Tour de Bloom",
        date=datetime(2026, 5, 14),
        location="Wenatchee",
        state_province="WA",
        race_type=RaceType.STAGE_RACE,
        series_id=parent.id,
        is_upcoming=True,
        registration_url="https://bikereg.example.com/tdb",
    )
    sess.add(parent_race)
    sess.flush()

    # Parent startlist
    sess.add(Startlist(
        series_id=parent.id,
        rider_name="Alice Fast",
        category="Women Cat 1/2",
        team="Speed Team",
        source="road-results",
        scraped_at=datetime.utcnow(),
    ))

    # Child 1: Mission Ridge Hill Climb (has course data)
    child1 = RaceSeries(
        normalized_name="tdb_stage_1_mission_ridge",
        display_name="Tour de Bloom: Mission Ridge Hill Climb",
        rwgps_route_id=2398131,
        parent_series_id=parent.id,
        stage_number=1,
    )
    sess.add(child1)
    sess.flush()

    child1_race = Race(
        name="Tour de Bloom: Mission Ridge Hill Climb",
        date=datetime(2026, 5, 14),
        location="Wenatchee",
        state_province="WA",
        race_type=RaceType.HILL_CLIMB,
        series_id=child1.id,
        is_upcoming=True,
    )
    sess.add(child1_race)

    # Course for child 1
    sess.add(Course(
        series_id=child1.id,
        rwgps_route_id=2398131,
        distance_m=46500,
        total_gain_m=1243,
        course_type=CourseType.MOUNTAINOUS,
        profile_json='[{"d": 0, "e": 100}]',
    ))

    # Child 2: Waterville Road Race (has course data)
    child2 = RaceSeries(
        normalized_name="tdb_stage_2_waterville",
        display_name="Tour de Bloom: Waterville Road Race",
        rwgps_route_id=46491966,
        parent_series_id=parent.id,
        stage_number=2,
    )
    sess.add(child2)
    sess.flush()

    child2_race = Race(
        name="Tour de Bloom: Waterville Road Race",
        date=datetime(2026, 5, 15),
        location="Wenatchee",
        state_province="WA",
        race_type=RaceType.ROAD_RACE,
        series_id=child2.id,
        is_upcoming=True,
    )
    sess.add(child2_race)

    sess.add(Course(
        series_id=child2.id,
        rwgps_route_id=46491966,
        distance_m=90700,
        total_gain_m=942,
        course_type=CourseType.HILLY,
    ))

    # Child 5: TT (no course data)
    child5 = RaceSeries(
        normalized_name="tdb_stage_5_tt",
        display_name="Tour de Bloom: 19 km Time Trial (Elites)",
        parent_series_id=parent.id,
        stage_number=5,
    )
    sess.add(child5)
    sess.flush()

    child5_race = Race(
        name="Tour de Bloom: 19 km Time Trial (Elites)",
        date=datetime(2026, 5, 18),
        race_type=RaceType.TIME_TRIAL,
        series_id=child5.id,
        is_upcoming=True,
    )
    sess.add(child5_race)

    sess.commit()
    yield sess
    sess.close()


class TestStagePreview:
    def test_child_returns_own_course(self, session):
        """Preview for child series returns stage-specific Course data."""
        # Get child1 (Mission Ridge)
        child1 = session.query(RaceSeries).filter(
            RaceSeries.display_name.like("%Mission Ridge%")
        ).first()
        preview = get_race_preview(session, child1.id)
        assert preview is not None
        assert preview["course"] is not None
        assert preview["course"]["course_type"] == "mountainous"
        assert preview["course"]["distance_m"] == 46500

    def test_child_without_course_returns_none(self, session):
        """Preview for child without Course returns course = None."""
        child5 = session.query(RaceSeries).filter(
            RaceSeries.display_name.like("%Time Trial%")
        ).first()
        preview = get_race_preview(session, child5.id)
        assert preview is not None
        assert preview["course"] is None

    def test_sibling_navigation(self, session):
        """Siblings list is correct and ordered by stage_number."""
        child1 = session.query(RaceSeries).filter(
            RaceSeries.display_name.like("%Mission Ridge%")
        ).first()
        preview = get_race_preview(session, child1.id)
        siblings = preview["series"]["siblings"]
        assert len(siblings) == 3  # 3 children in test fixture
        assert siblings[0]["stage_number"] == 1
        assert siblings[0]["is_current"] is True
        assert siblings[1]["stage_number"] == 2
        assert siblings[1]["is_current"] is False
        assert siblings[2]["stage_number"] == 5
        assert siblings[2]["is_current"] is False

    def test_registration_url_inheritance(self, session):
        """Registration URL falls back to parent's."""
        child1 = session.query(RaceSeries).filter(
            RaceSeries.display_name.like("%Mission Ridge%")
        ).first()
        preview = get_race_preview(session, child1.id)
        assert preview["registration_url"] == "https://bikereg.example.com/tdb"

    def test_startlist_fallback(self, session):
        """Startlist falls back to parent's when child has none."""
        child1 = session.query(RaceSeries).filter(
            RaceSeries.display_name.like("%Mission Ridge%")
        ).first()
        preview = get_race_preview(session, child1.id)
        # Child has no startlist, should fall back to parent
        assert preview["has_startlist"] is True
        parent = session.query(RaceSeries).filter(
            RaceSeries.display_name == "Tour de Bloom"
        ).first()
        assert preview["startlist_source_id"] == parent.id

    def test_history_banner(self, session):
        """Historical data falls back to parent with banner text."""
        child1 = session.query(RaceSeries).filter(
            RaceSeries.display_name.like("%Mission Ridge%")
        ).first()
        preview = get_race_preview(session, child1.id)
        assert preview["history_banner"] is not None
        assert "Tour de Bloom" in preview["history_banner"]
        assert "no stage-specific" in preview["history_banner"]

    def test_parent_series_info(self, session):
        """Stage preview includes parent info."""
        child1 = session.query(RaceSeries).filter(
            RaceSeries.display_name.like("%Mission Ridge%")
        ).first()
        preview = get_race_preview(session, child1.id)
        assert preview["series"]["parent_series_id"] is not None
        assert preview["series"]["parent_display_name"] == "Tour de Bloom"
        assert preview["series"]["stage_number"] == 1

    def test_standalone_series_no_stage_data(self, session):
        """Non-stage series has no stage-related data."""
        standalone = RaceSeries(
            normalized_name="mason lake",
            display_name="Mason Lake Road Race",
        )
        session.add(standalone)
        session.flush()
        race = Race(
            name="Mason Lake Road Race",
            date=datetime(2026, 4, 1),
            race_type=RaceType.ROAD_RACE,
            series_id=standalone.id,
            is_upcoming=True,
        )
        session.add(race)
        session.commit()

        preview = get_race_preview(session, standalone.id)
        assert preview is not None
        assert preview["series"]["parent_series_id"] is None
        assert preview["series"]["siblings"] == []
        assert preview["history_banner"] is None

    def test_different_stages_different_courses(self, session):
        """Two different stages return different course data."""
        child1 = session.query(RaceSeries).filter(
            RaceSeries.display_name.like("%Mission Ridge%")
        ).first()
        child2 = session.query(RaceSeries).filter(
            RaceSeries.display_name.like("%Waterville%")
        ).first()

        preview1 = get_race_preview(session, child1.id)
        preview2 = get_race_preview(session, child2.id)

        assert preview1["course"]["course_type"] == "mountainous"
        assert preview2["course"]["course_type"] == "hilly"
        assert preview1["course"]["distance_m"] != preview2["course"]["distance_m"]
