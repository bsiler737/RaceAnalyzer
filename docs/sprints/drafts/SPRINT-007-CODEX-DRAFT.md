# Sprint 007: Schema Foundation, Baseline Predictions & Race Preview

## Overview

This sprint pivots RaceAnalyzer from a backward-looking race archive into a forward-looking decision tool. The target user story is concrete: a Cat 3 racer in Seattle checks their phone Saturday morning, sees that Seward Park Crit is "Likely Bunch Sprint" with 47m elevation, notices that three riders with 200+ carried_points are registered, and decides to drive down to Mason Lake Road Race instead because it suits their climbing legs. That decision loop -- see predictions, compare options, pick a race -- is what we ship.

The sprint has six deliverables but they are not equal. Schema changes (deliverable 1) and elevation extraction (deliverable 2) are pure plumbing -- they unblock everything else but deliver zero user value alone. Baseline predictions (deliverables 3-4) are the analytical core. The Race Preview page (deliverable 5) is where users actually see value. The upcoming calendar + startlists (deliverable 6) is the highest-risk, most-deferrable piece. If time runs short, cut deliverable 6 first -- historical performers at a series are 70% as useful as a real startlist, and we already have `get_scary_racers()` doing exactly that.

Engineering approach: extend existing patterns aggressively. The codebase already has a clean CLI-command-per-feature pattern, a queries.py layer that returns DataFrames, and Streamlit pages that compose query results into cards. We add four new tables, two new CLI commands, three new query functions, and one new page. No new architectural patterns. No new dependencies except for BikeReg HTTP calls (and even those use the existing `requests` + `responses` testing pattern). Ship the minimum viable version of each deliverable, then layer polish in a final phase.

---

## Use Cases

1. **As a racer**, I see terrain classification ("Rolling -- 8.2 m/km") on the Race Preview page so I know whether to expect a sprint or a selection.
2. **As a racer**, I see "Predicted: Small Group Sprint (based on 6 editions)" on the Race Preview page with a confidence badge, so I can plan tactics.
3. **As a racer**, I see "Top Contenders" ranked by carried_points percentile on the Race Preview page, so I know who to watch.
4. **As a racer**, I see upcoming races on the calendar page with registration links and predicted finish types, so I can pick a race for this weekend.
5. **As a racer**, I can view a Race Preview for an upcoming race even when no startlist exists -- the system falls back to "riders who've raced this series before."
6. **As a developer**, I can run `raceanalyzer elevation-extract` to populate the courses table from RWGPS route data.
7. **As a developer**, I can run `raceanalyzer scrape-startlists` to fetch BikeReg registrations for upcoming PNW races.
8. **As a developer**, I can verify prediction quality by comparing the heuristic finish-type predictor against a "most common for category" baseline.

---

## Architecture

```
raceanalyzer/
├── db/
│   └── models.py              # MODIFY: Add Course, CourseType enum, rating cols on
│                               #   Rider/Result, Startlist, UserLabel tables
├── queries.py                 # MODIFY: Add predict_finish_type(), predict_contenders(),
│                              #   get_upcoming_races(), get_race_preview()
├── rwgps.py                   # MODIFY: Add extract_elevation_stats() from route JSON
├── elevation.py               # CREATE: Terrain classification logic (m/km -> 4-bin)
├── predictions.py             # CREATE: Baseline heuristic prediction functions
├── startlists.py              # CREATE: BikeReg client + startlist parsing
├── ui/
│   └── pages/
│       └── race_preview.py    # CREATE: Race Preview page (mobile-first)
│   └── components.py          # MODIFY: Add prediction cards, contender cards
│   └── pages/
│       └── calendar.py        # MODIFY: Add upcoming races section
├── cli.py                     # MODIFY: Add elevation-extract, scrape-startlists commands

tests/
├── test_elevation.py          # CREATE: Terrain classification, m/km edge cases
├── test_predictions.py        # CREATE: Finish type prediction, contender ranking
├── test_startlists.py         # CREATE: BikeReg response parsing, graceful degradation
├── test_queries.py            # MODIFY: Upcoming race queries, preview data assembly
```

### Data Flow

```
RWGPS route JSON ──extract_elevation_stats()──> Course row (total_gain, distance, m_per_km, course_type)
                                                       │
Historical RaceClassification rows ─────────────────┐  │
                                                     ▼  ▼
                                              predict_finish_type()
                                                     │
                                                     ▼
BikeReg / historical riders ──predict_contenders()──> contender list
                                                     │
                                                     ▼
                                              get_race_preview() ──> Race Preview page
```

