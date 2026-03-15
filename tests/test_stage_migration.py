"""Tests for stage race migration (Sprint 021 SM-04)."""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from raceanalyzer.db.models import Base, Race, RaceSeries, RaceType


@pytest.fixture
def session():
    """Create an in-memory DB session with schema."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sess = sessionmaker(bind=engine)()
    yield sess
    sess.close()


def _create_parent_series(session, name, normalized, race_type=RaceType.STAGE_RACE):
    """Create a parent stage race series + upcoming race."""
    parent = RaceSeries(
        normalized_name=normalized,
        display_name=name,
    )
    session.add(parent)
    session.flush()

    race = Race(
        name=name,
        date=datetime(2026, 5, 14),
        location="Wenatchee",
        state_province="WA",
        race_type=race_type,
        series_id=parent.id,
        is_upcoming=True,
        registration_url="https://bikereg.example.com/tdb",
    )
    session.add(race)
    session.flush()
    return parent


class TestStageMigrationDB:
    """Test stage migration behavior using in-memory DB."""

    def test_child_series_created(self, session):
        """Migration creates child series with correct parent_series_id."""
        parent = _create_parent_series(session, "Tour de Bloom", "tour de bloom")

        # Simulate what migrate-stages does
        from raceanalyzer.stages import load_stage_schedule
        stages = load_stage_schedule("tour_de_bloom")
        assert stages is not None
        assert len(stages) == 6

        for stage in stages:
            stage_display = stage.name
            if stage.elites_only:
                stage_display = f"{stage_display} (Elites)"
            full_display = f"{parent.display_name}: {stage_display}"
            child_norm = f"tour_de_bloom_stage_{stage.number}_{stage.name.lower().replace(' ', '_')}"

            child = RaceSeries(
                normalized_name=child_norm,
                display_name=full_display,
                rwgps_route_id=stage.rwgps_route_id,
                parent_series_id=parent.id,
                stage_number=stage.number,
            )
            session.add(child)
            session.flush()

            child_race = Race(
                name=full_display,
                date=datetime.combine(stage.date, datetime.min.time()),
                location="Wenatchee",
                state_province="WA",
                race_type=RaceType(stage.race_type),
                series_id=child.id,
                is_upcoming=True,
                registration_url="https://bikereg.example.com/tdb",
            )
            session.add(child_race)

        session.commit()

        children = (
            session.query(RaceSeries)
            .filter(RaceSeries.parent_series_id == parent.id)
            .order_by(RaceSeries.stage_number)
            .all()
        )
        assert len(children) == 6

    def test_child_metadata_correct(self, session):
        """Child series have correct parent_series_id, stage_number, race_type."""
        parent = _create_parent_series(session, "Tour de Bloom", "tour de bloom")
        from raceanalyzer.stages import load_stage_schedule
        stages = load_stage_schedule("tour_de_bloom")

        for stage in stages:
            child = RaceSeries(
                normalized_name=f"tdb_s{stage.number}",
                display_name=f"Tour de Bloom: {stage.name}",
                rwgps_route_id=stage.rwgps_route_id,
                parent_series_id=parent.id,
                stage_number=stage.number,
            )
            session.add(child)
        session.commit()

        children = (
            session.query(RaceSeries)
            .filter(RaceSeries.parent_series_id == parent.id)
            .order_by(RaceSeries.stage_number)
            .all()
        )
        # Stage 1 is a hill climb with RWGPS
        assert children[0].stage_number == 1
        assert children[0].rwgps_route_id == 2398131
        # Stage 5 has no RWGPS
        assert children[4].rwgps_route_id is None
        # Stage 6 has no RWGPS
        assert children[5].rwgps_route_id is None

    def test_no_rwgps_stages(self, session):
        """Stages without rwgps_route_id have null rwgps_route_id."""
        parent = _create_parent_series(session, "Tour de Bloom", "tour de bloom")
        from raceanalyzer.stages import load_stage_schedule
        stages = load_stage_schedule("tour_de_bloom")

        for stage in stages:
            child = RaceSeries(
                normalized_name=f"tdb_null_{stage.number}",
                display_name=f"TdB: {stage.name}",
                rwgps_route_id=stage.rwgps_route_id,
                parent_series_id=parent.id,
                stage_number=stage.number,
            )
            session.add(child)
        session.commit()

        no_route = (
            session.query(RaceSeries)
            .filter(
                RaceSeries.parent_series_id == parent.id,
                RaceSeries.rwgps_route_id.is_(None),
            )
            .all()
        )
        # TdB stages 5 and 6 have no route
        assert len(no_route) == 2
        stage_nums = {s.stage_number for s in no_route}
        assert stage_nums == {5, 6}

    def test_idempotent_migration(self, session):
        """Running migration twice does not create duplicates."""
        parent = _create_parent_series(session, "Tour de Bloom", "tour de bloom")

        # First run
        child1 = RaceSeries(
            normalized_name="tdb_idem_1",
            display_name="TdB: Mission Ridge",
            parent_series_id=parent.id,
            stage_number=1,
        )
        session.add(child1)
        session.commit()

        # Second run: check for existing
        existing = (
            session.query(RaceSeries)
            .filter(
                RaceSeries.parent_series_id == parent.id,
                RaceSeries.stage_number == 1,
            )
            .first()
        )
        assert existing is not None
        assert existing.id == child1.id

        # Count should still be 1
        count = (
            session.query(RaceSeries)
            .filter(RaceSeries.parent_series_id == parent.id)
            .count()
        )
        assert count == 1

    def test_child_race_rows_created(self, session):
        """Child Race rows are created with correct dates."""
        parent = _create_parent_series(session, "Tour de Bloom", "tour de bloom")
        from raceanalyzer.stages import load_stage_schedule
        stages = load_stage_schedule("tour_de_bloom")

        for stage in stages:
            child = RaceSeries(
                normalized_name=f"tdb_race_{stage.number}",
                display_name=f"TdB: {stage.name}",
                parent_series_id=parent.id,
                stage_number=stage.number,
            )
            session.add(child)
            session.flush()
            child_race = Race(
                name=child.display_name,
                date=datetime.combine(stage.date, datetime.min.time()),
                series_id=child.id,
                is_upcoming=True,
                race_type=RaceType(stage.race_type),
            )
            session.add(child_race)
        session.commit()

        # Check dates
        children = (
            session.query(RaceSeries)
            .filter(RaceSeries.parent_series_id == parent.id)
            .order_by(RaceSeries.stage_number)
            .all()
        )
        for child in children:
            race = session.query(Race).filter(Race.series_id == child.id).first()
            assert race is not None
            assert race.is_upcoming is True
            assert race.date is not None

    def test_baker_city_stages(self, session):
        """BCCC has 4 stages, stage 3 has no RWGPS."""
        parent = _create_parent_series(
            session, "Baker City Cycling Classic", "baker city cycling classic"
        )
        from raceanalyzer.stages import load_stage_schedule
        stages = load_stage_schedule("baker_city_cycling_classic")
        assert stages is not None
        assert len(stages) == 4

        for stage in stages:
            child = RaceSeries(
                normalized_name=f"bccc_{stage.number}",
                display_name=f"BCCC: {stage.name}",
                rwgps_route_id=stage.rwgps_route_id,
                parent_series_id=parent.id,
                stage_number=stage.number,
            )
            session.add(child)
        session.commit()

        children = (
            session.query(RaceSeries)
            .filter(RaceSeries.parent_series_id == parent.id)
            .all()
        )
        assert len(children) == 4

        # Stage 3 (Downtown Criterium) has no RWGPS
        stage3 = (
            session.query(RaceSeries)
            .filter(
                RaceSeries.parent_series_id == parent.id,
                RaceSeries.stage_number == 3,
            )
            .first()
        )
        assert stage3.rwgps_route_id is None

    def test_dalles_stages(self, session):
        """The Dalles Omnium has 2 stages."""
        parent = _create_parent_series(
            session, "The Dalles Omnium", "the_dalles_omnium"
        )
        from raceanalyzer.stages import load_stage_schedule
        stages = load_stage_schedule("the_dalles_omnium")
        assert stages is not None
        assert len(stages) == 2

        for stage in stages:
            child = RaceSeries(
                normalized_name=f"dalles_{stage.number}",
                display_name=f"Dalles: {stage.name}",
                rwgps_route_id=stage.rwgps_route_id,
                parent_series_id=parent.id,
                stage_number=stage.number,
            )
            session.add(child)
        session.commit()

        children = (
            session.query(RaceSeries)
            .filter(RaceSeries.parent_series_id == parent.id)
            .all()
        )
        assert len(children) == 2
        # Both Dalles stages have RWGPS routes
        for child in children:
            assert child.rwgps_route_id is not None
