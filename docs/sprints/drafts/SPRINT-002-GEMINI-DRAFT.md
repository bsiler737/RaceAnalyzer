# SPRINT-002-GEMINI-DRAFT: Streamlit UI & Query Layer

## Overview

This sprint introduces the first user-facing component of RaceAnalyzer: an interactive web UI built with Streamlit. The goal is to provide users with intuitive tools to explore and analyze Pacific Northwest (PNW) cycling race data. The UI will feature a comprehensive race calendar, detailed per-race analysis with finish type classifications, and a dashboard for visualizing trends over time. This sprint focuses on creating a robust query layer to aggregate data from the existing SQLite database and presenting it through a clean, functional, and insightful interface using Streamlit and Plotly, directly addressing user needs identified in `seed.md` and `research-findings.md`.

## Use Cases

- **UC-1: Browse Race Calendar:** As a user, I want to view all PNW races organized chronologically so I can see what's happened or is coming up. I want to filter this calendar by year, state/province, and race category to narrow down the results.
- **UC-2: Analyze a Specific Race:** As a user, I want to click on a race from the calendar and see a detailed breakdown. For each category in that race, I want to see the classified finish type (e.g., "Bunch Sprint"), accompanied by a color-coded confidence badge and key metrics that justify the classification.
- **UC-3: Understand Finish Type Trends:** As a user, I want to see the overall distribution of finish types across all races to understand what kind of racing is most common. I also want to see how these trends have evolved over the last 5 years via a stacked area chart.
- **UC-4: Simple Application Launch:** As a user, I want a simple, memorable command (`raceanalyzer ui`) to launch the web application.

## Architecture

The architecture for this sprint centers on adding a presentation and query layer to the existing application stack.

1.  **UI Layer (`raceanalyzer/ui/`)**:
    *   A new sub-package to house all Streamlit-related code.
    *   **`__main__.py`**: A dedicated entry point to launch the Streamlit app, allowing for `python -m raceanalyzer.ui`.
    *   **`app.py`**: The main Streamlit application file, handling routing between pages, the sidebar, and global state like the category filter.
    *   **`pages/`**: A directory for individual Streamlit pages (multi-page app structure).
        *   `1_Race_Calendar.py`: Displays a filterable, chronological list of all PNW races.
        *   `2_Race_Detail.py`: Shows finish type classifications for a selected race.
        *   `3_Finish_Type_Dashboard.py`: Contains Plotly charts for finish type distribution and trends.
    *   The UI will be read-only regarding the database. All scraping and classification triggers will remain CLI-only to maintain a separation of concerns.

2.  **Query Layer (`raceanalyzer/queries.py`)**:
    *   A new module responsible for all database interactions required by the UI. It will contain functions that encapsulate SQLAlchemy queries, returning data in a UI-friendly format (e.g., Pandas DataFrames).
    *   This layer will abstract the database schema from the UI code, making the Streamlit pages cleaner and focused on presentation logic.
    *   Functions will handle aggregations, filtering, and fetching data for the calendar, detail views, and charts. All functions will accept a `Session` object to interact with the database.

3.  **CLI Integration (`raceanalyzer/cli.py`)**:
    *   A new `ui` command will be added to the existing Click-based CLI.
    *   This command will use `subprocess` to run `streamlit run raceanalyzer/ui/app.py`, providing a simple and consistent entry point for users.

4.  **Dependencies (`pyproject.toml`)**:
    *   `streamlit` and `plotly` will be added as new project dependencies.

### Key Architectural Decisions
- **Separation of Layers**: The `queries.py` module acts as a service layer, cleanly separating the data access logic from the UI presentation logic in the `ui/` package. This improves testability and maintainability.
- **Streamlit Multi-Page App**: We will use Streamlit's native multi-page app functionality. Each page will be a separate `.py` file in the `pages/` directory, which is a simple and effective way to organize the UI.
- **State Management**: The category selector will be placed in the Streamlit sidebar (`st.sidebar`) to persist its state across pages, a standard and user-friendly Streamlit pattern. Race selection will be managed via query parameters in the URL to make detail pages linkable.

## Implementation

