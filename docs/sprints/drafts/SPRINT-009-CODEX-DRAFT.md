# Sprint 009: Road-Results Integration for Registered Riders & Power Rankings

## Overview

Sprint 009 replaces the BikeReg-based calendar and startlist pipeline with road-results.com as the single source of truth for upcoming PNW races, pre-registered riders, and power rankings. The existing BikeReg integration (Sprint 006) was a minimum viable approach with incomplete coverage; road-results is already the project's primary data source for historical results, and extending it to cover pre-registration data eliminates a seam between two separate scraping systems.

This sprint adds three concrete capabilities: (1) discovering upcoming races from road-results region listings, (2) fetching pre-registered riders with their `carried_points` / `Points` power rankings from road-results' JSON API, and (3) enforcing a daily refresh limit per race edition so we do not hammer the site. By the end, the `fetch-calendar` and `fetch-startlists` CLI commands talk exclusively to road-results.com, the Race Preview page shows richer contender data backed by road-results power rankings, and BikeReg code is retained but demoted to a dormant fallback.

**Why now:** The existing `RoadResultsClient` already handles cloudscraper/browser-UA, rate limiting (3s delay), exponential backoff, and retry logic. The `RaceResultParser` already extracts `Points`, `CarriedPoints`, and `RacerID`. The `Startlist` model already has a `source` field. The architectural runway is clear -- this sprint is primarily new data acquisition, a new parser, a new refresh-tracking table, and wiring changes.

**Duration**: ~2 weeks
**Prerequisite**: Sprint 008 complete (interactive course maps, historical stats, narrative generator)

---

## Use Cases

1. **As a racer**, I can run `fetch-calendar` and see upcoming PNW races discovered from road-results.com, so the race calendar reflects what is actually on the local racing schedule.
2. **As a racer**, I can run `fetch-startlists` and see pre-registered riders for an upcoming race with their road-results power ranking points, so I know who to watch.
3. **As a racer**, I can view the Race Preview page and see contenders sorted by road-results `carried_points`, giving me a more accurate picture of who the strongest riders are.
4. **As a developer**, I can call `RoadResultsClient.fetch_upcoming_races(region)` and get back structured data about future race editions.
5. **As a developer**, I can call `RoadResultsClient.fetch_race_startlist(race_id)` and get back a list of pre-registered riders with their power ranking data.
6. **As an operator**, I can trust that the system will not refresh any race edition more than once per day, and will never refresh editions that lack an upcoming race in the current calendar year.
7. **As a developer**, I can verify all road-results HTTP interactions via `responses`-mocked unit tests without hitting the live site.

---

## Architecture

### Road-Results URL Patterns

Road-results.com organizes data around numeric race IDs. Based on the existing scraper's usage and the site's structure:

- **Region listing (existing):** `/?n=results&sn=all&region={region}` -- returns HTML with links to `/race/{id}`. Region 4 = Pacific Northwest, region 12 = British Columbia.
- **Race page (existing):** `/race/{race_id}` -- HTML page with metadata (name, date, location). The `RacePageParser` already extracts this.
- **Race JSON (existing):** `/downloadrace.php?raceID={race_id}&json=1` -- returns the full result set including `Points`, `CarriedPoints`, `RacerID`, `RaceCategoryName`.
- **Upcoming/pre-registration (new, to discover):** Road-results likely uses the same region listing but includes upcoming races with future dates. Upcoming races may appear with a date in the future and no results yet, or there may be a separate `sn=upcoming` parameter. The implementation must probe for the correct URL pattern and fall back gracefully.

**Discovery strategy:** Fetch the region listing page, parse all `/race/{id}` links, then for each race ID fetch the HTML page to extract the date. Races with `date >= today` are upcoming. This is a two-pass approach -- slower but robust, since it reuses the existing `RacePageParser` and does not depend on an undocumented "upcoming" endpoint.

**Pre-registration strategy:** For each upcoming race, fetch the JSON endpoint (`downloadrace.php?raceID={id}&json=1`). If the race has pre-registered riders but no results yet, the JSON may return entries with `Points`/`CarriedPoints` but no `RaceTime` or `Place`. Parse these using a new `StartlistParser` that extracts rider name, team, category, racer_id, carried_points, and points. If the JSON endpoint returns an empty list for an upcoming race, the pre-reg data may live on a separate HTML page -- implement an HTML fallback parser using regex patterns similar to `RacePageParser`.

