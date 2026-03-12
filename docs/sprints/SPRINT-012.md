# Sprint 012: UX Audit Fix — Course-Based Prediction & Data Quality

## Overview

Sprint 012 closes the 13 remaining issues from the UX audit (`docs/UX_AUDIT_FINDINGS.md`). The root cause analysis reveals these are not 13 independent problems — they are a **data quality cascade**. When `predicted_finish_type` is UNKNOWN, five downstream systems degrade simultaneously:

```
predicted_finish_type = "unknown"
    |
    +-> Card finish description: HIDDEN (Issue #17)
    |     feed.py: finish_type_plain_english() returns None
    |
    +-> racer_type_description(): returns None (Issue #16)
    |     predictions.py: if not finish_type: return None
    |
    +-> racer_type_long_form(): returns None (Issue #16)
    |     predictions.py: calls racer_type_description()
    |
    +-> compute_similarity(): loses 30 points (Issue #15)
    |     queries.py: predicted_finish_type match = +30
    |
    +-> generate_narrative(): skips history sentence (Issue #5)
          predictions.py: if predicted_finish_type and edition_count > 0
```

The single most impactful change is a **course-based finish type predictor** that infers likely finish outcomes from terrain data for the 45% of races where time-gap classification is impossible. These 630 races have results but no finish times — the existing classifier will never help them. Fixing prediction at the source cascades improvements through all five systems without modifying their consumer logic.

The approach is deliberately conservative about confidence. Course-based predictions use hedged phrasing ("Course profile suggests a bunch sprint") rather than the definitive language of time-gap predictions ("Historically ends in a bunch sprint"). A new `prediction_source` field on `SeriesPrediction` makes this distinction explicit in the data model, the UI, and the narrative. This honesty about uncertainty is itself a UX improvement.

The remaining nine issues span: **data pipeline gaps** (race_type on upcoming races), **deep-link UX** (past-only series showing empty pages), and **minor UI fixes** (startlist label, state filter, register button, chart sizing). The sprint is organized into 5 phases ordered by dependency.

---

## Use Cases

### Course-Based Prediction (CP-01 -> CP-07)

| ID | Name | Priority | Audit Issues | Affected Journeys |
|----|------|----------|--------------|-------------------|
| CP-01 | Course-based finish type predictor with climb-aware rules | P0 | #5 | 2, 5 |
| CP-02 | prediction_source field on SeriesPrediction | P0 | #5, #17 | 1, 2, 5, 7, 10 |
| CP-03 | Integrate course predictor into precompute pipeline | P0 | #5, #17 | All |
| CP-04 | Race-type-only fallback for series without course data | P1 | #5 | 2, 5 |
| CP-05 | Course-predicted finish types populate similarity scoring | P1 | #15 | 6 |
| CP-06 | Course-predicted finish types populate racer type description | P1 | #16 | 5 |
| CP-07 | Source-aware hedged language on cards and narratives | P1 | #17 | 1, 7, 10 |

### Data Pipeline (DP-01 -> DP-02)

| ID | Name | Priority | Audit Issues | Affected Journeys |
|----|------|----------|--------------|-------------------|
| DP-01 | Inherit race_type on upcoming races from series history | P0 | #6 | 4 |
| DP-02 | Expand RWGPS route linking and series edition coverage | P2 | #7, #8 | 1, 2, 5, 7, 9 |

### Deep-Link & Search UX (DL-01 -> DL-02)

| ID | Name | Priority | Audit Issues | Affected Journeys |
|----|------|----------|--------------|-------------------|
| DL-01 | Deep-link to past-only series shows expanded card | P0 | #9 | 6, 10 |
| DL-02 | Search for past-only series shows preview summary | P1 | #10 | 5 |

### UI Polish (UP-01 -> UP-04)

| ID | Name | Priority | Audit Issues | Affected Journeys |
|----|------|----------|--------------|-------------------|
| UP-01 | Startlist label: "Likely contenders based on past editions" | P0 | #11 | 3 |
| UP-02 | PNW state whitelist (remove Ontario) | P1 | #12 | 4 |
| UP-03 | Guard register button on null registration_url | P1 | #13 | 1, 10 |
| UP-04 | Increase elevation chart height relative to map | P2 | #14 | 9 |

---

## Architecture

### Course-Based Predictor: Decision Tree with Climb-Aware Rules

The predictor uses a decision tree in a new `classification/course_predictor.py` module, separate from the existing time-gap classifier (`classification/finish_type.py`). The two predictors share a domain but have fundamentally different inputs (terrain features vs gap-grouped results).

**m/km Thresholds with Crit Offset:**