### Phase 1: Setup & Query Layer Foundation

1.  **Update Dependencies**:
    -   Modify `pyproject.toml` to add `streamlit` and `plotly`.
    -   Run `pip install -e ".[dev]"` to update the environment.
2.  **Create Query Module**:
    -   Create `raceanalyzer/queries.py`.
    -   Implement initial query functions with clear signatures:
        -   `get_pnw_races(session: Session, year: int | None, state: str | None, category: str | None) -> pd.DataFrame`: Fetches races for the calendar view. Returns a DataFrame with columns like `id`, `name`, `date`, `location`.
        -   `get_race_classifications(session: Session, race_id: int) -> pd.DataFrame`: Fetches all classifications for a given race. Returns a DataFrame with `category`, `finish_type`, `cv_of_times`, and other metrics.
        -   `get_all_categories(session: Session) -> list[str]`: Fetches a unique, sorted list of all `race_category_name` values from the `results` table.
        -   `get_finish_type_distribution(session: Session, category: str | None) -> pd.DataFrame`: Calculates the count of each `FinishType`.
        -   `get_finish_type_trend(session: Session, category: str | None) -> pd.DataFrame`: Aggregates finish type counts by year.
3.  **Write Tests for Queries**:
    -   Create `tests/test_queries.py`.
    -   Use the `session` fixture from `conftest.py` to test query functions against a pre-populated in-memory SQLite database. Cover filtering and aggregation logic.

### Phase 2: Streamlit App Shell & CLI Command

1.  **Create UI Package**:
    -   Create the directory `raceanalyzer/ui/`.
    -   Create `raceanalyzer/ui/app.py`.
    -   In `app.py`, set up the main page title, sidebar, and the category selector widget.
2.  **Add CLI Command**:
    -   Modify `raceanalyzer/cli.py` to add the `ui` command.
    -   This command will launch the Streamlit application using `subprocess.run(["streamlit", "run", "raceanalyzer/ui/app.py"])`.

### Phase 3: Implementing UI Pages

1.  **Race Calendar Page**:
    -   Create `raceanalyzer/ui/pages/1_Race_Calendar.py`.
    -   Add filters for Year, State/Province, and Category in the sidebar.
    -   Call `queries.get_pnw_races` with the filter values.
    -   Display the resulting DataFrame using `st.dataframe`. Use Streamlit's column configuration to format dates and create a link to the detail page.
2.  **Race Detail Page**:
    -   Create `raceanalyzer/ui/pages/2_Race_Detail.py`.
    -   Retrieve `race_id` from URL query parameters (`st.experimental_get_query_params`).
    -   Call `queries.get_race_classifications` to get the data.
    -   For each category classification, display the `finish_type` and a color-coded confidence badge.
        -   **Confidence Badge Logic**: Map `cv_of_times` to confidence levels (e.g., Green for < 0.005, Yellow for 0.005-0.01, Red for > 0.01) with accompanying text ("High Confidence", "Medium Confidence", "Low Confidence").
    -   Display the supporting metrics (`num_finishers`, `leader_group_size`, etc.) in an expander for progressive disclosure.
3.  **Dashboard Page**:
    -   Create `raceanalyzer/ui/pages/3_Finish_Type_Dashboard.py`.
    -   Call `queries.get_finish_type_distribution` and `queries.get_finish_type_trend`.
    -   Use `plotly.express.pie` to create a pie chart for the overall distribution.
    -   Use `plotly.express.area` to create a stacked area chart for the trend over time.
    -   Render the charts using `st.plotly_chart`.
    -   Ensure charts respect the global category filter from the sidebar.

### Phase 4: Refinement & Edge Cases

1.  **Empty State Handling**: Add checks in all pages to display graceful messages if the query returns an empty DataFrame (e.g., "No races found for the selected filters.", "This race has not been classified yet.").
2.  **Styling and Formatting**: Use Markdown in `st.markdown` to improve text and layout. Format numbers and dates appropriately. Ensure consistent naming and layout across pages.
3.  **Final Review**: Manually test all UI interactions and filters. Ensure all existing 62 tests still pass.

## Files Summary

