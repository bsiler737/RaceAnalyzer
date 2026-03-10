# Sprint 007: Schema Foundation, Baseline Predictions & Race Preview

## Overview

This sprint transforms RaceAnalyzer from a backward-looking analysis tool into a forward-looking race planning platform. The core motivation: a Cat 3 racer in Seattle checking their phone Saturday morning should see upcoming races, understand what kind of finish to expect, and know which competitors are registered — all in under 30 seconds. Every feature in this sprint serves that single user journey.

The architecture follows a "graceful degradation at every layer" principle. Each prediction component has three tiers: best-case (full data), degraded (partial data), and fallback (no data at all). A race with no RWGPS route still shows historical finish type predictions. A race with no startlist still shows top historical performers. A brand-new series with no history still shows category-level averages. The system never shows a blank page; it always communicates what it knows and what it lacks.

Implementation is phased across five stages: schema foundation first (tables and columns everything depends on), elevation extraction and terrain classification (standalone, testable in isolation), baseline predictions (depends on schema), startlist and calendar integration (depends on schema, highest external risk), and finally the UI surface (depends on all backend work). The total scope is ambitious — six deliverables — but each is deliberately minimal. We build the simplest correct version of each feature, designed to be extended in Sprint 008 with Glicko-2 ratings and richer prediction models.

**Duration**: ~2-3 weeks
**Prerequisite**: Sprint 006 complete (course maps and series dedup).
**Merged from**: Claude draft (rich Course model, dual FK, graceful degradation, track_points fallback, UserLabel dedup, configurable thresholds), Codex draft (scope ladder, predictions module separation, confidence model, mobile design rules, effort allocation), Gemini draft (phase structure, rate limiting, security concerns).

---

## Use Cases

1. **As a racer**, I can see upcoming PNW races on the calendar page with predicted finish types and registration links, so I can decide which race to target this weekend.
2. **As a racer**, I can open a Race Preview page for an upcoming race and see predicted finish type, terrain classification, course map, and top contenders — everything I need to prepare.
3. **As a racer**, I can see terrain classification (flat/rolling/hilly/mountainous) for any race with a matched RWGPS route, so I know whether the course suits my strengths.
4. **As a racer**, I can see the top 10 contenders for an upcoming race — from the startlist (if available), from historical performers, or from category-wide top riders — so I know who to watch.
5. **As a racer**, I can view Race Preview on my phone with a card-based, mobile-first layout, so I can check race info at the coffee shop before driving to the venue.
6. **As a racer**, I can confirm or deny the predicted finish type after a race ("Was this prediction right?"), helping improve future predictions.
7. **As a developer**, I can run `raceanalyzer elevation-extract` to populate course elevation data from RWGPS routes.
8. **As a developer**, I can run `raceanalyzer fetch-startlists` to pull registered riders from BikeReg for upcoming races.
9. **As a developer**, I can run `raceanalyzer fetch-calendar` to import upcoming race dates from BikeReg/OBRA schedules.
10. **As a developer**, I can validate that the baseline heuristic prediction beats a "most-common-finish-type-for-category" random baseline.

---

## Architecture

```
raceanalyzer/
├── db/
│   └── models.py              # MODIFY: Add Course, CourseType enum, rating columns
│                               #          on Rider/Result, Startlist, UserLabel tables
├── queries.py                 # MODIFY: Add prediction queries, upcoming race queries,
│                              #          race preview assembly
├── rwgps.py                   # MODIFY: Add fetch_route_elevation(), extract elevation
│                              #          stats from RWGPS route detail JSON
├── elevation.py               # CREATE: Terrain classification logic, m/km binning
├── predictions.py             # CREATE: Baseline heuristic prediction engine
├── startlists.py              # CREATE: BikeReg startlist fetcher with graceful degradation
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
├── test_predictions.py        # CREATE: Baseline heuristic, degradation tiers
├── test_startlists.py         # CREATE: BikeReg parsing, graceful fallback
├── test_calendar_feed.py      # CREATE: Upcoming race parsing
├── test_queries.py            # MODIFY: Prediction queries, upcoming race queries
├── conftest.py                # MODIFY: Add Course fixtures, startlist fixtures
```

