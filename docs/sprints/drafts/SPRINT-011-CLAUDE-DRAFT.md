# Sprint 011: Feed First Glance, Detail Dive, Personalization & Performance

## Overview

Sprint 011 transforms the feed from a functional list into a racer-first decision tool. The feed card's first glance answers "should I care?" in under 3 seconds by surfacing information in the racer's actual decision priority order: date/logistics → social → course → finish type → field → drop rate. Beyond the card, the detail dive (preview page) becomes a confidence-builder with hero course profiles, climb breakdowns with race context, team-grouped startlists, and similar-race cross-references. A lightweight "My Team" feature unlocks social signals. Feed organization replaces vague tier labels with countdown timers, month-grouped agenda views, and multi-dimensional filtering. Performance work eliminates the N+1 query problem and introduces caching, lazy loading, and pre-computation.

**Scope**: 31 use cases across 5 areas (First Glance, Detail Dive, My Team, Feed Organization, Performance).

**Phasing**: 5 phases over the sprint, ordered by dependency and user impact:
1. **Performance & Query Foundation** (PF-01 through PF-06) — must come first; subsequent phases depend on batch-loaded data and caching
2. **Feed Organization & Filtering** (FO-01 through FO-08) — restructures the feed container that cards live in
3. **First Glance Card Redesign** (FG-01 through FG-08) — reorders and enriches card content
4. **My Team Personalization** (MT-01, MT-02) — adds social layer on top of redesigned cards
5. **Detail Dive Enhancements** (DD-01 through DD-07) — enriches the preview page accessed from cards

---

## Use Cases

### First Glance (FG-01 → FG-08)

| ID | Name | Priority | Status |
|----|------|----------|--------|
| FG-01 | Date and location in header | P0 | Gap — location buried in caption |
| FG-02 | Teammates registered badge | P0 | Gap — not built |
| FG-03 | Course character one-liner | P1 | Gap — distance/gain not on card |
| FG-04 | Finish pattern prediction lead | P1 | Built — confirm position |
| FG-05 | Field size on card | P1 | Gap — data exists, not rendered |
| FG-06 | Drop rate label prominent | P2 | Partially built — needs label emphasis |
| FG-07 | Race type label | P2 | Gap — may need data work |
| FG-08 | Card layout reorder | P0 | Redesign needed |

### Detail Dive (DD-01 → DD-07)

| ID | Name | Priority | Status |
|----|------|----------|--------|
| DD-01 | Interactive course profile hero | P0 | Built (Sprint 008) — confirm placement |
| DD-02 | Climb breakdown with race context | P1 | Partially built — needs narrative |
| DD-03 | Startlist with team groupings | P1 | Gap — data exists, not grouped |
| DD-04 | Racer type description expanded | P2 | Partially built — needs expansion |
| DD-05 | Historical finish type visualization | P2 | Gap — text-only popover |
| DD-06 | Similar races cross-reference | P1 | Gap — needs similarity logic |
| DD-07 | Course map with race features | P2 | Built (Sprint 008) — confirm placement |

### My Team (MT-01, MT-02)

| ID | Name | Priority | Status |
|----|------|----------|--------|
| MT-01 | Set my team name | P0 | Gap — not built |
| MT-02 | Teammate names on card | P1 | Gap — depends on MT-01 |

### Feed Organization (FO-01 → FO-08)

| ID | Name | Priority | Status |
|----|------|----------|--------|
| FO-01 | Discipline filter | P0 | Gap — discipline not modeled |
| FO-02 | Race type filter within discipline | P1 | Gap — race_type exists, not filterable |
| FO-03 | Geographic filter by state/region | P0 | Gap — data exists, not filterable |
| FO-04 | Persistent filter preferences | P1 | Partially built — category only |
| FO-05 | Days-until countdown labels | P0 | Gap — uses "SOON"/"UPCOMING" |
| FO-06 | Month-based section headers | P0 | Gap — flat list |
| FO-07 | Don't over-emphasize next race | P1 | Gap — "Racing Soon" auto-expands |
| FO-08 | Scannable card density | P1 | Gap — cards too tall collapsed |

### Performance (PF-01 → PF-06)

| ID | Name | Priority | Status |
|----|------|----------|--------|
| PF-01 | Eliminate N+1 queries | P0 | Gap — 8-10 queries per series |
| PF-02 | Cache feed results | P0 | Gap — no caching on main feed |
| PF-03 | Lazy-load expanded card content | P1 | Gap — all computed upfront |
| PF-04 | Pre-compute predictions at scrape time | P1 | Gap — computed at render time |
| PF-05 | Paginate at query layer | P1 | Gap — Python-side slicing |
| PF-06 | Profile and set performance budget | P0 | Gap — no instrumentation |

---

## Architecture

### Data Flow (Current → Proposed)

**Current** (Sprint 010):
```
feed.py render()
  → queries.get_feed_items(session, category, search)
    → for each series:
        → query upcoming race          (1 query)
        → query most recent race       (1 query)
        → count editions               (1 query)
        → predict_series_finish_type   (2-3 queries)
        → query course                 (1 query)
        → calculate_drop_rate          (N queries per edition)
        → calculate_typical_duration   (N queries per edition)
        → generate_narrative           (pure computation)
        → query editions for summary   (1 query + N finish type computations)
  → render cards (all content computed upfront)
```

**Proposed**:
```
feed.py render()
  → queries.get_feed_items_batch(session, filters)
    → ONE query: all series with upcoming race, most recent race, edition count
    → ONE query: all courses (JOIN series)
    → ONE query: pre-computed predictions (JOIN series_predictions)
    → ONE query: pre-computed drop rates + durations (from series_predictions)
    → ONE query: teammate matches (if team_name set)
    → ONE query: field sizes (aggregate from results)
    → Assemble Tier 1 (collapsed card) data in Python
    → Return list[FeedItem] with Tier 1 populated, Tier 2 = None
  → render cards (Tier 1 only for collapsed)
  → on expand: queries.get_feed_item_detail(session, series_id, category)
    → compute narrative, sparkline, climb highlight, racer type desc, editions
    → return Tier 2 data
```

### New Data Model: `series_predictions` Table

```python
class SeriesPrediction(Base):
    __tablename__ = "series_predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("race_series.id"), index=True
    )
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # NULL category = "all categories" aggregate

    predicted_finish_type: Mapped[Optional[str]] = mapped_column(String)
    confidence: Mapped[Optional[str]] = mapped_column(String)
    edition_count: Mapped[int] = mapped_column(default=0)
    distribution_json: Mapped[Optional[str]] = mapped_column(Text)

    drop_rate: Mapped[Optional[float]] = mapped_column(Float)
    drop_rate_label: Mapped[Optional[str]] = mapped_column(String)

    typical_winner_duration_min: Mapped[Optional[float]] = mapped_column(Float)
    typical_field_duration_min: Mapped[Optional[float]] = mapped_column(Float)

    field_size_median: Mapped[Optional[int]] = mapped_column(Integer)
    field_size_min: Mapped[Optional[int]] = mapped_column(Integer)
    field_size_max: Mapped[Optional[int]] = mapped_column(Integer)

    last_computed: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("series_id", "category", name="uq_series_cat"),
    )
```

**Rationale**: A dedicated table beats caching predictions as JSON on `race_series` because: (a) we need per-category predictions, (b) the feed query can JOIN directly without Python-side deserialization, (c) staleness is explicit via `last_computed`, (d) field size stats have a natural home here.

### New Data Model: `Discipline` Derivation

Rather than adding a column, derive discipline from `RaceType` via a pure function:

