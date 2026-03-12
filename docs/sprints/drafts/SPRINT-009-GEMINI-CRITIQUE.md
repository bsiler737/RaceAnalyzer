# Sprint 009 Draft Critique

## Claude Draft (`SPRINT-009-CLAUDE-DRAFT.md`)

### 1. Strengths
- **JSON-first strategy is well-reasoned.** The "try JSON first, fall back to HTML" approach (Architecture section) correctly minimizes new parsing code by reusing `RaceResultParser`. The explicit acknowledgment that `CarriedPoints` is pre-race data and may already be populated in the JSON endpoint shows domain understanding.
- **Data flow diagrams are clear and actionable.** The `fetch-calendar` and `fetch-startlists` flow diagrams in the Architecture section give an implementer an unambiguous execution path, including the decision point for JSON vs. HTML fallback.
- **Separation of RefreshLog from ScrapeLog.** The rationale for a dedicated `RefreshLog` table rather than overloading `ScrapeLog` is correct -- these are different concerns with different cadences. The schema includes a `checksum` column for future change-detection optimization, which is forward-thinking.
- **BikeReg deprecation is clean.** Renaming files to `*_bikereg.py` and removing imports is the right level of deprecation: no dead code in the active path, no premature deletion. This is more decisive than the Codex approach of keeping old modules in place.
- **Region listing optimization.** Phase 1 explicitly calls out the optimization of parsing dates from the region listing HTML in a single pass to avoid O(n) HTTP calls. This is a critical performance insight given the 3s rate limit.
- **Scope discipline.** The "What this sprint does NOT do" section explicitly states that `predictions.py`, `queries.py`, and the UI are untouched. This is mostly correct given the existing architecture -- except for one contradiction (see Weaknesses).

### 2. Weaknesses
- **Internal contradiction on predictions.py scope.** The Overview says this sprint "does not change `predictions.py`," but Phase 3 includes a task to "Update `predict_contenders()` Tier 1 in `predictions.py` to prefer `Startlist.carried_points` when available." This is a real change with real testing implications. The Overview should not claim zero-touch on predictions.
- **Phase ordering creates a dependency problem.** Phase 2 (startlist fetching) references storing `carried_points` on the `Startlist` row and says "requires schema change -- see Phase 3." This means Phase 2 cannot be fully completed and tested until Phase 3 is done. The schema changes in Phase 3 should be moved to the beginning of Phase 2, or Phase 3 should be Phase 1.
- **Calendar refresh tracking with `race_id=0` sentinel.** Phase 3 proposes using `race_id=0` as a sentinel value for calendar-level refresh tracking. This is a code smell -- it conflates a row-level foreign key concept with a system-level flag. A separate config key or a dedicated table row with `refresh_type="calendar_discovery"` and `race_id=NULL` would be cleaner, though the latter requires making `race_id` nullable on `RefreshLog`.
- **`days_ahead` parameter on `fetch_upcoming_race_ids`.** The method signature includes `days_ahead: int = 60`, but 60 days is quite narrow for PNW racing -- riders often register months in advance. The Codex draft uses 90 days, which is more reasonable. Neither draft makes this configurable via `Settings`, though Claude's Phase 1 does add it to `config.py` (inconsistency in the default value).
- **No `--dry-run` flag.** Unlike the Codex draft, Claude does not propose a `--dry-run` mode for either CLI command. For a sprint that replaces a working data pipeline, the ability to preview what would be fetched and persisted without actually writing to the DB is an important safety net during rollout.

### 3. Gaps in Risk Analysis
- **No risk for region listing pagination.** If road-results paginates the region listing (only showing the most recent N races per page), the `discover_region_race_ids` method would miss upcoming races that appear on later pages or on a separate "upcoming" section. The existing regex `r'/race/(\d+)" >'` was designed for historical results -- it may not match links in a different HTML structure for upcoming events.
- **No risk for time zone handling.** The `is_stale_edition` logic compares `race.date < today`, but `race.date` is a `DateTime` column stored without timezone info, and "today" depends on the system clock. A race at 8 AM Pacific on March 15 could be skipped if the system runs at 1 AM UTC on March 16. The intent document says "upcoming race in the current year" but does not specify timezone semantics. This is a subtle bug that should be called out.
- **No risk for concurrent CLI invocations.** If two `fetch-startlists` processes run simultaneously (e.g., cron overlap), the `should_refresh` check has a TOCTOU race condition -- both could see "no refresh today" and proceed. For a single-user CLI tool this is low-likelihood, but it should be acknowledged.