### Key Design Decisions

1. **Course table is series-level, not race-level.** A course belongs to a `RaceSeries`. Year-over-year course changes are rare in PNW; when they happen, create a new Course row. Defer `course_version` tracking (distance +/- 1km, gain +/- 50m) to Sprint 008 -- we do not have enough data to need it yet.

2. **Predictions live in `predictions.py`, not in `classification/`.** The classification module answers "what happened?" (past tense). Predictions answer "what will happen?" (future tense). Different modules, different test files, different confidence semantics. No shared code beyond the `FinishType` enum.

3. **Rating columns added now, populated later.** `Rider.mu`, `Rider.sigma` and `Result.prior_mu`, `Result.prior_sigma`, `Result.mu`, `Result.sigma` columns are created in this sprint but default to NULL. Glicko-2 population is Sprint 008. Adding columns now avoids a second migration.

4. **Startlist scraping is best-effort.** BikeReg's API stability is unknown. The startlist feature degrades in three tiers: (a) BikeReg registered riders, (b) historical performers at this series via `get_scary_racers()`, (c) top-rated riders in this category. Tier (b) already works today.

5. **No probabilities shown to users.** Per research-findings.md, we show qualitative labels ("Likely", "Probable", "Possible") and natural language ("Predicted: Bunch Sprint"). No percentages, no decimal scores. Calibration is a Sprint 008 concern.

6. **Mobile-first means card-based.** The Race Preview page uses `st.container()` cards, not tables. Each card is one information chunk: terrain, prediction, contenders. Designed for a phone screen in portrait orientation.

---

## Scope Ladder

### Must Ship (MVP -- cuts nothing users notice)
- [ ] Schema: `courses` table, `startlists` table, `user_labels` table, rating columns on `Rider`/`Result`
- [ ] `elevation-extract` CLI: populate courses from RWGPS route data
- [ ] 4-bin terrain classification (flat/rolling/hilly/mountainous)
- [ ] Baseline finish-type prediction from historical series data
- [ ] Baseline contender ranking from carried_points percentile
- [ ] Race Preview page showing terrain + prediction + contenders

### Should Ship (high value, moderate risk)
- [ ] Upcoming races section on calendar page (from BikeReg event scraping)
- [ ] BikeReg startlist integration for contender list
- [ ] `scrape-startlists` CLI command

### Nice to Have (cut first)
- [ ] User labels table with post-race feedback prompt
- [ ] Registration links on upcoming race tiles
- [ ] Confidence indicators comparing prediction to "most common for category" baseline

---

## Implementation

### Phase 1: Schema & Elevation (40% of effort)

**Files:**

| File | Action |
|------|--------|
| `raceanalyzer/db/models.py` | MODIFY |
| `raceanalyzer/rwgps.py` | MODIFY |
| `raceanalyzer/elevation.py` | CREATE |
| `raceanalyzer/cli.py` | MODIFY |
| `tests/test_elevation.py` | CREATE |

**Tasks:**

1. **Add `CourseType` enum and `Course` model to `models.py`:**

```python
class CourseType(enum.Enum):
    FLAT = "flat"                  # <5 m/km
    ROLLING = "rolling"            # 5-10 m/km
    HILLY = "hilly"                # 10-15 m/km
    MOUNTAINOUS = "mountainous"    # >15 m/km
    UNKNOWN = "unknown"

class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    series_id = Column(Integer, ForeignKey("race_series.id"), nullable=False, unique=True)
    rwgps_route_id = Column(Integer, nullable=True)
    distance_m = Column(Float, nullable=True)       # Route distance in meters
    total_gain_m = Column(Float, nullable=True)      # Total elevation gain in meters
    m_per_km = Column(Float, nullable=True)          # Computed: total_gain_m / (distance_m / 1000)
    course_type = Column(SAEnum(CourseType), nullable=True)

    series = relationship("RaceSeries", backref="course")

    __table_args__ = (
        Index("ix_courses_series_id", "series_id"),
        Index("ix_courses_course_type", "course_type"),
    )
```

2. **Add rating columns to `Rider` and `Result`:**

