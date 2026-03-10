# Sprint 004: Race Tiles UI + Scary Racers

## Overview

Overhaul the main calendar page from a flat table into a visual 3-wide grid of race tiles. Each tile shows the race name, date, a race type icon (inline SVG), and a Strava-style mini course map (route outline on white background). Clicking a tile navigates to race detail. The detail page adds a "Scary Racers" section — top predicted performers per category, ranked by road-results' existing Elo-like points system (`carried_points`). Fun personality throughout.

This sprint touches every layer: schema (new `race_type`, `course_lat`, `course_lon` columns on Race), demo data (course polylines, race type assignment), query layer (tile queries, scary racer lookup), and UI (tile grid, icons, mini maps, scary racer cards).

**Duration**: ~3-4 days
**Prerequisite**: Sprint 003 complete (demo data with 50 races, 80 riders).
**Merged from**: Claude draft (primary), Gemini draft (UNKNOWN type, index), interview feedback (road-results points, route outlines, Claude SVGs).

---

## Use Cases

1. **As a racer**, I open the calendar and see a visual grid of race tiles — each with an icon telling me if it's a crit, road race, hill climb, etc.
2. **As a racer**, I see a mini course map on each tile that shows the route shape (loop, out-and-back, point-to-point).
3. **As a racer**, I click a tile and go straight to that race's detail page.
4. **As a racer**, I see "Scary Racers" for my category — the riders with the highest road-results ranking points who are racing.
5. **As a developer**, I can seed demo data and see tiles with course maps and scary racers populated.
6. **As a tester**, I verify all 6 race types have distinct icons, tiles render correctly, and scary racers are ranked by points.

---

## Architecture

```
raceanalyzer/
├── db/
│   └── models.py           # MODIFY: Add RaceType enum, race_type + course columns on Race
├── demo.py                 # MODIFY: Generate course polylines, assign race_type
├── queries.py              # MODIFY: Add infer_race_type(), get_race_tiles(), get_scary_racers()
├── ui/
│   ├── pages/
│   │   ├── calendar.py     # REWRITE: Replace table with 3-wide tile grid
│   │   └── race_detail.py  # MODIFY: Add Scary Racers section
│   ├── components.py       # MODIFY: Add render_race_tile(), render_race_type_icon(), render_scary_racer_card()
│   └── charts.py           # MODIFY: Add _build_mini_course_map()

tests/
├── test_queries.py         # MODIFY: Tests for get_race_tiles, get_scary_racers
├── test_demo.py            # MODIFY: Tests for course coords, race_type assignment
└── test_race_type.py       # CREATE: Tests for infer_race_type()
```

### Key Design Decisions

1. **`race_type` as a nullable column on Race** — Derived from race name via `infer_race_type()` at demo generation time. Nullable to avoid breaking existing fixtures. `RaceType` enum includes `UNKNOWN` as safety valve.

2. **Course coordinates as comma-separated Text** — `course_lat` and `course_lon` columns store comma-separated float strings. Simple, debuggable, adequate for 10-20 points per route. No encoding/decoding overhead.

3. **6 race types + UNKNOWN** — `criterium`, `road_race`, `hill_climb`, `stage_race`, `time_trial`, `gravel`, `unknown`. Inferred from race name keywords.

4. **Static route outlines (no map tiles)** — Plotly `go.Scatter` on white background showing just the route shape. No Mapbox token, no external tile loading. Fast to render 50+ tiles. Strava-style thumbnail aesthetic.

