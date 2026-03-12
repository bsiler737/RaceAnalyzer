# Sprint 008 Intent: P0 Race Intelligence — Interactive Maps, Predictions & Narrative

## Seed

Implement the 12 P0 user stories from the prioritized backlog (`best_user_stories.md`). These stories represent the core product — helping new racers understand race strategy and tactics through predictive intelligence mapped onto the course. The stories span three domains:

**Interactive Mapping** (#1, #2, #3, #10, #19):
- #1 Interactive Course Map — full interactive map with zoom/pan (foundation for all spatial features)
- #2 Elevation Profile Overlaid on Map — elevation profile synced to map with hover highlighting
- #3 Climb Segments on Map — individual climbs color-coded by gradient
- #10 Wind Exposure Zones — exposed vs. sheltered sections for crosswind/echelon risk
- #19 Predicted Key Moments on Map — pins showing where splits, attacks, regrouping happen

**Predictive Intelligence** (#11, #12, #16, #17, #18, #20):
- #11 Predicted Finish Type — already has a baseline in `predictions.py`; needs enhanced UX
- #12 Pack Odds — probability of finishing with the main group vs. getting dropped
- #16 Typical Finishing Speeds — average speeds from previous editions by category
- #17 Drop Rate — historical DNF/drop percentage by category
- #18 "What to Expect" Summary — plain-language narrative describing the race
- #20 Weather-Adjusted Predictions — factor weather forecast into predictions

**Visualization** (#28):
- #28 Animated Race Replay — simplified replay showing how gaps developed in past editions

The scope is large (12 stories). Drafts should propose how to phase these across 2-3 sprints while keeping each sprint deliverable and valuable independently.

## Context

- **Sprint 007 just shipped**: Schema foundation (Course, Startlist, UserLabel models), baseline finish-type predictions, elevation extraction, terrain classification, Race Preview page, contender ranking. This is the foundation all P0 stories build on.
- **Existing map infrastructure**: `raceanalyzer/ui/maps.py` renders course polylines via Folium with start/finish markers. RWGPS polylines stored on `RaceSeries.rwgps_encoded_polyline`.
- **Existing predictions**: `predictions.py` has `predict_series_finish_type()` (weighted historical frequency) and `predict_contenders()` (3-tier degradation). Race Preview page shows these.
- **Elevation data available**: `Course` model has `distance_m`, `total_gain_m/loss_m`, `max/min_elevation_m`, `m_per_km`, `course_type`. RWGPS track_points include per-point elevation.
- **Tech stack**: Python, SQLAlchemy ORM, SQLite, Streamlit UI, Folium for maps, Plotly for charts, pandas for data manipulation.

## Recent Sprint Context

- **Sprint 001-003**: Data pipeline (scraper, classifier, series dedup)
- **Sprint 004-005**: RWGPS integration, course map rendering, classification refinement
- **Sprint 006**: Series deduplication, route matching
- **Sprint 007**: Schema foundation, baseline predictions, terrain classification, Race Preview page

## Relevant Codebase Areas

| Module | Purpose | Relevance |
|--------|---------|-----------|
| `raceanalyzer/db/models.py` | 9 ORM models | Course, Result, RaceClassification have the data needed |
| `raceanalyzer/predictions.py` | Baseline finish type + contender prediction | Needs extension for pack odds, drop rate, speeds |
| `raceanalyzer/elevation.py` | Terrain classification | Foundation for climb segment detection |
| `raceanalyzer/rwgps.py` | RWGPS route fetching | Has track_points with lat/lon/elevation per point |
| `raceanalyzer/queries.py` | Query helpers, `get_race_preview()` | Will need new queries for historical stats |
| `raceanalyzer/ui/maps.py` | Folium course map, geocoding | Needs major extension for interactive features |
| `raceanalyzer/ui/charts.py` | Plotly charts | Elevation profile rendering target |
| `raceanalyzer/ui/pages/race_preview.py` | Race Preview page | Primary UI surface for all P0 stories |
| `raceanalyzer/ui/components.py` | Reusable UI components | Badges, cards, etc. |
| `raceanalyzer/config.py` | Settings (terrain thresholds, etc.) | Weather API config, new thresholds |

## Constraints

- Must follow existing patterns: SQLAlchemy ORM, Streamlit UI, graceful degradation, qualitative labels (no raw probabilities)
- No new heavyweight dependencies (prefer extending Folium/Plotly/pandas)
- RWGPS track_points are the primary geospatial data source (lat/lon/elevation per point)
- Weather data requires an external API (Open-Meteo is free, no API key needed)
- Wind exposure analysis needs terrain/land-use data beyond what RWGPS provides — may need OpenStreetMap or heuristic approach
- Animated replay (#28) needs historical gap data from `Result.gap_to_leader` and `Result.gap_group_id`
- "Key moments" (#19) require correlating elevation features with historical race data — this is the hardest feature
- All features must degrade gracefully when data is missing

## Success Criteria

1. A racer can open a Race Preview page and see an interactive course map with climb segments highlighted by gradient
2. An elevation profile chart is synced to the map (hover/click on one highlights the other)
3. The racer sees predicted finish type (from Sprint 007) PLUS: drop rate, typical speeds, and pack odds
4. A "What to Expect" narrative summarizes the race in plain English
5. For races with sufficient history, key moments are pinned on the map
6. Weather-adjusted predictions factor in forecast data
7. An animated replay visualizes how past editions played out

## Verification Strategy

- **Unit tests**: Each prediction function (drop rate, pack odds, speeds) tested with known historical data
- **Integration tests**: Race Preview page renders with all new components without errors
- **Graceful degradation**: Each feature tested with missing data (no history, no weather, no track_points)
- **Visual verification**: Map features (climb coloring, wind zones, key moments) manually inspected
- **Baseline comparison**: New prediction features compared against naive baselines

## Uncertainty Assessment

- **Correctness uncertainty: Medium** — Prediction algorithms (pack odds, key moments) are novel; no reference implementation exists. Need to define what "correct" means for narrative generation.
- **Scope uncertainty: High** — 12 stories across mapping, prediction, and visualization. Must be phased across 2-3 sprints. Risk of trying to do too much in one sprint.
- **Architecture uncertainty: Medium** — Map interactivity within Streamlit/Folium has known limitations (Folium maps are not natively interactive in Streamlit the way React maps would be). Elevation profile ↔ map sync requires careful design. Weather API integration is straightforward but wind exposure analysis is architecturally novel.

## Open Questions

1. **How to phase 12 stories across sprints?** Should Sprint 008 focus on the map foundation (#1, #2, #3) + historical stats (#16, #17), leaving predictions (#12, #18, #20) and advanced features (#10, #19, #28) for Sprint 009+?

2. **Folium interactivity limits**: Streamlit's Folium integration (`st_folium`) has limited bidirectional communication. How do we sync elevation profile hover with map highlighting? Options: (a) Plotly chart + Folium side-by-side with click-to-scroll, (b) custom HTML/JS component, (c) use Deck.gl via `pydeck` instead of Folium.

3. **Wind exposure data source**: RWGPS track_points have lat/lon/elevation but not terrain type. Options: (a) heuristic based on elevation (exposed = above treeline or flat with no nearby hills), (b) OpenStreetMap land-use data, (c) manual annotation. Which approach balances accuracy with build effort?

4. **"Key moments" algorithm**: How do we identify where races split? Options: (a) correlate climb locations with historical gap data, (b) use gradient change points, (c) crowdsource from user annotations. The first option requires sufficient historical data per location.

5. **Narrative generation (#18)**: Use LLM (Claude API) for natural language, or template-based? Template is simpler and more predictable; LLM produces more natural prose but adds API dependency.

6. **Weather API selection**: Open-Meteo (free, no key) vs. OpenWeatherMap (free tier, key required) vs. Weather.gov (US only, free). Open-Meteo seems simplest.

7. **Animated replay (#28)**: What technology? Options: (a) Plotly animation frames, (b) custom JS/HTML animation in Streamlit, (c) pre-rendered GIF/video. Historical data granularity (only finish times, not mid-race positions) limits replay fidelity.

8. **Pack odds calculation (#12)**: Based on what inputs? Options: (a) historical drop rate * rider's relative fitness, (b) course difficulty * category field size, (c) simple lookup from similar past races. Need to define the model.
