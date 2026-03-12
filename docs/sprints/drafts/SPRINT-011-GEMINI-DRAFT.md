# Sprint 011: Feed First Glance, Detail Dive, Personalization & Performance

## Overview

Sprint 011 is a comprehensive overhaul of the RaceAnalyzer feed experience. It transitions the application from a functional list of races to a high-performance, personalized decision engine tailored to the beginner racer persona. The sprint introduces 31 use cases across five themes:

1. **Performance**: Eliminate N+1 queries, pre-compute predictions, and introduce batch/lazy loading to ensure <1s cold load times.
2. **Feed Organization**: Adopt a month-based agenda view with discipline and geographic filters.
3. **First Glance**: Restructure feed cards to instantly answer the user's highest priority questions without requiring expansion.
4. **My Team (Personalization)**: Introduce a lightweight team affiliation setting to surface teammates across the app.
5. **Detail Dive**: Enrich the race preview page with hero visualizations, plain-English climb breakdowns, team-grouped startlists, and similar-race discovery.

## Use Cases

### First Glance (No Click Required)
- **FG-01**: Date and location visible in the card header.
- **FG-02**: Teammates registered badge prominently displayed.
- **FG-03**: Course character one-liner (terrain + distance + gain) on the first visual row.
- **FG-04**: Finish pattern prediction highlighted as the headline of the card content.
- **FG-05**: Field size (typical or registered) shown on the card.
- **FG-06**: Drop rate label (low/moderate/high) emphasized over the raw percentage.
- **FG-07**: Race type icon or label (road race, crit, etc.) for familiarity.
- **FG-08**: Reorder card content to strictly match racer decision priority.

### Detail Dive (One Click Deep)
- **DD-01**: Interactive course profile as the hero visualization.
- **DD-02**: Climb-by-climb breakdown with context (where the race splits vs. recovers).
- **DD-03**: Startlist visually grouped by team to expose pack dynamics.
- **DD-04**: Expanded "What kind of racer does well here?" paragraph.
- **DD-05**: Visual timeline of historical finish types.
- **DD-06**: "Similar races" cross-reference using course type and finish type.
- **DD-07**: Course map featuring key race markers (start/finish, climbs).

### My Team
- **MT-01**: Persist the user's team name via sidebar configuration.
- **MT-02**: Identify and list specific registered teammates directly on feed cards.

### Feed Organization
- **FO-01**: Top-level Discipline filter (Road, Gravel, CX, MTB, Track).
- **FO-02**: Race type filter within the selected discipline (Crit, Road Race, etc.).
- **FO-03**: Geographic filter by state/region.
- **FO-04**: Persistent filter preferences across sessions (via URL and session state).
- **FO-05**: Days-until countdown labels (e.g., "in 3 days") replacing "SOON/UPCOMING".
- **FO-06**: Month-based section headers functioning as an agenda view.
- **FO-07**: Remove the auto-expanded "Racing Soon" section to treat all upcoming races equally.
- **FO-08**: Ensure collapsed cards are highly dense and scannable.

### Performance
- **PF-01**: Eliminate N+1 queries in `get_feed_items` via batch loading.
- **PF-02**: Cache main feed results at the query layer.
- **PF-03**: Lazy-load expanded card content (narratives, sparklines) on click.
- **PF-04**: Pre-compute predictions during scraping and store them.
- **PF-05**: Push pagination to the database query layer.
- **PF-06**: Profile feed loads and assert a <1s cold / <200ms warm budget.

---

## Architecture

