# Sprint 010 Intent: Unified Race Feed & Forward-Looking UX

## Seed

Plan a UX sprint for the RaceAnalyzer project based on the use cases in `docs/USE_CASES_UX_IMPROVEMENT.md`. Prioritize the use cases rated "good" by the user. The core UX thesis is collapsing upcoming/historical race data into a single forward-looking feed. The target persona is a newer PNW road racer deciding which races to do.

## Context

- **Project state**: Python CLI + Streamlit UI for analyzing PNW road race results. 9 sprints completed covering: data pipeline (scraping, classification), predictions, course intelligence (interactive maps, elevation profiles, climb detection), historical stats (drop rate, speeds), narrative generator, and road-results/BikeReg integration for upcoming race discovery and startlists.
- **Current UI architecture**: 5 separate Streamlit pages — Calendar (tile grid + upcoming races section), Series Detail, Race Detail, Race Preview, Finish Type Dashboard. The user must navigate between pages to go from "what races exist?" to "what should I expect?" Navigation is page-based with `st.switch_page()` and query params.
- **Recent work**: Sprint 008 built interactive course maps, climb detection, drop rate/speed stats, and the "What to Expect" narrative. Sprint 009 replaced BikeReg with road-results GraphQL for calendar discovery and predictor.aspx for ranked startlists. Both shipped successfully.
- **Sprint 008's original plan** had Sprint 010 as "Key moments on map, animated race replay" — but the user's use cases document redirects Sprint 010 toward a UX overhaul instead.
- **Key constraint**: The app is Streamlit-based. Streamlit's page model, session state, and component system shape what's feasible in a single sprint. Deep custom JS components are possible (Sprint 008 proved this) but expensive.

## Recent Sprint Context

- **Sprint 009** (just completed): Road-results integration. GraphQL calendar discovery, predictor.aspx startlists, refresh limiting, `--source` flag. The calendar now has real upcoming race data with power rankings.
- **Sprint 008**: Interactive course map (Leaflet+Plotly in iframe), climb detection, drop rate, typical speeds, narrative generator, race preview page layout.
- **Sprint 007**: Schema foundation, baseline predictions, Race Preview page created.
- **Sprint 006**: BikeReg integration (now deprecated in favor of road-results).

## Relevant Codebase Areas

| Area | Key Files | Notes |
|------|-----------|-------|
| **UI pages** | `ui/pages/calendar.py`, `ui/pages/race_preview.py`, `ui/pages/series_detail.py`, `ui/pages/race_detail.py`, `ui/pages/dashboard.py` | Calendar is landing page; Race Preview is the forward-looking view |
| **UI components** | `ui/components.py` | Tile grids, badges, filters, empty states |
| **UI routing** | `ui/app.py` | Streamlit `st.navigation()` with 5 pages |
| **Data queries** | `queries.py` | `get_race_preview()`, `get_series_tiles()`, `get_race_tiles()` |
| **Predictions** | `predictions.py` | `predict_series_finish_type()`, `calculate_drop_rate()`, `calculate_typical_speeds()`, `generate_narrative()` |
| **Models** | `db/models.py` | Race, RaceSeries, Course, Startlist, Result, etc. |
| **Maps** | `ui/maps.py` | `render_interactive_course_profile()`, `render_course_map()` |
| **Config** | `config.py` | Settings dataclass |

## Constraints

- Must remain a Streamlit application (no framework migration)
- Must preserve all existing data pipeline functionality (scraping, classification, predictions)
- Must work with existing SQLite database schema (new columns OK, but no destructive migrations)
- Python test suite must continue passing (`pytest tests/ -v`, `ruff check .`)
- No new external API dependencies (all data already in DB or fetched by existing CLI commands)
- The Race Preview page already has the "What to Expect" narrative, course profile, predictions, stats, and contenders — this sprint reorganizes and surfaces that data, not recreates it
- Sprint 008's interactive map component pattern (custom HTML in iframe) is proven and reusable

## Success Criteria

1. A racer opens the app and sees a single unified feed with upcoming races prominently featured at top, sorted by date
2. Each race card in the feed shows inline: predicted finish type, terrain badge, drop rate, and a 1-2 sentence preview — no clicking required to get the gist
3. Tapping a race card expands it inline (or navigates to a forward-looking preview) showing full course profile, narrative, contenders, and registration link
4. Category filter is set once and persists across all views
5. Historical editions of a series are accessible but secondary to the upcoming edition
6. Race search by name works
7. "This Weekend" quick filter highlights imminent races
8. Finish type labels use plain English by default

## Verification Strategy

- **Existing tests**: All `pytest` tests must pass unchanged (data layer is not modified)
- **New tests**: Query functions for the unified feed, search, and any new data aggregation
- **Manual UI testing**: Checklist covering each "good" use case from the doc
- **Regression**: Calendar, Race Preview, and Dashboard pages still function
- **Edge cases**: Series with no upcoming edition, races with no historical data, races with no course data, empty search results

## Uncertainty Assessment

- Correctness uncertainty: **Low** — We're reorganizing existing data and UI, not building new algorithms. All the underlying data (predictions, stats, narratives, courses) already exists and is tested.
- Scope uncertainty: **Medium** — 28 "good" use cases is a lot. Need to prioritize ruthlessly — some use cases (UC-37 side-by-side comparison, UC-33 course comparison) may be too ambitious for one sprint. The drafts should propose a realistic subset.
- Architecture uncertainty: **Medium** — Streamlit's page model makes "expand card inline" (UC-46) and "persistent category filter" (UC-45) non-trivial. Streamlit reruns the entire script on interaction, which constrains inline expansion patterns. The drafts should propose concrete Streamlit-compatible implementations.

## Open Questions

1. **How to implement inline card expansion in Streamlit?** Options: (a) use `st.expander` for a lightweight expand/collapse, (b) use session state to track which card is "open" and conditionally render detail content, (c) keep page navigation but make it feel seamless. Which approach best serves the "single feed" thesis?

2. **Should we merge all 5 pages into 1, or keep Race Preview as a separate page that the feed links to?** The use cases want "one entry point" (UC-44) but Streamlit's multi-page architecture may make a single-page app harder to maintain.

3. **Which "good" use cases should be cut if scope is too large?** Candidates for deferral: UC-37 (side-by-side comparison), UC-33 (course comparison to known race), UC-38 (season calendar view), UC-26 (contender rider types), UC-28 (team representation). These require new data or significant UI work.

4. **How should "This Weekend" (UC-48) work?** A filter toggle at the top of the feed? A separate section? A date range picker?

5. **Plain-English finish types (UC-09) — how verbose?** "The group usually stays together and sprints for the finish" vs. "Bunch Sprint" with a tooltip. How much real estate do we spend on this?

6. **Field strength indicator (UC-25) — what's the algorithm?** Aggregate carried_points of registered riders vs. historical averages? Needs definition.

7. **"Where does the race get hard?" (UC-31) — this is essentially the narrative's climb sentence. Do we need a separate UI element, or is surfacing the narrative sentence inline on the card enough?**
