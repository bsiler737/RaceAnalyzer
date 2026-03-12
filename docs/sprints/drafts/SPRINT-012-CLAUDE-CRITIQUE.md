# Sprint 012 Cross-Critique: Codex Draft vs Gemini Draft

## Codex Draft Critique

### 1. Strengths

- **Exceptional clarity of engineering rationale.** The overview explains *why* the approach is incremental, *why* testability matters, and *why* a lookup table was chosen over a decision tree. Each design decision includes explicit tradeoffs. This is the strongest aspect of the draft.
- **Pure-function predictor design.** Isolating the course predictor as a zero-dependency pure function (`predict_finish_type_from_course`) is exactly right. It mirrors the existing `classify_finish_type()` pattern in `classification/finish_type.py` where the classifier is a pure function and the pipeline decides when to call it.
- **Explicit edge case enumeration for race type inheritance.** The threshold decision section (lines 153-178) lists six concrete test cases for `infer_race_type_from_series()` with expected outcomes. This is directly implementable.
- **Conservative confidence ceiling (0.75).** Lower than Gemini's 0.80, which better reflects the inherent uncertainty of course-based heuristics. The reasoning that time-gap minimum confidence is 0.50 (so precedence is guaranteed) is correct given the code in `classification/finish_type.py` where the lowest non-UNKNOWN confidence is 0.50 (MIXED).
- **Clean phase separation.** Phases 1-4 have strict dependency ordering and each produces independently testable output. Phase 1 requires zero database fixtures, which is a significant testing advantage.
- **Addresses all 13 audit issues.** Every issue from the intent document is mapped to a use case with a clear fix.

### 2. Weaknesses