### 1. Data Modeling Changes
- **Discipline Modeling**: Introduce a `Discipline` Enum (`ROAD`, `GRAVEL`, `CX`, `MTB`, `TRACK`). Map `RaceType` values to `Discipline` implicitly, or add a `discipline` column to `RaceSeries`. Given the scale, adding `discipline` to `RaceSeries` ensures fast top-level filtering.
- **Pre-computed Predictions**: Create a `SeriesPrediction` table to cache computationally heavy aggregations.
  ```python
  class SeriesPrediction(Base):
      __tablename__ = "series_predictions"
      id = Column(Integer, primary_key=True)
      series_id = Column(Integer, ForeignKey("race_series.id"), unique=True)
      category = Column(String, nullable=True) # Null for overall
      predicted_finish_type = Column(SAEnum(FinishType))
      confidence = Column(String)
      drop_rate_pct = Column(Float)
      drop_rate_label = Column(String)
      median_winner_speed_kph = Column(Float)
      edition_count = Column(Integer)
      last_computed_at = Column(DateTime)
  ```

### 2. Query Layer Optimizations
- **Pagination & Batching**: Overhaul `get_feed_items` to accept `limit` and `offset`. Instead of a Python loop querying relationships per series, the query will `JOIN` `SeriesPrediction`, `Course`, and use window functions (e.g., `ROW_NUMBER()`) to fetch the single most relevant upcoming/recent `Race` per series in one database trip.
- **Caching**: Wrap `get_feed_items` (or an underlying fetcher) with `@st.cache_data(ttl=300)`. Use a tuple of filter arguments as the cache key.
- **Lazy Loading Strategy**: `get_feed_items` will only fetch "Tier 1" data required for the collapsed card. A new function `get_feed_item_expanded_details(series_id)` will fetch narratives, sparklines, and editions summaries only when the card expands.

### 3. Personalization State
- Track the user's team name via `st.session_state.my_team`. Support persistence by reading/writing to local browser storage via a lightweight Streamlit component or storing it in URL parameters (though URL params might be cluttered).

---

## Implementation (Phased Approach)

Given the magnitude of the sprint (31 use cases), implementation is strictly phased to ensure stability.

### Phase 1: The Performance Foundation (PF-01 to PF-06)
1. **Schema Migration**: Add `SeriesPrediction` table and `discipline` column to `RaceSeries`.
2. **Pre-computation Engine**: Extract prediction logic from `predictions.py` into a batch job `raceanalyzer compute-predictions`. Run this after scraping.
3. **Query Rewrite**: Rewrite `get_feed_items(session, limit, offset, filters...)` to execute in <3 SQL queries using the new predictions table.
4. **Lazy Loading UI**: Refactor `ui/pages/feed.py` so expanders fetch their rich content via `st.session_state` or a separate cached function upon expansion.
5. **Instrumentation**: Wrap the query layer with `time.perf_counter()` to enforce the performance budget.

### Phase 2: Feed Organization & First Glance (FO-01 to FO-08, FG-01 to FG-08)
1. **Filters**: Add Discipline, Race Type, and State filters to the sidebar. Sync all to URL parameters.
2. **Month Grouping**: Refactor the feed rendering loop to group fetched items by `upcoming_date.strftime('%B %Y')`. 
3. **Countdown Logic**: Implement a `days_until_str(date)` utility and inject it into card headers.
4. **Card Density & Reorder**: Build a new CSS grid layout for collapsed feed cards ensuring all FG constraints (terrain badge + distance + gain + field size + drop rate) fit into 2 lines.

### Phase 3: My Team & Detail Dive (MT-01 to MT-02, DD-01 to DD-07)
1. **My Team**: Add a text input in the sidebar for "My Team". Update `get_feed_items` to join against the `Startlist` table dynamically to count/list teammates.
2. **Preview Page Overhaul**:
   - Promote the interactive Folium map and RWGPS elevation profile to the top.
   - Build a `generate_climb_breakdown(climbs, finish_type)` narrative function.
   - Group the Startlist DataFrame by the `team` column.
   - Implement `get_similar_races(course_type, distance_m, finish_type)` heuristic.

---

## Files Summary