```python
# On Rider:
mu = Column(Float, nullable=True)          # Current Glicko-2 rating (Sprint 008)
sigma = Column(Float, nullable=True)       # Current rating uncertainty
num_rated_races = Column(Integer, default=0)

# On Result:
prior_mu = Column(Float, nullable=True)    # Rating before this race
prior_sigma = Column(Float, nullable=True)
mu = Column(Float, nullable=True)          # Rating after this race
sigma = Column(Float, nullable=True)
```

3. **Add `Startlist` and `UserLabel` models:**

```python
class Startlist(Base):
    __tablename__ = "startlists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    series_id = Column(Integer, ForeignKey("race_series.id"), nullable=False)
    category = Column(String, nullable=False)
    rider_name = Column(String, nullable=False)
    rider_id = Column(Integer, ForeignKey("riders.id"), nullable=True)
    source = Column(String, nullable=False)    # "bikereg", "obra", "manual"
    registration_date = Column(DateTime, nullable=True)
    scraped_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_startlists_series_cat", "series_id", "category"),
    )

class UserLabel(Base):
    __tablename__ = "user_labels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=False)
    category = Column(String, nullable=False)
    labeled_finish_type = Column(SAEnum(FinishType), nullable=False)
    is_correct = Column(Boolean, nullable=True)   # True = confirmed prediction, False = corrected
    created_at = Column(DateTime, nullable=False)
```

4. **Add `extract_elevation_stats()` to `rwgps.py`:**

```python
def extract_elevation_stats(route_id: int) -> Optional[dict]:
    """Fetch route detail and extract elevation stats.

    Returns: {"distance_m": float, "total_gain_m": float, "m_per_km": float} or None.
    """
    resp = requests.get(
        _RWGPS_ROUTE_URL.format(route_id=route_id),
        headers={"User-Agent": "RaceAnalyzer/0.1"},
        timeout=15,
    )
    if not resp.ok:
        return None
    data = resp.json()
    distance = data.get("distance")        # meters
    gain = data.get("elevation_gain")       # meters
    if not distance or not gain:
        # Fallback: compute from track_points if available
        track = data.get("track_points", [])
        if track:
            distance, gain = _compute_from_track(track)
    if not distance or distance <= 0:
        return None
    m_per_km = gain / (distance / 1000.0)
    return {"distance_m": distance, "total_gain_m": gain, "m_per_km": m_per_km}
```

5. **Create `elevation.py` with terrain classifier:**

```python
"""Terrain classification from elevation statistics."""

from raceanalyzer.db.models import CourseType

# Thresholds from mid-plan-improvements.md Section 2a
_THRESHOLDS = [
    (5.0, CourseType.FLAT),
    (10.0, CourseType.ROLLING),
    (15.0, CourseType.HILLY),
]

def classify_terrain(m_per_km: float) -> CourseType:
    """Classify course terrain from meters-of-gain per kilometer.

    Flat: <5 m/km, Rolling: 5-10, Hilly: 10-15, Mountainous: >15.
    """
    for threshold, course_type in _THRESHOLDS:
        if m_per_km < threshold:
            return course_type
    return CourseType.MOUNTAINOUS

COURSE_TYPE_DISPLAY = {
    "flat": "Flat",
    "rolling": "Rolling",
    "hilly": "Hilly",
    "mountainous": "Mountainous",
    "unknown": "Unknown Terrain",
}

def course_type_display(course_type_value: str) -> str:
    return COURSE_TYPE_DISPLAY.get(course_type_value, course_type_value.title())
```

6. **Add `elevation-extract` CLI command:**

```python
@main.command("elevation-extract")
@click.option("--series-id", type=int, help="Extract for a single series.")
@click.option("--all", "extract_all", is_flag=True, help="Extract for all series with RWGPS routes.")
@click.pass_context
def elevation_extract(ctx, series_id, extract_all):
    """Extract elevation stats from RWGPS routes and populate courses table."""
```

The command iterates series with `rwgps_route_id` set, calls `extract_elevation_stats()`, creates/updates `Course` rows, classifies terrain. Rate limit: 1 request/second. Idempotent -- skips series that already have a Course row unless `--force` is passed.

