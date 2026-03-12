# Sprint 011: Feed First Glance, Detail Dive, Personalization & Performance

## Overview

Sprint 011 transforms the feed from a functional list into a racer-first decision tool. The feed card's first glance answers "should I care?" in under 3 seconds by surfacing information in the racer's actual decision priority order: date/logistics → social → course → finish type → field → drop rate. The card does this without requiring any click or expansion — adopting `st.container(border=True)` instead of `st.expander` so all first-glance data is always visible.

Beyond the card, the detail dive (preview page) becomes a confidence-builder with hero course profiles, climb breakdowns with race context, team-grouped startlists, and similar-race cross-references. A lightweight "My Team" feature unlocks social signals. Feed organization replaces vague tier labels with countdown timers, month-grouped agenda views, and multi-dimensional filtering. Performance work eliminates the N+1 query problem and introduces caching, lazy loading, and pre-computation.

**Scope**: 31 use cases across 5 areas (First Glance, Detail Dive, My Team, Feed Organization, Performance).

**Phasing** (5 phases, ordered by dependency):
1. **Performance & Query Foundation** — must come first; subsequent phases depend on batch-loaded data and caching
2. **Feed Organization & Filtering** — restructures the feed container and filtering
3. **First Glance Card Redesign** — reorders and enriches card content using container cards
4. **My Team Personalization** — adds social layer on top of redesigned cards
5. **Detail Dive Enhancements** — enriches the preview page accessed from cards

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
| DD-07 | Course map with race features | P2 | Built (Sprint 008) — add climb markers |

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
  → render cards (all content computed upfront, inside st.expander)
```

**Proposed**:
```
feed.py render()
  → queries.get_feed_items_batch(session, filters)
    → ONE query: all series + races (batch, grouped in Python)
    → ONE query: all courses (JOIN series)
    → ONE query: pre-computed predictions (JOIN series_predictions)
    → ONE query: teammate matches (if team_name set)
    → Assemble Tier 1 (summary card) data in Python
    → Return list[dict] with Tier 1 populated
  → render container cards (Tier 1 always visible, no click needed)
  → on "Details" click: queries.get_feed_item_detail(session, series_id, category)
    → compute narrative, sparkline, climb highlight, racer type desc, editions
    → return Tier 2 data (cached per series+category)
```

### Key Architectural Decisions

**1. Container cards replace expanders (FG-08 mandate)**

The "no click required" first-glance principle is incompatible with `st.expander`, which hides content until clicked. Feed items now use `st.container(border=True)` for an always-visible summary card. A "Details" button within the container toggles Tier 2 content via `st.session_state.expanded_series_ids: set[int]`, avoiding full-page scroll jumps.

```python
# Card rendering pattern:
with st.container(border=True):
    # Always visible: header, quick-scan badges, finish prediction
    _render_card_header(item)
    _render_quick_scan_row(item)
    _render_finish_prediction(item)

    # Action row: Register + Details toggle
    cols = st.columns([1, 1, 4])
    with cols[0]:
        if item.get("registration_url"):
            st.link_button("Register", item["registration_url"])
    with cols[1]:
        expanded = item["series_id"] in st.session_state.get("expanded_ids", set())
        if st.button("Details" if not expanded else "Less", key=f"detail_{item['series_id']}"):
            _toggle_expanded(item["series_id"])

    # Tier 2: only rendered when expanded
    if item["series_id"] in st.session_state.get("expanded_ids", set()):
        detail = get_feed_item_detail_cached(session, item["series_id"], category)
        _render_tier2_content(detail)
```

**2. Discipline derived from race_type (no schema change)**

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

**3. New `series_predictions` table for pre-computed data (PF-04)**

```python
class SeriesPrediction(Base):
    __tablename__ = "series_predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("race_series.id"), index=True)
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)

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

    last_computed: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("series_id", "category", name="uq_series_cat"),
    )
