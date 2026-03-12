# Sprint 009 Draft Critique

## Codex Draft

### Strengths

1. **Thorough architecture section with concrete code samples.** The `RefreshLog` model, `should_refresh()`, and `is_refreshable_edition()` functions are implementation-ready. The SQL schema, index choices, and query patterns are all correct and follow existing ORM conventions in `models.py`.

2. **Correct identification that the JSON endpoint may serve both results and pre-registration.** The `StartlistParser` design (Phase 2) correctly observes that pre-reg entries can be distinguished from result entries by the absence of `Place`/`RaceTime`. This is the pragmatic approach: try the existing `downloadrace.php` endpoint first, since `RaceResultParser` already extracts every needed field (`RacerID`, `CarriedPoints`, `Points`, `FirstName`, `LastName`, `TeamName`, `RaceCategoryName`).

3. **Clean BikeReg transition strategy.** The `--source` flag on CLI commands, keeping BikeReg code intact, and the `Startlist.source` field approach means rollback is a single flag change. The observation that `predictions.py` already works source-agnostically (it reads `carried_points` regardless of source) is correct -- verified by reading `_rank_from_startlist()` in the actual codebase.

4. **Realistic risk table with the bulk discovery timing concern.** The note that 100+ race IDs at 3s/request = 5+ minutes is a real usability issue that Gemini does not flag. The `--limit` flag mitigation is practical.

5. **Explicit effort percentages per phase** (25/30/15/20/10) that sum to 100% and roughly align with complexity. Phase 2 (startlist parsing) getting the largest share is correct -- it has the most unknown-endpoint risk.

6. **Good separation of concerns.** Creating `refresh.py` as a standalone module (Phase 3) rather than embedding refresh logic in the calendar/startlist modules makes the daily-limit logic independently testable. This is the right call.

7. **`road_results_racer_id` column on Startlist.** Adding this alongside `rider_id` means we preserve the raw road-results identifier even when rider linking fails. Useful for debugging and future reconciliation.

### Weaknesses

1. **Creates too many new modules.** The draft proposes three new files: `road_results_calendar.py`, `road_results_startlists.py`, and `refresh.py`. But `calendar_feed.py` and `startlists.py` already exist and are small (140 and 119 lines respectively). The intent document says "REPLACE" not "create parallel modules." Adding the road-results functions directly to the existing modules (alongside the BikeReg functions, marked deprecated) would be simpler, reduce import sprawl, and match the Gemini approach. Two calendar modules and two startlist modules is confusing.

2. **`StartlistParser` may be unnecessary.** The draft creates a new parser class in Phase 2, but `RaceResultParser.results()` already extracts every field the `StartlistParser` would need: `name`, `team`, `race_category_name`, `racer_id`, `carried_points`, `points`. The only difference is filtering out entries that have `Place`/`RaceTime`. A simple filter function on `RaceResultParser.results()` output would be ~10 lines vs. a new class. The draft acknowledges this possibility ("This may literally be the same endpoint") but still budgets for a full parser class.

3. **Phase ordering creates unnecessary dependency risk.** The `RefreshLog` model is created in Phase 1, but the refresh logic (`should_refresh`, `is_refreshable_edition`) is deferred to Phase 3. This means Phase 1 and Phase 2 implementations must either (a) hardcode refresh checks or (b) be written without refresh protection and retrofitted later. It would be cleaner to build `refresh.py` in Phase 1 alongside the `RefreshLog` model.

4. **The `UniqueConstraint` on `RefreshLog` is wrong.** The constraint `uq_refresh_per_type_time` on `(race_id, refresh_type, refreshed_at)` is meaningless -- `refreshed_at` is a `DateTime` with microsecond precision, so two entries with the same `race_id` and `refresh_type` would need to be written at the exact same microsecond to collide. This constraint does not enforce the "one refresh per day" business rule. It should either be removed (the daily check is a query-time concern) or replaced with a constraint on `(race_id, refresh_type, date(refreshed_at))` -- though SQLite does not support computed columns in constraints. The Gemini draft avoids this by not adding the constraint.

5. **No discussion of the `Startlist` table's existing `checksum` column.** The `Startlist` model already has a `checksum` column (line 287 of `models.py`). The Codex draft mentions checksums only in passing ("The `checksum` column on `Startlist` can optionally detect no-change refreshes") but doesn't integrate it into the clear-and-reinsert strategy. If the checksum matches, the delete+reinsert is wasted work.

6. **Open question #5 (store `Points` separately from `CarriedPoints`) is already answered.** The `Result` model already stores both `points` and `carried_points` as separate columns. The draft should note this and propose doing the same on `Startlist` -- adding a `points` column alongside `carried_points`.