| m/km Range (Road) | m/km Range (Crit) | Terrain | Rationale |
|---|---|---|---|
| 0 - 5 | 0 - 3 | Flat | Short crit laps amplify even small elevation |
| 5 - 12 | 3 - 10 | Rolling | Enough climbing for surges but not sustained selection |
| 12 - 20 | 10 - 18 | Hilly | Repeated efforts thin the field |
| > 20 | > 18 | Mountainous | Pure climber territory |

The crit-specific offset (`_CRIT_OFFSET = -2.0`) recognizes that a 5 m/km criterium on a short repeated loop is experientially "rolling" compared to a 5 m/km road race over 80 km.

**Key Algorithm:**

```python
# classification/course_predictor.py

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from raceanalyzer.db.models import FinishType


@dataclass
class CoursePrediction:
    """Result of course-based finish type prediction."""
    finish_type: FinishType
    confidence: float          # 0.0-1.0
    source: str                # "course_profile" or "race_type_only"
    reasoning: str             # human-readable explanation


# --- Thresholds ---
_THRESHOLDS = (5.0, 12.0, 20.0)  # flat/rolling, rolling/hilly, hilly/mountainous
_CRIT_OFFSET = -2.0               # shift thresholds down for crits

STEEP_CLIMB_GRADE = 8.0           # Climbs averaging 8%+ are selective
LONG_CLIMB_M = 2000.0             # Climbs >2 km are significant
LONG_ROAD_RACE_M = 80000.0        # Races >80 km are more selective


def _resolve_course_character(
    course_type: str | None,
    m_per_km: float | None,
    race_type: str | None = None,
) -> str | None:
    """Derive course character from stored course_type or raw m_per_km."""
    if course_type and course_type not in ("unknown", ""):
        return course_type

    if m_per_km is None:
        return None

    t1, t2, t3 = _THRESHOLDS
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


def predict_finish_type_from_course(
    course_type: str | None,
    race_type: str | None,
    total_gain_m: float | None = None,
    distance_m: float | None = None,
    climbs_json: str | None = None,
    m_per_km: float | None = None,
) -> CoursePrediction | None:
    """Predict finish type from course characteristics.

    Returns None if insufficient data. Uses a decision tree
    with climb-aware rules for richer predictions on hilly/
    mountainous courses.
    """
    # Parse climbs
    climbs: list[dict] = []
    if climbs_json:
        try:
            climbs = json.loads(climbs_json) if isinstance(climbs_json, str) else climbs_json
        except (json.JSONDecodeError, TypeError):
            pass

    # Compute m/km if not provided
    if m_per_km is None and total_gain_m and distance_m and distance_m > 0:
        m_per_km = (total_gain_m / distance_m) * 1000.0

    character = _resolve_course_character(course_type, m_per_km, race_type)

    # --- Rule 1: Time trials ---
    if race_type == "time_trial":
        return CoursePrediction(
            finish_type=FinishType.INDIVIDUAL_TT,
            confidence=0.95,
            source="race_type_only",
            reasoning="Race type is time trial.",
        )

    # --- Rule 2: Hill climbs -> GC_SELECTIVE (mass-start, not TT) ---
    if race_type == "hill_climb":
        return CoursePrediction(
            finish_type=FinishType.GC_SELECTIVE,
            confidence=0.85,
            source="race_type_only",
            reasoning="Hill climbs are mass-start climbing events.",
        )

    # --- Rule 3: Criteriums ---
    if race_type == "criterium":
        if character and character in ("hilly", "mountainous"):
            return CoursePrediction(
                finish_type=FinishType.REDUCED_SPRINT,
                confidence=0.55,
                source="course_profile",
                reasoning=(
                    f"Criterium on {character} terrain"
                    " — hillier than typical, likely a reduced field sprint."
                ),
            )
        return CoursePrediction(
            finish_type=FinishType.BUNCH_SPRINT,
            confidence=0.75 if character else 0.60,
            source="course_profile" if character else "race_type_only",
            reasoning="Criteriums typically end in bunch sprints.",
        )

    # --- Rule 4: Need some data for road races ---
    if character is None and race_type is None:
        return None  # Not enough data

    # Race-type-only fallback for road races without course data
    if character is None:
        if race_type == "road_race":
            return None  # Road race without course data is too ambiguous
        if race_type == "gravel":
            return CoursePrediction(
                finish_type=FinishType.REDUCED_SPRINT,
                confidence=0.50,
                source="race_type_only",
                reasoning="Gravel races typically thin the field.",
            )
        if race_type == "stage_race":
            return CoursePrediction(
                finish_type=FinishType.MIXED,
                confidence=0.45,
                source="race_type_only",
                reasoning="Stage races have varied finishes across stages.",
            )
        return None  # Unknown race type without course data

    # --- From here, character is not None ---
    m_per_km_str = f"{m_per_km:.0f} m/km" if m_per_km is not None else character

    # --- Rule 5: Mountainous terrain ---
    if character == "mountainous":
        has_steep_climb = any(
            c.get("avg_grade", 0) >= STEEP_CLIMB_GRADE for c in climbs
        )
        has_long_climb = any(
            c.get("length_m", 0) >= LONG_CLIMB_M for c in climbs
        )

        if has_steep_climb or has_long_climb:
            return CoursePrediction(
                finish_type=FinishType.BREAKAWAY_SELECTIVE,
                confidence=0.70,
                source="course_profile",
                reasoning=(
                    f"Mountainous course ({m_per_km_str}) with "
                    f"{'steep' if has_steep_climb else 'long'} climbs "
                    "— the field will likely shatter."
                ),
            )
        return CoursePrediction(
            finish_type=FinishType.GC_SELECTIVE,
            confidence=0.65,
            source="course_profile",
            reasoning=f"Mountainous course ({m_per_km_str}) — expect a selective finish.",
        )

    # --- Rule 6: Hilly terrain ---
    if character == "hilly":
        n_climbs = len(climbs)
        has_late_climb = False
        if distance_m and distance_m > 0:
            has_late_climb = any(
                c.get("start_d", 0) / distance_m > 0.6 for c in climbs
            )

        if has_late_climb and n_climbs >= 2:
            return CoursePrediction(
                finish_type=FinishType.BREAKAWAY_SELECTIVE,
                confidence=0.60,
                source="course_profile",
                reasoning=(
                    f"Hilly course ({m_per_km_str}) with "
                    f"{n_climbs} climbs including a late climb "
                    "— likely a selective breakaway finish."
                ),
            )
        if n_climbs >= 3:
            return CoursePrediction(
                finish_type=FinishType.SMALL_GROUP_SPRINT,
                confidence=0.55,
                source="course_profile",
                reasoning=(
                    f"Hilly course ({m_per_km_str}) with "
                    f"{n_climbs} climbs — expect a reduced group sprint."
                ),
            )
        return CoursePrediction(
            finish_type=FinishType.REDUCED_SPRINT,
            confidence=0.55,
            source="course_profile",
            reasoning=f"Hilly course ({m_per_km_str}) — the climbs will thin the field.",
        )

    # --- Rule 7: Rolling terrain ---
    if character == "rolling":
        is_long = distance_m is not None and distance_m > LONG_ROAD_RACE_M
        if is_long:
            return CoursePrediction(
                finish_type=FinishType.REDUCED_SPRINT,
                confidence=0.55,
                source="course_profile",
                reasoning=(
                    f"Long rolling course ({distance_m / 1000:.0f} km, "
                    f"{m_per_km_str}) — fatigue will thin the sprint group."
                ),
            )
        return CoursePrediction(
            finish_type=FinishType.BUNCH_SPRINT,
            confidence=0.55,
            source="course_profile",
            reasoning=f"Rolling course ({m_per_km_str}) — most rolling races still end in a group sprint.",
        )

    # --- Rule 8: Flat terrain ---
    if character == "flat":
        is_long = distance_m is not None and distance_m > LONG_ROAD_RACE_M
        conf = 0.70 if is_long else 0.65
        return CoursePrediction(
            finish_type=FinishType.BUNCH_SPRINT,
            confidence=conf,
            source="course_profile",
            reasoning=f"Flat course ({m_per_km_str}) — expect the pack to stay together.",
        )

    return None
```

