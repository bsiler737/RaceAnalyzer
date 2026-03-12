# Sprint 011 (Codex Draft): Feed First Glance, Detail Dive, My Team, Feed Organization & Performance

## Overview

Sprint 011 implements all 31 use cases in `docs/USE_CASES_FEED_FIRST_GLANCE.md` across five areas:

- **First Glance (FG-01 → FG-08)**: Make the feed card answer decision factors in priority order with **no click required**.
- **Detail Dive (DD-01 → DD-07)**: Upgrade the Race Preview into a true “detail dive” with course/climb context, teams, patterns, and similarity.
- **My Team (MT-01 → MT-02)**: Lightweight personalization (no login) to surface teammate context in feed + preview.
- **Feed Organization (FO-01 → FO-08)**: Multi-axis filtering + month-based agenda layout + density improvements.
- **Performance (PF-01 → PF-06)**: Remove N+1s, introduce caching, lazy detail loading, precompute predictions, query-layer pagination, and instrumentation/budgets.

### Current implementation snapshot (observed)

- **Feed UI**: `raceanalyzer/ui/pages/feed.py` renders items from `queries.get_feed_items()` and uses `st.expander` for every card. The “Racing Soon” section auto-expands items. Labels use `SOON` / `UPCOMING`.
- **Feed query**: `raceanalyzer/queries.py:get_feed_items()` loops series and runs many per-series queries (upcoming race, most recent, edition count, course row, predictions, durations, drop rate, editions summary).
- **Models**: ORM models live in `raceanalyzer/db/models.py` (the path `raceanalyzer/models.py` referenced in the prompt does not exist in this repo).
- **Race preview**: `raceanalyzer/ui/pages/race_preview.py` already has the interactive profile component and map integration (Sprint 008), but does not yet include team-grouped startlists, finish-pattern visualization, similar races, or climb context text.

### Conventions / constraints

- A top-level `CLAUDE.md` is not present in this repository; this draft follows observable conventions from:
  - `pyproject.toml` (ruff/pytest configuration, Python 3.9 target, 100-char lines)
  - existing sprint drafts in `docs/sprints/drafts/`
  - current module boundaries: `queries.py` as a testable aggregation layer; `predictions.py` for derived stats; Streamlit pages/components for rendering; “graceful degradation” for missing data.
- SQLite only; avoid Postgres-only SQL features.
- No new dependencies unless unavoidable.
- Preserve deep-link patterns via `st.query_params`.

---

## Use Cases

This sprint covers **all** use cases below, grouped by area and mapped to phases (see Implementation).

### First Glance (FG)

- **FG-01 (P0)**: Date + location in card header.
- **FG-02 (P0)**: Teammates registered badge.
- **FG-03 (P1)**: Course character one-liner: terrain + distance + gain.
- **FG-04 (P1)**: Finish pattern prediction remains lead content.
- **FG-05 (P1)**: Field size on the card (registered or historical typical).
- **FG-06 (P2)**: Drop rate remains prominent; emphasize label more than raw %.
- **FG-07 (P2)**: Race type icon/label.
- **FG-08 (P0)**: Reorder card content to match decision priority.

### Detail Dive (DD)

- **DD-01 (P0)**: Interactive course profile hero visualization (already built; ensure it’s centerpiece).
- **DD-02 (P1)**: Climb-by-climb breakdown + race-context one-liners.
- **DD-03 (P1)**: Startlist grouped by team, highlight user team.
- **DD-04 (P2)**: Expand “what kind of racer does well here?” into a paragraph with reasoning.
- **DD-05 (P2)**: Historical finish type pattern visualization (icons across editions).
- **DD-06 (P1)**: Similar races cross-reference.
- **DD-07 (P2)**: Course map with race features (already built; integrate with features like climbs markers).

### My Team (MT)

- **MT-01 (P0)**: Set team name once (sidebar/settings) with persistence.
- **MT-02 (P1)**: Teammate names on the feed card (names for 1–2, count otherwise).

### Feed Organization (FO)