7. **Missing: how `discover_upcoming_race_ids` differs from `discover_region_race_ids`.** The draft proposes a new method but acknowledges it "may be identical to the existing method." If the only difference is downstream date filtering, don't add a new client method -- just reuse `discover_region_race_ids()` and filter in the calling code.

### Gaps in Risk Analysis

1. **No risk for "road-results JSON returns `NoResultsError` for upcoming races with no results yet."** Looking at the actual `RaceResultParser.results()` (line 128 of `parsers.py`), it raises `NoResultsError` when `self._data` is empty. If the JSON endpoint returns `[]` for an upcoming race (no results, no pre-reg data), the parser will throw, not degrade gracefully. The `fetch_race_startlist_json` method needs to catch this.

2. **No risk for `RacePageParser` failing on upcoming race pages.** The parser relies on a `resultstitle` HTML element (line 15 of `parsers.py`). Upcoming race pages may have different HTML structure than completed race pages. If the title regex does not match, `UnexpectedParsingError` is raised -- not graceful degradation.

3. **No risk for concurrent CLI invocations.** Two `fetch-startlists` runs at the same time could both pass `should_refresh()` (both query before either writes) and produce duplicate `RefreshLog` entries and race conditions on the clear-and-reinsert. SQLite's write locking partially mitigates this but deserves mention.

### Missing Edge Cases

1. **Race ID exists in region listing but is a non-road discipline** (cyclocross, mountain bike, track). Road-results covers multiple disciplines. The draft has no filtering by discipline type, which could pollute the upcoming-race calendar with irrelevant events.
2. **Race with pre-registration data but the rider has `CarriedPoints = 0`.** A zero value is truthy in Python but semantically different from None. The `_rank_from_startlist` update needs to handle this: `if entry.carried_points is not None` rather than `if entry.carried_points`.
3. **Startlist entries for riders who have changed names** (marriage, etc.). Road-results `RacerID` is the correct dedup key, but the `rider_name` stored in `Startlist` may not match the `Rider.name` from historical data. Not critical but worth a note.
4. **Region listing returns paginated results.** If road-results paginates the region listing beyond a certain number of races, `discover_region_race_ids` would only get the first page. The existing regex-based approach has no pagination handling.

### Definition of Done Completeness

The DoD is comprehensive and well-structured across Data Acquisition, Power Rankings, Refresh Limiting, HTTP, BikeReg Transition, and Testing categories. Specific notes:

- **Good: minimum test case counts per area.** "4+ test cases" for `StartlistParser`, "6+ test cases" for refresh logic -- these are concrete and verifiable.
- **Good: "All existing tests pass" and "ruff check passes"** are included as baseline requirements.
- **Missing: end-to-end CLI verification.** No DoD item confirms that `fetch-calendar` followed by `fetch-startlists` followed by Race Preview produces correct output. The individual pieces are tested but the pipeline is not.
- **Missing: performance criteria.** No time limit for `fetch-calendar` on a typical region, no expectation for how many races should be discoverable. Given the bulk-discovery timing risk, a "completes within 10 minutes for 100 races" criterion would be useful.
- **Missing: schema migration verification.** No DoD item confirms that `ALTER TABLE startlists ADD COLUMN carried_points` and `CREATE TABLE refresh_log` work on an existing database with data.

### Implementation Phasing Assessment

The five-phase structure is logical and dependency-aware: discovery (Phase 1) before startlists (Phase 2) before predictions (Phase 4) is correct. However, Phase 3 (refresh limiting) being separate from Phase 1 (where `RefreshLog` is created) is awkward -- the model and its business logic should be co-located in the same phase. The cleanup phase (Phase 5) is lightweight and appropriate as a final pass.

---

## Gemini Draft

### Strengths

1. **Superior prose quality and document structure.** The overview clearly explains *why* this sprint matters (eliminating the cross-provider data join), what it does, and what it does NOT do. The flow diagram in the Architecture section showing the end-to-end pipeline (`fetch-calendar -> fetch-startlists -> Race Preview`) is excellent for orientation.

2. **Two-prong discovery strategy is creative.** Prong 1 (date-scanning the region listing) is the standard approach, but Prong 2 (series-based forward lookup by race ID range) is a genuinely novel idea that addresses the risk of upcoming races not appearing in region listings. Neither the intent document nor the Codex draft proposes this fallback.

3. **Correct decision to add new functions to existing modules.** `search_upcoming_events_rr()` goes in `calendar_feed.py`; `fetch_startlist_rr()` goes in `startlists.py`. This keeps related code together and avoids the module proliferation of the Codex draft.