```

**4. Tiered data model: Tier 1 (always) vs Tier 2 (on demand)**

**Tier 1** — always loaded for every visible card (cheap, batch-queried):
- series_id, display_name, location, state_province
- upcoming_date, most_recent_date, days_until, countdown_label
- is_upcoming, race_type, discipline (derived)
- course_type, distance_m, total_gain_m
- predicted_finish_type, confidence
- drop_rate_pct, drop_rate_label
- field_size_display, registration_url, edition_count
- teammate_names (from startlist batch query)

**Tier 2** — loaded on "Details" click (expensive, cached per series+category):
- narrative_snippet, elevation_sparkline_points
- climb_highlight, racer_type_description
- duration_minutes, editions_summary

**5. Team name matching: normalized substring**

Case-insensitive substring match with a minimum 3-character guard to prevent false positives:

```python
def get_teammates_by_series(session, series_ids, category, team_name):
    if not team_name or len(team_name.strip()) < 3:
        return {}
    normalized = team_name.strip()
    teammates = (
        session.query(Startlist.series_id, Startlist.rider_name)
        .filter(
            Startlist.series_id.in_(series_ids),
            func.lower(Startlist.team).contains(normalized.lower()),
        )
        .all()
    )
    result = {}
    for sid, name in teammates:
        result.setdefault(sid, []).append(name)
    return result
```

**6. Countdown label logic**

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

**7. Month grouping for agenda view**

```python
def group_by_month(items: list[dict]) -> list[tuple[str, list[dict]]]:
    from itertools import groupby
    upcoming = sorted(
        [i for i in items if i["is_upcoming"]],
        key=lambda i: i["upcoming_date"] or date.max,
    )
    historical = [i for i in items if not i["is_upcoming"]]

    groups = []
    for (year, month), group_items in groupby(
        upcoming, key=lambda i: (i["upcoming_date"].year, i["upcoming_date"].month)
    ):
        header = f"{date(year, month, 1):%B %Y}"
        groups.append((header, list(group_items)))

    if historical:
        groups.append(("Past Races", historical))
    return groups
```

**8. Similar races scoring heuristic (DD-06)**

```python
def compute_similarity(series_a: dict, series_b: dict) -> float:
    score = 0.0
    if series_a["course_type"] == series_b["course_type"]:
        score += 40
    if series_a["predicted_finish_type"] == series_b["predicted_finish_type"]:
        score += 30
    da, db = series_a.get("distance_m"), series_b.get("distance_m")
    if da and db and da > 0 and db > 0:
        ratio = min(da, db) / max(da, db)
        if ratio > 0.75:
            score += 20 * ((ratio - 0.75) / 0.25)
    if series_a.get("discipline") == series_b.get("discipline"):
        score += 10
    return score
```

Top 3 similar races shown on preview page where `score >= 50`.

**9. Performance instrumentation**

```python
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

---

## Implementation

### Phase 1: Performance & Query Foundation (PF-01 → PF-06, ~35%)

**Goal**: Eliminate N+1 queries, add pre-computation, caching, and instrumentation. All subsequent phases build on batch-loaded data.

