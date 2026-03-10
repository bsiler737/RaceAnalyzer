# Sprint 002: Streamlit UI & Query Layer

*Codex Draft — Independent perspective for synthesis review*

## Overview

Sprint 001 delivered a complete data pipeline: scraper, SQLite storage, gap-grouping classifier, and CLI. The database now holds race results with per-category finish type classifications, group-structure metrics, and confidence signals (via `cv_of_times`). What it lacks is any way for a human to explore this data. Sprint 002 closes that gap by building a Streamlit + Plotly visualization layer and the SQLAlchemy query functions that feed it.

The central design decision in this sprint is where the query logic lives. The intent document asks whether queries should be a standalone module or embedded in the UI package. This draft argues for a **separate `raceanalyzer/queries.py` module** that returns plain data structures (lists of dicts, DataFrames) with zero Streamlit imports. The reasoning is testability: query functions can be unit-tested against an in-memory SQLite database without spinning up a Streamlit app or mocking `st.session_state`. The UI layer (`raceanalyzer/ui/`) then becomes a thin presentation skin that calls query functions and renders Plotly charts. This separation also positions the query layer for reuse by future CLI analytics commands or a REST API, should one ever be needed.

The second key decision is how to handle confidence display. The `RaceClassification` table stores `cv_of_times` (coefficient of variation) as a continuous float, but research-findings.md explicitly says to show color-coded badges with natural language qualifiers, not raw decimals. This draft defines a three-tier confidence mapping — High (green), Medium (yellow), Low (red) — derived from `cv_of_times` thresholds calibrated to the classifier's known behavior: classifications with `cv_of_times < 0.005` (tight finishes, clear pattern) get green; `0.005-0.02` get yellow; above `0.02` get red. These thresholds are configurable in `Settings` so they can be tuned as more data is classified.

## Use Cases

1. **UC-1: Browse Race Calendar** — A user opens the app and sees all PNW races in chronological order. They can filter by year (dropdown), state/province (multiselect: WA, OR, ID, BC), and race category (sidebar selector that persists across pages). Each row shows race name, date, location, state, and the dominant finish type for the selected category (or "Not classified" if no classification exists).

2. **UC-2: View Race Detail** — From the calendar, the user clicks a race name to see all category classifications for that race. Each category row shows: finish type with a color-coded confidence badge (green/yellow/red), natural language qualifier ("Likely bunch sprint"), number of finishers, number of gap groups, largest group ratio, and gap to second group in seconds.

3. **UC-3: Explore Finish Type Distribution** — The user navigates to a dashboard page showing two charts: (a) a Plotly bar chart of finish type distribution across all classified races, filterable by the sidebar category selector; and (b) a Plotly stacked area chart showing finish type proportions over time (by year), revealing trends like "sprints are becoming less common in Cat 3 races."

4. **UC-4: Category-Scoped Analysis** — The sidebar category selector (populated dynamically from database categories) filters all pages simultaneously. Selecting "Men Pro/1/2" constrains the calendar to races with that category, the detail page to that category's classification, and the dashboard charts to that category's data.

5. **UC-5: Empty Database Handling** — A user who runs the app before scraping any data sees informative empty states on every page: "No races found. Run `raceanalyzer scrape` to import data." instead of blank charts or Python errors.

6. **UC-6: Launch from CLI** — The user runs `python -m raceanalyzer ui` (or `raceanalyzer ui`) and a Streamlit app opens in their browser. No manual `streamlit run` invocation required.

## Architecture

### Package Layout

```
raceanalyzer/
    queries.py               # SQLAlchemy query functions (no Streamlit imports)
    ui/
        __init__.py
        app.py               # Streamlit entry point (multipage config, sidebar)
        pages/
            __init__.py
            calendar.py       # Race calendar page
            race_detail.py    # Single race detail page
            dashboard.py      # Finish type distribution + trend charts
        components/
            __init__.py
            badges.py         # Confidence badge rendering (color-coded HTML)
            charts.py         # Plotly chart builders (bar, stacked area)
            filters.py        # Sidebar filter widgets (year, state, category)
            empty_states.py   # Graceful empty state messages
```

### Component Descriptions

