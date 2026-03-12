# Sprint 012: UX Audit Fix — Course-Based Prediction & Data Quality

## Overview

Sprint 012 closes the 13 remaining issues found in the UX audit (`docs/UX_AUDIT_FINDINGS.md`). The single most impactful change is a **course-based finish type predictor** that infers likely finish outcomes from terrain data (elevation gain, distance, m/km, climb count, race type) for the 45% of races where time-gap classification is impossible. These 630 races have results but no finish times — the existing classifier will never help them. A course-based heuristic fills this gap, lifting finish type coverage from 55% to 80%+ and unblocking four cascading UX issues: missing finish type descriptions on cards (#17), empty "Similar Races" sections (#15), absent "Who does well here?" paragraphs (#16), and the generic "No historical data for predictions yet" message (#5).

The remaining nine issues span three categories: **data pipeline gaps** (populating `race_type` on upcoming races from series history, expanding RWGPS coverage, linking more series editions), **deep-link UX** (showing useful content when a shared link points to a past-only series instead of a collapsed expander), and **minor UI fixes** (startlist label contradiction, Ontario in the state filter, register button guarding, elevation chart sizing). These are smaller, well-scoped changes with clear root causes documented in the audit.

The sprint is organized into 5 phases ordered by dependency. Phase 1 builds the course-based predictor (the foundation everything else depends on). Phase 2 integrates it into the pre-computation pipeline and populates `race_type` on upcoming races. Phase 3 fixes deep-link and search UX for past-only series. Phase 4 addresses the startlist label and minor UI fixes. Phase 5 improves data quality by expanding RWGPS linking and series edition coverage.

---

## Use Cases

### Course-Based Prediction (CP-01 → CP-06)

| ID | Name | Priority | Audit Issue |
|----|------|----------|-------------|
| CP-01 | Predict finish type from course terrain + race type | P0 | #5 |
| CP-02 | Integrate course predictor into pre-computation pipeline | P0 | #5 |
| CP-03 | Populate finish type description on feed cards for course-predicted series | P0 | #17 |
| CP-04 | Enable similarity scoring for course-predicted series | P1 | #15 |
| CP-05 | Generate "Who does well here?" for course-predicted series | P1 | #16 |
| CP-06 | Add prediction_source field to track provenance (time-gap vs course) | P1 | #5 |

### Data Pipeline (DP-01 → DP-03)

| ID | Name | Priority | Audit Issue |
|----|------|----------|-------------|
| DP-01 | Populate race_type on upcoming races from series history | P0 | #6 |
| DP-02 | Expand RWGPS route linking to more series | P2 | #7 |
| DP-03 | Link additional series editions (Banana Belt etc.) | P2 | #8 |

### Deep-Link & Search UX (DL-01 → DL-02)

| ID | Name | Priority | Audit Issue |
|----|------|----------|-------------|
| DL-01 | Deep-link to past-only series shows expanded preview card | P0 | #9 |
| DL-02 | Search for past-only series shows preview summary | P1 | #10 |

### UI Fixes (UF-01 → UF-04)

| ID | Name | Priority | Audit Issue |
|----|------|----------|-------------|
| UF-01 | Startlist label says "Likely contenders based on past editions" | P0 | #11 |
| UF-02 | Remove Ontario from state filter (PNW whitelist) | P1 | #12 |
| UF-03 | Guard register button on races without registration URL | P1 | #13 |
| UF-04 | Increase elevation chart height relative to map | P2 | #14 |

---

## Architecture

### Data Flow: Course-Based Predictor

```
precompute.py → precompute_series_predictions(session, series_id)
  → predict_series_finish_type(session, series_id, category)
      → [existing] weighted frequency of historical time-gap classifications
      → if result is "unknown":
          → predict_finish_type_from_course(session, series_id)
              → query Course table (course_type, total_gain_m, distance_m, climbs_json)
              → query Race table (race_type from series history)
              → apply heuristic rules → FinishType + confidence
  → write to SeriesPrediction (with prediction_source field)
```

The course-based predictor sits **downstream** of the time-gap classifier. When `predict_series_finish_type` returns "unknown" (meaning all historical classifications are UNKNOWN or absent), we fall back to `predict_finish_type_from_course`. This preserves time-gap classifications as the gold standard while filling the gap for the 630 races that lack timing data.

### Key Algorithm: Course-Based Finish Type Predictor

```python
# classification/course_predictor.py

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from raceanalyzer.db.models import CourseType, FinishType, RaceType


@dataclass
class CoursePrediction:
    """Result of course-based finish type prediction."""
    finish_type: FinishType
    confidence: float          # 0.0–1.0
    source: str = "course"     # always "course" for this predictor
    reasoning: str = ""        # human-readable explanation


# --- Thresholds (m/km = meters of climbing per km of distance) ---
#
# These are calibrated from PNW race data and domain knowledge:
#   - Flat crits: <3 m/km (typical crit circuits are pancake-flat)
#   - Flat road:  <5 m/km (e.g., Woodland Park GP, ~2 m/km)
#   - Rolling:    5–12 m/km (e.g., Mutual of Enumclaw, ~8 m/km)
#   - Hilly:      12–20 m/km (e.g., Seward Park hill circuit, ~15 m/km)
#   - Mountainous: >20 m/km (e.g., Banana Belt, ~25 m/km)

M_PER_KM_FLAT = 5.0        # Below this: flat terrain
M_PER_KM_ROLLING_LOW = 5.0  # 5–8: easy rolling
M_PER_KM_ROLLING_HIGH = 12.0  # 8–12: hard rolling
M_PER_KM_HILLY = 20.0       # 12–20: hilly
# Above 20: mountainous

CRIT_DISTANCE_MAX_M = 3000.0  # Crits are typically <3 km per lap
LONG_ROAD_RACE_M = 80000.0    # Races >80 km are more selective
SHORT_ROAD_RACE_M = 40000.0   # Races <40 km favor punchier riders

STEEP_CLIMB_GRADE = 8.0       # Climbs averaging 8%+ are selective
LONG_CLIMB_M = 2000.0         # Climbs >2 km are significant


def predict_finish_type_from_course(
    course_type: Optional[str],
    race_type: Optional[str],
    total_gain_m: Optional[float],
    distance_m: Optional[float],
    climbs_json: Optional[str],
    m_per_km: Optional[float] = None,
) -> Optional[CoursePrediction]:
    """Predict finish type from course characteristics.

    Returns None if insufficient data to make a prediction.
    Uses a decision tree based on race_type, terrain, m/km,
    and climb characteristics.
    """
    # Parse climbs
    climbs = []
    if climbs_json:
        try:
            climbs = json.loads(climbs_json) if isinstance(climbs_json, str) else climbs_json
        except (json.JSONDecodeError, TypeError):
            pass

    # Compute m/km if not provided
    if m_per_km is None and total_gain_m and distance_m and distance_m > 0:
        m_per_km = (total_gain_m / distance_m) * 1000.0

    # --- Rule 1: Time trials and hill climbs ---
    if race_type in ("time_trial", "hill_climb"):
        return CoursePrediction(
            finish_type=FinishType.INDIVIDUAL_TT,
            confidence=0.95,
            reasoning=f"Race type is {race_type}.",
        )

    # --- Rule 2: Criteriums ---
    if race_type == "criterium":
        # Crits are almost always bunch sprints
        if m_per_km is not None and m_per_km > M_PER_KM_ROLLING_HIGH:
            # Hilly crit — unusual, more selective
            return CoursePrediction(
                finish_type=FinishType.REDUCED_SPRINT,
                confidence=0.55,
                reasoning=(
                    f"Criterium with {m_per_km:.0f} m/km — hillier than "
                    "typical, likely a reduced field sprint."
                ),
            )
        return CoursePrediction(
            finish_type=FinishType.BUNCH_SPRINT,
            confidence=0.75,
            reasoning="Criteriums typically end in bunch sprints.",
        )

    # --- Rule 3: Need terrain data for road races ---
    # If we have no course data at all, try race_type alone
    if m_per_km is None and course_type is None:
        if race_type == "road_race":
            # Road race with no course data — weak prediction
            return CoursePrediction(
                finish_type=FinishType.BUNCH_SPRINT,
                confidence=0.40,
                reasoning=(
                    "Road race with no course data — defaulting to "
                    "bunch sprint (most common outcome)."
                ),
            )
        return None  # Not enough data

    # --- Rule 4: Mountainous terrain ---
    if (
        course_type == "mountainous"
        or (m_per_km is not None and m_per_km > M_PER_KM_HILLY)
    ):
        has_steep_climb = any(
            c.get("avg_grade", 0) >= STEEP_CLIMB_GRADE
            for c in climbs
        )
        has_long_climb = any(
            c.get("length_m", 0) >= LONG_CLIMB_M
            for c in climbs
        )

        if has_steep_climb or has_long_climb:
            return CoursePrediction(
                finish_type=FinishType.BREAKAWAY_SELECTIVE,
                confidence=0.70,
                reasoning=(
                    f"Mountainous course ({m_per_km:.0f} m/km) with "
                    f"{'steep' if has_steep_climb else 'long'} climbs "
                    "— the field will likely shatter."
                ),
            )
        return CoursePrediction(
            finish_type=FinishType.GC_SELECTIVE,
            confidence=0.65,
            reasoning=(
                f"Mountainous course ({m_per_km:.0f} m/km) — "
                "expect a selective finish."
            ),
        )

    # --- Rule 5: Hilly terrain ---
    if (
        course_type == "hilly"
        or (m_per_km is not None and m_per_km > M_PER_KM_ROLLING_HIGH)
    ):
        n_climbs = len(climbs)
        has_late_climb = False
        if distance_m and distance_m > 0:
            has_late_climb = any(
                c.get("start_d", 0) / distance_m > 0.6
                for c in climbs
            )

        if has_late_climb and n_climbs >= 2:
            return CoursePrediction(
                finish_type=FinishType.BREAKAWAY_SELECTIVE,
                confidence=0.60,
                reasoning=(
                    f"Hilly course ({m_per_km:.0f} m/km) with "
                    f"{n_climbs} climbs including a late climb — "
                    "likely a selective breakaway finish."
                ),
            )
        if n_climbs >= 3:
            return CoursePrediction(
                finish_type=FinishType.SMALL_GROUP_SPRINT,
                confidence=0.55,
                reasoning=(
                    f"Hilly course ({m_per_km:.0f} m/km) with "
                    f"{n_climbs} climbs — expect a reduced group sprint."
                ),
            )
        return CoursePrediction(
            finish_type=FinishType.REDUCED_SPRINT,
            confidence=0.55,
            reasoning=(
                f"Hilly course ({m_per_km:.0f} m/km) — "
                "the climbs will thin the field."
            ),
        )

    # --- Rule 6: Rolling terrain ---
    if (
        course_type == "rolling"
        or (m_per_km is not None and m_per_km > M_PER_KM_FLAT)
    ):
        is_long = distance_m is not None and distance_m > LONG_ROAD_RACE_M
        if is_long:
            return CoursePrediction(
                finish_type=FinishType.REDUCED_SPRINT,
                confidence=0.55,
                reasoning=(
                    f"Long rolling course ({distance_m/1000:.0f} km, "
                    f"{m_per_km:.0f} m/km) — fatigue will thin the "
                    "sprint group."
                ),
            )
        return CoursePrediction(
            finish_type=FinishType.BUNCH_SPRINT,
            confidence=0.55,
            reasoning=(
                f"Rolling course ({m_per_km:.0f} m/km) — "
                "most rolling races still end in a group sprint."
            ),
        )

    # --- Rule 7: Flat terrain ---
    if course_type == "flat" or (m_per_km is not None and m_per_km <= M_PER_KM_FLAT):
        is_long = distance_m is not None and distance_m > LONG_ROAD_RACE_M
        if is_long:
            return CoursePrediction(
                finish_type=FinishType.BUNCH_SPRINT,
                confidence=0.70,
                reasoning=(
                    f"Long flat course ({distance_m/1000:.0f} km, "
                    f"{m_per_km:.0f} m/km) — flat + long strongly "
                    "favors a bunch sprint."
                ),
            )
        return CoursePrediction(
            finish_type=FinishType.BUNCH_SPRINT,
            confidence=0.65,
            reasoning=(
                f"Flat course ({m_per_km:.0f} m/km) — "
                "expect the pack to stay together."
            ),
        )

    # Fallback: shouldn't reach here if any data is present
    return None
```

### M/km Breakpoint Summary

| M/km Range | Terrain | Typical Finish | Confidence |
|-----------|---------|---------------|------------|
| < 5 | Flat | Bunch Sprint | 0.65–0.70 |
| 5–12 | Rolling | Bunch Sprint or Reduced Sprint (if >80 km) | 0.55 |
| 12–20 | Hilly | Reduced Sprint, Small Group Sprint, or Breakaway Selective | 0.55–0.60 |
| > 20 | Mountainous | GC Selective or Breakaway Selective | 0.65–0.70 |

These thresholds are intentionally conservative (confidence 0.55–0.70) compared to time-gap classifications (0.65–0.90) because course terrain is an indirect signal. A flat course *usually* produces a bunch sprint, but wind, tactics, and field composition can override terrain.

### Design Decisions

**1. Course predictor is a separate module (`classification/course_predictor.py`)**

Keeps the time-gap classifier (`classification/finish_type.py`) clean and unchanged. The course predictor has fundamentally different inputs (terrain data vs gap-grouped results) and different confidence levels. Separate modules make testing easier and prevent accidental coupling.

**2. Predictions pipeline: time-gap first, course fallback**

```python
# In predictions.py — updated predict_series_finish_type
def predict_series_finish_type(session, series_id, category=None):
    result = _existing_time_gap_prediction(session, series_id, category)
    if result["predicted_finish_type"] != "unknown":
        result["prediction_source"] = "time_gap"
        return result

    # Fallback: course-based prediction
    course_result = _course_based_prediction(session, series_id)
    if course_result:
        return {
            "predicted_finish_type": course_result.finish_type.value,
            "confidence": _map_numeric_confidence(course_result.confidence),
            "edition_count": result["edition_count"],
            "distribution": result["distribution"],
            "prediction_source": "course",
            "reasoning": course_result.reasoning,
        }

    result["prediction_source"] = "none"
    return result
```

**3. prediction_source tracking**

Adding a `prediction_source` column to `SeriesPrediction` (values: `"time_gap"`, `"course"`, `"none"`) lets us track provenance without changing the schema of downstream consumers. The feed card rendering doesn't need to know the source — it just checks if `predicted_finish_type` is non-null.

**4. race_type inheritance for upcoming races**

```python
def populate_upcoming_race_types(session):
    """Inherit race_type for upcoming races from series history.

    Logic: if >=80% of historical editions share the same race_type,
    assign it to upcoming races that have race_type=None.
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
        historical = (
            session.query(Race.race_type)
            .filter(
                Race.series_id == race.series_id,
                Race.is_upcoming.is_(False),
                Race.race_type.isnot(None),
            )
            .all()
        )
        if not historical:
            continue

        from collections import Counter
        type_counts = Counter(r[0] for r in historical)
        total = sum(type_counts.values())
        most_common, count = type_counts.most_common(1)[0]
        if count / total >= 0.80:
            race.race_type = most_common
            updated += 1

    session.commit()
    return updated
```

**5. Past-only series deep-link: force-expand the card**

When `?series_id=N` points to a series with no upcoming races, the current code puts it inside a collapsed "Past Races" expander — the user sees a blank page. The fix: when `isolated_series_id` is set and the matching item is past-only, render it as an expanded container card (same as upcoming) instead of hiding it inside the past section.

**6. PNW state whitelist for state filter**

Rather than trying to clean all data anomalies, apply a whitelist of PNW-relevant states:

```python
PNW_STATES = {"WA", "OR", "ID", "BC", "MT"}

def get_available_states(session):
    # ... existing normalization ...
    return sorted(s for s in result if s in PNW_STATES)
```

---

## Implementation

### Phase 1: Course-Based Finish Type Predictor (CP-01, CP-06, ~35%)

**Goal**: Build the course-based predictor module, integrate it as a fallback into `predict_series_finish_type`, and add the `prediction_source` tracking field.

**Tasks:**
- [ ] Create `raceanalyzer/classification/course_predictor.py` with `CoursePrediction` dataclass, threshold constants, and `predict_finish_type_from_course()` function
- [ ] Add `prediction_source` column to `SeriesPrediction` model in `raceanalyzer/db/models.py` (String, nullable, default None)
- [ ] Update `predict_series_finish_type()` in `raceanalyzer/predictions.py` to fall back to course-based prediction when time-gap result is "unknown"
- [ ] Add helper `_course_based_prediction(session, series_id)` in `raceanalyzer/predictions.py` that loads Course data and calls the predictor
- [ ] Add confidence mapping: numeric 0.0–1.0 from course predictor maps to "high" (>0.70), "moderate" (0.50–0.70), "low" (<0.50)
- [ ] Create `tests/test_course_predictor.py` with tests for each rule:
  - Criterium + flat -> BUNCH_SPRINT
  - Criterium + hilly -> REDUCED_SPRINT
  - Road race + mountainous + steep climb -> BREAKAWAY_SELECTIVE
  - Road race + mountainous, no steep climb -> GC_SELECTIVE
  - Road race + hilly + late climb -> BREAKAWAY_SELECTIVE
  - Road race + hilly + 3+ climbs -> SMALL_GROUP_SPRINT
  - Road race + rolling + long -> REDUCED_SPRINT
  - Road race + rolling + short -> BUNCH_SPRINT
  - Road race + flat + long -> BUNCH_SPRINT (higher confidence)
  - Road race + flat -> BUNCH_SPRINT
  - Time trial -> INDIVIDUAL_TT
  - No data -> None
- [ ] Update `tests/test_predictions.py` to test fallback behavior: series with all-UNKNOWN classifications now returns course-based prediction

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/classification/course_predictor.py` | Create | Course-based finish type predictor module |
| `raceanalyzer/db/models.py` | Modify | Add `prediction_source` column to `SeriesPrediction` |
| `raceanalyzer/predictions.py` | Modify | Integrate course predictor fallback into `predict_series_finish_type` |
| `tests/test_course_predictor.py` | Create | Unit tests for each prediction rule |
| `tests/test_predictions.py` | Modify | Integration tests for fallback behavior |

**Exit criteria:**
- `predict_finish_type_from_course()` returns correct FinishType for all rule branches
- `predict_series_finish_type()` returns a non-"unknown" result for series that have Course data but no time-gap classifications
- Time-gap classifications still take priority when present (no regression)
- All 12+ test cases in `test_course_predictor.py` pass
- Course predictions have confidence in the 0.40–0.75 range (lower than time-gap)

---

### Phase 2: Pipeline Integration & Race Type Inheritance (CP-02, CP-03, CP-04, CP-05, DP-01, ~25%)

**Goal**: Wire the course predictor into the pre-computation pipeline so all SeriesPrediction rows benefit from it. Populate `race_type` on upcoming races. Verify that finish type descriptions, similarity scoring, and racer type descriptions now work for previously-UNKNOWN series.

**Tasks:**
- [ ] Update `precompute_series_predictions()` in `raceanalyzer/precompute.py` to store `prediction_source` on each SeriesPrediction row
- [ ] Add `populate_upcoming_race_types()` to `raceanalyzer/precompute.py`
- [ ] Add CLI command `populate-race-types` to `raceanalyzer/cli.py` (or integrate into `compute-predictions`)
- [ ] Run `compute-predictions` against test DB and verify:
  - SeriesPrediction rows for previously-UNKNOWN series now have non-"unknown" `predicted_finish_type`
  - `prediction_source` is "course" for these rows and "time_gap" for existing ones
- [ ] Verify feed cards now show finish type descriptions for course-predicted series (CP-03) — no code change needed, just data flow
- [ ] Verify `compute_similarity()` now finds matches for course-predicted series (CP-04) — no code change needed, just data coverage
- [ ] Verify `racer_type_description()` and `racer_type_long_form()` now return text for course-predicted series (CP-05) — no code change needed
- [ ] Add more course_type → finish_type combinations to `RACER_TYPE_DESCRIPTIONS` in `predictions.py` if needed (e.g., mountainous + breakaway_selective)
- [ ] Test: `test_precompute.py` — verify pipeline produces course-based predictions for series with Course data but no time-gap classifications
- [ ] Test: verify `racer_type_description` coverage for all course-predicted finish types

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/precompute.py` | Modify | Store prediction_source; add populate_upcoming_race_types |
| `raceanalyzer/cli.py` | Modify | Add populate-race-types command or integrate into compute-predictions |
| `raceanalyzer/predictions.py` | Modify | Expand RACER_TYPE_DESCRIPTIONS with new terrain+finish combinations |
| `tests/test_precompute.py` | Modify | Test course-based predictions in pipeline |
| `tests/test_predictions.py` | Modify | Test racer type description coverage |

**Exit criteria:**
- Running `compute-predictions` increases non-UNKNOWN finish type coverage from 55% to 80%+
- All 18 upcoming races have `race_type` populated (inherited from series history)
- `prediction_source` column correctly tracks "time_gap" vs "course" provenance
- Feed cards for previously-blank series now show finish type description, racer type, and find similar races
- `RACER_TYPE_DESCRIPTIONS` covers all terrain+finish combinations the course predictor can produce

---

### Phase 3: Deep-Link & Search UX for Past-Only Series (DL-01, DL-02, ~15%)

**Goal**: When a user arrives via a shared link (`?series_id=N`) to a series with no upcoming races, show the full preview card expanded instead of an empty page with a collapsed expander. Similarly, when searching returns only past series, show a preview summary instead of hiding results inside "Past Races (N)".

**Tasks:**
- [ ] In `raceanalyzer/ui/pages/feed.py`, when `isolated_series_id` is set:
  - Find the matching item from `all_items`
  - If the item is past-only (`not item["is_upcoming"]`), render it as an expanded container card at the top level (not inside the "Past Races" expander)
  - Show "Show all races" button above the card
- [ ] In `raceanalyzer/ui/pages/feed.py`, when `search_query` is set and all results are past-only:
  - Instead of putting everything inside collapsed "Past Races" expander, render the first 3 results as expanded container cards
  - Add a caption: "Showing past editions for '{search_query}'"
  - Keep remaining results in a collapsed expander if >3 results
- [ ] Tests: deep-link to past-only series renders expanded card; search with all-past results shows preview

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/ui/pages/feed.py` | Modify | Force-expand past-only series on deep-link; show previews on all-past search |

**Exit criteria:**
- `/?series_id=9` (Gorge Roubaix, past-only) shows an expanded card with name, location, terrain, finish type, and Tier 2 content
- Searching "Banana Belt" shows preview cards for the matching series, not just a collapsed expander
- Upcoming series deep-links and searches continue to work as before (no regression)

---

### Phase 4: Startlist Label & Minor UI Fixes (UF-01, UF-02, UF-03, UF-04, ~15%)

**Goal**: Fix the remaining UI issues: startlist label contradiction, Ontario in state filter, register button guarding, and elevation chart sizing.

**Tasks:**
- [ ] **UF-01 — Startlist label**: In the race preview page or component that renders the startlist, change the caption from "Based on past editions (no startlist available)" to "Likely contenders based on past editions" when the displayed riders come from historical fallback (Tier 2 in `predict_contenders`)
  - Find where the startlist source label is rendered (likely in `ui/pages/race_preview.py` or `ui/components.py`)
  - Check the `source` field of the contenders DataFrame: if "series_history" or "category", use the new label; if "startlist", use "Registered riders"
- [ ] **UF-02 — Ontario in state filter**: Add PNW whitelist to `get_available_states()` in `raceanalyzer/queries.py`:
  ```python
  PNW_STATES = {"WA", "OR", "ID", "BC", "MT"}
  # After normalization, filter to PNW only:
  return sorted(s for s in result if s in PNW_STATES)
  ```
- [ ] **UF-03 — Register button guard**: Verify that the register button in `_render_container_card()` in `feed.py` is already guarded by `item.get("is_upcoming") and item.get("registration_url")`. Check the existing code — this may already be correct per the audit note ("the card code checks... but worth verifying all upcoming races actually have URLs"). If any upcoming race has `registration_url=None`, the button correctly won't render.
- [ ] **UF-04 — Elevation chart sizing**: In the course profile rendering code (likely `raceanalyzer/ui/pages/race_preview.py` or the elevation module), increase the Plotly chart height from ~250px to ~350px and reduce the Folium map height from ~400px to ~300px. This inverts the ratio so the elevation profile (the more useful element for course study) gets more visual space.
- [ ] Tests: state filter no longer includes "Ontario"; startlist label changes based on source

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/queries.py` | Modify | PNW whitelist in `get_available_states()` |
| `raceanalyzer/ui/pages/race_preview.py` | Modify | Startlist label fix; elevation chart sizing |
| `raceanalyzer/ui/components.py` | Modify | Startlist label based on source field (if rendered here) |
| `tests/test_queries.py` | Modify | Test state filter excludes non-PNW states |

**Exit criteria:**
- Startlist section shows "Likely contenders based on past editions" when data comes from historical fallback
- Startlist section shows "Registered riders" when data comes from an actual startlist
- State filter shows only WA, OR, ID, BC, MT (no Ontario or other non-PNW states)
- Register button does not render on cards where `registration_url` is null
- Elevation chart is taller than the map on the course profile view

---

### Phase 5: Data Quality Improvements (DP-02, DP-03, ~10%)

**Goal**: Expand RWGPS route coverage and link additional series editions to improve data quality for the course-based predictor and drop rate calculations.

**Tasks:**
- [ ] **DP-02 — More RWGPS linking**: Run the existing RWGPS route matching command (`raceanalyzer match-routes` or similar) against series that currently lack Course rows. Document which series gained routes and log the new coverage numbers.
- [ ] **DP-03 — More series editions**: Investigate why Banana Belt has only 1 edition linked despite being a well-known multi-year series. Check if:
  - The series matching algorithm (`normalized_name` comparison) is too strict
  - There are unlinked races in the DB that should be matched
  - Additional scraping is needed
- [ ] Run `compute-predictions` after linking new data to update SeriesPrediction rows
- [ ] Document final coverage metrics:
  - Number of series with Course data (before vs after)
  - Number of series with >1 edition (before vs after)
  - Finish type coverage percentage (before vs after)

**Files:**

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/cli.py` | Possible modify | If match-routes needs improvements |
| `raceanalyzer/series.py` | Possible modify | If series matching needs loosening |

**Exit criteria:**
- At least 5 additional series gain Course rows from RWGPS linking
- At least 2 additional series gain multiple linked editions
- Finish type coverage reaches 80%+ of races with at least one non-UNKNOWN classification
- Banana Belt shows >1 edition with a reasonable drop rate

---

## Files Summary

| File | Action | Phase | Purpose |
|------|--------|-------|---------|
| `raceanalyzer/classification/course_predictor.py` | Create | 1 | Course-based finish type predictor |
| `raceanalyzer/db/models.py` | Modify | 1 | Add `prediction_source` to `SeriesPrediction` |
| `raceanalyzer/predictions.py` | Modify | 1, 2 | Integrate course fallback; expand racer type descriptions |
| `raceanalyzer/precompute.py` | Modify | 2 | Store prediction_source; add `populate_upcoming_race_types` |
| `raceanalyzer/cli.py` | Modify | 2 | Integrate race_type population into compute-predictions |
| `raceanalyzer/queries.py` | Modify | 4 | PNW state whitelist |
| `raceanalyzer/ui/pages/feed.py` | Modify | 3 | Force-expand past-only deep-links; preview on all-past search |
| `raceanalyzer/ui/pages/race_preview.py` | Modify | 4 | Startlist label; elevation chart sizing |
| `raceanalyzer/ui/components.py` | Modify | 4 | Startlist label based on source field |
| `raceanalyzer/series.py` | Possible modify | 5 | Series matching improvements |
| `tests/test_course_predictor.py` | Create | 1 | Unit tests for course predictor rules |
| `tests/test_predictions.py` | Modify | 1, 2 | Fallback behavior; racer type coverage |
| `tests/test_precompute.py` | Modify | 2 | Pipeline integration tests |
| `tests/test_queries.py` | Modify | 4 | State filter whitelist test |

---

## Definition of Done

### Course-Based Prediction (CP)
- [ ] `predict_finish_type_from_course()` produces correct FinishType for all terrain/race_type combinations documented in the M/km breakpoint table
- [ ] `predict_series_finish_type()` falls back to course-based prediction when time-gap result is "unknown"
- [ ] Time-gap classifications still take priority when present (no regression)
- [ ] `prediction_source` column is populated for all SeriesPrediction rows ("time_gap", "course", or "none")
- [ ] Finish type coverage increases from 55% to 80%+ of races with at least one non-UNKNOWN classification
- [ ] Feed cards show plain-English finish type description for course-predicted series
- [ ] "Who does well here?" paragraph appears for course-predicted series with course data
- [ ] Similar races section finds matches for course-predicted series

### Data Pipeline (DP)
- [ ] All 18 upcoming races have `race_type` populated (inherited from series history at 80% threshold)
- [ ] `populate_upcoming_race_types()` is callable from CLI and integrated into compute-predictions workflow
- [ ] RWGPS route coverage expanded (at least 5 additional series)
- [ ] Banana Belt shows >1 linked edition

### Deep-Link & Search UX (DL)
- [ ] `/?series_id=N` for a past-only series shows an expanded card with full preview content, not a collapsed expander
- [ ] Searching for a term that only matches past series shows preview cards, not just "Past Races (N)"
- [ ] Existing deep-links and searches for upcoming series continue to work

### UI Fixes (UF)
- [ ] Startlist label says "Likely contenders based on past editions" for historical fallback data
- [ ] Startlist label says "Registered riders" for actual startlist data
- [ ] State filter shows only PNW states (WA, OR, ID, BC, MT)
- [ ] Register button does not render when `registration_url` is null
- [ ] Elevation chart height is ~350px, map height is ~300px (chart larger than map)

### Quality
- [ ] `ruff check .` passes
- [ ] `pytest` passes with no regressions
- [ ] New test files: `tests/test_course_predictor.py`
- [ ] Updated test files: `tests/test_predictions.py`, `tests/test_precompute.py`, `tests/test_queries.py`
- [ ] Feed load time remains <1s cold / <200ms warm

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Course predictor accuracy** — heuristic thresholds (m/km breakpoints) may misclassify edge cases | Medium | Medium | Use conservative confidence levels (0.40–0.75); predictor is a supplement, not a replacement. Add `prediction_source` tracking so we can audit and tune later. Include "reasoning" field for debuggability. |
| **Threshold tuning** — the 5/12/20 m/km breakpoints are informed estimates, not validated against labeled data | Medium | Low | Breakpoints are based on well-known cycling heuristics (flat crits sprint, mountains shatter). Confidence levels reflect uncertainty. Can tune in Sprint 013 using `UserLabel` table feedback. |
| **Race type inheritance false positive** — a series that changed from criterium to road race would inherit the wrong type for the upcoming edition | Low | Medium | 80% threshold guards against this: if 4 out of 5 editions are crits and 1 is a road race, it still inherits criterium. If the split is 60/40, no inheritance occurs. |
| **Schema migration** — adding `prediction_source` column to `SeriesPrediction` | Low | Low | `Base.metadata.create_all()` handles new columns on existing tables in SQLite (adds column). For PostgreSQL, need an `ALTER TABLE` or migration script. |
| **Past-only deep-link UX** — force-expanding past cards may look different from upcoming cards (missing countdown, registration) | Low | Low | Container card already handles graceful degradation: missing fields (countdown, registration URL) are simply not rendered. Past cards will show "last raced {date}" instead. |
| **PNW whitelist too restrictive** — if a race legitimately occurs in a non-PNW state (e.g., NV for a cross-state event) | Low | Low | The whitelist includes MT as a border state. If expansion is needed, it's a one-line change to add more states. |
| **RWGPS linking coverage** — Phase 5 depends on external data availability | Medium | Low | Phase 5 is a best-effort data quality improvement. The core predictor (Phases 1-2) works with whatever Course data exists today. |

---

## Security Considerations

- **SQL injection**: All new queries use SQLAlchemy parameterized bindings. The `populate_upcoming_race_types()` function uses ORM-level updates, not raw SQL.
- **XSS via `prediction_source`**: The `prediction_source` field contains only controlled values ("time_gap", "course", "none") — not user input. No HTML escaping needed for this field.
- **State whitelist**: The `PNW_STATES` set is hardcoded, not derived from user input. The existing `normalize_state()` function already sanitizes raw state values before comparison.
- **Course predictor inputs**: All inputs to `predict_finish_type_from_course()` come from the database (Course table, Race table), not from user input. No injection risk.

---

## Dependencies

- **No new Python dependencies** — uses existing: SQLAlchemy, Streamlit, Plotly, Folium, Click, pytest
- **Sprint 008**: Course table, RWGPS route matching, elevation extraction, course_type classification, climbs_json
- **Sprint 009**: Startlist data (source tracking for label fix)
- **Sprint 010**: Feed page, deep linking, URL state persistence
- **Sprint 011**: SeriesPrediction table, pre-computation pipeline, batch feed queries, container cards, PerfTimer
- **Commit a15343c**: UX audit fixes (duplicate location, blank elevation chart, filter exclusion, state normalization)

---

## Open Questions

1. **Should course predictions apply to individual race categories or only series-level?** The time-gap classifier works per-category (different categories can have different finish types). Course terrain is the same for all categories, but race dynamics differ (Cat 5 crits are more chaotic). Recommendation: apply the same course prediction to all categories within a series, but note that confidence should be lower for lower categories.

2. **Should we log course predictor reasoning to the DB?** The `reasoning` field in `CoursePrediction` is useful for debugging but adds a text column to `SeriesPrediction`. Recommendation: store it as a new `prediction_reasoning` Text column — it's cheap storage and valuable for auditing threshold choices.

3. **How aggressively should we populate race_type from series history?** The 80% threshold is conservative. An alternative is to use the most common race type if there are at least 3 editions. Recommendation: start with 80%; lower to 67% if too many upcoming races remain untyped.

4. **Should the course predictor also consider the number of laps for criteriums?** Multi-lap criteriums on a hilly circuit might be more selective than single-lap road races. We don't currently track lap count. Recommendation: defer to Sprint 013 — the crit=bunch_sprint rule is correct for >90% of PNW crits.

5. **For the deep-link past-only fix, should we auto-expand Tier 2 content or just show Tier 1?** Showing Tier 1 (always-visible summary) is the minimum viable fix. Auto-expanding Tier 2 (narrative, climbs, editions) provides a richer experience for shared links. Recommendation: auto-expand Tier 2 for deep-linked series (both past and upcoming), since the user specifically navigated to this series.

6. **Should the PNW state whitelist be configurable?** Hardcoding `{"WA", "OR", "ID", "BC", "MT"}` is simple but inflexible. Recommendation: hardcode for now; if the app expands beyond PNW, move to a config setting.
