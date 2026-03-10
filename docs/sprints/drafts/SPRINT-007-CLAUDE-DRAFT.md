# Sprint 007: Schema Foundation, Baseline Predictions & Race Preview

## Overview

This sprint transforms RaceAnalyzer from a backward-looking analysis tool into a forward-looking race planning platform. The core motivation is simple: a Cat 3 racer in Seattle checking their phone Saturday morning should be able to see upcoming races, understand what kind of finish to expect, and know which competitors are registered -- all in under 30 seconds. Every feature in this sprint serves that single user journey.

The architecture follows a "graceful degradation at every layer" principle. Each prediction component has three tiers: best-case (full data available), degraded (partial data), and fallback (no data at all). A race with no RWGPS route still shows historical finish type predictions. A race with no startlist still shows top historical performers. A brand-new race series with no history still shows category-level averages. The system never shows a blank page; it always communicates what it knows and what it does not know.

Implementation is phased across four stages: schema foundation first (tables and columns that everything else depends on), then elevation extraction and terrain classification (standalone, testable in isolation), then the prediction and startlist layer (depends on schema), and finally the UI surface (depends on all backend work). This ordering minimizes blocked work and allows each phase to be tested independently. The total scope is ambitious -- six deliverables -- but each is deliberately minimal. We build the simplest correct version of each feature, designed to be extended in Sprint 008 with Glicko-2 ratings and richer prediction models.

---

## Use Cases

1. **As a racer**, I can see upcoming PNW races on the calendar page with predicted finish types and registration links, so I can decide which race to target this weekend.
2. **As a racer**, I can open a Race Preview page for an upcoming race and see predicted finish type, terrain classification, course map, and top contenders, so I have everything I need to prepare.
3. **As a racer**, I can see terrain classification (flat/rolling/hilly/mountainous) for any race with a matched RWGPS route, so I know whether the course suits my strengths.
4. **As a racer**, I can see the top 5 contenders for an upcoming race -- either from the startlist (if available) or from historical performers -- so I know who to watch.
5. **As a racer**, I can view Race Preview on my phone with a card-based, mobile-first layout, so I can check race info at the coffee shop before driving to the venue.
6. **As a racer**, I can confirm or deny the predicted finish type after a race ("Was this prediction right?"), generating labeled training data for future model improvements.
7. **As a developer**, I can run `raceanalyzer elevation-extract` to populate course elevation data from RWGPS routes.
8. **As a developer**, I can run `raceanalyzer fetch-startlists` to pull registered riders from BikeReg for upcoming races.
9. **As a developer**, I can run `raceanalyzer fetch-calendar` to import upcoming race dates from BikeReg/OBRA schedules.
10. **As a developer**, I can validate that the baseline heuristic prediction beats a "most-common-finish-type-for-category" random baseline using existing test data.

---

## Architecture

```
raceanalyzer/
├── db/
│   └── models.py              # MODIFY: Add Course, CourseType enum, rating columns
│                               #          on Rider/Result, Startlist, UserLabel tables
├── queries.py                 # MODIFY: Add prediction queries, upcoming race queries,
│                              #          startlist-aware get_scary_racers()
├── rwgps.py                   # MODIFY: Add fetch_route_elevation(), extract elevation
│                              #          stats from RWGPS route detail JSON
├── elevation.py               # CREATE: Terrain classification logic, m/km binning
├── prediction.py              # CREATE: Baseline heuristic prediction engine
├── startlist.py               # CREATE: BikeReg startlist fetcher with graceful degradation
├── calendar_feed.py           # CREATE: Upcoming race calendar scraper (BikeReg/OBRA)
├── config.py                  # MODIFY: Add elevation thresholds, BikeReg settings
├── ui/
│   ├── components.py          # MODIFY: Add terrain badge, contender card, prediction badge
│   ├── pages/
│   │   ├── calendar.py        # MODIFY: Add upcoming races section
│   │   ├── race_preview.py    # CREATE: Race Preview page (mobile-first)
│   │   └── series_detail.py   # MODIFY: Add terrain badge, link to preview
├── cli.py                     # MODIFY: Add elevation-extract, fetch-startlists,
│                              #          fetch-calendar commands

tests/
├── test_elevation.py          # CREATE: Terrain classification, m/km computation
├── test_prediction.py         # CREATE: Baseline heuristic, degradation tiers
├── test_startlist.py          # CREATE: BikeReg parsing, graceful fallback
├── test_calendar_feed.py      # CREATE: Upcoming race parsing
├── test_queries.py            # MODIFY: Prediction queries, upcoming race queries
├── conftest.py                # MODIFY: Add Course fixtures, startlist fixtures
```

### Data Flow

```
RWGPS Route JSON ──► elevation.py ──► Course table (total_gain, distance, m_per_km, course_type)
                                            │
BikeReg/OBRA ──► calendar_feed.py ──► Race table (future dates, reg_url)
                                            │
BikeReg ──► startlist.py ──► Startlist table (rider_name, category, source)
                                            │
                              ┌──────────────┘
                              ▼
                     prediction.py ──► Predicted finish type + top contenders
                              │
                              ▼
                     race_preview.py (Streamlit page)
```

### Key Design Decisions

1. **Separate `Course` model from `RaceSeries`**. A course is a physical route with elevation data; a series is a recurring event. A series may use different courses across years (e.g., Seward Park when the pass is snowed in). The `Course` table links to `RaceSeries` with a nullable FK but can also link directly to individual `Race` rows. This avoids conflating event identity with route identity.

2. **4-bin terrain classification with simple m/km thresholds**. Flat (<5 m/km), Rolling (5-10), Hilly (10-15), Mountainous (>15). These thresholds are stored in `Settings` so they can be tuned without code changes. This is Phase 0 from mid-plan-improvements.md -- deliberately unsophisticated, deliberately correct for the PNW's typical terrain distribution.

3. **Baseline prediction uses carried_points percentile, not raw values**. The heuristic ranks riders by their max carried_points within a category, then predicts finish type from the series' historical distribution. This provides immediate value and establishes a benchmark that Sprint 008's Glicko-2 model must beat.

4. **Three-tier graceful degradation for contender lists**:
   - **Tier 1**: Startlist available -- show registered riders ranked by carried_points.
   - **Tier 2**: No startlist, but race has history -- show "Top riders who've raced this event before" using existing `get_scary_racers()` logic, scoped to the race series.
   - **Tier 3**: No history at all -- show "Top-rated riders in this category in WA/OR."
   Each tier is labeled in the UI so users understand the data source.

5. **BikeReg integration via CSV export first, API second**. BikeReg's "Confirmed Riders" CSV is publicly accessible for most events. The REST API (if available) is secondary. Both share a common parser interface. If neither works, the system silently falls back to Tier 2.

6. **`user_labels` table captures post-race feedback**. After a race date passes, the Race Preview page shows a "Was this prediction right?" prompt. Responses are stored as labeled training data. This is lightweight -- no auth required, cookie-based to avoid duplicate submissions -- and generates the labeled dataset that mid-plan-improvements.md identifies as a P1 gap.

7. **Rating columns (mu, sigma) are added to Rider and Result now but left NULL**. Sprint 008 will populate them with Glicko-2. Adding the columns now avoids a schema migration later and lets queries reference them with `COALESCE(mu, carried_points)` fallback logic.

8. **Mobile-first Race Preview page**. Single-column card layout. Terrain badge and predicted finish type at the top (the two things a racer needs fastest). Course map below. Contender list as expandable cards. No wide tables.

---

## Implementation

### Phase 1: Schema Foundation (~20% effort)

**Files**: `raceanalyzer/db/models.py`, `raceanalyzer/config.py`, `tests/conftest.py`

**Tasks**:

1.1. Add `CourseType` enum to `models.py`:

```python
class CourseType(enum.Enum):
    FLAT = "flat"
    ROLLING = "rolling"
    HILLY = "hilly"
    MOUNTAINOUS = "mountainous"
    UNKNOWN = "unknown"
```

