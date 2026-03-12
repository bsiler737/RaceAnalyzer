# Sprint 009: Road-Results Integration for Registered Riders & Power Rankings

## Overview

Sprint 009 replaces BikeReg as the source for upcoming race discovery and pre-registered rider data with road-results.com, the primary data source the project already uses for historical results. The existing `RoadResultsClient` already handles browser-spoofed HTTP requests with rate limiting and retry logic; this sprint extends it with two new capabilities: (1) discovering upcoming races from the regional results listing, and (2) fetching pre-registered riders from individual race pages. It also adds daily refresh limiting so we don't hammer road-results for data that hasn't changed, and skips stale race editions that have no upcoming date in the current year.

**Why road-results over BikeReg:** BikeReg coverage is incomplete for PNW races, and its data doesn't include power rankings. Road-results already provides `CarriedPoints` (their Elo-like ranking system) in the JSON API, which `RaceResultParser` already parses. By sourcing startlists from road-results, we get `racer_id` linkage to historical results for free, and we can pull `carried_points` directly from the pre-registration data or look them up from the `results` table.

**What this sprint does NOT do:** It does not change `predictions.py`, `queries.py`, or the Race Preview UI. The `predict_contenders()` function already ranks by `carried_points` and consumes `Startlist` rows regardless of source. This sprint only changes where that data comes from.

**Duration**: ~1-2 weeks
**Prerequisite**: Sprint 008 complete (interactive course maps, historical stats, narrative generator)

---

## Use Cases

1. **As a racer**, I can run `fetch-calendar` and see upcoming PNW races discovered from road-results.com, matched to existing series in the database, so I can prepare for events without manually checking the website.
2. **As a racer**, I can run `fetch-startlists` and get pre-registered riders for upcoming races with their power ranking points, so the Race Preview contender predictions reflect who's actually signed up.
3. **As a developer**, I can call `RoadResultsClient.fetch_upcoming_race_ids(region)` to get race IDs for upcoming events in a region.
4. **As a developer**, I can call `RoadResultsClient.fetch_race_startlist(race_id)` to get pre-registered rider data including `racer_id` and `carried_points`.
5. **As an operator**, I can run `fetch-startlists` multiple times per day without worrying about excessive requests, because each race edition is refreshed at most once per 24 hours.
6. **As an operator**, I know that stale race editions (no upcoming date this year) are automatically skipped during refresh, preventing wasted requests.

---

## Architecture

### Road-Results URL Patterns and Data Discovery

Road-results.com serves PNW race data through several known URL patterns:

| Purpose | URL Pattern | Response | Already Used? |
|---------|------------|----------|---------------|
| Region listing | `/?n=results&sn=all&region=4` | HTML with race links | Yes (`discover_region_race_ids`) |
| Race page | `/race/{id}` | HTML with metadata | Yes (`fetch_race_page`) |
| Race results JSON | `/downloadrace.php?raceID={id}&json=1` | JSON array of results | Yes (`fetch_race_json`) |
| **Pre-registration** | `/race/{id}` (upcoming race page) | HTML with registered riders table | **New** |

**Upcoming race discovery strategy:** The existing `discover_region_race_ids()` method scrapes `/race/{id}` links from the region listing page. This page includes both past and upcoming races. For each discovered race ID, we fetch the race page HTML and parse the date. If the date is in the future (or within the current season window), it's an upcoming race. This is a two-step process: discover IDs, then filter by date.

**Pre-registration data:** Road-results.com shows pre-registered riders on the race page for upcoming events. The page contains a table of registered riders organized by category, with columns for Name, Team, City/State, and often RacerID links. The page may also serve this data through the same JSON endpoint (`/downloadrace.php?raceID={id}&json=1`) with `CarriedPoints` already populated -- this is the preferred path since `RaceResultParser` already handles this format. If the JSON endpoint returns empty for pre-reg (returns results only post-race), we fall back to HTML parsing.

**Key insight: try JSON first.** The `fetch_race_json()` call already exists and the parser already extracts `racer_id`, `carried_points`, `name`, `team`, and `race_category_name`. If road-results populates these fields before the race (likely, since `CarriedPoints` are pre-race data), we get the richest data with zero new parsing code. The HTML fallback is only needed if the JSON endpoint is empty for pre-registration.

### Daily Refresh Limiting

Rather than overloading `ScrapeLog` (which tracks historical scrape operations), create a dedicated `RefreshLog` table. This cleanly separates "we scraped historical results for race X" from "we refreshed the startlist for race X today."