### Prediction Priority: Three-Tier Cascade

The orchestration lives in `precompute.py`, keeping `predict_series_finish_type()` in `predictions.py` unchanged:

```python
# In precompute.py

def _resolve_prediction(session, series_id, category, course):
    """Resolve finish type with source priority.

    1. Time-gap (highest fidelity, empirical data)
    2. Course profile (terrain + race type heuristic)
    3. Race type only (lowest fidelity)
    """
    # 1. Time-gap prediction
    time_gap = predict_series_finish_type(session, series_id, category)
    if time_gap["predicted_finish_type"] != "unknown":
        return {**time_gap, "prediction_source": "time_gap"}

    # 2. Course-based prediction
    race_type = _get_series_race_type(session, series_id)
    if course:
        course_pred = predict_finish_type_from_course(
            course_type=course.course_type.value if course.course_type else None,
            race_type=race_type,
            total_gain_m=course.total_gain_m,
            distance_m=course.distance_m,
            climbs_json=course.climbs_json,
            m_per_km=course.m_per_km,
        )
        if course_pred:
            return {
                "predicted_finish_type": course_pred.finish_type.value,
                "confidence": _confidence_label(course_pred.confidence),
                "edition_count": time_gap["edition_count"],
                "distribution": time_gap["distribution"],
                "prediction_source": course_pred.source,
                "reasoning": course_pred.reasoning,
            }

    # 3. Race-type-only fallback (no course data)
    if race_type:
        rt_pred = predict_finish_type_from_course(
            course_type=None, race_type=race_type,
        )
        if rt_pred:
            return {
                "predicted_finish_type": rt_pred.finish_type.value,
                "confidence": _confidence_label(rt_pred.confidence),
                "edition_count": time_gap["edition_count"],
                "distribution": time_gap["distribution"],
                "prediction_source": "race_type_only",
                "reasoning": rt_pred.reasoning,
            }

    # 4. Unknown
    return {**time_gap, "prediction_source": None}


def _get_series_race_type(session, series_id):
    """Infer race_type from series history. >50% threshold, min 2 editions."""
    historical = (
        session.query(Race.race_type)
        .filter(
            Race.series_id == series_id,
            Race.is_upcoming.is_(False),
            Race.race_type.isnot(None),
        )
        .all()
    )
    if len(historical) < 2:
        return None

    from collections import Counter
    type_counts = Counter(r[0].value for r in historical)
    total = sum(type_counts.values())
    most_common, count = type_counts.most_common(1)[0]
    if count / total > 0.50:
        return most_common
    return None


def _confidence_label(numeric_conf: float) -> str:
    """Convert numeric confidence to label. Course-based caps at 'moderate'."""
    if numeric_conf >= 0.65:
        return "moderate"
    return "low"
```

