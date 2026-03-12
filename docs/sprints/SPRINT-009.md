# Sprint 009: Road-Results Integration for Registered Riders & Power Rankings

## Overview

Sprint 009 replaces BikeReg as the source for upcoming race discovery and pre-registered rider data with road-results.com's power ranking system. The existing BikeReg integration (Sprint 006) was a minimum viable approach with incomplete PNW coverage and no power ranking data. Road-results is already the project's primary data source for historical results, and its predictor system ranks registered riders by a points-based power ranking — exactly what the contender prediction system needs.

**Key discovery (from live API research):** Road-results' upcoming events come from a **GraphQL API** at `outsideapi.com/fed-gw/graphql` (the same backend BikeReg uses). Registered riders ranked by power points come from road-results' **predictor.aspx** HTML endpoint, which takes a BikeReg eventId and returns riders sorted by their road-results power ranking. This means the sprint integrates two endpoints: GraphQL for discovery, predictor.aspx for ranked startlists.

**What this sprint does NOT do:** It does not change the Race Preview UI, the prediction algorithms, or the historical scraping pipeline. The existing `predict_contenders()` three-tier ranking system already consumes `Startlist` rows and ranks by `carried_points` — this sprint only changes where that data comes from and adds power ranking points directly from road-results.

**Duration**: ~2 weeks
**Prerequisite**: Sprint 008 complete

---

## Use Cases

1. **As a racer**, I can run `fetch-calendar` and see upcoming PNW races discovered from road-results.com/BikeReg's shared event system, matched to existing series in the database.
2. **As a racer**, I can run `fetch-startlists` and get pre-registered riders ranked by road-results power points, so the Race Preview contender predictions reflect who's actually signed up and how strong they are.
3. **As an operator**, I can run `fetch-startlists` multiple times per day without hammering road-results — each race edition is refreshed at most once per 24 hours.
4. **As an operator**, I know that race editions without a future date are automatically skipped during refresh.
5. **As a developer**, I can pass `--source bikereg` to either CLI command to fall back to the old BikeReg pipeline without any code changes.
6. **As a developer**, I can pass `--dry-run` to `fetch-startlists` to preview which races would be refreshed without making HTTP requests.

---

## Architecture

### Data Pipeline Overview

```
fetch-calendar:
  GraphQL API (outsideapi.com/fed-gw/graphql)
    → POST query with region coords, minDate, eventTypes=[1]
    → returns: [{eventId, name, startDate, city, state, eventUrl}]
  For each event:
    Fuzzy-match to existing RaceSeries via match_event_to_series()
    Create/update Race row: is_upcoming=True, registration_source="road-results"
    Store eventId on Race for startlist fetching

fetch-startlists:
  For each Race WHERE is_upcoming=True AND date >= today:
    Check RefreshLog: skip if refreshed in last 24h
    Step 1: GET predictor.aspx?url={eventId}&token={random}
      → parse category list [{catId, catName, riderCount}]
    Step 2: For each category:
      GET predictor.aspx?url={eventId}&cat={catId}&v=1
      → parse HTML table: [{rank, name, team, racerID, points}]
    Upsert Startlist rows (source="road-results", carried_points=points)
    Record RefreshLog entry
```

### GraphQL Event Discovery

The `outsideapi.com/fed-gw/graphql` endpoint serves the same data as BikeReg's event calendar. Road-results' own events page calls this same API. The query:

```graphql
query AR_SearchUpcomingCX($first: Int, $searchParameters: SearchEventQueryParamsInput) {
  athleticEventCalendar(first: $first, searchParameters: $searchParameters) {
    nodes {
      name, startDate, endDate, latitude, longitude,
      city, state, eventId,
      athleticEvent { eventTypes, eventUrl }
    }
  }
}
```

Variables include `userDistanceFilter` (lat/lon/radius), `minDate`, `eventTypes: [1]` (cycling), and `appTypes: "BIKEREG"`. This returns upcoming events within the search radius, already filtered to future dates.

**Why this over scraping the region listing:** Live testing confirmed that road-results' region listing (`/?n=results&sn=all&region=4`) contains NO 2026 races — only historical results. The GraphQL API is the actual source of upcoming event data.

### Road-Results Predictor Endpoint

The predictor.aspx endpoint is road-results' race prediction tool. It takes a BikeReg eventId and returns registered riders ranked by their road-results power ranking.