**Tasks:**
- [ ] Add `SeriesPrediction` model to `raceanalyzer/db/models.py` with composite unique constraint `(series_id, category)`
- [ ] Add `Discipline` enum and `discipline_for_race_type()` to `raceanalyzer/queries.py`
- [ ] Create `raceanalyzer/precompute.py` with `precompute_series_predictions()` and `precompute_all()`
- [ ] Add `compute-predictions` CLI command to `raceanalyzer/cli.py`; integrate into post-scrape workflow
- [ ] Implement `get_feed_items_batch()` in `raceanalyzer/queries.py` — batch-loads all series, races, courses, predictions, and teammates in ≤6 SQL queries
- [ ] Add `get_feed_item_detail()` for lazy Tier 2 loading
- [ ] Wrap both with `@st.cache_data(ttl=300)` (cache keys: filter tuple + category + team_name)
- [ ] Add `PerfTimer` instrumentation around each query phase; log totals; warn if over budget
- [ ] Add `countdown_label()` utility
- [ ] Tests: batch query correctness, countdown logic, discipline derivation, precompute pipeline, field size calculation

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/db/models.py` | Modify | Add `SeriesPrediction` model |
| `raceanalyzer/queries.py` | Modify | Add `get_feed_items_batch`, `get_feed_item_detail`, `countdown_label`, `Discipline`, `discipline_for_race_type`, `PerfTimer` |
| `raceanalyzer/precompute.py` | Create | `precompute_series_predictions`, `precompute_all`, `_calculate_field_size` |
| `raceanalyzer/cli.py` | Modify | Add `compute-predictions` command |
| `tests/test_queries.py` | Modify | Tests for batch query, countdown, discipline |
| `tests/test_precompute.py` | Create | Tests for precomputation pipeline |

**Exit criteria:**
- `get_feed_items_batch` executes ≤6 SQL queries for the full dataset (verified via query counter)
- `@st.cache_data` wraps both feed and detail queries
- Instrumentation logs timing for each query phase
- `compute-predictions` CLI command works and integrates with scrape workflow
- All new functions have test coverage

---

### Phase 2: Feed Organization & Filtering (FO-01 → FO-08, ~25%)

**Goal**: Replace flat feed with month-grouped agenda, add multi-dimensional filters, replace vague labels with countdowns, remove "Racing Soon" hero.

**Tasks:**
- [ ] Add `render_feed_filters()` to sidebar: discipline, race type (conditional on discipline), state/region multi-select
- [ ] Sync all new filters to `st.query_params` with idempotence guards (prevent rerun loops)
- [ ] Implement `group_by_month()` and render month headers with `st.subheader`
- [ ] Replace "SOON"/"UPCOMING" labels with countdown labels from `countdown_label()`
- [ ] Remove "Racing Soon" auto-expanded section entirely
- [ ] Historical/dormant races in collapsed "Past Races" section at bottom
- [ ] Add empty-state UX: "No races match your filters" with "Clear filters" button
- [ ] Backward compatibility: existing `?series_id=` and `?category=` URLs continue to work
- [ ] Tests: month grouping, filter interactions, empty states, countdown in card headers

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/ui/pages/feed.py` | Modify | Month-grouped agenda, remove "Racing Soon", read new filters, empty states |
| `raceanalyzer/ui/components.py` | Modify | Add `render_feed_filters`, `_race_types_for_discipline` |
| `raceanalyzer/queries.py` | Modify | Add `group_by_month` |
| `tests/test_feed.py` | Create | Tests for month grouping, filters, empty states |

**Exit criteria:**
- Feed is month-grouped with clear headers (e.g., "March 2026", "April 2026")
- "Racing Soon" section removed; countdown labels on every upcoming card
- Discipline, race type, and state filters functional and URL-persistent
- Existing Sprint 010 deep links (`?series_id=N`, `?category=X`) still work
- Empty-state UX when filters yield zero results

---

### Phase 3: First Glance Card Redesign (FG-01 → FG-08, ~20%)

**Goal**: Replace `st.expander` with `st.container(border=True)` cards. Reorder card content to match racer decision priority. Add missing data elements. All first-glance data visible without any click.

**Tasks:**
- [ ] Replace `st.expander` feed items with `st.container(border=True)` summary cards
- [ ] Card header: Race name + date + location + countdown (FG-01, FO-05)
- [ ] Row 1 quick-scan badges: teammates (if any) + terrain + distance + gain + field size + drop rate label (FG-02, FG-03, FG-05, FG-06)
- [ ] Row 2: finish type prediction plain English + race type label (FG-04, FG-07)
- [ ] "Details" button toggles Tier 2 content (narrative, sparkline, climb highlight, duration, editions) via `st.session_state.expanded_ids`
- [ ] Row 3 (Tier 2, on demand): narrative snippet + racer type description + duration + climb highlight
- [ ] Row 4: registration link + View Preview button
- [ ] Row 5 (Tier 2): editions popover
- [ ] Graceful degradation: cards render correctly when any of {course data, startlists, predictions, climb data} are missing
- [ ] Target: ≥4 summary cards visible on a standard desktop viewport (1080p)
- [ ] Tests: card rendering with all field combinations, missing data scenarios

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/ui/components.py` | Modify | Rewrite `render_feed_card` with container cards, new row ordering, `_render_badge` helper |
| `raceanalyzer/ui/pages/feed.py` | Modify | Replace expander loop with container card loop, pass session/category for lazy loading |
| `tests/test_components.py` | Modify | Tests for card rendering, graceful degradation |

**Exit criteria:**
- Feed cards use `st.container(border=True)`, not `st.expander`
- First-glance data (date, location, countdown, terrain, distance, gain, field size, drop rate label, finish prediction) visible without clicking
- Teammate badge appears when team name is set and matches exist
- Missing data doesn't break cards (terrain badge hidden if no course, field size hidden if no predictions, etc.)
- ≥4 summary cards visible on standard desktop viewport

---

### Phase 4: My Team Personalization (MT-01, MT-02, ~5%)

**Goal**: One-time team name entry unlocks social signals on feed cards.

**Tasks:**
- [ ] Add `render_team_setting()` to sidebar — text input with `st.query_params["team"]` persistence
- [ ] Minimum 3-character guard on team name to prevent false positives
- [ ] Pass team_name through to `get_feed_items_batch` for teammate matching
- [ ] Teammate badge already rendered in Phase 3 card layout (FG-02 / MT-02)
- [ ] Tests: team matching edge cases (short strings rejected, case-insensitive, partial match, no match, multiple teammates across series)

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/ui/components.py` | Modify | Add `render_team_setting` |
| `raceanalyzer/ui/pages/feed.py` | Modify | Call `render_team_setting()`, pass team_name to queries |
| `tests/test_teammates.py` | Create | Team matching tests |

