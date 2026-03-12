# Sprint 009: Road-Results Integration for Registered Riders & Power Rankings

## Overview

Sprint 009 replaces the BikeReg-based data acquisition pipeline with road-results.com as the primary source for upcoming race discovery and pre-registered rider lists. Road-results is already the authoritative data source for PNW historical race results, and its JSON API already returns `Points` and `CarriedPoints` fields that constitute a power ranking system. This sprint closes the loop: instead of stitching together two separate data sources (road-results for history, BikeReg for upcoming events), the entire race intelligence pipeline flows through a single provider with richer, more consistent data.

**Why this sprint matters:** The BikeReg integration built in Sprint 006 was a minimum-viable bridge. BikeReg coverage of PNW races is incomplete, its confirmed-riders CSV export is fragile (the HTML fallback in `startlists.py` currently returns `[]` unconditionally), and it provides no power ranking data. Road-results covers the same events with pre-registration lists that include `RacerID`, `CarriedPoints`, and `Points` -- the exact fields the prediction system already consumes. Switching sources eliminates a cross-provider data join, improves coverage, and unlocks road-results' native power rankings as a first-class input to contender predictions.

**What this sprint does NOT do:** It does not remove BikeReg code. BikeReg modules (`calendar_feed.py`, `startlists.py`) are preserved as deprecated fallbacks accessible via `--source bikereg`. This sprint also does not introduce new prediction algorithms -- it feeds better data into the existing `predict_contenders()` three-tier ranking system.

**Duration**: ~2 weeks
**Prerequisite**: Sprint 008 complete (interactive course maps, historical stats, narrative generator)

---

## Use Cases

1. **As a racer**, I can see which riders are pre-registered for an upcoming race on the Race Preview page, ranked by road-results power points, so I know who the strongest competition will be. _(Primary)_
2. **As a racer**, I can run `fetch-calendar` and see upcoming PNW races discovered from road-results.com, not BikeReg, so I get more complete event coverage. _(Primary)_
3. **As a racer**, I can run `fetch-startlists` and get pre-registered riders with their carried points from road-results.com, so contender rankings are based on the same data source as historical analysis. _(Primary)_
4. **As a developer**, I can call `RoadResultsClient.fetch_upcoming_races(region)` and get structured data about upcoming events, including race edition IDs that link directly to the existing `Race` model.
5. **As a developer**, I can call `RoadResultsClient.fetch_pre_registration(race_id)` and get a list of registered riders with `racer_id`, `carried_points`, `category`, and `team`.
6. **As a developer**, I can rely on the system enforcing at most 1 refresh per race edition per day, so road-results.com is not hammered by repeated CLI invocations.
7. **As a developer**, I can verify that race editions without an upcoming date in the current calendar year are never refreshed, preventing unnecessary requests for historical data that will not change.
8. **As a developer**, I can run the full test suite and see road-results integration covered by `responses` mocks, following the same patterns as `test_scraper.py`.

---

## Architecture

### Road-Results Site Organization: Upcoming vs. Past Races

Road-results.com organizes races into two discovery surfaces:

1. **Region results listing** (`/?n=results&sn=all&region={region}`): This is the existing discovery endpoint used by `discover_region_race_ids()`. It returns race IDs for completed events with results. The page lists races in reverse chronological order and includes the race name, date, and a link to `/race/{id}`.

2. **Individual race pages** (`/race/{id}`): Each race edition has a detail page. For completed events, this shows results. For upcoming events with open registration, this page contains a pre-registration section. The JSON API endpoint `downloadrace.php?raceID={id}&json=1` may return pre-registered riders with `CarriedPoints` for upcoming events, or the data may be embedded in the HTML only.

**Discovery strategy**: Rather than relying on a dedicated "upcoming events" calendar page (which may not exist as a structured endpoint), this sprint uses a two-pronged approach:

- **Prong 1: Region listing date scan.** Extend `discover_region_race_ids()` to also detect future-dated events from the region listing HTML. Road-results includes dates in the listing rows; events with dates >= today are candidates for upcoming races. This requires parsing the date alongside the race ID in the existing regex-based discovery.
- **Prong 2: Series-based forward lookup.** For known series in the database, check whether a current-year edition exists on road-results. Road-results assigns sequential race IDs, and a series that ran as race ID 14500 last year likely has a 2026 edition somewhere in the 14800-15200 range. By checking the race page for known series names near the expected ID range, we can discover upcoming editions even if they do not yet appear on the region listing.