### Race Type Inheritance for Upcoming Races

```python
def populate_upcoming_race_types(session):
    """Inherit race_type for upcoming races from series history.

    Uses simple majority (>50%) with minimum 2 historical editions.
    """
    upcoming = (
        session.query(Race)
        .filter(Race.is_upcoming.is_(True), Race.race_type.is_(None))
        .all()
    )
    updated = 0
    for race in upcoming:
        if not race.series_id:
            continue
        inferred = _get_series_race_type(session, race.series_id)
        if inferred:
            race.race_type = RaceType(inferred)
            updated += 1
    session.commit()
    return updated
```

### Source-Aware UX Language

Course-based predictions use qualifying language to maintain user trust:

| Source | Card Text | Narrative Phrasing |
|--------|-----------|-------------------|
| `time_gap` | "The whole pack stayed together and sprinted for the line" | "Based on N previous editions, this race typically ends in a bunch sprint." |
| `course_profile` | "Course profile suggests a bunch sprint finish" | "The course profile suggests this race likely ends in a bunch sprint." |
| `race_type_only` | "Criteriums typically end in a bunch sprint" | "As a criterium, this race typically ends in a bunch sprint." |

```python
# In queries.py
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
        return f"Course profile suggests: {base[0].lower()}{base[1:]}"
    elif prediction_source == "race_type_only":
        rt_display = race_type_display_name(race_type) if race_type else "This race type"
        return f"{rt_display}s typically end this way: {base[0].lower()}{base[1:]}"
    else:
        return base
```

### Schema Change

Add `prediction_source` column to `SeriesPrediction`:

```python
prediction_source = Column(String, nullable=True)
# Values: "time_gap", "course_profile", "race_type_only", None
```

**Migration:** `Base.metadata.create_all()` does NOT add columns to existing tables. Add explicit migration:

```python
# In cli.py compute-predictions command, before running predictions:
from sqlalchemy import text, inspect
insp = inspect(session.bind)
columns = [c["name"] for c in insp.get_columns("series_predictions")]
if "prediction_source" not in columns:
    session.execute(text("ALTER TABLE series_predictions ADD COLUMN prediction_source VARCHAR"))
    session.commit()
```

### RACER_TYPE_DESCRIPTIONS Expansion

Add 3 missing entries for combinations the course predictor will produce:

```python
# Add to RACER_TYPE_DESCRIPTIONS in predictions.py:
("hilly", "breakaway_selective"): "Strong climbers who can attack on the decisive hills dominate.",
("hilly", "small_group_sprint"): "Punchy riders who survive the climbs and still have a kick do well.",
("mountainous", "breakaway_selective"): "Pure climbers who can sustain attacks on long climbs thrive.",
```

---

## Implementation