### Data Flow

```
RWGPS Route JSON ──► elevation.py ──► Course table (gain, loss, distance, m_per_km, course_type)
                                              │
BikeReg/OBRA ──► calendar_feed.py ──► Race table (future dates, reg_url, is_upcoming)
                                              │
BikeReg ──► startlists.py ──► Startlist table (rider_name, category, source)
                                              │
                                ┌─────────────┘
                                ▼
                       predictions.py ──► Predicted finish type + top contenders
                                │
                                ▼
                       race_preview.py (Streamlit page)
                                │
                                ▼ (after race date)
                       UserLabel table ◄── "Was this right?" feedback prompt
```

### Key Design Decisions

1. **Separate `Course` model from `RaceSeries`.** A course is a physical route with elevation data; a series is a recurring event. A series may use different courses across years. The `Course` table links to both `RaceSeries` (default) and individual `Race` rows (override). This avoids conflating event identity with route identity.

2. **Rich Course model with 7 elevation fields.** `distance_m`, `total_gain_m`, `total_loss_m`, `max_elevation_m`, `min_elevation_m`, `m_per_km`, `course_type`. All are available from RWGPS at zero marginal cost during extraction. Storing them now avoids re-scraping in Sprint 008 when scipy peak detection needs min/max elevation.

3. **4-bin terrain classification with configurable m/km thresholds.** Flat (<5), Rolling (5-10), Hilly (10-15), Mountainous (>15). Thresholds stored in `Settings` for tuning without code changes. This is Phase 0 from mid-plan-improvements.md — deliberately unsophisticated, deliberately correct for PNW terrain.

4. **Predictions live in `predictions.py`, not in `classification/`.** The classification module answers "what happened?" (past tense). Predictions answer "what will happen?" (future tense). Different modules, different confidence semantics.

5. **Three-tier graceful degradation for contender lists:**
   - **Tier 1**: Startlist available — show registered riders ranked by carried_points.
   - **Tier 2**: No startlist, but race has history — show "Top riders who've raced this event before."
   - **Tier 3**: No history at all — show "Top-rated riders in this category in WA/OR."
   Each tier is labeled in the UI so users understand the data source.

6. **Rating columns (mu, sigma) added now, populated in Sprint 008.** Avoids a second schema migration. Columns stay NULL until Glicko-2 is implemented.

7. **BikeReg CSV-first, API-second.** BikeReg's "Confirmed Riders" CSV is publicly accessible for most events. The REST API (if available) is secondary. If neither works, the system silently falls back to Tier 2 contenders.

8. **No raw probabilities shown to users.** Per research-findings.md: qualitative labels only ("Likely", "Probable", "Possible"). No percentages, no decimal scores. Calibration is a Sprint 008 concern.

9. **Mobile-first Race Preview page as standalone top-level page.** Card-based single-column layout. Shareable URL (`?series_id=X&category=Y`). Terrain badge and predicted finish type at the top (the two things a racer needs fastest).

10. **Post-race feedback generates labeled training data.** After a race date passes, the Race Preview page shows a "Was this prediction right?" prompt. Responses stored in `user_labels` table with session-based dedup. Solves the labeled data problem identified in mid-plan-improvements.md as a P1 gap.

---

## Scope Ladder

All tiers are targeted for Sprint 007. The ladder serves as contingency guidance if time runs short.

### Must Ship (MVP)
- [ ] Schema: `courses` table (7 fields, dual FK), `startlists` table, `user_labels` table, rating columns on `Rider`/`Result`
- [ ] `elevation-extract` CLI: populate courses from RWGPS route data
- [ ] 4-bin terrain classification (flat/rolling/hilly/mountainous)
- [ ] Baseline finish-type prediction from historical series data
- [ ] Baseline contender ranking from carried_points percentile
- [ ] Race Preview page showing terrain + prediction + contenders

