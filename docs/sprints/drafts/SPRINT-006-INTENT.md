# Sprint 006 Intent: Course Maps & Race Deduplication

## Problem Statement

Two major gaps remain in RaceAnalyzer's value proposition:

1. **No course maps.** Users can't see the race route. The Strava-style map overlay (polyline on a map) is the gold standard for cycling route visualization. Currently we only show a geocoded area map (pin on a map) on the race detail page.

2. **No race deduplication.** The same race occurs every year (e.g., "Banana Belt RR" has editions in 2022, 2023, 2024). Some races have multiple editions per year (Mason Lake has 2, Pacific Raceways has many). Currently each edition is a separate tile. Users want to see "Banana Belt" as one entity with aggregated classification history across all editions.

## User Stories

1. **As a racer**, I see a course map on the race detail page showing the route polyline overlaid on a real map (Strava-style), so I can understand the terrain and plan my race strategy.
2. **As a racer**, I see races grouped by name in the calendar view — "Banana Belt" is one tile, not four separate tiles for each year.
3. **As a racer**, I see aggregated classification history for a race series — a chart showing how the race has finished across all editions and categories.
4. **As a racer**, the default classification badge on a race tile reflects the most common finish type across ALL editions, giving me the best prediction of what the next edition will be like.
5. **As a developer**, course route data is fetched from RideWithGPS and cached in the database so maps render instantly after first load.

## Research Findings

### Course Maps — Data Sources

**RideWithGPS undocumented search API** (`/find/search.json`):
- No auth required
- Supports `search[keywords]` + `search[lat]` + `search[lng]` for geographic+text search
- Returns route metadata including bounding box, distance, elevation
- Route embed: `ridewithgps.com/embeds?type=route&id=ROUTE_ID` (iframe, no auth)
- Route details: `ridewithgps.com/routes/ROUTE_ID.json` may provide track points

**Road-results.com coordinates**: Race pages contain `GetMap("lat:lon",0)` — extractable for venue location but NOT course routes. Behind Cloudflare (needs headless browser). We already have Nominatim geocoding as fallback.

**MapMyFitness API**: Has `text_search` + `close_to_location` for global public route search. Requires OAuth but client credentials work. 25 req/s rate limit. Less cycling community adoption than RWGPS.

**Recommended approach**: Use RWGPS `/find/search.json` with race name + geocoded coordinates. Match by proximity and name similarity. Cache RWGPS route ID in the database. Embed via iframe or fetch polyline for custom rendering.

### Race Deduplication

**Current DB state** (269 races, scraping ongoing toward 1,385):
- Many races repeat: "Twilight TT" (4 editions), "Red R Criterium" (4), "Pacific Raceways Circuit Race" (4+)
- Race names are usually consistent but sometimes vary slightly (e.g., "Banana Belt RR" vs "Banana Belt Road Race")
- Some races have multiple editions per year (Mason Lake, Pacific Raceways)

**Dedup strategy**: Normalize race names, group by normalized name. Create a `race_series` concept — a virtual entity that groups all editions. The calendar shows series tiles, not individual race tiles. Detail page shows all editions with aggregated statistics.

## Existing Architecture

- `Race` model has: id, name, date, location, state_province, course_lat, course_lon, race_type
- `RaceClassification` has: race_id, category, finish_type, metrics
- `queries.py` has: `_compute_overall_finish_type()`, `get_race_tiles()`, `get_race_detail()`
- `components.py` has: `render_tile_grid()`, `_render_single_tile()`
- `maps.py` has: `geocode_location()`, `render_location_map()`
- Calendar page shows tiles via `render_tile_grid(get_race_tiles(...))`
- Race detail page shows per-category classifications, results, scary racers, area map

## Scope

**In scope:**
- RWGPS route discovery and caching
- Course map rendering (embed or polyline overlay)
- Race series grouping (name normalization + DB model)
- Aggregated classification view (chart + badge)
- Calendar dedup (one tile per series)
- Series detail page (all editions, aggregated stats)

**Out of scope (for this sprint):**
- MapMyFitness API integration (RWGPS is sufficient)
- Manual course route curation UI
- Road-results.com coordinate scraping (Cloudflare issues)
- Full fuzzy matching (start with exact normalized name matching)

## Key Design Questions for Drafts

1. **DB schema**: New `RaceSeries` table? Or just a `series_key` column on Race? Or purely computed at query time?
2. **Name normalization**: How to handle "Banana Belt RR" vs "Banana Belt Road Race"? Strip year, normalize suffixes, or fuzzy match?
3. **RWGPS route caching**: Store route_id on Race? New table? Cache polyline data or just use embed?
4. **Calendar UX**: One tile per series (expandable to see editions?) or a new "series view" page?
5. **Aggregation**: How to combine classifications across years AND categories into meaningful summary stats?
6. **Course map rendering**: RWGPS iframe embed vs custom Leaflet/Folium map with polyline overlay?
