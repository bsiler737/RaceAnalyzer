# Sprint 012: UX Audit Fix — Course-Based Prediction & Data Quality Cascade

## Overview

Sprint 012 addresses the single most impactful quality gap in RaceAnalyzer: **45% of races produce no actionable prediction for the user**. The UX audit (docs/UX_AUDIT_FINDINGS.md) tested 10 beginner-racer journeys and found 13 remaining issues, but the root cause analysis reveals these are not 13 independent problems — they are a **data quality cascade**. When `finish_type` is UNKNOWN, the card loses its finish description (Issue #17), the "Who does well here?" section vanishes (Issue #16), similar-race matching fails (Issue #15), and the narrative becomes skeletal (Issue #5). Fixing the prediction gap at the source fixes four issues simultaneously and transforms card density from "some cards are rich, others are empty" into a consistently useful experience across the feed.

The approach is deliberately conservative about confidence. We introduce a **course-based finish type predictor** as a fallback when time-gap classification is impossible, but we treat its outputs as lower-fidelity than time-gap results. A new `prediction_source` field on `SeriesPrediction` makes this distinction explicit in the data model, the UI, and the narrative language. Course-based predictions use hedged phrasing ("Course profile suggests...") rather than the definitive language of time-gap predictions ("Historically ends in..."). This honesty about uncertainty is itself a UX improvement — a beginner racer trusts a system that tells them what it knows and what it is guessing.

Beyond prediction, the sprint fixes the **past-only series deep-link problem** holistically. A shared link to `/?series_id=9` (Gorge Roubaix) currently shows an empty page — the collapsed expander pattern that works for browsing is hostile to sharing. The fix reframes past-only series as a "race profile" view: expanded card with course data, historical summary, racer type, and similar races. This turns a dead-end into a discovery moment. The remaining UI issues (startlist label, Ontario in state filter, register button guard, elevation chart sizing) are quick fixes that round out the polish pass.

---

## Use Cases

### Course-Based Prediction (CP-01 -> CP-06)

| ID | Name | Priority | Audit Issues | Affected Journeys |
|----|------|----------|--------------|-------------------|
| CP-01 | Course-based finish type predictor | P0 | #5 | 2, 5 |
| CP-02 | prediction_source field on SeriesPrediction | P0 | #5, #17 | 1, 2, 5, 7, 10 |
| CP-03 | Course-predicted finish types populate similarity scoring | P1 | #15 | 6 |
| CP-04 | Course-predicted finish types populate racer type description | P1 | #16 | 5 |
| CP-05 | Course-predicted finish types populate card finish description | P1 | #17 | 1, 7, 10 |
| CP-06 | Race-type-only predictor for series without course data | P2 | #5 | 2, 5 |

### Data Pipeline (DP-01 -> DP-03)

| ID | Name | Priority | Audit Issues | Affected Journeys |
|----|------|----------|--------------|-------------------|
| DP-01 | Inherit race_type on upcoming races from series history | P0 | #6 | 4 |
| DP-02 | Backfill race_type using name-based inference for all races | P1 | #6 | 4 |
| DP-03 | Drop rate caveat for single-edition series | P2 | #8 | 2, 5 |

### Past-Only Series UX (PS-01 -> PS-03)

| ID | Name | Priority | Audit Issues | Affected Journeys |
|----|------|----------|--------------|-------------------|
| PS-01 | Deep-link to past-only series shows expanded race profile | P0 | #9 | 6, 10 |
| PS-02 | Search results for past-only series show preview summary | P1 | #10 | 5 |
| PS-03 | Past-only series profile includes course, racer type, similar races | P1 | #9, #15, #16 | 5, 6 |

### UI Polish (UP-01 -> UP-05)

| ID | Name | Priority | Audit Issues | Affected Journeys |
|----|------|----------|--------------|-------------------|
| UP-01 | Startlist label: "Likely contenders based on past editions" | P0 | #11 | 3 |
| UP-02 | Exclude non-PNW states from filter | P1 | #12 | 4 |
| UP-03 | Guard register button on null registration_url | P1 | #13 | 1, 10 |
| UP-04 | Increase elevation chart height relative to map | P2 | #14 | 9 |
| UP-05 | Visual distinction for course-based vs time-gap predictions | P1 | #17 | 1, 7, 10 |

---

## Architecture

### Data Quality Cascade: How One Fix Propagates

The core insight driving this sprint is that `predicted_finish_type` is a **load-bearing column**. When it is `"unknown"`, five downstream systems produce degraded output:

```
predicted_finish_type = "unknown"
    |
    +-> Card finish description: HIDDEN (Issue #17)
    |     feed.py: finish_type_plain_english() returns None
    |
    +-> racer_type_description(): returns None (Issue #16)
    |     predictions.py line 710: if not finish_type: return None
    |
    +-> racer_type_long_form(): returns None (Issue #16)
    |     predictions.py line 725: calls racer_type_description()
    |
    +-> compute_similarity(): loses 30 points from scoring (Issue #15)
    |     queries.py line 1584: predicted_finish_type match = +30
    |
    +-> generate_narrative(): skips history sentence (Issue #5)
          predictions.py line 635: if predicted_finish_type and edition_count > 0
```

By populating `predicted_finish_type` via course-based inference for the 630 races that lack time-gap data, we cascade improvements through all five systems without modifying their logic. The only new downstream change is adding `prediction_source` awareness to the narrative template so it uses appropriately hedged language.

### Course-Based Predictor: Decision Matrix

The predictor uses a two-dimensional decision matrix keyed on `(course_character, race_type)`. Course character is derived from `m_per_km` (meters of climbing per kilometer of distance), which is already stored on the `Course` table.

**m/km Thresholds:**

| m/km Range | Course Character | Rationale |
|------------|------------------|-----------|
| 0 - 5 | Flat | Under 5 m/km is essentially flat; packs stay together on road races. For crits, use 0-3 threshold instead (short laps amplify even small elevation). |
| 5 - 10 | Rolling | Enough climbing to create surges but not sustained selection. For crits, 3-7 m/km. |
| 10 - 18 | Hilly | Significant climbing; repeated efforts thin the field. For crits, 7-12 m/km. |
| 18+ | Mountainous | Major mountain passes; pure climber territory. For crits, 12+ m/km. |

The race-type-specific adjustment for criteriums recognizes that a 5 m/km crit (short repeated laps) is experientially different from a 5 m/km road race (one long effort). The `_resolve_course_character()` function applies a configurable offset:

```python
# In classification/course_predictor.py

# m/km thresholds for course character classification
_DEFAULT_THRESHOLDS = (5.0, 10.0, 18.0)  # flat/rolling, rolling/hilly, hilly/mountainous
_CRIT_OFFSET = -2.0  # shift thresholds down for crits (short laps amplify climbing)

def _resolve_course_character(
    course_type: str | None,
    m_per_km: float | None,
    race_type: str | None = None,
) -> str | None:
    """Derive course character from stored course_type or raw m_per_km."""
    # Prefer stored course_type if available
    if course_type and course_type != "unknown":
        return course_type

    if m_per_km is None:
        return None

    t1, t2, t3 = _DEFAULT_THRESHOLDS
    if race_type == "criterium":
        t1 += _CRIT_OFFSET
        t2 += _CRIT_OFFSET
        t3 += _CRIT_OFFSET

    if m_per_km < t1:
        return "flat"
    elif m_per_km < t2:
        return "rolling"
    elif m_per_km < t3:
        return "hilly"
    else:
        return "mountainous"
```

These thresholds align with the existing `CourseType` classification in `elevation.py` and the `m_per_km` column on `Course`.

**Decision Matrix (course_character x race_type -> predicted_finish_type, confidence):**

| | Criterium | Road Race | Hill Climb | Gravel | Stage Race | Unknown Type |
|---|-----------|-----------|------------|--------|------------|--------------|
| **Flat** | bunch_sprint (0.80) | bunch_sprint (0.60) | individual_tt (0.70) | reduced_sprint (0.55) | mixed (0.50) | bunch_sprint (0.50) |
| **Rolling** | bunch_sprint (0.65) | reduced_sprint (0.55) | breakaway_selective (0.60) | reduced_sprint (0.55) | mixed (0.50) | reduced_sprint (0.45) |
| **Hilly** | reduced_sprint (0.55) | breakaway_selective (0.60) | gc_selective (0.70) | breakaway_selective (0.55) | gc_selective (0.60) | breakaway_selective (0.50) |
| **Mountainous** | breakaway_selective (0.55) | gc_selective (0.65) | gc_selective (0.75) | gc_selective (0.55) | gc_selective (0.65) | gc_selective (0.55) |

Confidence scores are deliberately capped: no course-based prediction exceeds 0.80. Time-gap predictions range 0.65-0.95. This ensures time-gap results always win when both are available.

**Refinement signals (adjust confidence +/- 0.05):**

- Climb count >= 3 AND any climb > 8% avg grade -> +0.05 toward selective types
- Distance < 5 km AND not TT -> likely crit lap distance, leave confidence as-is (already handled by race_type)
- Single significant climb in final 25% of course -> +0.05 toward breakaway_selective
- Total gain > 1500m -> +0.05 toward gc_selective regardless of m/km

```python
# classification/course_predictor.py

@dataclass
class CoursePrediction:
    finish_type: FinishType
    confidence: float
    source: str  # "course_profile" or "race_type_only"
    reasoning: str  # Human-readable explanation for debugging/narrative

def predict_from_course(
    course_type: str | None,
    m_per_km: float | None,
    race_type: str | None,
    distance_m: float | None = None,
    total_gain_m: float | None = None,
    climbs: list[dict] | None = None,
) -> CoursePrediction | None:
    """Predict finish type from course characteristics.

    Returns None if insufficient data (no course_type AND no race_type).
    """
    character = _resolve_course_character(course_type, m_per_km, race_type)
    if character is None and race_type is None:
        return None

    # Lookup in decision matrix
    ft, conf = _DECISION_MATRIX.get(
        (character or "rolling", race_type or "road_race"),
        (FinishType.MIXED, 0.45),
    )

    # Apply refinement signals
    conf = _apply_refinements(
        ft, conf, character, race_type,
        distance_m, total_gain_m, climbs,
    )

    source = "course_profile" if character else "race_type_only"
    reasoning = _build_reasoning(character, race_type, ft)

    return CoursePrediction(
        finish_type=ft, confidence=round(conf, 2),
        source=source, reasoning=reasoning,
    )
```

### prediction_source Field: Schema Change

Add a `prediction_source` column to `SeriesPrediction` to distinguish how the finish type was determined:

```python
# In db/models.py, add to SeriesPrediction:
prediction_source = Column(String, nullable=True)
# Values: "time_gap", "course_profile", "race_type_only", None
```

This is a non-breaking additive column (nullable, no unique constraint). Existing rows will have `prediction_source = None` until the next `compute-predictions` run, at which point the precompute pipeline sets the source.

**Precompute priority logic:**

```python
# In precompute.py, updated precompute_series_predictions:
def _resolve_prediction(session, series_id, category, course):
    """Resolve finish type prediction with source priority.

    Priority order:
    1. Time-gap (highest fidelity, empirical data)
    2. Course profile (terrain + race type heuristic)
    3. Race type only (lowest fidelity)
    """
    # 1. Try time-gap prediction (highest fidelity)
    time_gap = predict_series_finish_type(session, series_id, category)
    if time_gap["predicted_finish_type"] != "unknown":
        return {
            **time_gap,
            "prediction_source": "time_gap",
        }

    # 2. Try course-based prediction
    if course:
        from raceanalyzer.classification.course_predictor import predict_from_course
        course_pred = predict_from_course(
            course_type=(
                course.course_type.value if course.course_type else None
            ),
            m_per_km=course.m_per_km,
            race_type=_get_series_race_type(session, series_id),
            distance_m=course.distance_m,
            total_gain_m=course.total_gain_m,
            climbs=(
                json.loads(course.climbs_json) if course.climbs_json else None
            ),
        )
        if course_pred:
            return {
                "predicted_finish_type": course_pred.finish_type.value,
                "confidence": _confidence_label(course_pred.confidence),
                "edition_count": time_gap["edition_count"],
                "distribution": time_gap["distribution"],
                "prediction_source": course_pred.source,
            }

    # 3. Try race-type-only fallback
    rt = _get_series_race_type(session, series_id)
    if rt:
        from raceanalyzer.classification.course_predictor import predict_from_course
        rt_pred = predict_from_course(
            course_type=None, m_per_km=None, race_type=rt,
        )
        if rt_pred:
            return {
                "predicted_finish_type": rt_pred.finish_type.value,
                "confidence": _confidence_label(rt_pred.confidence),
                "edition_count": time_gap["edition_count"],
                "distribution": time_gap["distribution"],
                "prediction_source": "race_type_only",
            }

    # 4. Fall through to unknown
    return {**time_gap, "prediction_source": None}


def _confidence_label(numeric_conf: float) -> str:
    """Convert numeric confidence (0-1) to label."""
    if numeric_conf >= 0.7:
        return "moderate"  # Course-based caps below "high"
    elif numeric_conf >= 0.5:
        return "low"
    return "low"
```

### Past-Only Series: Deep-Link Experience Redesign

The current flow for `/?series_id=9` (a past-only series):

```
feed.py render()
  -> items = [item for item in all_items if series_id == 9]
  -> group_by_month(items) -> [("Past Races", [item])]
  -> renders collapsed st.expander("Past Races (1)")
  -> user sees: empty page with collapsed section
```

The redesigned flow:

```
feed.py render()
  -> items = [item for item in all_items if series_id == 9]
  -> if isolated_series_id AND all items are past-only:
      -> render_series_profile(item, session, category)
      -> shows: expanded card + course data + racer type + similar races
  -> else:
      -> normal month-grouped rendering
```

`render_series_profile` is a new component that treats the series as a discoverable entity, not just a container for upcoming races. It shows:

1. Full card header with "last raced {date}" context
2. Course profile hero (if course data exists)
3. What to Expect narrative
4. Who Does Well Here racer type description
5. Similar Races cross-references (deep links to other series)
6. Historical editions with finish type icons
7. "Show all races" button to return to the full feed

This reframing means a shared link like `raceanalyzer.app/?series_id=9` becomes useful rather than hostile — the recipient sees a rich profile of the race even though it has no upcoming edition.

For **search results** (PS-02), when a search returns only past-only items (e.g., searching "Banana Belt"), we render the top 3 matches as expanded summary cards above the collapsed "Past Races" section. Each summary shows: display name, location, course character, finish type, and edition count. This provides immediate utility without requiring the user to expand the section.

### UX Treatment for Course-Based Predictions

Course-based predictions should be **visually identical in structure** but **textually distinguished** to maintain user trust:

| Source | Card Text | Narrative Phrasing | Badge Style |
|--------|-----------|--------------------|----|
| `time_gap` | "The whole pack stayed together and sprinted for the line" | "Based on 4 previous editions, this race typically ends in a bunch sprint." | Solid color badge |
| `course_profile` | "Course profile suggests a bunch sprint finish" | "The flat, short course profile suggests this race likely ends in a bunch sprint." | Solid color badge with italic qualifier |
| `race_type_only` | "Criteriums typically end in a bunch sprint" | "As a criterium, this race typically ends in a bunch sprint — course data would help confirm." | Lighter/desaturated badge |

The visual weight is the same across all three sources. We do not want course-based predictions to feel "second class" — they should feel helpful but honest. The distinction is in the language, not the layout.

```python
# In queries.py, new function:

def finish_type_plain_english_with_source(
    finish_type: str,
    prediction_source: str | None = None,
    course_type: str | None = None,
    race_type: str | None = None,
) -> str | None:
    """Return plain English finish description with source-appropriate framing."""
    base = finish_type_plain_english(finish_type)
    if not base:
        return None

    if prediction_source == "course_profile":
        terrain = course_type or "this"
        return f"Course profile suggests: {base.lower()}"
    elif prediction_source == "race_type_only":
        rt_display = race_type_display_name(race_type) if race_type else "This race type"
        return f"{rt_display}s typically end this way: {base.lower()}"
    else:
        # time_gap or None — use the definitive phrasing
        return base
```

### Similarity Scoring: Cascade Improvement

`compute_similarity()` currently awards 30 points for matching `predicted_finish_type`. With 45% of races having `finish_type=unknown`, most pairs cannot access the full 100-point scoring range. The `min_score=50` threshold means many valid similar-race pairs are found, but quality is lower because finish type — the most semantically meaningful signal — is missing from nearly half the dataset.

After this sprint, course-based predictions populate `predicted_finish_type` for most series with course data, enabling the full scoring range. **No changes to `compute_similarity()` itself are needed** — the improvement comes from better input data. This is the cascade at work.

One consideration: should we weight course-based predictions lower in similarity? No. From the user's perspective, "these two courses are both flat criteriums that both end in bunch sprints" is equally useful whether the prediction came from time-gap analysis or course inference. The similarity score reflects user utility, not data provenance.

---

## Implementation

### Phase 1: Course-Based Predictor & prediction_source (CP-01, CP-02, CP-06, ~40%)

**Goal**: Build the course-based finish type predictor, add `prediction_source` to `SeriesPrediction`, integrate into the precompute pipeline, and verify coverage improves from 55% to 80%+.

**Tasks:**
- [ ] Create `raceanalyzer/classification/course_predictor.py` with `CoursePrediction` dataclass, `predict_from_course()`, `_resolve_course_character()`, `_DECISION_MATRIX`, `_apply_refinements()`, `_build_reasoning()`
- [ ] Add `prediction_source` column to `SeriesPrediction` in `raceanalyzer/db/models.py`
- [ ] Update `raceanalyzer/precompute.py`: add `_resolve_prediction()` that tries time-gap first, then course-based, then race-type-only; set `prediction_source` on each row
- [ ] Add `_get_series_race_type()` helper to `precompute.py`: returns the most common `race_type` from historical editions (requires > 50% agreement), or None
- [ ] Add `_confidence_label()` to `precompute.py`: converts numeric confidence (0-1) to "high"/"moderate"/"low" label with course-based predictions capped at "moderate"
- [ ] Update `raceanalyzer/predictions.py` `generate_narrative()` to accept `prediction_source` kwarg; when source is "course_profile" or "race_type_only", use hedged phrasing: "The course profile suggests this race ends in..." instead of "Based on N previous editions, this race typically ends in..."
- [ ] Run `compute-predictions` CLI and verify coverage change with: `SELECT COUNT(*) FROM series_predictions WHERE predicted_finish_type != 'unknown'`
- [ ] Create `tests/test_course_predictor.py` with `TestCourseBasedPrediction` class covering:
  - Each of the 24 cells of the decision matrix (4 terrains x 6 race types)
  - Refinement signal adjustments (climb count, final-quarter climb, high total gain)
  - Edge cases: no course data + no race_type returns None; crit m/km threshold offset; m_per_km = None with valid course_type
- [ ] Update `tests/test_precompute.py`: verify pipeline prefers time-gap over course-based, sets `prediction_source` correctly, handles missing Course gracefully

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/classification/course_predictor.py` | Create | Decision matrix predictor, CoursePrediction dataclass, threshold config |
| `raceanalyzer/db/models.py` | Modify | Add `prediction_source` to `SeriesPrediction` |
| `raceanalyzer/precompute.py` | Modify | `_resolve_prediction`, `_get_series_race_type`, `_confidence_label`, integrate course predictor |
| `raceanalyzer/predictions.py` | Modify | Hedged narrative language for course-based predictions |
| `tests/test_course_predictor.py` | Create | Decision matrix tests, refinement tests, edge cases |
| `tests/test_precompute.py` | Modify | prediction_source tests, priority logic |

**Exit criteria:**
- `predict_from_course()` returns correct predictions for all 24 cells of the decision matrix (verified by unit tests)
- `precompute_series_predictions()` sets `prediction_source` to "time_gap", "course_profile", or "race_type_only" on every non-unknown row
- Time-gap predictions are never overwritten by course-based predictions
- Coverage of non-UNKNOWN `predicted_finish_type` increases from 55% to 80%+ (verified by DB query after `compute-predictions` run)
- Course-based prediction confidence never exceeds 0.80; confidence label never exceeds "moderate" for course-based
- Narrative uses hedged language when `prediction_source` is "course_profile" or "race_type_only"

---

### Phase 2: Data Pipeline Fixes (DP-01, DP-02, DP-03, UP-02, ~15%)

**Goal**: Populate `race_type` on upcoming races, backfill missing race types, add drop rate caveats for single-edition data, and clean state filter.

**Tasks:**
- [ ] Add `inherit_race_type_from_series()` to `raceanalyzer/precompute.py`: for each upcoming `Race` with `race_type=None`, query historical editions in the same series and set `race_type` to the most common non-None value (require >= 80% agreement among editions with a known type)
- [ ] Add `backfill_race_types()` to `raceanalyzer/precompute.py`: for historical races with `race_type=None`, apply `infer_race_type(race.name)` from queries.py
- [ ] Integrate both into `precompute_all()` as a pre-step before prediction computation, so predictions benefit from backfilled types
- [ ] Add `--backfill-types` flag to `compute-predictions` CLI command in `raceanalyzer/cli.py`
- [ ] Update `generate_narrative()`: when `edition_count == 1` AND `drop_rate` is present AND `drop_rate["drop_rate"] < 0.05`, append "Based on a single edition — attrition may vary."
- [ ] Add `PNW_STATES` constant to `raceanalyzer/queries.py`: `{"WA", "OR", "ID", "BC", "MT"}` (include Montana as border state)
- [ ] Update `get_available_states()` in `raceanalyzer/queries.py` to filter results against `PNW_STATES` — non-PNW values like "Ontario" are excluded from the UI filter
- [ ] Tests: race_type inheritance (>= 80% threshold, mixed types, no history), backfill from name patterns, PNW state filtering

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/precompute.py` | Modify | `inherit_race_type_from_series`, `backfill_race_types`, integrate into `precompute_all` |
| `raceanalyzer/predictions.py` | Modify | Single-edition drop rate caveat in narrative |
| `raceanalyzer/queries.py` | Modify | Add `PNW_STATES`, filter non-PNW in `get_available_states()` |
| `raceanalyzer/cli.py` | Modify | `--backfill-types` flag on `compute-predictions` |
| `tests/test_precompute.py` | Modify | Race type inheritance and backfill tests |
| `tests/test_queries.py` | Modify | PNW state filtering tests |

**Exit criteria:**
- All 18 upcoming races have a non-None `race_type` after running `compute-predictions --backfill-types`
- Race type inheritance requires >= 80% historical agreement (not simple majority) to prevent incorrect propagation
- `get_available_states()` no longer returns "Ontario" or other non-PNW values
- Single-edition series with implausible 0% drop rate show appropriate caveat in narrative
- Backfill runs as part of `precompute_all()` so predictions benefit from newly assigned types

---

### Phase 3: Past-Only Series UX (PS-01, PS-02, PS-03, ~20%)

**Goal**: Transform deep-links and search results for past-only series from empty dead-ends into rich race profiles.

**Tasks:**
- [ ] Add `render_series_profile()` to `raceanalyzer/ui/components.py`: renders an expanded container card showing:
  - Header: display name, location, "last raced {date}"
  - Course profile hero (via existing `render_interactive_course_profile` if course data exists)
  - Narrative (via `get_feed_item_detail()` Tier 2 data)
  - Racer type description (via `racer_type_long_form()`)
  - Similar races (via `get_similar_series()`)
  - Historical editions with finish type icons (via `render_finish_pattern()`)
- [ ] Modify `raceanalyzer/ui/pages/feed.py` deep-link handling: when `isolated_series_id` is set and the matched item is past-only (`not item["is_upcoming"]`), call `render_series_profile()` instead of passing through to `group_by_month()` which collapses it
- [ ] Modify `raceanalyzer/ui/pages/feed.py` search handling: when search returns only past items, render up to 3 items as expanded summary cards (display_name, location, course character, finish type, edition count) above the collapsed "Past Races" expander
- [ ] Ensure `render_series_profile` gracefully degrades: missing course -> skip profile hero; missing predictions -> skip racer type; missing similar -> show "No similar races found"
- [ ] Tests: deep-link to past-only series renders profile (mock test verifying `render_series_profile` is called), search for past-only term surfaces preview summaries

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/ui/pages/feed.py` | Modify | Past-only series detection, series profile rendering, search preview summaries |
| `raceanalyzer/ui/components.py` | Modify | Add `render_series_profile` component |
| `tests/test_feed.py` | Modify | Deep-link and search behavior tests |

**Exit criteria:**
- `/?series_id=9` (Gorge Roubaix) shows an expanded race profile with course data, narrative, and similar races — not a collapsed expander
- Searching "Banana Belt" shows a preview summary of the series above the collapsed "Past Races" section
- "Show all races" button remains available to return to the full feed
- Past-only series profile gracefully degrades when course data or predictions are missing (no errors, just omitted sections)

---

### Phase 4: UI Polish & Card Consistency (UP-01 -> UP-05, CP-03 -> CP-05, ~25%)

**Goal**: Fix remaining UI issues, add visual distinction for prediction sources, wire course-based predictions into card rendering and downstream features.

**Tasks:**
- [ ] Fix startlist label (UP-01): in `raceanalyzer/ui/pages/race_preview.py`, change "Based on past editions (no startlist available)" to "Likely contenders based on past editions"
- [ ] Guard register button (UP-03): audit `_render_container_card` in `feed.py` — the existing check `item.get("is_upcoming") and item.get("registration_url")` appears correct; verify by inspecting all 18 upcoming races' `registration_url` values in the DB; add `and item["registration_url"]` explicit truthiness check to catch empty strings
- [ ] Increase elevation chart height (UP-04): in the Plotly+Folium fallback renderer (likely in `raceanalyzer/elevation.py` or `race_preview.py`), change elevation chart from 250px to 400px and map from 400px to 300px
- [ ] Add `finish_type_plain_english_with_source()` to `raceanalyzer/queries.py` that generates source-appropriate text
- [ ] Wire `prediction_source` into `get_feed_items_batch()` output — add to the Tier 1 dict so cards can use it
- [ ] Update `_render_container_card()` in `feed.py` to call `finish_type_plain_english_with_source()` instead of `finish_type_plain_english()`, passing `prediction_source`, `course_type`, and `race_type` from the item dict
- [ ] Verify similar races (CP-03) and racer type (CP-04) automatically benefit from new predictions — write integration-style tests that create a series with course data but no time-gap data and confirm `get_similar_series()` returns matches and `racer_type_description()` returns a description
- [ ] Tests: card rendering with different `prediction_source` values, register button null/empty safety, startlist label text, plain English with source formatting

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/ui/pages/race_preview.py` | Modify | Startlist label fix, elevation chart sizing |
| `raceanalyzer/ui/pages/feed.py` | Modify | prediction_source in card rendering, source-aware plain English |
| `raceanalyzer/ui/components.py` | Modify | Visual distinction for prediction sources (optional desaturated badge for race_type_only) |
| `raceanalyzer/queries.py` | Modify | `finish_type_plain_english_with_source()`, prediction_source in batch output |
| `tests/test_components.py` | Modify | Prediction source rendering tests |
| `tests/test_queries.py` | Modify | Plain English with source tests, integration tests for cascade |

**Exit criteria:**
- Startlist header reads "Likely contenders based on past editions" when showing historical fallback
- Register button does not render when `registration_url` is null or empty string
- Elevation chart is taller than the map in the Plotly+Folium fallback
- Course-based predictions show qualifying language ("Course profile suggests...") on feed cards
- Race-type-only predictions show qualifying language ("Criteriums typically end this way...")
- Time-gap predictions continue to use definitive language ("The whole pack stayed together...")
- State filter does not include non-PNW values
- Cards with course-based predictions show the same structural elements as time-gap cards (finish description present, racer type present, similar races findable)

---

## Files Summary

| File | Action | Phase | Purpose |
|------|--------|-------|---------|
| `raceanalyzer/classification/course_predictor.py` | Create | 1 | Course-based finish type predictor with decision matrix |
| `raceanalyzer/db/models.py` | Modify | 1 | Add `prediction_source` to `SeriesPrediction` |
| `raceanalyzer/precompute.py` | Modify | 1, 2 | `_resolve_prediction`, `_get_series_race_type`, `inherit_race_type_from_series`, `backfill_race_types` |
| `raceanalyzer/predictions.py` | Modify | 1, 2 | Hedged narrative for course-based predictions, single-edition drop rate caveat |
| `raceanalyzer/queries.py` | Modify | 2, 4 | `PNW_STATES`, `finish_type_plain_english_with_source`, prediction_source in batch output |
| `raceanalyzer/cli.py` | Modify | 2 | `--backfill-types` flag on `compute-predictions` |
| `raceanalyzer/ui/pages/feed.py` | Modify | 3, 4 | Past-only series profile, prediction_source in cards, search preview summaries |
| `raceanalyzer/ui/components.py` | Modify | 3, 4 | `render_series_profile`, visual distinction for prediction sources |
| `raceanalyzer/ui/pages/race_preview.py` | Modify | 4 | Startlist label fix, elevation chart sizing |
| `tests/test_course_predictor.py` | Create | 1 | Decision matrix tests, refinement tests, edge cases |
| `tests/test_precompute.py` | Modify | 1, 2 | prediction_source priority, race_type inheritance |
| `tests/test_feed.py` | Modify | 3 | Deep-link and search behavior for past-only series |
| `tests/test_components.py` | Modify | 4 | Prediction source rendering, register button safety |
| `tests/test_queries.py` | Modify | 2, 4 | Plain English with source, PNW_STATES filtering, cascade integration |

---

## Definition of Done

### Course-Based Prediction (CP)
- [ ] `predict_from_course()` covers all 24 cells of the (course_character x race_type) decision matrix with unit tests
- [ ] Course-based prediction confidence is capped at 0.80; confidence label capped at "moderate"
- [ ] `prediction_source` column exists on `SeriesPrediction` with values: "time_gap", "course_profile", "race_type_only", or None
- [ ] Precompute pipeline never overwrites a time-gap prediction with a course-based one
- [ ] Finish type coverage increases from 55% to 80%+ of races with at least one non-UNKNOWN prediction (verified by `SELECT` query after `compute-predictions`)
- [ ] Race-type-only fallback provides predictions for series without course data but with a known race_type
- [ ] Crit m/km thresholds are offset from road race thresholds

### Data Pipeline (DP)
- [ ] All 18 upcoming races have a non-None `race_type` after `compute-predictions --backfill-types`
- [ ] Race type inheritance requires >= 80% historical agreement among typed editions
- [ ] `get_available_states()` excludes non-PNW states (Ontario, etc.)
- [ ] Single-edition series with near-zero drop rate display a caveat in the narrative

### Past-Only Series UX (PS)
- [ ] `/?series_id=9` renders an expanded race profile, not a collapsed expander
- [ ] Search for "Banana Belt" shows a preview summary above the collapsed "Past Races" section
- [ ] Past-only series profile includes: course data (if available), narrative, racer type, similar races, historical editions
- [ ] Graceful degradation: missing course data or predictions do not break the profile view

### UI Polish (UP)
- [ ] Startlist fallback header reads "Likely contenders based on past editions"
- [ ] Register button does not render when `registration_url` is null or empty
- [ ] Elevation chart height >= map height in Plotly+Folium fallback
- [ ] Course-based predictions use qualifying language ("Course profile suggests...") on cards and in narratives
- [ ] Race-type-only predictions use qualifying language ("Criteriums typically end this way...")
- [ ] Time-gap predictions continue to use definitive language ("Historically ends in...")

### Quality
- [ ] `ruff check .` passes
- [ ] `pytest` passes with no regressions
- [ ] New test file: `tests/test_course_predictor.py`
- [ ] Updated test files: `tests/test_precompute.py`, `tests/test_feed.py`, `tests/test_components.py`, `tests/test_queries.py`
- [ ] Feed load time remains < 1s cold / < 200ms warm (verified via PerfTimer)
- [ ] No new SQL queries added to the feed critical path (course predictor runs at precompute time only)

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Course predictor heuristics are wrong** — the decision matrix may mis-predict for edge cases (e.g., flat road race that historically produces breakaways due to wind or course layout) | Medium | Medium | Confidence ceiling of 0.80 limits downstream damage. `prediction_source` field makes it easy to audit and override. Hedged language ("suggests") sets user expectations. Post-sprint, `UserLabel` table can validate predictions. |
| **m/km thresholds need tuning** — the 5/10/18 breakpoints may not reflect PNW course reality (short steep courses vs long gradual grades) | Medium | Low | Thresholds are named constants in `course_predictor.py`, not hardcoded in branching logic. Phase 1 exit criteria includes a manual review of 10 series comparing predictions to local knowledge. Crit offset is separately configurable. |
| **Schema migration on production DB** — adding `prediction_source` column to `SeriesPrediction` | Low | Low | Nullable column, added via `Base.metadata.create_all()`. No existing column changes. Existing rows get `prediction_source = None` until next `compute-predictions` run. |
| **Past-only series profile is too query-heavy** — calling `get_feed_item_detail()` + `get_similar_series()` for deep-linked past series adds latency | Low | Medium | Only fires for isolated deep-links (`?series_id=N`), not for feed browsing. The detail query is already cached with 5-min TTL. Similarity scoring operates on the already-loaded feed items batch. |
| **Overscope** — 17 use cases across 4 phases | Medium | Medium | Phases are strictly ordered by dependency. Phase 1 (predictor) is the hard floor — it unblocks 4 issues alone. UP-04 (chart sizing) and CP-06 (race-type-only fallback) are P2 stretch goals individually deferrable to Sprint 013. |
| **Inconsistent prediction language across UI surfaces** — card, narrative, preview page each format predictions differently | Medium | Low | `finish_type_plain_english_with_source()` is the single source of truth for prediction text. All surfaces call it rather than formatting independently. |
| **Race type inheritance propagates wrong types** — e.g., a series that was historically a criterium but is switching to a road race | Low | Medium | 80% agreement threshold is deliberately high. If only 3 out of 5 editions are crits, we do not propagate. The scraper can always override with explicit data in future sprints. |

---

## Security Considerations

- **SQL injection**: No new raw SQL. Course predictor is pure Python logic operating on dataclass fields. Precompute pipeline uses SQLAlchemy ORM exclusively. The new `PNW_STATES` constant is a hardcoded set, not user input.
- **XSS via prediction_source**: The `prediction_source` field is set by server-side code (precompute pipeline), never by user input. It flows through `finish_type_plain_english_with_source()` which uses parameterized string formatting, not HTML interpolation. Any values rendered with `unsafe_allow_html=True` continue to use `html.escape()` for user-derived fields.
- **Schema migration safety**: The `prediction_source` column addition is additive-only. No existing columns are modified or dropped. `Base.metadata.create_all()` is idempotent for new tables/columns.
- **State filter hardcoding**: `PNW_STATES` is a server-side constant. It does not accept user input and cannot be manipulated via query params.

---

## Dependencies

- **No new Python dependencies** — course predictor uses only stdlib (dataclasses, enum) and existing project imports (db/models enums)
- **Sprint 011**: `SeriesPrediction` table, `get_feed_items_batch()`, `get_feed_item_detail()`, `compute_similarity()`, `get_similar_series()`, container card pattern, PerfTimer, `render_finish_pattern()`, `render_similar_races()`
- **Sprint 008**: `Course` table with `course_type`, `m_per_km`, `total_gain_m`, `distance_m`, `climbs_json` columns
- **Sprint 010**: Deep-link pattern (`?series_id=N`), URL state persistence, search query param
- **Existing `classification/finish_type.py`**: Time-gap classifier is preserved completely unchanged; course predictor is a sibling module in the same package, not a modification of the existing classifier

---

## Open Questions

1. **Should the decision matrix be a Config object or hardcoded constants?** Hardcoded constants are simpler and more auditable for a first implementation; a Config object (like the existing `Settings()` in config.py) would allow runtime tuning without code changes. Recommendation: start with constants in `course_predictor.py`, extract to Config if tuning becomes frequent after real-world validation.

2. **What happens when time-gap and course-based predictions disagree?** For example, time-gap says bunch_sprint but course profile is mountainous. Currently time-gap always wins (higher fidelity). Should we log disagreements for data quality review? Recommendation: yes, log at WARNING level during precompute. Disagreements may indicate data issues (wrong RWGPS route linked to a series, or genuinely unusual race dynamics worth investigating).

3. **Should `prediction_source` be exposed in the feed batch query (Tier 1) or only in the detail query (Tier 2)?** It is needed on the card (Tier 1) to choose the right text prefix for the finish description. Recommendation: include in Tier 1 — it is a single string column join, negligible query cost, and avoids needing Tier 2 for basic card rendering.

4. **For the past-only series profile, should we show a "Notify me when registration opens" CTA?** This would add significant value for the "plan my spring season" journey, but requires a notification system that does not exist. Recommendation: defer to a future sprint. For now, show "No upcoming edition scheduled" with the full profile content below it.

5. **Should race-type-only predictions (CP-06) be shown on cards, or only used for similarity scoring?** They are the lowest-confidence predictions (0.45-0.55). Recommendation: show them on cards with clear qualifying language ("Criteriums typically end in a bunch sprint") because some signal is better than none for the beginner racer deciding whether to register. The qualifying language makes the confidence level transparent.

6. **m/km thresholds: should the crit offset be configurable per-region?** PNW crits may differ from Midwest crits in typical terrain. Recommendation: not in this sprint. Use a single `_CRIT_OFFSET = -2.0` constant. If regional differences emerge from real-world validation, extract to Config in a future sprint.

7. **How to handle series with multiple courses (e.g., course changed year to year)?** The `Course` table links to `series_id` and the batch query takes the first match. For prediction purposes, the most recent course (by `extracted_at`) is the best proxy for the next edition. Recommendation: `_resolve_prediction()` uses the most recent course. If courses differ significantly across editions, the time-gap prediction (which uses actual results reflecting whatever course was used) is likely more reliable anyway and will take priority.