### Refresh Tracking: `RefreshLog` Table

A new `RefreshLog` model tracks when each race edition was last refreshed for startlist/calendar data. This is separate from `ScrapeLog` (which tracks historical result scraping) because the refresh cadence and purpose differ.

```python
class RefreshLog(Base):
    __tablename__ = "refresh_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=False)
    refresh_type = Column(String, nullable=False)  # "calendar", "startlist"
    refreshed_at = Column(DateTime, nullable=False)
    status = Column(String, nullable=False)  # "success", "empty", "error"
    entry_count = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_refresh_log_race_type", "race_id", "refresh_type"),
        UniqueConstraint("race_id", "refresh_type", "refreshed_at",
                         name="uq_refresh_per_type_time"),
    )
```

**Daily limit logic:**

```python
def should_refresh(session, race_id, refresh_type, now=None):
    """Return True if this race+type has not been refreshed today."""
    now = now or datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    existing = (
        session.query(RefreshLog)
        .filter(
            RefreshLog.race_id == race_id,
            RefreshLog.refresh_type == refresh_type,
            RefreshLog.refreshed_at >= today_start,
        )
        .first()
    )
    return existing is None
```

**Stale edition guard:** Before refreshing, check whether the race edition has an upcoming date in the current calendar year:

```python
def is_refreshable_edition(session, race_id):
    """Return True only if this race has a date in the current year AND date >= today."""
    race = session.get(Race, race_id)
    if not race or not race.date:
        return False
    now = datetime.utcnow()
    return race.date.year == now.year and race.date.date() >= now.date()
```

### BikeReg Transition Strategy

BikeReg code is **not deleted**. The transition is handled via the `source` field on `Startlist` and `registration_source` on `Race`:

1. `calendar_feed.py` is renamed internally but the module is kept. A new `road_results_calendar.py` module handles discovery. The CLI `fetch-calendar` command switches to calling the new module.
2. `startlists.py` is kept as-is. A new `road_results_startlists.py` module handles road-results pre-reg. The CLI `fetch-startlists` command switches to calling the new module.
3. `Startlist.source` gains a new value: `"road-results"`. The `predictions.py` contender ranking already works source-agnostically -- it reads `carried_points` regardless of source.
4. `Race.registration_source` gains `"road-results"` as a value.

This means rolling back to BikeReg requires only changing two CLI command implementations -- no schema changes, no model changes.

### Configuration Changes

New fields on `Settings`:

```python
# Road-results upcoming race settings
road_results_upcoming_regions: tuple[int, ...] = (4, 12)  # PNW, BC
road_results_max_daily_refreshes: int = 1
road_results_calendar_days_ahead: int = 90
road_results_startlist_source: str = "road-results"  # or "bikereg" for rollback
```

The existing `min_request_delay` (3.0s), `retry_count` (3), `retry_backoff_base` (2.0), and `base_url` settings are reused without change.

---

## Implementation

### Phase 1: Road-Results Upcoming Race Discovery (~25% effort)

**Goal:** Discover upcoming PNW races from road-results region listings and persist them as `Race` rows with `is_upcoming=True`.

**Files:**
- `raceanalyzer/scraper/client.py` -- Add `discover_upcoming_race_ids(region)` and `fetch_race_metadata(race_id)` methods
- `raceanalyzer/road_results_calendar.py` -- CREATE: New module for upcoming race discovery logic
- `raceanalyzer/config.py` -- Add road-results upcoming race settings
- `raceanalyzer/cli.py` -- Rewrite `fetch-calendar` command to use road-results
- `raceanalyzer/db/models.py` -- Add `RefreshLog` model
- `tests/test_road_results_calendar.py` -- CREATE: Discovery tests with `responses` mocks