7. **Tests (`tests/test_elevation.py`):**
   - `test_classify_terrain_flat` -- 3.0 m/km -> FLAT
   - `test_classify_terrain_rolling` -- 7.5 m/km -> ROLLING
   - `test_classify_terrain_hilly` -- 12.0 m/km -> HILLY
   - `test_classify_terrain_mountainous` -- 18.0 m/km -> MOUNTAINOUS
   - `test_classify_terrain_boundary` -- 5.0 m/km -> ROLLING (boundary is exclusive lower)
   - `test_extract_elevation_stats_from_route_json` -- mock RWGPS response with `responses` library
   - `test_extract_elevation_stats_fallback_to_trackpoints` -- mock response without summary fields
   - `test_extract_elevation_stats_missing_data` -- returns None

---

### Phase 2: Baseline Predictions (30% of effort)

**Files:**

| File | Action |
|------|--------|
| `raceanalyzer/predictions.py` | CREATE |
| `raceanalyzer/queries.py` | MODIFY |
| `tests/test_predictions.py` | CREATE |

**Tasks:**

1. **Create `predictions.py` with two baseline heuristics:**

```python
"""Baseline heuristic predictions. Every future model must beat these."""

from __future__ import annotations
from typing import Optional
import pandas as pd
from sqlalchemy.orm import Session
from raceanalyzer.db.models import (
    FinishType, Race, RaceClassification, RaceSeries, Result,
)


def predict_series_finish_type(
    session: Session,
    series_id: int,
    category: Optional[str] = None,
) -> dict:
    """Predict finish type for next edition of a series.

    Algorithm: weighted frequency of historical finish types for this series.
    Recent editions weighted 2x. If category is provided, filter to that
    category; otherwise use all categories.

    Returns: {
        "predicted_finish_type": FinishType value string,
        "confidence": "high" | "moderate" | "low",
        "edition_count": int,
        "distribution": dict[str, int],  # finish_type -> count
    }
    """

def predict_contenders(
    session: Session,
    series_id: int,
    category: str,
    *,
    top_n: int = 10,
) -> pd.DataFrame:
    """Rank likely top finishers for an upcoming race.

    Algorithm:
    1. If startlist exists for this series+category, rank registered riders
       by carried_points percentile.
    2. Else, find riders who've raced this series before in this category,
       ranked by max carried_points.
    3. Else, find top carried_points riders in this category regionwide.

    Columns: name, team, carried_points, source ("startlist"|"series_history"|"category"),
             wins_in_series, last_raced.
    """
```

2. **Finish-type prediction detail:**

The `predict_series_finish_type` function queries `RaceClassification` rows for all races in the series. It counts finish types, weighting the most recent 2 editions at 2x. The predicted type is the plurality winner. Confidence is:
- "high" if 4+ editions and plurality > 60%
- "moderate" if 2-3 editions or plurality 40-60%
- "low" if 1 edition or plurality < 40%

This is deliberately simple. It is the baseline that Glicko-2 predictions (Sprint 008) must beat.

3. **Contender prediction detail:**

The `predict_contenders` function implements the three-tier degradation:

```python
# Tier 1: Real startlist
startlist_riders = session.query(Startlist).filter(
    Startlist.series_id == series_id,
    Startlist.category == category,
).all()
if startlist_riders:
    # Join to Result for carried_points, rank by max carried_points
    ...
    return df.assign(source="startlist")

# Tier 2: Historical performers at this series
historical = session.query(Result).join(Race).filter(
    Race.series_id == series_id,
    Result.race_category_name == category,
    Result.rider_id.isnot(None),
    Result.dnf.is_(False),
).all()
if historical:
    # Aggregate per rider: max carried_points, win count, last race date
    ...
    return df.assign(source="series_history")

# Tier 3: Category-wide top riders
# Reuse existing get_scary_racers() pattern
return get_scary_racers(session, race_id=0, category=category, top_n=top_n).assign(
    source="category"
)
```

4. **Add `get_race_preview()` to `queries.py`:**

```python
def get_race_preview(
    session: Session,
    series_id: int,
    category: Optional[str] = None,
) -> Optional[dict]:
    """Assemble all data for the Race Preview page.

    Returns: {
        "series": dict,
        "course": dict | None,        # terrain, distance, gain, map polyline
        "prediction": dict | None,     # predicted finish type + confidence
        "contenders": pd.DataFrame,    # ranked contender list
        "categories": list[str],       # available categories
        "has_startlist": bool,
    }
    """
```

This is a facade function that calls `get_series_detail()`, reads the `Course` row, calls `predict_series_finish_type()`, and calls `predict_contenders()`. Single entry point for the page.