### Phase 1: Course-Based Finish Type Predictor (~30%)

**Goal**: Build and test the course-based predictor as a standalone module. Zero database dependencies for the predictor itself.

**Tasks:**
- [ ] Create `raceanalyzer/classification/course_predictor.py` with `CoursePrediction` dataclass, `_resolve_course_character()` with crit offset, and `predict_finish_type_from_course()` decision tree
- [ ] Implement all rule branches: TT, hill climb, criterium (flat vs hilly), road race per terrain (mountainous with climb analysis, hilly with late-climb detection, rolling, flat), gravel, stage race, race-type-only fallback
- [ ] Guard against None m_per_km in reasoning strings (use `character` as fallback text)
- [ ] Create `tests/test_course_predictor.py` with tests for each rule:
  - Time trial -> INDIVIDUAL_TT (0.95)
  - Hill climb -> GC_SELECTIVE (0.85)
  - Criterium + flat -> BUNCH_SPRINT (0.75)
  - Criterium + hilly -> REDUCED_SPRINT (0.55)
  - Criterium + no course data -> BUNCH_SPRINT (0.60)
  - Road race + mountainous + steep climb -> BREAKAWAY_SELECTIVE (0.70)
  - Road race + mountainous, no steep climb -> GC_SELECTIVE (0.65)
  - Road race + hilly + late climb + 2+ climbs -> BREAKAWAY_SELECTIVE (0.60)
  - Road race + hilly + 3+ climbs -> SMALL_GROUP_SPRINT (0.55)
  - Road race + hilly -> REDUCED_SPRINT (0.55)
  - Road race + rolling + long -> REDUCED_SPRINT (0.55)
  - Road race + rolling + short -> BUNCH_SPRINT (0.55)
  - Road race + flat -> BUNCH_SPRINT (0.65-0.70)
  - Road race + no course data -> None (too ambiguous)
  - Gravel + no course -> REDUCED_SPRINT (0.50)
  - No data at all -> None
  - Crit m/km offset: 4 m/km crit classified as "rolling", not "flat"
  - Confidence never exceeds 0.75 for course_profile, 0.60 for race_type_only (except TT/hill_climb)
- [ ] Test malformed climbs_json (garbage string, empty list, None)

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/classification/course_predictor.py` | Create | Decision tree predictor with climb-aware rules |
| `tests/test_course_predictor.py` | Create | Exhaustive unit tests for all rule branches |

**Exit criteria:**
- All 17+ test cases pass
- Predictor is a pure function with zero database dependencies
- Crit offset shifts terrain classification boundaries correctly
- Confidence caps enforced (verified by test)
- Returns None for insufficient data (no false predictions)

---

### Phase 2: Pipeline Integration & Prediction Source (~30%)

**Goal**: Wire the course predictor into the precompute pipeline. Add `prediction_source` column. Populate race_type on upcoming races. Expand RACER_TYPE_DESCRIPTIONS.

**Tasks:**
- [ ] Add `prediction_source` column to `SeriesPrediction` model in `raceanalyzer/db/models.py`
- [ ] Add migration check in CLI: inspect columns, ALTER TABLE if `prediction_source` missing
- [ ] Add `_resolve_prediction()`, `_get_series_race_type()`, `_confidence_label()` to `raceanalyzer/precompute.py`
- [ ] Update `precompute_series_predictions()` to use `_resolve_prediction()` and store `prediction_source`
- [ ] Add `populate_upcoming_race_types()` to `raceanalyzer/precompute.py`
- [ ] Integrate `populate_upcoming_race_types()` into `precompute_all()` as a pre-step
- [ ] Add `--stats` flag to `compute-predictions` CLI: print before/after coverage stats
- [ ] Add 3 new entries to `RACER_TYPE_DESCRIPTIONS` in `predictions.py`
- [ ] Update `generate_narrative()` to accept `prediction_source` param; use hedged language for course-based predictions
- [ ] Handle multi-course series: use most recent Course by `extracted_at`
- [ ] Ensure CourseType enum -> string conversion via `.value` at integration boundary
- [ ] Update `tests/test_precompute.py`: verify pipeline prefers time-gap over course-based, sets prediction_source correctly
- [ ] Add test: series with Course data but all-UNKNOWN classifications gets course-based prediction
- [ ] Add test: series with time-gap data keeps time-gap prediction (no override)
- [ ] Add test: populate_upcoming_race_types uses >50% threshold, min 2 editions
- [ ] Add test: racer_type_description returns non-None for all course predictor output combinations

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/db/models.py` | Modify | Add `prediction_source` to SeriesPrediction |
| `raceanalyzer/precompute.py` | Modify | `_resolve_prediction`, `_get_series_race_type`, `populate_upcoming_race_types` |
| `raceanalyzer/predictions.py` | Modify | Expand RACER_TYPE_DESCRIPTIONS (3 entries); hedged narrative language |
| `raceanalyzer/cli.py` | Modify | Migration check; `--stats` flag; integrate race_type population |
| `tests/test_precompute.py` | Modify | Pipeline integration tests |
| `tests/test_predictions.py` | Modify | Racer type coverage; narrative with prediction_source |

