# Sprint 009 Merge Notes

## Draft Comparison

### Claude Draft Strengths (adopted)
- Tight scope control (data pipeline only, no UI changes)
- RefreshLog without FK on race_id (allows calendar-level sentinel entries)
- Sliding 24-hour window for refresh limiting (more robust than calendar-day boundary)
- JSON-first strategy for pre-reg data

### Claude Draft Rejected
- File rename deprecation (`*_bikereg.py`) — user chose `--source` flag instead
- Phase ordering (schema changes in Phase 3 but needed by Phase 2) — fixed in merge
- `race_id=0` sentinel for calendar refresh — replaced with nullable race_id

### Codex Draft Strengths (adopted)
- `--source` and `--dry-run` CLI flags — essential for safe rollout and rollback
- `road_results_racer_id` column on Startlist — preserves raw identifier
- `status` and `error_message` columns on RefreshLog — operational debugging
- Clear-and-reinsert strategy with transaction safety
- `StartlistParser` distinguishing pre-reg from results (Place/RaceTime check)

### Codex Draft Rejected
- Creating new parallel modules (`road_results_calendar.py`, `road_results_startlists.py`) — scope creep
- UniqueConstraint on RefreshLog (microsecond timestamps make it meaningless)
- Five phases (over-decomposed) — consolidated to four

### Gemini Draft Strengths (adopted)
- `--source` flag for soft deprecation (matches user choice)
- Checksum on RefreshLog for future optimization
- BikeReg code preserved intact (not renamed)

### Gemini Draft Rejected
- Prong 2 series-based forward lookup — speculative and expensive
- Phase 5 UI updates — out of scope per interview
- `UpcomingRaceParser` class — unnecessary given GraphQL discovery

## Valid Critiques Accepted

All three critiques identified:
- **NoResultsError gap**: `RaceResultParser.results()` raises on empty data — all new callers must catch this
- **carried_points = 0.0 vs None**: The `_rank_from_startlist` truthiness check treats 0.0 as falsy — must fix
- **Schema changes must come first**: Moved to Phase 1 (all drafts had them too late)
- **Transaction safety**: Clear-and-reinsert must be atomic
- **is_upcoming lifecycle**: Need to flip is_upcoming=False when race date passes

## Interview Refinements

1. **BikeReg**: `--source` flag, keep both paths (user chose this explicitly)
2. **Scope**: Data pipeline only, no UI changes
3. **Staleness**: Race date >= today only (strictest policy)

## Critical Finding: Live API Research

**All three drafts were wrong about the data pipeline.** Live research during interview revealed:

1. **Upcoming events**: NOT from road-results region listing. They come from a **GraphQL API** at `outsideapi.com/fed-gw/graphql` — the same backend BikeReg uses. Returns: eventId, name, startDate, city, state, lat/lon, bikereg URL.

2. **Registered riders + power rankings**: NOT from `downloadrace.php` JSON API. They come from **`road-results.com/predictor.aspx`** HTML endpoint:
   - Step 1: `predictor.aspx?url={eventId}` → category list with pre-reg counts
   - Step 2: `predictor.aspx?url={eventId}&cat={catId}&v=1` → HTML table of ranked riders with rID (RacerID), name, team, and power ranking points

3. **Region listing** doesn't have 2026 races at all — only historical results.

4. **The JSON endpoint** (`downloadrace.php`) returns results/rankings for past races, NOT pre-registration data for future races.

This means the final sprint needs:
- GraphQL client for event discovery (new, simple POST request)
- HTML parser for predictor.aspx response (new, straightforward table parsing)
- eventId-to-race-ID mapping (GraphQL returns BikeReg eventId, road-results uses its own race IDs)