| File | Proposed Changes |
|------|------------------|
| `raceanalyzer/db/models.py` | Add `Discipline` enum, add `SeriesPrediction` table, add `discipline` to `RaceSeries`. |
| `raceanalyzer/queries.py` | Massive rewrite of `get_feed_items` for batch queries and pagination. Add `get_feed_item_details`. |
| `raceanalyzer/predictions.py` | Create a batch computation script that writes to `SeriesPrediction`. Add similarity algorithms. |
| `raceanalyzer/ui/pages/feed.py` | Implement month grouping, countdowns, lazy-loading expanders, and remove "Racing Soon" tier. |
| `raceanalyzer/ui/components.py` | Redesign `render_feed_card` and expander labels for extreme density and priority ordering. Add filters. |
| `raceanalyzer/ui/pages/preview.py` | Overhaul to include hero map/profile, climb breakdowns, team-grouped startlists, and similar races. |
| `raceanalyzer/cli.py` | Add a `compute-predictions` command. |
| `tests/test_queries.py` | Assert N+1 queries are eliminated. Test pagination and batch loading. |
| `tests/test_feed_ui.py` | Validate month grouping, countdown strings, and teammate badge logic. |

---

## Definition of Done

1. **Performance**: `get_feed_items` executes 3 or fewer SQL queries. The feed page loads in <1.0s (cold cache) and <0.2s (warm cache) for 100+ series.
2. **UI correctness**: The feed is grouped by month. "Racing Soon" is gone. Countdowns are present. Card content matches the persona priority order.
3. **Filtering**: Discipline, race type, category, and state filters work simultaneously and persist in the URL.
4. **Personalization**: Entering a team name successfully highlights races where teammates are registered.
5. **Detail Dive**: The preview page contains a functional hero course profile, climb breakdown, team-grouped startlist, and similar race recommendations.
6. **Tests**: All new queries, utility functions, and CLI commands are covered by pytest fixtures. Existing tests pass.

---

## Risks

- **SQLite Limitations**: Complex batch queries (specifically fetching the "latest" or "upcoming" race per series alongside aggregations) might require sophisticated `ROW_NUMBER() OVER (...)` window functions. SQLite supports window functions natively since version 3.25.0, but we must ensure the local dev/prod environments utilize a compatible version.
- **Lazy Loading in Streamlit**: Streamlit's execution model reruns the entire script on interaction. True "lazy loading" inside an expander can be tricky; clicking an expander will trigger a rerun. We must rely on `@st.cache_data` on the detail-fetch function to avoid redundant database hits upon expansion.
- **Teammate Startlist Join**: Dynamically calculating "teammates registered" for every series in the feed query could re-introduce N+1 or slow table scans if `startlists.team` is unindexed.

---

## Security

- **SQL Injection**: Ensure all search and filter parameters (e.g., team name input, discipline filters) are bound safely via SQLAlchemy ORM.
- **Data Privacy**: Teammate names are derived from public startlists, but providing an aggregated view introduces minor privacy implications. Adhere to the existing application standard of only surfacing publicly scraped data. No user authentication is introduced.

---

## Dependencies

- No new external Python packages are strictly required. 
- Existing `folium` and `streamlit-folium` (Sprint 008) will be reused heavily.
- Built-in `time` module for PF-06 profiling.

---

## Open Questions

1. **Similar Races Algorithm**: Will a basic heuristic (matching `course_type`, `predicted_finish_type`, and `distance_m +/- 20%`) yield sufficiently useful comparisons, or should we use K-Nearest Neighbors on the normalized profile data? *(Decision: Start with the basic heuristic for Phase 3, iterate later).*
2. **Team Name Normalization**: "Team Rapha", "Rapha Racing", and "Rapha" are often distinct in BikeReg data. Do we perform fuzzy matching on the user's `my_team` input, or require an exact match? *(Decision: Start with case-insensitive substring matching `startlists.team ILIKE %user_input%`).*
3. **Streamlit Expander State**: When a user clicks an expander, Streamlit reruns. If the feed is heavily paginated or dynamically filtered, expander state might collapse on rerun unless explicitly managed in `st.session_state`. We need to verify UI stability during the lazy-load implementation.