**Exit criteria:**
- Running `compute-predictions` increases non-UNKNOWN finish type coverage from 55% to 80%+
- All 18 upcoming races have race_type populated
- prediction_source correctly set on all SeriesPrediction rows
- Time-gap predictions never overwritten by course predictions
- RACER_TYPE_DESCRIPTIONS covers all (course_type, finish_type) pairs the predictor can produce
- generate_narrative() uses "Course profile suggests..." for course-based predictions
- `--stats` flag prints coverage before/after

---

### Phase 3: Deep-Link & Search UX for Past-Only Series (~15%)

**Goal**: When a shared link points to a past-only series, show useful content instead of an empty page. When search returns only past series, show preview summaries.

**Tasks:**
- [ ] In `raceanalyzer/ui/pages/feed.py`, when `isolated_series_id` is set and the matched item is past-only:
  - Render it as an expanded container card at the top level (reuse existing `_render_container_card` with `expanded=True`)
  - Show "Show all races" button above the card
  - Auto-expand Tier 2 content (narrative, climbs, editions) since the user specifically navigated here
- [ ] When `search_query` is set and all results are past-only:
  - Render first 3 results as expanded container cards in the main body
  - Add caption: "Showing past editions for '{search_query}'"
  - Keep remaining results in collapsed expander if >3
- [ ] Handle mixed search results (some upcoming, some past): upcoming items render normally; past-only items get preview treatment only when ALL results are past
- [ ] Tests: deep-link to past-only series renders expanded card; search with all-past results shows previews

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/ui/pages/feed.py` | Modify | Force-expand past-only deep-links; search preview summaries |
| `tests/test_feed.py` | Modify | Deep-link and search behavior tests |

**Exit criteria:**
- `/?series_id=9` (Gorge Roubaix) shows expanded card with name, location, terrain, narrative, Tier 2 content
- Searching "Banana Belt" shows preview cards, not just "Past Races (N)" collapsed
- Existing deep-links and searches for upcoming series continue to work

---

### Phase 4: UI Polish & Card Consistency (~20%)

**Goal**: Fix remaining UI issues and wire source-aware prediction language into cards.

**Tasks:**
- [ ] **UP-01 — Startlist label**: Change "Based on past editions (no startlist available)" to "Likely contenders based on past editions" when rider data comes from historical fallback (check `source` field of contenders DataFrame)
- [ ] **UP-02 — PNW state filter**: Add `PNW_STATES = {"WA", "OR", "ID", "BC", "MT"}` to `queries.py`; filter `get_available_states()` to whitelist
- [ ] **UP-03 — Register button**: Verify existing guard `item.get("is_upcoming") and item.get("registration_url")` works; add explicit truthiness check to catch empty strings
- [ ] **UP-04 — Elevation chart sizing**: Increase Plotly chart height from ~250px to ~400px; reduce Folium map height from ~400px to ~300px
- [ ] **CP-07 — Source-aware language**: Add `finish_type_plain_english_with_source()` to `queries.py`; include `prediction_source` in `get_feed_items_batch()` Tier 1 output; update card rendering to use source-aware text
- [ ] Tests: state filter excludes Ontario; startlist label changes based on source; card rendering with different prediction_source values

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/queries.py` | Modify | PNW whitelist; `finish_type_plain_english_with_source()`; prediction_source in batch output |
| `raceanalyzer/ui/pages/race_preview.py` | Modify | Startlist label fix; elevation chart sizing |
| `raceanalyzer/ui/pages/feed.py` | Modify | Source-aware card rendering |
| `tests/test_queries.py` | Modify | State filter; plain English with source |
| `tests/test_components.py` | Modify | Register button guard; prediction source rendering |

**Exit criteria:**
- Startlist shows "Likely contenders based on past editions" for historical fallback
- State filter shows only WA, OR, ID, BC, MT
- Register button does not render when registration_url is null/empty
- Elevation chart is taller than the map
- Course-based predictions show "Course profile suggests..." on cards
- Race-type-only predictions show "Criteriums typically end this way..."
- Time-gap predictions continue to use definitive language

---