- **FO-01 (P0)**: Discipline filter (road/gravel/CX/MTB/track).
- **FO-02 (P1)**: Race type filter within discipline.
- **FO-03 (P0)**: Geographic filter by state/region.
- **FO-04 (P1)**: Persistent filter preferences (URL + local persistence).
- **FO-05 (P0)**: Replace SOON/UPCOMING with days-until countdown labels.
- **FO-06 (P0)**: Month-based section headers (agenda view).
- **FO-07 (P1)**: Remove “Racing Soon” hero emphasis.
- **FO-08 (P1)**: Scannable card density (4–5 cards visible).

### Performance (PF)

- **PF-01 (P0)**: Eliminate N+1 queries in feed query.
- **PF-02 (P0)**: Cache feed results at query layer.
- **PF-03 (P1)**: Lazy-load expanded card content (tiered loading).
- **PF-04 (P1)**: Precompute and store prediction results at scrape time.
- **PF-05 (P1)**: Paginate at query layer (LIMIT/OFFSET) not Python slicing.
- **PF-06 (P0)**: Instrument and enforce performance budget.

---

## Architecture

### Key design decisions

1. **Move away from `st.expander` as the primary card shell.**
   - The use cases require “no click required” first glance, which is incompatible with “everything is inside an expander.”
   - Proposed: every feed item renders as a **compact always-visible summary card** (`st.container(border=True)`), with an optional “Details” button that fetches and renders Tier-2 content.

2. **Introduce explicit tiering in feed data: Summary vs Detail.**
   - **Tier 1 (summary, always loaded)**: fields needed for FG + FO scanning and filtering.
   - **Tier 2 (detail, loaded on demand)**: narrative snippet, sparkline points, climb highlight, duration, editions summary, etc.

3. **Batch-load feed summary data in one query plan.**
   - Replace the per-series loop in `get_feed_items()` with a small number of bulk queries that return:
     - base series list (filtered)
     - upcoming race row per series
     - most-recent race row per series
     - edition count per series
     - course aggregates per series
     - startlist counts (and teammate matches) per series (conditional)
     - field sizes (historical typical) per series (conditional on category)

4. **Prediction/storage plan: precompute into a dedicated table.**
   - To meet PF-04 and simplify PF-01, precompute series-level predictions/statistics and store them.
   - Because the repo currently has no migration mechanism beyond `Base.metadata.create_all`, this sprint should include a **lightweight SQLite schema migration utility** (or explicitly document “rebuild DB” as a stopgap).

### Proposed data contracts

Use typed dicts or dataclasses (internal) to make the split explicit.

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass(frozen=True)
class FeedFilters:
    category: Optional[str]
    disciplines: Optional[list[str]]          # e.g., ["road", "gravel"]
    race_types: Optional[list[str]]           # RaceType enum values
    states: Optional[list[str]]               # ["WA", "OR", ...]
    search_query: Optional[str]

@dataclass(frozen=True)
class FeedCardSummary:
    series_id: int
    display_name: str
    upcoming_date: Optional[datetime]
    most_recent_date: Optional[datetime]
    location: Optional[str]
    state_province: Optional[str]
    discipline: str                           # derived
    race_type: Optional[str]                  # enum value
    course_type: Optional[str]
    distance_m: Optional[float]
    total_gain_m: Optional[float]
    countdown_label: Optional[str]            # "Tomorrow", "in 6 days", ...
    predicted_finish_type: Optional[str]
    finish_confidence: Optional[str]
    drop_rate_pct: Optional[int]
    drop_rate_label: Optional[str]
    field_size_label: Optional[str]           # "28 registered" / "Usually 35–40"
    teammate_badge: Optional[str]             # "Jake, Maria registered" / "3 teammates registered"
    registration_url: Optional[str]

@dataclass(frozen=True)
class FeedCardDetail:
    narrative_snippet: Optional[str]
    elevation_sparkline_points: list[dict]
    climb_highlight: Optional[str]
    racer_type_description: Optional[str]
    duration_minutes: Optional[dict]
    editions_summary: list[dict]
```

### Discipline modeling (FO-01)

The existing DB models include `Race.race_type` (`RaceType` enum) but do not model discipline. This sprint can meet FO-01 in two steps:

**Step A (no schema change; immediate value): derive discipline at query time**

- A `derive_discipline()` function maps the best available signal to discipline:
  - If `race_type == GRAVEL` → `gravel`
  - If race name contains CX keywords → `cyclocross`
  - If race name contains MTB keywords → `mtb`
  - If race name contains track keywords → `track`
  - Else default → `road`

```python
def derive_discipline(*, race_type_value: Optional[str], race_name: str) -> str:
    ...