**Exit criteria:**
- Team name persists via `st.query_params["team"]` across page reloads
- Teammate badge appears on cards where normalized substring matches exist
- Short team names (<3 chars) are silently ignored (no badge, no query)
- No badge when team name not set or no matches found

---

### Phase 5: Detail Dive Enhancements (DD-01 → DD-07, ~15%)

**Goal**: Enrich the preview page with hero course profile, climb race context, team-grouped startlist, expanded racer type, finish type visualization, similar races, and enhanced course map.

**Tasks:**
- [ ] DD-01: Move interactive course profile to top of preview page as hero visualization
- [ ] DD-02: Add climb-by-climb breakdown with race-context narratives (use hedged language unless strong historical evidence). Context rules:
  - Climb after 60% of distance + selective finish type → "Likely where the field splits"
  - Early/small climb + sprint finish type → "Unlikely to be decisive"
  - High drop rate + any significant climb → "This climb sheds riders"
- [ ] DD-03: Group startlist by team. Highlight user's team (from MT-01). Show team block counts. Sort by team size descending.
- [ ] DD-04: Expand racer type description into a full paragraph combining course type, finish type, historical pattern, and course-specific reasoning
- [ ] DD-05: Historical finish type pattern — render a horizontal row of finish type icons (from `FINISH_TYPE_ICONS`) with year labels and tooltips, per edition. Source: `race_classifications` for the selected category (or overall computation for "all categories")
- [ ] DD-06: Similar races — query all other series, score via `compute_similarity()`, show top 3 with `score >= 50` as deep links to their preview pages. Show "No similar races found" if <3 candidates.
- [ ] DD-07: Add climb markers to the Folium course map (colored markers at climb start positions with grade info)
- [ ] Tests: climb context generation, similarity scoring, startlist grouping, finish pattern computation

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/ui/pages/race_preview.py` | Modify | Hero profile, climb breakdown, team startlist, similar races, finish pattern viz |
| `raceanalyzer/ui/components.py` | Modify | Add `render_climb_breakdown`, `render_finish_pattern`, `render_similar_races`, `render_team_startlist` |
| `raceanalyzer/predictions.py` | Modify | Add `racer_type_long_form`, `climb_context_line` |
| `raceanalyzer/queries.py` | Modify | Add `get_similar_series`, `get_startlist_team_blocks` |
| `tests/test_predictions.py` | Modify | Tests for climb context, expanded racer type |
| `tests/test_queries.py` | Modify | Tests for similarity scoring, startlist grouping |

**Exit criteria:**
- Preview page opens with interactive course profile as the hero element
- Climb breakdown shows each climb with stats and hedged race-context narrative
- Startlist grouped by team with user's team highlighted (when set)
- Expanded racer type paragraph explains why the course favors certain racers
- Historical finish pattern shows icons per edition year
- Similar races section shows 1-3 comparable races with deep links (or "No similar races" if none)
- Course map includes climb markers

---

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/db/models.py` | Modify | Add `SeriesPrediction` table |
| `raceanalyzer/queries.py` | Modify | Batch feed query, feed detail, countdown, discipline, month grouping, similar series, startlist grouping, PerfTimer |
| `raceanalyzer/precompute.py` | Create | Pre-computation pipeline for predictions, drop rate, duration, field size |
| `raceanalyzer/predictions.py` | Modify | Expanded racer type, climb context narratives |
| `raceanalyzer/cli.py` | Modify | `compute-predictions` CLI command |
| `raceanalyzer/ui/pages/feed.py` | Modify | Container cards, month agenda, filters, countdown labels, remove "Racing Soon", empty states |
| `raceanalyzer/ui/components.py` | Modify | Feed filters, container card rendering, team setting, badges, climb/pattern/similarity components |
| `raceanalyzer/ui/pages/race_preview.py` | Modify | Hero profile, climb breakdown, team startlist, similar races, finish pattern |
| `tests/test_queries.py` | Modify | Batch query, countdown, discipline, similarity, startlist grouping |
| `tests/test_precompute.py` | Create | Precomputation pipeline tests |
| `tests/test_feed.py` | Create | Month grouping, filter interactions, empty states |
| `tests/test_teammates.py` | Create | Team matching edge cases |
| `tests/test_components.py` | Modify | Card rendering, graceful degradation |
| `tests/test_predictions.py` | Modify | Climb context, expanded racer type |

