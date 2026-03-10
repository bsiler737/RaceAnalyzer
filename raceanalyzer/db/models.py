"""SQLAlchemy ORM models for RaceAnalyzer.

9 tables: race_series, races, riders, results, race_classifications, scrape_log,
courses, startlists, user_labels.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class RaceType(enum.Enum):
    CRITERIUM = "criterium"
    ROAD_RACE = "road_race"
    HILL_CLIMB = "hill_climb"
    STAGE_RACE = "stage_race"
    TIME_TRIAL = "time_trial"
    GRAVEL = "gravel"
    UNKNOWN = "unknown"


class FinishType(enum.Enum):
    BUNCH_SPRINT = "bunch_sprint"
    SMALL_GROUP_SPRINT = "small_group_sprint"
    BREAKAWAY = "breakaway"
    BREAKAWAY_SELECTIVE = "breakaway_selective"
    REDUCED_SPRINT = "reduced_sprint"
    GC_SELECTIVE = "gc_selective"
    MIXED = "mixed"
    INDIVIDUAL_TT = "individual_tt"
    UNKNOWN = "unknown"


class CourseType(enum.Enum):
    FLAT = "flat"
    ROLLING = "rolling"
    HILLY = "hilly"
    MOUNTAINOUS = "mountainous"
    UNKNOWN = "unknown"


class RaceSeries(Base):
    """A grouping of recurring race editions (e.g., 'Banana Belt Road Race')."""

    __tablename__ = "race_series"

    id = Column(Integer, primary_key=True, autoincrement=True)
    normalized_name = Column(String, nullable=False, unique=True)
    display_name = Column(String, nullable=False)

    # Course map data (applies to all editions unless overridden)
    rwgps_route_id = Column(Integer, nullable=True)
    rwgps_encoded_polyline = Column(Text, nullable=True)
    rwgps_manual_override = Column(Boolean, default=False)

    races = relationship("Race", back_populates="series")

    __table_args__ = (
        Index("ix_race_series_normalized_name", "normalized_name"),
    )


class Race(Base):
    """A race event on a specific date."""

    __tablename__ = "races"

    id = Column(Integer, primary_key=True)  # road-results.com raceID
    name = Column(String, nullable=False)
    date = Column(DateTime, nullable=True)
    location = Column(String, nullable=True)
    state_province = Column(String, nullable=True)
    url = Column(String, nullable=True)
    race_type = Column(SAEnum(RaceType), nullable=True)
    course_lat = Column(Text, nullable=True)  # Comma-separated latitudes
    course_lon = Column(Text, nullable=True)  # Comma-separated longitudes

    # Series grouping
    series_id = Column(Integer, ForeignKey("race_series.id"), nullable=True)

    # Per-race RWGPS route override (if course changed from series default)
    rwgps_route_id = Column(Integer, nullable=True)

    # Upcoming race fields
    registration_url = Column(String, nullable=True)
    registration_source = Column(String, nullable=True)  # "bikereg", "obra"
    is_upcoming = Column(Boolean, default=False)

    series = relationship("RaceSeries", back_populates="races")
    results = relationship("Result", back_populates="race", cascade="all, delete-orphan")
    classifications = relationship(
        "RaceClassification", back_populates="race", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_races_date", "date"),
        Index("ix_races_state", "state_province"),
        Index("ix_races_race_type", "race_type"),
        Index("ix_races_series_id", "series_id"),
    )


class Rider(Base):
    """A deduplicated rider identity."""

    __tablename__ = "riders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    road_results_id = Column(Integer, nullable=True, unique=True)
    license_number = Column(String, nullable=True)

    # Rating columns (populated by Sprint 008 Glicko-2; NULL until then)
    mu = Column(Float, nullable=True)
    sigma = Column(Float, nullable=True)
    rating_updated_at = Column(DateTime, nullable=True)
    num_rated_races = Column(Integer, default=0)

    results = relationship("Result", back_populates="rider")

    __table_args__ = (
        Index("ix_riders_name", "name"),
        Index("ix_riders_rr_id", "road_results_id"),
    )


class Result(Base):
    """One rider's result in one race category."""

    __tablename__ = "results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=False)
    rider_id = Column(Integer, ForeignKey("riders.id"), nullable=True)

    # From JSON API
    place = Column(Integer, nullable=True)
    name = Column(String, nullable=False)
    team = Column(String, nullable=True)
    age = Column(Integer, nullable=True)
    city = Column(String, nullable=True)
    state_province = Column(String, nullable=True)
    license = Column(String, nullable=True)
    race_category_name = Column(String, nullable=True)
    race_time = Column(String, nullable=True)
    race_time_seconds = Column(Float, nullable=True)
    field_size = Column(Integer, nullable=True)
    dnf = Column(Boolean, default=False)
    dq = Column(Boolean, default=False)
    dnp = Column(Boolean, default=False)
    points = Column(Float, nullable=True)
    carried_points = Column(Float, nullable=True)

    # Computed during classification
    gap_group_id = Column(Integer, nullable=True)
    gap_to_leader = Column(Float, nullable=True)

    # Rating snapshot at time of this result (populated by Sprint 008)
    prior_mu = Column(Float, nullable=True)
    prior_sigma = Column(Float, nullable=True)
    mu = Column(Float, nullable=True)
    sigma = Column(Float, nullable=True)

    race = relationship("Race", back_populates="results")
    rider = relationship("Rider", back_populates="results")

    __table_args__ = (
        Index("ix_results_race_cat", "race_id", "race_category_name"),
        Index("ix_results_rider", "rider_id"),
    )