### Should Ship (high value, moderate risk)
- [ ] Upcoming races section on calendar page (from BikeReg event scraping)
- [ ] BikeReg startlist integration for contender list
- [ ] `fetch-startlists` and `fetch-calendar` CLI commands
- [ ] Post-race user feedback prompt ("Was this prediction right?")

### Nice to Have (cut last)
- [ ] Registration links on upcoming race tiles
- [ ] Confidence indicators comparing prediction to "most common for category" baseline
- [ ] Natural language terrain descriptions on preview cards

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
    distance_m = Column(Float, nullable=True)
    total_gain_m = Column(Float, nullable=True)
    total_loss_m = Column(Float, nullable=True)
    max_elevation_m = Column(Float, nullable=True)
    min_elevation_m = Column(Float, nullable=True)

    # Derived classification
    m_per_km = Column(Float, nullable=True)
    course_type = Column(SAEnum(CourseType), nullable=True)

    # Metadata
    extracted_at = Column(DateTime, nullable=True)
    source = Column(String, default="rwgps")  # "rwgps", "manual", "strava"

    series = relationship("RaceSeries", backref="courses")

    __table_args__ = (
        Index("ix_courses_series_id", "series_id"),
        Index("ix_courses_race_id", "race_id"),
        Index("ix_courses_rwgps_route_id", "rwgps_route_id"),
    )
```

1.3. Add rating columns to `Rider`:

```python
# Rating columns (populated by Sprint 008 Glicko-2; NULL until then)
mu = Column(Float, nullable=True)
sigma = Column(Float, nullable=True)
rating_updated_at = Column(DateTime, nullable=True)
num_rated_races = Column(Integer, default=0)
```

1.4. Add rating snapshot columns to `Result`:

```python
# Rating snapshot at time of this result (populated by Sprint 008)
prior_mu = Column(Float, nullable=True)
prior_sigma = Column(Float, nullable=True)
mu = Column(Float, nullable=True)
sigma = Column(Float, nullable=True)
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
    actual_finish_type = Column(SAEnum(FinishType), nullable=True)  # NULL = skip
    is_correct = Column(Boolean, nullable=True)
    submitted_at = Column(DateTime, nullable=False)
    session_id = Column(String, nullable=True)  # Cookie-based dedup

    race = relationship("Race")

    __table_args__ = (
        UniqueConstraint("race_id", "category", "session_id",
                         name="uq_user_label_per_session"),
    )
```

1.7. Add upcoming race columns to `Race`:

```python
registration_url = Column(String, nullable=True)
registration_source = Column(String, nullable=True)  # "bikereg", "obra"
is_upcoming = Column(Boolean, default=False)
```

1.8. Add settings to `config.py`:

```python
# Terrain classification thresholds (m/km)
terrain_flat_max: float = 5.0
terrain_rolling_max: float = 10.0
terrain_hilly_max: float = 15.0

# BikeReg settings
bikereg_base_url: str = "https://www.bikereg.com"
bikereg_request_delay: float = 2.0

# Prediction settings
prediction_min_editions: int = 2
prediction_min_results: int = 5
```

1.9. Update `tests/conftest.py` — add `Course`, `Startlist`, `UserLabel` to imports. Create `seeded_course_session` fixture with sample elevation data.

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
```

The function tries `data.get("elevation_gain")` and `data.get("distance")` first. If those are missing, it falls back to `_compute_elevation_from_track(data.get("track_points", []))` which iterates track points summing positive elevation deltas for gain and negative for loss.

2.2. Create `raceanalyzer/elevation.py`:

```python
"""Terrain classification from elevation data."""

def compute_m_per_km(total_gain_m: Optional[float], distance_m: Optional[float]) -> Optional[float]:
    """Compute meters of climbing per kilometer. Returns None if inputs missing."""

def classify_terrain(m_per_km: Optional[float], settings: Optional[Settings] = None) -> CourseType:
    """Classify terrain into 4-bin system. Returns UNKNOWN if m_per_km is None."""

COURSE_TYPE_DISPLAY_NAMES = {
    "flat": "Flat", "rolling": "Rolling", "hilly": "Hilly",
    "mountainous": "Mountainous", "unknown": "Unknown Terrain",
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
```