1.2. Add `Course` model:

```python
class Course(Base):
    """Physical course with elevation data, linked to a race series or individual race."""

    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    series_id = Column(Integer, ForeignKey("race_series.id"), nullable=True)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=True)
    rwgps_route_id = Column(Integer, nullable=True)

    # Elevation stats (from RWGPS or manual entry)
    distance_m = Column(Float, nullable=True)       # Total distance in meters
    total_gain_m = Column(Float, nullable=True)      # Total elevation gain in meters
    total_loss_m = Column(Float, nullable=True)      # Total elevation loss in meters
    max_elevation_m = Column(Float, nullable=True)    # Maximum elevation in meters
    min_elevation_m = Column(Float, nullable=True)    # Minimum elevation in meters

    # Derived classification
    m_per_km = Column(Float, nullable=True)          # total_gain_m / (distance_m / 1000)
    course_type = Column(SAEnum(CourseType), nullable=True)

    # Metadata
    extracted_at = Column(DateTime, nullable=True)
    source = Column(String, default="rwgps")          # "rwgps", "manual", "strava"

    series = relationship("RaceSeries", backref="courses")

    __table_args__ = (
        Index("ix_courses_series_id", "series_id"),
        Index("ix_courses_rwgps_route_id", "rwgps_route_id"),
    )
```

1.3. Add rating columns to `Rider`:

```python
# Rating columns (populated by Sprint 008 Glicko-2; NULL until then)
mu = Column(Float, nullable=True)           # Current rating mean
sigma = Column(Float, nullable=True)        # Current rating uncertainty
rating_updated_at = Column(DateTime, nullable=True)
num_rated_races = Column(Integer, default=0)
```

1.4. Add rating snapshot columns to `Result`:

```python
# Rating snapshot at time of this result (populated by Sprint 008)
prior_mu = Column(Float, nullable=True)
prior_sigma = Column(Float, nullable=True)
posterior_mu = Column(Float, nullable=True)
posterior_sigma = Column(Float, nullable=True)
```

1.5. Add `Startlist` model:

```python
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
    source = Column(String, nullable=False)    # "bikereg", "obra", "manual"
    source_url = Column(String, nullable=True)
    scraped_at = Column(DateTime, nullable=False)

    # Dedup
    checksum = Column(String, nullable=True)   # Hash of rider list for change detection

    rider = relationship("Rider")

    __table_args__ = (
        Index("ix_startlists_race_id", "race_id"),
        Index("ix_startlists_series_id", "series_id"),
        Index("ix_startlists_rider_id", "rider_id"),
    )
```

1.6. Add `UserLabel` model:

```python
class UserLabel(Base):
    """User-submitted finish type label for training data."""

    __tablename__ = "user_labels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=False)
    category = Column(String, nullable=False)
    predicted_finish_type = Column(SAEnum(FinishType), nullable=False)
    actual_finish_type = Column(SAEnum(FinishType), nullable=True)  # NULL = "skip"
    is_correct = Column(Boolean, nullable=True)                      # NULL = "skip"
    submitted_at = Column(DateTime, nullable=False)
    session_id = Column(String, nullable=True)  # Cookie-based dedup (no auth)

    race = relationship("Race")

    __table_args__ = (
        UniqueConstraint("race_id", "category", "session_id",
                         name="uq_user_label_per_session"),
    )
```

1.7. Add upcoming race columns to `Race`:

```python
# Upcoming race metadata (for calendar integration)
registration_url = Column(String, nullable=True)
registration_source = Column(String, nullable=True)  # "bikereg", "obra"
is_upcoming = Column(Boolean, default=False)
```

1.8. Add elevation threshold settings to `config.py`:

```python
# Terrain classification thresholds (m/km)
terrain_flat_max: float = 5.0
terrain_rolling_max: float = 10.0
terrain_hilly_max: float = 15.0
# > terrain_hilly_max = mountainous

# BikeReg settings
bikereg_base_url: str = "https://www.bikereg.com"
bikereg_request_delay: float = 2.0

# Prediction settings
prediction_min_editions: int = 2    # Minimum series editions for finish type prediction
prediction_min_results: int = 5     # Minimum results for carried_points ranking
```

1.9. Update `tests/conftest.py` -- add `Course` to imports, create `seeded_course_session` fixture with sample elevation data.

---

### Phase 2: Elevation Extraction & Terrain Classification (~20% effort)

**Files**: `raceanalyzer/rwgps.py`, `raceanalyzer/elevation.py`, `raceanalyzer/cli.py`, `tests/test_elevation.py`

**Tasks**:

2.1. Add `fetch_route_elevation()` to `rwgps.py`:

```python
def fetch_route_elevation(route_id: int) -> Optional[dict]:
    """Fetch elevation stats from RWGPS route detail JSON.

    Returns dict with keys: distance_m, total_gain_m, total_loss_m,
    max_elevation_m, min_elevation_m. Returns None on failure.

    Falls back to computing from track_points if summary stats
    are not present in the RWGPS response.
    """
    try:
        resp = requests.get(
            _RWGPS_ROUTE_URL.format(route_id=route_id),
            headers={"User-Agent": "RaceAnalyzer/0.1"},
            timeout=15,
        )
        if not resp.ok:
            return None

        data = resp.json()

        # Try summary stats first (cheaper, more reliable)
        distance = data.get("distance")  # meters
        gain = data.get("elevation_gain") or data.get("total_elevation_gain")
        loss = data.get("elevation_loss") or data.get("total_elevation_loss")
        max_elev = data.get("max_elevation")
        min_elev = data.get("min_elevation")

        # If summary stats missing, compute from track_points
        if gain is None:
            track = data.get("track_points", [])
            if track:
                stats = _compute_elevation_from_track(track)
                gain = stats.get("total_gain_m")
                loss = stats.get("total_loss_m")
                max_elev = stats.get("max_elevation_m")
                min_elev = stats.get("min_elevation_m")
                if distance is None:
                    distance = stats.get("distance_m")

        if distance is None or gain is None:
            logger.debug("No elevation data for route %d", route_id)
            return None

        return {
            "distance_m": float(distance),
            "total_gain_m": float(gain),
            "total_loss_m": float(loss) if loss else None,
            "max_elevation_m": float(max_elev) if max_elev else None,
            "min_elevation_m": float(min_elev) if min_elev else None,
        }
    except Exception:
        logger.debug("Failed to fetch elevation for route %d", route_id)
        return None


def _compute_elevation_from_track(track_points: list[dict]) -> dict:
    """Compute elevation stats from RWGPS track_points array.

    Each point has 'e' (elevation in meters), 'd' (cumulative distance),
    or 'x'/'y'/'e' format.
    """
    elevations = []
    for p in track_points:
        e = p.get("e", p.get("elevation"))
        if e is not None:
            elevations.append(float(e))

    if not elevations:
        return {}

    total_gain = 0.0
    total_loss = 0.0
    for i in range(1, len(elevations)):
        diff = elevations[i] - elevations[i - 1]
        if diff > 0:
            total_gain += diff
        else:
            total_loss += abs(diff)

    # Distance from last track point's cumulative distance, or None
    distance = None
    last_d = track_points[-1].get("d")
    if last_d is not None:
        distance = float(last_d)

    return {
        "distance_m": distance,
        "total_gain_m": total_gain,
        "total_loss_m": total_loss,
        "max_elevation_m": max(elevations),
        "min_elevation_m": min(elevations),
    }
```

2.2. Create `raceanalyzer/elevation.py`:

```python
"""Terrain classification from elevation data."""

from __future__ import annotations

from typing import Optional

from raceanalyzer.config import Settings
from raceanalyzer.db.models import CourseType


def compute_m_per_km(
    total_gain_m: Optional[float],
    distance_m: Optional[float],
) -> Optional[float]:
    """Compute meters of climbing per kilometer.

    Returns None if inputs are missing or distance is zero.
    """
    if total_gain_m is None or distance_m is None or distance_m <= 0:
        return None
    return total_gain_m / (distance_m / 1000.0)


def classify_terrain(
    m_per_km: Optional[float],
    settings: Optional[Settings] = None,
) -> CourseType:
    """Classify terrain into 4-bin system based on m/km.

    Thresholds from mid-plan-improvements.md:
      Flat:        < 5 m/km
      Rolling:     5-10 m/km
      Hilly:       10-15 m/km
      Mountainous: > 15 m/km

    Returns CourseType.UNKNOWN if m_per_km is None.
    """
    if m_per_km is None:
        return CourseType.UNKNOWN

    if settings is None:
        settings = Settings()

    if m_per_km < settings.terrain_flat_max:
        return CourseType.FLAT
    elif m_per_km < settings.terrain_rolling_max:
        return CourseType.ROLLING
    elif m_per_km < settings.terrain_hilly_max:
        return CourseType.HILLY
    else:
        return CourseType.MOUNTAINOUS


COURSE_TYPE_DISPLAY_NAMES = {
    "flat": "Flat",
    "rolling": "Rolling",
    "hilly": "Hilly",
    "mountainous": "Mountainous",
    "unknown": "Unknown Terrain",
}

COURSE_TYPE_DESCRIPTIONS = {
    "flat": "Minimal climbing. Expect bunch finishes unless wind or tactics break it up.",
    "rolling": "Moderate climbing. Strong all-rounders and punchy riders thrive.",
    "hilly": "Significant climbing. Climbers and breakaway artists have the advantage.",
    "mountainous": "Major climbing. Pure climbers dominate; the field will shatter.",
    "unknown": "No elevation data available for this course.",
}
```

2.3. Add `elevation-extract` CLI command:

```python
@main.command("elevation-extract")
@click.option("--force", is_flag=True, help="Re-extract even if course data exists.")
@click.pass_context
def elevation_extract(ctx, force):
    """Extract elevation data from RWGPS routes and populate courses table."""
    import time
    from datetime import datetime

    settings = ctx.obj["settings"]

    from raceanalyzer.db.engine import get_session, init_db
    from raceanalyzer.db.models import Course, RaceSeries
    from raceanalyzer.elevation import classify_terrain, compute_m_per_km
    from raceanalyzer.rwgps import fetch_route_elevation

    init_db(settings.db_path)
    session = get_session(settings.db_path)

    # Find series with RWGPS routes but no course data
    query = session.query(RaceSeries).filter(
        RaceSeries.rwgps_route_id.isnot(None)
    )
    series_list = query.all()

    extracted = 0
    skipped = 0
    failed = 0

    for series in series_list:
        # Check for existing course data
        existing = (
            session.query(Course)
            .filter(Course.series_id == series.id)
            .first()
        )
        if existing and not force:
            skipped += 1
            continue

        elev = fetch_route_elevation(series.rwgps_route_id)
        if not elev:
            click.echo(f"  {series.display_name}: no elevation data")
            failed += 1
            continue

        m_km = compute_m_per_km(elev["total_gain_m"], elev["distance_m"])
        course_type = classify_terrain(m_km, settings)

        if existing:
            existing.distance_m = elev["distance_m"]
            existing.total_gain_m = elev["total_gain_m"]
            existing.total_loss_m = elev.get("total_loss_m")
            existing.max_elevation_m = elev.get("max_elevation_m")
            existing.min_elevation_m = elev.get("min_elevation_m")
            existing.m_per_km = m_km
            existing.course_type = course_type
            existing.extracted_at = datetime.utcnow()
        else:
            course = Course(
                series_id=series.id,
                rwgps_route_id=series.rwgps_route_id,
                distance_m=elev["distance_m"],
                total_gain_m=elev["total_gain_m"],
                total_loss_m=elev.get("total_loss_m"),
                max_elevation_m=elev.get("max_elevation_m"),
                min_elevation_m=elev.get("min_elevation_m"),
                m_per_km=m_km,
                course_type=course_type,
                extracted_at=datetime.utcnow(),
                source="rwgps",
            )
            session.add(course)

        click.echo(
            f"  {series.display_name}: {elev['total_gain_m']:.0f}m gain, "
            f"{m_km:.1f} m/km -> {course_type.value}"
        )
        extracted += 1

        # Rate limit: 2s between RWGPS requests
        time.sleep(2.0)

    session.commit()
    session.close()
    click.echo(f"Extracted: {extracted}, Skipped: {skipped}, Failed: {failed}")
```

2.4. Create `tests/test_elevation.py`:

- `test_compute_m_per_km_normal` -- 500m gain over 50km = 10.0 m/km
- `test_compute_m_per_km_zero_distance` -- returns None
- `test_compute_m_per_km_none_inputs` -- returns None for None gain or distance
- `test_classify_flat` -- 3.0 m/km -> FLAT
- `test_classify_rolling` -- 7.5 m/km -> ROLLING
- `test_classify_hilly` -- 12.0 m/km -> HILLY
- `test_classify_mountainous` -- 18.0 m/km -> MOUNTAINOUS
- `test_classify_unknown_none` -- None -> UNKNOWN
- `test_classify_boundary_exact` -- 5.0 m/km -> ROLLING (boundary is exclusive for flat)
- `test_classify_custom_thresholds` -- custom Settings overrides default thresholds
- `test_fetch_route_elevation_summary_stats` -- mocked RWGPS response with summary (uses `responses` library)
- `test_fetch_route_elevation_from_track_points` -- mocked response without summary, computes from track
- `test_fetch_route_elevation_network_failure` -- returns None on network error
- `test_compute_elevation_from_track_monotonic_climb` -- all gains, no loss
- `test_compute_elevation_from_track_empty` -- empty track returns empty dict

---

### Phase 3: Baseline Predictions & Startlist Integration (~35% effort)

**Files**: `raceanalyzer/prediction.py`, `raceanalyzer/startlist.py`, `raceanalyzer/calendar_feed.py`, `raceanalyzer/queries.py`, `raceanalyzer/cli.py`, `tests/test_prediction.py`, `tests/test_startlist.py`, `tests/test_calendar_feed.py`

**Tasks**:

3.1. Create `raceanalyzer/prediction.py`:

```python
"""Baseline heuristic prediction engine.

Predicts finish type from historical series data and ranks contenders
by carried_points percentile. This is the benchmark that all future
models (Glicko-2, Bradley-Terry, LambdaMART) must beat.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Optional

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from raceanalyzer.db.models import (
    Course,
    Race,
    RaceClassification,
    RaceSeries,
    Result,
    Startlist,
)


@dataclass
class FinishTypePrediction:
    """Predicted finish type with confidence metadata."""
    predicted_type: str          # FinishType enum value
    confidence: str              # "high", "moderate", "low", "speculative"
    edition_count: int           # Number of historical editions used
    category_count: int          # Number of category-editions used
    distribution: dict[str, int] # {finish_type: count} across history
    source: str                  # "series_history", "category_average", "no_data"


@dataclass
class ContenderPrediction:
    """Ranked contender with source metadata."""
    name: str
    team: str
    carried_points: float
    wins: int
    recent_results: int          # Results in last 12 months
    source: str                  # "startlist", "series_history", "category_top"
    rank: int


def predict_finish_type(
    session: Session,
    series_id: int,
    category: Optional[str] = None,
) -> FinishTypePrediction:
    """Predict finish type for a race series + optional category.

    Strategy:
    1. If series has >= 2 editions with classifications, use historical
       distribution (most common finish type).
    2. If series has < 2 editions, fall back to category-wide average
       across all series.
    3. If no data at all, return UNKNOWN with "no_data" source.

    Confidence mapping:
    - >= 5 editions with same plurality type: "high"
    - 3-4 editions: "moderate"
    - 2 editions: "low"
    - < 2 or fallback: "speculative"
    """
    # Query historical classifications for this series
    query = (
        session.query(RaceClassification.finish_type)
        .join(Race, Race.id == RaceClassification.race_id)
        .filter(Race.series_id == series_id)
    )
    if category:
        query = query.filter(RaceClassification.category == category)

    rows = query.all()

    if len(rows) >= 2:
        counts = Counter(r[0].value for r in rows if r[0].value != "unknown")
        if counts:
            predicted = counts.most_common(1)[0][0]
            edition_count = (
                session.query(func.count(func.distinct(Race.id)))
                .filter(Race.series_id == series_id)
                .scalar()
            ) or 0

            if edition_count >= 5 and counts[predicted] >= len(rows) * 0.4:
                confidence = "high"
            elif edition_count >= 3:
                confidence = "moderate"
            else:
                confidence = "low"

            return FinishTypePrediction(
                predicted_type=predicted,
                confidence=confidence,
                edition_count=edition_count,
                category_count=len(rows),
                distribution=dict(counts),
                source="series_history",
            )

    # Fallback: category-wide average
    cat_query = session.query(RaceClassification.finish_type)
    if category:
        cat_query = cat_query.filter(RaceClassification.category == category)
    cat_rows = cat_query.all()

    if cat_rows:
        counts = Counter(r[0].value for r in cat_rows if r[0].value != "unknown")
        if counts:
            predicted = counts.most_common(1)[0][0]
            return FinishTypePrediction(
                predicted_type=predicted,
                confidence="speculative",
                edition_count=0,
                category_count=len(cat_rows),
                distribution=dict(counts),
                source="category_average",
            )

    return FinishTypePrediction(
        predicted_type="unknown",
        confidence="speculative",
        edition_count=0,
        category_count=0,
        distribution={},
        source="no_data",
    )


def predict_contenders(
    session: Session,
    series_id: int,
    category: str,
    *,
    top_n: int = 5,
) -> list[ContenderPrediction]:
    """Predict top contenders using three-tier graceful degradation.

    Tier 1: Startlist available -- rank registered riders by carried_points.
    Tier 2: No startlist -- rank historical performers at this series.
    Tier 3: No history -- rank top category-wide riders in PNW.
    """
    from datetime import datetime, timedelta

    twelve_months_ago = datetime.utcnow() - timedelta(days=365)

    # Tier 1: Check startlist
    startlist_entries = (
        session.query(Startlist)
        .filter(
            Startlist.series_id == series_id,
            Startlist.category == category,
        )
        .all()
    )

    if startlist_entries:
        return _rank_startlist_riders(
            session, startlist_entries, category, top_n, twelve_months_ago
        )

    # Tier 2: Historical performers at this series
    series_results = (
        session.query(Result)
        .join(Race, Race.id == Result.race_id)
        .filter(
            Race.series_id == series_id,
            Result.race_category_name == category,
            Result.rider_id.isnot(None),
            Result.dnf.is_(False),
        )
        .all()
    )

    if series_results:
        return _rank_historical_performers(
            session, series_results, category, top_n,
            twelve_months_ago, source="series_history",
        )

    # Tier 3: Top category-wide riders in PNW
    pnw_results = (
        session.query(Result)
        .join(Race, Race.id == Result.race_id)
        .filter(
            Result.race_category_name == category,
            Result.rider_id.isnot(None),
            Result.dnf.is_(False),
            Result.carried_points.isnot(None),
            Race.state_province.in_(["WA", "OR", "ID", "BC"]),
        )
        .all()
    )

    if pnw_results:
        return _rank_historical_performers(
            session, pnw_results, category, top_n,
            twelve_months_ago, source="category_top",
        )

    return []


def _rank_startlist_riders(
    session: Session,
    entries: list,
    category: str,
    top_n: int,
    since: "datetime",
) -> list[ContenderPrediction]:
    """Rank startlist entries by carried_points from their result history."""
    rider_stats: dict[str, dict] = {}

    for entry in entries:
        key = entry.rider_name
        if key in rider_stats:
            continue

        # Look up best carried_points and win count
        best_cp = 0.0
        wins = 0
        recent = 0

        if entry.rider_id:
            results = (
                session.query(Result)
                .filter(
                    Result.rider_id == entry.rider_id,
                    Result.race_category_name == category,
                    Result.dnf.is_(False),
                )
                .all()
            )
            for r in results:
                if r.carried_points and r.carried_points > best_cp:
                    best_cp = r.carried_points
                if r.place == 1:
                    wins += 1
                if r.race and r.race.date and r.race.date >= since:
                    recent += 1

        rider_stats[key] = {
            "name": entry.rider_name,
            "team": entry.team or "",
            "carried_points": best_cp,
            "wins": wins,
            "recent_results": recent,
            "source": "startlist",
        }

    ranked = sorted(
        rider_stats.values(),
        key=lambda x: x["carried_points"],
        reverse=True,
    )[:top_n]

    return [
        ContenderPrediction(rank=i + 1, **stats)
        for i, stats in enumerate(ranked)
    ]


def _rank_historical_performers(
    session: Session,
    results: list,
    category: str,
    top_n: int,
    since: "datetime",
    source: str,
) -> list[ContenderPrediction]:
    """Rank riders from historical results by max carried_points."""
    rider_stats: dict[int, dict] = {}

    for r in results:
        if r.rider_id is None:
            continue
        if r.rider_id not in rider_stats:
            rider_stats[r.rider_id] = {
                "name": r.name,
                "team": r.team or "",
                "carried_points": 0.0,
                "wins": 0,
                "recent_results": 0,
                "source": source,
            }
        stats = rider_stats[r.rider_id]
        if r.carried_points and r.carried_points > stats["carried_points"]:
            stats["carried_points"] = r.carried_points
        if r.place == 1:
            stats["wins"] += 1
        if r.race and r.race.date and r.race.date >= since:
            stats["recent_results"] += 1

    ranked = sorted(
        rider_stats.values(),
        key=lambda x: x["carried_points"],
        reverse=True,
    )[:top_n]

    return [
        ContenderPrediction(rank=i + 1, **stats)
        for i, stats in enumerate(ranked)
    ]
```

3.2. Create `raceanalyzer/startlist.py`:

```python
"""BikeReg startlist integration with graceful degradation.

Primary: BikeReg CSV export (publicly accessible for most events).
Secondary: BikeReg REST API (if available).
Fallback: Silent failure -> prediction.py uses Tier 2/3 instead.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
from datetime import datetime
from typing import Optional

import requests

from raceanalyzer.config import Settings

logger = logging.getLogger(__name__)

_BIKEREG_CSV_URL = "https://www.bikereg.com/api/events/{event_id}/registrations.csv"
_BIKEREG_SEARCH_URL = "https://www.bikereg.com/api/search"


def fetch_bikereg_startlist(
    event_id: str,
    settings: Optional[Settings] = None,
) -> Optional[list[dict]]:
    """Fetch registered riders from BikeReg CSV export.

    Returns list of dicts with keys: rider_name, category, team.
    Returns None if the event is not found or access is denied.
    """
    if settings is None:
        settings = Settings()

    try:
        resp = requests.get(
            _BIKEREG_CSV_URL.format(event_id=event_id),
            headers={"User-Agent": "RaceAnalyzer/0.1"},
            timeout=15,
        )
        if resp.status_code == 404:
            logger.debug("BikeReg event %s not found", event_id)
            return None
        if resp.status_code == 403:
            logger.debug("BikeReg event %s access denied", event_id)
            return None
        if not resp.ok:
            logger.debug("BikeReg HTTP %d for event %s", resp.status_code, event_id)
            return None

        return _parse_bikereg_csv(resp.text)
    except requests.RequestException:
        logger.debug("BikeReg request failed for event %s", event_id)
        return None


def _parse_bikereg_csv(csv_text: str) -> list[dict]:
    """Parse BikeReg CSV into structured rider entries.

    Expected columns (case-insensitive): Name, Category, Team.
    Handles missing columns gracefully.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        return []

    # Normalize column names for case-insensitive matching
    col_map = {col.lower().strip(): col for col in reader.fieldnames}
    name_col = col_map.get("name") or col_map.get("rider name") or col_map.get("rider")
    cat_col = col_map.get("category") or col_map.get("cat") or col_map.get("class")
    team_col = col_map.get("team") or col_map.get("club")

    entries = []
    for row in reader:
        name = row.get(name_col, "").strip() if name_col else ""
        if not name:
            continue
        entries.append({
            "rider_name": name,
            "category": row.get(cat_col, "").strip() if cat_col else None,
            "team": row.get(team_col, "").strip() if team_col else None,
        })

    return entries


def compute_startlist_checksum(entries: list[dict]) -> str:
    """Compute SHA-256 hash of sorted rider names for change detection."""
    names = sorted(e["rider_name"] for e in entries)
    return hashlib.sha256("|".join(names).encode()).hexdigest()[:16]


def search_bikereg_events(
    query: str,
    region: str = "WA",
) -> list[dict]:
    """Search BikeReg for upcoming events by name/region.

    Returns list of {event_id, name, date, url}.
    Returns empty list on failure.
    """
    try:
        resp = requests.get(
            _BIKEREG_SEARCH_URL,
            params={"q": query, "region": region},
            headers={"User-Agent": "RaceAnalyzer/0.1"},
            timeout=10,
        )
        if resp.ok:
            data = resp.json()
            events = data if isinstance(data, list) else data.get("events", [])
            return [
                {
                    "event_id": str(e.get("id", "")),
                    "name": e.get("name", ""),
                    "date": e.get("date"),
                    "url": e.get("url", ""),
                }
                for e in events
            ]
    except Exception:
        logger.debug("BikeReg search failed for %s", query)
    return []
```

