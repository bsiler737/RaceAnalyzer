# Sprint 009 Intent: Road-Results Integration for Registered Riders & Power Rankings

## Seed

Replace BikeReg integration with Road-Results integration for pulling registered riders and power rankings. Key requirements:
1. Pull registered riders from road-results instead of bikereg
2. Use road-results' existing power ranking methodology (carried_points / points from their JSON API)
3. Spoof user-agent to appear as a browser (already done for the scraper — extend to new endpoints)
4. Rate limiting: max daily refreshes per race edition (1 refresh/day/edition)
5. No refreshes for race editions that don't have an upcoming race in the current year
6. Road-results wants to see a spoofed browser user-agent

## Context

- **Project**: RaceAnalyzer — PNW bike race analysis tool that scrapes road-results.com for historical results, classifies finish types, and predicts race outcomes
- **Current state**: Sprint 008 complete (interactive course maps, historical stats, narrative generator). The system currently uses BikeReg for two functions: (1) discovering upcoming events via `calendar_feed.py`, and (2) fetching pre-registered riders via `startlists.py`. These feed into `predictions.py` which ranks contenders by `carried_points` from historical results.
- **Road-results already integrated for historical data**: The scraper (`scraper/client.py`) already uses `cloudscraper` with browser UA headers and has robust rate limiting (3s delay, exponential backoff, retry logic). The JSON API already returns `Points` and `CarriedPoints` fields per result — this IS road-results' power ranking system.
- **The gap**: Road-results also hosts pre-registration lists and upcoming race information for PNW races, but we currently only use it for historical results. BikeReg coverage is incomplete and the data doesn't include power rankings.
- **Architecture is ready**: The `Startlist` model already has a `source` field supporting multiple sources. The `predictions.py` contender ranking already uses `carried_points`. This sprint primarily needs new data acquisition, not architectural changes.

## Recent Sprint Context

- **Sprint 008**: Interactive course maps, climb detection, historical stats (drop rate, speeds), narrative generator
- **Sprint 007**: Schema foundation, baseline predictions, race preview page
- **Sprint 006**: Calendar feed (BikeReg), startlist fetching, contender predictions
- The BikeReg integration was built in Sprint 006 as a minimum viable approach. Road-results is the primary data source for PNW racing and provides richer data.

## Relevant Codebase Areas

### Data Acquisition (to be modified/replaced)
- `raceanalyzer/startlists.py` — BikeReg startlist fetcher (119 lines) — **REPLACE** with road-results
- `raceanalyzer/calendar_feed.py` — BikeReg calendar search (140 lines) — **REPLACE** with road-results upcoming race discovery
- `raceanalyzer/scraper/client.py` — Road-results HTTP client with rate limiting — **EXTEND** with new endpoints

### Existing Infrastructure (to leverage)
- `raceanalyzer/scraper/client.py` — `RoadResultsClient` with cloudscraper, browser UA, rate limiting, retry logic
- `raceanalyzer/scraper/parsers.py` — `RaceResultParser` already extracts `points`, `carried_points`, `racer_id`
- `raceanalyzer/config.py` — `Settings` dataclass with `min_request_delay`, `base_url`, etc.
- `raceanalyzer/predictions.py` — `predict_contenders()` with three-tier ranking using `carried_points`
- `raceanalyzer/db/models.py` — `Startlist` model with `source` field, `Race` with `is_upcoming`, `registration_url`

### CLI & UI (to update)
- `raceanalyzer/cli.py` — `fetch-calendar` and `fetch-startlists` commands
- `raceanalyzer/queries.py` — `get_race_preview()` assembles contender data
- `raceanalyzer/ui/pages/race_preview.py` — Race Preview page

### Tests
- `tests/test_startlists.py` — BikeReg startlist tests
- `tests/test_calendar_feed.py` — BikeReg calendar tests
- `tests/test_scraper.py` — Road-results scraper tests (pattern to follow)

## Constraints