| Component | Responsibility |
|-----------|---------------|
| `queries.py` | All SQLAlchemy queries: calendar listing, race detail, finish type distributions, yearly trends, distinct categories/years/states. Returns dicts and lists, never Streamlit objects. |
| `ui/app.py` | Streamlit `st.set_page_config()`, sidebar layout, multipage navigation via `st.navigation()` (Streamlit 1.36+) or manual radio-button page switching for broader compatibility. Initializes DB session in `st.session_state`. |
| `ui/pages/calendar.py` | Renders the race calendar as a `st.dataframe` with clickable race names (via `st.query_params` for navigation). Calls `queries.get_race_calendar()`. |
| `ui/pages/race_detail.py` | Shows all category classifications for a single race. Renders confidence badges and group metrics. Calls `queries.get_race_detail()`. |
| `ui/pages/dashboard.py` | Two Plotly charts: `px.bar` for finish type distribution and `px.area` (stacked) for year-over-year trends. Calls `queries.get_finish_type_distribution()` and `queries.get_finish_type_trend()`. |
| `ui/components/badges.py` | Converts `cv_of_times` float to a colored HTML badge with natural language qualifier. Uses `st.markdown(unsafe_allow_html=True)`. |
| `ui/components/charts.py` | Builds Plotly figures with consistent styling (color palette for 8 finish types, axis labels, hover templates). |
| `ui/components/filters.py` | Sidebar widgets: `st.selectbox` for year, `st.multiselect` for state, `st.selectbox` for category. Reads distinct values from query layer. Stores selections in `st.session_state` for cross-page persistence. |
| `ui/components/empty_states.py` | Standardized `st.info()` messages for empty query results with actionable guidance. |

### Data Flow

```
Browser (Streamlit frontend)
         |
         v
  ui/app.py  (session init, sidebar filters, page routing)
         |
         +--- ui/pages/calendar.py ----+
         |                              |
         +--- ui/pages/race_detail.py --+---> queries.py ---> SQLAlchemy Session
         |                              |          |
         +--- ui/pages/dashboard.py ----+          v
                    |                        SQLite DB
                    v                    (races, results,
         ui/components/                  race_classifications)
           badges.py
           charts.py
           filters.py
           empty_states.py
```

### Confidence Badge Logic

The classifier stores `cv_of_times` on `RaceClassification`. The badge mapping:

| CV Range | Label | Color | CSS Class |
|----------|-------|-------|-----------|
| cv < 0.005 | "High confidence" | Green (#28a745) | `badge-high` |
| 0.005 <= cv < 0.02 | "Medium confidence" | Yellow (#ffc107) | `badge-medium` |
| cv >= 0.02 or NULL | "Low confidence" | Red (#dc3545) | `badge-low` |

Natural language qualifiers combine finish type + confidence: "Likely bunch sprint" (high), "Probable breakaway" (medium), "Possible GC selective" (low).

### Finish Type Color Palette

Consistent across all charts:

| Finish Type | Color |
|-------------|-------|
| BUNCH_SPRINT | #1f77b4 (blue) |
| SMALL_GROUP_SPRINT | #aec7e8 (light blue) |
| BREAKAWAY | #ff7f0e (orange) |
| BREAKAWAY_SELECTIVE | #ffbb78 (light orange) |
| REDUCED_SPRINT | #2ca02c (green) |
| GC_SELECTIVE | #d62728 (red) |
| MIXED | #9467bd (purple) |
| UNKNOWN | #c7c7c7 (gray) |

## Implementation

### Phase 1: Dependencies & CLI Launcher (5% of effort)

**Files:**
- `pyproject.toml` — Add `streamlit>=1.32` and `plotly>=5.18` to dependencies
- `raceanalyzer/cli.py` — Add `ui` subcommand
- `raceanalyzer/config.py` — Add confidence threshold settings

**Tasks:**

| Task | Description |
|------|-------------|
| 1.1 | Add `streamlit>=1.32` and `plotly>=5.18` to `[project.dependencies]` in `pyproject.toml` |
| 1.2 | Add `ui` command to CLI that launches Streamlit via `subprocess.run(["streamlit", "run", app_path])` |
| 1.3 | Add confidence threshold fields to `Settings` dataclass |

**Key signatures:**
```python
# raceanalyzer/cli.py (addition)
@main.command()
@click.option("--port", default=8501, help="Streamlit server port.")
@click.pass_context
def ui(ctx, port: int) -> None:
    """Launch the Streamlit UI."""
    ...

# raceanalyzer/config.py (additions)
@dataclass
class Settings:
    ...
    confidence_high_threshold: float = 0.005   # cv_of_times below this = green
    confidence_medium_threshold: float = 0.02  # cv_of_times below this = yellow, above = red
    streamlit_port: int = 8501
```

### Phase 2: Query Layer (25% of effort)

**Files:**
- `raceanalyzer/queries.py` — New file, all query functions

**Tasks:**

| Task | Description |
|------|-------------|
| 2.1 | Implement `get_race_calendar()` — paginated race listing with optional filters |
| 2.2 | Implement `get_race_detail()` — all classifications for a single race |
| 2.3 | Implement `get_finish_type_distribution()` — aggregated counts by finish type |
| 2.4 | Implement `get_finish_type_trend()` — yearly finish type counts for stacked area chart |
| 2.5 | Implement `get_distinct_categories()`, `get_distinct_years()`, `get_distinct_states()` — filter options |
| 2.6 | Write unit tests for all query functions against seeded in-memory SQLite |

**Key function signatures:**
```python
# raceanalyzer/queries.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from raceanalyzer.db.models import FinishType, Race, RaceClassification


def get_race_calendar(
    session: Session,
    *,
    year: Optional[int] = None,
    states: Optional[list[str]] = None,
    category: Optional[str] = None,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    """Return races ordered by date (descending) with optional filters.

    Each dict contains: race_id, name, date, location, state_province,
    finish_type (for the given category, or most common across categories),
    num_categories.

    Joins Race -> RaceClassification, groups by race, filters by year/state/category.
    """
    ...


def get_race_detail(
    session: Session,
    race_id: int,
) -> dict:
    """Return full race info with all category classifications.

    Returns: {
        "race": {id, name, date, location, state_province, url},
        "classifications": [
            {category, finish_type, confidence_level, confidence_color,
             qualifier_text, num_finishers, num_groups, largest_group_size,
             largest_group_ratio, leader_group_size, gap_to_second_group,
             cv_of_times},
            ...
        ]
    }
    """
    ...


def get_finish_type_distribution(
    session: Session,
    *,
    category: Optional[str] = None,
    states: Optional[list[str]] = None,
    year: Optional[int] = None,
) -> list[dict]:
    """Return finish type counts for bar chart.

    Each dict: {finish_type: str, count: int, percentage: float}
    Uses: func.count(), group_by(RaceClassification.finish_type)
    """
    ...


def get_finish_type_trend(
    session: Session,
    *,
    category: Optional[str] = None,
    states: Optional[list[str]] = None,
    min_year: Optional[int] = None,
) -> list[dict]:
    """Return yearly finish type counts for stacked area chart.

    Each dict: {year: int, finish_type: str, count: int, percentage: float}
    Uses: extract('year', Race.date), func.count(), group_by(year, finish_type)
    """
    ...


def get_distinct_categories(session: Session) -> list[str]:
    """Return all unique category names from race_classifications, sorted."""
    ...


def get_distinct_years(session: Session) -> list[int]:
    """Return all unique years from races with classifications, descending."""
    ...


def get_distinct_states(session: Session) -> list[str]:
    """Return all unique state_province values from classified races."""
    ...


def compute_confidence_level(cv_of_times: Optional[float]) -> tuple[str, str, str]:
    """Map cv_of_times to (level, color_hex, qualifier_prefix).

    Returns:
        ("high", "#28a745", "Likely") | ("medium", "#ffc107", "Probable") | ("low", "#dc3545", "Possible")
    """
    ...
```

### Phase 3: UI Skeleton & Sidebar (15% of effort)

**Files:**
- `raceanalyzer/ui/__init__.py`
- `raceanalyzer/ui/app.py`
- `raceanalyzer/ui/pages/__init__.py`
- `raceanalyzer/ui/components/__init__.py`
- `raceanalyzer/ui/components/filters.py`
- `raceanalyzer/ui/components/empty_states.py`

**Tasks:**

| Task | Description |
|------|-------------|
| 3.1 | Create `ui/app.py` with `st.set_page_config(page_title="RaceAnalyzer", layout="wide")`, DB session init in `st.session_state`, and page routing |
| 3.2 | Implement sidebar filters: year selector (`st.selectbox`), state multiselect (`st.multiselect`), category selector (`st.selectbox`) — all populated from query layer |
| 3.3 | Implement empty state component: `render_empty_state(entity: str)` showing `st.info()` with CLI guidance |
| 3.4 | Wire `st.session_state["db_session"]` initialization with `get_session()` from `db/engine.py` |

**Key signatures:**
```python
# raceanalyzer/ui/app.py
import streamlit as st

from raceanalyzer.db.engine import get_session
from raceanalyzer.config import Settings


def main() -> None:
    """Streamlit app entry point."""
    st.set_page_config(
        page_title="RaceAnalyzer",
        page_icon="🚴",
        layout="wide",
    )
    _init_session_state()
    _render_sidebar()
    _route_pages()


def _init_session_state() -> None:
    """Initialize DB session and shared state once."""
    if "db_session" not in st.session_state:
        settings = Settings()
        st.session_state["db_session"] = get_session(settings.db_path)
        st.session_state["settings"] = settings


def _render_sidebar() -> None:
    """Render persistent sidebar filters."""
    ...


def _route_pages() -> None:
    """Route to the selected page."""
    ...


# raceanalyzer/ui/components/filters.py
def render_sidebar_filters(session) -> dict:
    """Render year, state, category filters in sidebar. Returns filter dict.

    Returns: {"year": int|None, "states": list[str], "category": str|None}
    """
    ...


# raceanalyzer/ui/components/empty_states.py
def render_empty_state(entity: str = "races") -> None:
    """Show st.info() with guidance when no data is found."""
    ...
```

### Phase 4: Race Calendar Page (15% of effort)

**Files:**
- `raceanalyzer/ui/pages/calendar.py`

**Tasks:**

| Task | Description |
|------|-------------|
| 4.1 | Implement calendar page: call `get_race_calendar()` with sidebar filters, render as `st.dataframe` with columns: Date, Name, Location, State, Finish Type, Categories |
| 4.2 | Make race names clickable via `st.query_params` to navigate to race detail page |
| 4.3 | Add sort controls (date ascending/descending) |
| 4.4 | Handle empty result set with `render_empty_state("races")` |

**Key signature:**
```python
# raceanalyzer/ui/pages/calendar.py
def render_calendar_page(session, filters: dict) -> None:
    """Render the race calendar page.

    Displays a filterable, sortable table of all PNW races with:
    - Date, Name (clickable), Location, State, dominant finish type for
      selected category (or overall if no category selected), category count.
    - Uses st.dataframe for the table.
    - Clicking a race name sets st.query_params(race_id=...) to navigate
      to the detail page.
    """
    ...
```

### Phase 5: Race Detail Page (15% of effort)

**Files:**
- `raceanalyzer/ui/pages/race_detail.py`
- `raceanalyzer/ui/components/badges.py`

**Tasks:**

| Task | Description |
|------|-------------|
| 5.1 | Implement race detail page: read `race_id` from `st.query_params`, call `get_race_detail()`, display race header (name, date, location) |
| 5.2 | Render per-category classification cards: finish type name, confidence badge (colored HTML span), qualifier text, group metrics in an expander |
| 5.3 | Implement `render_confidence_badge()` in `badges.py` using `st.markdown(unsafe_allow_html=True)` |
| 5.4 | Handle missing race or no classifications gracefully |

**Key signatures:**
```python
# raceanalyzer/ui/pages/race_detail.py
def render_race_detail_page(session) -> None:
    """Render the detail page for a single race.

    Reads race_id from st.query_params. Shows race header and a card
    per category with finish type, confidence badge, and group metrics
    in an expandable section.
    """
    ...


# raceanalyzer/ui/components/badges.py
def render_confidence_badge(
    finish_type: str,
    cv_of_times: float | None,
) -> str:
    """Return HTML string for a color-coded confidence badge.

    Example output:
    '<span style="background-color:#28a745;color:white;padding:2px 8px;
     border-radius:4px;font-size:0.85em;">Likely bunch sprint</span>'
    """
    ...


def render_finish_type_label(finish_type: str) -> str:
    """Convert enum value to human-readable label.

    'bunch_sprint' -> 'Bunch Sprint'
    'gc_selective' -> 'GC Selective'
    """
    ...
```

### Phase 6: Finish Type Dashboard (15% of effort)

**Files:**
- `raceanalyzer/ui/pages/dashboard.py`
- `raceanalyzer/ui/components/charts.py`

**Tasks:**

| Task | Description |
|------|-------------|
| 6.1 | Implement distribution bar chart: `plotly.express.bar()` with finish types on x-axis, count on y-axis, colored by finish type using the defined palette |
| 6.2 | Implement stacked area trend chart: `plotly.express.area()` with year on x-axis, count (or percentage) on y-axis, color by finish type, `groupnorm="percent"` for normalized view |
| 6.3 | Add toggle between absolute counts and percentage view for both charts |
| 6.4 | Wire sidebar filters (category, state, year range) into both charts |
| 6.5 | Handle insufficient data for trend chart (fewer than 2 years) with `st.warning()` |

**Key signatures:**
```python
# raceanalyzer/ui/pages/dashboard.py
def render_dashboard_page(session, filters: dict) -> None:
    """Render the finish type analytics dashboard.

    Two main sections:
    1. Distribution: px.bar of finish type counts, filtered by sidebar selections
    2. Trends: px.area (stacked) of finish type proportions over years

    Includes toggle for absolute vs. percentage view.
    """
    ...


# raceanalyzer/ui/components/charts.py
import plotly.express as px
import plotly.graph_objects as go

FINISH_TYPE_COLORS: dict[str, str] = {
    "bunch_sprint": "#1f77b4",
    "small_group_sprint": "#aec7e8",
    "breakaway": "#ff7f0e",
    "breakaway_selective": "#ffbb78",
    "reduced_sprint": "#2ca02c",
    "gc_selective": "#d62728",
    "mixed": "#9467bd",
    "unknown": "#c7c7c7",
}


def build_distribution_chart(
    data: list[dict],
    *,
    normalize: bool = False,
    title: str = "Finish Type Distribution",
) -> go.Figure:
    """Build a Plotly bar chart of finish type distribution.

    Args:
        data: List of {finish_type, count, percentage} dicts from query layer.
        normalize: If True, show percentages instead of counts.
        title: Chart title.

    Returns:
        plotly.graph_objects.Figure
    """
    ...


def build_trend_chart(
    data: list[dict],
    *,
    normalize: bool = False,
    title: str = "Finish Type Trends",
) -> go.Figure:
    """Build a Plotly stacked area chart of finish type trends over years.

    Args:
        data: List of {year, finish_type, count, percentage} dicts.
        normalize: If True, use groupnorm='percent' for 0-100% y-axis.
        title: Chart title.

    Returns:
        plotly.graph_objects.Figure with stacked areas, one per finish type.
    """
    ...
```

### Phase 7: Testing & Polish (10% of effort)

**Files:**
- `tests/test_queries.py` — New file
- `tests/conftest.py` — Extend with UI test fixtures

**Tasks:**

| Task | Description |
|------|-------------|
| 7.1 | Write `tests/test_queries.py` with seeded in-memory SQLite: test each query function with known data, including edge cases (empty DB, no classifications, single race, no dates) |
| 7.2 | Write tests for `compute_confidence_level()` boundary conditions |
| 7.3 | Write tests for badge rendering and chart builder functions |
| 7.4 | Verify all 62 existing tests still pass |
| 7.5 | Manual visual verification: screenshots of calendar, detail page, dashboard with real data |
| 7.6 | Test empty database path: app launches and shows empty states without errors |

**Key test fixtures:**
```python
# tests/conftest.py (additions)
@pytest.fixture
def seeded_session(db_session):
    """Session with sample races, results, and classifications for query testing."""
    # 5 races across 3 years, 2 states, 3 categories
    # Mix of finish types for distribution/trend testing
    ...
```

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `pyproject.toml` | Modify | Add `streamlit>=1.32`, `plotly>=5.18` to dependencies |
| `raceanalyzer/config.py` | Modify | Add `confidence_high_threshold`, `confidence_medium_threshold`, `streamlit_port` to Settings |
| `raceanalyzer/cli.py` | Modify | Add `ui` subcommand that launches Streamlit |
| `raceanalyzer/queries.py` | New | SQLAlchemy query functions for calendar, detail, distribution, trend |
| `raceanalyzer/ui/__init__.py` | New | UI package init |
| `raceanalyzer/ui/app.py` | New | Streamlit entry point: config, session init, sidebar, page routing |
| `raceanalyzer/ui/pages/__init__.py` | New | Pages package init |
| `raceanalyzer/ui/pages/calendar.py` | New | Race calendar page with filterable table |
| `raceanalyzer/ui/pages/race_detail.py` | New | Single race detail with per-category classifications |
| `raceanalyzer/ui/pages/dashboard.py` | New | Finish type distribution bar chart + stacked area trend |
| `raceanalyzer/ui/components/__init__.py` | New | Components package init |
| `raceanalyzer/ui/components/badges.py` | New | Color-coded confidence badge HTML rendering |
| `raceanalyzer/ui/components/charts.py` | New | Plotly chart builders with consistent styling |
| `raceanalyzer/ui/components/filters.py` | New | Sidebar filter widgets (year, state, category) |
| `raceanalyzer/ui/components/empty_states.py` | New | Graceful empty state messages |
| `tests/test_queries.py` | New | Unit tests for all query functions |
| `tests/conftest.py` | Modify | Add `seeded_session` fixture with sample data |

## Definition of Done

- [ ] `python -m raceanalyzer ui` launches a Streamlit app in the browser without errors
- [ ] Race calendar page displays all PNW races chronologically, filterable by year, state, and category
- [ ] Clicking a race in the calendar navigates to its detail page
- [ ] Race detail page shows finish type + color-coded confidence badge (green/yellow/red) per category
- [ ] Race detail page shows natural language qualifiers ("Likely bunch sprint") not raw decimals
- [ ] Race detail page shows group metrics (num_finishers, num_groups, largest_group_ratio, gap_to_second_group) in expandable sections
- [ ] Dashboard page shows a Plotly bar chart of finish type distribution
- [ ] Dashboard page shows a Plotly stacked area chart of finish type trends over years
- [ ] Dashboard charts respond to sidebar category/state/year filters
- [ ] Category selector in sidebar persists across page navigation
- [ ] App renders graceful empty states when database is empty or filters match no data
- [ ] All query functions have unit tests covering: normal data, empty results, single-item results, multiple years
- [ ] All 62 existing tests still pass
- [ ] `ruff check .` passes with zero errors
- [ ] Python 3.9 compatible: all new files use `from __future__ import annotations`

## Risks & Mitigations

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Streamlit version incompatibility with multipage navigation API | Medium | Medium | Use `st.radio` for page switching as a fallback if `st.navigation()` (1.36+) is unavailable. Pin minimum Streamlit version to 1.32 which supports `st.query_params`. |
| SQLAlchemy session lifecycle issues in Streamlit's rerun model | Medium | High | Initialize session once in `st.session_state` on first run. Use `@st.cache_resource` for the engine, not the session. Never pass sessions between threads. |
| `cv_of_times` thresholds for confidence badges poorly calibrated | Low | Medium | Make thresholds configurable in `Settings`. Log distribution of `cv_of_times` values across classified races to calibrate after initial deployment. Include a "Calibration" section in the dashboard showing the distribution. |
| Plotly charts slow with large datasets (thousands of races) | Low | Low | Query layer uses `limit`/`offset` for calendar. Aggregation queries (`GROUP BY`) return summary rows, not raw data. Stacked area chart operates on yearly counts (tens of rows), not individual races. |
| Category names are inconsistent across races (e.g., "Men P/1/2" vs "Men Pro/1/2") | Medium | High | Out of scope for this sprint — display raw category names as-is. Note as a Sprint 003 task to build a category normalization/alias system. The sidebar selector will show all distinct values. |
| `st.markdown(unsafe_allow_html=True)` for badges is a security concern | Low | Low | Badges are rendered from trusted internal data (enum values and computed confidence), never from user input. No XSS vector exists in a local-only tool. |
| Streamlit app does not support concurrent users well | Low | Low | This is a local analysis tool. Single-user access is the expected mode. Document this limitation. |

## Security Considerations

- **No authentication required**: This is a local analysis tool. Streamlit runs on `localhost` by default with `server.headless=true` set when launched from CLI.
- **No user input reaches the database**: All queries use SQLAlchemy ORM with parameterized queries. Sidebar filters produce constrained values (year integers, state strings from a known list, category strings from the database). No free-text SQL.
- **`unsafe_allow_html=True`**: Used only for badge rendering with internally-generated HTML. No user-supplied content is rendered as HTML.
- **Dependency security**: Streamlit and Plotly are widely-used, actively-maintained packages. Pin minimum versions to avoid known vulnerabilities.
- **Data privacy**: Same as Sprint 001 — all data is publicly available race results. The UI does not expose any data not already visible on road-results.com.

## Dependencies

### New Python Packages

| Package | Version | Purpose |
|---------|---------|---------|
| `streamlit` | >= 1.32 | Web UI framework. 1.32+ required for `st.query_params` API. |
| `plotly` | >= 5.18 | Interactive charts (bar, stacked area). Integrates natively with Streamlit via `st.plotly_chart()`. |

### Existing (unchanged)
- `sqlalchemy>=2.0` — ORM queries
- `pandas>=2.0` — DataFrame intermediary for Plotly charts
- `click>=8.0` — CLI `ui` subcommand

### Internal
- `raceanalyzer.db.models` — Race, RaceClassification, FinishType enum
- `raceanalyzer.db.engine` — `get_session()`, `get_engine()`
- `raceanalyzer.config` — Settings dataclass
- `raceanalyzer.classification.finish_type` — ClassificationResult (reference for confidence logic)

## Open Questions

1. **Query layer placement**: This draft proposes `raceanalyzer/queries.py` as a standalone module. An alternative is `raceanalyzer/ui/queries.py` inside the UI package. The standalone approach is better for testability and reuse, but adds a top-level module to a package that has so far been organized by domain (db, scraper, classification). **Recommendation**: Standalone `queries.py` — it is a cross-cutting concern, not UI-specific.

2. **Race series grouping**: The intent document asks whether "Banana Belt RR 2022" and "Banana Belt RR 2023" should be recognized as the same series. This sprint should **not** add a `series` table. The trend chart already groups by year, and the calendar shows individual race editions. Series recognition is a fuzzy-matching problem best deferred to Sprint 003 when category normalization is also addressed.

3. **Scrape trigger in UI**: The intent asks whether the UI should include a "scrape" button. **Recommendation**: No. Scraping is a long-running, network-dependent operation that does not fit Streamlit's synchronous rerun model. Keep it CLI-only. The UI should display a helpful message when data is missing.

4. **Category selector population**: Should categories be a curated list or dynamic from data? **Recommendation**: Dynamic from data via `get_distinct_categories()`. The query returns all unique `RaceClassification.category` values. A curated list would require maintenance and might miss categories present in scraped data.

5. **Minimum years for trend chart**: What threshold before showing the stacked area chart? **Recommendation**: Show it with 2+ years of data. With only 1 year, show a `st.info()` message: "Trend chart requires data from at least 2 different years." The chart is still meaningful with 2 years — it shows whether the distribution shifted.

6. **Streamlit multipage approach**: Streamlit offers multiple patterns — `st.navigation()` (1.36+), file-based pages directory, or manual radio-button routing. **Recommendation**: Use manual `st.radio` in sidebar + conditional rendering for maximum compatibility with the `>=1.32` minimum version. Upgrade to `st.navigation()` when the minimum version can be raised.

7. **Should the dashboard show overall stats or only per-category?**: **Recommendation**: Default to overall (all categories aggregated) when no category is selected in the sidebar. When a category is selected, filter to that category only. This gives the user a natural "drill-down" experience.