```python
class Discipline(str, Enum):
    ROAD = "road"
    GRAVEL = "gravel"
    CYCLOCROSS = "cyclocross"
    MTB = "mtb"
    TRACK = "track"
    UNKNOWN = "unknown"

RACE_TYPE_TO_DISCIPLINE: dict[RaceType, Discipline] = {
    RaceType.CRITERIUM: Discipline.ROAD,
    RaceType.ROAD_RACE: Discipline.ROAD,
    RaceType.HILL_CLIMB: Discipline.ROAD,
    RaceType.STAGE_RACE: Discipline.ROAD,
    RaceType.TIME_TRIAL: Discipline.ROAD,
    RaceType.GRAVEL: Discipline.GRAVEL,
}

def discipline_for_race_type(race_type: Optional[RaceType]) -> Discipline:
    if race_type is None:
        return Discipline.UNKNOWN
    return RACE_TYPE_TO_DISCIPLINE.get(race_type, Discipline.UNKNOWN)
```

**Rationale**: The current dataset is overwhelmingly road discipline. A derivation function is simpler than a schema migration and can be replaced with a column later if multi-discipline data grows. The function is called once per series at feed-build time, not per-query.

### Feed Item Data Tiers

**Tier 1** (always computed — collapsed card data):
```python
@dataclass
class FeedItemTier1:
    series_id: int
    display_name: str
    location: Optional[str]
    state_province: Optional[str]
    upcoming_date: Optional[date]
    most_recent_date: Optional[date]
    days_until: Optional[int]          # NEW: computed countdown
    countdown_label: str               # NEW: "in 3 days", "Tomorrow", etc.
    is_upcoming: bool
    race_type: Optional[str]           # NEW: from most recent edition
    discipline: Optional[str]          # NEW: derived from race_type
    course_type: Optional[str]
    distance_m: Optional[float]
    total_gain_m: Optional[float]
    predicted_finish_type: Optional[str]
    confidence: Optional[str]
    drop_rate_pct: Optional[int]
    drop_rate_label: Optional[str]
    field_size_display: Optional[str]  # NEW: "Usually 35-40" or "28 registered"
    registration_url: Optional[str]
    edition_count: int
    teammate_names: list[str]          # NEW: from startlist team matching
```

**Tier 2** (computed on expand — rich card content):
```python
@dataclass
class FeedItemTier2:
    narrative_snippet: str
    elevation_sparkline_points: list
    climb_highlight: Optional[str]
    racer_type_description: Optional[str]
    duration_minutes: Optional[dict]
    editions_summary: list[dict]
```

### Team Name Persistence

Use Streamlit's `st.session_state` + URL query param `team` for persistence:

```python
# In sidebar:
team_name = st.sidebar.text_input(
    "My Team",
    value=st.session_state.get("team_name", st.query_params.get("team", "")),
    placeholder="e.g. Team Rapha",
    key="team_name_input",
)
if team_name != st.session_state.get("team_name"):
    st.session_state["team_name"] = team_name
    if team_name:
        st.query_params["team"] = team_name
    elif "team" in st.query_params:
        del st.query_params["team"]
```

**Rationale**: This follows the existing pattern for category filter persistence (Sprint 010). URL param survives page reloads and can be bookmarked. No new dependencies. No accounts or cookies needed.

### Similar Races Algorithm

Simple heuristic scoring (0-100 scale):

```python
def compute_similarity(series_a: dict, series_b: dict) -> float:
    score = 0.0
    # Same course type: +40
    if series_a["course_type"] == series_b["course_type"]:
        score += 40
    # Same predicted finish type: +30
    if series_a["predicted_finish_type"] == series_b["predicted_finish_type"]:
        score += 30
    # Similar distance (within 25%): +20
    da, db = series_a.get("distance_m"), series_b.get("distance_m")
    if da and db and da > 0 and db > 0:
        ratio = min(da, db) / max(da, db)
        if ratio > 0.75:
            score += 20 * ((ratio - 0.75) / 0.25)
    # Same discipline: +10
    if series_a.get("discipline") == series_b.get("discipline"):
        score += 10
    return score
```

Top 3 similar races shown on preview page where `score >= 50`. Pre-computed at scrape time is ideal but can start as on-demand with caching.

### Countdown Label Logic

```python
def countdown_label(days_until: Optional[int]) -> str:
    if days_until is None:
        return ""
    if days_until == 0:
        return "Today"
    if days_until == 1:
        return "Tomorrow"
    if days_until <= 14:
        return f"in {days_until} days"
    weeks = days_until // 7
    return f"in {weeks} weeks"
```

### Month Grouping

```python
def group_by_month(items: list[dict]) -> list[tuple[str, list[dict]]]:
    """Group upcoming feed items by month. Returns (header, items) pairs."""
    from itertools import groupby
    upcoming = [i for i in items if i["is_upcoming"]]
    historical = [i for i in items if not i["is_upcoming"]]

    def month_key(item):
        d = item["upcoming_date"]
        return (d.year, d.month) if d else (9999, 12)

    upcoming.sort(key=lambda i: i["upcoming_date"] or date.max)
    groups = []
    for (year, month), group_items in groupby(upcoming, key=month_key):
        header = f"{date(year, month, 1):%B %Y}"
        groups.append((header, list(group_items)))

    if historical:
        groups.append(("Past Races", historical))
    return groups
```

---

## Implementation

### Phase 1: Performance & Query Foundation (PF-01 → PF-06)

**Goal**: Eliminate N+1 queries, add caching and instrumentation. All subsequent phases build on batch-loaded data.

**Effort**: ~35% of sprint

#### PF-06: Performance instrumentation

Add timing context manager and logging to `queries.py`:

```python
import time
import logging

logger = logging.getLogger("raceanalyzer.perf")

class PerfTimer:
    def __init__(self, label: str):
        self.label = label
        self.elapsed_ms = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000
        logger.info(f"[perf] {self.label}: {self.elapsed_ms:.1f}ms")

PERF_BUDGET_COLD_MS = 1000
PERF_BUDGET_WARM_MS = 200
```

Wrap each phase of `get_feed_items_batch` in a `PerfTimer`. Log total at the end. Warn if over budget.

#### PF-04: Pre-compute predictions — `series_predictions` table

Add `SeriesPrediction` model to `raceanalyzer/db/models.py`. Create `raceanalyzer/precompute.py`:

```python
def precompute_series_predictions(session: Session, series_id: int) -> None:
    """Compute and store predictions for all categories of a series."""
    # Get all categories for this series
    categories = _get_series_categories(session, series_id)

    for category in [None] + categories:  # None = all-categories aggregate
        prediction = predict_series_finish_type(session, series_id, category=category)
        drop_rate = calculate_drop_rate(session, series_id, category=category)
        duration = calculate_typical_duration(session, series_id, category=category)
        field_size = _calculate_field_size(session, series_id, category=category)

        # Upsert into series_predictions
        existing = session.query(SeriesPrediction).filter_by(
            series_id=series_id, category=category
        ).first()
        if existing:
            _update_prediction(existing, prediction, drop_rate, duration, field_size)
        else:
            session.add(SeriesPrediction(
                series_id=series_id,
                category=category,
                **_build_prediction_row(prediction, drop_rate, duration, field_size),
            ))
    session.commit()


def precompute_all(session: Session) -> None:
    """Recompute predictions for all series. Called after scrape."""
    series_ids = [s.id for s in session.query(RaceSeries.id).all()]
    for sid in series_ids:
        precompute_series_predictions(session, sid)
```