Iterates series with `rwgps_route_id` set. Calls `fetch_route_elevation()`, creates/updates `Course` rows, classifies terrain. Rate limit: 2s between RWGPS requests. Idempotent — skips series with existing Course row unless `--force`.

2.4. Tests (`tests/test_elevation.py`):
- Terrain classification boundary conditions (4.9 -> FLAT, 5.0 -> ROLLING, etc.)
- `compute_m_per_km` with zero distance, None inputs
- `fetch_route_elevation` with mocked RWGPS JSON (summary stats present, summary stats missing with track_points fallback, both missing)
- CLI command integration test with in-memory DB

---

### Phase 3: Baseline Predictions (~25% effort)

**Files**: `raceanalyzer/predictions.py`, `raceanalyzer/queries.py`, `tests/test_predictions.py`

**Tasks**:

3.1. Create `raceanalyzer/predictions.py`:

```python
"""Baseline heuristic predictions. Every future model must beat these."""

def predict_series_finish_type(
    session: Session,
    series_id: int,
    category: Optional[str] = None,
) -> dict:
    """Predict finish type for next edition of a series.

    Algorithm: weighted frequency of historical finish types for this series.
    Recent editions weighted 2x. If category provided, filter to that
    category; otherwise use all categories.

    Returns: {
        "predicted_finish_type": FinishType value string,
        "confidence": "high" | "moderate" | "low",
        "edition_count": int,
        "distribution": dict[str, int],
    }

    Confidence:
    - "high":     4+ editions and plurality > 60%
    - "moderate": 2-3 editions or plurality 40-60%
    - "low":      1 edition or plurality < 40%
    """

def predict_contenders(
    session: Session,
    series_id: int,
    category: str,
    *,
    top_n: int = 10,
) -> pd.DataFrame:
    """Rank likely top finishers for an upcoming race.

    Three-tier graceful degradation:
    1. If startlist exists for this series+category: rank registered riders
       by carried_points percentile.
    2. Else, find riders who've raced this series before in this category,
       ranked by max carried_points.
    3. Else, find top carried_points riders in this category regionwide.

    Columns: name, team, carried_points, source ("startlist"|"series_history"|"category"),
             wins_in_series, last_raced.
    """
```