3.3. Create `raceanalyzer/calendar_feed.py`:

```python
"""Upcoming race calendar integration (BikeReg/OBRA schedules).

Fetches upcoming race dates and registration links for PNW races.
All functions return empty lists on failure -- never raises to caller.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import requests

from raceanalyzer.config import Settings

logger = logging.getLogger(__name__)

_BIKEREG_CALENDAR_URL = "https://www.bikereg.com/api/events"


def fetch_upcoming_races(
    region: str = "WA",
    days_ahead: int = 60,
    settings: Optional[Settings] = None,
) -> list[dict]:
    """Fetch upcoming races from BikeReg calendar API.

    Returns list of {name, date, location, registration_url, event_id, source}.
    Returns empty list on any failure.
    """
    if settings is None:
        settings = Settings()

    try:
        resp = requests.get(
            _BIKEREG_CALENDAR_URL,
            params={
                "region": region,
                "days": days_ahead,
                "discipline": "road",
            },
            headers={"User-Agent": "RaceAnalyzer/0.1"},
            timeout=15,
        )
        if not resp.ok:
            logger.debug("BikeReg calendar HTTP %d", resp.status_code)
            return []

        data = resp.json()
        events = data if isinstance(data, list) else data.get("events", [])

        results = []
        for e in events:
            results.append({
                "name": e.get("name", ""),
                "date": _parse_date(e.get("date")),
                "location": e.get("location", ""),
                "state_province": e.get("state", region),
                "registration_url": e.get("url", ""),
                "event_id": str(e.get("id", "")),
                "source": "bikereg",
            })
        return results
    except Exception:
        logger.debug("BikeReg calendar fetch failed")
        return []


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse date string from BikeReg, handling multiple formats."""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None
```

3.4. Add new query functions to `raceanalyzer/queries.py`:

```python
def get_upcoming_races(
    session: Session,
    *,
    states: Optional[list[str]] = None,
    days_ahead: int = 60,
) -> pd.DataFrame:
    """Return upcoming races (future dates) with predicted finish types.

    Columns: id, name, date, location, state_province, series_id,
    registration_url, predicted_finish_type, terrain_type.
    """
    from datetime import datetime

    now = datetime.utcnow()
    query = session.query(Race).filter(
        Race.date > now,
        Race.is_upcoming.is_(True),
    )
    if states:
        query = query.filter(Race.state_province.in_(states))

    query = query.order_by(Race.date.asc())
    races = query.all()

    columns = [
        "id", "name", "date", "location", "state_province",
        "series_id", "registration_url", "predicted_finish_type", "terrain_type",
    ]
    if not races:
        return pd.DataFrame(columns=columns)

    from raceanalyzer.db.models import Course
    from raceanalyzer.prediction import predict_finish_type

    data = []
    for race in races:
        # Get predicted finish type from series history
        predicted_ft = "unknown"
        if race.series_id:
            pred = predict_finish_type(session, race.series_id)
            predicted_ft = pred.predicted_type

        # Get terrain type from course data
        terrain = "unknown"
        if race.series_id:
            course = (
                session.query(Course)
                .filter(Course.series_id == race.series_id)
                .first()
            )
            if course and course.course_type:
                terrain = course.course_type.value

        data.append({
            "id": race.id,
            "name": race.name,
            "date": race.date,
            "location": race.location,
            "state_province": race.state_province,
            "series_id": race.series_id,
            "registration_url": race.registration_url,
            "predicted_finish_type": predicted_ft,
            "terrain_type": terrain,
        })

    return pd.DataFrame(data, columns=columns)


def get_race_preview(
    session: Session,
    race_id: Optional[int] = None,
    series_id: Optional[int] = None,
    category: Optional[str] = None,
) -> Optional[dict]:
    """Assemble all data for the Race Preview page.

    Returns dict with keys: race, series, prediction, terrain,
    contenders, course_map, categories, data_completeness.

    Every key is always present; values may be None/empty with
    explanatory metadata in data_completeness.
    """
    from raceanalyzer.db.models import Course, RaceSeries
    from raceanalyzer.prediction import predict_contenders, predict_finish_type

    # Resolve race and series
    race = session.get(Race, race_id) if race_id else None
    series = None
    if race and race.series_id:
        series = session.get(RaceSeries, race.series_id)
    elif series_id:
        series = session.get(RaceSeries, series_id)

    if race is None and series is None:
        return None

    sid = series.id if series else None

    # Categories available
    categories = []
    if sid:
        from sqlalchemy import distinct
        cat_rows = (
            session.query(distinct(RaceClassification.category))
            .join(Race, Race.id == RaceClassification.race_id)
            .filter(Race.series_id == sid)
            .all()
        )
        categories = sorted([r[0] for r in cat_rows if r[0]])

    # Prediction
    prediction = predict_finish_type(session, sid, category) if sid else None

    # Terrain
    course = None
    terrain = None
    if sid:
        course = (
            session.query(Course)
            .filter(Course.series_id == sid)
            .first()
        )
        if course:
            terrain = {
                "course_type": course.course_type.value if course.course_type else "unknown",
                "m_per_km": course.m_per_km,
                "total_gain_m": course.total_gain_m,
                "distance_m": course.distance_m,
            }

    # Contenders
    contenders = []
    if sid and category:
        contenders = predict_contenders(session, sid, category)

    # Course map polyline
    polyline = None
    if series:
        polyline = series.rwgps_encoded_polyline

    # Data completeness report
    data_completeness = {
        "has_history": prediction is not None and prediction.source == "series_history",
        "has_terrain": terrain is not None and terrain["course_type"] != "unknown",
        "has_startlist": any(c.source == "startlist" for c in contenders),
        "has_course_map": polyline is not None,
        "has_contenders": len(contenders) > 0,
    }

    return {
        "race": {
            "id": race.id if race else None,
            "name": race.name if race else series.display_name,
            "date": race.date if race else None,
            "location": race.location if race else None,
            "registration_url": race.registration_url if race else None,
        },
        "series": {
            "id": series.id if series else None,
            "display_name": series.display_name if series else None,
        },
        "prediction": prediction,
        "terrain": terrain,
        "contenders": contenders,
        "course_map": polyline,
        "categories": categories,
        "data_completeness": data_completeness,
    }
```

3.5. Add `fetch-startlists` and `fetch-calendar` CLI commands to `cli.py`:

```python
@main.command("fetch-startlists")
@click.option("--event-id", type=str, help="BikeReg event ID to fetch.")
@click.option("--all-upcoming", is_flag=True, help="Fetch for all upcoming races.")
@click.pass_context
def fetch_startlists(ctx, event_id, all_upcoming):
    """Fetch startlists from BikeReg for upcoming races."""
    import time
    from datetime import datetime

    settings = ctx.obj["settings"]
    from raceanalyzer.db.engine import get_session, init_db
    from raceanalyzer.db.models import Race, Startlist
    from raceanalyzer.startlist import (
        compute_startlist_checksum,
        fetch_bikereg_startlist,
    )

    init_db(settings.db_path)
    session = get_session(settings.db_path)

    if event_id:
        event_ids = [event_id]
    elif all_upcoming:
        # Find upcoming races with BikeReg registration URLs
        races = (
            session.query(Race)
            .filter(
                Race.is_upcoming.is_(True),
                Race.registration_source == "bikereg",
                Race.registration_url.isnot(None),
            )
            .all()
        )
        # Extract event IDs from registration URLs
        event_ids = []
        for race in races:
            eid = _extract_bikereg_event_id(race.registration_url)
            if eid:
                event_ids.append(eid)
        click.echo(f"Found {len(event_ids)} upcoming BikeReg events.")
    else:
        click.echo("Provide --event-id or --all-upcoming.", err=True)
        raise SystemExit(1)

    fetched = 0
    for eid in event_ids:
        entries = fetch_bikereg_startlist(eid, settings)
        if entries is None:
            click.echo(f"  Event {eid}: no data (404 or access denied)")
            continue

        checksum = compute_startlist_checksum(entries)
        now = datetime.utcnow()

        for entry in entries:
            session.add(Startlist(
                rider_name=entry["rider_name"],
                category=entry.get("category"),
                team=entry.get("team"),
                source="bikereg",
                source_url=f"https://www.bikereg.com/events/{eid}",
                scraped_at=now,
                checksum=checksum,
            ))

        click.echo(f"  Event {eid}: {len(entries)} riders")
        fetched += 1
        time.sleep(settings.bikereg_request_delay)

    session.commit()
    session.close()
    click.echo(f"Fetched startlists for {fetched} events.")


def _extract_bikereg_event_id(url: str) -> Optional[str]:
    """Extract BikeReg event ID from a registration URL."""
    import re
    match = re.search(r"bikereg\.com/(?:events/)?(\d+)", url or "")
    return match.group(1) if match else None


@main.command("fetch-calendar")
@click.option("--region", default="WA", help="Region code (WA, OR, ID, BC).")
@click.option("--days", default=60, type=int, help="Days ahead to fetch.")
@click.pass_context
def fetch_calendar(ctx, region, days):
    """Import upcoming race dates from BikeReg calendar."""
    settings = ctx.obj["settings"]
    from raceanalyzer.calendar_feed import fetch_upcoming_races
    from raceanalyzer.db.engine import get_session, init_db
    from raceanalyzer.db.models import Race
    from raceanalyzer.series import normalize_race_name

    init_db(settings.db_path)
    session = get_session(settings.db_path)

    events = fetch_upcoming_races(region=region, days_ahead=days, settings=settings)
    click.echo(f"Found {len(events)} upcoming events from BikeReg.")

    created = 0
    linked = 0
    for event in events:
        if not event["name"] or not event["date"]:
            continue

        # Check if race already exists (by name + date)
        existing = (
            session.query(Race)
            .filter(Race.name == event["name"], Race.date == event["date"])
            .first()
        )
        if existing:
            # Update registration info
            existing.registration_url = event["registration_url"]
            existing.registration_source = event["source"]
            existing.is_upcoming = True
            linked += 1
            continue

        # Create new upcoming race
        race = Race(
            name=event["name"],
            date=event["date"],
            location=event.get("location"),
            state_province=event.get("state_province", region),
            registration_url=event["registration_url"],
            registration_source=event["source"],
            is_upcoming=True,
        )

        # Try to link to existing series
        norm = normalize_race_name(event["name"])
        from raceanalyzer.db.models import RaceSeries
        series = (
            session.query(RaceSeries)
            .filter(RaceSeries.normalized_name == norm)
            .first()
        )
        if series:
            race.series_id = series.id
            linked += 1

        session.add(race)
        created += 1

    session.commit()
    session.close()
    click.echo(f"Created {created} new upcoming races, linked {linked} to series.")
```

3.6. Create tests:

**`tests/test_prediction.py`**:
- `test_predict_finish_type_with_history` -- series with 5 editions of bunch sprints predicts bunch sprint with high confidence
- `test_predict_finish_type_mixed_history` -- 3 bunch sprints + 2 breakaways predicts bunch sprint with moderate confidence
- `test_predict_finish_type_no_history` -- unknown series falls back to category average
- `test_predict_finish_type_no_data` -- empty DB returns unknown with no_data source
- `test_predict_finish_type_with_category_filter` -- respects category parameter
- `test_predict_contenders_from_startlist` -- Tier 1: returns startlist riders ranked by carried_points
- `test_predict_contenders_from_history` -- Tier 2: no startlist, uses historical performers
- `test_predict_contenders_from_category` -- Tier 3: no history, uses category-wide top riders
- `test_predict_contenders_empty` -- no data at all returns empty list
- `test_baseline_beats_random` -- verify prediction accuracy > most-common-type baseline on seeded data

**`tests/test_startlist.py`** (uses `responses` library for HTTP mocking):
- `test_parse_bikereg_csv_normal` -- standard CSV with Name, Category, Team columns
- `test_parse_bikereg_csv_missing_columns` -- CSV missing Team column still works
- `test_parse_bikereg_csv_empty` -- empty CSV returns empty list
- `test_parse_bikereg_csv_alternate_headers` -- "Rider Name" instead of "Name"
- `test_fetch_bikereg_startlist_404` -- returns None
- `test_fetch_bikereg_startlist_403` -- returns None
- `test_fetch_bikereg_startlist_network_error` -- returns None
- `test_compute_checksum_deterministic` -- same entries produce same hash
- `test_compute_checksum_order_independent` -- reordered entries produce same hash

**`tests/test_calendar_feed.py`** (uses `responses` library):
- `test_fetch_upcoming_races_success` -- mocked BikeReg response returns parsed events
- `test_fetch_upcoming_races_network_failure` -- returns empty list
- `test_parse_date_multiple_formats` -- handles YYYY-MM-DD, MM/DD/YYYY, ISO

---

### Phase 4: Race Preview Page & Calendar Updates (~25% effort)

**Files**: `raceanalyzer/ui/pages/race_preview.py`, `raceanalyzer/ui/pages/calendar.py`, `raceanalyzer/ui/components.py`, `raceanalyzer/ui/pages/series_detail.py`

**Tasks**:

4.1. Create `raceanalyzer/ui/pages/race_preview.py`:

```python
"""Race Preview page -- mobile-first, forward-looking race analysis.

Layout (single column, card-based for mobile):
1. Race header: name, date, location, registration link
2. Prediction card: predicted finish type + confidence badge
3. Terrain card: course type + elevation summary
4. Course map (Folium polyline, if available)
5. Contenders card: top 5 with source indicator
6. Data completeness indicator
7. User feedback prompt (after race date has passed)
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from raceanalyzer import queries
from raceanalyzer.elevation import COURSE_TYPE_DESCRIPTIONS, COURSE_TYPE_DISPLAY_NAMES
from raceanalyzer.queries import finish_type_display_name


def render():
    session = st.session_state.db_session

    # Back navigation
    if st.button("Back"):
        st.switch_page("pages/calendar.py")

    # Resolve race/series from query params
    race_id = st.query_params.get("race_id")
    series_id = st.query_params.get("series_id")
    if race_id:
        race_id = int(race_id)
    if series_id:
        series_id = int(series_id)

    if not race_id and not series_id:
        st.warning("No race selected.")
        return

    # Get preview data -- always returns something (graceful degradation)
    preview = queries.get_race_preview(
        session, race_id=race_id, series_id=series_id
    )
    if preview is None:
        st.error("Race not found.")
        return

    race = preview["race"]
    prediction = preview["prediction"]
    terrain = preview["terrain"]
    contenders = preview["contenders"]
    completeness = preview["data_completeness"]
    categories = preview["categories"]

    # --- Race Header ---
    st.title(race["name"])
    if race.get("date"):
        st.caption(f"{race['date']:%A, %B %d, %Y}")
    if race.get("location"):
        st.caption(race["location"])
    if race.get("registration_url"):
        st.link_button("Register", race["registration_url"])

    st.divider()

    # --- Category Selector ---
    selected_cat = None
    if categories:
        selected_cat = st.selectbox(
            "Category",
            options=[None] + categories,
            format_func=lambda x: "All Categories" if x is None else x,
        )
        if selected_cat:
            # Refresh preview with category filter
            preview = queries.get_race_preview(
                session,
                race_id=race_id,
                series_id=series_id,
                category=selected_cat,
            )
            prediction = preview["prediction"]
            contenders = preview["contenders"]

    # --- Prediction Card ---
    st.subheader("Predicted Finish Type")
    if prediction and prediction.predicted_type != "unknown":
        ft_display = finish_type_display_name(prediction.predicted_type)
        _render_prediction_badge(ft_display, prediction.confidence)

        # Show distribution on expand
        with st.expander("Historical distribution"):
            for ft, count in sorted(
                prediction.distribution.items(),
                key=lambda x: -x[1],
            ):
                st.text(f"  {finish_type_display_name(ft)}: {count}")
            st.caption(
                f"Based on {prediction.edition_count} editions "
                f"({prediction.source.replace('_', ' ')})"
            )
    else:
        st.info("No prediction available -- this race has no historical data yet.")

    st.divider()

    # --- Terrain Card ---
    st.subheader("Terrain")
    if terrain and terrain["course_type"] != "unknown":
        ct = terrain["course_type"]
        st.markdown(f"**{COURSE_TYPE_DISPLAY_NAMES.get(ct, ct)}**")
        st.caption(COURSE_TYPE_DESCRIPTIONS.get(ct, ""))
        col1, col2 = st.columns(2)
        if terrain.get("total_gain_m"):
            col1.metric("Elevation Gain", f"{terrain['total_gain_m']:.0f} m")
        if terrain.get("distance_m"):
            col2.metric("Distance", f"{terrain['distance_m'] / 1000:.1f} km")
        if terrain.get("m_per_km"):
            st.caption(f"{terrain['m_per_km']:.1f} m/km climbing ratio")
    else:
        st.info("No terrain data -- course elevation has not been mapped yet.")

    # --- Course Map ---
    polyline = preview.get("course_map")
    if polyline:
        st.divider()
        from raceanalyzer.ui.maps import render_course_map
        render_course_map(polyline, race["name"])

    st.divider()

    # --- Contenders Card ---
    st.subheader("Top Contenders")
    if contenders:
        source_label = contenders[0].source.replace("_", " ").title()
        st.caption(f"Source: {source_label}")
        for c in contenders:
            with st.container():
                col1, col2, col3 = st.columns([3, 2, 1])
                col1.markdown(f"**{c.rank}. {c.name}**")
                col2.caption(c.team)
                if c.carried_points > 0:
                    col3.caption(f"{c.carried_points:.0f} pts")
    else:
        st.info(
            "No contender data available. "
            "Check back closer to race day for startlist updates."
        )

    # --- Data Completeness ---
    st.divider()
    missing = [
        k.replace("has_", "").replace("_", " ")
        for k, v in completeness.items()
        if not v
    ]
    if missing:
        st.caption(f"Missing data: {', '.join(missing)}")

    # --- User Feedback Prompt (after race date) ---
    if (
        race.get("date")
        and race["date"] < datetime.utcnow()
        and prediction
        and prediction.predicted_type != "unknown"
    ):
        st.divider()
        st.subheader("Was this prediction right?")
        ft_display = finish_type_display_name(prediction.predicted_type)
        st.write(f"We predicted **{ft_display}** for this race.")

        col1, col2, col3 = st.columns(3)
        if col1.button("Yes, correct"):
            _submit_label(session, race_id, selected_cat, prediction, is_correct=True)
            st.success("Thanks! Your feedback helps improve predictions.")
        if col2.button("No, wrong"):
            _submit_label(session, race_id, selected_cat, prediction, is_correct=False)
            st.info("Thanks! What was the actual finish type?")
        if col3.button("Skip"):
            pass


def _render_prediction_badge(finish_type_name: str, confidence: str):
    """Render a finish type prediction with confidence badge."""
    confidence_colors = {
        "high": "green",
        "moderate": "orange",
        "low": "red",
        "speculative": "gray",
    }
    color = confidence_colors.get(confidence, "gray")
    st.markdown(
        f"**{finish_type_name}** "
        f":{color}[{confidence.title()} confidence]"
    )


def _submit_label(session, race_id, category, prediction, is_correct):
    """Store user feedback as a training label."""
    from raceanalyzer.db.models import FinishType, UserLabel
    from datetime import datetime

    if race_id is None:
        return

    label = UserLabel(
        race_id=race_id,
        category=category or "unknown",
        predicted_finish_type=FinishType(prediction.predicted_type),
        is_correct=is_correct,
        submitted_at=datetime.utcnow(),
    )
    session.add(label)
    session.commit()


render()
```

4.2. Modify `raceanalyzer/ui/pages/calendar.py` -- add an "Upcoming Races" section above the historical series tiles:

```python
# --- Upcoming Races Section ---
st.subheader("Upcoming Races")
upcoming_df = queries.get_upcoming_races(
    session, states=selected_states
)
if not upcoming_df.empty:
    for _, row in upcoming_df.iterrows():
        with st.container():
            col1, col2, col3 = st.columns([3, 2, 1])
            col1.markdown(f"**{row['name']}**")
            if row.get("date"):
                col1.caption(f"{row['date']:%b %d}")
            if row.get("predicted_finish_type") != "unknown":
                ft = finish_type_display_name(row["predicted_finish_type"])
                col2.write(ft)
            if row.get("terrain_type") != "unknown":
                col3.write(COURSE_TYPE_DISPLAY_NAMES.get(row["terrain_type"], ""))
            # Link to preview
            if st.button("Preview", key=f"preview_{row['id']}"):
                st.query_params["race_id"] = str(row["id"])
                st.switch_page("pages/race_preview.py")
else:
    st.info("No upcoming races found. Run `raceanalyzer fetch-calendar` to import.")

st.divider()
# ... existing series tiles below ...
```

4.3. Add terrain badge to `raceanalyzer/ui/components.py`:

```python
COURSE_TYPE_COLORS = {
    "flat": "#4CAF50",
    "rolling": "#FF9800",
    "hilly": "#F44336",
    "mountainous": "#9C27B0",
    "unknown": "#9E9E9E",
}

def render_terrain_badge(course_type: str):
    """Render a colored terrain type badge."""
    from raceanalyzer.elevation import COURSE_TYPE_DISPLAY_NAMES
    display = COURSE_TYPE_DISPLAY_NAMES.get(course_type, course_type)
    color = COURSE_TYPE_COLORS.get(course_type, "#9E9E9E")
    st.markdown(
        f'<span style="background-color:{color};color:white;'
        f'padding:2px 8px;border-radius:4px;font-size:0.85em">'
        f'{display}</span>',
        unsafe_allow_html=True,
    )
```

4.4. Add terrain badge to `series_detail.py` header section, next to the overall classification badge.