### 4. Missing Edge Cases
- **Race with pre-reg data AND historical results in the same JSON response.** The draft assumes JSON returns either pre-reg data or post-race results. But what about a multi-day event where Day 1 results are posted while Day 2 still has pre-reg entries? The `StartlistParser` needs to distinguish between result rows and pre-reg rows in the same response, which the Codex draft handles better by checking for empty `Place`/`RaceTime`.
- **Race ID collision between regions.** If regions 4 and 12 share race IDs (unlikely but not impossible), deduplication should happen at the discovery stage. Neither draft addresses this.
- **Startlist with zero `carried_points` vs. null `carried_points`.** A rider with `carried_points = 0.0` is different from a rider with `carried_points = None` (no data). The current `_rank_from_startlist` treats both as "no points" because of the `if r.carried_points` truthiness check on line 195 of `predictions.py`. Adding `Startlist.carried_points` doesn't fix this pre-existing bug, but the sprint should acknowledge it.

### 5. Definition of Done Completeness
- **Strong and well-structured.** The DoD is organized by functional area (Calendar, Startlist, Refresh, Request Safety, BikeReg, Testing) with specific, checkable items.
- **Test counts are good.** Specifying "5+ tests" per area with explicit scenarios is more actionable than vague "adequate coverage" language.
- **Missing: performance constraint.** There is no DoD item for maximum wall-clock time of `fetch-calendar` or `fetch-startlists`. Given the 3s rate limit and potentially 100+ races, this could be a 5+ minute command with no progress feedback. A DoD item like "progress logging every 10 races" or "completes within 10 minutes for typical PNW region" would be useful.
- **Missing: migration path for existing databases.** The DoD does not include verifying that existing databases (with `Startlist` rows from BikeReg) continue to work after adding the `carried_points` column and `RefreshLog` table. The Risks section mentions manual `ALTER TABLE`, but there is no DoD item ensuring this is tested.

### 6. Implementation Phasing
- **Mostly logical, with one ordering issue.** The four phases follow a sensible progression: discover races, fetch startlists, add schema + refresh limits, clean up BikeReg. However, as noted above, Phase 3's schema changes are prerequisites for Phase 2's data persistence. Reordering Phase 3 to come before or merge with Phase 2 would eliminate this dependency.
- **Phase 4 effort estimate (15%) is reasonable** for file renames and cleanup, but it bundles test suite verification, linting, and integration testing, which could reveal issues requiring backtracking to earlier phases. This should be acknowledged.

---

## Codex Draft (`SPRINT-009-CODEX-DRAFT.md`)

### 1. Strengths
- **Richer `RefreshLog` schema.** The inclusion of `status` ("success", "empty", "error") and `error_message` columns is operationally superior to Claude's simpler schema. When debugging why a startlist is stale, knowing whether the last refresh attempt failed vs. returned empty is valuable. The `UniqueConstraint` on `(race_id, refresh_type, refreshed_at)` also prevents duplicate log entries from concurrent writes.
- **`StartlistParser` is well-specified.** The Architecture section gives concrete parsing rules for distinguishing pre-reg entries from result entries (`Place` is None/empty AND `RaceTime` is None/empty). This directly addresses the mixed-response edge case that Claude's draft leaves ambiguous.
- **Clear-and-reinsert strategy for startlist updates.** Phase 2's approach of deleting all `source="road-results"` startlist entries for a race before inserting fresh data is explicit about idempotency. This avoids the accumulation of stale entries that plagues naive upsert approaches.
- **`--source` and `--dry-run` CLI flags.** These provide both rollback capability (switch back to BikeReg with a flag) and safe preview during migration. These are operationally important features that Claude's draft omits.
- **BikeReg transition strategy is more graceful.** By creating new modules (`road_results_calendar.py`, `road_results_startlists.py`) alongside the existing ones rather than rewriting in-place, the Codex approach lets both pipelines coexist. Rolling back requires changing one CLI flag, not reverting file renames.
- **`road_results_startlist_source` config setting.** This makes the active source configurable without code changes, which is useful for gradual rollout and A/B comparison.