5. **Scary Racers = road-results points** — Rank riders by their `carried_points` field (road-results' existing Elo-like system). No custom scoring formula. Simple, authoritative, already in the data. Course-type adjustments deferred to future sprint.

6. **Tile grid with pagination** — 12 tiles per page (4 rows of 3) with "Show More" button. Avoids rendering 50+ charts at once.

7. **Inline SVG icons** — 24x24 colored SVGs rendered via `st.markdown(unsafe_allow_html=True)`. Each race type has a distinct icon and color.

---

## Implementation

### Schema: `raceanalyzer/db/models.py`

Add `RaceType` enum and three new nullable columns to Race:

```python
class RaceType(enum.Enum):
    CRITERIUM = "criterium"
    ROAD_RACE = "road_race"
    HILL_CLIMB = "hill_climb"
    STAGE_RACE = "stage_race"
    TIME_TRIAL = "time_trial"
    GRAVEL = "gravel"
    UNKNOWN = "unknown"

# On Race:
    race_type = Column(SAEnum(RaceType), nullable=True)
    course_lat = Column(Text, nullable=True)   # Comma-separated latitudes
    course_lon = Column(Text, nullable=True)   # Comma-separated longitudes
```

All nullable — existing test fixtures and real data unaffected.

### Queries: `raceanalyzer/queries.py`

**Race type inference:**
```python
_RACE_TYPE_PATTERNS = [
    (["criterium", "crit ", "grand prix", "short track"], RaceType.CRITERIUM),
    (["stage race", "tour de"], RaceType.STAGE_RACE),
    (["hill climb", "mount ", "mt ", "hillclimb"], RaceType.HILL_CLIMB),
    (["time trial", "tt ", "chrono"], RaceType.TIME_TRIAL),
    (["roubaix", "gravel", "unpaved"], RaceType.GRAVEL),
]

def infer_race_type(race_name: str) -> RaceType:
    name_lower = race_name.lower()
    for patterns, race_type in _RACE_TYPE_PATTERNS:
        for pattern in patterns:
            if pattern in name_lower:
                return race_type
    return RaceType.ROAD_RACE
```

**Tile query** — `get_race_tiles(session, year, states, limit)` returns DataFrame with id, name, date, location, state_province, race_type, course_lat, course_lon, num_categories. Uses `func.strftime("%Y", Race.date)` for year filtering (not `extract`).

**Scary racers** — `get_scary_racers(session, race_id, category, top_n=5)` returns top riders by `carried_points` for riders in this race's category. Columns: name, team, carried_points, wins (count of place==1 results).

### Demo Data: `raceanalyzer/demo.py`

**Course coordinate generation** — `_generate_course_coords(location, race_type)` returns (lats, lons) based on PNW city centers with race-type-specific shapes:
- Criterium: small rectangular loop (~0.01°)
- Road race: elongated loop (~0.04°)
- Hill climb: upward winding line
- Stage race: larger irregular loop
- Time trial: straight-ish out-and-back
- Gravel: irregular loop with more variation

**Race type assignment** — Call `infer_race_type(race_name)` for each race at creation time.

**Rider points** — Assign `carried_points` based on result history. Top finishers accumulate more points across races.

### UI Components: `raceanalyzer/ui/components.py`

**Race type icons** — `RACE_TYPE_ICONS` dict mapping race type values to inline SVG strings:
- Criterium (red): rectangular loop with center dot
- Road race (blue): winding S-curve road
- Hill climb (green): ascending mountain line with arrow
- Stage race (orange): connected circles (multi-day)
- Time trial (purple): clock face
- Gravel (brown): bumpy path with scatter dots

**Tile renderer** — `render_race_tile(tile_data)`: container with border, icon + name header, mini course map, date/location footer, race type color badge, "View Details" button.

**Mini course map** — `_build_mini_course_map(course_lat, course_lon, color)`: Plotly scatter figure, 120px height, white background, route as colored line, start/finish marker.

**Scary racer card** — `render_scary_racer_card(racer)`: name, team, points, threat level badge (Apex Predator / Very Dangerous / Dangerous / One to Watch based on point thresholds).

### Calendar Page: `raceanalyzer/ui/pages/calendar.py`

Rewrite to use tile grid:
- Sidebar filters (year, state) — unchanged
- Metrics row (total races, states, date range) — unchanged
- 3-wide tile grid with pagination (12 per page, "Show More" button)
- Each tile renders via `render_race_tile()`

### Race Detail Page: `raceanalyzer/ui/pages/race_detail.py`

Add after classifications section:
- "Scary Racers" header with skull emoji and explanation
- Per-category tabs showing top 5 riders by carried_points
- Threat level badges for visual fun

---

## Files Summary

| File | Action | Description |
|------|--------|-------------|
| `raceanalyzer/db/models.py` | **Modify** | Add `RaceType` enum, `race_type`, `course_lat`, `course_lon` columns |
| `raceanalyzer/queries.py` | **Modify** | Add `infer_race_type()`, `get_race_tiles()`, `get_scary_racers()`, `race_type_display_name()` |
| `raceanalyzer/demo.py` | **Modify** | Course coord generation, race type assignment, rider points |
| `raceanalyzer/ui/pages/calendar.py` | **Rewrite** | Table → 3-wide tile grid with pagination |
| `raceanalyzer/ui/pages/race_detail.py` | **Modify** | Add Scary Racers section |
| `raceanalyzer/ui/components.py` | **Modify** | Add tile renderer, SVG icons, scary racer cards, mini map builder |
| `tests/test_race_type.py` | **Create** | Tests for `infer_race_type()` |
| `tests/test_queries.py` | **Modify** | Tests for `get_race_tiles()`, `get_scary_racers()` |
| `tests/test_demo.py` | **Modify** | Tests for course coords, race type, rider points |

**Total new files**: 1
**Total modified files**: 8
**Estimated new tests**: ~15

---

## Definition of Done

1. Main page shows a 3-wide grid of race tiles (not a table)
2. Each tile displays: race name, date, location, race type SVG icon, mini course map
3. 6 distinct race type icons render correctly (criterium, road race, hill climb, stage race, time trial, gravel)
4. Mini course maps show route outlines on white background, colored by race type
5. Clicking a tile navigates to that race's detail page
6. Race detail page includes "Scary Racers" section per category
7. Scary Racers ranks riders by `carried_points` (road-results Elo-like points)
8. Scary Racer cards show threat level badges (Apex Predator / Very Dangerous / Dangerous / One to Watch)
9. Tile grid is paginated (12 per page with "Show More")
10. Demo data generator produces course coordinates and race types for all races
11. Demo data assigns `carried_points` to riders based on result history
12. All existing 119 tests pass (zero regressions)
13. New tests pass: race type inference, tile queries, scary racer queries, course coord generation
14. Python 3.9 compatible: `from __future__ import annotations` in all new/modified files
15. No new external dependencies

---

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 50+ Plotly charts slow on calendar page | Poor UX | Medium | Pagination (12/page), static plots, no map tiles |
| Race type inference misclassifies edge cases | Wrong icon on tile | Low | Fallback to ROAD_RACE; `infer_race_type()` is deterministic and testable |
| `carried_points` is null/zero for demo riders | Empty Scary Racers | Medium | Demo generator must assign realistic points; test for non-empty results |
| `st.markdown(unsafe_allow_html=True)` for SVGs | XSS if user data in SVGs | Very Low | Icons are hardcoded constants, no user input flows into SVG strings |
| Course coordinate generation looks unrealistic | Ugly thumbnails | Low | Race-type-specific shapes (loops for crits, lines for climbs); visual QA during demo |
| SQLite `extract` bug resurfaces | Query crash | Low | Known fix: use `func.strftime` — already documented from Sprint 002 |

---

## Open Questions — Resolved

1. **Race types**: criterium, road_race, hill_climb, stage_race, time_trial, gravel, unknown (7 values)
2. **Course maps**: Static route outlines on white, no map tiles
3. **Demo coordinates**: Race-type-specific shapes near PNW city centers
4. **Scoring**: Road-results `carried_points` — no custom formula
5. **Race type storage**: Nullable DB column, inferred from name at generation time
6. **Mapbox token**: Not needed — no map tiles
7. **Icons**: Inline SVG generated by Claude
8. **Pagination**: 12 tiles per page with "Show More"
