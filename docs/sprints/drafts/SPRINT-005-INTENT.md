# Sprint 005 Intent: UI Overhaul — Classification-Centric Tiles, Navigation, Maps

## Seed Prompt

Big UI sprint with 8 requirements:
1. New "Individual TT" finish type for time trials/hill climbs — detected when riders are evenly spaced or based on race names containing "Hill Climb" or "Time Trial"
2. Tile icons should represent finish type classification (bunch sprint, breakaway, etc.), NOT event type (criterium, road race, etc.)
3. Hide races without time data (classified as UNKNOWN) by default, with a UI toggle to show them
4. Entire tile should be clickable (not just the View Details button), with hover effects
5. Show the overall race classification on each tile
6. Tooltips explaining each classification in casual, plain language
7. Get real race maps from bikereg.com (look for RideWithGPS/Strava links) or fallback to area map of the race location
8. Back navigation from race detail page to the tile grid

## Orientation Summary

- **Current state**: 20 real PNW races, 190 classifications (101 UNKNOWN due to no time data). Tile grid with race-type icons (criterium/road/hill climb/etc.), mini course maps from demo data coords, scary racers section on detail page.
- **Recent direction**: Moved from synthetic to real scraped data. Classifier works but many races lack finish times. UI is functional but tiles show event type rather than the more interesting finish type classification.
- **Key modules to modify**:
  - `raceanalyzer/db/models.py` — Add `INDIVIDUAL_TT` to `FinishType` enum
  - `raceanalyzer/classification/finish_type.py` — Add Individual TT detection logic
  - `raceanalyzer/ui/components.py` — Replace race-type icons with finish-type icons, add tooltips, make tiles clickable with hover CSS, add back button
  - `raceanalyzer/ui/pages/calendar.py` — Add "show hidden races" toggle, pass finish type data to tiles
  - `raceanalyzer/ui/pages/race_detail.py` — Add back navigation button
  - `raceanalyzer/queries.py` — Modify tile query to include classification/finish type data, add INDIVIDUAL_TT display name
  - `raceanalyzer/scraper/client.py` — Potentially add bikereg course map fetching
- **Constraints**: Python 3.9+, SQLite, Streamlit, Plotly, no heavy new deps. `from __future__ import annotations` everywhere. Real PNW data with many UNKNOWN classifications.

## Relevant Codebase Areas

### Classification
- `raceanalyzer/classification/finish_type.py` — Rule-based classifier. Current types: BUNCH_SPRINT, SMALL_GROUP_SPRINT, BREAKAWAY, BREAKAWAY_SELECTIVE, REDUCED_SPRINT, GC_SELECTIVE, MIXED, UNKNOWN.
- `raceanalyzer/classification/grouping.py` — UCI chain rule gap grouping (3-second threshold).
- `raceanalyzer/db/models.py:39-47` — `FinishType` enum.

### UI
- `raceanalyzer/ui/components.py` — Current RACE_TYPE_ICONS (SVGs for event types), render_race_tile(), render_race_type_icon(), RACE_TYPE_COLORS.
- `raceanalyzer/ui/pages/calendar.py` — Tile grid (3-wide, 12/page pagination). Calls get_race_tiles() which returns race_type (event type), NOT finish type.
- `raceanalyzer/ui/pages/race_detail.py` — Detail page with classifications, results, scary racers. No back button currently.

### Queries
- `raceanalyzer/queries.py` — get_race_tiles() returns race_type, course coords. FINISH_TYPE_DISPLAY_NAMES dict. get_race_detail() returns classifications per category.

### Data Reality
- 20 PNW races, ~12 have no finish times (UNKNOWN classification)
- Real races have no course_lat/course_lon (those came from demo data generator)
- Need to either get real maps from bikereg/RideWithGPS/Strava or use location-based area maps

## Constraints

1. Must handle the "101 UNKNOWN classifications" reality gracefully — hiding them by default is correct
2. Each race may have multiple categories with different finish types — tile needs an "overall" classification (most common or most interesting)
3. Real course map fetching from bikereg is speculative — need a fallback strategy
4. Streamlit has limited CSS customization — clickable tiles may require creative HTML/CSS injection
5. No breaking changes to existing classification pipeline or DB schema migrations beyond adding enum value

## Success Criteria

1. Individual TT finish type is detected and classified correctly for time trials and hill climbs
2. Tiles display finish-type icons instead of event-type icons
3. UNKNOWN-classified races are hidden by default with a toggle to show them
4. Clicking anywhere on a tile navigates to the race detail page
5. Each tile shows an overall finish type classification
6. Hovering over a classification name shows a tooltip explaining it in casual language
7. Race detail page has a "Back to Calendar" button/link
8. Course maps come from real data when available, with a sensible fallback
9. All existing tests pass, new tests for Individual TT classification

## Verification Strategy

- Unit tests for Individual TT detection in classifier
- Visual QA of tile icons, tooltips, hover effects, click navigation
- Verify UNKNOWN races are hidden/shown correctly via toggle
- Test back navigation from detail page
- Check that bikereg map fetching works or falls back gracefully

## Uncertainty Assessment

| Factor | Level | Reasoning |
|--------|-------|-----------|
| **Correctness** | Medium | Individual TT detection rules are novel — need to define "evenly spaced" precisely |
| **Scope** | Medium | 8 requirements is substantial but most are UI changes. Bikereg map scraping is the wildcard. |
| **Architecture** | Low | Extends existing patterns (new enum value, new icon set, modified tile component) |

## Open Questions

1. How to determine the "overall" race classification for a tile when categories differ? Most common? Highest-confidence? Most interesting?
2. What defines "evenly spaced" for Individual TT detection? Low CV with many groups? Linear spacing?
3. Is bikereg.com scrapable for course map links? Does it have Cloudflare protection too?
4. Should the area map fallback use a static map image API (e.g. OpenStreetMap) or just show the location text?
5. What icons best represent each finish type? (Bunch sprint = packed group, breakaway = solo rider ahead, etc.)