```

**Step B (optional; schema-backed): store `discipline` on `RaceSeries`**

- Add `RaceSeries.discipline` as `String` or `SAEnum` for stability and query performance.
- Requires migration strategy (see Dependencies / Risks).

### Query-layer structure (PF-01, PF-05)

Replace `get_feed_items()` with:

```python
def get_feed_page(
    session: Session,
    *,
    filters: FeedFilters,
    page: int,
    page_size: int,
    today: Optional[datetime] = None,
) -> tuple[list[FeedCardSummary], int]:
    """Returns summaries + total_count (after filters)."""

def get_feed_card_detail(
    session: Session,
    *,
    series_id: int,
    category: Optional[str],
) -> FeedCardDetail:
    """Compute Tier-2 detail for one series (cached)."""
```

### Batch SQL patterns (concrete)

The core pattern is to select **one upcoming** and **one most-recent** race row per series using window functions (SQLite supports them).

**Upcoming race per series**

```sql
WITH upcoming AS (
  SELECT
    r.*,
    row_number() OVER (PARTITION BY r.series_id ORDER BY r.date ASC) AS rn
  FROM races r
  WHERE r.date >= :today
)
SELECT * FROM upcoming WHERE rn = 1;
```

**Most recent race per series**

```sql
WITH recent AS (
  SELECT
    r.*,
    row_number() OVER (PARTITION BY r.series_id ORDER BY r.date DESC) AS rn
  FROM races r
  WHERE r.date IS NOT NULL
)
SELECT * FROM recent WHERE rn = 1;
```

**Edition counts per series**

```sql
SELECT series_id, COUNT(*) AS edition_count
FROM races
GROUP BY series_id;
```

**Startlist “registered count” per series/category**

```sql
SELECT series_id, category, COUNT(*) AS registered
FROM startlists
GROUP BY series_id, category;
```

**SQLAlchemy implementation sketch (window functions)**

The intent is to keep this inside `queries.py` and return plain dicts (no ORM objects) for cacheability.

```python
from sqlalchemy import func, select

def _first_race_per_series_subquery(*, ascending: bool, today: Optional[datetime] = None):
    order = Race.date.asc() if ascending else Race.date.desc()
    rn = func.row_number().over(partition_by=Race.series_id, order_by=order).label("rn")

    stmt = select(
        Race.id.label("race_id"),
        Race.series_id.label("series_id"),
        Race.date.label("date"),
        Race.location.label("location"),
        Race.state_province.label("state_province"),
        Race.race_type.label("race_type"),
        Race.registration_url.label("registration_url"),
        rn,
    ).where(Race.date.isnot(None))

    if today is not None:
        stmt = stmt.where(Race.date >= today)

    return stmt.subquery()

upcoming_sq = _first_race_per_series_subquery(ascending=True, today=today)
recent_sq = _first_race_per_series_subquery(ascending=False)

base_stmt = (
    select(
        RaceSeries.id.label("series_id"),
        RaceSeries.display_name.label("display_name"),
        upcoming_sq.c.date.label("upcoming_date"),
        upcoming_sq.c.location.label("upcoming_location"),
        upcoming_sq.c.state_province.label("upcoming_state"),
        upcoming_sq.c.race_type.label("upcoming_race_type"),
        upcoming_sq.c.registration_url.label("registration_url"),
        recent_sq.c.date.label("most_recent_date"),
        recent_sq.c.location.label("most_recent_location"),
        recent_sq.c.state_province.label("most_recent_state"),
        recent_sq.c.race_type.label("most_recent_race_type"),
        func.count(Race.id).label("edition_count"),
        Course.course_type.label("course_type"),
        Course.distance_m.label("distance_m"),
        Course.total_gain_m.label("total_gain_m"),
    )
    .select_from(RaceSeries)
    .join(Race, Race.series_id == RaceSeries.id)
    .outerjoin(Course, Course.series_id == RaceSeries.id)
    .outerjoin(upcoming_sq, (upcoming_sq.c.series_id == RaceSeries.id) & (upcoming_sq.c.rn == 1))
    .outerjoin(recent_sq, (recent_sq.c.series_id == RaceSeries.id) & (recent_sq.c.rn == 1))
    .group_by(RaceSeries.id)
)
```

Sorting/pagination then becomes:

- Sort key:
  - tier 0: upcoming (by upcoming_date asc)
  - tier 1: historical (by most_recent_date desc)
- Apply `LIMIT/OFFSET` after filters and sort.

```python
from sqlalchemy import case