- **Missing FinishType enum values in the lookup table.** The `COURSE_RACE_TYPE_TABLE` omits `small_group_sprint` and `individual_tt` entirely. The `FinishType` enum in `db/models.py` (line 43) defines `SMALL_GROUP_SPRINT` as a valid value. Flat criteriums with technical courses can produce small-group sprints. The table also never predicts `breakaway` (without `_selective`) from Tier 2 -- only from Tier 1 race-type defaults, despite the Tier 2 table including `("hilly", "road_race"): ("breakaway", 0.55)`. Wait, it does include breakaway. But `small_group_sprint` and `individual_tt` are still absent from the course predictor vocabulary, meaning those finish types can only come from time-gap classification.
- **No handling of `gravel` or `stage_race` race types.** The `RaceType` enum in `db/models.py` includes `GRAVEL` and `STAGE_RACE`, but neither appears in `RACE_TYPE_DEFAULTS` (Tier 1) or `COURSE_RACE_TYPE_TABLE` (Tier 2). Gravel races exist in the PNW (e.g., STP gravel alternatives, Oregon gravel events). These fall through to `None` race_type handling, which is likely wrong -- a flat gravel race is not a bunch sprint.
- **Dual lookup table is harder to extend than it looks.** The two-tier structure (Tier 1 for race_type-only, Tier 2 for course_type + race_type) means adding a new race type requires updating two dictionaries. A single matrix approach (like Gemini's) with explicit None-course handling would be more maintainable.
- **67% threshold for race type inheritance may be too low.** Consider: a series with 3 editions where 2 are criteriums and 1 is a road race (because the organizer changed format). 67% passes the threshold, but the most recent edition being a road race is a strong signal the format changed. The function as specified doesn't weight recency, unlike `predict_series_finish_type()` in `predictions.py` (lines 78-85) which weights the most recent 2 editions at 2x.
- **Phase 3 feels thin.** It's essentially "verify Phase 2 works end-to-end" plus the Ontario fix. The Ontario fix is a simple filter change that could be in Phase 2 or Phase 4. Having a dedicated phase for what amounts to verification + one small fix wastes phase overhead.
- **No mention of `RACER_TYPE_DESCRIPTIONS` coverage.** The `predictions.py` `RACER_TYPE_DESCRIPTIONS` dict (lines 687-700) only covers 12 of the possible (course_type x finish_type) pairs. Course-based predictions will populate new (course_type, finish_type) combinations that may not have racer type descriptions. The draft mentions CP-04 ("Populate 'Who does well here?' from course predictions") but doesn't address whether the description table needs expansion.

### 3. Risk Analysis Gaps

- **No risk for lookup table staleness.** The table is hardcoded. If a new race type is added to the `RaceType` enum, the predictor silently falls through to None handling. There should be a risk item about keeping the table synchronized with the enum.
- **No risk for Course data quality.** The predictor trusts `course_type` from the `Course` table, but this value comes from `elevation.py` m/km thresholds which may be wrong for specific courses (e.g., a course with one massive climb and otherwise flat terrain could be classified "rolling" by average m/km but race like a "hilly" course).
- **No risk for `climbs_json` parsing.** The course predictor accepts `climb_count` as an integer, but the actual data comes from `climbs_json` (a JSON text column on `Course`). The draft doesn't specify who parses this or what happens if the JSON is malformed.

### 4. Missing Edge Cases

- **Series with multiple Course records.** The `Course` table has both `series_id` and `race_id` fields. A series could have multiple Course rows (one per edition if the course changed). The draft says "Load Course for series_id" in the data flow but doesn't specify which Course to use when multiple exist.
- **course_type = "unknown".** The `CourseType` enum includes `UNKNOWN`. The lookup table uses string keys like `"flat"`, `"rolling"`, etc. What happens when `course_type` is `"unknown"`? It won't match any Tier 2 key and will fall through to Tier 1, but this isn't documented.
- **Confidence adjustment can push below 0.40.** The table states confidence range is 0.40-0.75, but the -0.10 adjustment for short races could push a 0.45 base confidence to 0.35. No floor is specified.
- **`infer_race_type_from_series` called for series with 0 historical editions.** The function should handle this, and the minimum-2-editions rule does, but the draft doesn't address what happens when the upcoming race IS the first edition (series_id exists but zero past races).

### 5. Definition of Done Completeness

- **Coverage target is testable ("45% to <20%")** but the 80%+ non-UNKNOWN metric is aspirational without data backing. How many of the 630 "unknown" races have Course data? If only 300 have Course data, the coverage improvement may be smaller than expected.
- **Missing DoD for `racer_type_description` expansion.** CP-04 says course predictions populate racer type, but there's no acceptance criterion for what happens when the (course_type, finish_type) pair isn't in `RACER_TYPE_DESCRIPTIONS`.
- **No DoD for narrative language changes.** Open Question #2 discusses showing "Course suggests..." vs "Historically ends in..." but there's no acceptance criterion requiring this distinction be implemented in Sprint 012. It's left as "defer to Phase 4 or Sprint 013."
- **Quality DoD is strong.** Lint, tests, performance, and batch query count are all covered with specific thresholds.

### 6. Architecture Concerns

- **`prediction_source` as a raw string is fragile.** Values are "time_gap", "course_profile", "race_type_only", None -- but there's no enum or validation. The existing codebase uses `SAEnum` for type-constrained columns (e.g., `FinishType`, `RaceType`). A string column risks typos. An enum would be more consistent with the codebase patterns in `db/models.py`.
- **Predictor returns string finish types, not FinishType enums.** The `CoursePrediction` dataclass uses `finish_type: str`, but the existing `ClassificationResult` in `classification/finish_type.py` (line 17) uses `finish_type: FinishType`. Using raw strings introduces a type inconsistency within the `classification/` package.
- **No migration strategy beyond "ALTER TABLE."** The draft acknowledges existing databases need ALTER TABLE but says "Document in CLI output." For a SQLAlchemy project using `Base.metadata.create_all()`, adding a column to an existing table does NOT work -- `create_all()` only creates missing tables, not missing columns. This is a real deployment issue that needs Alembic or a manual migration script.

---

## Gemini Draft Critique

### 1. Strengths

- **Outstanding "data quality cascade" framing.** The architecture section (lines 56-79) traces exactly how `predicted_finish_type = "unknown"` propagates through five downstream systems with specific line numbers from `predictions.py` and `queries.py`. This is the strongest analytical insight across both drafts and makes the case for the sprint's value better than any other section.
- **Broader decision matrix.** Covers all 6 race types from the `RaceType` enum (criterium, road_race, hill_climb, gravel, stage_race, unknown) crossed with 4 terrain types = 24 cells. This is more complete than Codex's table, which omits gravel and stage_race entirely.
- **Crit m/km offset is a good domain insight.** Recognizing that a 5 m/km criterium is experientially different from a 5 m/km road race (short repeated laps vs. one long effort) and implementing a -2.0 threshold offset is a nuanced detail that would improve prediction accuracy for PNW criteriums on hilly courses.
- **`render_series_profile` as a dedicated component.** Rather than just "expand the card," this draft proposes a purpose-built profile view for past-only series with 7 specific content sections. This is a more thoughtful UX solution than Codex's "force-expand and render outside the Past Races expander."
- **Refinement signals include climb positioning.** The "+0.05 toward breakaway_selective when a significant climb is in the final 25% of the course" refinement uses `climbs_json` data meaningfully. This leverages existing Sprint 008 data that Codex ignores.
- **Source-aware narrative language is well-specified.** The `finish_type_plain_english_with_source()` function and the UX treatment table (lines 326-331) give concrete text for each prediction source, making implementation unambiguous.

### 2. Weaknesses

- **Phase 1 is overloaded (~40%).** It bundles the predictor, the schema change, the precompute integration, AND narrative language changes into a single phase. Codex splits predictor (Phase 1) from pipeline integration (Phase 2), which is cleaner. If Phase 1 fails testing, the narrative changes are also blocked despite being independent.
- **80% threshold for race type inheritance is too aggressive.** The draft specifies ">= 80% historical agreement" (line 415). For a series with 5 editions where 4 are criteriums, that's 80% -- passes. But for 4 editions where 3 are criteriums, that's 75% -- fails. This seems overly conservative for a function whose fallback is "leave race_type as None" (which causes the original problem). Codex's 67% is arguably better calibrated, especially since the function includes a minimum-2-editions guard.
- **`_resolve_prediction` has redundant code.** Steps 2 and 3 in the precompute priority logic (lines 231-269) both call `predict_from_course()`, first with course data and then without. But `predict_from_course()` already handles the case where course_type is None -- it would fall through to race_type_only internally. The two-step approach in the precompute function duplicates logic that should be in the predictor itself.
- **`_confidence_label` mapping is too coarse.** The function (lines 275-281) maps >= 0.7 to "moderate" and everything below to "low". This means a 0.50 prediction and a 0.69 prediction both get labeled "low", losing meaningful gradation. The existing time-gap confidence labels in `predictions.py` (lines 113-117) use a three-tier system (high/moderate/low) with more useful boundaries.
- **`_get_series_race_type` uses "> 50% agreement" (line 379).** This is a different threshold than the 80% used for `inherit_race_type_from_series` (line 415). Having two different thresholds for conceptually similar operations (inferring race type from history) is confusing and likely to cause bugs.
- **DP-03 (single-edition drop rate caveat) is scope creep.** The intent document doesn't mention Issue #8. Adding narrative caveats for single-edition data is a nice improvement but increases the sprint scope without being part of the 13 issues to fix.
- **"mixed" as a finish type in the decision matrix.** For flat stage races and rolling stage races, the matrix predicts `mixed (0.50)`. But `FinishType.MIXED` in the existing classifier (line 47 of `db/models.py`) is a catch-all for "doesn't fit any pattern." Using it as a deliberate prediction for stage races conflates "we analyzed this and it's varied" with "we couldn't classify this." A better approach might be to skip prediction for stage races entirely.

### 3. Risk Analysis Gaps

- **No risk for `render_series_profile` performance.** This component calls `get_feed_item_detail()` + `get_similar_series()` for deep-linked past series. The draft acknowledges this in the risk table but waves it away with "only fires for isolated deep-links." However, if a popular race like Gorge Roubaix gets shared on social media, many concurrent deep-link requests could hit this path.
- **No risk for stale `prediction_source` values.** If `compute-predictions` is run without `--backfill-types`, existing rows keep `prediction_source = None` even though they may have time-gap data. The UI code that checks `prediction_source` to choose language needs to handle None gracefully (defaulting to time-gap language), but this isn't called out.
- **No risk for `climbs_json` deserialization.** The refinement signals parse `climbs_json` via `json.loads(course.climbs_json)`. If the JSON structure has changed between Sprint 008 and now, or if some entries have malformed JSON, the predictor could throw. No try/except is specified.

### 4. Missing Edge Cases

- **`predict_from_course` defaults to `("rolling", "road_race")` when character and race_type are both unknown.** Line 181: `_DECISION_MATRIX.get((character or "rolling", race_type or "road_race"), ...)`. This means any series with no course data and no race type silently predicts as a rolling road race instead of returning None. This contradicts the docstring ("Returns None if insufficient data") and could produce false predictions.
- **Empty `climbs` list vs None.** The `_apply_refinements` function receives `climbs` which could be `[]` (JSON parsed, no climbs found) or `None` (no climbs_json at all). The refinement "climb count >= 3 AND any climb > 8% avg grade" needs to handle both cases.
- **`course_type.value` when `course_type` is `CourseType.UNKNOWN`.** Line 236: `course.course_type.value if course.course_type else None` would produce `"unknown"` for `CourseType.UNKNOWN`, which would then be passed to `_resolve_course_character()`. That function checks `course_type != "unknown"` (line 110), which handles it, but the data flow is fragile -- it relies on string comparison against an enum value.
- **Search returning a mix of past-only and upcoming items.** Phase 3 handles "when search returns only past items" but what about a search that returns 2 upcoming items and 5 past-only items? The past items still end up in the collapsed expander.

### 5. Definition of Done Completeness

- **Strong cascade verification.** The DoD explicitly checks that downstream systems (similarity scoring, racer type, card rendering) benefit from new predictions. This is more thorough than Codex's DoD.
- **Missing DoD for backfill idempotency.** The `backfill_race_types()` function should be safe to run multiple times. There's no acceptance criterion that verifies running it twice doesn't change results or create duplicates.
- **Missing DoD for graceful degradation of `render_series_profile`.** The exit criteria mention "gracefully degrades when course data or predictions are missing" but don't specify what the user sees in each degradation scenario. Is it just missing sections? Is there a fallback message?
- **Crit m/km offset has no validation criterion.** The feature is specified but there's no test case that verifies, e.g., a 4 m/km criterium is classified as "rolling" (not "flat" as it would be for a road race).

### 6. Architecture Concerns

- **`_get_series_race_type` in `precompute.py` duplicates `infer_race_type` in `queries.py`.** The codebase already has `infer_race_type(race_name)` (line 116 in `queries.py`) for name-based race type inference. Adding `_get_series_race_type` with a different algorithm (historical majority) in a different module creates two parallel race-type inference paths. These should be composed, not duplicated.
- **`prediction_source` in Tier 1 batch query increases coupling.** Adding `prediction_source` to `get_feed_items_batch()` output means the batch query now must join `SeriesPrediction` for a field that's only used for text formatting. This is technically low-cost (it's already joining `SeriesPrediction`), but it adds a column to every item dict that 55% of cards (those with time-gap data) don't need for rendering decisions.
- **`finish_type_plain_english_with_source` wraps `finish_type_plain_english`.** This creates a two-function call chain for something that could be a single function with an optional parameter. The existing `finish_type_plain_english()` in `queries.py` (line 967) returns a string -- the wrapper adds source-aware prefix text. This will be confusing for future developers who need to choose between the two.
- **Same `Base.metadata.create_all()` migration issue as Codex.** The draft says "additive column, handled by `create_all()`" -- but `create_all()` does not add columns to existing tables. This will silently fail on existing databases.