**Tasks:**
- [ ] Add `RefreshLog` model to `models.py` with columns: `race_id`, `refresh_type`, `refreshed_at`, `status`, `entry_count`, `error_message`
- [ ] Add `discover_upcoming_race_ids(region)` to `RoadResultsClient`: fetch region listing, parse race IDs (reuse existing `discover_region_race_ids` regex), return list of IDs. This may be identical to the existing method -- the key difference is downstream filtering by date.
- [ ] Add `fetch_race_metadata(race_id)` to `RoadResultsClient`: fetch `/race/{race_id}` HTML, parse with `RacePageParser`, return metadata dict. This is a thin wrapper around `fetch_race_page` + `RacePageParser`.
- [ ] Create `road_results_calendar.py` with `discover_upcoming_races(client, session, settings)`:
  1. For each region in `settings.road_results_upcoming_regions`, call `client.discover_region_race_ids(region)`
  2. For each race ID, check `should_refresh(session, race_id, "calendar")`
  3. If refreshable, fetch metadata via `client.fetch_race_metadata(race_id)`
  4. If `metadata.date >= today` and `metadata.date` is within `calendar_days_ahead`, persist as `Race` with `is_upcoming=True`, `registration_source="road-results"`
  5. Fuzzy-match race name to existing `RaceSeries` (reuse `match_event_to_series` logic from `calendar_feed.py`)
  6. Log to `RefreshLog`
- [ ] Add `road_results_upcoming_regions`, `road_results_max_daily_refreshes`, `road_results_calendar_days_ahead`, `road_results_startlist_source` to `Settings`
- [ ] Rewrite `fetch-calendar` CLI command to call `discover_upcoming_races()` instead of `search_upcoming_events()`
- [ ] Add `--source` flag to `fetch-calendar` (default `"road-results"`, alternative `"bikereg"`) for rollback capability
- [ ] Tests: mock region listing HTML with mix of past/future race links, mock race page HTML with future date, verify only future races are persisted, verify `RefreshLog` is created, verify daily limit prevents duplicate refresh

### Phase 2: Road-Results Startlist Parser & Fetcher (~30% effort)

**Goal:** Fetch pre-registered riders from road-results and persist them as `Startlist` rows with power ranking data.

**Files:**
- `raceanalyzer/scraper/client.py` -- Add `fetch_race_startlist_json(race_id)` method
- `raceanalyzer/scraper/parsers.py` -- Add `StartlistParser` class
- `raceanalyzer/road_results_startlists.py` -- CREATE: New module for startlist fetching logic
- `raceanalyzer/db/models.py` -- Add `carried_points` and `road_results_id` columns to `Startlist`
- `raceanalyzer/cli.py` -- Rewrite `fetch-startlists` command to use road-results
- `tests/test_road_results_startlists.py` -- CREATE: Startlist parser and fetcher tests

**Tasks:**
- [ ] Add `carried_points` (Float, nullable) and `road_results_racer_id` (Integer, nullable) columns to `Startlist` model
- [ ] Add `fetch_race_startlist_json(race_id)` to `RoadResultsClient`: same as `fetch_race_json(race_id)` but with explicit handling for the case where JSON returns pre-registration data (entries without `Place` or `RaceTime`). This may literally be the same endpoint -- road-results uses `downloadrace.php` for both results and pre-reg data.
- [ ] Create `StartlistParser` in `parsers.py`:
  ```python
  class StartlistParser:
      """Parses road-results JSON into pre-registration rider dicts.

      Distinguishes pre-reg entries from result entries: pre-reg entries
      have no Place and no RaceTime (or RaceTime is empty/null).
      """
      def __init__(self, race_id: int, raw_json: list[dict]):
          ...

      def entries(self) -> list[dict]:
          """Parse pre-registration entries.

          Returns: [{
              "name": str,
              "team": str | None,
              "category": str | None,
              "racer_id": int | None,
              "carried_points": float | None,
              "points": float | None,
          }]
          """
  ```
  Key parsing rules:
  - Entry is a pre-reg if `Place` is None/empty AND `RaceTime` is None/empty/not a valid time
  - Extract `FirstName`/`LastName` or `Name` (same logic as `RaceResultParser`)
  - Extract `CarriedPoints`/`PriorPoints` as `carried_points`
  - Extract `Points` as `points`
  - Extract `RacerID` as `racer_id`
  - Extract `RaceCategoryName` as `category`
  - Extract `TeamName`/`Team` as `team`
  - Deduplicate by `racer_id` (keep first occurrence per category)