4. **Three-tier data extraction pipeline (JSON -> HTML fallback -> history enrichment)** is more resilient than Codex's approach. The fallback chain ensures that even if the JSON endpoint fails for upcoming races, HTML scraping provides a second chance, and historical `carried_points` lookup provides a third. Codex mentions the HTML fallback but does not structure it as cleanly.

5. **`RefreshLog.checksum` for change detection.** Including a checksum column and computing it on every refresh (even if skip-on-unchanged is deferred) collects data for a future optimization. This is good engineering discipline -- instrument before optimizing.

6. **Explicit "data freshness tiers" table** (Active vs. Stale) makes the refresh policy instantly understandable. The justification for why `RefreshLog` is separate from `ScrapeLog` (different cardinality, different unique constraints) is well-reasoned and would be useful to a future developer.

7. **UI updates included in scope.** Phase 5 adds a data source badge and last-refreshed timestamp to the Race Preview page. This is a small but meaningful UX improvement that the Codex draft omits.

8. **Risk table covers concurrent CLI invocations.** "Use checksum on `RefreshLog` for idempotency. Clear existing Startlist rows for a race+source before writing new batch. SQLite write lock serializes concurrent access." This is a real-world concern that Codex misses.

### Weaknesses

1. **Prong 2 (series-based forward lookup) is speculative and potentially expensive.** The claim that "a series that ran as race ID 14500 last year likely has a 2026 edition somewhere in the 14800-15200 range" assumes road-results uses roughly sequential IDs and that the gap between years is predictable. This requires probing potentially hundreds of race IDs speculatively, which at 3s/request could take 10+ minutes and amounts to brute-force ID scanning. The draft does not address the cost of this approach or provide a stopping condition. This should either be scoped down (e.g., check only ID+1 through ID+500) or deferred to a future sprint.

2. **`UpcomingRaceParser` may be unnecessary.** The region listing page is already parsed by `discover_region_race_ids()` using a simple regex (`/race/(\d+)" >`). If upcoming races appear on the same page with dates, extending the existing regex to capture the date (e.g., a `(\w{3}\s+\d{1,2}\s+\d{4})` adjacent to the race link) is more appropriate than a new parser class. The draft allocates a full class where a regex extension would suffice.

3. **No `road_results_racer_id` column on Startlist.** The Codex draft adds this column to preserve the raw road-results identifier even when rider linking fails. The Gemini draft links riders by `racer_id -> Rider.road_results_id` but doesn't store the `racer_id` on the `Startlist` row itself. If linking fails (no matching `Rider`), the road-results ID is lost.

4. **Phase 5 scope creep into UI.** Adding a data source badge and last-refreshed timestamp to `race_preview.py` is useful but introduces Streamlit UI work into a sprint that the intent document describes as "primarily new data acquisition, not architectural changes." The UI changes depend on `get_race_preview()` returning new metadata, which couples Phase 5 to Phase 4's queries work. If Phase 4 slips, Phase 5 is blocked.

5. **`fetch_pre_registration` returning `list[dict] | str` is a code smell.** The method returns either a parsed JSON list or a raw HTML string depending on which path succeeds. This union type pushes parsing-strategy decisions to the caller and makes the return type unpredictable. Better: have two methods (`fetch_pre_registration_json`, `fetch_pre_registration_html`) or have the method always return parsed dicts by handling both paths internally.

6. **Missing `points` column on `Startlist`.** Like the Codex draft, only `carried_points` is added. The `Result` model stores both `points` and `carried_points`. If road-results pre-reg data includes both (likely, since the JSON API returns both), the `points` field should also be stored on `Startlist` for parity.

7. **Open question #7 is over-cautious.** The recommendation to "compute and store the checksum, but always write the full startlist regardless" adds code complexity (computing the checksum) with zero immediate benefit. Either use the checksum to skip writes or don't compute it yet. Collecting data "to determine whether skip-on-unchanged is worth building" is premature instrumentation -- the answer is obvious: if the checksum matches, skip the write.

### Gaps in Risk Analysis

1. **No risk for Prong 2 failure modes.** The series-based forward lookup could discover a completely unrelated race at an estimated ID, leading to incorrect series linking. There is no validation step described to confirm that a discovered race ID actually belongs to the expected series before associating them.

2. **No risk for `RaceResultParser` raising `NoResultsError` on empty JSON.** Same issue as the Codex draft: the existing parser throws on empty data (line 128 of `parsers.py`). The `fetch_pre_registration` method must handle this.

3. **No risk for the `UpcomingRaceParser` depending on a date format that varies by region.** Road-results may format dates differently for BC (region 12) vs. PNW (region 4), or the region listing may not include dates in a parseable format. The existing `RacePageParser._parse_date()` handles `Mon DD YYYY` but the region listing may use a different format.