is_upcoming = upcoming_sq.c.date.isnot(None)
sort_stmt = base_stmt.order_by(
    case((is_upcoming, 0), else_=1),        # upcoming first
    upcoming_sq.c.date.asc().nulls_last(),
    recent_sq.c.date.desc().nulls_last(),
    RaceSeries.display_name.asc(),
).limit(page_size).offset(page * page_size)
```

This sketch is intentionally “query-only”: additional per-series features (field sizes, teammates) should be computed via separate bulk queries keyed by the visible `series_id`s, then merged in Python.

**User team matches per series/category (for FG-02, MT-02)**

Normalize team names in Python and store a normalized copy (optional) for speed:

- If schema-backed: add `Startlist.team_norm` computed at scrape time.
- Else: normalize on read for the subset of rows in the user’s selected category.

```sql
SELECT series_id, category, rider_name, team
FROM startlists
WHERE category = :category;
```

**Historical “typical field size” per series/category**

Preferred, robust approach (no reliance on `Result.field_size` consistency):

```sql
SELECT r.series_id, res.race_id, res.race_category_name AS category, COUNT(*) AS starters
FROM results res
JOIN races r ON r.id = res.race_id
WHERE res.race_category_name = :category
GROUP BY r.series_id, res.race_id, res.race_category_name;
```

Then compute per-series median (and an interquartile-ish band) in Python:

- `median_starters`
- `p25_starters`, `p75_starters` (approx via sorting; no percentile func needed)

### Caching strategy (PF-02, PF-03)

Use the existing Streamlit convention of ignoring the session in cache keys via underscore arg names:

- `@st.cache_data(ttl=300)` on `get_feed_page_cached(_session, filters_json, page, page_size, today_date)`
- `@st.cache_data(ttl=300)` on `get_feed_card_detail_cached(_session, series_id, category)`

Cache only JSON-serializable payloads (lists/dicts), not ORM objects.

### Precompute predictions (PF-04)

Add a new table for series-level “snapshotted” computations:

`series_predictions` (proposed)

- `id` (pk)
- `series_id` (fk race_series.id)
- `category` (nullable string; NULL = “all categories”)
- `computed_at` (datetime)
- `predicted_finish_type` (string enum value)
- `confidence` (string)
- `edition_count` (int)
- `finish_distribution_json` (text json)
- `drop_rate` (float, nullable)
- `drop_rate_label` (string, nullable)
- `duration_winner_minutes` (float, nullable)
- `duration_field_minutes` (float, nullable) (optional)
- `typical_field_median` (int, nullable) (optional)

This table is written by a CLI command invoked after scraping/classifying:

```python
@main.command("compute-predictions")
@click.option("--category", multiple=True)
def compute_predictions(...):
    """Compute/refresh series_predictions rows for all series."""
```

Feed summary reads from this table via JOINs rather than recomputing per series.

---

## Implementation (phased approach)

### Phase 0 — Guardrails, definitions, and instrumentation (PF-06 foundations)

Deliverables:

- Define a single countdown formatter used everywhere (FO-05):

```python
def countdown_label(*, race_date: datetime, today: datetime) -> str:
    """Today/Tomorrow/in N days/in N weeks (floor)."""
```

- Add timing + query-count instrumentation for feed queries:
  - Total wall time
  - DB time (best-effort: wrap query execution segments)
  - Number of SQL statements executed (SQLAlchemy event listener in debug mode)

Concrete hook (dev-only):

```python
from sqlalchemy import event

class QueryCounter:
    count: int = 0

