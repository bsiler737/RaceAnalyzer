# Sprint 010: Unified Race Feed (UX Overhaul)

## Overview
This sprint shifts RaceAnalyzer from a multi-page dashboard to a single, unified, forward-looking race feed. Designed for newer PNW road racers deciding what to race next, the new UX collapses upcoming races and historical intelligence into one view. Users will be able to discover a race, understand its course and expected dynamics, and assess the competition without clicking through multiple pages.

## Use Cases
Prioritized from the "Good" use cases in `USE_CASES_UX_IMPROVEMENT.md`:
- **A. Unified Race Feed**: Single feed of upcoming races, sorted by date (soonest first). Historical editions collapse under the upcoming race. Inline registration links. (UC-01, UC-03, UC-04, UC-05, UC-06, UC-07)
- **B. Reducing Race-Day Anxiety**: 1-2 sentence "What to Expect" narrative visible inline. Plain English finish types (e.g., "The group usually stays together and sprints" vs. "Bunch Sprint"). (UC-08, UC-09, UC-10, UC-16)
- **D. Understanding the Competition**: Field strength indicator and team representation summaries. (UC-25, UC-26, UC-28)
- **E. Course Intelligence**: Small course profile sparkline/thumbnail and "where does it get hard?" sentence on the feed card. (UC-29, UC-31, UC-32)
- **H. Information Architecture**: Single entry point (the Feed). Persistent global category filter. Inline card expansion via `st.expander` or session state instead of page navigation. "This Weekend" quick filter. Search by name. Deep linking support. (UC-44, UC-45, UC-46, UC-47, UC-48, UC-49, UC-50)

*Excluded/Deferred*: Side-by-side comparison (UC-37), course comparison (UC-33), and season calendar view (UC-38) are deferred to keep the sprint tightly scoped to the feed architecture.

## Architecture
- **Streamlit Single-Page Focus**: The app will consolidate around `calendar.py` (repurposed as the "Feed"). We will reduce reliance on `st.navigation()` and `st.switch_page()` for the core discovery flow. 
- **Inline Expansion**: We will utilize Streamlit's `st.expander` (or session-state driven conditional rendering) for inline race details (UC-46). When a user expands a race card, it will reveal the full course profile, narrative, and contender list that currently lives on `race_preview.py`.
- **Persistent State**: The selected Category and Search terms will be stored in `st.session_state` and synced with `st.query_params` to enable deep linking (UC-47) and state memory (UC-50).
- **Component Refactoring**: The existing UI functions in `queries.py` and `components.py` will be adapted to return compact versions (e.g., a simplified text summary or smaller badge).

## Implementation

### Phase 1: Feed Foundation & State Management
- Modify `app.py` and `calendar.py` to prioritize the single feed view.
- Implement a persistent Category selector in the sidebar/header that updates `st.session_state.category`.
- Add a "Search by Name" text input and a "This Weekend" toggle filter to the top of the feed.
- Sort the main feed by upcoming race date (soonest first).

### Phase 2: The Unified Race Card
- Redesign the race card in `calendar.py` to include:
  - The 1-2 sentence "What to Expect" narrative inline (UC-08).
  - Plain English finish type descriptions (UC-09).
  - A compact terrain indicator (UC-29).
  - A prominent "Register" button (UC-07).
  - A field strength indicator (UC-25).
- Ensure dormant series (no upcoming date) are visually deprioritized or grouped at the bottom of the feed.

### Phase 3: Inline Expansion & Preview Integration
- Replace the "View Preview" page navigation with an inline `st.expander("View Full Race Details")` (or button toggle) on each race card.
- Move the rendering logic from `race_preview.py` (interactive map, full contender list, historical stats) into the expanded state of the card.
- Ensure `st.query_params` updates when a specific race is expanded to support deep linking to a specific race in the feed (UC-47).

### Phase 4: Refinement & Data Surfacing
- Implement logic for "team representation" summary in the startlist view (UC-28).
- Refine the plain English finish type text and tooltips in `queries.py` or `components.py`.
- Ensure all existing `pytest` tests pass and functionality from the old separate pages is properly encapsulated in the new feed.

## Files Summary
- `raceanalyzer/ui/app.py`: Update routing/navigation to focus on the unified feed.
- `raceanalyzer/ui/pages/calendar.py`: Major refactor to become the "Unified Feed", implementing search, filters, and inline expanders.
- `raceanalyzer/ui/pages/race_preview.py`: Logic extracted into reusable components for the feed's expanded state; file may be deprecated or kept only for explicit deep-link routing.
- `raceanalyzer/ui/components.py`: New components for inline race cards, plain-English finish types, field strength indicators, and mini course profiles.
- `raceanalyzer/queries.py`: Update query functions to support feed sorting, efficient bulk narrative loading, and search.

## Definition of Done
- A single unified feed is the default landing experience.
- Upcoming races are sorted chronologically at the top.
- Race cards display narrative, plain-English finish type, terrain badge, and drop rate inline.
- Expanding a race card shows full preview details (map, contenders) without navigating to a new page.
- Category filter persists across the session.
- Search and "This Weekend" filters function correctly.
- All existing tests pass.

## Risks
- **Streamlit Performance**: Rendering many `st.expander` components with complex data (maps, charts) could slow down the page. *Mitigation*: Lazily load the complex preview data only when the expander is opened (e.g., using session state or `@st.fragment` in newer Streamlit versions), or rely heavily on the existing pagination.
- **Data Clutter**: Trying to fit narrative, stats, and badges on one card might make the UI too dense. *Mitigation*: Strict adherence to visual hierarchy and whitespace.

## Security
- No new external APIs are introduced. Database access remains read-only for the UI.

## Dependencies
- Existing data pipeline (SQLite, classified races, generated narratives).

## Open Questions
- **Lazy Loading in Streamlit**: Will `st.expander` render all nested Plotly/Leaflet charts eagerly? If so, we may need to use `st.button` toggles instead of `st.expander` to conditionally render the heavy components only when clicked.
- **Deep Linking**: Should the deep link to a specific race (`?series_id=123`) scroll the feed to that card and expand it, or should it temporarily isolate that race at the top of the feed? (Isolating might be easier to implement and less confusing for the user).
- **Field Strength Algorithm**: How exactly do we calculate the field strength summary metric? (e.g., median carried points vs. historical average for the category).