---

## Definition of Done

### Performance (PF)
- [ ] `get_feed_items_batch` executes ≤6 SQL queries for the full dataset (verified via SQLAlchemy event listener or query counter in tests)
- [ ] Feed page loads in <1s (cold cache) and <200ms (warm cache) for a dataset of 50+ series, measured via `PerfTimer` logging
- [ ] SQL statement count is O(1) with respect to series count (no N+1)
- [ ] `@st.cache_data(ttl=300)` wraps feed summary and detail queries
- [ ] `series_predictions` table is populated by `compute-predictions` CLI command
- [ ] `compute-predictions` integrates into scrape workflow or staleness check warns at render time

### Feed Organization (FO)
- [ ] Feed organized by month headers ("March 2026", "April 2026", etc.) for upcoming races
- [ ] "Racing Soon" section removed entirely; all upcoming cards have equal visual weight
- [ ] Countdown labels replace "SOON"/"UPCOMING": Today / Tomorrow / in N days / in N weeks
- [ ] Discipline, race type, state filters exist in sidebar, apply correctly, and persist via `st.query_params`
- [ ] Race type filter is conditional on selected discipline
- [ ] Existing `?series_id=` and `?category=` deep links remain functional
- [ ] Empty state: "No races match your filters" with "Clear filters" action when filters yield zero results
- [ ] Past/dormant races in collapsed section below upcoming months

### First Glance (FG)
- [ ] Feed cards use `st.container(border=True)`, not `st.expander`
- [ ] Card header shows: race name + date + location + countdown
- [ ] Quick-scan row shows: teammate badge (if matches) + terrain badge + distance + gain + field size + drop rate label
- [ ] Finish type prediction (plain English) is the visual headline of the card body
- [ ] Race type label visible on each card
- [ ] ≥4 summary cards visible on a standard 1080p desktop viewport
- [ ] Graceful degradation: cards render correctly when any of {course data, startlists, predictions, climb data} are absent — missing elements are simply hidden, not errored

### My Team (MT)
- [ ] Sidebar text input for "My Team" persists via `st.query_params["team"]`
- [ ] Team names <3 characters are silently ignored (no query, no badge)
- [ ] Teammate badge: 1-2 names shown, 3+ shows count
- [ ] No badge when no team name set or no matches found

### Detail Dive (DD)
- [ ] Preview page leads with interactive course profile as hero visualization
- [ ] Climb-by-climb breakdown with stats (start km, length, avg grade, max grade) and hedged race-context narrative
- [ ] Startlist grouped by team, user's team highlighted, sorted by team size
- [ ] Expanded racer type paragraph with course-specific reasoning
- [ ] Historical finish type icons per edition year
- [ ] Similar races section: 1-3 comparable races with deep links, or "No similar races"
- [ ] Course map includes climb markers at climb start positions