**Step 1 — Category discovery:**
```
GET /predictor.aspx?url={eventId}&token={random}
```
Returns HTML with category headers like:
```html
<div class='predictorheader'>
  <span class='categoryname' raceid='74287-3'>Master Men 40+ 1/2/3</span>
</div>
```

**Step 2 — Ranked riders per category:**
```
GET /predictor.aspx?url={eventId}&cat={catId}&v=1
```
Returns HTML table:
```html
<table class='datatable1'>
  <tr><td>1. <a href="?n=racers&sn=r&rID=1162">Brian Breach</a></td>
      <td>Stages by Cuore</td><td>267.12</td></tr>
  ...
</table>
```

Each row contains: rank, rider name, link with rID (= RacerID), team name, and power ranking points. **Lower points = stronger rider** (road-results uses an Elo-like system where points decrease with better performance).

### RefreshLog Table

Separate from `ScrapeLog` (which tracks historical result scraping). No foreign key on `race_id` to allow calendar-level entries.

```python
class RefreshLog(Base):
    __tablename__ = "refresh_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, nullable=True)       # NULL for calendar-level entries
    event_id = Column(Integer, nullable=True)       # BikeReg/GraphQL eventId
    refresh_type = Column(String, nullable=False)   # "calendar", "startlist"
    refreshed_at = Column(DateTime, nullable=False)
    status = Column(String, nullable=False)         # "success", "empty", "error"
    entry_count = Column(Integer, nullable=True)
    checksum = Column(String, nullable=True)        # SHA-256 of rider list
    error_message = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_refresh_log_lookup", "race_id", "refresh_type"),
    )
```

**Daily limit:** `should_refresh()` uses a sliding 24-hour window:
```sql
SELECT 1 FROM refresh_log
WHERE race_id = ? AND refresh_type = ?
AND refreshed_at > datetime('now', '-24 hours')
```

### Staleness Policy

A race edition is refreshable only if `Race.date >= today` (decided in interview). Races in the past — even in the current year — are never refreshed. This is the most conservative policy with road-results requests.

### BikeReg Transition

BikeReg code is **preserved intact** with `--source` flag for rollback:
- `--source road-results` (default): uses GraphQL + predictor.aspx pipeline
- `--source bikereg`: delegates to existing `search_upcoming_events()` and `fetch_startlist()`
- Both sources write to the same `Startlist` table with different `source` values
- BikeReg settings in `config.py` retained with deprecation comments

### Startlist Schema Changes

```python
# New columns on Startlist
carried_points = Column(Float, nullable=True)       # Road-results power ranking
road_results_racer_id = Column(Integer, nullable=True)  # rID from predictor
event_id = Column(Integer, nullable=True)           # BikeReg/GraphQL eventId
```

### Bug Fix: carried_points = 0.0 truthiness

All three critiques identified a pre-existing bug in `predictions.py`: `_rank_from_startlist()` uses `if r.carried_points` which treats `0.0` as falsy. A rider with `carried_points = 0.0` is ranked the same as one with no data. This sprint fixes it to `if r.carried_points is not None`.

---

## Implementation

### Phase 1: Schema & Refresh Infrastructure (~20% effort)

**Goal:** Add database tables and refresh-limiting logic before any data fetching. All subsequent phases depend on this.

**Files:**
- `raceanalyzer/db/models.py` — Add `RefreshLog` model; add columns to `Startlist`
- `raceanalyzer/refresh.py` — CREATE: `should_refresh()`, `is_refreshable()`, `record_refresh()`
- `raceanalyzer/config.py` — Add road-results settings
- `tests/test_refresh.py` — CREATE: Refresh logic tests

**Tasks:**
- [ ] Add `RefreshLog` model to `models.py` (schema above)
- [ ] Add `carried_points`, `road_results_racer_id`, `event_id` columns to `Startlist`
- [ ] Create `refresh.py` with:
  - `should_refresh(session, race_id, refresh_type) -> bool`: Returns False if refreshed in last 24h
  - `is_refreshable(race) -> bool`: Returns True only if `race.date is not None and race.date >= today`
  - `record_refresh(session, race_id, refresh_type, status, entry_count=None, checksum=None, error_message=None, event_id=None)`
- [ ] Add settings to `config.py`:
  - `road_results_search_lat: float = 47.6` (Seattle)
  - `road_results_search_lon: float = -122.3`
  - `road_results_search_radius_miles: int = 300`
  - `road_results_calendar_days_ahead: int = 90`
  - `road_results_predictor_delay: float = 1.0` (delay between predictor.aspx calls — lighter than scraper)
