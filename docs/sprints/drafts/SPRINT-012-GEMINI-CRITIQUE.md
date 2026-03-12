# Sprint 012 Cross-Critique: Claude Draft & Codex Draft

## Claude Draft Critique

### 1. Strengths

- **Comprehensive algorithm specification.** The full Python implementation of `predict_finish_type_from_course()` is the most valuable part of this draft. Every rule branch is enumerated with concrete threshold values, confidence levels, and human-readable reasoning strings. This eliminates ambiguity during implementation.
- **Climb-aware predictions.** The decision tree uses `climbs_json` data (steep climbs, long climbs, late climbs) to distinguish between BREAKAWAY_SELECTIVE and GC_SELECTIVE on mountainous courses, and between BREAKAWAY_SELECTIVE and SMALL_GROUP_SPRINT on hilly courses. This produces richer, more accurate predictions than a flat lookup table.
- **Explicit RACER_TYPE_DESCRIPTIONS gap awareness.** Phase 2 explicitly calls out the need to expand the `RACER_TYPE_DESCRIPTIONS` table for new course+finish combinations, and includes a task to verify coverage. This is critical because the existing table (12 entries) does not cover several combinations the course predictor will produce.
- **Deep-link fix is well-specified.** The Phase 3 design for past-only series deep-link is clear: detect the past-only case, render as expanded container card, show "Show all races" button. The search fix (first 3 results expanded, remainder in expander) is a thoughtful UX compromise.
- **Security section is thorough.** Covers SQL injection, XSS vectors, and input sanitization for all new code paths.

### 2. Weaknesses

- **Modifying `predictions.py` to call the course predictor is architecturally questionable.** The draft places the fallback logic inside `predict_series_finish_type()`, which currently returns a dict with string-typed fields. The course predictor returns a `CoursePrediction` dataclass with enum-typed fields. The conversion layer (`_course_based_prediction` and `_map_numeric_confidence`) adds complexity to `predictions.py`, which the Codex draft avoids by keeping this logic in `precompute.py`.
- **The decision tree has overlapping conditions.** Rule 4 (mountainous) triggers on `m_per_km > 20` OR `course_type == "mountainous"`. Rule 5 (hilly) triggers on `m_per_km > 12` OR `course_type == "hilly"`. If `course_type == "hilly"` but `m_per_km == 25` (disagreement between classified course_type and raw metric), both rules would match. The function relies on rule ordering (Rule 4 checked first) to resolve this, but the reasoning string would say "Hilly course (25 m/km)" which is misleading. There is no guard for course_type/m_per_km disagreement.
- **80% threshold for race_type inheritance is too conservative given the data.** The intent document notes only 18 upcoming races need race_type. Many PNW series have 2-3 editions. An 80% threshold on a 3-edition series requires 3/3 agreement. The Codex draft uses 67% (2/3), which is more practical for small sample sizes.
- **Phase 5 (data quality) is underspecified.** Tasks say "Investigate why Banana Belt has only 1 edition" and "Document final coverage metrics" but provide no concrete implementation steps. This phase will likely slip or be handwaved.
- **The draft proposes modifying `predictions.py` to also hold the course fallback, which splits the prediction logic across two modules** (`classification/course_predictor.py` for the algorithm and `predictions.py` for the integration). The precompute pipeline already orchestrates predictions; adding another orchestration point in `predictions.py` creates two places where prediction precedence is managed.

### 3. Risk Analysis Gaps

- **No risk identified for `m_per_km` being None when `course_type` is set.** The Course table may have `course_type` classified (from name heuristics or manual assignment) but `total_gain_m` or `distance_m` as NULL, making `m_per_km` uncomputable. The algorithm handles this (falls through to course_type-only rules), but the risk table doesn't acknowledge this data quality scenario.
- **No risk for the `generate_narrative()` function.** When prediction_source is "course", the narrative says "Based on N previous editions, this race typically ends in a {finish_type}" -- but for course-predicted series with zero non-UNKNOWN historical classifications, `edition_count` might be nonzero (editions exist, they just have UNKNOWN finish types). The narrative would falsely imply that the prediction comes from historical outcomes when it actually comes from terrain analysis.
- **No risk for Streamlit cache invalidation.** Adding `prediction_source` to `SeriesPrediction` and changing feed card rendering means the 5-min TTL cache (`_cached_states`, `get_feed_items_batch`) will serve stale data for up to 5 minutes after running `compute-predictions`. This is minor but not acknowledged.