New helper for field size:

```python
def _calculate_field_size(
    session: Session, series_id: int, category: Optional[str] = None
) -> Optional[dict]:
    """Calculate historical field size stats from Results."""
    editions = (
        session.query(Race)
        .filter(Race.series_id == series_id)
        .all()
    )
    sizes = []
    for race in editions:
        query = session.query(func.count(Result.id)).filter(
            Result.race_id == race.id
        )
        if category:
            query = query.filter(Result.race_category_name == category)
        count = query.scalar()
        if count and count > 0:
            sizes.append(count)

    if not sizes:
        return None
    return {
        "median": int(statistics.median(sizes)),
        "min": min(sizes),
        "max": max(sizes),
    }
```

Hook into scrape pipeline: after `scrape` CLI command finishes importing results, call `precompute_all(session)`.

#### PF-01: Batch feed query — `get_feed_items_batch`

Replace the per-series loop in `get_feed_items` with batch queries:

```python
def get_feed_items_batch(
    session: Session,
    *,
    category: Optional[str] = None,
    search_query: Optional[str] = None,
    discipline: Optional[str] = None,
    race_type: Optional[str] = None,
    states: Optional[list[str]] = None,
    team_name: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    """Batch-loaded feed items. Replaces get_feed_items."""
    today = date.today()

    with PerfTimer("total_feed_query"):
        # 1. Base series query with filters
        series_query = session.query(RaceSeries)
        if search_query:
            matching_ids = search_series(session, search_query)
            if not matching_ids:
                return []
            series_query = series_query.filter(RaceSeries.id.in_(matching_ids))

        series_list = series_query.all()
        if not series_list:
            return []
        series_ids = [s.id for s in series_list]
        series_map = {s.id: s for s in series_list}

        # 2. Batch: all races for these series (upcoming + most recent)
        with PerfTimer("batch_races"):
            all_races = (
                session.query(Race)
                .filter(Race.series_id.in_(series_ids))
                .order_by(Race.date.desc())
                .all()
            )
            # Group by series_id
            races_by_series: dict[int, list[Race]] = {}
            for race in all_races:
                races_by_series.setdefault(race.series_id, []).append(race)

        # 3. Batch: all courses
        with PerfTimer("batch_courses"):
            courses = (
                session.query(Course)
                .filter(Course.series_id.in_(series_ids))
                .all()
            )
            course_map = {c.series_id: c for c in courses}

        # 4. Batch: pre-computed predictions
        pred_category = category  # None means all-categories aggregate
        with PerfTimer("batch_predictions"):
            predictions = (
                session.query(SeriesPrediction)
                .filter(
                    SeriesPrediction.series_id.in_(series_ids),
                    SeriesPrediction.category == pred_category,
                )
                .all()
            )
            pred_map = {p.series_id: p for p in predictions}

        # 5. Batch: teammate matching (if team_name set)
        teammate_map: dict[int, list[str]] = {}
        if team_name:
            with PerfTimer("batch_teammates"):
                teammates = (
                    session.query(
                        Startlist.series_id,
                        Startlist.rider_name,
                    )
                    .filter(
                        Startlist.series_id.in_(series_ids),
                        Startlist.team.ilike(f"%{team_name}%"),
                    )
                    .all()
                )
                for sid, name in teammates:
                    teammate_map.setdefault(sid, []).append(name)

        # 6. Assemble Tier 1 items
        with PerfTimer("assemble_items"):
            items = []
            for sid in series_ids:
                series = series_map[sid]
                races = races_by_series.get(sid, [])
                if not races:
                    continue

                most_recent = races[0]  # already sorted desc
                upcoming = next(
                    (r for r in reversed(races) if r.date and r.date >= today),
                    None,
                )

                is_upcoming = upcoming is not None
                upcoming_date = upcoming.date if upcoming else None
                days_until = (upcoming_date - today).days if upcoming_date else None

                # Apply filters
                race_type_val = most_recent.race_type
                disc = discipline_for_race_type(race_type_val)
                if discipline and disc.value != discipline:
                    continue
                if race_type and (not race_type_val or race_type_val.value != race_type):
                    continue
                if states and most_recent.state_province not in states:
                    continue

                course = course_map.get(sid)
                pred = pred_map.get(sid)

                # Field size display
                field_display = None
                if pred and pred.field_size_median:
                    if pred.field_size_min == pred.field_size_max:
                        field_display = f"Usually {pred.field_size_median} starters"
                    else:
                        field_display = (
                            f"Usually {pred.field_size_min}-{pred.field_size_max} starters"
                        )

                item = {
                    "series_id": sid,
                    "display_name": series.display_name,
                    "location": most_recent.location,
                    "state_province": most_recent.state_province,
                    "upcoming_date": upcoming_date,
                    "most_recent_date": most_recent.date,
                    "days_until": days_until,
                    "countdown_label": countdown_label(days_until),
                    "is_upcoming": is_upcoming,
                    "race_type": race_type_val.value if race_type_val else None,
                    "discipline": disc.value,
                    "course_type": (
                        course.course_type.value
                        if course and course.course_type else None
                    ),
                    "distance_m": course.distance_m if course else None,
                    "total_gain_m": course.total_gain_m if course else None,
                    "predicted_finish_type": (
                        pred.predicted_finish_type if pred else None
                    ),
                    "confidence": pred.confidence if pred else None,
                    "drop_rate_pct": (
                        round(pred.drop_rate * 100)
                        if pred and pred.drop_rate is not None else None
                    ),
                    "drop_rate_label": pred.drop_rate_label if pred else None,
                    "field_size_display": field_display,
                    "registration_url": (
                        upcoming.registration_url if upcoming else None
                    ),
                    "edition_count": len(races),
                    "teammate_names": teammate_map.get(sid, []),
                    # Tier 2 placeholders (lazy-loaded)
                    "narrative_snippet": None,
                    "elevation_sparkline_points": None,
                    "climb_highlight": None,
                    "racer_type_description": None,
                    "duration_minutes": None,
                    "editions_summary": None,
                }
                items.append(item)

        # 7. Sort and paginate
        items = _sort_feed_items(items, today)
        items = items[offset:offset + limit]

    return items
```

#### PF-02: Cache feed results

```python
@st.cache_data(ttl=300)
def _cached_feed_items(
    _session,
    category: Optional[str],
    search_query: Optional[str],
    discipline: Optional[str],
    race_type: Optional[str],
    states_tuple: Optional[tuple],  # tuples are hashable
    team_name: Optional[str],
) -> list[dict]:
    states = list(states_tuple) if states_tuple else None
    return get_feed_items_batch(
        _session,
        category=category,
        search_query=search_query,
        discipline=discipline,
        race_type=race_type,
        states=states,
        team_name=team_name,
    )
```

#### PF-03: Lazy-load expanded card content

Add `get_feed_item_detail` for Tier 2 data:

```python
def get_feed_item_detail(
    session: Session,
    series_id: int,
    category: Optional[str] = None,
) -> dict:
    """Load Tier 2 (expanded card) content for a single series."""
    import json
    from raceanalyzer.predictions import (
        calculate_typical_duration,
        generate_narrative,
        racer_type_description,
    )

    course = session.query(Course).filter(Course.series_id == series_id).first()

    # Parse profile and climbs
    sparkline_points = []
    climbs_data = None
    if course:
        if course.profile_json:
            try:
                profile = json.loads(course.profile_json)
                sparkline_points = _downsample_profile(profile)
            except (json.JSONDecodeError, TypeError):
                pass
        if course.climbs_json:
            try:
                climbs_data = json.loads(course.climbs_json)
            except (json.JSONDecodeError, TypeError):
                pass

    # Pre-computed prediction (for narrative inputs)
    pred = (
        session.query(SeriesPrediction)
        .filter_by(series_id=series_id, category=category)
        .first()
    )

    course_type = course.course_type.value if course and course.course_type else None
    predicted_ft = pred.predicted_finish_type if pred else None
    distance_km = course.distance_m / 1000.0 if course and course.distance_m else None
    total_gain_m = course.total_gain_m if course else None

    drop_rate_dict = None
    if pred and pred.drop_rate is not None:
        drop_rate_dict = {"drop_rate": pred.drop_rate, "label": pred.drop_rate_label}

    narrative = generate_narrative(
        course_type=course_type,
        predicted_finish_type=predicted_ft,
        drop_rate=drop_rate_dict,
        distance_km=distance_km,
        total_gain_m=total_gain_m,
        climbs=climbs_data,
        edition_count=pred.edition_count if pred else 0,
    )

    racer_desc = racer_type_description(course_type, predicted_ft)

    duration = None
    if pred and pred.typical_winner_duration_min:
        duration = {
            "winner_duration_minutes": pred.typical_winner_duration_min,
            "field_duration_minutes": pred.typical_field_duration_min,
        }

    # Editions summary
    editions = (
        session.query(Race)
        .filter(Race.series_id == series_id)
        .order_by(Race.date.desc())
        .all()
    )
    editions_summary = []
    for ed in editions:
        year = ed.date.year if ed.date else None
        ed_ft = _compute_overall_finish_type(session, ed.id)
        editions_summary.append({
            "year": year,
            "finish_type": ed_ft,
            "finish_type_display": finish_type_display_name(ed_ft),
        })

    return {
        "narrative_snippet": _snippet(narrative, max_sentences=2, max_chars=200),
        "elevation_sparkline_points": sparkline_points,
        "climb_highlight": climb_highlight(climbs_data),
        "racer_type_description": racer_desc,
        "duration_minutes": duration,
        "editions_summary": editions_summary,
    }
```

Cache this per series_id+category with `@st.cache_data(ttl=300)`.

#### PF-05: Query-layer pagination

Already handled in `get_feed_items_batch` via `limit` and `offset` parameters. The feed page passes these through:

```python
# In feed.py
page = int(st.query_params.get("page", "0"))
items = _cached_feed_items(
    session, category, search, discipline, race_type, states_tuple, team_name
)
# Pagination is applied inside get_feed_items_batch
```

#### Phase 1 Files

| File | Changes |
|------|---------|
| `raceanalyzer/db/models.py` | Add `SeriesPrediction` model, `Discipline` enum |
| `raceanalyzer/queries.py` | Add `get_feed_items_batch`, `get_feed_item_detail`, `countdown_label`, `discipline_for_race_type`, `PerfTimer`; deprecate `get_feed_items` |
| `raceanalyzer/precompute.py` | NEW — `precompute_series_predictions`, `precompute_all`, `_calculate_field_size` |
| `raceanalyzer/predictions.py` | No changes (existing functions used by precompute) |
| `tests/test_queries.py` | Tests for batch query, countdown_label, discipline derivation |
| `tests/test_precompute.py` | NEW — tests for precomputation and field size calculation |

---

### Phase 2: Feed Organization & Filtering (FO-01 → FO-08)

**Goal**: Replace flat feed with month-grouped agenda, add multi-dimensional filters, replace vague labels with countdowns.

**Effort**: ~25% of sprint

#### FO-01 & FO-02: Discipline and race type filters

Add to sidebar alongside existing category filter:

```python
def render_feed_filters(session) -> dict:
    """Render all feed filters in sidebar. Returns filter dict."""
    render_global_category_filter(session)
    category = st.session_state.get("global_category")

    # Discipline filter
    discipline_options = ["All"] + [d.value.title() for d in Discipline if d != Discipline.UNKNOWN]
    disc_param = st.query_params.get("discipline", "All")
    disc_idx = discipline_options.index(disc_param.title()) if disc_param.title() in discipline_options else 0
    discipline = st.sidebar.selectbox(
        "Discipline",
        options=discipline_options,
        index=disc_idx,
        key="discipline_filter",
    )
    if discipline != "All":
        st.query_params["discipline"] = discipline.lower()
    elif "discipline" in st.query_params:
        del st.query_params["discipline"]

    # Race type filter (conditional on discipline)
    race_type = None
    if discipline != "All":
        types_for_disc = _race_types_for_discipline(discipline.lower())
        if types_for_disc:
            type_options = ["All"] + [race_type_display_name(t) for t in types_for_disc]
            rt_param = st.query_params.get("race_type", "All")
            race_type_sel = st.sidebar.selectbox(
                "Race Type",
                options=type_options,
                key="race_type_filter",
            )
            if race_type_sel != "All":
                race_type = _display_name_to_value(race_type_sel)
                st.query_params["race_type"] = race_type
            elif "race_type" in st.query_params:
                del st.query_params["race_type"]

    # State/region filter
    available_states = _cached_states(session)
    states_param = st.query_params.get("states", "")
    default_states = states_param.split(",") if states_param else available_states
    states = st.sidebar.multiselect(
        "State/Region",
        options=available_states,
        default=[s for s in default_states if s in available_states],
        key="state_filter",
    )
    if states and set(states) != set(available_states):
        st.query_params["states"] = ",".join(states)
    elif "states" in st.query_params:
        del st.query_params["states"]

    return {
        "category": category,
        "discipline": discipline.lower() if discipline != "All" else None,
        "race_type": race_type,
        "states": states if states != available_states else None,
    }
```

Helper for discipline → race type mapping:

```python
def _race_types_for_discipline(discipline: str) -> list[str]:
    mapping = {
        "road": ["criterium", "road_race", "hill_climb", "stage_race", "time_trial"],
        "gravel": ["gravel"],
    }
    return mapping.get(discipline, [])
```

#### FO-03: Geographic filter

Handled in `render_feed_filters` above — the `st.sidebar.multiselect` for states with URL persistence via `st.query_params["states"]`.

#### FO-04: Persistent filter preferences

All filters persist via `st.query_params` (already shown above). On page load, filters read from URL params first, then fall back to defaults. Pattern matches existing category filter from Sprint 010.

#### FO-05: Days-until countdown labels

`countdown_label()` function defined in Architecture section. Used in the expander label:

```python
def _build_expander_label(item: dict) -> str:
    name = item["display_name"]
    if item["is_upcoming"] and item.get("upcoming_date"):
        date_str = f"{item['upcoming_date']:%b %d, %Y}"
        countdown = item.get("countdown_label", "")
        location = item.get("location", "")
        parts = [name, date_str]
        if countdown:
            parts.append(countdown)
        if location:
            parts.append(location)
        return " — ".join(parts)
    elif item.get("most_recent_date"):
        location = item.get("location", "")
        loc_str = f" — {location}" if location else ""
        return f"{name} — last raced {item['most_recent_date']:%b %Y}{loc_str}"
    return name
```

#### FO-06: Month-based section headers

`group_by_month()` function defined in Architecture section. Feed rendering becomes:

```python
# In feed.py render():
month_groups = group_by_month(items)
for header, group_items in month_groups:
    st.subheader(header)
    for item in group_items:
        _render_feed_expander(item, expanded=False, key_prefix=f"feed_{header}")
```

Historical/dormant races go in a collapsed "Past Races" section at the bottom.

#### FO-07: Remove auto-expanded "Racing Soon" hero