- [ ] Create `road_results_startlists.py` with `fetch_startlists(client, session, settings)`:
  1. Query `Race` rows where `is_upcoming=True` and `date >= today` and `date.year == current_year`
  2. For each race, check `should_refresh(session, race_id, "startlist")` and `is_refreshable_edition(session, race_id)`
  3. If refreshable, call `client.fetch_race_startlist_json(race_id)`
  4. Parse with `StartlistParser`
  5. For each entry, match `racer_id` to existing `Rider.road_results_id` to set `Startlist.rider_id`
  6. Clear previous road-results startlist entries for this race (delete where `source="road-results"` and `race_id=race_id`) before inserting fresh data
  7. Persist `Startlist` rows with `source="road-results"`, `carried_points`, `road_results_racer_id`
  8. Log to `RefreshLog`
- [ ] Rewrite `fetch-startlists` CLI command to call `fetch_startlists()` instead of BikeReg's `fetch_startlist()`
- [ ] Add `--source` flag to `fetch-startlists` (default `"road-results"`, alternative `"bikereg"`)
- [ ] Tests:
  - Mock JSON with pre-reg entries (no Place, no RaceTime, has CarriedPoints) -- verify correct parsing
  - Mock JSON with mix of results and pre-reg entries -- verify only pre-reg entries are extracted
  - Mock JSON with empty list -- verify graceful empty return
  - Mock JSON with duplicate racer_id across categories -- verify dedup within category, distinct across categories
  - Verify `should_refresh()` blocks second call on same day
  - Verify `is_refreshable_edition()` blocks refresh for past-year races
  - Verify existing road-results startlist entries are cleared before re-insert
  - Verify `Startlist.rider_id` is linked when `Rider.road_results_id` matches

### Phase 3: Refresh Limiting & Stale Edition Guards (~15% effort)

**Goal:** Enforce the daily refresh limit and prevent refreshing stale editions.

**Files:**
- `raceanalyzer/refresh.py` -- CREATE: Refresh limiting logic (extracted for testability)
- `raceanalyzer/road_results_calendar.py` -- Integrate refresh checks
- `raceanalyzer/road_results_startlists.py` -- Integrate refresh checks
- `tests/test_refresh.py` -- CREATE: Refresh logic tests

**Tasks:**
- [ ] Create `refresh.py` with `should_refresh(session, race_id, refresh_type, now=None)` and `is_refreshable_edition(session, race_id, now=None)` functions
- [ ] `should_refresh`: Query `RefreshLog` for any entry with matching `race_id` + `refresh_type` where `refreshed_at >= start of today (UTC)`. Return `True` if no such entry exists.
- [ ] `is_refreshable_edition`: Load `Race` by ID. Return `True` only if `race.date` is not None, `race.date.year == now.year`, and `race.date.date() >= now.date()`. This prevents refreshing historical editions and editions from prior years.
- [ ] Add `record_refresh(session, race_id, refresh_type, status, entry_count=None, error_message=None)` helper that creates a `RefreshLog` row.
- [ ] Wire `should_refresh` and `is_refreshable_edition` into `discover_upcoming_races()` and `fetch_startlists()` from Phases 1-2
- [ ] Tests:
  - `should_refresh` returns True when no prior refresh exists
  - `should_refresh` returns False after a refresh today
  - `should_refresh` returns True after a refresh yesterday (different UTC day)
  - `is_refreshable_edition` returns True for race with date = today
  - `is_refreshable_edition` returns True for race with date = 30 days from now, same year
  - `is_refreshable_edition` returns False for race with date = last year
  - `is_refreshable_edition` returns False for race with date = yesterday
  - `is_refreshable_edition` returns False for race with date = None
  - `record_refresh` creates correct `RefreshLog` entry

### Phase 4: Predictions Integration & CLI Wiring (~20% effort)

**Goal:** Ensure the prediction pipeline uses road-results power rankings from startlists, update the Race Preview data assembly, and verify end-to-end flow.

**Files:**
- `raceanalyzer/predictions.py` -- Update `_rank_from_startlist()` to prefer `Startlist.carried_points` over historical lookup
- `raceanalyzer/queries.py` -- Update `get_race_preview()` to surface power ranking source
- `raceanalyzer/cli.py` -- Final CLI command updates
- `tests/test_predictions.py` -- Add tests for road-results-sourced startlists