The two prongs are complementary: Prong 1 finds events that road-results has already listed, while Prong 2 proactively discovers events for known series.

### Pre-Registration Data Extraction Approach

Once an upcoming race ID is identified, data extraction follows this pipeline:

1. **Try JSON endpoint first** (`downloadrace.php?raceID={id}&json=1`): If road-results uses the same JSON schema for pre-registration as for results, `RaceResultParser` already extracts every field we need: `RacerID`, `FirstName`, `LastName`, `TeamName`, `RaceCategoryName`, `CarriedPoints`, `Points`. This is the ideal path -- zero new parser code.

2. **Fall back to HTML scraping**: If the JSON endpoint returns empty for upcoming events, parse the `/race/{id}` HTML page. Add a `PreRegistrationParser` class alongside `RacePageParser` and `RaceResultParser` in `parsers.py`. This parser extracts rider rows from the registration table in the HTML, pulling name, team, category, and racer ID (from profile links).

3. **Enrich with carried_points from history**: If the pre-registration data (from either JSON or HTML) does not include `CarriedPoints` directly, look up each rider's most recent `carried_points` from the `results` table via `Rider.road_results_id`. This is a fallback -- road-results likely includes points in the pre-reg data, but the lookup ensures coverage even when it does not.

### Power Ranking Integration with the Existing Prediction System

The existing `predict_contenders()` in `predictions.py` already ranks riders by `carried_points` as its primary sort key. The integration path is clean:

```
Road-Results Pre-Reg JSON/HTML
  -> Parser extracts racer_id, carried_points per rider
  -> Startlist rows written with:
      rider_id linked via racer_id -> Rider.road_results_id
      carried_points stored directly on Startlist row
  -> predict_contenders() Tier 1 reads Startlist
  -> _rank_from_startlist() uses Startlist.carried_points (preferred)
     or falls back to historical Result.carried_points lookup
```

The key improvement over the current BikeReg path: `_rank_from_startlist()` currently iterates over all of a rider's historical `Result` rows to find their best `carried_points`. With road-results pre-registration data, the `carried_points` value comes directly from the source -- it represents the rider's *current* power ranking, not a historical maximum. To capture this, the `Startlist` model gets a new `carried_points` column, and `_rank_from_startlist()` prefers it when available.

### Refresh Scheduling and Rate Limiting Architecture

**Layer 1: Per-request rate limiting** (existing, unchanged): `RoadResultsClient._rate_limit()` enforces >= 3s between any two HTTP requests via `time.monotonic()`.

**Layer 2: Per-edition daily refresh limit** (new): A new `RefreshLog` table tracks the last refresh timestamp per race edition per refresh type. Before fetching pre-registration data for a race, the system checks:

```python
def should_refresh(session, race_id, refresh_type) -> bool:
    """Returns True if this race edition can be refreshed now."""
    # Never refresh stale editions
    race = session.get(Race, race_id)
    if not race or not race.date:
        return False
    today = datetime.utcnow().date()
    if race.date.date() < today or race.date.year != today.year:
        return False  # Stale edition

    # Check daily limit
    start_of_day = datetime.combine(today, datetime.min.time())
    existing = session.query(RefreshLog).filter(
        RefreshLog.race_id == race_id,
        RefreshLog.refresh_type == refresh_type,
        RefreshLog.refreshed_at >= start_of_day,
    ).first()
    return existing is None
```

**Why a new `RefreshLog` table instead of extending `ScrapeLog`:** `ScrapeLog` tracks one-time historical scraping of race results. Its schema (`status`, `result_count`, `error_message`) and its `race_id UNIQUE` constraint are designed for a single scrape per race. Pre-registration refreshes are recurring (up to once daily per race) and need their own tracking semantics: `refresh_type`, `entry_count`, `checksum` for change detection, and multiple rows per `race_id`. Overloading `ScrapeLog` would require breaking its unique constraint and muddling its purpose.