### Quality
- [ ] `ruff check .` passes
- [ ] `pytest` passes with no regressions
- [ ] New test files: `test_precompute.py`, `test_feed.py`, `test_teammates.py`
- [ ] Existing test files updated: `test_queries.py`, `test_components.py`, `test_predictions.py`

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Overscope** — 31 use cases is aggressive for one sprint | High | High | Strict phasing; P0 use cases (14 items) are the hard floor; P1 (12) and P2 (5) are stretch within the sprint. If time runs short, defer P2 items to Sprint 012. |
| **Container card density** — `st.container` may not achieve 4-5 cards on screen | Medium | High | Spike the container card pattern in Phase 3 before committing. If density target can't be met, fall back to hybrid approach (container summary + expander for details). |
| **Streamlit scroll-jump** — "Details" button triggers full rerun, potentially losing scroll position | Medium | Medium | Track expanded IDs in `st.session_state`; use `st.fragment` if available in the Streamlit version; test scroll behavior during Phase 3. |
| **Schema migration** — `SeriesPrediction` table requires `CREATE TABLE` on existing DBs | Low | Medium | `Base.metadata.create_all()` handles new table creation. No column additions to existing tables needed (discipline is derived, not stored). |
| **Cache staleness** — predictions cached for 5 minutes may be stale after scrape | Medium | Low | `compute-predictions` updates `last_computed`; add a dev-mode staleness warning if `last_computed` is older than the most recent race result. |
| **Team name false positives** — short substrings match too many teams | Medium | Low | Minimum 3-character guard; normalized case-insensitive matching; UI shows actual matched names for verification. |
| **Discipline derivation misclassification** — keyword matching could misclassify edge cases | Low | Low | Current dataset is overwhelmingly road discipline; derivation is simple enum mapping, not keyword-based. CX/MTB/track not yet in dataset. |
| **Widget rerun loops** — multiple filter widgets synced to query params can trigger cascading reruns | Medium | Medium | Guard query-param writes with idempotence checks: only write if value actually changed. |
| **Data completeness** — some series lack course data, startlists, or historical results | High | Low | All Tier 1 fields gracefully degrade: missing course → no terrain/distance/gain; missing startlist → no teammate badge; missing predictions → no finish type/drop rate. Tested in DoD. |

---

## Security Considerations

- **SQL injection**: All queries use SQLAlchemy parameterized bindings. Team name search uses `func.lower().contains()`, not raw string interpolation.
- **XSS via `unsafe_allow_html`**: Any badge/icon rendering that uses `st.markdown(unsafe_allow_html=True)` must HTML-escape user-provided strings (team name, location, series name) before interpolation.
- **Team name in URL**: `st.query_params["team"]` puts team name in the URL, which could leak via screenshots or shared links. Acceptable for team names (not PII), but document this behavior.
- **Startlist data**: Rider names and team names from startlists are publicly available data. Aggregating "teammates registered" does not introduce new privacy concerns.

---

## Dependencies

- **No new Python dependencies** — uses existing: SQLAlchemy, Streamlit, pandas, Plotly, Folium, Click
- **Sprint 008**: Elevation profiles, climb detection, course type classification, interactive maps
- **Sprint 009**: Road-results startlists with team names, event discovery
- **Sprint 010**: Feed page, global category filter, URL state persistence, deep linking

---

## Open Questions

1. **Feed default discipline**: Should default be "Road" (matches persona) or "All"? Recommendation: default "All" since the dataset is currently all-road; switch to "Road" default when multi-discipline data exists.

2. **Precompute staleness check**: Should the feed warn/auto-recompute if `series_predictions.last_computed` is older than the newest race result? Recommendation: log a warning in dev mode; auto-recompute is a Sprint 012 enhancement.

3. **Similar races on preview vs feed**: Should similar races appear only on the preview page (DD-06), or also as a "Related races" section on the card? Recommendation: preview page only for Sprint 011; card is already dense.

4. **Historical editions category**: DD-05 finish pattern visualization — use the globally selected category, or show "overall"? Recommendation: use the selected category if set, fall back to overall computation otherwise.

5. **Stage races / multi-day events**: Countdown rules (FO-05) should use start date. If an event spans months, group by start month. Document this as a convention.