- [ ] Fix `_rank_from_startlist()` in `predictions.py`: change `if r.carried_points` to `if r.carried_points is not None`
- [ ] Tests:
  - `should_refresh` returns True on first call, False on second within 24h, True after 24h
  - `is_refreshable` returns True for future date, False for past date, False for None
  - `record_refresh` creates correct RefreshLog entry
  - `_rank_from_startlist` correctly handles `carried_points = 0.0`

### Phase 2: GraphQL Calendar Discovery (~25% effort)

**Goal:** Discover upcoming PNW races from the GraphQL API and persist as `Race` rows.

**Files:**
- `raceanalyzer/calendar_feed.py` — Add `search_upcoming_events_rr()` alongside existing BikeReg functions
- `raceanalyzer/cli.py` — Update `fetch-calendar` with `--source` flag
- `tests/test_calendar_feed.py` — Add road-results calendar tests

**Tasks:**
- [ ] Implement `search_upcoming_events_rr(settings) -> list[dict]`:
  - POST to `https://outsideapi.com/fed-gw/graphql` with the discovery query
  - Headers: `apollographql-client-name: crossresults`, `Content-Type: application/json`, browser UA
  - Variables: `first=50`, `eventTypes=[1]`, `minDate=today`, `appTypes="BIKEREG"`, `userDistanceFilter` from settings
  - Parse response: extract `eventId`, `name`, `startDate`, `city`, `state`, `eventUrl`
  - Return `[{"event_id": int, "name": str, "date": datetime, "city": str, "state": str, "registration_url": str}]`
  - Graceful: return `[]` on any failure
- [ ] Update `fetch-calendar` CLI command:
  - Add `--source` option: `["road-results", "bikereg"]`, default `"road-results"`
  - When `road-results`: call `search_upcoming_events_rr()`, create/update Race rows with `is_upcoming=True`, `registration_source="road-results"`, `event_id` stored for startlist fetching
  - Fuzzy-match to existing RaceSeries via `match_event_to_series()` (already source-agnostic)
  - When `bikereg`: delegate to existing `search_upcoming_events()`
  - Log discovered events with date and matched series
  - Set `is_upcoming=False` on any Race rows with `date < today` (cleanup stale flags)
- [ ] Mark BikeReg functions in `calendar_feed.py` with deprecation docstrings
- [ ] Tests:
  - Mock GraphQL response with 3 upcoming events; verify Race rows created with correct fields
  - Mock GraphQL response with empty nodes; verify graceful empty return
  - Verify fuzzy match to existing series
  - Verify `--source bikereg` delegates to BikeReg
  - Verify `is_upcoming=False` cleanup for past races

### Phase 3: Predictor.aspx Startlist Fetching (~35% effort)

**Goal:** Fetch pre-registered riders ranked by power points from road-results' predictor endpoint.

**Files:**
- `raceanalyzer/scraper/client.py` — Add `fetch_predictor_categories()` and `fetch_predictor_category()` methods
- `raceanalyzer/scraper/parsers.py` — Add `PredictorCategoryParser` and `PredictorRiderParser`
- `raceanalyzer/startlists.py` — Add `fetch_startlist_rr()` alongside existing BikeReg function
- `raceanalyzer/cli.py` — Update `fetch-startlists` with `--source` and `--dry-run` flags
- `tests/test_startlists.py` — Add road-results startlist tests

**Tasks:**
- [ ] Add `fetch_predictor_categories(self, event_id: int) -> str` to `RoadResultsClient`:
  - GET `{base_url}/predictor.aspx?url={event_id}&token={random}`
  - Returns raw HTML response
  - Uses `_request_with_retry()` for rate limiting and retries
- [ ] Add `fetch_predictor_category(self, event_id: int, cat_id: str) -> str` to `RoadResultsClient`:
  - GET `{base_url}/predictor.aspx?url={event_id}&cat={cat_id}&v=1`
  - Returns raw HTML response
  - Rate limited at `road_results_predictor_delay` (1s between calls — lighter endpoint)
- [ ] Implement `PredictorCategoryParser` in `parsers.py`:
  - Input: HTML from predictor.aspx?url={eventId}
  - Extract category entries from `<span class='categoryname' raceid='{catId}'>{catName}</span>`
  - Also extract total rider count from "This race has N racers preregistered"
  - Returns `[{"cat_id": str, "cat_name": str}]`