**Tasks:**
- [ ] Update `_rank_from_startlist()` in `predictions.py`: When a `Startlist` entry has `carried_points` (from road-results), use that value directly instead of looking up the rider's historical best. This is more current and matches what road-results shows. Fall back to historical lookup only if `carried_points` is None.
- [ ] Update `predict_contenders()` to include `road_results_racer_id` in output DataFrame when available (useful for linking to road-results profile pages in the UI)
- [ ] Update `get_race_preview()` to include `startlist_source` in the return dict (either `"road-results"` or `"bikereg"` based on the `Startlist.source` of the first entry found)
- [ ] Ensure `fetch-calendar` CLI prints discovered upcoming races with dates and matched series
- [ ] Ensure `fetch-startlists` CLI prints rider counts and power ranking summaries per race
- [ ] Add `--dry-run` flag to both `fetch-calendar` and `fetch-startlists` for safe preview
- [ ] Tests:
  - `predict_contenders` with road-results startlist entries that have `carried_points` -- verify direct use without DB lookup
  - `predict_contenders` with road-results startlist entries that have `carried_points=None` -- verify fallback to historical lookup
  - `predict_contenders` with mixed sources -- verify correct ranking
  - `get_race_preview` includes `startlist_source` field

### Phase 5: Cleanup, Documentation & Edge Case Hardening (~10% effort)

**Goal:** Harden error paths, add logging, ensure graceful degradation, and verify the full pipeline.

**Files:**
- `raceanalyzer/road_results_calendar.py` -- Error handling hardening
- `raceanalyzer/road_results_startlists.py` -- Error handling hardening
- `raceanalyzer/scraper/client.py` -- Logging for new endpoints
- `tests/test_scraper.py` -- Add client tests for new methods

**Tasks:**
- [ ] Verify all new HTTP calls go through `_request_with_retry()` (inheriting rate limiting, backoff, and browser UA)
- [ ] Add structured logging at INFO level for: races discovered, startlists fetched, refresh skipped (daily limit), refresh skipped (stale edition)
- [ ] Add structured logging at WARNING level for: HTTP errors during discovery, empty JSON responses, parser failures
- [ ] Handle edge case: race ID appears in region listing but `/race/{id}` returns 404 (race was deleted) -- log and skip
- [ ] Handle edge case: JSON endpoint returns valid JSON but with unexpected structure (not a list) -- return empty, log warning
- [ ] Handle edge case: race name from road-results doesn't match any existing series -- create the Race row but leave `series_id=None`, log info
- [ ] Handle edge case: `RacerID` in startlist doesn't match any existing `Rider.road_results_id` -- still create `Startlist` row with `rider_id=None`, the contender ranker handles this gracefully
- [ ] Verify `ruff check .` passes on all new/modified files
- [ ] Verify all existing tests pass
- [ ] Add client-level `responses` tests for `fetch_race_metadata` and `fetch_race_startlist_json` in `test_scraper.py`

