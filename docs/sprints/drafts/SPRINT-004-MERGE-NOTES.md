# Sprint 004 Merge Notes

## Draft Summary
- **Claude draft** (1155 lines): Full implementation code, SVG icons, course coord generation, tile grid with pagination, custom scary racer scoring
- **Gemini draft** (313 lines): High-level architecture, encoded polyline approach, scatter_mapbox, UNKNOWN race type default
- **Codex draft**: Did not produce output file (sandbox issues)

## Critique Summary
- **Gemini critique**: Recommends Claude draft as primary. Flags coordinate storage (2 columns vs polyline), in-memory aggregation, race type inference brittleness
- **Claude self-critique**: Identifies SQLite `extract` bug in tile query, validates route outline approach over map tiles

## Interview Decisions
1. **Maps**: Route outlines on white background (no map tiles, no Mapbox) — confirmed
2. **Scoring**: Use road-results' existing Elo-like points (`carried_points` on Result model) instead of custom formula — major simplification
3. **Icons**: Claude generates inline SVGs for all 6 race types

## Merge Decisions

### Primary base: Claude draft
Most complete, all code provided, strongest DoD.

### Accepted from Gemini:
- Add `UNKNOWN` to RaceType enum as safety valve
- Index on `race_type` column

### Rejected from Gemini:
- `scatter_mapbox` with OSM tiles — too slow for 50+ tiles, external dependency
- Encoded polyline — adds decode complexity for no real benefit at demo scale
- `course_centroid_lat/lon` columns — unnecessary when we just render the route shape
- No pagination — unacceptable for 50+ chart renders

### Interview overrides:
- **Scary Racers scoring completely simplified**: Drop custom `wins*3 + podiums*1 + type_wins*2` formula. Instead, rank by `carried_points` from road-results (already on Result model). This is the existing Elo-like system from road-results.com. Course-type adjustments deferred to future sprint.
- This eliminates: `get_scary_racers()` complex aggregation, scoring tests, threat level thresholds
- Keeps: display of top riders by points, fun "Scary Racers" branding, threat badges based on point thresholds

### Bug fixes incorporated:
- Use `func.strftime("%Y", Race.date)` not `extract("year")` in tile query (known SQLite bug from Sprint 002)

### Architecture:
- `race_type` as nullable column on Race (not `nullable=False` — avoids breaking test fixtures)
- `course_lat` and `course_lon` as comma-separated Text columns (simple, debuggable)
- `infer_race_type()` in queries.py, called at demo generation time
- Static Plotly scatter for mini maps (no tiles)
- Tile grid with 12-per-page pagination
- Inline SVG icons for 6 race types + fallback