### 4. Missing Edge Cases

- **Series with multiple courses across editions.** If a series changed venues (different RWGPS routes in different years), the Course table may have data from one edition but not the current venue. The predictor would use stale course data. Neither draft addresses how Course data is selected when multiple Course rows exist for a series.
- **The `m_per_km` formatting in reasoning strings will crash when `m_per_km` is None.** Rule 7 (flat terrain) can trigger when `course_type == "flat"` even if `m_per_km is None`, but the reasoning string uses `f"{m_per_km:.0f}"` which will throw `TypeError` on None. The same issue exists in Rules 4, 5, and 6.
- **Road race without course data returns BUNCH_SPRINT at 0.40 confidence (Rule 3).** This is a bold default -- many PNW road races are hilly. The intent document's Open Question #7 asks whether this should be done, but the draft just does it without flagging the controversy.
- **hill_climb mapped to INDIVIDUAL_TT (Rule 1).** Hill climbs are not time trials -- they are mass-start events where the field separates on the climb. GC_SELECTIVE or BREAKAWAY_SELECTIVE would be more accurate. The Codex draft maps hill_climb to GC_SELECTIVE, which is better.

### 5. Definition of Done Completeness

- **Missing criterion for narrative correctness.** The DoD says "Feed cards show plain-English finish type description for course-predicted series" but does not verify that the `generate_narrative()` output is accurate when the prediction source is "course" rather than "time_gap". The narrative should distinguish between "Historically ends in..." and "Course profile suggests...".
- **Missing criterion for confidence level display.** Course-predicted confidence values (0.40-0.75) map to "moderate" or "low" via the existing string mapping. The DoD should verify that feed cards display an appropriate confidence qualifier (not just the finish type) for lower-confidence predictions.
- **No acceptance criterion for the `prediction_reasoning` column** mentioned in Open Question #2. If reasoning is stored, it should be verifiable; if not stored, the question should be resolved in the draft, not left open.

### 6. Architecture Concerns

- **The course predictor function takes raw strings instead of enums.** `predict_finish_type_from_course(course_type: Optional[str], race_type: Optional[str], ...)` compares against string literals like `"criterium"` and `"mountainous"`. The codebase has `CourseType` and `RaceType` enums. Using raw strings bypasses type safety and risks silent mismatches if enum values change.
- **The `prediction_source` column as a plain String is fragile.** The values ("time_gap", "course", "none") are not enforced at the database level. Using an enum or check constraint would prevent invalid values from creeping in.
- **Adding the fallback inside `predict_series_finish_type()` changes its contract.** Callers currently expect the function to return purely time-gap-based results. Adding a course fallback means callers cannot distinguish whether a "moderate" confidence result came from 3 editions of data or from terrain heuristics, unless they also check `prediction_source`. This is a subtle API contract change that could mislead downstream consumers that don't check the new field.

---

## Codex Draft Critique

### 1. Strengths

- **Lookup table is exhaustively testable.** The two-tier design (RACE_TYPE_DEFAULTS + COURSE_RACE_TYPE_TABLE) means every possible prediction is a row in a table. Tests can iterate over the table and verify each row. This is simpler to audit and maintain than a decision tree with continuous thresholds.
- **Confidence ceiling of 0.75 is explicitly enforced.** The draft specifies this as a hard cap verified by tests. This prevents course predictions from ever outranking time-gap predictions in downstream consumers that sort by confidence.
- **road_race without course data returns None, not a guess.** This is the correct conservative choice. A road race could be anything from a flat circuit to a mountain stage. Predicting BUNCH_SPRINT at 0.40 (as the Claude draft does) is worse than admitting ignorance.
- **67% race_type inheritance threshold with minimum 2 editions.** This is better calibrated than Claude's 80%. A 2-edition series with matching types (100%) inherits; a 3-edition series with 2/3 matching (67%) inherits. The minimum-2 guard prevents single-edition inheritance. The draft includes explicit edge case tests for this.
- **Clean separation of concerns: predictor in `classification/`, orchestration in `precompute.py`.** The draft explicitly states `predictions.py` is NOT modified. The course predictor is a pure function; the precompute pipeline decides when to call it. This avoids the dual-orchestration problem in the Claude draft.
- **Phase structure is incrementally valuable.** Phase 1 (pure function, no DB) -> Phase 2 (pipeline integration) -> Phase 3 (race_type inheritance) -> Phase 4 (UI fixes). Each phase produces independently testable output.