---

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/db/models.py` | MODIFY | Add `CourseType` enum, `Course` model, rating columns on `Rider`/`Result`, `Startlist` model, `UserLabel` model, upcoming race columns on `Race` |
| `raceanalyzer/config.py` | MODIFY | Add terrain thresholds, BikeReg settings, prediction settings |
| `raceanalyzer/rwgps.py` | MODIFY | Add `fetch_route_elevation()`, `_compute_elevation_from_track()` |
| `raceanalyzer/elevation.py` | CREATE | `compute_m_per_km()`, `classify_terrain()`, display name/description maps |
| `raceanalyzer/prediction.py` | CREATE | `predict_finish_type()`, `predict_contenders()`, graceful degradation tiers |
| `raceanalyzer/startlist.py` | CREATE | `fetch_bikereg_startlist()`, `_parse_bikereg_csv()`, `compute_startlist_checksum()`, `search_bikereg_events()` |
| `raceanalyzer/calendar_feed.py` | CREATE | `fetch_upcoming_races()`, date parsing |
| `raceanalyzer/queries.py` | MODIFY | Add `get_upcoming_races()`, `get_race_preview()` |
| `raceanalyzer/cli.py` | MODIFY | Add `elevation-extract`, `fetch-startlists`, `fetch-calendar` commands |
| `raceanalyzer/ui/pages/race_preview.py` | CREATE | Mobile-first Race Preview page with prediction, terrain, contenders, feedback |
| `raceanalyzer/ui/pages/calendar.py` | MODIFY | Add upcoming races section above historical tiles |
| `raceanalyzer/ui/components.py` | MODIFY | Add `render_terrain_badge()`, `COURSE_TYPE_COLORS` |
| `raceanalyzer/ui/pages/series_detail.py` | MODIFY | Add terrain badge to header |
| `tests/conftest.py` | MODIFY | Add `Course` import, `seeded_course_session` fixture |
| `tests/test_elevation.py` | CREATE | Terrain classification and m/km computation tests |
| `tests/test_prediction.py` | CREATE | Baseline prediction and contender ranking tests |
| `tests/test_startlist.py` | CREATE | BikeReg CSV parsing and HTTP mocking tests |
| `tests/test_calendar_feed.py` | CREATE | Calendar feed parsing tests |
| `tests/test_queries.py` | MODIFY | Add tests for `get_upcoming_races()`, `get_race_preview()` |

---

## Definition of Done

- [ ] `Course` table created with `distance_m`, `total_gain_m`, `m_per_km`, `course_type` columns
- [ ] Rating columns (`mu`, `sigma`) exist on `Rider` and `Result` (NULL, ready for Sprint 008)
- [ ] `Startlist` and `UserLabel` tables created and tested
- [ ] `raceanalyzer elevation-extract` populates courses table from RWGPS route data
- [ ] Terrain classification correctly bins routes into flat/rolling/hilly/mountainous
- [ ] `predict_finish_type()` returns predictions from series history with confidence labels
- [ ] `predict_contenders()` implements all three degradation tiers (startlist -> series history -> category top)
- [ ] Contender source is always labeled in the UI so users know the data quality
- [ ] BikeReg startlist parsing handles CSV with missing columns without crashing
- [ ] `raceanalyzer fetch-startlists` and `raceanalyzer fetch-calendar` CLI commands work (and degrade gracefully on network failure)
- [ ] Race Preview page renders on mobile viewports (single-column card layout)
- [ ] Race Preview page shows predicted finish type, terrain, course map, and contenders
- [ ] Upcoming races appear on calendar page with predicted finish types
- [ ] User feedback prompt appears on Race Preview after race date has passed
- [ ] All new functions have unit tests with >85% coverage
- [ ] All HTTP calls use `responses` library mocking in tests
- [ ] All CLI commands are idempotent (safe to re-run)
- [ ] No raw probabilities or decimals shown in UI -- only natural language labels and badges
- [ ] System never shows a blank page -- every missing data scenario has a fallback message

---

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| BikeReg API does not exist or is undocumented | Cannot fetch startlists or upcoming calendar | Medium | CSV export fallback. Manual startlist entry. Tier 2/3 degradation means predictions still work without startlists. |
| RWGPS route JSON lacks elevation summary stats | Must compute from track_points (slower, less accurate) | Medium | `_compute_elevation_from_track()` fallback already implemented. Tested with both code paths. |
| BikeReg CSV column names vary across events | Startlist parsing breaks silently | Medium | Case-insensitive column matching with multiple aliases (`Name`, `Rider Name`, `Rider`). Empty results treated as "no startlist" not "error". |
| Sprint scope is 6 deliverables in ~2 weeks | May not finish everything | High | Deliverables are ordered by dependency. Phase 1-2 (schema + elevation) are standalone. Phase 3-4 (prediction + UI) can be scoped down. Startlist integration and upcoming calendar are the most droppable -- they enhance but do not block the core Race Preview feature. |
| Baseline prediction is too simple to be useful | Users lose trust | Low | Explicit confidence labels ("speculative" for sparse data) set expectations. The point is establishing a benchmark, not shipping a production model. Sprint 008 adds Glicko-2. |
| N+1 queries in `get_upcoming_races()` and `get_race_preview()` | Slow page loads with many upcoming races | Low | Acceptable for <50 upcoming races. If performance becomes an issue, precompute predictions via CLI and cache on the Race model. |
| RWGPS rate limiting during elevation extraction | Incomplete course data | Low | 2-second delay between requests. `--force` flag allows re-running for missed routes. Idempotent design means partial runs are safe. |

---

## Security Considerations

- **No authentication on user feedback**: `UserLabel` uses cookie-based `session_id` for dedup, not auth. Acceptable for a local tool; would need auth before any multi-user deployment.
- **BikeReg scraping**: Use conservative rate limiting (2s delay). Respect 403/429 responses by backing off, not retrying aggressively. Never cache or expose personal rider data beyond what is already publicly visible on BikeReg.
- **No secrets in code**: BikeReg endpoints are public. No API keys required for current implementation. If API keys are needed later, they go in environment variables, never in source.
- **SQLite concurrent access**: All CLI commands commit at the end, not per-row. No concurrent write risk with single-user local tool. If Streamlit and CLI run simultaneously, SQLite's WAL mode (already configured) handles it.

---

## Dependencies

- **Existing**: SQLAlchemy 2.0, Streamlit, Folium, Plotly, requests, polyline, Click
- **No new dependencies required**. All new functionality uses existing libraries. `responses` (already in dev deps) for HTTP mocking in tests.
- **Future**: `skelo` (Glicko-2) and `scipy` are planned for Sprint 008 but explicitly not needed here.

---

## Open Questions

1. **BikeReg API surface**: Does BikeReg expose a public REST API for event search and registration lists, or is CSV export the only reliable method? This affects `startlist.py` and `calendar_feed.py` implementation. The current design uses CSV as primary and API as secondary, but the API URLs are speculative.

2. **RWGPS elevation data availability**: Do the undocumented RWGPS search/route endpoints return `elevation_gain` and `distance` in summary fields, or must we always compute from `track_points`? A quick manual test of 3-5 routes would answer this.

3. **Scope cut candidates**: If time runs short, which deliverables should be deferred to Sprint 008?
   - **Recommended to keep**: Schema (Phase 1), Elevation (Phase 2), Prediction (Phase 3a), Race Preview (Phase 4a). These form the minimum viable "Race Preview" experience.
   - **Recommended to defer if needed**: BikeReg startlist integration (3b -- predictions still work via Tier 2/3), upcoming calendar (3c -- users can bookmark series pages directly).

4. **Prediction granularity**: Should `predict_finish_type()` operate per-series (all categories pooled) or per-series-per-category? The current implementation supports both via the optional `category` parameter. Per-category is more accurate but has sparser data. Recommendation: default to per-series, filter to per-category when the user selects one in the UI.

5. **Race Preview page placement**: The current design adds it as a new top-level page (`pages/race_preview.py`). An alternative is to make it a tab on the existing Series Detail page. Recommendation: top-level page for now, since it serves a different intent (forward-looking) than Series Detail (backward-looking).

6. **Course version tracking**: mid-plan-improvements.md mentions keying courses by distance +/-1km and gain +/-50m. This sprint creates a simple `Course` model without version tracking. Deferring versioning to Sprint 008+ when we have enough multi-year course data to validate the matching logic.