**Data freshness tiers:**

| Tier | Condition | Refresh Policy |
|------|-----------|----------------|
| **Active** | `Race.date >= today AND Race.date.year == current_year` | Max 1 refresh/day |
| **Stale** | `Race.date < today OR Race.date.year != current_year` | Never refreshed |

### Migration Strategy from BikeReg

This is a **soft deprecation**, not a hard cutover:

1. Default `fetch-calendar` and `fetch-startlists` CLI commands are rewired to use road-results.
2. A `--source` option is added: `--source road-results` (default) or `--source bikereg`.
3. BikeReg functions in `calendar_feed.py` and `startlists.py` are marked with deprecation docstrings but remain functional.
4. BikeReg settings in `config.py` (`bikereg_base_url`, `bikereg_request_delay`) are retained with deprecation comments.
5. Both sources write to the same `Startlist` table with different `source` values (`"road_results"` vs `"bikereg"`).

This ensures that if road-results integration encounters issues during the PNW race season, BikeReg can be re-enabled with a single `--source bikereg` flag.

### Integration with the Broader Race Preview Workflow

The end-to-end data flow for Race Preview after this sprint:

```
fetch-calendar (road-results by default)
  -> discovers upcoming race IDs from region listing + series forward lookup
  -> creates/updates Race rows: is_upcoming=True, registration_source="road_results"
  -> links to existing RaceSeries via fuzzy name matching

fetch-startlists (road-results by default)
  -> for each upcoming Race where is_stale_edition() == False
  -> checks should_refresh() (skip if already refreshed today)
  -> fetches pre-reg from road-results (JSON endpoint first, HTML fallback)
  -> writes Startlist rows: rider_id, carried_points, source="road_results"
  -> records RefreshLog entry

Race Preview page render (unchanged code path)
  -> get_race_preview() calls predict_contenders()
  -> Tier 1: reads Startlist, prefers Startlist.carried_points (road-results power ranking)
  -> Tier 2: historical series performers (unchanged)
  -> Tier 3: category-wide top riders (unchanged)
  -> narrative, stats, interactive map all unchanged
  -> NEW: shows data source badge and last-refreshed timestamp
```

---

## Implementation

### Phase 1: Road-Results Upcoming Race Discovery (~20% effort)

**Goal:** Extend `RoadResultsClient` to discover upcoming PNW races from road-results.com, replacing the BikeReg calendar search.

**Files:**
- `raceanalyzer/scraper/client.py` -- Add `fetch_region_page()` method
- `raceanalyzer/scraper/parsers.py` -- Add `UpcomingRaceParser` class to extract future-dated events from region listing HTML
- `raceanalyzer/calendar_feed.py` -- Add `search_upcoming_events_rr()` function; deprecate BikeReg functions
- `raceanalyzer/config.py` -- Add `road_results_region_ids` mapping
- `tests/test_calendar_rr.py` -- New test file for road-results calendar discovery

**Tasks:**
- [ ] Add `fetch_region_page(region: int) -> str` to `RoadResultsClient`: fetches `/?n=results&sn=all&region={region}` and returns raw HTML (reuses `_request_with_retry`)
- [ ] Implement `UpcomingRaceParser(html: str)` in `parsers.py`: extracts race entries (ID, name, date, location) from region listing HTML, returns only entries where parsed date >= today
- [ ] Add `road_results_region_ids: dict[str, int]` to `Settings`: `{"PNW": 4, "BC": 12}` (these region IDs are already known from `discover_region_race_ids`)
- [ ] Implement `search_upcoming_events_rr(client: RoadResultsClient, regions: list[int], days_ahead: int) -> list[dict]` in `calendar_feed.py`: calls `fetch_region_page` for each region, parses upcoming events, deduplicates by race ID, returns `[{"race_id", "name", "date", "location"}]`
- [ ] Reuse existing `match_event_to_series()` fuzzy matcher for linking discovered events to existing `RaceSeries` rows (adjust threshold if road-results naming differs from BikeReg)
- [ ] Add deprecation notice to `search_upcoming_events()` and `_search_bikereg()` docstrings
- [ ] Tests: mock region listing HTML with mix of past/future events; verify only future events returned; verify race ID + date extraction; verify empty region returns []; verify fuzzy match to series