4. **Understated risk for "Pre-registration data is sparse."** Marked "High likelihood, Low impact" which is correct, but the mitigation ("UI can note 'Pre-registration data may be incomplete'") is not reflected in any phase's task list. It is mentioned but not implemented.

### Missing Edge Cases

1. **Same edge cases as Codex:** non-road disciplines in region listings, `CarriedPoints = 0` vs. None, paginated region listings.
2. **Prong 2 discovering a race that belongs to a different series** at the estimated ID range. No name-matching verification is described.
3. **`Rider` auto-creation from pre-reg data.** The draft says "create `Rider` if not found" in Phase 2 tasks. This could create `Rider` rows with incomplete data (no historical results, no `mu`/`sigma` ratings). These phantom riders would appear in category-wide queries (Tier 3 predictions) with no meaningful ranking data.
4. **Race edition that changes date after initial discovery.** If road-results updates a race date, the `is_stale_edition` check uses the cached `Race.date`. The refresh system would use the old date, potentially blocking a refresh that should be allowed.

### Definition of Done Completeness

The DoD is well-structured and covers Data Acquisition, Data Model, Refresh Policy, CLI, Predictions, UI, and Testing. Compared to Codex:

- **Better: includes UI verification items** (source badge, timestamp, graceful empty state).
- **Better: includes "Test coverage remains > 85%"** as a measurable threshold.
- **Missing: `ruff check` appears in Testing but not as prominently as Codex.**
- **Missing: end-to-end pipeline verification** (same gap as Codex).
- **Missing: schema migration on existing database** (same gap as Codex).
- **Weaker: "All existing tests pass without modification"** -- this is aspirational but may conflict with reality. If `test_startlists.py` imports from `startlists.py` and the module's public API changes (new functions, deprecated functions), existing tests may need updates. Codex's "All existing tests pass" is equally aspirational but less explicitly stated.

### Implementation Phasing Assessment

The five-phase structure is sound. Phase 1 (discovery) -> Phase 2 (pre-reg data) -> Phase 3 (refresh policy) -> Phase 4 (CLI) -> Phase 5 (predictions + UI) follows a logical dependency chain. However:

- **Phase 4 (CLI) should come earlier.** The CLI is the primary user interface for this sprint. Deferring it to Phase 4 means the first three phases produce code with no way to exercise it outside of tests. Moving CLI wiring to Phase 2 (alongside the data extraction code it depends on) would enable manual testing earlier.
- **Phase 5 is overloaded.** It contains both prediction integration (core data pipeline) and UI updates (presentation layer). These have different risk profiles. Splitting into Phase 5a (predictions) and Phase 5b (UI) would allow predictions to land even if UI work is cut.

---

## Recommendation

**The Codex draft has stronger implementation detail; the Gemini draft has better architecture and resilience thinking. The merged sprint should use Codex's concrete task structure with Gemini's architectural ideas.**

### Key decisions for the merge

1. **Module organization: follow Gemini.** Add road-results functions to existing `calendar_feed.py` and `startlists.py` rather than creating parallel modules. This matches the intent document's "REPLACE" language and avoids import confusion.

2. **Discovery strategy: use Codex's single-prong approach (region listing + date filtering).** Gemini's Prong 2 (series-based forward lookup) is creative but speculative and expensive. Defer it unless Prong 1 proves insufficient during implementation.

3. **Parser strategy: reuse `RaceResultParser` with a filter function.** Neither a new `StartlistParser` (Codex) nor an `UpcomingRaceParser` (Gemini) is justified until the JSON endpoint is tested against a real upcoming race. A 10-line filter function that selects entries without `Place`/`RaceTime` from `RaceResultParser.results()` is the right starting point.

4. **Refresh logic: build in Phase 1 alongside `RefreshLog`.** Don't defer `should_refresh` and `is_refreshable_edition` to Phase 3 (Codex) or Phase 3 (Gemini). Co-locate the model and its logic.

5. **Store `road_results_racer_id` on Startlist (from Codex).** Gemini misses this. The raw identifier is essential for debugging and rider reconciliation.

6. **Include UI updates (from Gemini).** The data source badge and last-refreshed timestamp are low-effort, high-value additions that complete the user-facing story.

7. **Fix the `NoResultsError` gap** that both drafts miss. The existing `RaceResultParser.results()` raises on empty data. All callers in this sprint must catch it and return empty lists.

8. **Drop the `UniqueConstraint` on `RefreshLog`** (Codex's `uq_refresh_per_type_time` is meaningless with microsecond timestamps). Keep the index for query performance.

9. **Add `points` column to `Startlist`** alongside `carried_points`. Both are available from the JSON API; both are already stored on `Result`.