- [ ] Implement `PredictorRiderParser` in `parsers.py`:
  - Input: HTML from predictor.aspx?url={eventId}&cat={catId}&v=1
  - Extract rider rows from `<table class='datatable1'>` rows
  - Parse: rank (from "N. " prefix), name (from `<a href="?n=racers&sn=r&rID={rID}">` link), team (second `<td>`), points (third `<td>`)
  - Returns `[{"rank": int, "name": str, "racer_id": int, "team": str, "points": float}]`
  - Conservative: returns `[]` on unexpected HTML structure
- [ ] Implement `fetch_startlist_rr(client, race, session) -> list[dict]`:
  - Check `is_refreshable(race)` and `should_refresh(session, race.id, "startlist")`
  - If not refreshable, return `[]` with log message
  - Fetch categories via `fetch_predictor_categories(race.event_id)`
  - For each category, fetch ranked riders via `fetch_predictor_category()`
  - Match `racer_id` to existing `Rider.road_results_id` to set `rider_id`
  - Return `[{"name", "team", "category", "racer_id", "rider_id", "carried_points", "rank"}]`
- [ ] Update `fetch-startlists` CLI command:
  - Add `--source` option: `["road-results", "bikereg"]`, default `"road-results"`
  - Add `--dry-run` flag: print which races would be refreshed without making requests
  - When `road-results`: query `Race WHERE is_upcoming=True AND date >= today`, call `fetch_startlist_rr()` for each
  - **Clear-and-reinsert** (atomic): within a transaction, delete existing `source="road-results"` Startlist rows for this race, then insert new rows. Rollback on failure.
  - Upsert `Startlist` rows with: `source="road-results"`, `carried_points`, `road_results_racer_id`, `event_id`, `category`
  - Record `RefreshLog` entry with status and checksum
  - Print per-race summary: "Mason Lake 1: 51 riders (6 categories)" or "Skipped: refreshed 3h ago"
  - When `bikereg`: delegate to existing `fetch_startlist()`
- [ ] Mark BikeReg functions in `startlists.py` with deprecation docstrings
- [ ] Tests:
  - Mock predictor.aspx category response; verify category parsing
  - Mock predictor.aspx rider response; verify name, team, racer_id, points extraction
  - Mock empty predictor response; verify graceful `[]` return
  - Verify clear-and-reinsert is atomic (rollback on failure preserves old data)
  - Verify `should_refresh` blocks second call on same day
  - Verify `is_refreshable` blocks past-date races
  - Verify `--source bikereg` delegates to BikeReg
  - Verify `--dry-run` makes no HTTP calls

### Phase 4: Integration, Cleanup & Hardening (~20% effort)

**Goal:** Wire predictions to use inline carried_points, harden error paths, verify end-to-end.

**Files:**
- `raceanalyzer/predictions.py` — Update `_rank_from_startlist()` to prefer `Startlist.carried_points`
- `raceanalyzer/scraper/client.py` — Add `JSONDecodeError` catch to `fetch_race_json()`
- `tests/test_predictions.py` — Add road-results startlist ranking tests
- `tests/test_scraper.py` — Add predictor endpoint tests

**Tasks:**
- [ ] Update `_rank_from_startlist()` in `predictions.py`: when `entry.carried_points is not None`, use it directly instead of historical `Result` lookup. Fall back to historical lookup only when `carried_points` is None.
- [ ] Fix pre-existing bug in `fetch_race_json()` (client.py line 84): add `try/except json.JSONDecodeError` around `response.json()` — return `[]` on decode failure (handles Cloudflare challenge pages)
- [ ] Handle edge case: predictor.aspx returns 500 for invalid category — catch and skip that category
- [ ] Handle edge case: rider name with asterisk ("Brian Breach *") — strip asterisks (road-results uses them for riders with < 4 scoring races)
- [ ] Add structured logging at INFO level for: events discovered, startlists fetched, refresh skipped (with reason)
- [ ] Add structured logging at WARNING level for: HTTP errors, empty predictor responses, parser failures
- [ ] Ensure `is_upcoming=False` is set on races whose date has passed (cleanup in `fetch-calendar`)
- [ ] Verify `match_event_to_series()` works with road-results event names (may need threshold adjustment)
- [ ] Run full test suite: `pytest tests/ -v`
- [ ] Run linter: `ruff check .`
- [ ] Tests:
  - `predict_contenders` with road-results startlist (carried_points set) — verify direct use
  - `predict_contenders` with carried_points=None — verify fallback to historical
  - `predict_contenders` with carried_points=0.0 — verify treated as valid (not falsy)
  - `fetch_race_json` with invalid JSON response — verify graceful `[]` return