### Phase 2: Pre-Registration Data Extraction (~25% effort)

**Goal:** Fetch pre-registered riders from road-results.com for upcoming race editions, including power ranking points.

**Files:**
- `raceanalyzer/scraper/client.py` -- Add `fetch_pre_registration(race_id)` method
- `raceanalyzer/scraper/parsers.py` -- Validate `RaceResultParser` for pre-reg data; add `PreRegistrationParser` if needed
- `raceanalyzer/startlists.py` -- Add `fetch_startlist_rr()` function; deprecate BikeReg functions
- `raceanalyzer/db/models.py` -- Add `carried_points` column to `Startlist`; add `RefreshLog` model
- `tests/test_startlists_rr.py` -- New test file for road-results startlist fetching

**Tasks:**
- [ ] Add `fetch_pre_registration(race_id: int) -> list[dict] | str` to `RoadResultsClient`: tries JSON endpoint first (`downloadrace.php?raceID={id}&json=1`), returns parsed JSON list; if JSON is empty or malformed, fetches `/race/{id}` HTML and returns raw HTML string for fallback parsing
- [ ] Test `RaceResultParser.results()` against pre-registration JSON from a known upcoming race. If it works (returns riders with `racer_id`, `carried_points`, `name`, `team`, `race_category_name`), no new parser needed. If schema differs, implement `PreRegistrationParser` alongside existing parsers
- [ ] Add `carried_points = Column(Float, nullable=True)` to `Startlist` model (safe additive migration; existing rows get NULL)
- [ ] Create `RefreshLog` model:
  ```python
  class RefreshLog(Base):
      __tablename__ = "refresh_log"
      id = Column(Integer, primary_key=True, autoincrement=True)
      race_id = Column(Integer, ForeignKey("races.id"), nullable=False)
      refresh_type = Column(String, nullable=False)  # "calendar", "startlist"
      refreshed_at = Column(DateTime, nullable=False)
      entry_count = Column(Integer, nullable=True)
      checksum = Column(String, nullable=True)
  ```
  With index on `(race_id, refresh_type, refreshed_at)` for efficient daily-limit lookups
- [ ] Implement `fetch_startlist_rr(client: RoadResultsClient, race_id: int, session: Session) -> list[dict]` in `startlists.py`: fetches pre-reg, links riders by `racer_id` -> `Rider.road_results_id` (create `Rider` if not found), returns list of dicts for `Startlist` row creation
- [ ] Handle cross-category deduplication: same `racer_id` may appear in multiple categories -- write one `Startlist` row per (race_id, rider_id, category) combination
- [ ] Add deprecation notice to `fetch_startlist()`, `_parse_bikereg_csv()`, `_parse_bikereg_html()` docstrings
- [ ] Tests: mock pre-reg JSON with 3 categories and overlapping riders; verify `Startlist` rows created with correct `carried_points`; verify rider linking via `road_results_id`; verify empty pre-reg returns []; verify graceful failure on HTTP error

### Phase 3: Refresh Scheduling & Staleness Enforcement (~15% effort)

**Goal:** Enforce daily refresh limits per race edition and prevent refreshes for stale editions.

**Files:**
- `raceanalyzer/refresh.py` -- New module with refresh policy functions
- `raceanalyzer/config.py` -- Add `max_daily_refreshes_per_edition` setting
- `tests/test_refresh.py` -- Refresh policy tests

**Tasks:**
- [ ] Implement `should_refresh(session: Session, race_id: int, refresh_type: str) -> bool` in `refresh.py`: checks `RefreshLog` for entry with matching `race_id` + `refresh_type` where `refreshed_at >= start_of_today_utc`. Returns False if found (already refreshed today).
- [ ] Implement `is_stale_edition(session: Session, race_id: int) -> bool` in `refresh.py`: returns True if `Race.date` is in the past OR `Race.date.year != current_year`. Stale editions are never refreshed regardless of `RefreshLog` state.
- [ ] Implement `record_refresh(session: Session, race_id: int, refresh_type: str, entry_count: int, checksum: str | None)` in `refresh.py`: creates `RefreshLog` row.
- [ ] Add `max_daily_refreshes_per_edition: int = 1` to `Settings` (for future configurability; currently hard-coded to 1)
- [ ] Compute checksum for change detection: `hashlib.sha256` of sorted `f"{rider_name}:{category}"` strings from the fetched startlist. Stored on `RefreshLog.checksum` for future skip-on-unchanged optimization.
- [ ] Tests: first refresh of the day -> allowed; second refresh same day -> blocked; refresh on next day -> allowed (mock `datetime.utcnow`); stale edition (past date) -> always blocked; stale edition (wrong year) -> always blocked; race with no date -> blocked