### 2. Weaknesses
- **Five phases is over-decomposed.** Phase 3 (Refresh Limiting, 15% effort) and Phase 5 (Cleanup & Edge Cases, 10% effort) could be absorbed into Phases 1-2 and Phase 4 respectively. Separating refresh logic into its own phase means Phases 1 and 2 are implemented without their guard rails, requiring later retrofitting. Claude's approach of including refresh checks directly in the CLI commands is more natural.
- **Phase 4 modifies `predictions.py` and `queries.py` -- scope creep.** The intent document and both drafts agree that `predict_contenders()` already works source-agnostically. Adding `Startlist.carried_points` and having Tier 1 prefer it is a reasonable optimization, but modifying `get_race_preview()` to surface `startlist_source` and adding `road_results_racer_id` to the predictions output is UI-layer work that goes beyond the sprint's stated scope of "new data acquisition, not architectural changes." If this work is included, it should be reflected in the effort estimate and risk analysis.
- **`is_refreshable_edition` uses `session.get(Race, race_id)`.** This assumes `race_id` in `RefreshLog` is the SQLAlchemy primary key of the `Race` model, but the `RefreshLog.race_id` column uses `ForeignKey("races.id")`. This is fine for correctness but creates a tight coupling -- if we ever need to track refreshes for race IDs that don't yet have a `Race` row (e.g., during calendar discovery before persisting), the foreign key constraint will block the insert. Claude's draft avoids this by not putting a FK on `RefreshLog.race_id`.
- **New modules increase surface area.** Creating `road_results_calendar.py`, `road_results_startlists.py`, and `refresh.py` as three new modules (plus three new test files) adds significant surface area compared to Claude's approach of rewriting the existing modules in-place. For a project of this size, the additional indirection may not be worth the modularity benefit.
- **`should_refresh` uses calendar-day boundary, not 24-hour window.** The Codex implementation checks `refreshed_at >= today_start` (midnight UTC), meaning a refresh at 11:59 PM UTC becomes stale at 12:00 AM UTC -- one minute later. Claude's draft uses a sliding 24-hour window (`refreshed_at > datetime('now', '-24 hours')`), which better matches the intent of "at most once per day." The intent document says "1 refresh/day/edition" but doesn't specify which semantics to use. The sliding window is more robust.

### 3. Gaps in Risk Analysis
- **No risk for the `ForeignKey` constraint on `RefreshLog.race_id`.** As noted above, this creates an ordering dependency: a `Race` row must exist before a `RefreshLog` entry can be created. During calendar discovery, we might want to log a refresh attempt for a race ID before deciding whether to persist the `Race` row (e.g., if the race date is in the past). The FK constraint makes this impossible without a two-pass approach.
- **No risk for `road_results_startlist_source` config drift.** If an operator sets `road_results_startlist_source = "bikereg"` to roll back but forgets to change it back, the system silently stays on BikeReg indefinitely. There should be a warning log when BikeReg is active, or a CLI prompt confirming the active source.
- **OBRA fallback mentioned but not scoped.** The risk table mentions "fall back to scraping the OBRA calendar as a race-ID source" if the road-results region listing doesn't include future races. This is a significant piece of work (new scraper, new parser, new domain) that is not reflected in the effort estimate or phasing. If this risk materializes, the sprint scope blows up. It should either be scoped as a contingency task or explicitly deferred.

### 4. Missing Edge Cases
- **Race edition with multiple categories having different dates.** Some road-results events list different categories on different days (e.g., juniors on Saturday, Cat 1/2 on Sunday). The `Race.date` field is singular. If `is_refreshable_edition` checks against a single date, it might skip refresh for categories racing on a different day.
- **`match_event_to_series` reuse from `calendar_feed.py`.** Phase 1 says to "reuse `match_event_to_series` logic from `calendar_feed.py`" but the BikeReg module is being kept as a dormant fallback, not rewritten. If `match_event_to_series` is imported from `calendar_feed.py`, it creates an active dependency on a "dormant" module. This function should either be extracted to a shared utility or duplicated in the new module.
- **Empty startlist after clear-and-reinsert.** If the road-results fetch fails after the delete step (which removes old entries), the race ends up with zero startlist entries. The clear-and-reinsert should be wrapped in a transaction so the delete is rolled back on fetch failure.