---

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/db/models.py` | MODIFY | Add `RefreshLog` model; add `carried_points`, `road_results_racer_id`, `event_id` to `Startlist` |
| `raceanalyzer/refresh.py` | CREATE | `should_refresh()`, `is_refreshable()`, `record_refresh()` |
| `raceanalyzer/config.py` | MODIFY | Add road-results search settings; deprecation comments on BikeReg settings |
| `raceanalyzer/calendar_feed.py` | MODIFY | Add `search_upcoming_events_rr()` using GraphQL; deprecate BikeReg functions |
| `raceanalyzer/scraper/client.py` | MODIFY | Add `fetch_predictor_categories()`, `fetch_predictor_category()`; fix `JSONDecodeError` |
| `raceanalyzer/scraper/parsers.py` | MODIFY | Add `PredictorCategoryParser`, `PredictorRiderParser` |
| `raceanalyzer/startlists.py` | MODIFY | Add `fetch_startlist_rr()` using predictor.aspx; deprecate BikeReg functions |
| `raceanalyzer/predictions.py` | MODIFY | Prefer `Startlist.carried_points`; fix 0.0 truthiness bug |
| `raceanalyzer/cli.py` | MODIFY | `--source` flag on both commands; `--dry-run` on fetch-startlists; is_upcoming cleanup |
| `tests/test_refresh.py` | CREATE | Refresh logic tests |
| `tests/test_calendar_feed.py` | MODIFY | Add GraphQL discovery tests |
| `tests/test_startlists.py` | MODIFY | Add predictor.aspx parsing tests |
| `tests/test_predictions.py` | MODIFY | Add carried_points ranking tests |
| `tests/test_scraper.py` | MODIFY | Add predictor endpoint and JSONDecodeError tests |

---

## Definition of Done

### Calendar Discovery
- [ ] `fetch-calendar` discovers upcoming PNW races from GraphQL API
- [ ] Events within 300mi of Seattle and 90 days ahead are discovered
- [ ] Events are fuzzy-matched to existing `RaceSeries`
- [ ] `Race` rows created with `is_upcoming=True`, `registration_source="road-results"`, `event_id` stored
- [ ] Past races have `is_upcoming=False` set (cleanup)
- [ ] Graceful degradation: returns empty on GraphQL failure
- [ ] `--source bikereg` falls back to BikeReg calendar

### Startlist Fetching
- [ ] `fetch-startlists` fetches ranked registered riders from predictor.aspx
- [ ] Categories are discovered from predictor.aspx?url={eventId}
- [ ] Riders parsed per category with: name, team, racer_id, power ranking points
- [ ] `Startlist` rows created with `source="road-results"`, `carried_points`, `road_results_racer_id`
- [ ] Clear-and-reinsert is atomic (transaction rollback on failure)
- [ ] Riders linked to existing `Rider` rows via `road_results_id`
- [ ] `--source bikereg` falls back to BikeReg startlists
- [ ] `--dry-run` shows plan without making requests

### Refresh Limiting
- [ ] Each race edition is refreshed at most once per 24 hours
- [ ] Races with `date < today` are never refreshed
- [ ] `RefreshLog` tracks all refresh attempts with timestamp, status, and checksum
- [ ] Skipped races are logged with reason

### Request Safety
- [ ] GraphQL requests use browser user-agent
- [ ] predictor.aspx requests go through `RoadResultsClient` with rate limiting
- [ ] Minimum delay between predictor.aspx calls (1s per category, 3s between races)
- [ ] Retry with exponential backoff on 403/429/5xx

### Predictions
- [ ] `_rank_from_startlist()` prefers `Startlist.carried_points` when available
- [ ] Falls back to historical lookup when `carried_points` is None
- [ ] `carried_points = 0.0` is treated as a valid value (not falsy)

### Testing
- [ ] Refresh logic: 6+ tests (should_refresh, is_refreshable, record_refresh, carried_points truthiness)
- [ ] Calendar discovery: 4+ tests (GraphQL happy path, empty, match to series, bikereg fallback)
- [ ] Startlist fetching: 6+ tests (category parsing, rider parsing, empty response, atomic clear-reinsert, refresh limit, bikereg fallback)
- [ ] Predictions: 3+ tests (inline carried_points, None fallback, 0.0 handling)
- [ ] All existing tests pass
- [ ] `ruff check .` passes

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **GraphQL API changes or adds authentication** | Low | High | API is public, used by road-results' own frontend. If it changes, fall back to `--source bikereg`. Monitor for schema changes. |
| **predictor.aspx HTML structure changes** | Medium | Medium | Parsers return `[]` on unexpected structure. Road-results has used this same predictor format for years. Tests catch regressions. |
| **predictor.aspx returns 500 for some categories** | Medium | Low | Already observed during testing. Catch and skip individual categories; log warning. Other categories still processed. |
| **Pre-registration data is sparse early in season** | High | Low | Expected. `predict_contenders()` Tier 2/3 fallbacks handle this. Startlists grow as race day approaches. |
| **GraphQL returns events from multiple disciplines** | Medium | Medium | Filter by `eventTypes: [1]` (cycling). Series matching also filters non-road events. Unmatched events get `series_id=None`. |
| **eventId doesn't map to road-results race ID** | High | Low | We don't need the road-results race ID — predictor.aspx takes eventId directly. The Startlist links via `event_id` and `road_results_racer_id`. |
| **Rate limiting on predictor.aspx** | Low | Medium | 1s delay between category calls, 3s between races. Total volume for 20 upcoming races × 5 categories = ~100 requests × 1s = ~2 minutes. Exponential backoff on 429. |
| **Concurrent CLI invocations create duplicate Startlist rows** | Medium | Medium | Clear-and-reinsert within transaction. SQLite write lock serializes concurrent access. RefreshLog prevents both from proceeding if one finishes first. |
| **cloudscraper blocked by Cloudflare upgrade** | Low | High | Existing risk for entire scraper. predictor.aspx may be lighter on protection than main site. GraphQL endpoint is separate domain (outsideapi.com). |

---

## Security

- **No new credentials.** Both the GraphQL API and predictor.aspx are public endpoints requiring no authentication.
- **Browser user-agent.** All requests use existing `BROWSER_HEADERS` via `cloudscraper`. GraphQL requests also include `apollographql-client-name: crossresults` (matching road-results' own frontend).
- **Rate limiting.** 1s between predictor.aspx category calls, 3s between race-level operations. Daily refresh cap bounds total volume to ~100 requests/day for a typical PNW season.
- **No PII.** Rider names, teams, and power ranking points are all publicly displayed on road-results.com.
- **Input sanitization.** All parsed values go through safe parsing functions. No string interpolation into SQL — all DB ops use SQLAlchemy ORM.

---

## Dependencies

**Existing Python packages (no changes):**
- `cloudscraper`, `requests`, `sqlalchemy`, `click`, `pandas`, `responses` (test)

**New Python packages: None.**

**External services:**
- `outsideapi.com/fed-gw/graphql` — Event discovery (new endpoint)
- `road-results.com/predictor.aspx` — Ranked startlists (new endpoint)

---

## Open Questions

1. **Does the GraphQL API have rate limiting?** Initial testing showed no issues, but sustained use may trigger limits. Mitigation: the daily refresh cap means we make at most 1 GraphQL call per day.

2. **Does predictor.aspx always return riders sorted by points?** Testing confirmed this for Mason Lake 1 (March 2026). Verify during implementation with multiple events to confirm consistency.

3. **How does road-results handle riders who change categories between registration and race day?** predictor.aspx shows riders in their registered category. If they switch, the old category entry persists until the next predictor.aspx refresh. The clear-and-reinsert strategy handles this naturally.

4. **Should unmatched events create new RaceSeries?** Recommendation: No. Create `Race` with `series_id=NULL` and log for manual review. `build-series` can link them later after importing historical data.

5. **What about events outside the search radius?** The GraphQL query uses a 300-mile radius from Seattle. This covers WA, OR, and parts of BC/ID. Events in eastern Oregon or Montana may be missed. Add a second search center or increase radius in a future sprint if needed.

6. **Should we track the mapping between BikeReg eventId and road-results race ID?** For this sprint, we don't need the road-results race ID — predictor.aspx takes eventId directly. If future sprints need to link to road-results' historical data, we'll need this mapping. For now, `Race.event_id` stores the BikeReg eventId.