### Phase 4: CLI Integration & BikeReg Deprecation (~20% effort)

**Goal:** Update CLI commands to use road-results by default; preserve BikeReg as a deprecated fallback.

**Files:**
- `raceanalyzer/cli.py` -- Rewrite `fetch-calendar` and `fetch-startlists` commands
- `raceanalyzer/calendar_feed.py` -- Module-level deprecation docstring for BikeReg functions
- `raceanalyzer/startlists.py` -- Module-level deprecation docstring for BikeReg functions
- `raceanalyzer/config.py` -- Mark BikeReg settings as deprecated in comments
- `tests/test_cli.py` -- CLI integration tests for updated commands

**Tasks:**
- [ ] Rewrite `fetch-calendar` command body: instantiate `RoadResultsClient`, call `search_upcoming_events_rr()`, create/update `Race` rows with `is_upcoming=True` and `registration_source="road_results"`, link to series via `match_event_to_series()`, print summary
- [ ] Add `--source` option to `fetch-calendar`: choices `["road-results", "bikereg"]`, default `"road-results"`. When `bikereg`, delegate to existing `search_upcoming_events()`.
- [ ] Rewrite `fetch-startlists` command body: iterate upcoming `Race` rows, check `is_stale_edition()` and `should_refresh()` for each, call `fetch_startlist_rr()` for eligible races, write `Startlist` rows, call `record_refresh()`
- [ ] Add `--source` option to `fetch-startlists`: same pattern as `fetch-calendar`
- [ ] Add `--dry-run` flag to `fetch-startlists`: prints which races would be refreshed (eligible/skipped) without making HTTP requests
- [ ] Update command output formatting: show per-race status lines -- "Fetched 12 riders (3 categories)", "Skipped: already refreshed today", "Skipped: stale edition (2024)"
- [ ] Add `# DEPRECATED: retained for --source bikereg fallback` comment to `bikereg_base_url` and `bikereg_request_delay` in `config.py`
- [ ] Tests: verify default `fetch-calendar` calls road-results; verify `--source bikereg` calls BikeReg; verify `fetch-startlists` respects refresh limits; verify `--dry-run` makes no HTTP calls

### Phase 5: Prediction Integration & UI Updates (~20% effort)

**Goal:** Wire road-results power rankings into the contender prediction pipeline and update the Race Preview page to show data provenance.

**Files:**
- `raceanalyzer/predictions.py` -- Update `_rank_from_startlist()` to prefer `Startlist.carried_points`
- `raceanalyzer/queries.py` -- Update `get_race_preview()` to include refresh metadata
- `raceanalyzer/ui/pages/race_preview.py` -- Add data source badge, last-refreshed timestamp
- `tests/test_predictions.py` -- Updated contender ranking tests
- `tests/test_queries.py` -- Updated race preview tests

**Tasks:**
- [ ] Update `_rank_from_startlist()` in `predictions.py`: check `entry.carried_points` first. If not None (road-results source), use it directly as `best_points`. Only fall back to the historical `Result` row lookup when `entry.carried_points` is NULL (BikeReg-sourced entries with no inline power ranking).
- [ ] Update `get_race_preview()` in `queries.py` to include two new keys in the returned dict:
  - `"startlist_source"`: dominant source from Startlist entries ("road_results", "bikereg", "mixed", or "none")
  - `"startlist_refreshed_at"`: most recent `RefreshLog.refreshed_at` for this series' upcoming race