### 5. Definition of Done Completeness
- **Well-organized with clear functional areas.** The split into Data Acquisition, Power Rankings, Refresh Limiting, HTTP & Rate Limiting, BikeReg Transition, and Testing covers the sprint comprehensively.
- **Test specification is strong.** The testing section specifies test counts per area and explicitly requires `responses` mocking with no live network calls.
- **Missing: backward compatibility check.** No DoD item verifies that existing BikeReg-sourced `Startlist` rows (with `source="bikereg"`) continue to work correctly in `predict_contenders()` after the schema changes.
- **Missing: `--source bikereg` verification.** The BikeReg Transition section claims `--source bikereg` activates the fallback, but there is no DoD item requiring this to be tested end-to-end. If it is listed as a feature, it should be tested.
- **Power Rankings DoD is overreaching.** "Race Preview page shows contenders sorted by road-results power rankings" implies UI verification, but no UI changes are in the implementation plan. If the existing UI already sorts by `carried_points`, this DoD item is redundant. If it requires UI changes, those are missing from the phasing.

### 6. Implementation Phasing
- **Refresh logic should not be a separate phase.** Phase 3 (Refresh Limiting) is structurally dependent on Phases 1 and 2 already being wired up. Implementing discovery and startlist fetching without refresh guards means the initial implementation can hammer road-results during development and testing. The refresh checks should be baked into the client methods or CLI commands from the start.
- **Phase 4 (Predictions Integration) is partially unnecessary.** The existing `_rank_from_startlist` already queries the `Result` table for `carried_points` and sorts by it. Adding `Startlist.carried_points` as a shortcut is an optimization, not a requirement. If this optimization is deferred, Phase 4 shrinks to just CLI wiring and can merge with Phase 2.
- **Phase 5 (Cleanup) is too vague.** "Edge case hardening" and "structured logging" are open-ended tasks that resist estimation. Specific edge cases should be handled in the phase that introduces the relevant code, not batched into a cleanup phase.

---

## Recommendation

**The merged sprint should use Claude's data pipeline architecture and phasing structure, augmented with Codex's operational features and parser specificity.**

**Claude's approach is stronger overall** because it keeps the sprint tightly scoped to data acquisition (matching the intent document's "primarily new data acquisition, not architectural changes"), reuses existing modules rather than creating parallel ones, and has a more natural phase ordering despite the Phase 2/3 dependency issue.

**What to take from Claude:**
- **Pipeline architecture:** JSON-first with HTML fallback, rewriting existing modules in-place rather than creating parallel ones.
- **BikeReg deprecation:** Rename to `*_bikereg.py` -- cleaner than keeping dormant modules in the active namespace.
- **RefreshLog without FK:** No foreign key on `race_id` allows logging refresh attempts before `Race` rows exist.
- **Sliding 24-hour window:** More robust than calendar-day boundary for daily refresh limiting.
- **Region listing date optimization:** Parse dates from the listing HTML in one pass to avoid O(n) HTTP calls.

**What to take from Codex:**
- **`RefreshLog` status tracking:** Add `status` and `error_message` columns for operational debugging.
- **`StartlistParser` specificity:** The concrete rules for distinguishing pre-reg from result entries (no `Place`, no `RaceTime`) should be adopted.
- **`--dry-run` and `--source` CLI flags:** Essential for safe rollout and rollback capability.
- **Clear-and-reinsert with transaction safety:** Delete old startlist entries and insert new ones atomically.
- **`road_results_racer_id` on `Startlist`:** Storing this alongside `rider_id` provides a direct link to road-results profiles without requiring a join through `Rider`.

**What both drafts miss:**
- Timezone handling for date comparisons (UTC vs. Pacific).
- Pagination risk for region listings.
- Transaction safety for the clear-and-reinsert pattern.
- Backward compatibility testing for existing BikeReg data.
- The `carried_points = 0.0` vs. `None` truthiness bug in `predictions.py` line 195.