5. **Tests (`tests/test_predictions.py`):**
   - `test_predict_finish_type_single_edition` -- 1 edition -> low confidence
   - `test_predict_finish_type_unanimous` -- 5 editions all BUNCH_SPRINT -> high confidence, BUNCH_SPRINT
   - `test_predict_finish_type_mixed` -- 3 editions, 2 different types -> moderate confidence, plurality wins
   - `test_predict_finish_type_recency_weighting` -- recent editions break ties
   - `test_predict_finish_type_empty_series` -- returns None/unknown
   - `test_predict_contenders_with_startlist` -- tier 1 path
   - `test_predict_contenders_historical_fallback` -- tier 2 path
   - `test_predict_contenders_category_fallback` -- tier 3 path
   - `test_predict_contenders_empty` -- graceful empty DataFrame
   - `test_heuristic_beats_random_baseline` -- on seeded demo data, heuristic accuracy > 1/num_finish_types

---

### Phase 3: Race Preview Page (20% of effort)

**Files:**

| File | Action |
|------|--------|
| `raceanalyzer/ui/pages/race_preview.py` | CREATE |
| `raceanalyzer/ui/components.py` | MODIFY |
| `raceanalyzer/ui/pages/calendar.py` | MODIFY |

**Tasks:**

1. **Create `race_preview.py` page:**

```python
"""Race Preview page -- forward-looking race analysis."""

def render():
    session = st.session_state.db_session
    series_id = st.query_params.get("series_id")
    # ...

    preview = queries.get_race_preview(session, int(series_id), category=selected_cat)

    # Card 1: Terrain
    with st.container():
        st.subheader("Course Profile")
        if preview["course"]:
            course = preview["course"]
            col1, col2, col3 = st.columns(3)
            col1.metric("Terrain", course_type_display(course["course_type"]))
            col2.metric("Elevation", f"{course['total_gain_m']:.0f}m gain")
            col3.metric("Distance", f"{course['distance_m']/1000:.1f} km")
        # Course map (reuse existing render_course_map)

    # Card 2: Prediction
    with st.container():
        st.subheader("Predicted Finish Type")
        pred = preview["prediction"]
        if pred:
            ft_display = finish_type_display_name(pred["predicted_finish_type"])
            st.markdown(f"### {ft_display}")
            render_confidence_badge(pred["confidence"], ...)
            st.caption(f"Based on {pred['edition_count']} previous editions")
            # Distribution bar
        else:
            st.info("No historical data for predictions yet.")

    # Card 3: Top Contenders
    with st.container():
        st.subheader("Top Contenders")
        contenders = preview["contenders"]
        if not contenders.empty:
            source = contenders["source"].iloc[0]
            if source == "startlist":
                st.caption("From registered riders")
            elif source == "series_history":
                st.caption("Based on past editions (no startlist available)")
            else:
                st.caption("Top-rated riders in this category")

            for _, rider in contenders.iterrows():
                with st.container():
                    col1, col2 = st.columns([3, 1])
                    col1.write(f"**{rider['name']}** — {rider['team']}")
                    col2.write(f"{rider['carried_points']:.0f} pts")
```

2. **Add navigation from calendar/series pages:**
   - Series tile gains a "Preview" button that navigates to `race_preview.py?series_id=X`
   - Series detail page gains a "Preview Next Edition" button at the top

3. **Mobile-first design rules:**
   - All columns are `st.columns([1])` on mobile (single column stacking)
   - No wide tables -- use `st.container()` cards with metric/text pairs
   - Font sizes use Streamlit defaults (no custom CSS hacks)
   - Test at 375px viewport width

---

### Phase 4: Upcoming Calendar & Startlists (10% of effort -- CUT FIRST)

**Files:**

| File | Action |
|------|--------|
| `raceanalyzer/startlists.py` | CREATE |
| `raceanalyzer/cli.py` | MODIFY |
| `raceanalyzer/ui/pages/calendar.py` | MODIFY |
| `tests/test_startlists.py` | CREATE |

**Tasks:**

1. **Create `startlists.py` BikeReg client:**