Delete the "Racing Soon" section from `feed.py`. The countdown labels (FO-05) naturally create urgency for imminent races. All cards render with equal visual weight.

```python
# REMOVE this block from feed.py:
# if not isolated_series_id and not search_query:
#     racing_soon = [i for i in items if i["is_racing_soon"]]
#     ...
```

#### FO-08: Scannable card density

Move high-priority info into the expander label itself so the collapsed state is information-dense:

```
"Banana Belt Road Race — Mar 22, 2026 — in 11 days — Drain, OR"
```

The collapsed expander now carries name + date + countdown + location — enough for many decisions without expanding. When expanded, the card shows badges and content per the First Glance layout.

Additionally, reduce internal card padding by keeping Tier 2 content lazy-loaded (it's not rendered until expand).

#### Phase 2 Files

| File | Changes |
|------|---------|
| `raceanalyzer/ui/pages/feed.py` | Replace flat list with month-grouped agenda; remove "Racing Soon" hero; new expander labels with countdown + location; read new filters |
| `raceanalyzer/ui/components.py` | Add `render_feed_filters`; update `render_feed_card` for Tier 1/Tier 2 split |
| `raceanalyzer/queries.py` | Add `group_by_month`, `_race_types_for_discipline` |
| `tests/test_feed.py` | NEW — tests for month grouping, filter interactions, countdown labels in expander |

---

### Phase 3: First Glance Card Redesign (FG-01 → FG-08)

**Goal**: Reorder card content to match racer decision priority. Add missing data elements.

**Effort**: ~20% of sprint

#### FG-08 & FG-01: Card layout reorder + header redesign

The expander label now includes date + location + countdown (from Phase 2). The card body is reordered:

```python
def render_feed_card(item: dict, session=None, category=None):
    """Render feed card with racer-priority content ordering."""
    # --- Row 1: Quick-scan badges ("should I care?" row) ---
    cols = st.columns([1.5, 2, 1, 1])

    with cols[0]:
        # FG-02: Teammates badge
        teammates = item.get("teammate_names", [])
        if teammates:
            if len(teammates) <= 2:
                names = ", ".join(teammates)
                _render_badge(f"🚴 {names}", "#1565C0")
            else:
                _render_badge(f"🚴 {len(teammates)} teammates", "#1565C0")

    with cols[1]:
        # FG-03: Course character one-liner
        parts = []
        if item.get("course_type"):
            from raceanalyzer.elevation import course_type_display
            parts.append(course_type_display(item["course_type"]))
        if item.get("distance_m"):
            parts.append(f"{item['distance_m'] / 1000:.0f} km")
        if item.get("total_gain_m"):
            parts.append(f"{item['total_gain_m']:.0f}m gain")
        if parts:
            st.markdown(f"**{' — '.join(parts)}**")

    with cols[2]:
        # FG-05: Field size
        if item.get("field_size_display"):
            st.caption(item["field_size_display"])

    with cols[3]:
        # FG-06: Drop rate label (prominent)
        if item.get("drop_rate_label"):
            render_selectivity_badge(item["drop_rate_label"])

    # --- Row 1.5: Race type label (FG-07) ---
    if item.get("race_type"):
        rt_display = race_type_display_name(item["race_type"])
        st.caption(f"📋 {rt_display}")

    # --- Row 2: How it plays out (FG-04) ---
    col_pred, col_spark = st.columns([3, 1])
    with col_pred:
        if item.get("predicted_finish_type"):
            plain = finish_type_plain_english(item["predicted_finish_type"])
            if plain:
                st.write(plain)
            st.caption(finish_type_display_name(item["predicted_finish_type"]))
    with col_spark:
        # Sparkline is Tier 2 — load on demand
        detail = _get_tier2(session, item, category)
        if detail and detail.get("elevation_sparkline_points"):
            render_elevation_sparkline(detail["elevation_sparkline_points"])

    # --- Row 3: Deeper context (Tier 2 — lazy loaded) ---
    detail = _get_tier2(session, item, category)
    if detail:
        if detail.get("narrative_snippet"):
            st.write(detail["narrative_snippet"])
        if detail.get("racer_type_description"):
            st.caption(detail["racer_type_description"])
        if detail.get("duration_minutes"):
            d = detail["duration_minutes"]
            hours, mins = divmod(int(d["winner_duration_minutes"]), 60)
            st.caption(f"Typical duration: ~{hours}h {mins:02d}m")
        if detail.get("climb_highlight"):
            st.caption(detail["climb_highlight"])

    # --- Row 4: Action buttons ---
    if item.get("is_upcoming") and item.get("registration_url"):
        st.markdown(f"[Register]({item['registration_url']})")

    # --- Row 5: Historical editions (Tier 2) ---
    if detail:
        editions = detail.get("editions_summary", [])
        if editions and len(editions) > 1:
            with st.popover(f"{len(editions)} previous editions"):
                for ed in editions:
                    year_str = str(ed["year"]) if ed.get("year") else "?"
                    st.write(f"- {year_str}: {ed['finish_type_display']}")
```

Helper for lazy Tier 2 loading:

```python
def _get_tier2(session, item: dict, category: Optional[str]) -> Optional[dict]:
    """Load Tier 2 data on demand, caching in the item dict."""
    if item.get("narrative_snippet") is not None:
        return item  # already loaded
    if session is None:
        return None
    detail = get_feed_item_detail(session, item["series_id"], category=category)
    # Cache into item for subsequent calls within this render
    item.update(detail)
    return detail
```

#### FG-02: Teammates registered badge

Data comes from `teammate_names` in Tier 1 (populated by batch startlist query in Phase 1). Rendering shown above in Row 1.

#### FG-03: Course character one-liner

Data comes from `course_type`, `distance_m`, `total_gain_m` in Tier 1. Already available from batch course query. Rendering: `"Rolling — 62 km — 800m gain"`.

#### FG-04: Finish pattern prediction

Already built. Confirmed as Row 2 lead content in the new layout.

#### FG-05: Field size

Data comes from `field_size_display` in Tier 1, populated from `series_predictions.field_size_*` columns. Display: `"Usually 35-40 starters"`.

#### FG-06: Drop rate label prominence

Move from percentage-first to label-first. The `render_selectivity_badge` already renders colored labels ("Low attrition", "High attrition"). Position it in Row 1 alongside course character.

#### FG-07: Race type label

`race_type` is already on the Race model. `infer_race_type` falls back to `ROAD_RACE`. Display `race_type_display_name(item["race_type"])` as a small caption below Row 1.

#### Phase 3 Files

| File | Changes |
|------|---------|
| `raceanalyzer/ui/components.py` | Rewrite `render_feed_card` with new row ordering; add `_render_badge` helper; add `_get_tier2` lazy loader |
| `raceanalyzer/ui/pages/feed.py` | Pass `session` and `category` to `render_feed_card` for lazy loading |
| `tests/test_components.py` | Tests for card rendering with all field combinations (teammate badge, field size, missing data graceful degradation) |

---

### Phase 4: My Team Personalization (MT-01, MT-02)

**Goal**: One-time team name entry unlocks social signals on feed cards.

**Effort**: ~5% of sprint

#### MT-01: Set my team name

Add to sidebar via `render_feed_filters` (or a dedicated `render_team_setting`):

```python
def render_team_setting() -> Optional[str]:
    """Render team name input in sidebar. Returns current team name."""
    current = st.session_state.get("team_name", st.query_params.get("team", ""))
    team_name = st.sidebar.text_input(
        "My Team",
        value=current,
        placeholder="e.g. Team Rapha",
        key="team_name_input",
        help="Enter your team name to see which races your teammates are registered for.",
    )
    if team_name != st.session_state.get("team_name"):
        st.session_state["team_name"] = team_name
        if team_name:
            st.query_params["team"] = team_name
        elif "team" in st.query_params:
            del st.query_params["team"]
    return team_name or None
```

**Matching logic**: Case-insensitive substring match on `Startlist.team`. This handles variations like "Team Rapha" vs "TEAM RAPHA" vs "Rapha Racing". The batch query in Phase 1 already implements this via `Startlist.team.ilike(f"%{team_name}%")`.

#### MT-02: Teammate names on card

Already implemented in FG-02 (Phase 3). The teammate badge shows individual names (1-2 teammates) or a count (3+). Full list available on click/expand.

#### Phase 4 Files

| File | Changes |
|------|---------|
| `raceanalyzer/ui/components.py` | Add `render_team_setting` |
| `raceanalyzer/ui/pages/feed.py` | Call `render_team_setting()` in sidebar; pass `team_name` to feed query |
| `tests/test_teammates.py` | NEW — tests for team matching (case-insensitive, partial match, no match, multiple teammates) |

---

### Phase 5: Detail Dive Enhancements (DD-01 → DD-07)

**Goal**: Enrich the preview page with hero course profile, climb race context, team-grouped startlist, expanded racer type, finish type visualization, similar races, and course map.

**Effort**: ~15% of sprint

#### DD-01: Interactive course profile as hero

The profile visualization exists from Sprint 008. Ensure it's the first major visual element on the preview page:

```python
# In race_preview.py, move course profile to top:
def render():
    ...
    # Hero: Course Profile
    if preview_data.get("profile_points"):
        st.subheader("Course Profile")
        render_elevation_profile(preview_data["profile_points"], preview_data.get("climbs"))
        render_climb_legend()
    ...
```

#### DD-02: Climb-by-climb breakdown with race context

Add `render_climb_breakdown` to components:

```python
def render_climb_breakdown(climbs: list, predicted_ft: Optional[str], distance_km: Optional[float]):
    """Render each climb with stats and race-context narrative."""
    if not climbs:
        return

    st.subheader("Climb-by-Climb Breakdown")
    for i, climb in enumerate(sorted(climbs, key=lambda c: c.get("start_d", 0)), 1):
        start_km = climb.get("start_d", 0) / 1000
        length_km = climb.get("length_m", 0) / 1000
        avg_grade = climb.get("avg_grade", 0)
        max_grade = climb.get("max_grade", 0)
        end_km = start_km + length_km

        # Race context narrative
        context = _climb_race_context(
            climb_index=i,
            total_climbs=len(climbs),
            start_km=start_km,
            distance_km=distance_km,
            predicted_ft=predicted_ft,
            avg_grade=avg_grade,
        )

        st.markdown(
            f"**Climb {i}**: km {start_km:.1f}–{end_km:.1f} | "
            f"{length_km:.1f} km at {avg_grade:.1f}% avg "
            f"(max {max_grade:.0f}%)"
        )
        if context:
            st.caption(context)


def _climb_race_context(
    climb_index: int,
    total_climbs: int,
    start_km: float,
    distance_km: Optional[float],
    predicted_ft: Optional[str],
    avg_grade: float,
) -> str:
    """Generate a one-liner about what typically happens at this climb."""
    parts = []

    # Position context
    if distance_km and distance_km > 0:
        position_pct = start_km / distance_km
        if position_pct > 0.75:
            parts.append("Late in the race")
        elif position_pct > 0.5:
            parts.append("In the second half")

    # Selectivity context based on finish type
    if predicted_ft in ("gc_selective", "breakaway_selective"):
        if avg_grade >= 6:
            parts.append("this is where the field usually splits")
        else:
            parts.append("expect attacks here")
    elif predicted_ft in ("bunch_sprint", "small_group_sprint"):
        parts.append("the pack usually stays together through this")
    elif predicted_ft == "reduced_sprint":
        if climb_index == total_climbs:
            parts.append("the last real test before the sprint")
        else:
            parts.append("expect the pace to pick up here")

    return " — ".join(parts) + "." if parts else ""
```

#### DD-03: Startlist with team groupings

Add `render_team_grouped_startlist` to the preview page:

```python
def render_team_grouped_startlist(
    session: Session,
    series_id: int,
    category: Optional[str],
    user_team: Optional[str] = None,
):
    """Render startlist grouped by team, highlighting user's team."""
    entries = (
        session.query(Startlist)
        .filter(Startlist.series_id == series_id)
        .all()
    )
    if category:
        entries = [e for e in entries if e.category == category]
    if not entries:
        st.info("No startlist available for this race.")
        return

    # Group by team
    teams: dict[str, list] = {}
    for entry in entries:
        team = entry.team or "Unattached"
        teams.setdefault(team, []).append(entry)

    # Sort: user's team first, then by team size descending
    def team_sort_key(team_name: str) -> tuple:
        is_user_team = (
            user_team and user_team.lower() in team_name.lower()
        )
        return (0 if is_user_team else 1, -len(teams[team_name]), team_name)

    st.subheader(f"Startlist ({len(entries)} registered)")

    for team_name in sorted(teams.keys(), key=team_sort_key):
        members = teams[team_name]
        is_highlighted = user_team and user_team.lower() in team_name.lower()
        icon = "⭐" if is_highlighted else ""
        with st.expander(f"{icon} {team_name} ({len(members)} riders)", expanded=is_highlighted):
            for member in sorted(members, key=lambda m: m.carried_points or 0, reverse=True):
                pts = f" — {member.carried_points:.0f} pts" if member.carried_points else ""
                st.write(f"- {member.rider_name}{pts}")
```

#### DD-04: Expanded racer type description

Extend `racer_type_description` in `predictions.py` with a longer-form variant:

```python
RACER_TYPE_EXPANDED: dict[tuple[str, str], str] = {
    ("flat", "bunch_sprint"): (
        "This race favors sprinters and pack riders because the course is mostly "
        "flat with no significant climbs to break up the field. In most editions, "
        "the race ends in a bunch sprint. Riders who can stay in the draft and "
        "position well for the final kilometer tend to do best."
    ),
    ("flat", "breakaway"): (
        "Despite the flat terrain, breakaways have historically stuck in this race. "
        "Strong riders who can sustain a solo effort or work in a small group have "
        "an edge. The pack may not organize a chase."
    ),
    ("rolling", "bunch_sprint"): (
        "The rolling terrain creates surges but hasn't been enough to split the field "
        "in past editions. Riders who can handle repeated short climbs and still have "
        "a sprint at the finish do well."
    ),
    ("rolling", "reduced_sprint"): (
        "The hills thin the field, but a group of strong riders usually arrives together "
        "for a sprint. Punchy riders who can handle repeated surges and still kick at "
        "the end thrive here."
    ),
    ("hilly", "gc_selective"): (
        "This race is a pure climbing test. The field shatters on the climbs and only "
        "the strongest climbers survive in the front group. Expect to be riding alone "
        "or in very small groups for significant portions of the race."
    ),
    # ... (extend for all combinations in RACER_TYPE_DESCRIPTIONS)
}


def racer_type_description_expanded(
    course_type: Optional[str],
    finish_type: Optional[str],
    edition_count: int = 0,
) -> Optional[str]:
    """Return expanded racer type paragraph for preview page."""
    if not course_type or not finish_type:
        return None
    expanded = RACER_TYPE_EXPANDED.get((course_type, finish_type))
    if expanded and edition_count > 0:
        expanded = expanded.replace("In most editions", f"In {edition_count} previous editions")
    return expanded
```

#### DD-05: Historical finish type pattern visualization

Render a compact visual row of finish-type icons per year:

```python
def render_finish_type_timeline(editions_summary: list[dict]):
    """Render a visual timeline of finish types across editions."""
    if not editions_summary or len(editions_summary) < 2:
        return

    st.subheader("Historical Pattern")
    # Build HTML row of colored dots with year labels
    html_parts = ['<div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">']
    for ed in reversed(editions_summary):  # oldest first
        year = ed.get("year", "?")
        ft = ed.get("finish_type", "unknown")
        color = FINISH_TYPE_COLORS.get(ft, "#9E9E9E")
        icon_svg = FINISH_TYPE_ICONS.get(ft, FINISH_TYPE_ICONS["unknown"])
        display = FINISH_TYPE_DISPLAY_NAMES.get(ft, "Unknown")
        html_parts.append(
            f'<div style="text-align:center;" title="{year}: {display}">'
            f'{icon_svg}'
            f'<div style="font-size:0.75em;color:#666;">{year}</div>'
            f'</div>'
        )
    html_parts.append('</div>')
    st.markdown("".join(html_parts), unsafe_allow_html=True)
```

#### DD-06: Similar races cross-reference

Add to preview page using the `compute_similarity` function from Architecture section:

```python
def get_similar_series(
    session: Session,
    series_id: int,
    top_n: int = 3,
    min_score: float = 50.0,
) -> list[dict]:
    """Find similar series by course type, finish type, and distance."""
    target_course = session.query(Course).filter(Course.series_id == series_id).first()
    target_pred = (
        session.query(SeriesPrediction)
        .filter_by(series_id=series_id, category=None)
        .first()
    )
    if not target_course and not target_pred:
        return []

    target = {
        "course_type": target_course.course_type.value if target_course and target_course.course_type else None,
        "predicted_finish_type": target_pred.predicted_finish_type if target_pred else None,
        "distance_m": target_course.distance_m if target_course else None,
        "discipline": None,
    }

    # Get all other series with courses
    all_courses = session.query(Course).filter(Course.series_id != series_id).all()
    all_preds = {
        p.series_id: p
        for p in session.query(SeriesPrediction).filter(
            SeriesPrediction.category.is_(None)
        ).all()
    }

    candidates = []
    for course in all_courses:
        pred = all_preds.get(course.series_id)
        candidate = {
            "series_id": course.series_id,
            "course_type": course.course_type.value if course.course_type else None,
            "predicted_finish_type": pred.predicted_finish_type if pred else None,
            "distance_m": course.distance_m,
            "discipline": None,
        }
        score = compute_similarity(target, candidate)
        if score >= min_score:
            series = session.get(RaceSeries, course.series_id)
            candidates.append({
                "series_id": course.series_id,
                "display_name": series.display_name if series else "Unknown",
                "score": score,
            })

    candidates.sort(key=lambda c: -c["score"])
    return candidates[:top_n]
```

Render on preview page:

```python
similar = get_similar_series(session, series_id)
if similar:
    st.subheader("Similar Races")
    for s in similar:
        if st.button(s["display_name"], key=f"similar_{s['series_id']}"):
            st.query_params["series_id"] = str(s["series_id"])
            st.rerun()
```

#### DD-07: Course map with race features

Already built in Sprint 008. Ensure it's placed alongside the course profile on the preview page. No new code needed — just confirm layout position.

#### Phase 5 Files

| File | Changes |
|------|---------|
| `raceanalyzer/ui/pages/race_preview.py` | Reorder layout: hero profile → climb breakdown → finish type timeline → racer type expanded → startlist with teams → similar races → map; add team highlighting |
| `raceanalyzer/ui/components.py` | Add `render_climb_breakdown`, `render_finish_type_timeline`, `render_team_grouped_startlist` |
| `raceanalyzer/predictions.py` | Add `RACER_TYPE_EXPANDED`, `racer_type_description_expanded` |
| `raceanalyzer/queries.py` | Add `get_similar_series`, `compute_similarity` |
| `tests/test_preview.py` | NEW — tests for climb context generation, similarity scoring, team grouping |

---

## Files Summary

| File | Phase(s) | Nature of Change |
|------|----------|-----------------|
| `raceanalyzer/db/models.py` | 1 | Add `SeriesPrediction` model, `Discipline` enum |
| `raceanalyzer/queries.py` | 1, 2, 5 | Major rewrite: `get_feed_items_batch`, `get_feed_item_detail`, `countdown_label`, `group_by_month`, `discipline_for_race_type`, `compute_similarity`, `get_similar_series`, `PerfTimer` |
| `raceanalyzer/precompute.py` | 1 | NEW — prediction pre-computation pipeline |
| `raceanalyzer/predictions.py` | 5 | Add `RACER_TYPE_EXPANDED`, `racer_type_description_expanded` |
| `raceanalyzer/ui/pages/feed.py` | 2, 3, 4 | Major rewrite: month-grouped agenda, new filters, team input, lazy card loading |
| `raceanalyzer/ui/components.py` | 2, 3, 4, 5 | Major: `render_feed_card` rewrite, `render_feed_filters`, `render_team_setting`, `render_climb_breakdown`, `render_finish_type_timeline`, `render_team_grouped_startlist` |
| `raceanalyzer/ui/pages/race_preview.py` | 5 | Layout reorder, new sections (climb breakdown, timeline, similar races, team startlist) |
| `tests/test_queries.py` | 1, 2 | Tests for batch query, countdown, discipline, month grouping |
| `tests/test_precompute.py` | 1 | NEW — precomputation tests |
| `tests/test_feed.py` | 2 | NEW — feed rendering integration tests |
| `tests/test_components.py` | 3 | Card rendering tests with all field combinations |
| `tests/test_teammates.py` | 4 | NEW — team matching tests |
| `tests/test_preview.py` | 5 | NEW — preview enhancement tests |

---

## Definition of Done

### Phase 1: Performance & Query Foundation
- [ ] `SeriesPrediction` model added to `models.py` with migration
- [ ] `Discipline` enum and `discipline_for_race_type` function added
- [ ] `precompute.py` created with `precompute_series_predictions` and `precompute_all`
- [ ] `_calculate_field_size` returns median/min/max from historical results
- [ ] `precompute_all` called after scrape completes
- [ ] `get_feed_items_batch` replaces `get_feed_items` — single-digit query count
- [ ] Batch query loads all races, courses, predictions, and teammates in ≤6 queries
- [ ] `PerfTimer` instrumentation on all feed query phases
- [ ] Feed renders in <1s cold cache, <200ms warm cache (50 series)
- [ ] `@st.cache_data(ttl=300)` on main feed query
- [ ] `get_feed_item_detail` loads Tier 2 data on demand
- [ ] Existing tests pass (no regressions)
- [ ] New tests for batch query, countdown_label, discipline derivation, field size calculation
- [ ] New tests for precomputation (series with/without data, multiple categories)

### Phase 2: Feed Organization & Filtering
- [ ] Discipline filter in sidebar with URL persistence
- [ ] Race type filter conditional on discipline selection
- [ ] State/region multiselect with URL persistence
- [ ] All filter values survive page reload via query params
- [ ] `countdown_label` returns "Today", "Tomorrow", "in N days", "in N weeks"
- [ ] Expander labels show: `Name — Date — countdown — Location`
- [ ] Feed grouped by month headers ("March 2026", "April 2026", ...)
- [ ] Past/dormant races in collapsed "Past Races" section
- [ ] "Racing Soon" auto-expanded hero section removed
- [ ] At least 4-5 collapsed cards visible on screen without scrolling
- [ ] New tests for month grouping (empty months, single item, cross-year)
- [ ] New tests for filter URL persistence round-trip

### Phase 3: First Glance Card Redesign
- [ ] Card Row 1: teammates badge + course one-liner + field size + drop rate label
- [ ] Card Row 2: finish type prediction (plain English) + sparkline
- [ ] Card Row 3: narrative + racer type + duration + climb highlight
- [ ] Card Row 4: registration link (if upcoming)
- [ ] Card Row 5: historical editions popover
- [ ] Location and date in expander header, not in card body caption
- [ ] Race type label displayed on card (FG-07)
- [ ] Graceful degradation: missing distance → no distance shown (not error)
- [ ] Graceful degradation: missing teammates → no badge (not empty badge)
- [ ] Graceful degradation: missing field size → no field size shown
- [ ] New tests for card rendering with all data present
- [ ] New tests for card rendering with each field missing

### Phase 4: My Team Personalization
- [ ] Team name text input in sidebar
- [ ] Team name persists to `st.query_params["team"]`
- [ ] Team name survives page reload
- [ ] Teammate matching: case-insensitive substring on `Startlist.team`
- [ ] Teammate badge shows names (1-2) or count (3+)
- [ ] No badge when no teammates or no team set
- [ ] New tests for team matching (case variations, partial match, no match)

### Phase 5: Detail Dive Enhancements
- [ ] Course profile is hero visualization at top of preview page
- [ ] Climb-by-climb breakdown with stats and race context narrative
- [ ] `_climb_race_context` generates position-aware and finish-type-aware sentences
- [ ] Startlist grouped by team, user's team highlighted and sorted first
- [ ] Startlist shows rider count and carried_points per rider
- [ ] Expanded racer type description (full paragraph) on preview page
- [ ] Historical finish type timeline with colored icons per year
- [ ] Similar races section showing top 3 matches with clickable navigation
- [ ] `compute_similarity` scores on course_type, finish_type, distance, discipline
- [ ] Course map confirmed in preview layout alongside profile
- [ ] New tests for climb context generation
- [ ] New tests for similarity scoring (same course type, different distance, etc.)
- [ ] New tests for team-grouped startlist ordering

---

## Risks

| # | Risk | Impact | Likelihood | Mitigation |
|---|------|--------|------------|------------|
| 1 | **Scope is too large for one sprint** | High | High | Phases are independent. Phase 1 (performance) + Phase 2 (organization) deliver the highest-value changes. Phases 4 and 5 can slip to Sprint 012 without blocking. |
| 2 | **Pre-computation adds complexity to scrape pipeline** | Medium | Medium | `precompute_all` is a standalone function called after scrape. If it fails, feed falls back to on-demand computation (slower but functional). |
| 3 | **Streamlit expander label limits information density** | Medium | Medium | Expander labels are plain text — no HTML or markdown. Countdown + location may make labels long. Test with real data; truncate location if needed. |
| 4 | **Team name matching is too fuzzy** | Low | Medium | Substring match on team name could match unrelated teams ("Team A" matches "Team Awesome"). Mitigate with exact-match option or confirmation UI. Start with substring; refine if false positives appear. |
| 5 | **Similar races algorithm too simplistic** | Low | Low | Simple heuristic (course_type + finish_type + distance) may surface irrelevant matches. The `min_score=50` threshold filters weak matches. Can add more factors later. |
| 6 | **`series_predictions` table gets stale** | Medium | Low | `last_computed` timestamp tracks freshness. `precompute_all` runs after every scrape. Could add a staleness check that falls back to on-demand if `last_computed` is too old. |
| 7 | **Caching stale data after filter changes** | Medium | Medium | `@st.cache_data` is keyed on all filter values (category, discipline, race_type, states, team_name). Cache invalidates when any filter changes. TTL of 300s prevents indefinite staleness. |
| 8 | **Lazy loading creates visible content shift** | Low | Medium | When user expands a card, Tier 2 content loads and the card height changes. Streamlit handles this natively (expanders resize). Could add a skeleton/loading state if noticeable. |
| 9 | **Month grouping edge cases** | Low | Low | Series with no upcoming_date, races spanning midnight, etc. Defensive: filter for `upcoming_date is not None` before grouping. Historical races go in "Past Races" section. |
| 10 | **Migration complexity for SeriesPrediction table** | Low | Low | SQLite schema migration via Alembic or manual `CREATE TABLE`. No foreign key enforcement issues. Table can be dropped and recreated without data loss (it's all derived). |
| 11 | **N+1 in editions_summary within Tier 2** | Medium | High | `_compute_overall_finish_type` per edition is still N+1 within Tier 2. Mitigate by pre-computing edition-level finish types in `series_predictions` or by batch-loading classifications for all editions of a series in one query. |

---

## Security

- **Team name input**: Sanitized via `html.escape` before rendering in any HTML context. Stored only in session state and URL params — no database writes.
- **URL query params**: All filter values validated against known options before use. Unknown discipline/race_type values ignored (fall back to "All").
- **SQL injection**: All queries use SQLAlchemy ORM parameterized queries. `search_series` escapes LIKE wildcards. No raw SQL.
- **XSS**: All user-provided text (`team_name`, `search_query`) escaped with `html.escape` before inclusion in `unsafe_allow_html=True` markdown blocks.

---

## Dependencies

- **No new Python packages required**. All features built with existing stack: Streamlit, SQLAlchemy, pandas, standard library.
- **Internal dependencies between phases**:
  - Phase 2 depends on Phase 1 (batch queries, `countdown_label`)
  - Phase 3 depends on Phase 1 (Tier 1/Tier 2 split, `field_size_display`, `teammate_names`)
  - Phase 4 depends on Phase 1 (batch teammate query) and Phase 3 (teammate badge rendering)
  - Phase 5 depends on Phase 1 (`SeriesPrediction` for similarity, `get_feed_item_detail`) — but could also run in parallel with Phases 3-4

---

## Open Questions

1. **Sprint scope**: 31 use cases is ambitious. The phasing allows Phases 4-5 to slip. Should we commit to Phases 1-3 as the hard scope and treat 4-5 as stretch goals?

2. **Discipline modeling**: The derivation function approach is proposed. Should we also add a `discipline` column to `RaceSeries` for cases where inference fails (e.g., a gravel race whose name doesn't contain "gravel")? This would require a data backfill.

3. **Team matching precision**: Substring match is simple but may cause false positives. Should we offer exact match + substring match modes, or start with substring and iterate?

4. **Startlist availability**: Not all races have startlists. How should the teammate badge behave for races without startlist data? Current proposal: no badge (no noise). Should we show "No startlist yet" to set expectations?

5. **Pre-computation timing**: Should `precompute_all` run synchronously after scrape (simpler, slower scrape) or asynchronously (faster scrape, complexity)? Synchronous is proposed as the default.

6. **Feed pagination UX**: Current "Show more" button loads more items. With month grouping, should pagination be per-month (show one month at a time) or still a flat count?

7. **Historical races in agenda view**: Show them in a collapsed "Past Races" section below upcoming months? Or hide entirely and make them accessible only via search/browse? The former is proposed.

8. **Backward compatibility**: Should `get_feed_items` be kept as a deprecated wrapper around `get_feed_items_batch`, or removed outright? Keeping it avoids breaking any code that calls it directly.