**New Files:**
- `raceanalyzer/queries.py`: The central module for UI-related database queries.
- `raceanalyzer/ui/__init__.py`: Makes the `ui` directory a package.
- `raceanalyzer/ui/app.py`: The main entry point and shell for the Streamlit application.
- `raceanalyzer/ui/pages/1_Race_Calendar.py`: The race calendar view.
- `raceanalyzer/ui/pages/2_Race_Detail.py`: The race detail view.
- `raceanalyzer/ui/pages/3_Finish_Type_Dashboard.py`: The finish type trends dashboard.
- `tests/test_queries.py`: Unit tests for the new query layer.

**Modified Files:**
- `pyproject.toml`: To add `streamlit` and `plotly` dependencies.
- `raceanalyzer/cli.py`: To add the new `ui` command.

## Definition of Done

1.  All new query functions in `raceanalyzer/queries.py` are implemented and have unit tests in `tests/test_queries.py` with at least 80% coverage.
2.  The `raceanalyzer ui` command successfully launches the Streamlit application.
3.  The Race Calendar page loads, displays PNW races, and can be filtered by year, state, and category.
4.  The Race Detail page displays finish type classifications for a selected race, including color-coded confidence badges based on `cv_of_times`.
5.  The Finish Type Dashboard displays a pie chart of the overall distribution and a stacked area chart of trends over time, both of which respond to the category filter.
6.  The application handles empty states gracefully (e.g., no races found, race not classified).
7.  All existing project tests (`pytest tests/`) continue to pass.

## Risks & Mitigations

- **Risk:** Performance issues with large datasets. The number of races in the PNW is manageable, but inefficient queries could slow down the UI.
  - **Mitigation:** The query layer is designed to use efficient SQLAlchemy queries and Pandas for transformations. All queries will be indexed where appropriate. We will initially test with the full dataset to identify any bottlenecks early.
- **Risk:** Scope creep in UI features. "Meaningful analysis" is broad and could lead to adding more features than planned.
  - **Mitigation:** This sprint is strictly limited to the three defined pages and their core functionality. Additional analysis or features (like rider-specific views) will be deferred to future sprints.
- **Risk:** The `cv_of_times` metric may not be a perfect proxy for classification confidence.
  - **Mitigation:** For this sprint, we will use a simple threshold-based mapping for the confidence badge as a starting point. The underlying metric will be displayed, and the mapping can be refined in future sprints as we gain more domain knowledge.

## Security Considerations

- As this is a locally-run tool with no remote access or user authentication, the security risks are minimal.
- The application will only have read-access to the local SQLite database.
- We must ensure that any user input (from filters) is properly handled by the SQLAlchemy layer to prevent SQL injection, which SQLAlchemy's ORM does by default.

## Dependencies

- **New:**
  - `streamlit`: For building the interactive web UI.
  - `plotly`: For creating interactive charts and visualizations.
- **Existing:** `sqlalchemy`, `pandas`, `click`.

## Open Questions

1.  **Should the query layer be a separate module or integrated into a `raceanalyzer/ui/` package?**
    -   **Decision:** It will be a separate top-level module, `raceanalyzer/queries.py`. This promotes better separation of concerns and allows the query layer to be reused by other components (e.g., a future API) without creating a dependency on the UI package.
2.  **How should race names be grouped across years (e.g., a `series` concept)?**
    -   **Decision:** This is a valuable feature for future analysis but adds significant complexity (requires heuristics or manual curation). This will be deferred to a future sprint to keep the scope of the UI foundation manageable.
3.  **Should the UI include a "scrape" trigger button?**
    -   **Decision:** No. To maintain a clear separation between the analytical UI and the data pipeline, scraping and classification will remain CLI-only operations for this sprint.
4.  **What categories should appear in the category selector?**
    -   **Decision:** The selector will be dynamically populated with all unique categories present in the database. This is more robust and requires no maintenance as new data is scraped. A query `get_all_categories` will be implemented for this.
5.  **For the trend chart, what's the minimum number of years of data before showing it?**
    -   **Decision:** The chart will be displayed if there is data for two or more years. Less than that does not constitute a trend, and a message will be displayed instead.