def install_query_counter(engine, counter: QueryCounter) -> None: ...
```

Exit criteria:

- Debug output shows `total_ms`, `sql_count`, and per-stage timings for feed load.

### Phase 1 — Feed summary card redesign (FG-01/08, FO-05/06/07/08 baseline)

Goal: meet “no click required” first glance by replacing expanders with compact summary cards.

1. Replace feed expander loop with summary-card loop:
   - Render: header line + row 1 quick-scan badges + row 2 finish pattern + sparkline (optional small) + actions.
   - Remove “Racing Soon” hero section entirely (FO-07).
   - Organize upcoming items by month headers (FO-06), with a collapsed “Past races” section (optional).

2. Header content (FG-01 + FO-05):
   - `Race Name — Mar 22, 2026 — Drain, OR — in 11 days`
   - Replace `SOON`/`UPCOMING` with countdown.

3. Card density (FO-08):
   - Use 2–3 compact rows.
   - Avoid large `st.write()` blocks in the default view; prefer `st.caption()` and badges.
   - Provide a “Details” button or toggle that expands Tier-2 content (PF-03 enabler).

Concrete component APIs:

```python
def render_feed_card_summary(item: FeedCardSummary, *, key_prefix: str) -> None: ...
def render_feed_card_detail(detail: FeedCardDetail, *, key_prefix: str) -> None: ...
```

Exit criteria:

- Feed shows month headers for upcoming races.
- No “Racing Soon” auto-expanded block exists.
- Every card exposes FG-01 and FO-05 at a glance.
- At least 4 cards fit in a typical laptop viewport (qualitative check).

### Phase 2 — Filtering + persistence (FO-01/02/03/04)

Goal: add discipline, race type, and geo filters with persistence.

1. Filters UI (sidebar):
   - Discipline multi-select: `["road", "gravel", "cyclocross", "mtb", "track"]` default “road” or “all” (decision needed).
   - Race type multi-select: depends on chosen discipline (FO-02).
   - Geography multi-select: default PNW (`Settings().pnw_regions`) (FO-03).
   - Category remains global.

2. Persistence (FO-04):
   - URL params:
     - `category=...`
     - `disc=road,gravel`
     - `type=criterium,road_race`
     - `state=WA,OR`
     - `team=...` (optional; see Security)
   - Local persistence:
     - Save/load from `data/user_prefs.json` (repo-local) or `~/.raceanalyzer/prefs.json` (user-local) using stdlib JSON.
     - On first render: load prefs into `st.session_state` if URL doesn’t override.

Concrete functions:

```python
def parse_feed_filters_from_query_params(params: dict[str, str]) -> FeedFilters: ...
def sync_feed_filters_to_query_params(filters: FeedFilters) -> None: ...

def load_user_prefs() -> dict: ...
def save_user_prefs(prefs: dict) -> None: ...
```

Exit criteria:

- Changing filters updates URL.
- Reloading the app retains filters (URL and/or local prefs).
- Discipline and race type filters reduce feed items correctly.

### Phase 3 — “My Team” + teammate surfacing (MT-01/02, FG-02)

Goal: unlock social proof and teammate awareness.

1. Sidebar “My Team” input (MT-01):
   - `st.sidebar.text_input("My Team", key="team_name", ...)`
   - Save to prefs on change (Phase 2 infrastructure).

2. Feed teammate badge (FG-02, MT-02):
   - For each series, find matching startlist entries where normalized team matches user team.
   - If 1–2 names: `Jake, Maria registered`
   - If 3+: `3 teammates registered` with optional popover listing names

Batch query approach:

- Query all startlists for visible series IDs and selected category (or all categories if none).
- Filter in Python by `team_norm == user_team_norm`.
- Build per-series: `names[:2]`, `count`.

Function signatures:

```python
def normalize_team_name(name: str) -> str: ...

def get_teammates_by_series(
    session: Session,
    *,
    series_ids: list[int],
    category: Optional[str],
    team_name: str,
) -> dict[int, list[str]]:
    """series_id -> list of rider_name"""
```

Exit criteria:

- Team name persists across sessions.
- Feed cards show teammate badge only when matches exist.
- Preview page highlights user team in team-grouped startlist (DD-03 prerequisite).

### Phase 4 — Detail Dive upgrades (DD-02/03/04/05/06; DD-01/DD-07 integration)

Goal: make Race Preview the “one click deep” detail experience described in the use cases.

1. Climb breakdown with context (DD-02):
   - Render a table/list of climbs from `climbs_json`:
     - start km, end km, length, gain, avg/max grade
   - Add context one-liner derived from finish pattern + where the climb falls:
     - If predicted/selective + climb occurs after 60% of distance → “Likely selection point”
     - If sprinty + early climb small → “Probably not decisive”

Concrete helper:

```python
def climb_context_line(
    *,
    climb: dict,
    distance_m: Optional[float],
    predicted_finish_type: Optional[str],
    drop_rate_label: Optional[str],
) -> str:
    ...