```python
"""BikeReg startlist and upcoming event integration."""

_BIKEREG_SEARCH_URL = "https://www.bikereg.com/api/search"

def search_upcoming_events(
    region: str = "WA",
    days_ahead: int = 60,
) -> list[dict]:
    """Search BikeReg for upcoming cycling events in a region.

    Returns: [{"name", "date", "url", "location", "categories": [...]}]
    Graceful: returns [] on any failure.
    """

def fetch_startlist(
    event_url: str,
    category: str,
) -> list[dict]:
    """Fetch registered riders for a BikeReg event + category.

    Returns: [{"name", "registration_date"}]
    Graceful: returns [] on any failure.
    """
```

2. **Add `scrape-startlists` CLI command:**

```
$ raceanalyzer scrape-startlists --region WA --days-ahead 60
Found 12 upcoming events on BikeReg.
  Seward Park Crit -> matched series "Seward Park Criterium" (3 categories)
  Mason Lake RR -> matched series "Mason Lake Road Race" (4 categories)
  ...
Scraped 47 startlist entries across 7 matched events.
```

3. **Calendar page: upcoming section.** Add an "Upcoming Races" section above the historical series tiles. Shows BikeReg events matched to existing series, with predicted finish type badge and registration link. Unmatched events shown as plain tiles without predictions.

4. **Tests:** Mock BikeReg HTTP responses with `responses` library. Test: successful parse, empty response, network error, category matching.

**Why this phase is cuttable:** BikeReg API behavior is unknown. If it requires auth, has aggressive rate limits, or returns unparseable HTML, this phase could eat 2+ days of debugging. The Race Preview page works without it -- Tier 2/3 contender fallback covers the use case. Defer to Sprint 008 if BikeReg proves difficult.

