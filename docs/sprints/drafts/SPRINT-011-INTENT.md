# Sprint 011 Intent: Feed First Glance, Detail Dive, Personalization & Performance

## Seed

Implement ALL use cases from `docs/USE_CASES_FEED_FIRST_GLANCE.md` — a comprehensive overhaul of the feed experience across six areas:

1. **First Glance (FG-01 → FG-08)**: Card layout reorder to match racer decision priority. Add location + countdown to header, teammates badge, course character one-liner (terrain + distance + gain), field size, drop rate label emphasis, race type label. Reorder card content to match priority.

2. **Detail Dive (DD-01 → DD-07)**: Interactive course profile as hero visualization, climb-by-climb breakdown with race context, startlist with team groupings, expanded racer type description, historical finish type pattern visualization, similar races cross-reference, course map with race features.

3. **My Team (MT-01, MT-02)**: Set team name once (sidebar), surface teammate names on feed cards where teammates are registered.

4. **Feed Organization (FO-01 → FO-08)**: Discipline filter (road/gravel/CX/MTB/track), race type filter within discipline, geographic filter by state/region, persistent filter preferences, days-until countdown labels replacing "SOON"/"UPCOMING", month-based section headers (agenda view), remove auto-expanded "Racing Soon" hero, scannable card density.

5. **Performance (PF-01 → PF-06)**: Eliminate N+1 queries in get_feed_items, cache feed results at query layer, lazy-load expanded card content, pre-compute predictions at scrape time, paginate at query layer, profile and set performance budget.

## Context

- **Project state**: RaceAnalyzer is a PNW cycling race analysis tool at Sprint 010. Feed page is the primary landing point with rich cards (predicted finish type, terrain badge, narrative, sparkline, duration, climb highlights, racer type descriptions).
- **Recent direction**: Sprint 010 built the feed foundation with inline expansion, global category filter, URL state persistence, and rich card content. Sprint 009 integrated road-results.com for startlists. Sprint 008 built course intelligence (elevation profiles, climb detection, maps).
- **Key data available but not surfaced**: `distance_m`, `total_gain_m` in courses table; `state_province` in races; `team` in startlists; `race_type` enum on races; `field_size` in results.
- **Architecture is stable**: Separated query/prediction/UI layers, SQLAlchemy ORM, Streamlit with session state + query params, caching via `@st.cache_data`.
- **Testing is mature**: pytest with in-memory SQLite fixtures, ~15 test files, good edge case coverage.

## Recent Sprint Context

- **Sprint 010**: Feed page as primary landing point. Expander-based cards with rich content. Global category filter. URL-based deep linking. "Racing Soon" section for next 7 days.
- **Sprint 009**: Road-results.com GraphQL API for event discovery. Startlists with carried_points. 24-hour refresh limiting.
- **Sprint 008**: Elevation profiles from RWGPS. Climb detection. Course type classification. Interactive maps (Folium). Narrative generation. Glicko-2 ratings.

## Relevant Codebase Areas

| Module | Role | Sprint 011 Impact |
|--------|------|-------------------|
| `raceanalyzer/ui/pages/feed.py` | Feed page rendering | Major — card layout reorder, countdown labels, month headers, density |
| `raceanalyzer/ui/components.py` | Card rendering, badges, sparklines | Major — new badges, layout restructure, teammate display |
| `raceanalyzer/queries.py` | Feed query, search, enrichment | Major — batch queries, new fields, pagination, caching |
| `raceanalyzer/predictions.py` | Finish type, contenders, drop rate, duration, narrative | Moderate — pre-computation, expanded descriptions, similarity |
| `raceanalyzer/models.py` | SQLAlchemy schema | Moderate — possible new fields (discipline), series_predictions table |
| `raceanalyzer/series.py` | Series grouping logic | Minor — may need discipline derivation |
| `raceanalyzer/ui/pages/preview.py` | Race preview page | Moderate — hero course profile, climb breakdown, startlist grouping |
| `raceanalyzer/elevation.py` | Climb detection, course data | Minor — data already extracted |
| `tests/` | Test suite | Major — new tests for all features |

## Constraints

- Must follow existing project conventions (see `CLAUDE.md`)
- Must integrate with existing Streamlit + SQLAlchemy architecture
- Must maintain graceful degradation (missing data → card renders without that element)
- URL-based state persistence pattern must extend to new filters
- No new Python dependencies unless absolutely necessary
- Existing tests must not break
- SQLite database — no Postgres-specific features
- Feed must remain performant with 50+ series

## Success Criteria

1. Feed cards show information in racer decision-priority order (date/location → social → course → finish type → field → drop rate)
2. Days-until countdown replaces "SOON"/"UPCOMING" labels
3. Month-grouped agenda view is the default for upcoming races
4. Discipline, race type, and state filters are functional and URL-persistent
5. Team name setting persists; teammate badges appear on relevant cards
6. Detail dive (preview page) has hero course profile, climb breakdown with race context, team-grouped startlist, and similar races
7. Feed loads in <1 second cold cache, <200ms warm cache for full dataset
8. N+1 queries eliminated; batch loading in place
9. All new features have test coverage
10. No regressions in existing functionality

## Verification Strategy

- **Unit tests**: New tests for batch queries, countdown logic, discipline derivation, teammate matching, similarity scoring, month grouping
- **Integration tests**: Feed rendering with seeded data covering all card states (upcoming with teammates, dormant, missing course data, etc.)
- **Performance testing**: Timing instrumentation on feed load; assert <1s cold / <200ms warm
- **Visual verification**: Manual Streamlit review of card layout, filter interactions, deep linking
- **Edge cases**: Empty feed, no upcoming races, all races in one month, team with no matches, series with no course data, single-edition series

## Uncertainty Assessment

- **Correctness uncertainty**: Low — Use cases are well-specified with clear data sources and rendering targets
- **Scope uncertainty**: High — 31 use cases across 6 areas is very large; will likely need multiple sprints or aggressive phasing
- **Architecture uncertainty**: Medium — Performance overhaul (batch queries, pre-computation, lazy loading) requires restructuring the query layer; discipline modeling is new

## Open Questions

1. **Should this be one mega-sprint or split into 2-3 focused sprints?** The 31 use cases span UI, data modeling, query optimization, and personalization. Natural split points: (a) Card layout + feed organization, (b) Personalization + detail dive, (c) Performance.

2. **Discipline modeling**: Should `discipline` be a new column on `race_series` or derived from `race_type`? The use case doc suggests a mapping (Road = {criterium, road_race, hill_climb, stage_race, time_trial}). Is a derivation function sufficient or do we need schema changes?

3. **Pre-computed predictions table**: Is a new `series_predictions` table the right approach, or should predictions be cached in the existing `race_classifications` or as JSON on `race_series`?

4. **Team name persistence**: Session state + cookie? URL param? Sidebar text input saved to a local config file? What's the simplest approach that survives page reloads?

5. **Similar races algorithm**: Simple heuristic (same course_type + similar distance + same predicted finish type) or something more sophisticated?

6. **Month-grouped agenda view**: Replace the current flat list entirely, or offer both views with a toggle?

7. **Priority ordering within the sprint**: If we can't do everything, which use cases are cut-last? The use case doc marks priorities (P0/P1/P2) — should we follow those strictly?