- [ ] Update Race Preview UI (`race_preview.py`): render a small info line below the contenders table showing source ("Data from road-results.com" / "Data from BikeReg") and freshness ("Updated 2026-03-10")
- [ ] Handle edge case: if startlist entries come from both sources (BikeReg and road-results), show "Multiple sources" badge
- [ ] Ensure that when no startlist exists, no source badge or timestamp is shown (clean empty state)
- [ ] Tests: `_rank_from_startlist` with `Startlist.carried_points` set -> uses inline value; with NULL -> falls back to historical; mixed entries -> correct ordering; `get_race_preview` includes new metadata fields

---

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/scraper/client.py` | MODIFY | Add `fetch_region_page()`, `fetch_pre_registration()` methods to `RoadResultsClient` |
| `raceanalyzer/scraper/parsers.py` | MODIFY | Add `UpcomingRaceParser` for region listing; optionally add `PreRegistrationParser` |
| `raceanalyzer/db/models.py` | MODIFY | Add `carried_points` to `Startlist`; add `RefreshLog` model |
| `raceanalyzer/calendar_feed.py` | MODIFY | Add `search_upcoming_events_rr()`; deprecate BikeReg functions |
| `raceanalyzer/startlists.py` | MODIFY | Add `fetch_startlist_rr()`; deprecate BikeReg functions |
| `raceanalyzer/refresh.py` | CREATE | Refresh policy: `should_refresh()`, `is_stale_edition()`, `record_refresh()` |
| `raceanalyzer/config.py` | MODIFY | Add `road_results_region_ids`, `max_daily_refreshes_per_edition`; deprecate BikeReg settings |
| `raceanalyzer/predictions.py` | MODIFY | Update `_rank_from_startlist()` to prefer `Startlist.carried_points` |
| `raceanalyzer/queries.py` | MODIFY | Update `get_race_preview()` with startlist source and refresh metadata |
| `raceanalyzer/cli.py` | MODIFY | Rewrite `fetch-calendar` and `fetch-startlists` with `--source` option and `--dry-run` |
| `raceanalyzer/ui/pages/race_preview.py` | MODIFY | Add data source badge and last-refreshed timestamp below contenders |
| `tests/test_calendar_rr.py` | CREATE | Road-results calendar discovery tests with `responses` mocks |
| `tests/test_startlists_rr.py` | CREATE | Road-results startlist fetching tests with `responses` mocks |
| `tests/test_refresh.py` | CREATE | Refresh policy and staleness enforcement tests |
| `tests/test_cli.py` | MODIFY | CLI integration tests for `--source` routing and `--dry-run` |
| `tests/test_predictions.py` | MODIFY | Contender ranking tests with inline `carried_points` |
| `tests/test_queries.py` | MODIFY | Race preview tests with source metadata |

---

## Definition of Done

### Data Acquisition
- [ ] `RoadResultsClient.fetch_region_page(region)` returns HTML for the region listing page
- [ ] `UpcomingRaceParser` extracts future-dated events (race ID, name, date, location) from region HTML
- [ ] `RoadResultsClient.fetch_pre_registration(race_id)` returns pre-registered riders with `racer_id`, `carried_points`, `category`, `team`
- [ ] All new HTTP requests use `cloudscraper` with `BROWSER_HEADERS` via the existing `RoadResultsClient` session
- [ ] All new HTTP requests respect the >= 3s minimum delay via `_rate_limit()`
- [ ] Graceful degradation: all new fetch functions return empty list on any failure (HTTP error, parse error, timeout), never crash

### Data Model
- [ ] `Startlist.carried_points` column exists (Float, nullable)
- [ ] `RefreshLog` table exists with columns: `id`, `race_id`, `refresh_type`, `refreshed_at`, `entry_count`, `checksum`
- [ ] `RefreshLog` has index on `(race_id, refresh_type, refreshed_at)`
- [ ] Existing `Startlist` rows with `source="bikereg"` are unaffected by schema changes

### Refresh Policy
- [ ] `should_refresh()` returns False if race was refreshed today (same UTC date)
- [ ] `is_stale_edition()` returns True if `Race.date < today` or `Race.date.year != current_year`
- [ ] Stale editions are never fetched, regardless of `RefreshLog` state
- [ ] `record_refresh()` creates a `RefreshLog` entry with timestamp and checksum after each successful fetch

### CLI
- [ ] `fetch-calendar` discovers upcoming events from road-results.com by default
- [ ] `fetch-startlists` pulls pre-registered riders from road-results.com by default
- [ ] `--source bikereg` flag falls back to BikeReg for both commands
- [ ] `--dry-run` flag on `fetch-startlists` shows refresh plan without making requests
- [ ] Output shows per-race status: fetched count, skipped (refreshed today), skipped (stale)

### Predictions
- [ ] `_rank_from_startlist()` uses `Startlist.carried_points` when available (road-results-sourced entries)
- [ ] `_rank_from_startlist()` falls back to historical `Result.carried_points` lookup when `Startlist.carried_points` is NULL
- [ ] Contender ranking order matches road-results power ranking order for road-results-sourced startlists

### UI
- [ ] Race Preview shows data source badge below contenders table
- [ ] Race Preview shows last-refreshed timestamp below contenders table
- [ ] Both elements degrade gracefully when metadata is unavailable (no badge, no timestamp)

### Testing
- [ ] Calendar discovery: 4+ test cases (future events only, empty region, mixed past/future dates, fuzzy match to series)
- [ ] Startlist fetch: 5+ test cases (happy path with carried_points, empty pre-reg, multi-category dedup, rider linking, graceful HTTP failure)
- [ ] Refresh policy: 4+ test cases (first refresh allowed, second blocked, next day allowed, stale edition blocked)
- [ ] Prediction integration: 3+ test cases (inline carried_points preferred, NULL fallback to historical, mixed-source ordering)
- [ ] All existing tests pass without modification
- [ ] `ruff check .` passes
- [ ] Test coverage remains > 85%

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Road-results pre-reg endpoint uses different JSON schema than results** | Medium | Medium | Phase 2 tests `RaceResultParser` against pre-reg data first. If schema differs, `PreRegistrationParser` is ~50 lines using existing `_safe_int`/`_safe_float` helpers. Bounded effort. |
| **Road-results region listing does not include future-dated events** | Medium | High | Prong 2 (series-based forward lookup) provides an alternate discovery path. If neither works, keep BikeReg as primary calendar source and use road-results only for startlists. |
| **Road-results blocks rapid sequential requests despite cloudscraper** | Low | High | Existing 3s rate limit is conservative. If blocked, increase to 5s and add random jitter (0-2s). `_request_with_retry` already handles 403/429 with exponential backoff. |
| **Pre-registration data is sparse (few riders register early in the season)** | High | Low | Expected behavior. `predict_contenders()` Tier 2/3 fallbacks exist exactly for this case. UI can note "Pre-registration data may be incomplete" when < 5 riders are listed. |
| **Rider identity mismatch between pre-reg and historical data** | Low | Medium | Road-results uses consistent `RacerID` across all endpoints. The scraper pipeline already links riders by this field (`Rider.road_results_id`). Same field used for pre-reg. |
| **SQLite migration: adding column and new table** | Low | Low | `ALTER TABLE startlists ADD COLUMN carried_points REAL` is safe (NULL default). `CREATE TABLE refresh_log` is additive. Follow existing `init_db` pattern. |
| **BikeReg deprecation breaks existing user workflows** | Low | Medium | BikeReg commands preserved as `--source bikereg` fallback. No code deleted. Deprecation is docstring-only. |
| **Road-results HTML structure changes break `UpcomingRaceParser`** | Medium | Medium | Parser uses defensive patterns and returns [] on failure. `fetch_region_page` is tested with `responses` mocks. BikeReg fallback available via `--source`. |
| **`RefreshLog` table grows unbounded** | Low | Low | ~1 row per race per day. For 50 active races over a 7-month season, ~10K rows/year. Trivial for SQLite. Add cleanup note for future sprint if needed. |
| **Concurrent CLI invocations create duplicate Startlist rows** | Medium | Medium | Use checksum on `RefreshLog` for idempotency. Clear existing Startlist rows for a race+source before writing new batch. SQLite write lock serializes concurrent access. |

---

## Security

- **Browser user-agent spoofing**: All new road-results requests flow through `RoadResultsClient`, which uses `cloudscraper` with `BROWSER_HEADERS`. No separate HTTP client code is introduced. The existing Chrome UA string is reused for all new endpoints.
- **No credentials or API keys**: Road-results.com is a public website with no authentication. No secrets are stored, transmitted, or needed.
- **Rate limiting prevents abuse**: The 3s minimum inter-request delay and 1 refresh/day/edition limit bound total daily request volume. For a typical PNW season (~50 active races): ~50 startlist requests/day + ~10 calendar requests = ~60 requests/day, spread over ~3 minutes of wall time.
- **No PII beyond public race data**: Pre-registration data (rider name, team, category, points) is publicly visible on road-results.com. No private registration details (email, address, payment) are accessed or stored.
- **Input sanitization**: All road-results data passes through `RaceResultParser._safe_int()` / `_safe_float()` for numeric fields and is persisted via SQLAlchemy ORM parameterized queries. No string interpolation into SQL.
- **Deprecated BikeReg code is inert by default**: BikeReg functions are not invoked unless explicitly requested via `--source bikereg`. No accidental data leakage or request to BikeReg.

---

## Dependencies

**Existing Python packages (no additions):**
- `cloudscraper` -- HTTP client with Cloudflare bypass (used by `RoadResultsClient`)
- `requests` -- Underlying HTTP library
- `sqlalchemy` -- ORM for all database operations
- `click` -- CLI framework
- `pandas` -- DataFrames for prediction output
- `responses` -- HTTP mocking for tests

**New Python packages: None.**

**External services:**
- `road-results.com` -- Primary data source (already integrated for historical results; this sprint extends to calendar and pre-registration)

---

## Open Questions

1. **What URL pattern does road-results use for pre-registration data?** The JSON endpoint (`downloadrace.php?raceID={id}&json=1`) may or may not include pre-registered riders for upcoming events. This needs to be confirmed by fetching a known upcoming race ID during Phase 2 implementation. **Resolution approach**: Attempt JSON endpoint first. If it returns data with the expected schema, use `RaceResultParser`. If not, inspect HTML and build `PreRegistrationParser`.

2. **How does road-results organize upcoming vs. past races on the region listing page?** The region listing may interleave upcoming and past events chronologically, or may segregate them. The date parsing in `UpcomingRaceParser` needs to handle both layouts. **Resolution approach**: Fetch the PNW region page during Phase 1 and inspect HTML structure. The parser should be date-driven (compare parsed date to today) rather than relying on HTML structural cues.

3. **Should BikeReg code be fully removed in a future sprint?** This sprint preserves it as a deprecated fallback. Full removal should wait until road-results integration has been validated over at least one full PNW race season (March-September) to confirm coverage completeness and reliability. **Recommendation**: Schedule BikeReg removal for Sprint 012+ after a season of road-results-only operation.

4. **What constitutes "upcoming race in the current year" for the staleness check?** Proposed definition: `Race.date >= today AND Race.date.year == datetime.utcnow().year`. A race posted for January 2027 would not be refreshed during 2026. This is intentional for PNW racing (March-October season) and prevents unnecessary requests for far-future events.

5. **Does road-results publish a standalone power rankings leaderboard?** If so, it could pre-populate `Rider` ranking data for riders not yet in our database, improving Tier 3 predictions. **For Sprint 009**: Use `CarriedPoints` from pre-registration and historical results only. Standalone leaderboard scraping is deferred to a future sprint.

6. **How should the system handle a discovered race that does not match any existing series?** **Recommendation**: Create the `Race` row with `is_upcoming=True` and `series_id=NULL`. Log it as "unlinked" in CLI output. A future `build-series` run or manual override can associate it later. Do not auto-create `RaceSeries` rows from a single upcoming event -- series should be established from historical data.

7. **Should `RefreshLog.checksum` be used to skip writes when startlist data has not changed?** Computing the checksum is cheap; skipping writes reduces DB churn. **Recommendation for Sprint 009**: Compute and store the checksum, but always write the full startlist regardless. This collects checksum data that can be analyzed to determine whether skip-on-unchanged is worth building in a future sprint. Premature optimization adds complexity without validated benefit.