---

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/db/models.py` | MODIFY | Add `Course`, `CourseType`, `Startlist`, `UserLabel` models; rating cols on `Rider`/`Result` |
| `raceanalyzer/rwgps.py` | MODIFY | Add `extract_elevation_stats()` to pull gain/distance from route JSON |
| `raceanalyzer/elevation.py` | CREATE | `classify_terrain()` -- 4-bin m/km classification; display helpers |
| `raceanalyzer/predictions.py` | CREATE | `predict_series_finish_type()`, `predict_contenders()` -- baseline heuristics |
| `raceanalyzer/startlists.py` | CREATE | BikeReg client: `search_upcoming_events()`, `fetch_startlist()` |
| `raceanalyzer/queries.py` | MODIFY | Add `get_race_preview()`, `get_upcoming_races()` |
| `raceanalyzer/cli.py` | MODIFY | Add `elevation-extract`, `scrape-startlists` commands |
| `raceanalyzer/ui/pages/race_preview.py` | CREATE | Race Preview page -- terrain + prediction + contenders |
| `raceanalyzer/ui/pages/calendar.py` | MODIFY | Add upcoming races section |
| `raceanalyzer/ui/components.py` | MODIFY | Add prediction card, contender card components |
| `tests/test_elevation.py` | CREATE | Terrain classification unit tests |
| `tests/test_predictions.py` | CREATE | Prediction heuristic tests, baseline comparison |
| `tests/test_startlists.py` | CREATE | BikeReg mock tests |
| `tests/test_queries.py` | MODIFY | Race preview assembly, upcoming race queries |

---

## Definition of Done

- [ ] `Course` table exists with `series_id` FK, `distance_m`, `total_gain_m`, `m_per_km`, `course_type`
- [ ] `Startlist` table exists with `series_id`, `category`, `rider_name`, `source`, `scraped_at`
- [ ] `UserLabel` table exists with `race_id`, `category`, `labeled_finish_type`, `is_correct`
- [ ] `Rider` has `mu`, `sigma`, `num_rated_races` columns (nullable, unpopulated)
- [ ] `Result` has `prior_mu`, `prior_sigma`, `mu`, `sigma` columns (nullable, unpopulated)
- [ ] `raceanalyzer elevation-extract --all` populates courses table from RWGPS routes
- [ ] `classify_terrain()` correctly maps m/km to 4-bin CourseType
- [ ] `predict_series_finish_type()` returns predicted finish type with confidence for any series with 1+ editions
- [ ] `predict_contenders()` returns ranked riders via 3-tier degradation (startlist -> history -> category)
- [ ] Heuristic finish-type predictor accuracy > "predict most common type for category" baseline on demo data
- [ ] Race Preview page renders on mobile viewport (375px) with terrain, prediction, and contenders
- [ ] Race Preview page works with missing data: no course (skip terrain card), no history (show "no data"), no startlist (fall back to history)
- [ ] All new functions have unit tests with `responses` mocking for HTTP calls
- [ ] Test coverage remains >85%
- [ ] No raw probabilities or decimal scores shown to users -- qualitative labels only

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| RWGPS route JSON lacks `elevation_gain`/`distance` fields | Medium | Blocks elevation extraction | Fallback: compute from `track_points` array (sum positive deltas for gain, haversine for distance). Already have track_points in `fetch_route_polyline()`. |
| BikeReg has no public API or requires auth | High | Blocks startlist + upcoming calendar | Cut Phase 4 entirely. Contender prediction falls back to Tier 2 (historical performers). Calendar stays retrospective. Revisit in Sprint 008 with manual CSV import. |
| Prediction heuristic fails to beat random baseline | Low | Undermines prediction credibility | With 6+ editions of PNW series, finish type is usually consistent. If the heuristic genuinely cannot beat random, the signal is that finish types are more variable than expected -- useful finding regardless. |
| Rating columns cause migration issues on existing DB | Low | Dev friction | `ALTER TABLE ADD COLUMN ... DEFAULT NULL` is safe on SQLite. No data migration needed -- columns stay NULL until Sprint 008. |
| Scope creep from "one more feature" on Race Preview | Medium | Sprint slips | The scope ladder is explicit. Phase 4 is pre-designated as cuttable. Race Preview MVP ships with just terrain + prediction + contenders -- no fit score, no weather, no shareable links. |
| Course-to-series mapping assumes stable courses | Low | Wrong terrain data for changed courses | Acceptable for MVP. Mid-plan-improvements.md notes version tracking as future work. Flag in UI: "Course data based on most recent RWGPS route." |

---

## Security Considerations

- **Rate limiting on all HTTP calls**: 1 req/sec for RWGPS (existing pattern), 2 sec base delay for BikeReg (new scraping target). Exponential backoff on 429 responses.
- **No PII in startlists table**: Store rider name (already public on BikeReg) and registration date only. No email, phone, or payment info.
- **User labels are anonymous**: No user identity attached to `UserLabel` rows. Streamlit session-only.
- **BikeReg scraping ethics**: Use REST API if available; fallback to CSV export (which is explicitly offered to users). Do not scrape HTML aggressively. Respect robots.txt.

---

## Dependencies

- **Existing**: `sqlalchemy`, `requests`, `responses` (test), `click`, `streamlit`, `pandas`, `polyline`, `folium`, `streamlit-folium`
- **No new pip dependencies** for Phase 1-3. The entire MVP ships without adding a single package.
- **Phase 4 only**: No new dependencies either -- BikeReg calls use `requests`.

---

## Open Questions

1. **RWGPS route JSON fields**: Does the `/routes/{id}.json` endpoint return `elevation_gain` and `distance` as top-level fields, or are they nested? Need to inspect one real response. If neither exists, we compute from `track_points` (slower but works).

2. **BikeReg API discovery**: Before writing Phase 4 code, spend 30 minutes probing BikeReg's API surface. Check: `/api/search`, `/api/events/{id}/entries`, CSV download links. If nothing works, cut Phase 4 immediately and file a Sprint 008 ticket for manual startlist import.

3. **Prediction granularity**: Should `predict_series_finish_type()` predict per-category or across all categories? Recommendation: **per-category when 3+ editions have data for that category, otherwise fall back to all-category aggregate.** This gives the best balance of accuracy and coverage.

4. **Race Preview page placement**: Recommendation: **standalone top-level page** at `pages/race_preview.py`, not a tab within series detail. Reason: the preview page needs a shareable URL (`?series_id=X&category=Y`) and a clean mobile layout. The series detail page is already dense.

5. **Should elevation data override or supplement existing course maps?** Recommendation: **supplement.** The existing polyline map shows the route shape. The new terrain card shows elevation stats. Both appear on Race Preview. The Course table adds structured data; it does not replace the polyline cache.

6. **Demo data for testing predictions**: Should `seed-demo` generate series with consistent finish types (to validate the heuristic) or random ones (to test edge cases)? Recommendation: **mix.** Generate 5 series with 80%+ consistency (the heuristic should nail these) and 3 series with high variability (the heuristic should report low confidence). This validates both the prediction and the confidence calibration.