```

2. Startlist grouped by team (DD-03):
   - New query:

```python
def get_startlist_team_blocks(
    session: Session,
    *,
    series_id: int,
    category: Optional[str],
    user_team: Optional[str],
) -> list[dict]:
    """Each block: {team, count, riders:[...], is_user_team} sorted by count desc."""
```

   - Render:
     - “Top teams” blocks (count + names)
     - Highlight user team block

3. Expanded racer type description (DD-04):
   - Build a long-form paragraph combining:
     - course type description (`COURSE_TYPE_DESCRIPTIONS`)
     - predicted finish type plain-English
     - historical finish pattern (DD-05 data)

```python
def racer_type_long_form(
    *,
    course_type: Optional[str],
    predicted_finish_type: Optional[str],
    finish_pattern: list[dict],  # years + finish types
    distance_km: Optional[float],
    total_gain_m: Optional[float],
) -> str:
    ...
```

4. Historical finish pattern visualization (DD-05):
   - For a chosen category:
     - Use `RaceClassification` for that race+category when available.
   - For “all categories”:
     - Use a deterministic “overall” rule (existing helper `_compute_overall_finish_type()`).
   - Render a horizontal row of icons (from `FINISH_TYPE_ICONS`) with year labels and tooltips.

5. Similar races (DD-06):
   - Query candidate series with similar course type and distance band (±20%) and same discipline.
   - Score candidates in Python:
     - +3 same course_type
     - +2 same predicted finish type (from precompute table or lightweight compute)
     - minus normalized distance diff
     - minus normalized gain diff
   - Return top 3–5 with deep links to their preview pages.

```python
def get_similar_series(
    session: Session,
    *,
    series_id: int,
    category: Optional[str],
    limit: int = 5,
) -> list[dict]:
    """{series_id, display_name, reason, distance_km, gain_m, course_type, predicted_finish_type}"""
```

Exit criteria:

- Preview page includes climb list with context.
- Preview page includes startlist grouped by team (when startlists exist).
- Preview page includes finish pattern icons.
- Preview page includes similar races list with links.

### Phase 5 — Performance overhaul (PF-01/02/03/04/05)

Goal: make feed fast and stable under reruns.

1. Replace `get_feed_items()` with `get_feed_page()` that:
   - Applies filters in SQL (discipline derived via race_type/name; race_type/state/category/search filters).
   - Computes ordering in SQL where possible:
     - Upcoming first by date asc, then historical by most recent desc.
   - Applies `LIMIT/OFFSET` (PF-05).
   - Batch-loads series-level fields (PF-01).

2. Cache feed summaries (PF-02):

```python
@st.cache_data(ttl=300)
def get_feed_page_cached(_session, filters_json: str, page: int, page_size: int, today: str):
    ...