---

## Comparative Analysis

### Where Codex is stronger than Gemini:
- **Phase decomposition.** 4 phases with cleaner dependency boundaries. Phase 1 is truly standalone (pure function, no DB), making it faster to validate.
- **Confidence ceiling.** 0.75 is more conservative than 0.80, which is appropriate for heuristic-based predictions.
- **Race type inheritance threshold.** 67% is better calibrated than 80%. With the minimum-2-editions guard and the fact that `infer_race_type()` exists as a name-based fallback, a lower threshold fills more gaps without much risk.
- **Simpler predictor API.** A dataclass with string types is easier to test than one that depends on FinishType enum imports, even if the enum is arguably more correct.

### Where Gemini is stronger than Codex:
- **Decision matrix completeness.** 24 cells covering all race types vs. Codex's partial table missing gravel and stage_race. In a PNW-focused tool, gravel matters.
- **Cascade analysis.** The explicit trace through 5 downstream systems with line numbers is a better justification for the sprint's priorities.
- **Crit m/km offset.** A genuine domain insight that Codex misses entirely.
- **Past-only series as a "profile" view.** More ambitious and more useful than Codex's simple "force-expand" approach.
- **Refinement signals.** Using climb positioning (final-quarter detection) and total gain thresholds adds meaningful confidence adjustments that Codex's simpler approach misses.
- **Source-aware narrative language.** Fully specified with concrete text examples, making implementation unambiguous. Codex defers this.

