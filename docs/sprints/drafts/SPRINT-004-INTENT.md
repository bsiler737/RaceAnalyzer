# Sprint 004 Intent: Race Tiles UI + Scary Racers

## Seed

Overhaul the main page to show a 3-wide grid of race tiles. Each tile has: race name, a small icon indicating race type (crit, road race, hill climb, stage race), and a small Strava-style map of the race course. Clicking a tile navigates to race detail. The detail page shows category breakdowns and a "Scary Racers" section — predicted top performers based on historical results, with bonus weight for riders who've won similar race types. The goal: users see a broad overview of races and immediately understand each race's character, then drill into category-specific analysis and see who's dangerous. Fun personality encouraged ("Scary Racers" is a real feature name). Needs new synthetic data (course coordinates, rider win history), backend changes (race type field, rider strength model), and UI overhaul.

## Context

- Sprint 001 delivered scraper + classifier + CLI
- Sprint 002 delivered Streamlit UI (calendar table, race detail, dashboard)
- Sprint 003 delivered synthetic demo data (50 races, 80 riders, 5 years, 8 finish types)
- road-results.com still blocking IP — all work is against synthetic data
- Current UI is functional but plain: table-based calendar, selectbox navigation
- No "race type" field in DB (crit vs road race vs hill climb) — only finish type classification
- No course geometry/coordinates in DB
- No rider performance history tracking (wins, placements across races)
- 119 tests passing, clean architecture with query layer separated from UI

## Recent Sprint Context

- Sprint 003 just completed: seed-demo/clear-demo commands, 50 races with realistic finish type distributions
- Classifier fix: SMALL_GROUP_SPRINT now reachable in decision tree, all 8 finish types tested
- Race detail page: added sidebar race selector (was broken with query params only)
- Demo data has 80 riders, 25 PNW race names, 6 categories, but no course data or cross-race rider history

## Relevant Codebase Areas

- `raceanalyzer/db/models.py` — Race (needs race_type field, course_lat/course_lon), Rider, Result (has place, race_time_seconds)
- `raceanalyzer/demo.py` — Must extend to generate course coordinates and rider win history
- `raceanalyzer/queries.py` — New queries: get_race_tiles(), get_scary_racers(), rider performance aggregation
- `raceanalyzer/ui/pages/calendar.py` — Replace table with tile grid
- `raceanalyzer/ui/pages/race_detail.py` — Add Scary Racers section
- `raceanalyzer/ui/components.py` — Race tile component, race type icon rendering
- `raceanalyzer/ui/charts.py` — Mini course map rendering (Plotly scattermapbox or SVG)
- `raceanalyzer/config.py` — Settings with pnw_regions already defined

## Constraints

- Python 3.9+, `from __future__ import annotations`
- Must use existing ORM models (schema additions OK, no breaking changes)
- No new external dependencies beyond what's already in pyproject.toml (streamlit, plotly, sqlalchemy, pandas) — unless strongly justified
- Demo data must still work after schema changes (migration or regeneration)
- Race type icons: can be inline SVG or emoji — Claude can generate simple SVGs. User offered to make them in "nano banana" if needed.
- Strava-style course maps: need lat/lon coordinates per race. For demo data, generate plausible PNW route polylines. Real data would come from GPX files or geocoding later.
- Streamlit's `st.columns()` for grid layout, `st.container()` for tiles — no custom React components
- All existing 119 tests must continue to pass

## Success Criteria

1. Main page shows a 3-wide grid of race tiles instead of a table
2. Each tile displays: race name, date, location, race type icon (crit/road/hill climb/stage race), and a mini course map
3. Clicking a tile navigates to race detail for that race
4. Race detail page includes a "Scary Racers" section per category showing top predicted performers
5. Scary Racers ranking uses historical results: win count, podium count, weighted by race type similarity
6. All 8 race types have distinct icons
7. Demo data generator produces course coordinates and rider cross-race history
8. Dashboard page still works (no regressions)
9. All existing tests pass + new tests for race type, tile queries, scary racers logic

## Verification Strategy

- Unit tests for rider strength/scary racer scoring algorithm
- Unit tests for race type classification (name-based heuristic)
- Unit tests for new queries (get_race_tiles, get_scary_racers)
- Visual verification: seed demo data, launch UI, confirm tiles render with icons and maps
- Confirm tile click navigates to correct race detail
- Confirm Scary Racers shows different riders per category with sensible rankings
- 119 existing tests still green

## Uncertainty Assessment

- Correctness: **Low** — rider scoring is a simple heuristic, not ML
- Scope: **Medium** — multiple layers (schema, demo data, queries, UI components, icons, maps) but each is bounded
- Architecture: **Medium** — course map rendering in Streamlit is the biggest unknown (Plotly scattermapbox vs static SVG vs folium). Race type icons are straightforward (inline SVG or emoji).

## Open Questions

1. What race types should exist? Proposed: criterium, road_race, hill_climb, stage_race, time_trial, gravel. Is that the right set for PNW?
2. Should course maps be interactive (zoom/pan) or static thumbnails? Static is simpler and faster.
3. How to generate plausible PNW course coordinates for demo data? Options: hardcode ~10 real route polylines, or generate random walks near known PNW cities.
4. Scary Racer scoring formula: simple (wins * 3 + podiums * 1 + race_type_bonus) or something fancier (Elo-style)?
5. Should race type be a new DB column on Race, or derived from the race name at query time?
6. Do we need a Mapbox token for Plotly scattermapbox, or can we use open-source tile layers?
7. Icon format: inline SVG (most flexible, works in st.markdown), emoji (simplest), or image files?
8. Should the tile grid be paginated or infinite-scroll for 50+ races?