3.2. Add `get_race_preview()` to `queries.py`:

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
        "categories": list[str],
        "has_startlist": bool,
    }
    """
```

3.3. Tests (`tests/test_predictions.py`):
- Finish type prediction with 1 edition (low confidence), 5 unanimous editions (high), mixed editions (moderate)
- Recency weighting breaks ties
- Empty series returns unknown
- Contender prediction through all 3 tiers
- Heuristic accuracy > random baseline on seeded demo data

---

### Phase 4: Startlists & Calendar Integration (~15% effort)

**Files**: `raceanalyzer/startlists.py`, `raceanalyzer/calendar_feed.py`, `raceanalyzer/cli.py`, `tests/test_startlists.py`, `tests/test_calendar_feed.py`

**Tasks**:

4.1. Create `raceanalyzer/startlists.py`:

```python
"""BikeReg startlist integration with graceful degradation."""

def fetch_startlist(
    event_url: str,
    category: str,
    *,
    delay: float = 2.0,
) -> list[dict]:
    """Fetch registered riders for a BikeReg event + category.

    Returns: [{"name": str, "team": str, "registration_date": datetime}]
    Graceful: returns [] on any failure. Respects rate limit.
    """
```

4.2. Create `raceanalyzer/calendar_feed.py`:

```python
"""Upcoming race calendar scraper (BikeReg/OBRA)."""

def search_upcoming_events(
    region: str = "WA",
    days_ahead: int = 60,
) -> list[dict]:
    """Search BikeReg for upcoming cycling events in a region.

    Returns: [{"name", "date", "url", "location", "categories": [...]}]
    Graceful: returns [] on any failure.
    """
```

4.3. Add `fetch-startlists` and `fetch-calendar` CLI commands:

```
$ raceanalyzer fetch-calendar --region WA --days-ahead 60
Found 12 upcoming events on BikeReg.
  Seward Park Crit -> matched series "Seward Park Criterium"
  Mason Lake RR -> matched series "Mason Lake Road Race"
  ...

$ raceanalyzer fetch-startlists --region WA
Scraped 47 startlist entries across 7 matched events.
```

Both commands respect 2-second rate limits and exponential backoff on HTTP 429.

4.4. Tests: Mock BikeReg HTTP responses with `responses` library. Test successful parse, empty response, network error, rate limiting.

**Risk note**: BikeReg API behavior is unknown. If it requires auth or returns unparseable HTML, this phase may block. Contender prediction falls back to Tier 2/3, and the calendar stays retrospective. Revisit in Sprint 008 with manual CSV import if needed.

---

### Phase 5: Race Preview UI & Calendar Integration (~20% effort)

**Files**: `raceanalyzer/ui/pages/race_preview.py`, `raceanalyzer/ui/components.py`, `raceanalyzer/ui/pages/calendar.py`, `raceanalyzer/ui/pages/series_detail.py`

**Tasks**:

5.1. Create `raceanalyzer/ui/pages/race_preview.py` — standalone top-level page:

```python
"""Race Preview page — forward-looking race analysis."""

def render():
    session = st.session_state.db_session
    series_id = st.query_params.get("series_id")
    selected_cat = st.query_params.get("category")

    preview = queries.get_race_preview(session, int(series_id), category=selected_cat)

    # Card 1: Terrain
    with st.container():
        st.subheader("Course Profile")
        if preview["course"]:
            col1, col2, col3 = st.columns(3)
            col1.metric("Terrain", course_type_display(course["course_type"]))
            col2.metric("Elevation", f"{course['total_gain_m']:.0f}m gain")
            col3.metric("Distance", f"{course['distance_m']/1000:.1f} km")
        else:
            st.info("No course data available.")
        # Course map (reuse existing render_course_map)

    # Card 2: Prediction
    with st.container():
        st.subheader("Predicted Finish Type")
        if preview["prediction"]:
            pred = preview["prediction"]
            ft_display = finish_type_display_name(pred["predicted_finish_type"])
            st.markdown(f"### {ft_display}")
            render_confidence_badge(pred["confidence"])
            st.caption(f"Based on {pred['edition_count']} previous editions")
        else:
            st.info("No historical data for predictions yet.")

    # Card 3: Top Contenders
    with st.container():
        st.subheader("Top Contenders")
        contenders = preview["contenders"]
        if not contenders.empty:
            source = contenders["source"].iloc[0]
            source_labels = {
                "startlist": "From registered riders",
                "series_history": "Based on past editions (no startlist available)",
                "category": "Top-rated riders in this category",
            }
            st.caption(source_labels.get(source, ""))
            for _, rider in contenders.iterrows():
                with st.container():
                    col1, col2 = st.columns([3, 1])
                    col1.write(f"**{rider['name']}** — {rider['team']}")
                    col2.write(f"{rider['carried_points']:.0f} pts")

    # Card 4: User Feedback (shown after race date)
    if race_has_passed(preview):
        with st.container():
            st.subheader("Was this prediction right?")
            # Show predicted finish type, ask for confirmation/correction
```

5.2. Mobile-first design rules:
- All columns stack to single-column on mobile (Streamlit default)
- Use `st.container()` cards, not tables
- Font sizes use Streamlit defaults (no custom CSS)
- Test at 375px viewport width

5.3. Add upcoming races section to `calendar.py`:
- Query upcoming races (`is_upcoming=True`) above historical series tiles
- Show predicted finish type badge and registration link per event
- Unmatched events shown as plain tiles without predictions

5.4. Add "Preview" button to series detail page and series tiles for navigation.

5.5. Add terrain badge and prediction badge to `components.py`.

---

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/db/models.py` | MODIFY | Add `Course`, `CourseType`, `Startlist`, `UserLabel` models; rating cols on `Rider`/`Result`; upcoming cols on `Race` |
| `raceanalyzer/config.py` | MODIFY | Add terrain thresholds, BikeReg settings, prediction settings |
| `raceanalyzer/rwgps.py` | MODIFY | Add `fetch_route_elevation()` with track_points fallback |
| `raceanalyzer/elevation.py` | CREATE | `compute_m_per_km()`, `classify_terrain()`, display helpers |
| `raceanalyzer/predictions.py` | CREATE | `predict_series_finish_type()`, `predict_contenders()` |
| `raceanalyzer/startlists.py` | CREATE | BikeReg startlist fetcher: `fetch_startlist()` |
| `raceanalyzer/calendar_feed.py` | CREATE | Upcoming race scraper: `search_upcoming_events()` |
| `raceanalyzer/queries.py` | MODIFY | Add `get_race_preview()`, `get_upcoming_races()` |
| `raceanalyzer/cli.py` | MODIFY | Add `elevation-extract`, `fetch-startlists`, `fetch-calendar` commands |
| `raceanalyzer/ui/pages/race_preview.py` | CREATE | Race Preview page — terrain + prediction + contenders + feedback |
| `raceanalyzer/ui/pages/calendar.py` | MODIFY | Add upcoming races section |
| `raceanalyzer/ui/pages/series_detail.py` | MODIFY | Add terrain badge, link to preview |
| `raceanalyzer/ui/components.py` | MODIFY | Add terrain badge, contender card, prediction badge components |
| `tests/test_elevation.py` | CREATE | Terrain classification, m/km computation, CLI integration |
| `tests/test_predictions.py` | CREATE | Prediction heuristic, degradation tiers, baseline comparison |
| `tests/test_startlists.py` | CREATE | BikeReg mock tests |
| `tests/test_calendar_feed.py` | CREATE | Upcoming race parsing tests |
| `tests/test_queries.py` | MODIFY | Race preview assembly, upcoming race queries |
| `tests/conftest.py` | MODIFY | Add Course, Startlist, UserLabel fixtures |

---

## Definition of Done

- [ ] `Course` table exists with dual FK (`series_id`, `race_id`), 7 elevation fields, `course_type`
- [ ] `Startlist` table exists with `race_id` FK, `rider_id` FK, `source`, `scraped_at`
- [ ] `UserLabel` table exists with `predicted_finish_type`, `actual_finish_type`, `is_correct`, session dedup
- [ ] `Rider` has `mu`, `sigma`, `num_rated_races` columns (nullable, unpopulated)
- [ ] `Result` has `prior_mu`, `prior_sigma`, `mu`, `sigma` columns (nullable, unpopulated)
- [ ] `Race` has `is_upcoming`, `registration_url`, `registration_source` columns
- [ ] `raceanalyzer elevation-extract` populates courses table from RWGPS routes with track_points fallback
- [ ] `classify_terrain()` correctly maps m/km to 4-bin CourseType at all boundaries
- [ ] `predict_series_finish_type()` returns predicted finish type with confidence for any series with 1+ editions
- [ ] `predict_contenders()` returns ranked riders via 3-tier degradation (startlist -> history -> category)
- [ ] Heuristic finish-type predictor accuracy > "predict most common type for category" baseline on demo data
- [ ] Race Preview page renders on mobile viewport (375px) with terrain, prediction, and contenders
- [ ] Race Preview page works with missing data: no course (skip terrain card), no history (show "no data"), no startlist (fall back to history)
- [ ] Post-race feedback prompt appears for races with dates in the past; stores UserLabel rows
- [ ] `fetch-startlists` and `fetch-calendar` CLI commands work with BikeReg (or gracefully degrade)
- [ ] Calendar page shows upcoming races above historical series tiles
- [ ] All new functions have unit tests with `responses` mocking for HTTP calls
- [ ] Test coverage remains >85%
- [ ] No raw probabilities or decimal scores shown to users — qualitative labels only

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| RWGPS route JSON lacks `elevation_gain`/`distance` fields | Medium | Blocks elevation extraction | Fallback: compute from `track_points` array (sum positive deltas for gain, haversine for distance). Track_points already used in `fetch_route_polyline()`. |
| BikeReg has no public API or requires auth | High | Blocks startlist + upcoming calendar | Contender prediction falls back to Tier 2 (historical performers). Calendar stays retrospective. Revisit in Sprint 008 with manual CSV import. |
| `carried_points` data is sparse (many riders have NULL) | Medium | Contender ranking is unreliable | Fall through to Tier 3 (category-wide). Show "Limited data" badge. Consider using win count as secondary sort when carried_points is missing. |
| Prediction heuristic fails to beat random baseline | Low | Undermines prediction credibility | With 6+ editions of PNW series, finish type is usually consistent. If genuinely random, the signal is that finish types are more variable than expected — useful finding. |
| Rating columns cause migration issues on existing DB | Low | Dev friction | `ALTER TABLE ADD COLUMN ... DEFAULT NULL` is safe on SQLite. No data migration needed. |
| Scope creep from "one more feature" on Race Preview | Medium | Sprint slips | Scope ladder is explicit. Phase 4 (BikeReg) is highest risk. Race Preview MVP ships with just terrain + prediction + contenders from history. |
| Course-to-series mapping assumes stable courses | Low | Wrong terrain for changed courses | Acceptable for MVP. Flag in UI: "Course data based on most recent RWGPS route." Per-race Course override via `race_id` FK is available. |
| RWGPS rate limiting during batch extraction | Medium | Extraction slows/blocks | 2-second delay between requests. `--force` flag only for re-extraction. Skip series that already have Course rows. |

---

## Security Considerations

- **Rate limiting on all HTTP calls**: 2s between RWGPS requests, 2s base delay for BikeReg with exponential backoff on 429.
- **No PII beyond public racing data**: Startlist stores rider name (public on BikeReg) and registration date. No email, phone, or payment info.
- **User labels are anonymous**: No user identity beyond session cookie. `session_id` is for dedup only.
- **BikeReg scraping ethics**: Use CSV export (explicitly offered to users) first. REST API second. Do not scrape HTML aggressively. Respect robots.txt.
- **SQLi prevention**: All queries through SQLAlchemy ORM with parameterized queries. No raw SQL.

---

## Dependencies

- **Existing**: `sqlalchemy`, `requests`, `responses` (test), `click`, `streamlit`, `pandas`, `polyline`, `folium`, `streamlit-folium`, `plotly`
- **No new pip dependencies.** The entire sprint ships without adding a single package. BikeReg calls use `requests`. Terrain classification is pure Python.

---

## Open Questions

1. **RWGPS route JSON fields**: Does the `/routes/{id}.json` endpoint return `elevation_gain` and `distance` as top-level fields, or nested? Need to inspect one real response. If neither exists, compute from `track_points`.

2. **BikeReg API discovery**: Before coding Phase 4, spend 30 minutes probing BikeReg's API surface. Check: `/api/search`, CSV download links, "Confirmed Riders" page structure. If nothing works, defer to Sprint 008 with manual CSV import.

3. **Prediction granularity**: Should `predict_series_finish_type()` predict per-category or across all categories? Recommendation: **per-category when 3+ editions have data for that category, otherwise fall back to all-category aggregate.**

4. **Demo data for testing predictions**: Generate a mix of series — 5 with 80%+ finish type consistency (heuristic should nail these) and 3 with high variability (heuristic should report low confidence). Validates both prediction and confidence calibration.

5. **Recency window definition**: "Recent 2 editions weighted 2x" — does "recent" mean last 2 calendar years, or last 2 editions regardless of gap? Recommendation: last 2 editions by date, to handle COVID-era gaps gracefully.