### Shared weaknesses:
- **Both get `Base.metadata.create_all()` wrong** for adding a column to an existing table. This is a deployment blocker that neither draft addresses correctly.
- **Neither addresses `RACER_TYPE_DESCRIPTIONS` coverage gap.** New (course_type, finish_type) combinations from the course predictor may not have entries in the `RACER_TYPE_DESCRIPTIONS` dict in `predictions.py` (lines 687-700). Both mention the racer type feature improving but neither expands the description table.
- **Neither specifies what happens when `predictions.py` `generate_narrative()` receives a course-based prediction.** The function currently checks `if predicted_finish_type and edition_count > 0` (line 635). For a course-based prediction on a series with 0 editions (new series with a course but no history), `edition_count` would be 0, and the history sentence would be skipped even though there's a valid prediction. Both drafts need to address this condition.
- **Neither proposes an Alembic migration.** The project uses `Base.metadata.create_all()` per the existing patterns, but adding a column to `series_predictions` requires either Alembic or a manual `ALTER TABLE`. Both drafts handwave this.
- **Neither discusses `SMALL_GROUP_SPRINT` in the course predictor.** This is a valid `FinishType` value (line 43 of `db/models.py`) that neither predictor can produce from course data alone. This may be acceptable (it's a tactical outcome hard to predict from terrain), but it should be explicitly noted as a deliberate omission.
