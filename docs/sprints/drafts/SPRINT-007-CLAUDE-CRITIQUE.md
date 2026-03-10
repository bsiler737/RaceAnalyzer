# Claude's Critique of Codex and Gemini Drafts

## Codex Draft Critique

### Strengths
1. **Scope Ladder is excellent.** The Must Ship / Should Ship / Nice to Have tiers with explicit cut guidance ("cut Phase 4 first") is the most pragmatic scope management across all drafts. This should survive into the final doc.
2. **Data flow diagram** is clean and shows the pipeline clearly from RWGPS -> Course -> prediction -> UI.
3. **Concrete function signatures** for `predict_series_finish_type()` and `predict_contenders()` with return types are immediately implementable.
4. **Confidence calibration logic** is well-defined: 4+ editions + >60% plurality = high, 2-3 editions = moderate, 1 edition = low. Simple, defensible.
5. **"No new dependencies"** is a smart constraint that reduces risk.
6. **Explicit Phase 4 cut rationale** with BikeReg risk assessment is honest and useful.

### Weaknesses
1. **Course model is too simple.** Only `series_id` FK (unique), no `race_id` FK. This means if a course changes between editions (common for PNW events that alternate between rain and dry routes), there's no way to represent that. Claude's draft has both `series_id` and `race_id` FKs, which is more flexible.
2. **Missing `total_loss_m`, `max_elevation_m`, `min_elevation_m`** on Course. These are available from RWGPS at zero extra cost and useful for Phase 1 elevation analysis in Sprint 008. Storing them now saves a re-scrape later.
3. **Startlist model uses `series_id` not `race_id`** as the primary FK. But startlists are per-race (specific date), not per-series. A rider registers for the 2026 Banana Belt, not "the Banana Belt series." The FK should be `race_id` with an optional `series_id` for joining.
4. **No mention of `UserLabel` uniqueness constraints.** Claude's draft has `UniqueConstraint("race_id", "category", "session_id")` to prevent duplicate submissions. Codex's model lacks this.
5. **Missing RWGPS track_points fallback detail.** The `extract_elevation_stats()` function signature is shown but the fallback to computing from track points is mentioned as a risk mitigation but not implemented in the code.
6. **Prediction uses "recency weighting" (2x for recent editions)** but doesn't define what "recent" means. Last 2 editions? Last 2 years? This matters for series that skipped COVID years.

### Gaps in Risk Analysis
- No mention of the risk that `carried_points` may be stale (road-results.com updates sporadically).
- No data migration plan for adding columns to existing Rider/Result tables (SQLite ALTER TABLE limitations).

### Definition of Done Completeness
Strong. The DoD checklist covers schema, extraction, prediction, UI, degradation, and test coverage. The "heuristic beats random baseline" criterion is a nice touch.

---

## Gemini Draft Critique

### Strengths
1. **Clear phase structure** separating schema, elevation, startlists, prediction, and UI.
2. **Terrain classification logic** with explicit threshold values matches the spec.
3. **BikeReg rate limiting** (2-second delay, exponential backoff) is correctly specified.
4. **Security section** correctly identifies PII concerns and SQLi prevention.

### Weaknesses
1. **Significantly less detailed than other drafts.** No function signatures, no code snippets, no SQL queries. "Implement `BaselinePredictor` class" is not actionable without specifying the algorithm, inputs, and outputs. The other two drafts provide complete function signatures with return types.
2. **No graceful degradation tiers.** Mentions "tier 1: startlist -> tier 2: historical performers" but doesn't define Tier 3 (category-wide fallback). The Race Preview page layout mentions "fallback data" but doesn't specify what that means concretely.
3. **Course model has `version_hash`** but no explanation of how it's computed or when it changes. This is premature -- the intent doc suggests deferring course versioning.
4. **Startlist model has `rider_name` and `team_name` but no `rider_id` FK.** This means startlist entries can't be joined to historical results for carried_points ranking. Both other drafts include `rider_id` FK.
5. **No scope management.** No indication of what to cut if time runs short. Both other drafts explicitly identify BikeReg startlists as the highest-risk, most-cuttable piece.
6. **Missing the user labels feedback UX.** The UserLabel model is defined in Phase 1 but there's no implementation phase for the "Was this prediction right?" UI prompt. The table exists but is never populated.
7. **Prediction phase doesn't define what "ranks riders" means** -- by what metric? Max carried_points? Average percentile? The algorithm is unspecified.
8. **Definition of Done is weak.** Six items, mostly existence checks ("table is present", "correctly calculates"). No accuracy benchmarks, no mobile viewport testing criterion, no test coverage threshold beyond "achieving >85%."
9. **No open questions about RWGPS data availability** (whether elevation_gain is in the JSON response). This is the highest-uncertainty technical question.

### Gaps in Risk Analysis
- Overcomplicating risk mentions BikeReg API and RWGPS data gaps but misses: what if carried_points data is sparse? What if most riders have zero carried_points?
- No mention of scope risk (6 deliverables in one sprint).

### Definition of Done Completeness
Weak. Needs concrete acceptance criteria for prediction accuracy, mobile responsiveness, and graceful degradation behavior.
