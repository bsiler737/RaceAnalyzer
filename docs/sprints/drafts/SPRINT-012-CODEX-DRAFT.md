# Sprint 012: Course-Based Prediction & Data Quality — Codex Draft

## Overview

Sprint 012 exists because the flagship feature of RaceAnalyzer — "Can I survive this race?" — is broken for 45% of all races. The time-gap classifier (`classification/finish_type.py`) requires finish-time data that 630 races simply do not have and will never get. The UX audit walked 10 beginner-racer journeys and found 13 remaining issues; five of them (Issues #5, #15, #16, #17, and partially #6) trace back to this single gap. Fixing it is the highest-leverage change available.

The approach is deliberately incremental. Phase 1 builds and tests a course-based finish type predictor as a standalone, pure-function module that requires no new data. Phase 2 wires it into the pre-computation pipeline so `SeriesPrediction` rows get populated. Phase 3 fills the `race_type` gap on upcoming races by inheriting from series history. Phase 4 fixes the six remaining UI/UX issues from the audit. Each phase produces a testable, deployable improvement — a user benefits from Phase 1+2 even if Phase 4 slips.

The guiding engineering principle is testability first. The course predictor is a pure function of course and race-type attributes, making it trivially unit-testable with no database fixtures. The race-type inheritance logic is a single SQL-backed function that can be tested against synthetic series histories. The UI fixes are small, isolated changes with clear before/after states. Every function introduced in this sprint can be verified independently, and every phase has an explicit exit criterion tied to measurable outcomes (coverage percentage, query count, visual behavior).

---

## Use Cases

### Course-Based Prediction (CP-01 -> CP-06)

| ID | Name | Priority | Issue | Status |
|----|------|----------|-------|--------|
| CP-01 | Predict finish type from course profile | P0 | #5 | Gap — no course-based predictor exists |
| CP-02 | Predict finish type from race_type alone | P0 | #5 | Gap — criteriums lack course data but should still predict bunch_sprint |
| CP-03 | Integrate course prediction into precompute pipeline | P0 | #5, #17 | Gap — `precompute.py` only uses time-gap predictions |
| CP-04 | Populate "Who does well here?" from course predictions | P1 | #16 | Gap — `racer_type_long_form()` returns None for UNKNOWN finish type |
| CP-05 | Enable similarity scoring for course-predicted series | P1 | #15 | Gap — `compute_similarity()` scores 0 when finish_type is unknown |
| CP-06 | Track prediction source (time-gap vs course-based) | P1 | OQ #4 | Gap — no way to distinguish prediction provenance |

### Data Pipeline (DP-01 -> DP-03)

| ID | Name | Priority | Issue | Status |
|----|------|----------|-------|--------|
| DP-01 | Inherit race_type on upcoming races from series history | P0 | #6 | Gap — 18 upcoming races have race_type=None |
| DP-02 | Populate race_type during precompute (not just scrape) | P1 | #6 | Gap — race_type only set at scrape time |
| DP-03 | Add prediction_source column to SeriesPrediction | P1 | OQ #4 | Gap — no provenance tracking |

### UI/UX Fixes (UX-01 -> UX-06)

| ID | Name | Priority | Issue | Status |
|----|------|----------|-------|--------|
| UX-01 | Deep-link to past-only series shows expanded preview | P0 | #9 | Gap — collapsed expander shows empty page |
| UX-02 | Search for past-only series shows preview summary | P1 | #10 | Gap — "Past Races (N)" collapsed with no context |
| UX-03 | Startlist label says "Likely contenders based on past editions" | P1 | #11 | Gap — label says "no startlist available" next to actual rider list |
| UX-04 | Remove Ontario from state filter | P2 | #12 | Gap — non-PNW state appears in filter |
| UX-05 | Guard register button on races without URL | P2 | #13 | Partially built — verify guard works |
| UX-06 | Improve elevation chart sizing relative to map | P2 | #14 | Gap — chart-to-map ratio inverted |

---

## Architecture

### Course-Based Predictor: Design Decision — Lookup Table over Decision Tree

The predictor uses a **two-tier lookup table** rather than a decision tree. Rationale:

1. **Testability**: A lookup table is a static mapping — every input/output pair is enumerable and can be exhaustively tested. A decision tree with continuous thresholds (m/km boundaries, distance cutoffs) creates an infinite input space that must be sampled.
2. **Transparency**: Domain experts (racers) can review the table row-by-row and spot errors. A nested decision tree is harder to audit.
3. **Calibration**: Each row carries its own confidence score. A decision tree tends to produce a single confidence calculation that doesn't account for the varying reliability of different rule paths.

The tradeoff is that the lookup table requires discretizing continuous variables (m_per_km, climb_count) into bins. This is acceptable because the bins map directly to existing `CourseType` classifications (flat/rolling/hilly/mountainous) which are already discretized in the `Course` table.

### Predictor Logic (Tier 1: race_type + course_type, Tier 2: course metrics)

```python
# classification/course_predictor.py

@dataclass
class CoursePrediction:
    finish_type: str        # FinishType enum value
    confidence: float       # 0.0 - 1.0
    source: str             # "course_profile" | "race_type_only"
    reasoning: str          # Human-readable explanation

# Tier 1: race_type alone (no course data needed)
RACE_TYPE_DEFAULTS: dict[str, tuple[str, float]] = {
    "criterium":   ("bunch_sprint", 0.70),
    "time_trial":  ("individual_tt", 0.95),
    "hill_climb":  ("gc_selective", 0.85),
}

# Tier 2: (course_type, race_type) -> (finish_type, confidence)
# race_type=None means "any non-TT/non-crit road race"
COURSE_RACE_TYPE_TABLE: dict[tuple[str, str | None], tuple[str, float]] = {
    # Flat courses
    ("flat", "criterium"):      ("bunch_sprint", 0.85),
    ("flat", "road_race"):      ("bunch_sprint", 0.65),
    ("flat", None):             ("bunch_sprint", 0.55),

    # Rolling courses
    ("rolling", "criterium"):   ("bunch_sprint", 0.60),
    ("rolling", "road_race"):   ("reduced_sprint", 0.50),
    ("rolling", None):          ("reduced_sprint", 0.45),

    # Hilly courses
    ("hilly", "criterium"):     ("reduced_sprint", 0.55),
    ("hilly", "road_race"):     ("breakaway", 0.55),
    ("hilly", None):            ("breakaway", 0.50),

    # Mountainous courses
    ("mountainous", "road_race"):     ("breakaway_selective", 0.65),
    ("mountainous", "hill_climb"):    ("gc_selective", 0.80),
    ("mountainous", None):            ("breakaway_selective", 0.60),
}

def predict_finish_type_from_course(
    course_type: str | None,
    race_type: str | None,
    m_per_km: float | None = None,
    total_gain_m: float | None = None,
    climb_count: int = 0,
    distance_m: float | None = None,
) -> CoursePrediction | None:
    """Pure function: predict finish type from course + race attributes.

    Priority:
    1. Tier 2 lookup: (course_type, race_type) if course data exists
    2. Tier 1 fallback: race_type alone for crits/TTs/hill climbs
    3. None if insufficient data

    Confidence adjustments:
    - +0.05 if m_per_km confirms course_type bin
    - +0.05 if climb_count >= 3 and course is hilly/mountainous
    - -0.10 if distance < 20km (short races are less predictable)
    - Cap at 0.75 (course predictions should never exceed time-gap confidence)
    """
```

### Confidence Calibration Strategy

Course-based predictions are inherently less reliable than time-gap analysis. The calibration follows these principles:

| Source | Confidence Range | Rationale |
|--------|-----------------|-----------|
| Time-gap classification | 0.50 - 0.95 | Based on observed finish data; strongest signal |
| Course + race_type (Tier 2) | 0.40 - 0.75 | Course profile strongly constrains outcome, but tactics vary |
| Race type alone (Tier 1) | 0.55 - 0.70 | Crits are reliably bunch sprints; road races vary widely |
| Race type alone, road_race | Not predicted | Road race without course data is too ambiguous |

The **0.75 ceiling** on course-based confidence means that when both sources exist, time-gap always wins (since its minimum confidence is 0.50 and it has real outcome data). The `predictions.py` `predict_series_finish_type` function already returns "unknown" for races without time data; the course predictor fills exactly this gap.

### Prediction Source Precedence

```
predict_series_finish_type() returns non-unknown?
  YES -> use it (source: "time_gap")
  NO  -> predict_finish_type_from_course() returns non-None?
    YES -> use it (source: "course_profile" or "race_type_only")
    NO  -> remain unknown (source: null)
```

This logic lives in `precompute.py`, not in the predictor itself. The predictor is a pure function; the pipeline decides precedence.

### Race Type Inheritance: Threshold Decision

For inheriting `race_type` from series history onto upcoming races:

```python
def infer_race_type_from_series(
    session: Session, series_id: int, threshold: float = 0.67
) -> RaceType | None:
    """Inherit race_type from historical editions.

    Returns the most common race_type if it appears in >= threshold
    of editions that have a race_type set. Returns None if:
    - No historical editions have race_type
    - No single type meets the threshold
    - Fewer than 2 historical editions exist (insufficient evidence)

    The 67% threshold (2/3 supermajority) balances:
    - Too low (50%): A series with 1 crit + 1 road race would inherit
    - Too high (90%): A series that changed format once would fail
    - 67%: Requires clear historical pattern (2/3, 3/4, 4/6, etc.)
    """
```

Edge cases to test:
- Series with 1 edition: returns None (below minimum evidence)
- Series with 2 editions, same type: returns that type (100% >= 67%)
- Series with 2 editions, different types: returns None (50% < 67%)
- Series with 3 editions, 2 same: returns majority type (67% >= 67%)
- Series with mixed types but all None: returns None
- Series that changed format (4 crits + 1 road race): returns criterium (80%)

### Data Flow Changes

```
precompute_series_predictions(session, series_id)
  1. predict_series_finish_type()            # existing: time-gap based
  2. IF result is "unknown":
       a. Load Course for series_id
       b. Load or infer race_type
       c. predict_finish_type_from_course()  # NEW: course-based
       d. Set prediction_source = "course_profile" or "race_type_only"
  3. ELSE:
       Set prediction_source = "time_gap"
  4. Upsert into SeriesPrediction (with new prediction_source column)
```

### Schema Change: prediction_source on SeriesPrediction

```python
# Add to SeriesPrediction model:
prediction_source = Column(String, nullable=True)
# Values: "time_gap", "course_profile", "race_type_only", None
```

This is a single nullable column addition. `Base.metadata.create_all()` handles it for new databases; existing databases need an `ALTER TABLE` or migration.

### Deep-Link Fix for Past-Only Series (UX-01)

Current behavior: `/?series_id=9` -> all races are past -> all land in collapsed "Past Races" expander -> user sees blank page.

Fix: When `isolated_series_id` is set AND the matched item is not upcoming, render it in the main body with `expanded=True` instead of inside the "Past Races" expander. This requires a small change in `feed.py` to detect and handle this case:

```python
# In feed.py render():
if isolated_series_id:
    # Force-expand and render outside the Past Races expander
    for item in items:
        _render_container_card(item, session, category, expanded=True)
    return  # Skip month-grouped rendering
```

---

## Implementation

### Phase 1: Course-Based Predictor Module (~30%)

**Goal**: Build and test `classification/course_predictor.py` as a standalone pure-function module. Zero database dependencies. Fully unit-testable.

**Tasks:**
- [ ] Create `raceanalyzer/classification/course_predictor.py` with `CoursePrediction` dataclass and `predict_finish_type_from_course()` function
- [ ] Implement Tier 1 lookup: `RACE_TYPE_DEFAULTS` for criterium, time_trial, hill_climb
- [ ] Implement Tier 2 lookup: `COURSE_RACE_TYPE_TABLE` mapping (course_type, race_type) pairs to (finish_type, confidence)
- [ ] Implement confidence adjustments: m_per_km confirmation, climb count bonus, short-race penalty, 0.75 ceiling
- [ ] Handle edge cases: None course_type, None race_type, partial data (course_type without m_per_km)
- [ ] Create `tests/test_course_predictor.py` with exhaustive coverage of the lookup table
- [ ] Test edge cases: all-None inputs, partial inputs, confidence adjustment boundaries
- [ ] Test that confidence never exceeds 0.75
- [ ] Test that road_race without course data returns None (too ambiguous)

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/classification/course_predictor.py` | Create | Pure-function course-based finish type predictor |
| `tests/test_course_predictor.py` | Create | Exhaustive unit tests for predictor rules and edge cases |

**Exit criteria:**
- `predict_finish_type_from_course("flat", "criterium")` returns `CoursePrediction(finish_type="bunch_sprint", confidence=0.85, source="course_profile", ...)`
- `predict_finish_type_from_course(None, "criterium")` returns `CoursePrediction(finish_type="bunch_sprint", confidence=0.70, source="race_type_only", ...)`
- `predict_finish_type_from_course(None, "road_race")` returns `None` (insufficient data)
- `predict_finish_type_from_course(None, None)` returns `None`
- All confidence values are in [0.40, 0.75]
- 100% of lookup table rows are covered by tests
- `pytest tests/test_course_predictor.py` passes with zero database fixtures

---

### Phase 2: Pipeline Integration & Prediction Source Tracking (~25%)

**Goal**: Wire the course predictor into the pre-computation pipeline. Add `prediction_source` column. Verify coverage improvement.

**Tasks:**
- [ ] Add `prediction_source` column (String, nullable) to `SeriesPrediction` model
- [ ] Create `infer_race_type_from_series()` in `raceanalyzer/queries.py` with 67% threshold
- [ ] Create `populate_upcoming_race_types()` in `raceanalyzer/precompute.py` to inherit race_type on upcoming races
- [ ] Modify `precompute_series_predictions()` in `precompute.py`:
  - After time-gap prediction, if result is "unknown", call course predictor
  - Load Course data for the series
  - Use inferred or existing race_type
  - Call `predict_finish_type_from_course()` with all available attributes
  - Store result with appropriate `prediction_source`
- [ ] Modify `precompute_all()` to call `populate_upcoming_race_types()` before series predictions
- [ ] Add `--populate-race-types` flag to `compute-predictions` CLI command
- [ ] Create `tests/test_race_type_inheritance.py` with threshold edge cases
- [ ] Update `tests/test_precompute.py` to verify course-based fallback triggers correctly
- [ ] Add integration test: create series with Course data but no time-gap classifications, run precompute, verify SeriesPrediction has non-unknown finish_type

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/db/models.py` | Modify | Add `prediction_source` column to SeriesPrediction |
| `raceanalyzer/precompute.py` | Modify | Course predictor fallback + race_type inheritance + populate_upcoming_race_types |
| `raceanalyzer/queries.py` | Modify | Add `infer_race_type_from_series()` |
| `raceanalyzer/cli.py` | Modify | Add `--populate-race-types` flag |
| `tests/test_precompute.py` | Modify | Course predictor integration tests |
| `tests/test_race_type_inheritance.py` | Create | Threshold edge case tests |

**Exit criteria:**
- Running `compute-predictions` on test DB with Course data populates `prediction_source` on every SeriesPrediction row
- Series with time-gap data: `prediction_source = "time_gap"`, finish_type unchanged
- Series with Course data but no time-gap data: `prediction_source = "course_profile"`, finish_type non-unknown
- Series with race_type=criterium but no Course: `prediction_source = "race_type_only"`, finish_type = "bunch_sprint"
- Series with neither: `prediction_source = None`, finish_type = "unknown"
- All 18 upcoming races have `race_type` populated after `--populate-race-types`
- `infer_race_type_from_series()` returns None for series with < 2 editions
- `infer_race_type_from_series()` returns None when no type reaches 67%
- Coverage target: finish_type=UNKNOWN drops from 45% to <20% of races

---

### Phase 3: Race Type Inheritance for Upcoming Races (~15%)

**Goal**: Ensure upcoming races have race_type so discipline/type filters work correctly. Verify filter behavior.

**Tasks:**
- [ ] Verify `populate_upcoming_race_types()` from Phase 2 works end-to-end against production DB shape
- [ ] Update feed filter logic: now that upcoming races have race_type, verify filtering to "Criterium only" correctly shows only upcoming crits (not all upcoming races)
- [ ] Add `normalize_state()` allowlist to exclude non-PNW states (fix Issue #12: Ontario)
- [ ] Test: after race_type population, filtering to Criterium shows only crit series in upcoming section
- [ ] Test: after race_type population, filtering to Road Race excludes criterium series
- [ ] Test: races whose series has mixed history and falls below threshold still pass through filters (unknown type = show, don't hide)

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/queries.py` | Modify | Add PNW state allowlist to `normalize_state()` or `get_available_states()` |
| `tests/test_queries.py` | Modify | Filter correctness tests with populated race_types |

**Exit criteria:**
- Ontario does not appear in state filter dropdown
- Filtering to "Criterium" shows criterium series (upcoming and past) plus unknown-type series
- Filtering to "Road Race" shows road race series plus unknown-type series
- No upcoming races are hidden by filters due to None race_type (pass-through preserved)

---

### Phase 4: UI/UX Audit Fixes (~30%)

**Goal**: Fix remaining UI issues from the audit. Each fix is independent and can be verified visually.

**Tasks:**

**UX-01: Deep-link to past-only series (Issue #9)**
- [ ] Modify `feed.py` render(): when `isolated_series_id` is set, skip month grouping and render matched item(s) directly with `expanded=True`
- [ ] Test: `/?series_id=9` (past-only series) shows fully expanded card with all Tier 2 content visible

**UX-02: Search for past-only series shows preview (Issue #10)**
- [ ] Modify `feed.py`: when search results are all past, render them in the main body (not inside collapsed "Past Races" expander)
- [ ] Optionally: show a summary line above the results: "Showing N past editions of 'Banana Belt'"
- [ ] Test: searching "Banana Belt" shows cards directly, not a collapsed expander

**UX-03: Startlist label (Issue #11)**
- [ ] Find the caption/label that says "Based on past editions (no startlist available)" in `race_preview.py` or `components.py`
- [ ] Change to "Likely contenders based on past editions" when showing historical fallback
- [ ] Test: Gorge Roubaix preview shows corrected label

**UX-04: Ontario in state filter (Issue #12)**
- [ ] Add PNW state allowlist: `{"WA", "OR", "ID", "BC", "AB", "MT"}` (plus normalized variants)
- [ ] Filter `get_available_states()` to only return states in allowlist (or exclude known non-PNW states)
- [ ] Test: state filter contains only PNW states

**UX-05: Register button guard (Issue #13)**
- [ ] Verify existing guard in `_render_container_card`: `if item.get("is_upcoming") and item.get("registration_url"):`
- [ ] Query DB: do any upcoming races have `registration_url = None`? If so, confirm button doesn't render for them
- [ ] Test: card with `registration_url=None` does not show Register button

**UX-06: Elevation chart sizing (Issue #14)**
- [ ] In the Plotly+Folium fallback renderer, swap the vertical allocation: elevation chart gets ~400px, map gets ~250px
- [ ] Or: use a 60/40 split in favor of the elevation chart
- [ ] Test: visual verification that elevation profile is the dominant visualization

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/ui/pages/feed.py` | Modify | Deep-link past-only fix (UX-01), search past-only fix (UX-02) |
| `raceanalyzer/ui/pages/race_preview.py` | Modify | Startlist label fix (UX-03) |
| `raceanalyzer/queries.py` | Modify | PNW state allowlist (UX-04) |
| `raceanalyzer/elevation.py` | Modify | Elevation chart sizing (UX-06) |
| `tests/test_feed.py` | Modify | Past-only deep-link and search tests |
| `tests/test_components.py` | Modify | Register button guard test |

**Exit criteria:**
- `/?series_id=9` shows a fully rendered card (not an empty page)
- Searching "Banana Belt" shows visible cards with content
- Startlist fallback label reads "Likely contenders based on past editions"
- State filter does not contain "Ontario"
- Register button does not render when `registration_url` is None
- Elevation chart is visually larger than the course map

---

## Files Summary

| File | Action | Phase | Purpose |
|------|--------|-------|---------|
| `raceanalyzer/classification/course_predictor.py` | Create | 1 | Pure-function course-based finish type predictor |
| `raceanalyzer/db/models.py` | Modify | 2 | Add `prediction_source` to SeriesPrediction |
| `raceanalyzer/precompute.py` | Modify | 2 | Course predictor fallback, race_type inheritance |
| `raceanalyzer/queries.py` | Modify | 2, 3, 4 | `infer_race_type_from_series()`, PNW allowlist |
| `raceanalyzer/cli.py` | Modify | 2 | `--populate-race-types` flag |
| `raceanalyzer/predictions.py` | No change | — | Course predictor fills gap that predictions.py couldn't |
| `raceanalyzer/ui/pages/feed.py` | Modify | 4 | Deep-link and search fixes for past-only series |
| `raceanalyzer/ui/pages/race_preview.py` | Modify | 4 | Startlist label fix |
| `raceanalyzer/ui/components.py` | No change | — | Existing guards sufficient for register button |
| `raceanalyzer/elevation.py` | Modify | 4 | Chart sizing adjustment |
| `tests/test_course_predictor.py` | Create | 1 | Exhaustive predictor unit tests |
| `tests/test_race_type_inheritance.py` | Create | 2 | Threshold edge case tests |
| `tests/test_precompute.py` | Modify | 2 | Course predictor integration |
| `tests/test_queries.py` | Modify | 3 | Filter correctness with populated race_types |
| `tests/test_feed.py` | Modify | 4 | Past-only deep-link and search behavior |
| `tests/test_components.py` | Modify | 4 | Register button guard |

---

## Definition of Done

### Course-Based Prediction (CP)
- [ ] `classification/course_predictor.py` exists with pure-function predictor
- [ ] Every (course_type, race_type) pair in the lookup table has a unit test
- [ ] Predictor returns None for insufficient data (no false predictions)
- [ ] Confidence never exceeds 0.75 (verified by test)
- [ ] Time-gap predictions always take precedence over course predictions (verified by precompute test)
- [ ] `prediction_source` column populated on every SeriesPrediction row after `compute-predictions`

### Data Pipeline (DP)
- [ ] `infer_race_type_from_series()` uses 67% threshold with minimum 2 editions
- [ ] All 18 upcoming races have `race_type` populated after running `compute-predictions --populate-race-types`
- [ ] `precompute_series_predictions()` calls course predictor as fallback for unknown finish types
- [ ] Finish type coverage increases from 55% to 80%+ of races with non-UNKNOWN prediction

### UI/UX (UX)
- [ ] `/?series_id=N` for past-only series shows expanded card content (not blank page)
- [ ] Search for past-only series shows cards in main body (not collapsed expander)
- [ ] Startlist fallback label reads "Likely contenders based on past editions"
- [ ] Ontario not in state filter
- [ ] Register button does not appear for races with no registration URL
- [ ] Elevation chart is visually larger than course map in Plotly+Folium fallback

### Quality
- [ ] `ruff check .` passes
- [ ] `pytest` passes with no regressions
- [ ] New test files: `test_course_predictor.py`, `test_race_type_inheritance.py`
- [ ] Modified test files: `test_precompute.py`, `test_queries.py`, `test_feed.py`, `test_components.py`
- [ ] Feed load time remains <1s cold / <200ms warm (no new SQL queries in feed path)
- [ ] Batch query count remains <=6 (course predictor runs at precompute time, not render time)

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Course predictor accuracy** — heuristic rules may miscategorize some races (e.g., a flat crit that historically produces breakaways due to wind or course features) | Medium | Medium | Cap confidence at 0.75. Add `prediction_source` so UI can show softer language ("Course suggests...") vs. time-gap certainty ("Historically ends in..."). Expand lookup table based on feedback. |
| **m_per_km threshold boundaries** — rolling vs hilly vs mountainous cutoffs may not match real-world course profiles in the PNW | Medium | Low | The predictor uses the already-classified `course_type` from the Course table rather than re-deriving it. If course_type is wrong, that's an upstream issue. Confidence adjustments buffer boundary cases. |
| **Race type inheritance threshold too aggressive** — 67% might inherit incorrectly for series that changed format | Low | Medium | Minimum 2-edition requirement prevents single-edition inheritance. 67% requires clear majority. Add test case for format-change scenario. If concerned, can bump to 75% with minimal coverage loss. |
| **Race type inheritance threshold too conservative** — many series might have only 1 edition, leaving upcoming race_type=None | Medium | Low | Falls back to `infer_race_type()` name-based matching (already exists in queries.py). Series with 1 edition still get race_type from name keywords. |
| **Schema migration for prediction_source** — existing databases need ALTER TABLE | Low | Low | Column is nullable with no default constraint. `ALTER TABLE series_predictions ADD COLUMN prediction_source VARCHAR` is safe. Document in CLI output. |
| **Past-only deep-link fix breaks pagination** — rendering past items outside the expander changes the rendered count | Low | Low | The isolated_series_id path already bypasses month grouping. The fix makes this path render expanded instead of collapsed. No interaction with pagination. |
| **Overconfident race_type_only predictions** — predicting "bunch_sprint" for all criteriums ignores edge cases (uphill crits, technical crits) | Medium | Low | Confidence for race_type_only is 0.55-0.70, well below time-gap range. The prediction is a reasonable default that's better than "unknown" for the user. |

---

## Security Considerations

- **No new user inputs**: The course predictor operates entirely on internal database fields. No user-provided strings are interpolated into SQL or HTML.
- **prediction_source column**: Contains only enumerated string values ("time_gap", "course_profile", "race_type_only"). Not user-controlled.
- **PNW state allowlist**: Implemented as a hardcoded set, not a database query. No injection vector.
- **Existing guards preserved**: Register button guard, HTML escaping in `unsafe_allow_html` components, parameterized SQLAlchemy queries — all unchanged.

---

## Dependencies

- **No new Python dependencies**
- **Sprint 011**: Depends on `SeriesPrediction` table, `precompute.py` pipeline, `get_feed_items_batch()`, container cards, `PerfTimer`
- **Sprint 008**: Depends on `Course` table with `course_type`, `total_gain_m`, `distance_m`, `m_per_km`, `climbs_json`
- **Sprint 009**: Depends on `Startlist` data for startlist label fix (UX-03)
- **Sprint 010**: Depends on deep-link and URL state persistence for UX-01

---

## Open Questions

1. **Should the course predictor attempt mountainous + criterium?** This combination is rare (uphill crits exist but are unusual). Current table omits it. Recommendation: omit for now; if encountered, falls through to race_type_only prediction ("bunch_sprint" at 0.70). Add to table if data shows it matters.

2. **Should `prediction_source` be exposed in the UI?** Options: (a) show nothing, (b) show a small badge like "Based on course profile" vs "Based on historical results", (c) use different language confidence ("Course suggests a bunch sprint" vs "Historically ends in a bunch sprint"). Recommendation: option (c) — modify `finish_type_plain_english()` to accept source and adjust phrasing. Defer to Phase 4 or Sprint 013 if scope is tight.

3. **Should we backfill race_type on historical races too?** `infer_race_type()` (name-based) already exists but isn't called for all historical races. Running it as a one-time migration would improve filter accuracy for past races. Recommendation: yes, add to `populate_upcoming_race_types()` as an optional `--backfill-historical` flag. Low risk since it's using existing logic.

4. **How to handle series with Course data but ambiguous course_type?** If `course_type = "unknown"` but `m_per_km` is available, should the predictor reclassify? Recommendation: no — respect the existing classification. If `course_type` is unknown, fall through to race_type_only. Fixing course_type classification is a separate concern.

5. **Should the 67% race_type inheritance threshold be configurable?** Could put it in `Settings` for tuning. Recommendation: hardcode initially. If racers report mis-inherited types, make it configurable in a follow-up.

6. **What about series with zero Course data AND no clear race_type from name?** These will remain unknown. The audit found ~45% unknown; the goal is 80%+ coverage. Series with neither signal are the residual 20% — acceptable for Sprint 012. Future sprints could add manual overrides or additional data sources.
