"""Shared test fixtures."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from raceanalyzer.db.models import (
    Base,
    Course,
    CourseType,
    FinishType,
    Race,
    RaceClassification,
    RaceSeries,
    Result,
    Rider,
)


@pytest.fixture
def engine():
    """In-memory SQLite engine with WAL mode."""
    eng = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    """Database session for testing."""
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def seeded_session(session):
    """Session pre-populated with sample races, results, and classifications.

    5 races across 3 years, 2 states, 3 categories, multiple finish types.
    """
    races = [
        Race(id=1, name="Banana Belt RR", date=datetime(2022, 3, 5),
             location="Maryhill", state_province="WA"),
        Race(id=2, name="Cherry Pie Crit", date=datetime(2022, 2, 19),
             location="Niles", state_province="OR"),
        Race(id=3, name="Banana Belt RR", date=datetime(2023, 3, 4),
             location="Maryhill", state_province="WA"),
        Race(id=4, name="PIR Short Track", date=datetime(2023, 6, 10),
             location="Portland", state_province="OR"),
        Race(id=5, name="Banana Belt RR", date=datetime(2024, 3, 3),
             location="Maryhill", state_province="WA"),
    ]
    session.add_all(races)

    finish_types = [
        FinishType.BUNCH_SPRINT,
        FinishType.BREAKAWAY,
        FinishType.BUNCH_SPRINT,
        FinishType.REDUCED_SPRINT,
        FinishType.BREAKAWAY,
    ]
    cv_values = [0.003, 0.012, 0.004, 0.025, 0.008]
    categories = ["Men Cat 1/2", "Men Cat 3", "Women Cat 1/2/3"]

    for race, ft, cv in zip(races, finish_types, cv_values):
        for cat in categories:
            for i in range(10):
                session.add(Result(
                    race_id=race.id,
                    name=f"Rider {i}",
                    place=i + 1,
                    race_category_name=cat,
                    race_time_seconds=3600.0 + i * 2.0,
                    race_time=f"1:00:{i * 2:02d}.00",
                    field_size=10,
                    dnf=False,
                ))
            session.add(RaceClassification(
                race_id=race.id,
                category=cat,
                finish_type=ft,
                num_finishers=10,
                num_groups=1 if ft == FinishType.BUNCH_SPRINT else 3,
                largest_group_size=10 if ft == FinishType.BUNCH_SPRINT else 5,
                largest_group_ratio=1.0 if ft == FinishType.BUNCH_SPRINT else 0.5,
                leader_group_size=10 if ft == FinishType.BUNCH_SPRINT else 3,
                gap_to_second_group=0.0 if ft == FinishType.BUNCH_SPRINT else 30.0,
                cv_of_times=cv,
            ))

    session.commit()
    return session


@pytest.fixture
def seeded_series_session(seeded_session):
    """Seeded session with series groupings built."""
    from raceanalyzer.series import build_series

    build_series(seeded_session)
    return seeded_session


@pytest.fixture
def seeded_course_session(seeded_series_session):
    """Seeded session with series, riders, and sample course data."""
    session = seeded_series_session

    # Add riders linked to results
    riders = []
    for i in range(10):
        rider = Rider(name=f"Rider {i}")
        session.add(rider)
        riders.append(rider)
    session.flush()

    # Link riders to existing results

    results = session.query(Result).all()
    for r in results:
        for rider in riders:
            if r.name == rider.name:
                r.rider_id = rider.id
                break

    # Add a course for the first series
    series = session.query(RaceSeries).first()
    if series:
        course = Course(
            series_id=series.id,
            rwgps_route_id=12345,
            distance_m=85000.0,
            total_gain_m=850.0,
            total_loss_m=830.0,
            max_elevation_m=450.0,
            min_elevation_m=50.0,
            m_per_km=10.0,
            course_type=CourseType.ROLLING,
            extracted_at=datetime(2024, 1, 15),
            source="rwgps",
        )
        session.add(course)

    session.commit()
    return session