class RaceClassification(Base):
    """Finish type classification for a race + category pair."""

    __tablename__ = "race_classifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=False)
    category = Column(String, nullable=False)
    finish_type = Column(SAEnum(FinishType), nullable=False)

    # Group-structure metrics (for debugging, tuning, future ML)
    num_finishers = Column(Integer, nullable=True)
    num_groups = Column(Integer, nullable=True)
    largest_group_size = Column(Integer, nullable=True)
    largest_group_ratio = Column(Float, nullable=True)
    leader_group_size = Column(Integer, nullable=True)
    gap_to_second_group = Column(Float, nullable=True)
    cv_of_times = Column(Float, nullable=True)
    gap_threshold_used = Column(Float, nullable=True)

    race = relationship("Race", back_populates="classifications")

    __table_args__ = (
        UniqueConstraint("race_id", "category", name="uq_race_category_classification"),
    )


class ScrapeLog(Base):
    """Tracks scraping progress for resumability."""

    __tablename__ = "scrape_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, nullable=False, unique=True)
    status = Column(String, nullable=False)  # success, not_found, error
    scraped_at = Column(DateTime, default=datetime.utcnow)
    error_message = Column(Text, nullable=True)
    result_count = Column(Integer, nullable=True)


class Course(Base):
    """Physical course with elevation data, linked to a race series or individual race."""

    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    series_id = Column(Integer, ForeignKey("race_series.id"), nullable=True)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=True)
    rwgps_route_id = Column(Integer, nullable=True)

    # Elevation stats (from RWGPS or manual entry)
    distance_m = Column(Float, nullable=True)
    total_gain_m = Column(Float, nullable=True)
    total_loss_m = Column(Float, nullable=True)
    max_elevation_m = Column(Float, nullable=True)
    min_elevation_m = Column(Float, nullable=True)

    # Derived classification
    m_per_km = Column(Float, nullable=True)
    course_type = Column(SAEnum(CourseType), nullable=True)

    # Profile data (pre-computed from RWGPS track points)
    profile_json = Column(Text, nullable=True)  # [{d, e, y, x, g}, ...]
    climbs_json = Column(Text, nullable=True)  # [{start_d, end_d, ...}, ...]

    # Metadata
    extracted_at = Column(DateTime, nullable=True)
    source = Column(String, default="rwgps")  # "rwgps", "manual", "strava"

    series = relationship("RaceSeries", backref="courses")

    __table_args__ = (
        Index("ix_courses_series_id", "series_id"),
        Index("ix_courses_race_id", "race_id"),
        Index("ix_courses_rwgps_route_id", "rwgps_route_id"),
    )


class Startlist(Base):
    """Registered riders for an upcoming race category."""

    __tablename__ = "startlists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=True)
    series_id = Column(Integer, ForeignKey("race_series.id"), nullable=True)

    rider_name = Column(String, nullable=False)
    rider_id = Column(Integer, ForeignKey("riders.id"), nullable=True)
    category = Column(String, nullable=True)
    team = Column(String, nullable=True)

    # Source tracking
    source = Column(String, nullable=False)  # "bikereg", "obra", "manual"
    source_url = Column(String, nullable=True)
    scraped_at = Column(DateTime, nullable=False)
    checksum = Column(String, nullable=True)  # Hash of rider list for change detection

    rider = relationship("Rider")

    __table_args__ = (
        Index("ix_startlists_race_id", "race_id"),
        Index("ix_startlists_series_id", "series_id"),
        Index("ix_startlists_rider_id", "rider_id"),
    )


class UserLabel(Base):
    """User-submitted finish type label for training data."""

    __tablename__ = "user_labels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=False)
    category = Column(String, nullable=False)
    predicted_finish_type = Column(SAEnum(FinishType), nullable=False)
    actual_finish_type = Column(SAEnum(FinishType), nullable=True)  # NULL = skip
    is_correct = Column(Boolean, nullable=True)
    submitted_at = Column(DateTime, nullable=False)
    session_id = Column(String, nullable=True)  # Cookie-based dedup

    race = relationship("Race")

    __table_args__ = (
        UniqueConstraint(
            "race_id", "category", "session_id", name="uq_user_label_per_session"
        ),
    )