```

3. Lazy-load Tier-2 (PF-03):
   - UI only calls `get_feed_card_detail_cached()` for series where the user clicked “Details”.
   - Store expanded series IDs in `st.session_state.expanded_series_ids: set[int]`.

4. Precompute predictions (PF-04):
   - Add `series_predictions` model + CLI command `raceanalyzer compute-predictions`.
   - `get_feed_page()` joins this table for:
     - predicted finish type + confidence
     - drop rate + label
     - typical duration
     - typical field size (if stored)

5. Validate performance budget (PF-06):
   - With instrumentation enabled, verify:
     - cold cache: < 1.0s for default filters
     - warm cache: < 200ms
     - SQL statement count is bounded (target: O(10), not O(series))

Exit criteria:

- Feed summary load is O(1) queries with respect to series count.
- “Details” computation happens only for expanded items.
- Instrumentation demonstrates meeting budgets in dev dataset.

---

## Files Summary

Expected primary changes (and why):

- `raceanalyzer/ui/pages/feed.py`: replace expander-based feed with month-grouped agenda, filters, and tiered detail loading.
- `raceanalyzer/ui/components.py`: new compact feed summary renderer; teammate badge; race type + discipline badges; finish-pattern mini components reused in preview.
- `raceanalyzer/queries.py`: replace `get_feed_items()` with paginated/batched `get_feed_page()` + `get_feed_card_detail()`; add helper queries (field sizes, teammates).
- `raceanalyzer/predictions.py`: add long-form racer type helpers and climb-context helpers; refactor prediction logic to support precompute pipeline.
- `raceanalyzer/db/models.py`: add `SeriesPrediction` model (and optionally discipline field / normalized team fields).
- `raceanalyzer/cli.py`: add `compute-predictions` command and (if chosen) a `migrate` command for SQLite schema upgrades.
- `raceanalyzer/ui/pages/race_preview.py`: add DD sections (climbs w/ context, team-grouped startlist, finish pattern icons, similar races).
- `tests/` (new/updated): unit tests for countdown labels, discipline derivation, query pagination/filtering correctness, teammate matching, and similar-race scoring.

---

## Definition of Done

- **FG**: Feed cards show header `name + date + location + countdown`; quick-scan row includes teammates (if any), course one-liner, field size label, and drop rate label.
- **FO**: Discipline/race type/state filters exist, apply correctly, and persist across reloads; feed is month-grouped; “Racing Soon” hero section removed.
- **MT**: Team name input exists and persists; teammate badge logic works and is silent when no matches.
- **DD**: Preview shows interactive profile as hero, climb breakdown with context, team-grouped startlist, finish pattern visualization, similar races list; map with race features remains integrated.
- **PF**: Feed query has no N+1 behavior; feed summaries are cached; detail is lazy-loaded; pagination is query-layer; instrumentation exists; performance budgets are met on a representative dataset.
- **Quality**: `ruff check .` passes; `pytest` passes; new functionality has targeted tests.

---

## Risks

- **Scope risk**: 31 use cases across UI/query/data/perf is large; strict phasing is required to avoid “half-shipped everywhere.”
- **Schema migration risk**: adding `series_predictions` (and optional discipline fields) requires a migration approach; `create_all()` will not alter existing SQLite tables.
- **Streamlit interaction limits**: “true expander lazy-load” is not possible without explicit state controls; requires UI pattern change (button/toggle).
- **Data completeness**: some series may lack course stats (`distance_m`, `total_gain_m`), startlists, or consistent `race_type`; UI must degrade gracefully.
- **Team name matching**: messy real-world team strings can cause false negatives/positives; normalization rules must be conservative and test-backed.
- **Performance measurement**: wall time can vary across machines; budgets should be enforced in dev mode with logging rather than hard test assertions at first.

---

## Security

- **SQL safety**: continue using SQLAlchemy filters; escape wildcard characters in search (existing `search_series()` already does this).
- **XSS/HTML**: any custom badge rendering via `unsafe_allow_html=True` must escape user-provided strings (team name, location, series name) before interpolation.
- **Local prefs**: storing team name locally is sensitive-but-low-stakes; prefer user-local file path and document location. Avoid storing teammate names persistently.
- **URL params**: putting team name in URL can leak via screenshots/shared links. Default: persist team locally; only put in URL if user opts in (open question).

---

## Dependencies

- No new third-party dependencies required for the proposed approach.
- Requires Python 3.9+ (already in `pyproject.toml`) and existing dependencies: SQLAlchemy, Streamlit, pandas, Plotly, Folium.
- If schema migrations are implemented, they should be stdlib-based (SQLite `PRAGMA table_info`, `ALTER TABLE`, and/or “rebuild DB” workflow).

---

## Open Questions

1. **Discipline storage**: derive discipline at query time only, or add `RaceSeries.discipline` persisted in DB?
2. **Prediction persistence**: should `series_predictions` store per-category rows for commonly-used categories only, or compute lazily and cache per-category on demand?
3. **Team name persistence & privacy**: should team name be persisted only locally, or also in URL params for deep linking?
4. **Field size definition**: prefer “registered count” when startlist exists; otherwise “median starters” from results—confirm wording and thresholds.
5. **Finish pattern visualization granularity**: for “all categories,” compute per-edition overall finish type (existing helper) or require category selection to avoid misleading aggregation?
6. **Feed default view**: should default discipline be “Road” (persona) or “All” (more general)?
7. **Performance budget enforcement**: log-only vs. failing assertions in tests for query counts/timing.