- **Browser user-agent required**: road-results.com blocks non-browser UAs. Must use the existing `BROWSER_HEADERS` pattern from `scraper/client.py` with `cloudscraper`.
- **Rate limiting**: Reuse existing 3s minimum delay between requests. Add a new constraint: max 1 refresh per race edition per day (track via `ScrapeLog` or new table).
- **No refreshes for stale editions**: Race editions that don't have an upcoming race in the current calendar year should never be refreshed. This prevents hammering road-results for historical data that won't change.
- **Graceful degradation**: Follow existing pattern — return empty results on failure, never crash. The BikeReg fallback pattern in `startlists.py` is the model.
- **Test with `responses` library**: Follow existing test patterns using the `responses` mock library.
- **SQLAlchemy ORM**: All DB changes via existing ORM patterns.
- **Click CLI**: All new commands via existing Click group pattern.

## Success Criteria

1. `fetch-calendar` discovers upcoming PNW races from road-results.com (not BikeReg)
2. `fetch-startlists` pulls pre-registered riders from road-results.com with their power ranking points
3. Contender rankings in Race Preview use road-results power rankings (carried_points) as the primary sort
4. Each race edition is refreshed at most once per day
5. Race editions without an upcoming race in the current year are never refreshed
6. All requests use browser-spoofed user-agent via cloudscraper
7. Rate limiting enforces ≥3s between requests
8. Existing tests pass; new tests cover road-results integration
9. BikeReg code is cleanly deprecated (kept but no longer the primary path)

## Verification Strategy

- **Reference implementation**: The existing `scraper/client.py` + `parsers.py` demonstrate the correct pattern for road-results integration
- **Spec**: road-results.com JSON API returns `Points`, `CarriedPoints`, `RacerID` fields — already parsed by `RaceResultParser`
- **Edge cases**:
  - Race with no pre-registered riders → empty startlist, fall back to series history
  - Race edition with no upcoming date → skip refresh entirely
  - Rate limit exceeded (429) → exponential backoff (existing pattern)
  - road-results down / 403 → graceful degradation, return empty
  - Duplicate riders across categories → dedup by `racer_id`
  - Race name doesn't match any series → create new series or leave unlinked
- **Testing approach**: Unit tests with `responses` mocks for all new HTTP calls, integration tests for the refresh-limiting logic, existing test suite must pass

## Uncertainty Assessment

- **Correctness uncertainty: Medium** — Road-results' pre-registration page structure and URL patterns need to be discovered/confirmed. The JSON API for results is well-understood, but the pre-reg endpoint may differ.
- **Scope uncertainty: Low** — Clear requirements: replace BikeReg with road-results for two specific functions (calendar + startlists), add daily refresh limits.
- **Architecture uncertainty: Low** — Extends existing patterns (RoadResultsClient, parsers, Startlist model). No new architectural concepts needed.

## Open Questions

1. **What URL pattern does road-results use for pre-registration/upcoming race pages?** The existing scraper uses `/race/{id}` for results and `/?n=results&sn=all&region={region}` for discovery. Need to identify the pre-reg endpoint — likely `/race/{id}` with a different section, or a separate page.
2. **How does road-results organize upcoming vs. past races?** Is there a dedicated upcoming/calendar page, or do we discover upcoming races from the region listing?
3. **Should BikeReg code be fully removed or kept as a secondary source?** The user said "pull from road-results instead" — suggests replacement, but keeping BikeReg as a fallback adds resilience.
4. **How should we track daily refresh limits?** Options: (a) extend `ScrapeLog` with a `last_refreshed_at` column, (b) new `RefreshLog` table, (c) use file-based timestamps.
5. **What constitutes "upcoming race in the current year"?** Is it: (a) race has a `date` in the current calendar year AND `date >= today`, or (b) race has `is_upcoming=True`, or (c) series has any edition with a future date?
6. **Does road-results provide power rankings separately from race results?** Or do we compute rankings from `carried_points` in historical results (which we already have)?