---

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/db/models.py` | MODIFY | Add `RefreshLog` model; add `carried_points`, `road_results_racer_id` columns to `Startlist` |
| `raceanalyzer/config.py` | MODIFY | Add `road_results_upcoming_regions`, `road_results_max_daily_refreshes`, `road_results_calendar_days_ahead`, `road_results_startlist_source` |
| `raceanalyzer/scraper/client.py` | MODIFY | Add `fetch_race_metadata(race_id)`, `fetch_race_startlist_json(race_id)` methods |
| `raceanalyzer/scraper/parsers.py` | MODIFY | Add `StartlistParser` class for pre-registration data |
| `raceanalyzer/road_results_calendar.py` | CREATE | Upcoming race discovery from road-results region listings |
| `raceanalyzer/road_results_startlists.py` | CREATE | Pre-registered rider fetching from road-results JSON API |
| `raceanalyzer/refresh.py` | CREATE | `should_refresh()`, `is_refreshable_edition()`, `record_refresh()` logic |
| `raceanalyzer/predictions.py` | MODIFY | Update `_rank_from_startlist()` to prefer `Startlist.carried_points` |
| `raceanalyzer/queries.py` | MODIFY | Add `startlist_source` to `get_race_preview()` return |
| `raceanalyzer/cli.py` | MODIFY | Rewrite `fetch-calendar` and `fetch-startlists` to use road-results; add `--source` and `--dry-run` flags |
| `raceanalyzer/startlists.py` | KEEP | BikeReg startlist code retained as dormant fallback |
| `raceanalyzer/calendar_feed.py` | KEEP | BikeReg calendar code retained as dormant fallback; `match_event_to_series` reused |
| `tests/test_road_results_calendar.py` | CREATE | Discovery + calendar integration tests |
| `tests/test_road_results_startlists.py` | CREATE | Startlist parser + fetcher tests |
| `tests/test_refresh.py` | CREATE | Refresh limiting logic tests |
| `tests/test_scraper.py` | MODIFY | Add client tests for new methods |
| `tests/test_predictions.py` | MODIFY | Add tests for road-results-sourced startlist ranking |

---

## Definition of Done

### Data Acquisition
- [ ] `fetch-calendar` discovers upcoming races from road-results.com region listings (regions 4 and 12)
- [ ] Only races with dates in the future and within `calendar_days_ahead` are persisted
- [ ] Discovered races are fuzzy-matched to existing `RaceSeries` where possible
- [ ] `fetch-startlists` pulls pre-registered riders from road-results JSON API
- [ ] Startlist entries include `carried_points` and `road_results_racer_id` when available
- [ ] Riders are linked to existing `Rider` rows via `road_results_id` matching

### Power Rankings
- [ ] `predict_contenders()` uses `Startlist.carried_points` directly when available (no redundant DB lookup)
- [ ] Contender ranking falls back to historical `carried_points` when startlist value is None
- [ ] Race Preview page shows contenders sorted by road-results power rankings

### Refresh Limiting
- [ ] Each race edition is refreshed at most once per day per refresh type (calendar, startlist)
- [ ] Race editions with dates in prior years are never refreshed
- [ ] Race editions with dates in the past (even current year) are never refreshed
- [ ] `RefreshLog` table tracks all refresh attempts with timestamp, status, and entry count

### HTTP & Rate Limiting
- [ ] All road-results requests go through `RoadResultsClient._request_with_retry()`
- [ ] Browser-spoofed user-agent via cloudscraper on all requests
- [ ] Minimum 3s delay between requests (existing `min_request_delay`)
- [ ] Exponential backoff on 403, 429, and 5xx responses
- [ ] Graceful degradation: HTTP errors return empty results, never crash

### BikeReg Transition
- [ ] BikeReg code in `startlists.py` and `calendar_feed.py` is intact and importable
- [ ] `--source bikereg` flag on CLI commands activates BikeReg fallback
- [ ] `Startlist.source` values: `"road-results"` for new data, `"bikereg"` for legacy data

### Testing
- [ ] `StartlistParser`: 4+ test cases (pre-reg entries, mixed results/pre-reg, empty, dedup)
- [ ] Calendar discovery: 3+ test cases (future races, past races filtered, daily limit)
- [ ] Refresh logic: 6+ test cases (should_refresh variants, is_refreshable_edition variants)
- [ ] Predictions: 3+ test cases (road-results carried_points, None fallback, mixed sources)
- [ ] Client methods: 2+ test cases (fetch_race_metadata, fetch_race_startlist_json)
- [ ] All existing tests pass
- [ ] `ruff check .` passes
- [ ] All new HTTP calls mocked with `responses` library -- no live network calls in tests

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Road-results pre-registration endpoint differs from result JSON endpoint** | Medium | High | Probe `downloadrace.php` first. If it returns empty for upcoming races, inspect the HTML race page for embedded pre-reg data and write an HTML fallback parser. The `StartlistParser` is designed to handle both JSON and degraded data. |
| **Road-results region listing does not include future races** | Medium | High | If the `/?n=results&sn=all&region=4` page only shows past races, try alternative URL parameters (`sn=upcoming`, `sn=schedule`). If no programmatic discovery exists, fall back to scraping the OBRA (Oregon Bicycle Racing Association) calendar as a race-ID source. |
| **Road-results blocks scraping or changes anti-bot measures** | Low | High | Already mitigated by `cloudscraper` + browser UA. If blocking intensifies, reduce request frequency and add randomized delay jitter (1-5s). The `RefreshLog` daily limit provides a natural ceiling on request volume. |
| **Race names from road-results don't match existing series** | Medium | Medium | Reuse `match_event_to_series()` fuzzy matching (SequenceMatcher, year-stripped, min_score=0.5). Log unmatched races for manual review. These races still get `Race` rows but with `series_id=None`. |
| **Duplicate `Startlist` entries from repeated fetches** | Medium | Medium | Clear-and-reinsert strategy: delete all `source="road-results"` startlist entries for a race before inserting fresh data. This avoids accumulating stale entries. The `checksum` column on `Startlist` can optionally detect no-change refreshes. |
| **`CarriedPoints` is None/0 for all pre-reg entries** | Medium | Low | This just means road-results doesn't expose power rankings in pre-reg context. The system degrades to historical `carried_points` lookup via `_rank_from_startlist()`. No user-visible failure. |
| **SQLite migration: adding columns and new table** | Low | Low | Manual `ALTER TABLE` for new `Startlist` columns (NULL default). `CREATE TABLE` for `RefreshLog`. Follow existing pattern -- no migration framework needed for additive schema changes. |
| **Rate limiting during bulk calendar discovery** | Medium | Medium | Region listings can return 100+ race IDs. At 3s per request, fetching metadata for 100 races takes ~5 minutes. Add a `--limit` flag to cap discovery and a progress counter. Log estimated time remaining. |

---

## Security

- **Browser user-agent spoofing:** All requests use the existing `BROWSER_HEADERS` via `cloudscraper`. No new user-agent strings introduced. This is the same pattern used for historical scraping since Sprint 001.
- **No credentials stored:** Road-results.com does not require authentication for public race data. No API keys, tokens, or passwords are needed or stored.
- **Rate limiting as good citizenship:** The 3s minimum delay and daily-refresh-per-edition cap ensure we do not overload road-results.com. Total daily request volume is bounded by `number_of_upcoming_races * 2` (one metadata fetch + one startlist fetch per race per day).
- **No PII beyond public race data:** Rider names, teams, and carried_points are all publicly displayed on road-results.com. No private data (email, address, etc.) is scraped or stored.
- **Input validation on parsed data:** All parsed values go through `_safe_int()` and `_safe_float()` (existing patterns in `RaceResultParser`). No raw strings are interpolated into SQL -- all DB operations use SQLAlchemy ORM.

---

## Dependencies

**Existing Python packages (no changes):**
- `cloudscraper` -- browser-spoofed HTTP client (already used by `RoadResultsClient`)
- `requests` -- HTTP library (already a dependency)
- `sqlalchemy` -- ORM (already used throughout)
- `click` -- CLI framework (already used)
- `responses` -- HTTP mocking for tests (already a dev dependency)
- `pandas` -- DataFrames for predictions (already used)

**New Python packages: None.**

**External services:**
- `road-results.com` -- Public race results site (already the primary data source)

---

## Open Questions

1. **What URL pattern does road-results use for pre-registration data?** The `downloadrace.php?raceID={id}&json=1` endpoint is confirmed for race results. It may also serve pre-registration data for upcoming races (entries with no Place/RaceTime). This needs to be verified by fetching the JSON for a known upcoming race. If it does not, we need to discover the correct endpoint -- possibly an HTML table on the race page, or a separate API parameter.

2. **Does the road-results region listing include upcoming/future races?** The existing `discover_region_race_ids()` uses `/?n=results&sn=all&region=4`. If "all" means "all results" (past only), we need to find an alternative listing that includes upcoming races. Possible alternatives: `sn=upcoming`, `sn=schedule`, or a different top-level page.

3. **Should unmatched races create new `RaceSeries` entries?** Currently, if a road-results race name doesn't match any existing series, it gets a `Race` row with `series_id=None`. Should we auto-create a `RaceSeries` for truly new events, or leave them unlinked for manual curation? Recommendation: leave unlinked and log, to avoid polluting the series table with bad fuzzy matches.

4. **How should the system handle race editions that span multiple days (stage races)?** Road-results may list each stage as a separate race ID. The `is_refreshable_edition` check uses `race.date`, which works for single-day events. For multi-day events, we may need to check against the last stage date. Recommendation: defer to a future sprint; single-day events are the 90% case for PNW road racing.

5. **Should we store the road-results `Points` field separately from `CarriedPoints`?** `Points` represents points earned in a specific race, while `CarriedPoints` is the cumulative ranking metric. The `Startlist` model currently only stores `carried_points`. We should also store `points` if it is available in pre-reg data, as it may be useful for future ranking refinements.

6. **What is the expected volume of upcoming races per region?** This affects the time budget for the `fetch-calendar` command. If regions 4 and 12 together have 50+ upcoming races, bulk metadata fetching at 3s/request takes 2.5+ minutes. A `--limit` flag or parallel fetching (within rate limits) may be needed for usability.