### 2. Weaknesses

- **The lookup table sacrifices prediction quality.** By discretizing into (course_type, race_type) pairs, the Codex predictor loses the ability to use climb characteristics. A mountainous course with a steep 2km climb at the finish is very different from a mountainous course with gradual climbing throughout. The Claude draft's climb-aware rules (steep/long/late climb modifiers) produce meaningfully different predictions for these scenarios. The lookup table maps both to the same finish type.
- **No reasoning strings in the lookup table.** The `COURSE_RACE_TYPE_TABLE` maps to `(finish_type, confidence)` tuples. The `CoursePrediction` dataclass has a `reasoning` field, but the draft doesn't show how reasoning is generated from table lookups. Without clear reasoning, debugging incorrect predictions requires reading the source code rather than the prediction output.
- **Phase 3 is oddly separated from Phase 2.** Phase 2 creates `populate_upcoming_race_types()` in precompute.py, but Phase 3 "verifies" it works and also adds the PNW state filter fix. The state filter fix (Issue #12) has nothing to do with race_type inheritance. This phase is a grab bag rather than a coherent unit.
- **Missing explicit handling of the `RACER_TYPE_DESCRIPTIONS` gap.** The draft's files summary says `predictions.py: No change`. But the existing `RACER_TYPE_DESCRIPTIONS` table has 12 entries covering only certain (course_type, finish_type) pairs. The course predictor will produce new combinations. For example:
  - `("mountainous", "breakaway_selective")` -- not in the table
  - `("hilly", "breakaway")` -- IS in the table
  - `("rolling", "reduced_sprint")` -- IS in the table
  - `("flat", "bunch_sprint")` -- IS in the table
  - `("hilly", "small_group_sprint")` -- not in the table
  - `("mountainous", "gc_selective")` -- IS in the table
  - `("rolling", "bunch_sprint")` -- IS in the table

  The missing entries mean `racer_type_description()` will return None for some course-predicted series, leaving the "Who does well here?" section blank. The Claude draft catches this; the Codex draft does not.
- **UX-04 (Ontario) lists Alberta ("AB") in the PNW allowlist.** The intent document scopes the project to "WA, OR, ID, BC". Alberta is not PNW. Adding AB without justification inflates the state filter. The Claude draft uses `{"WA", "OR", "ID", "BC", "MT"}` which matches the project scope plus Montana as a border state.
- **The Codex draft puts `infer_race_type_from_series()` in `queries.py`.** This function mutates nothing (it's a read query), so `queries.py` is defensible. But `populate_upcoming_race_types()` in `precompute.py` calls it and writes back to the DB. The Claude draft puts both in `precompute.py`, keeping all write operations in one module. The Codex approach spreads the race_type inheritance logic across two files.

### 3. Risk Analysis Gaps

- **No risk identified for the "breakaway" finish type used in the lookup table.** The COURSE_RACE_TYPE_TABLE maps `("hilly", "road_race")` to `"breakaway"` and `("hilly", None)` to `"breakaway"`. But looking at `RACER_TYPE_DESCRIPTIONS`, the entry `("hilly", "breakaway")` exists with the text "Pure climbers and aggressive attackers dominate." However, the `FinishType` enum has both `BREAKAWAY` and `BREAKAWAY_SELECTIVE` as separate values. The lookup table uses bare string "breakaway" for hilly courses but "breakaway_selective" for mountainous. The distinction between these two finish types in terms of what riders actually experience is subtle, and the risk of user confusion is not addressed.
- **No risk for lookup table row coverage decay.** As the project adds new race_type or course_type values (e.g., "gravel" as a race_type), the lookup table silently produces no prediction (falls through to race_type_only or None). There is no warning mechanism when a new enum value is added but the lookup table is not updated.
- **No risk for schema migration on production PostgreSQL.** The draft mentions `ALTER TABLE` is needed but doesn't specify how. The Claude draft has the same gap but at least acknowledges it in the risk table.

### 4. Missing Edge Cases

- **Confidence adjustment interactions can produce unexpected values.** The draft specifies `+0.05 if m_per_km confirms course_type bin`, `+0.05 if climb_count >= 3`, `-0.10 if distance < 20km`, then `cap at 0.75`. But the base table already has values up to 0.85 (`("flat", "criterium"): 0.85`). After the 0.75 cap, this becomes 0.75. But with the short-race penalty, `("flat", "criterium")` for a 15km race would be `0.85 - 0.10 = 0.75`, capped at 0.75 = 0.75. Is a short flat criterium really 0.75 confidence for bunch_sprint? Short crits can be chaotic. The confidence adjustments need more careful interaction analysis.
- **`("mountainous", "criterium")` is missing from the lookup table.** Open Question #1 acknowledges this. But the fallback path is problematic: it goes to `RACE_TYPE_DEFAULTS["criterium"] = ("bunch_sprint", 0.70)`. A mountainous criterium predicted as bunch_sprint at 0.70 confidence is likely wrong. The fallback should at least lower the confidence for this combination.
- **No handling of `course_type = "unknown"`.** The Course table has a `CourseType.UNKNOWN` value. The lookup table has no entries with "unknown" as the course_type key. This means series with unclassified courses fall through to race_type_only. This is probably correct behavior but should be documented as a conscious choice.
- **The deep-link fix (UX-01) code snippet returns early after rendering isolated items.** This means the "Show more" pagination button is never rendered for isolated views. If a deep-linked past-only series has Tier 2 content that's very long, there's no way to paginate. This is probably fine (it's a single card) but worth noting.

### 5. Definition of Done Completeness

- **Missing criterion for `RACER_TYPE_DESCRIPTIONS` coverage.** The DoD lists "Populate 'Who does well here?' from course predictions (CP-04)" but has no acceptance criterion verifying that `racer_type_description()` returns non-None for all finish types the course predictor can produce. If the lookup table produces `("hilly", "small_group_sprint")` but `RACER_TYPE_DESCRIPTIONS` lacks that key, the user sees nothing.
- **Missing criterion for narrative language.** Neither the Claude nor Codex DoD specifies how the `generate_narrative()` function should behave differently for course-predicted vs time-gap-predicted series. The current narrative says "Based on N previous editions, this race typically ends in a {finish_type}" which is misleading when the prediction came from terrain analysis, not historical results. The DoD should require source-aware language.
- **No criterion for the confidence adjustment logic.** The DoD says "Confidence never exceeds 0.75 (verified by test)" but doesn't verify that the adjustments produce sensible values across all table rows. A test that iterates all rows with various adjustment combinations would be more robust.
- **"Visual verification" for UX-06 (elevation chart sizing) is not automatable.** The DoD should specify the pixel values or ratio so it can be verified in code review rather than requiring a manual visual check.

### 6. Architecture Concerns

- **Lookup table approach creates a maintenance burden.** Every new (course_type, race_type) combination requires adding a row. The Claude draft's decision tree automatically handles new combinations through threshold logic. With 4 course types and 6+ race types, the lookup table needs 24+ entries for full coverage. The current table has 12 entries, meaning half the input space produces no Tier 2 prediction.
- **Two-tier fallback within the predictor is redundant with the pipeline fallback.** The course predictor has Tier 1 (race_type only) and Tier 2 (course_type + race_type). The precompute pipeline has its own fallback: time-gap -> course predictor -> unknown. This creates a 3-level cascade that's harder to reason about than the Claude draft's 2-level cascade (time-gap -> course predictor with internal logic).
- **`prediction_source` distinguishes "course_profile" from "race_type_only".** This is finer-grained than the Claude draft's single "course" value. The extra granularity is useful for auditing but adds complexity: downstream consumers (UI, similarity scoring) must handle three non-null values instead of two. If the UI wants to show softer language for race_type_only predictions (as suggested in Open Question #2), this distinction is necessary. But it should be a design decision, not an open question.
- **The elevation chart fix targets `raceanalyzer/elevation.py` rather than `race_preview.py`.** The Plotly chart height is likely set where the chart is rendered (in the UI layer), not where the data is processed (in `elevation.py`). Changing it in `elevation.py` would affect all consumers of that module, not just the preview page. The Claude draft correctly targets `race_preview.py`.

---

## Cross-Cutting Concerns (Both Drafts)

### RACER_TYPE_DESCRIPTIONS Table Coverage

The existing table in `predictions.py` has 12 entries. The course predictor (both drafts) can produce the following (course_type, finish_type) combinations:

| course_type | finish_type | In table? |
|------------|-------------|-----------|
| flat | bunch_sprint | Yes |
| flat | breakaway | Yes |
| flat | small_group_sprint | Yes |
| flat | reduced_sprint | Yes |
| rolling | bunch_sprint | Yes |
| rolling | reduced_sprint | Yes |
| rolling | breakaway | Yes |
| rolling | small_group_sprint | Yes |
| hilly | breakaway | Yes |
| hilly | breakaway_selective | **No** |
| hilly | small_group_sprint | **No** |
| hilly | reduced_sprint | Yes |
| hilly | gc_selective | Yes |
| mountainous | gc_selective | Yes |
| mountainous | breakaway_selective | **No** |

Three combinations are missing. The Claude draft acknowledges this in Phase 2 ("Add more course_type -> finish_type combinations to RACER_TYPE_DESCRIPTIONS if needed"). The Codex draft does not mention it. Both drafts should add these entries as an explicit task with proposed text.

### Narrative Source Awareness

Neither draft addresses the `generate_narrative()` function's behavior when `prediction_source` is "course". The current code at line 635 says: "Based on N previous editions, this race typically ends in a {finish_type}." For a course-predicted series, this is misleading -- the prediction comes from terrain, not from observed historical outcomes. The `edition_count` might be nonzero (the series has editions, they just all have UNKNOWN finish types), making the narrative factually incorrect.

Both drafts should add a task to modify `generate_narrative()` to accept a `prediction_source` parameter and adjust phrasing:
- `time_gap`: "Based on N previous editions, this race typically ends in a {ft}."
- `course`: "The course profile suggests a {ft}."
- `race_type_only`: "As a {race_type}, this race typically ends in a {ft}."

### Past-Only Deep-Link: Tier 2 Auto-Expansion

Both drafts propose rendering past-only deep-linked series as expanded container cards. However, the current `_render_container_card` function in `feed.py` (line 276) loads Tier 2 content via `queries.get_feed_item_detail()` only when `is_expanded` is True. The `expanded` parameter is passed as True for deep-linked upcoming items (line 138), but the past-only items go through the "Past Races" expander path (lines 124-132) which never passes `expanded=True`.

The fix needs to ensure that past-only deep-linked items are routed to the non-expander rendering path AND that `expanded=True` is set. The Claude draft's Phase 3 description covers this but doesn't show the specific code change in `feed.py` needed at lines 119-142. The Codex draft shows a code snippet but it bypasses month grouping entirely (`return` after rendering), which means the "Show all races" button (lines 101-105) would need to be rendered before the bypass.

### PNW State Whitelist Discrepancy

The Claude draft uses `{"WA", "OR", "ID", "BC", "MT"}`. The Codex draft uses `{"WA", "OR", "ID", "BC", "AB", "MT"}`. The intent document says the project covers "WA, OR, ID, BC". Montana is a reasonable border inclusion (Missoula hosts some PNW-adjacent races). Alberta is a stretch -- Calgary and Edmonton are not PNW cycling markets. The drafts should agree on the whitelist, and the choice should be justified with data (how many races in the DB are in MT vs AB).

### hill_climb Finish Type Mapping

The Claude draft maps hill_climb to INDIVIDUAL_TT (Rule 1, same as time_trial). The Codex draft maps hill_climb to GC_SELECTIVE (RACE_TYPE_DEFAULTS table). Hill climbs are mass-start events where the strongest climber wins, not individual time trials. The Codex mapping is more accurate. The Claude draft should use GC_SELECTIVE or BREAKAWAY_SELECTIVE for hill_climb.