```
refresh_log
  id              INTEGER PRIMARY KEY
  race_id         INTEGER NOT NULL
  refresh_type    STRING NOT NULL     -- "startlist", "calendar"
  refreshed_at    DATETIME NOT NULL
  result_count    INTEGER             -- number of entries fetched
  checksum        STRING              -- hash of response for change detection
```

Index on `(race_id, refresh_type)` for fast lookups. Before any fetch, query:
```sql
SELECT 1 FROM refresh_log
WHERE race_id = ? AND refresh_type = ?
AND refreshed_at > datetime('now', '-24 hours')
```

If a row exists, skip the refresh.

### Stale Edition Filtering

A race edition is "stale" if it doesn't have an upcoming date in the current calendar year. The rule: **skip refresh if `race.date IS NULL` OR (`race.date.year != current_year`) OR (`race.date < today`)**. This is checked before any HTTP request, using only local DB data.

For the calendar discovery step, stale filtering is implicit: we only create/update Race rows with future dates.

### BikeReg Deprecation Strategy

Keep `startlists.py` and `calendar_feed.py` in the codebase but rename them to `startlists_bikereg.py` and `calendar_feed_bikereg.py`. Remove all imports of these modules from `cli.py`. This preserves the code for reference without any runtime path reaching it. Remove `bikereg_base_url` and `bikereg_request_delay` from `Settings`. If road-results is ever unreachable, the graceful degradation returns empty results (same pattern BikeReg used) -- there's no benefit to falling back to BikeReg since its coverage is inferior.

### Data Flow Diagram

```
fetch-calendar:
  RoadResultsClient.discover_region_race_ids(region=4)
    -> list of race IDs (all regions, past + upcoming)
  For each race_id not in ScrapeLog:
    RoadResultsClient.fetch_race_page(race_id)
      -> parse date, name, location
    If date >= today:
      Create/update Race(is_upcoming=True, ...)
      match_event_to_series() -> link to existing RaceSeries

fetch-startlists:
  Query Race WHERE is_upcoming=True AND date.year == current_year AND date >= today
  For each race:
    Check RefreshLog: skip if refreshed in last 24h
    RoadResultsClient.fetch_race_json(race_id)
      -> if non-empty: parse with RaceResultParser (gets racer_id, carried_points)
      -> if empty: RoadResultsClient.fetch_race_page(race_id)
           -> parse HTML startlist table (gets name, team, racer_id)
           -> look up carried_points from results table by racer_id
    Upsert Startlist rows (source="road-results")
    Insert RefreshLog entry
```

---

## Implementation

### Phase 1: Extend RoadResultsClient & Calendar Discovery (~30% effort)

**Goal:** Discover upcoming PNW races from road-results.com and create/update Race rows with `is_upcoming=True`.

**Files:**
- `raceanalyzer/scraper/client.py` -- Add `fetch_upcoming_race_ids()` helper method
- `raceanalyzer/calendar_feed.py` -- Replace BikeReg implementation with road-results
- `raceanalyzer/cli.py` -- Update `fetch-calendar` command
- `raceanalyzer/config.py` -- Add road-results region ID setting, remove BikeReg settings
- `tests/test_calendar_feed.py` -- Rewrite tests for road-results

