# Sprint 007 Intent: Schema Foundation, Baseline Predictions & Race Preview

## Seed

Implement the improvements specified in `mid-plan-improvements.md`, starting with Sprint 2a ("Ship Something Racers Can Use"). The goal: a Cat 3 racer in Seattle can open the app on their phone, see upcoming races with predicted finish types and top contenders, and decide which race to target this weekend.

Key deliverables from mid-plan-improvements.md §Sprint 2a:
1. Schema changes: courses table, rating columns, startlists table, user_labels table
2. Basic elevation stats from RWGPS (m/km, total gain) → 4-bin terrain classification
3. Baseline heuristic predictions using carried_points (benchmark for all future models)
4. BikeReg startlist integration (API/CSV) with graceful degradation tiers
5. Race Preview page (mobile-first): predicted finish type + terrain + top contenders
6. Upcoming race calendar with BikeReg/OBRA schedule data

## Context

- **Sprint 006 (Course Maps & Series Dedup)** is the most recent sprint. It added `RaceSeries` table, RWGPS route matching, Folium polyline rendering, series detail pages, and name normalization. This sprint builds directly on that foundation.
- **6-table schema** exists: `race_series`, `races`, `riders`, `results`, `race_classifications`, `scrape_log`. No courses, ratings, startlists, or user_labels tables yet.
- **Classification pipeline** is complete: gap-based grouping → rule-based finish type classifier → confidence badges. CV of times computed but only used for confidence, not classification.
- **UI** has Calendar, Series Detail, Race Detail, and Dashboard pages in Streamlit. All backward-looking — no forward-looking predictions or upcoming race features.
- **Dependencies** include SQLAlchemy 2.0, Streamlit, Folium, Plotly, requests-futures. `skelo` (Glicko-2) and `scipy` are planned but not yet added.

## Recent Sprint Context

- **Sprint 006**: Added RaceSeries model with normalized_name grouping, RWGPS route search/scoring/polyline caching, series detail page with classification trend charts, calendar tile grouping by series. Key patterns: 3-component scoring algorithm, LRU-cached normalization, fallback maps when no route match.
- **Sprint 005**: Dashboard with finish type distribution, category breakdown, heatmap.
- **Sprint 004**: UI foundation — Streamlit multi-page app, calendar page, race detail page.
- **Sprint 003**: Rule-based finish type classification with confidence badges.

## Relevant Codebase Areas

| Module | Relevance |
|--------|-----------|
| `raceanalyzer/db/models.py` | Must add Course, rating columns, startlist, user_labels tables |
| `raceanalyzer/queries.py` | Must add prediction queries, upcoming race queries, scary racer improvements |
| `raceanalyzer/rwgps.py` | Already fetches route data — must extract elevation stats (total gain, distance) |
| `raceanalyzer/classification/` | Finish type classifier — predictions will extend this |
| `raceanalyzer/ui/pages/` | Must add Race Preview page, modify calendar for upcoming races |
| `raceanalyzer/cli.py` | Must add commands for startlist scraping, elevation extraction |
| `raceanalyzer/scraper/` | Pattern for new BikeReg/OBRA scrapers |
| `tests/` | In-memory SQLite, `responses` mocking, parametrized edge cases |

## Constraints

- Must follow existing SQLAlchemy ORM patterns (no raw SQL except in queries.py)
- Must maintain idempotent CLI commands (safe to re-run)
- Must use `responses` library for HTTP mocking in tests
- Must maintain >85% test coverage
- UI must use natural language + badges, not raw decimals (per research-findings.md)
- Never show uncalibrated probabilities as numbers — use qualitative labels
- Rate limiting: 2s base delay for any new scraping, exponential backoff on 429
- Mobile-first design for all new UI components (Streamlit responsive layouts)
- Graceful degradation: every feature must work with missing data
- Use Claude Opus 4.6 for all coding tasks (per CLAUDE.md)

## Success Criteria

1. **Schema**: `courses` table stores elevation stats (total_gain, distance, m_per_km, course_type enum). Rating columns (mu, sigma) on riders and results. `startlists` and `user_labels` tables exist.
2. **Elevation**: `raceanalyzer elevation-extract` CLI command populates courses table from RWGPS data. 4-bin terrain classification (flat/rolling/hilly/mountainous) works.
3. **Baseline predictions**: Given a race series + category, the system predicts finish type based on historical data and ranks likely top finishers using carried_points percentile. Must beat random baseline.
4. **Startlists**: BikeReg API/CSV integration fetches registered riders for upcoming PNW races. Graceful fallback to "historical performers at this event" when no startlist available.
5. **Race Preview page**: Mobile-friendly page showing predicted finish type, terrain classification, course map, top contenders (from startlist or history), and confidence indicators.
6. **Upcoming calendar**: Calendar page shows upcoming races with registration links and predicted finish types alongside historical race series.

## Verification Strategy

- **Reference implementation**: `mid-plan-improvements.md` defines the spec. `research-findings.md` and `exemplary-code.md` define best practices.
- **Baseline benchmark**: Heuristic model must demonstrably beat "predict most common finish type for category" baseline.
- **Edge cases**: Races with no RWGPS route (fallback to no-terrain), races with no historical data (fallback to category average), startlists unavailable (fallback to historical performers), single-edition series, new riders with no history.
- **Testing approach**: Unit tests for elevation extraction, terrain classification, prediction logic, startlist parsing. Integration tests for Race Preview page data assembly. Mock BikeReg/OBRA HTTP responses.

## Uncertainty Assessment

- **Correctness uncertainty: Medium** — Prediction logic is novel for this codebase. Elevation extraction from RWGPS depends on undocumented API data availability. BikeReg API stability unknown.
- **Scope uncertainty: High** — Sprint 2a in mid-plan-improvements.md is ambitious (6 major deliverables). May need to cut startlist scraping or upcoming calendar if BikeReg API proves difficult. The document itself notes this is "2-3 weeks" of work.
- **Architecture uncertainty: Medium** — New tables and prediction layer are new patterns. Course-to-prediction pipeline is a new data flow. But the existing patterns (SQLAlchemy models, CLI commands, Streamlit pages) provide clear templates.

## Open Questions

1. **BikeReg API availability**: Does BikeReg have a public REST API, or is it CSV-export only? What's the rate limit? Is there a "Confirmed Riders" endpoint per event?
2. **RWGPS elevation data**: Does the undocumented search endpoint return total_elevation_gain and distance, or do we need to compute from polyline coordinates?
3. **Sprint scope**: Should we attempt all 6 deliverables, or cut to the 4 most impactful (schema + elevation + predictions + Race Preview) and defer startlists + upcoming calendar to Sprint 008?
4. **Prediction granularity**: Should baseline predictions be per-series (all editions) or per-series-per-category? The latter is more accurate but has sparser data.
5. **Race Preview page placement**: New top-level page, or a tab/view within the existing Series Detail page?
6. **Course version tracking**: mid-plan-improvements.md mentions keying by distance +/-1km & gain +/-50m. Is this needed now or can we defer to when we have more course data?