### Phase 5: Data Quality Improvements (~5%)

**Goal**: Best-effort expansion of RWGPS route coverage and series edition linking.

**Tasks:**
- [ ] Run existing RWGPS route matching against series lacking Course rows; document new coverage
- [ ] Investigate Banana Belt edition linking (series matching too strict? unlinked races?)
- [ ] Re-run `compute-predictions` after linking new data
- [ ] Document final coverage metrics (series with Course data, edition counts, finish type coverage %)

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/series.py` | Possible modify | Series matching improvements if needed |
| `raceanalyzer/cli.py` | Possible modify | Route matching improvements if needed |

**Exit criteria:**
- At least 5 additional series gain Course rows
- At least 2 additional series gain multiple linked editions
- Finish type coverage reaches 80%+ of races
- Coverage metrics documented

---

## Files Summary

| File | Action | Phase | Purpose |
|------|--------|-------|---------|
| `raceanalyzer/classification/course_predictor.py` | Create | 1 | Decision tree predictor with climb-aware rules and crit offset |
| `raceanalyzer/db/models.py` | Modify | 2 | Add `prediction_source` to SeriesPrediction |
| `raceanalyzer/precompute.py` | Modify | 2 | `_resolve_prediction`, `_get_series_race_type`, `populate_upcoming_race_types` |
| `raceanalyzer/predictions.py` | Modify | 2 | Expand RACER_TYPE_DESCRIPTIONS; hedged narrative for course predictions |
| `raceanalyzer/cli.py` | Modify | 2 | Migration check; `--stats` flag; race_type population |
| `raceanalyzer/queries.py` | Modify | 4 | PNW whitelist; `finish_type_plain_english_with_source()`; prediction_source in batch |
| `raceanalyzer/ui/pages/feed.py` | Modify | 3, 4 | Past-only deep-link/search fix; source-aware card rendering |
| `raceanalyzer/ui/pages/race_preview.py` | Modify | 4 | Startlist label fix; elevation chart sizing |
| `tests/test_course_predictor.py` | Create | 1 | Exhaustive predictor unit tests |
| `tests/test_precompute.py` | Modify | 2 | Pipeline integration; prediction_source; race_type inheritance |
| `tests/test_predictions.py` | Modify | 2 | Racer type coverage; narrative source awareness |
| `tests/test_feed.py` | Modify | 3 | Deep-link and search behavior |
| `tests/test_queries.py` | Modify | 4 | State filter; plain English with source |
| `tests/test_components.py` | Modify | 4 | Register button guard; source rendering |

---

## Definition of Done

### Course-Based Prediction (CP)
- [ ] `predict_finish_type_from_course()` covers all rule branches with unit tests (17+ cases)
- [ ] Crit m/km offset shifts terrain boundaries correctly (verified by test)
- [ ] Confidence never exceeds 0.75 for course_profile or 0.60 for race_type_only (except TT/hill_climb)
- [ ] `prediction_source` column on SeriesPrediction with values: "time_gap", "course_profile", "race_type_only", None
- [ ] Precompute pipeline never overwrites time-gap prediction with course-based
- [ ] Three-tier priority: time-gap > course_profile > race_type_only
- [ ] Finish type coverage increases from 55% to 80%+ (verified by `--stats` output)
- [ ] RACER_TYPE_DESCRIPTIONS covers all (course_type, finish_type) pairs predictor can produce
- [ ] Hedged narrative: "Course profile suggests..." for course-based; "Criteriums typically..." for race-type-only
- [ ] CourseType enum properly converted to string via `.value` at integration boundary
- [ ] Multi-course series resolved by most recent `extracted_at`

### Data Pipeline (DP)
- [ ] All 18 upcoming races have race_type populated (inherited from series history, >50% threshold, min 2 editions)
- [ ] populate_upcoming_race_types() integrated into precompute_all() as pre-step
- [ ] `--stats` CLI flag prints before/after coverage

### Deep-Link & Search UX (DL)
- [ ] `/?series_id=N` for past-only series shows expanded card with Tier 2 content, not a collapsed expander
- [ ] Searching for past-only series shows preview cards
- [ ] Existing upcoming deep-links and searches unaffected

### UI Polish (UP)
- [ ] Startlist label: "Likely contenders based on past editions" for historical fallback
- [ ] State filter: only WA, OR, ID, BC, MT (no Ontario)
- [ ] Register button: does not render when registration_url is null/empty
- [ ] Elevation chart height >= map height in Plotly+Folium fallback
- [ ] Source-aware language on feed cards via `finish_type_plain_english_with_source()`

### Quality
- [ ] `ruff check .` passes
- [ ] `pytest` passes with no regressions
- [ ] New: `tests/test_course_predictor.py`
- [ ] Updated: `tests/test_precompute.py`, `tests/test_predictions.py`, `tests/test_feed.py`, `tests/test_queries.py`, `tests/test_components.py`
- [ ] Feed load time < 1s cold / < 200ms warm (no new SQL queries in feed path)
- [ ] Batch query count remains <= 6 (course predictor runs at precompute time only)
- [ ] Precompute pipeline runtime < 5 minutes for full recompute

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Course predictor heuristics wrong** — terrain is an indirect signal; flat courses can produce breakaways due to wind/tactics | Medium | Medium | Cap confidence at 0.75; use hedged language ("suggests"); `prediction_source` enables auditing; `reasoning` field aids debugging |
| **m/km thresholds need tuning** — 5/12/20 breakpoints are informed estimates from PNW course data | Medium | Low | Thresholds are named constants, easily tuned. Crit offset is separately configurable. Manual review of 10 series during Phase 2 exit |
| **Race type inheritance propagates wrong type** — series that changed format | Low | Medium | >50% threshold requires clear majority; min 2 editions prevents single-edition inheritance; scraper can override in future |
| **Schema migration on existing DB** — prediction_source column addition | Low | Low | Explicit ALTER TABLE with column existence check (no reliance on create_all). Safe: nullable, no constraint |
| **CourseType enum vs string mismatch** — predictor uses strings, DB uses enums | Medium | Medium | Integration layer explicitly calls `.value`; unit test verifies enum conversion |
| **climbs_json parse failures** — malformed JSON in production DB | Low | Low | try/except in predictor; empty climbs list degrades gracefully to terrain-only rules |
| **Past-only deep-link query cost** — get_feed_item_detail() + Tier 2 on deep-link | Low | Medium | Only fires for isolated deep-links; detail query already cached with 5-min TTL |
| **RACER_TYPE_DESCRIPTIONS gap** — new predictor combinations missing descriptions | Medium | Low | Explicitly adding 3 missing entries in Phase 2; test verifies coverage for all predictor outputs |
| **Phase 5 data quality work is unbounded** — RWGPS linking and edition discovery are research tasks | Medium | Low | Phase 5 is best-effort at 5% of sprint; core predictor works with existing data |

---

## Security Considerations

- **SQL injection**: No new raw SQL. Course predictor is pure Python. Precompute pipeline uses SQLAlchemy ORM. The migration ALTER TABLE uses `text()` with no user input interpolation.
- **XSS via prediction_source**: Set only by server-side precompute code, never user input. Flows through `finish_type_plain_english_with_source()` which uses parameterized formatting.
- **PNW_STATES**: Hardcoded server-side constant, not derived from user input.
- **Course predictor inputs**: All from database (Course table, Race table), not user-provided.
- **Existing guards preserved**: Register button guard, HTML escaping, parameterized SQLAlchemy queries — all unchanged.

---

## Dependencies

- **No new Python dependencies** — course predictor uses only stdlib (json, dataclasses) and existing project imports
- **Sprint 011**: SeriesPrediction table, precompute pipeline, get_feed_items_batch(), container cards, PerfTimer
- **Sprint 008**: Course table with course_type, total_gain_m, distance_m, m_per_km, climbs_json
- **Sprint 010**: Deep-link pattern (?series_id=N), URL state persistence, search query param
- **Sprint 009**: Startlist data for label fix
- **Existing classification/finish_type.py**: Preserved completely unchanged; course predictor is a sibling module

---

## Open Questions

1. **Should course predictions apply per-category or series-level?** Course terrain is identical for all categories, but race dynamics differ (Cat 5 vs Pro/1/2). Recommendation: apply same course prediction to all categories; confidence is already conservative enough to account for this.

2. **Should we log time-gap vs course prediction disagreements?** If time-gap says bunch_sprint but course is mountainous, something may be wrong with the linked RWGPS route. Recommendation: log at WARNING during precompute — useful data quality signal.

3. **Should prediction_reasoning be stored in the DB?** The `reasoning` field on `CoursePrediction` is useful for debugging. Recommendation: defer to Sprint 013. Log it during precompute but don't add a column yet.

4. **Should mountainous+criterium be in the decision tree?** Rare combination (uphill crits exist). Currently falls through to the crit rule. Recommendation: leave as-is; the crit rule + hilly character check handles it correctly with REDUCED_SPRINT.

5. **Should the 50% race_type inheritance threshold be configurable?** Recommendation: hardcode initially. If racers report mis-inherited types, extract to Settings.