**Tasks:**
- [ ] Add `road_results_region_ids` setting to `Settings`: `tuple[int, ...] = (4, 12)` (PNW=4, BC=12)
- [ ] Remove `bikereg_base_url` and `bikereg_request_delay` from `Settings`
- [ ] Add `fetch_upcoming_race_ids(self, region: int, days_ahead: int = 60) -> list[dict]` to `RoadResultsClient`:
  - Call existing `discover_region_race_ids(region)` to get all race IDs
  - For each race_id, call `fetch_race_page(race_id)` and parse date with `RacePageParser`
  - Filter to races with `date >= today` and `date <= today + days_ahead`
  - Return `[{"race_id": int, "name": str, "date": datetime, "location": str, "state_province": str}]`
  - **Optimization:** Parse the region listing HTML directly for dates if embedded (avoid per-race HTTP calls). If the region listing page includes dates alongside race links (likely -- it's a results listing), extract them in one pass. Fall back to per-race fetching only if dates aren't in the listing.
- [ ] Rewrite `calendar_feed.py`:
  - Replace `search_upcoming_events()` signature to accept `client: RoadResultsClient, region_ids: tuple[int, ...], days_ahead: int`
  - Returns same `[{"name", "date", "url", "location", "race_id"}]` format
  - Keep `match_event_to_series()` unchanged (it's source-agnostic fuzzy matching)
  - Graceful degradation: return `[]` on any failure
- [ ] Update `fetch-calendar` CLI command:
  - Instantiate `RoadResultsClient` (reusing existing pattern from `scrape` command)
  - Call new `search_upcoming_events()` with road-results client
  - For matched events: create/update `Race` rows with `is_upcoming=True`, `registration_source="road-results"`, `url=f"{base_url}/race/{race_id}"`
  - For unmatched events: log but don't create Race rows (no series to link to)
  - Replace `--region` option (state code) with `--region-id` option (road-results region number, default=4)
- [ ] Rename `calendar_feed.py` (old BikeReg version) to `calendar_feed_bikereg.py` before rewriting
- [ ] Tests: mock region listing HTML, mock individual race page HTML, verify date filtering, verify `match_event_to_series` integration, verify `[]` on HTTP failure

### Phase 2: Pre-Registration Startlist Fetching (~30% effort)

**Goal:** Fetch pre-registered riders from road-results.com with their power ranking points.

**Files:**
- `raceanalyzer/scraper/client.py` -- Add `fetch_race_startlist()` method
- `raceanalyzer/scraper/parsers.py` -- Add `StartlistParser` for HTML fallback
- `raceanalyzer/startlists.py` -- Replace BikeReg implementation with road-results
- `raceanalyzer/cli.py` -- Update `fetch-startlists` command
- `tests/test_startlists.py` -- Rewrite tests for road-results

**Tasks:**
- [ ] Add `fetch_race_startlist(self, race_id: int) -> list[dict]` to `RoadResultsClient`:
  - **Primary path:** Call `fetch_race_json(race_id)`. If non-empty, parse with `RaceResultParser` and extract `name`, `team`, `racer_id`, `carried_points`, `race_category_name`
  - **Fallback path:** If JSON is empty, call `fetch_race_page(race_id)` and parse HTML for registered rider table
  - Returns `[{"name": str, "team": str, "racer_id": int|None, "carried_points": float|None, "category": str|None}]`
  - Dedup by `racer_id` (same rider in multiple categories -> keep each category entry)
- [ ] Add `StartlistParser` class to `parsers.py`:
  - Parses HTML race page for pre-registration table
  - Extracts rider name, team, city/state, and `racer_id` from links (road-results links riders as `/racer/{id}`)
  - Returns same dict format as the JSON path
  - Conservative: returns `[]` if table structure is unexpected
- [ ] Rewrite `startlists.py`:
  - Replace `fetch_startlist(event_url, category)` with `fetch_startlist(client: RoadResultsClient, race_id: int) -> list[dict]`
  - For riders with `racer_id` but no `carried_points` from the pre-reg page: look up best `carried_points` from the `results` table (same lookup `predict_contenders` already does)
  - Graceful: returns `[]` on any failure
- [ ] Rename `startlists.py` (old BikeReg version) to `startlists_bikereg.py` before rewriting
- [ ] Update `fetch-startlists` CLI command:
  - Instantiate `RoadResultsClient`
  - Query `Race WHERE is_upcoming=True` (remove requirement for `registration_url` -- road-results uses race_id, not a URL)
  - For each race: call new `fetch_startlist(client, race.id)`
  - Upsert `Startlist` rows with `source="road-results"`, `rider_id` resolved via `racer_id -> Rider.road_results_id`
  - Store `carried_points` on the `Startlist` row if returned from road-results (requires schema change -- see Phase 3)
- [ ] Tests: mock JSON response with pre-reg data, mock HTML fallback, verify `racer_id` dedup, verify `carried_points` lookup from results table, verify `[]` on failure

### Phase 3: Database Schema Changes & Refresh Limiting (~25% effort)

**Goal:** Add `RefreshLog` table, add `carried_points` to `Startlist`, implement daily refresh enforcement.

**Files:**
- `raceanalyzer/db/models.py` -- Add `RefreshLog` model, add `carried_points` column to `Startlist`
- `raceanalyzer/cli.py` -- Add refresh-limit checks to `fetch-startlists` and `fetch-calendar`
- `tests/test_refresh.py` -- New test file for refresh-limiting logic

**Tasks:**
- [ ] Add `RefreshLog` model to `models.py`:
  ```python
  class RefreshLog(Base):
      __tablename__ = "refresh_log"
      id = Column(Integer, primary_key=True, autoincrement=True)
      race_id = Column(Integer, nullable=False)
      refresh_type = Column(String, nullable=False)  # "startlist", "calendar"
      refreshed_at = Column(DateTime, nullable=False)
      result_count = Column(Integer, nullable=True)
      checksum = Column(String, nullable=True)
      __table_args__ = (
          Index("ix_refresh_log_race_type", "race_id", "refresh_type"),
      )
  ```
- [ ] Add `carried_points` column to `Startlist` model: `carried_points = Column(Float, nullable=True)`
  - This stores the road-results power ranking at time of startlist fetch, so `predict_contenders()` Tier 1 can use it directly without a separate DB lookup
- [ ] Implement `should_refresh(session, race_id, refresh_type) -> bool` helper function:
  - Returns `False` if a `RefreshLog` entry exists with `refreshed_at` within the last 24 hours
  - Returns `True` otherwise
- [ ] Implement `is_stale_edition(race) -> bool` helper function:
  - Returns `True` if `race.date is None` or `race.date.year != current_year` or `race.date < today`
  - Used before any HTTP request to skip stale editions
- [ ] Integrate refresh checks into `fetch-startlists` CLI command:
  - Before fetching each race's startlist: check `should_refresh()` and `is_stale_edition()`
  - After successful fetch: insert `RefreshLog` entry with `refresh_type="startlist"`
  - Log skipped races with reason ("already refreshed today" or "stale edition")
- [ ] Integrate refresh checks into `fetch-calendar` CLI command:
  - After discovering upcoming races: insert `RefreshLog` entries with `refresh_type="calendar"`
  - Skip re-discovery if calendar was refreshed within 24 hours (single entry with `race_id=0` as sentinel)
- [ ] Update `predict_contenders()` Tier 1 in `predictions.py` to prefer `Startlist.carried_points` when available, falling back to the existing `Result` table lookup
- [ ] Tests: verify `should_refresh` returns True for first call, False for second call within 24h, True after 24h; verify `is_stale_edition` for various date scenarios; verify CLI skips stale and recently-refreshed races

### Phase 4: BikeReg Deprecation & Cleanup (~15% effort)

**Goal:** Remove BikeReg from the active code path, clean up config, ensure all tests pass.

**Files:**
- `raceanalyzer/startlists.py` (old) -- Rename to `startlists_bikereg.py`
- `raceanalyzer/calendar_feed.py` (old) -- Rename to `calendar_feed_bikereg.py`
- `raceanalyzer/config.py` -- Remove BikeReg settings
- `raceanalyzer/cli.py` -- Remove BikeReg imports, update help text
- `tests/test_startlists.py` -- Fully rewritten (Phase 2)
- `tests/test_calendar_feed.py` -- Fully rewritten (Phase 1)

**Tasks:**
- [ ] Rename old BikeReg files (done in Phases 1-2, listed here for tracking):
  - `startlists.py` -> `startlists_bikereg.py`
  - `calendar_feed.py` -> `calendar_feed_bikereg.py`
- [ ] Remove BikeReg imports from `cli.py` (any lingering references)
- [ ] Update CLI help text:
  - `fetch-calendar`: "Import upcoming race dates from road-results.com" (was "from BikeReg")
  - `fetch-startlists`: "Pull registered riders from road-results.com for upcoming races" (was "from BikeReg")
- [ ] Update `Race.registration_source` default/docs to reflect "road-results" as primary source
- [ ] Remove `bikereg_base_url` and `bikereg_request_delay` from `Settings` (if not done in Phase 1)
- [ ] Run full test suite: `pytest tests/ -v`
- [ ] Run linter: `ruff check .`
- [ ] Verify `predict_contenders()` still works end-to-end with road-results startlist data (integration test)

---

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/scraper/client.py` | MODIFY | Add `fetch_upcoming_race_ids()` and `fetch_race_startlist()` methods |
| `raceanalyzer/scraper/parsers.py` | MODIFY | Add `StartlistParser` for HTML pre-registration table parsing |
| `raceanalyzer/calendar_feed.py` | REWRITE | Replace BikeReg calendar with road-results upcoming race discovery |
| `raceanalyzer/startlists.py` | REWRITE | Replace BikeReg startlist fetch with road-results pre-registration |
| `raceanalyzer/db/models.py` | MODIFY | Add `RefreshLog` model; add `carried_points` column to `Startlist` |
| `raceanalyzer/config.py` | MODIFY | Add `road_results_region_ids`; remove BikeReg settings |
| `raceanalyzer/cli.py` | MODIFY | Update `fetch-calendar` and `fetch-startlists` commands; add refresh limiting |
| `raceanalyzer/predictions.py` | MODIFY | Use `Startlist.carried_points` in Tier 1 ranking when available |
| `raceanalyzer/calendar_feed_bikereg.py` | RENAME | Preserve old BikeReg calendar code (no longer imported) |
| `raceanalyzer/startlists_bikereg.py` | RENAME | Preserve old BikeReg startlist code (no longer imported) |
| `tests/test_calendar_feed.py` | REWRITE | Road-results calendar discovery tests with `responses` mocks |
| `tests/test_startlists.py` | REWRITE | Road-results startlist fetching tests with `responses` mocks |
| `tests/test_refresh.py` | CREATE | Refresh-limiting logic tests (should_refresh, is_stale_edition) |
| `tests/test_scraper.py` | MODIFY | Add tests for new `RoadResultsClient` methods |

---

## Definition of Done

### Calendar Discovery
- [ ] `fetch-calendar` discovers upcoming PNW races from road-results.com (not BikeReg)
- [ ] Race IDs discovered from region listing page (regions 4 and 12)
- [ ] Only races with future dates are created/updated as `is_upcoming=True`
- [ ] Events are fuzzy-matched to existing `RaceSeries` via `match_event_to_series()`
- [ ] Unmatched events are logged but not silently dropped
- [ ] Graceful degradation: returns empty on HTTP failure, never crashes

### Startlist Fetching
- [ ] `fetch-startlists` pulls pre-registered riders from road-results.com
- [ ] Primary path: JSON API (`/downloadrace.php?raceID={id}&json=1`) returns pre-reg data with `carried_points`
- [ ] Fallback path: HTML parsing extracts rider name, team, and `racer_id` from race page
- [ ] `carried_points` resolved via JSON response or `results` table lookup by `racer_id`
- [ ] `Startlist` rows created with `source="road-results"` and `carried_points` populated
- [ ] Duplicate riders (same `racer_id`, different categories) are handled correctly

### Refresh Limiting
- [ ] `RefreshLog` table tracks per-race, per-type refresh timestamps
- [ ] Each race edition is refreshed at most once per 24 hours
- [ ] Stale editions (no future date in current year) are never refreshed
- [ ] Skipped races are logged with reason

### Request Safety
- [ ] All requests use `RoadResultsClient` with browser-spoofed user-agent via `cloudscraper`
- [ ] Rate limiting enforces >= 3s between requests (existing `min_request_delay`)
- [ ] Retry with exponential backoff on 403/429/5xx (existing pattern)

### BikeReg Deprecation
- [ ] BikeReg code renamed to `*_bikereg.py` and not imported from any active code path
- [ ] BikeReg settings removed from `Settings`
- [ ] CLI help text references road-results, not BikeReg

### Testing
- [ ] Calendar discovery: 5+ tests (region listing parse, date filtering, match to series, HTTP failure, empty listing)
- [ ] Startlist fetching: 5+ tests (JSON path, HTML fallback, `carried_points` lookup, dedup by `racer_id`, HTTP failure)
- [ ] Refresh limiting: 4+ tests (first refresh allowed, second blocked, 24h expiry, stale edition skip)
- [ ] Client methods: 2+ tests (new `fetch_upcoming_race_ids`, `fetch_race_startlist`)
- [ ] All existing tests pass
- [ ] `ruff check .` passes

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Road-results JSON API returns empty for pre-registration (only populated post-race)** | Medium | High | HTML fallback parser is the safety net. Try JSON first (zero cost -- one HTTP call), fall back to HTML parsing. If both fail, `predict_contenders()` Tier 2/3 still works from historical data. |
| **Region listing page doesn't embed dates alongside race links** | Medium | Medium | If dates aren't in the listing HTML, we must fetch each race page individually to check dates. This is expensive (one HTTP call per race * 3s delay). Mitigate by caching `ScrapeLog` data -- if we already scraped a race and it's historical, skip it. Only fetch pages for unknown race IDs. |
| **Road-results changes HTML structure for pre-registration table** | Medium | Medium | Keep HTML parsing conservative (return `[]` on unexpected structure). The JSON path is more stable since it's a structured API. Log warnings when HTML parsing fails so we detect breakage early. |
| **Rate limiting causes calendar discovery to take very long** | High | Medium | With 3s between requests and potentially 100+ race IDs in a region, full discovery could take 5+ minutes. Mitigate: (1) only fetch pages for race IDs not already in `ScrapeLog`, (2) parse dates from region listing if possible, (3) add `--limit` flag to cap the number of races checked. |
| **`cloudscraper` blocked by road-results Cloudflare upgrade** | Low | High | This is an existing risk for the entire scraper, not specific to this sprint. If it happens, the whole project needs a new HTTP strategy. No sprint-specific mitigation beyond what exists. |
| **Stale edition logic incorrectly skips races** | Low | Medium | Definition is conservative: `date.year == current_year AND date >= today`. A race on Jan 1 of next year wouldn't be refreshed until that year starts. This is acceptable for PNW racing (season is March-October). |
| **SQLite migration: adding RefreshLog table and Startlist column** | Low | Low | Uses `init_db()` pattern (creates all tables). For existing DBs: manual `ALTER TABLE startlists ADD COLUMN carried_points FLOAT` and `CREATE TABLE refresh_log (...)`. NULL defaults mean existing rows are unaffected. |

---

## Security

- **No new external API calls at render time.** All road-results fetching happens during CLI commands, not during UI page loads.
- **Browser user-agent spoofing:** Extends existing `BROWSER_HEADERS` pattern from `RoadResultsClient`. No new credentials or API keys.
- **No PII exposure:** Startlist data (rider names, teams) is already public on road-results.com. Power rankings (`carried_points`) are public race data.
- **Rate limiting protects both us and road-results:** The 3s minimum delay + daily refresh cap ensures we're a well-behaved client. A full calendar discovery of 100 races takes ~5 minutes, not a burst.
- **`RefreshLog` checksum:** Optional hash of the response body allows detecting when startlist data actually changed between refreshes, useful for future optimization (skip DB writes on identical data).

---

## Dependencies

**Existing Python packages (no changes):**
- `sqlalchemy`, `cloudscraper`, `requests`, `click`, `pandas`

**New Python packages: None.**

The `responses` library (already a test dependency) is used for mocking HTTP calls in tests.

---

## Open Questions

1. **Does road-results' JSON API (`/downloadrace.php?raceID={id}&json=1`) return data for upcoming races with pre-registered riders?** If yes, this is the cleanest path -- zero new parsing code needed. If no, the HTML fallback parser is required. **Resolution strategy:** Test this empirically by calling the JSON endpoint for a known upcoming race during implementation. The sprint plan handles both cases.

2. **Does the region listing page (`/?n=results&sn=all&region=4`) embed race dates in the HTML alongside race links?** If dates are visible in the listing (e.g., in a table row), we can extract them in a single HTTP call instead of fetching each race page individually. This would reduce calendar discovery from O(n) HTTP calls to O(1). **Resolution strategy:** Parse the listing HTML during Phase 1 implementation. The current regex `r'/race/(\d+)" >'` only extracts IDs; extend it to also capture adjacent date text if present.

3. **Should `carried_points` on `Startlist` be the value from road-results at fetch time, or the best historical value from the `results` table?** The road-results value is the most current ranking. The `results` table value is the best we've ever seen for that rider. **Recommendation:** Store the road-results value (most current) on `Startlist.carried_points`. The existing `predict_contenders()` Tier 1 already does a `results` table lookup for best historical points; having both available lets us pick the max.

4. **Should the `fetch-calendar` command also accept state codes (WA, OR) for familiarity, or only region IDs (4, 12)?** The intent document uses state codes, but road-results uses numeric region IDs. **Recommendation:** Accept both. Map state codes to region IDs internally: `{"WA": 4, "OR": 4, "ID": 4, "BC": 12}` (PNW states all map to region 4; BC maps to region 12). Default to discovering both regions.

5. **What happens when a race on road-results doesn't match any existing series?** Options: (a) create a new `RaceSeries` automatically, (b) log it and skip, (c) create an unlinked `Race` row. **Recommendation:** Option (b) for now -- log the unmatched race name at INFO level. Creating series automatically risks pollution from non-road-race events (gravel, CX, track) that appear on road-results. The user can manually link later via `build-series` after importing historical data for new events.

6. **Should we remove or deprecate the BikeReg code?** The intent says "cleanly deprecated (kept but no longer the primary path)." **Recommendation:** Rename files to `*_bikereg.py` so the code is preserved but unreachable from active imports. This is cleaner than leaving dead code in the active module path. Full deletion can happen in a future sprint once road-results has proven reliable.
