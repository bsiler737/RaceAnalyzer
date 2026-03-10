# Sprint 002: Streamlit UI & Query Layer

## Overview

Build the visualization and analysis layer for RaceAnalyzer: a Streamlit-based web UI with Plotly charts that surfaces the classified race data from Sprint 001. This sprint adds a query/aggregation layer over the existing SQLAlchemy models, three Streamlit pages (race calendar, race detail, finish type dashboard), and a CLI launcher command. Users will be able to browse PNW races chronologically, inspect per-category finish type classifications with color-coded confidence badges, and explore finish type distribution trends over time.

The UI is strictly **read-only** — all scraping and classification remain CLI-only operations. This maintains a clean separation between the analytical UI and the data pipeline, and avoids the complexity of long-running background tasks in Streamlit's synchronous rerun model.

The central design decision is placing query logic in a standalone `raceanalyzer/queries.py` module that returns pandas DataFrames with zero Streamlit imports. This allows query functions to be unit-tested against in-memory SQLite, reused from notebooks or a future API layer, and consumed directly by Plotly charts without conversion overhead.

**Prerequisite**: Sprint 001 complete (scraper, DB, classifier, CLI, 62 tests passing).

---

## Use Cases

1. **Browse Race Calendar**: A user opens the app and sees all PNW races in chronological order. They can filter by year, state/province (multiselect: WA, OR, ID, BC), and race category. Each row shows race name, date, location, state, and category count.

2. **View Race Detail**: From the calendar, the user clicks a race to see all category classifications. Each category shows: finish type with a color-coded confidence badge (green/yellow/red), natural language qualifier ("Likely bunch sprint"), group metrics, and expandable results table with group structure visualization.

3. **Explore Finish Type Distribution**: The dashboard shows a pie chart of overall finish type proportions and a horizontal bar chart of finish type counts, both filtered by the sidebar category/state/year selectors.

4. **Analyze Trends Over Time**: A stacked area chart shows how finish type distributions have changed year-over-year, filtered by category. Requires at least 2 years of data.

5. **Category-Scoped Analysis**: The sidebar category selector filters all pages simultaneously. Selecting "Men Cat 1/2" constrains the calendar, detail page, and dashboard to that category's data.

6. **Empty Database Handling**: Running the app before scraping shows informative empty states: "No races found. Run `raceanalyzer scrape` to import data."

7. **Launch from CLI**: `python -m raceanalyzer ui` launches the Streamlit app. No manual `streamlit run` invocation required.

---

## Architecture

### Package Layout

```
raceanalyzer/
├── __init__.py
├── __main__.py              # CLI entry point (existing)
├── cli.py                   # Click CLI — add `ui` command (modify)
├── config.py                # Settings — add confidence thresholds (modify)
├── db/
│   ├── engine.py            # Session factory (existing, no changes)
│   └── models.py            # ORM models (existing, no changes)
├── queries.py               # NEW: Query/aggregation layer (returns DataFrames)
├── ui/
│   ├── __init__.py          # NEW: Package init
│   ├── app.py               # NEW: Streamlit multipage app setup
│   ├── pages/
│   │   ├── __init__.py
│   │   ├── calendar.py      # NEW: Race calendar page
│   │   ├── race_detail.py   # NEW: Single race detail page
│   │   └── dashboard.py     # NEW: Finish type dashboard page
│   ├── components.py        # NEW: Shared UI components (badges, sidebar, empty states)
│   └── charts.py            # NEW: Plotly chart builders
├── classification/          # (existing, no changes)
├── scraper/                 # (existing, no changes)
└── utils/                   # (existing, no changes)

tests/
├── conftest.py              # Add seeded_session fixture (modify)
├── test_queries.py          # NEW: Query layer unit tests
└── test_ui.py               # NEW: Chart builder smoke tests
```

### Data Flow

```
SQLite DB (existing)
    │
    ▼
queries.py  ←── SQLAlchemy ORM queries, returns DataFrames
    │
    ▼
ui/charts.py  ←── Plotly figure builders, consume DataFrames
    │
    ▼
ui/pages/*.py  ←── Streamlit pages, compose charts + components
    │
    ▼
ui/app.py  ←── Streamlit multipage router (st.navigation)
    │
    ▼
cli.py `ui` command  ←── `streamlit run raceanalyzer/ui/app.py`
```

### Key Design Decisions

1. **Separate `queries.py` at package root** — not inside `ui/` — for testability and reuse. Returns pandas DataFrames for direct consumption by Plotly and `st.dataframe`.
2. **`st.navigation()` / `st.Page()`** (Streamlit 1.36+) for explicit page routing control rather than the older `pages/` directory convention.
3. **Single `components.py`** — badges, filters, and empty states in one file. Split later if it grows beyond ~150 lines.
4. **Separate `charts.py`** — Plotly figure construction isolated from Streamlit layout, making charts independently testable.
5. **Configurable confidence thresholds** — `confidence_high_threshold` and `confidence_medium_threshold` in Settings dataclass, not hardcoded.
6. **DB path via environment variable** — `RACEANALYZER_DB_PATH` env var used to forward path across subprocess boundary when launching Streamlit from CLI.
7. **`@st.cache_data`** on filter-populating queries (categories, years, states) with TTL to avoid redundant queries on every Streamlit rerun.

### Confidence Badge Logic

The `cv_of_times` (coefficient of variation) stored in `RaceClassification` serves as a proxy for classification confidence. Thresholds are configurable in Settings:

| CV Range | Label | Color | Natural Language | Badge Color |
|----------|-------|-------|-----------------|-------------|
| < `confidence_high_threshold` (default 0.005) | High confidence | Green | "Likely {finish type}" | #28a745 |
| < `confidence_medium_threshold` (default 0.02) | Moderate confidence | Orange | "Probable {finish type}" | #fd7e14 |
| ≥ `confidence_medium_threshold` | Low confidence | Red | "Possible {finish type}" | #dc3545 |
| None | Unknown | Gray | "Insufficient data" | #6c757d |

### Finish Type Color Palette

Consistent across all charts:

| Finish Type | Color | Hex |
|-------------|-------|-----|
| BUNCH_SPRINT | Blue | #2196F3 |
| SMALL_GROUP_SPRINT | Light Blue | #03A9F4 |
| BREAKAWAY | Orange | #FF9800 |
| BREAKAWAY_SELECTIVE | Deep Orange | #FF5722 |
| REDUCED_SPRINT | Green | #4CAF50 |
| GC_SELECTIVE | Purple | #9C27B0 |
| MIXED | Blue Gray | #607D8B |
| UNKNOWN | Gray | #9E9E9E |

---

## Implementation

### Phase 1: Dependencies, Config & CLI Launcher (~10% of effort)

**Files:**
- `pyproject.toml` — Add `streamlit>=1.36` and `plotly>=5.18`
- `raceanalyzer/config.py` — Add confidence threshold fields to Settings
- `raceanalyzer/cli.py` — Add `ui` subcommand

**Tasks:**
- [ ] Add `streamlit>=1.36` and `plotly>=5.18` to `[project.dependencies]`
- [ ] Add `confidence_high_threshold: float = 0.005` and `confidence_medium_threshold: float = 0.02` to Settings
- [ ] Add `ui` command to CLI that launches Streamlit via `subprocess.run`, forwarding DB path via `RACEANALYZER_DB_PATH` env var

**Key signatures:**
```python
# raceanalyzer/cli.py (addition)
@main.command()
@click.option("--port", type=int, default=8501, help="Port for Streamlit server.")
@click.pass_context
def ui(ctx, port):
    """Launch the Streamlit UI."""
    import os
    import subprocess
    import sys

    app_path = Path(__file__).parent / "ui" / "app.py"
    settings = ctx.obj["settings"]

    env = os.environ.copy()
    env["RACEANALYZER_DB_PATH"] = str(settings.db_path)

    cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(app_path),
        "--server.port", str(port),
        "--server.headless", "false",
    ]
    click.echo(f"Launching RaceAnalyzer UI on port {port}...")
    subprocess.run(cmd, env=env, check=True)
```

### Phase 2: Query Layer (~25% of effort)

**Files:**
- `raceanalyzer/queries.py` — New file, all query functions

**Tasks:**
- [ ] Implement `get_races()` — paginated race listing with optional filters
- [ ] Implement `get_race_detail()` — single race with classifications and results
- [ ] Implement `get_finish_type_distribution()` — aggregated counts by finish type
- [ ] Implement `get_finish_type_trend()` — yearly finish type counts
- [ ] Implement `get_categories()`, `get_available_years()`, `get_available_states()` — filter options
- [ ] Implement `confidence_label()` using configurable thresholds from Settings
- [ ] Implement `finish_type_display_name()` using lookup dict (not string manipulation)

**Key signatures:**
```python
"""Query and aggregation layer for RaceAnalyzer.

All functions accept a SQLAlchemy Session and return pandas DataFrames.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from raceanalyzer.config import Settings
from raceanalyzer.db.models import Race, RaceClassification, Result


def get_races(
    session: Session,
    *,
    year: Optional[int] = None,
    states: Optional[list[str]] = None,
    limit: int = 500,
) -> pd.DataFrame:
    """Races ordered by date descending, with optional filters.

    Columns: id, name, date, location, state_province, num_categories.
    """
    ...


def get_race_detail(session: Session, race_id: int) -> Optional[dict]:
    """Single race with classifications and results.

    Returns:
        {
            "race": {id, name, date, location, state_province, url},
            "classifications": DataFrame[category, finish_type, confidence_label,
                                         confidence_color, qualifier, num_finishers,
                                         num_groups, largest_group_size,
                                         largest_group_ratio, leader_group_size,
                                         gap_to_second_group, cv_of_times],
            "results": DataFrame[category, place, name, team, race_time,
                                 gap_to_leader, gap_group_id, dnf],
        }
    Returns None if race not found.
    """
    ...


def get_finish_type_distribution(
    session: Session,
    *,
    category: Optional[str] = None,
    states: Optional[list[str]] = None,
    year: Optional[int] = None,
) -> pd.DataFrame:
    """Finish type counts with percentages.

    Columns: finish_type, count, percentage.
    """
    ...


def get_finish_type_trend(
    session: Session,
    *,
    category: Optional[str] = None,
    states: Optional[list[str]] = None,
) -> pd.DataFrame:
    """Yearly finish type counts for stacked area chart.

    Columns: year, finish_type, count.
    """
    ...


def get_categories(session: Session) -> list[str]:
    """All distinct category names from RaceClassification, sorted."""
    ...


def get_available_years(session: Session) -> list[int]:
    """Distinct years with race data, sorted descending."""
    ...


def get_available_states(session: Session) -> list[str]:
    """Distinct state_province values, sorted."""
    ...


def confidence_label(
    cv_of_times: Optional[float],
    settings: Optional[Settings] = None,
) -> tuple[str, str, str]:
    """Map cv_of_times to (label, color, qualifier).

    Uses thresholds from Settings (configurable).
    Returns: ("High confidence", "green", "Likely") etc.
    """
    ...


# Lookup dict for display names — handles abbreviations correctly
FINISH_TYPE_DISPLAY_NAMES = {
    "bunch_sprint": "Bunch Sprint",
    "small_group_sprint": "Small Group Sprint",
    "breakaway": "Breakaway",
    "breakaway_selective": "Breakaway Selective",
    "reduced_sprint": "Reduced Sprint",
    "gc_selective": "GC Selective",
    "mixed": "Mixed",
    "unknown": "Unknown",
}


def finish_type_display_name(finish_type_value: str) -> str:
    """Convert enum value to human-readable name via lookup dict."""
    return FINISH_TYPE_DISPLAY_NAMES.get(finish_type_value, finish_type_value.replace("_", " ").title())
```

### Phase 3: Streamlit App Shell & Components (~15% of effort)

**Files:**
- `raceanalyzer/ui/__init__.py` — Package init
- `raceanalyzer/ui/app.py` — Streamlit multipage setup
- `raceanalyzer/ui/pages/__init__.py` — Package init
- `raceanalyzer/ui/components.py` — Sidebar, badges, empty states

**Tasks:**
- [ ] Create `app.py` with `st.set_page_config`, DB session init via env var, `st.navigation()` page routing
- [ ] Implement sidebar filters: year (`st.selectbox`), states (`st.multiselect`), category (`st.selectbox`)
- [ ] Implement `render_confidence_badge()` with inline CSS
- [ ] Implement `render_empty_state()` with actionable guidance messages
- [ ] Add `@st.cache_data` to filter-populating query calls

**Key code:**
```python
# raceanalyzer/ui/app.py
from __future__ import annotations

import os

import streamlit as st

from raceanalyzer.config import Settings
from raceanalyzer.db.engine import get_session


def main():
    st.set_page_config(page_title="RaceAnalyzer", page_icon="🚴", layout="wide")

    if "db_session" not in st.session_state:
        db_path = os.environ.get("RACEANALYZER_DB_PATH", None)
        settings = Settings() if db_path is None else Settings(db_path=db_path)
        st.session_state.db_session = get_session(settings.db_path)
        st.session_state.settings = settings

    calendar_page = st.Page("pages/calendar.py", title="Race Calendar", icon="📅", default=True)
    detail_page = st.Page("pages/race_detail.py", title="Race Detail", icon="🏁")
    dashboard_page = st.Page("pages/dashboard.py", title="Finish Type Dashboard", icon="📊")

    pg = st.navigation([calendar_page, detail_page, dashboard_page])
    pg.run()


if __name__ == "__main__":
    main()
```

```python
# raceanalyzer/ui/components.py
from __future__ import annotations

from typing import Optional

import streamlit as st

from raceanalyzer import queries


def render_sidebar_filters(session) -> dict:
    """Render sidebar filters. Returns dict with year, states, category."""
    st.sidebar.title("Filters")

    years = _cached_years(session)
    states = _cached_states(session)
    categories = _cached_categories(session)

    year = st.sidebar.selectbox(
        "Year", options=[None] + years,
        format_func=lambda x: "All Years" if x is None else str(x),
    )
    selected_states = st.sidebar.multiselect(
        "State/Province", options=states, default=states,
    )
    category = st.sidebar.selectbox(
        "Category", options=[None] + categories,
        format_func=lambda x: "All Categories" if x is None else x,
    )

    return {"year": year, "states": selected_states or None, "category": category}


@st.cache_data(ttl=300)
def _cached_years(_session) -> list[int]:
    return queries.get_available_years(_session)


@st.cache_data(ttl=300)
def _cached_states(_session) -> list[str]:
    return queries.get_available_states(_session)


@st.cache_data(ttl=300)
def _cached_categories(_session) -> list[str]:
    return queries.get_categories(_session)


def render_confidence_badge(label: str, color: str):
    """Render a colored confidence badge."""
    color_map = {
        "green": "#28a745", "orange": "#fd7e14",
        "red": "#dc3545", "gray": "#6c757d",
    }
    hex_color = color_map.get(color, "#6c757d")
    st.markdown(
        f'<span style="background-color:{hex_color};color:white;padding:2px 8px;'
        f'border-radius:4px;font-size:0.85em;">{label}</span>',
        unsafe_allow_html=True,
    )


def render_empty_state(message: str = "No data available."):
    """Render a friendly empty state message."""
    st.info(message)
```

### Phase 4: UI Pages (~30% of effort)

#### Race Calendar Page (`ui/pages/calendar.py`)

**Layout:**
- Sidebar: year, states (multiselect), category filters
- Metrics row: total races, states represented, date range
- Searchable/sortable `st.dataframe` of races
- Race selection → navigate to detail page via `st.query_params`

**Tasks:**
- [ ] Call `get_races()` with sidebar filters, render as `st.dataframe`
- [ ] Show metrics row with race count, state count, date range
- [ ] Handle NULL dates gracefully (skip from date range calculation)
- [ ] Race selection + "View Details" button navigating via `st.query_params` + `st.switch_page`
- [ ] Empty state when no races match filters

#### Race Detail Page (`ui/pages/race_detail.py`)

**Layout:**
- Header: race name, date, location
- Per-category classification with confidence badge, qualifier text, group metrics
- Expandable results table per category with group structure bar chart
- Guards for nullable fields (`gap_to_second_group`, `date`, etc.)

**Tasks:**
- [ ] Read `race_id` from `st.query_params`, validate as integer
- [ ] Show race header with null-safe date/location formatting
- [ ] Render classification rows with confidence badges and natural language qualifiers
- [ ] Expandable results table per category
- [ ] Group structure bar chart per category (via `charts.py`)
- [ ] Handle missing race and missing classifications gracefully

#### Finish Type Dashboard (`ui/pages/dashboard.py`)

**Layout:**
- Row 1: Pie chart (proportions) + horizontal bar chart (counts) side by side
- Row 2: Stacked area chart of finish type trend over years
- Row 3: Summary text ("Most common finish type: Bunch Sprint (65%)")

**Tasks:**
- [ ] Pie chart via `plotly.express.pie` with finish type color palette
- [ ] Horizontal bar chart via `plotly.express.bar` with same palette
- [ ] Stacked area chart via `plotly.express.area` with `groupnorm="percent"`
- [ ] Require 2+ years for trend chart; show info message otherwise
- [ ] Summary statistics text
- [ ] All charts respect sidebar filters

### Phase 5: Plotly Chart Builders (~10% of effort)

**File:** `raceanalyzer/ui/charts.py`

**Tasks:**
- [ ] `build_distribution_pie_chart(dist_df)` — pie chart with FINISH_TYPE_COLORS palette
- [ ] `build_distribution_bar_chart(dist_df)` — horizontal bar chart, sorted by count
- [ ] `build_trend_stacked_area_chart(trend_df)` — stacked area, year on x-axis, percentage normalized
- [ ] `build_group_structure_chart(results_df)` — bar chart of group sizes, returns None if no group data
- [ ] All charts use consistent color palette and display names via lookup dict

### Phase 6: Tests (~10% of effort)

**Files:**
- `tests/conftest.py` — Add `seeded_session` fixture
- `tests/test_queries.py` — Query layer unit tests
- `tests/test_ui.py` — Chart builder smoke tests

**Tasks:**
- [ ] `seeded_session` fixture with 5 races across 3 years, 2 states, 3 categories, **multiple finish types** (BUNCH_SPRINT, BREAKAWAY, REDUCED_SPRINT)
- [ ] `test_queries.py`: ~15 tests covering get_races, get_race_detail, get_finish_type_distribution, get_finish_type_trend, get_categories, confidence_label, finish_type_display_name, plus edge cases (empty DB, nonexistent race, single year)
- [ ] `test_ui.py`: ~5 smoke tests for chart builders (pie, bar, area, group structure, null data)
- [ ] Verify all 62 existing tests still pass

---

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `pyproject.toml` | Modify | Add `streamlit>=1.36`, `plotly>=5.18` |
| `raceanalyzer/config.py` | Modify | Add `confidence_high_threshold`, `confidence_medium_threshold` to Settings |
| `raceanalyzer/cli.py` | Modify | Add `ui` command launching Streamlit with env var for DB path |
| `raceanalyzer/queries.py` | Create | Query/aggregation layer: 7 query functions + 2 helpers, returns DataFrames |
| `raceanalyzer/ui/__init__.py` | Create | Package init |
| `raceanalyzer/ui/app.py` | Create | Streamlit multipage app entry point with session management |
| `raceanalyzer/ui/pages/__init__.py` | Create | Package init |
| `raceanalyzer/ui/pages/calendar.py` | Create | Race calendar: filterable chronological race list |
| `raceanalyzer/ui/pages/race_detail.py` | Create | Race detail: per-category classifications, badges, expandable results |
| `raceanalyzer/ui/pages/dashboard.py` | Create | Dashboard: pie, bar, stacked area charts |
| `raceanalyzer/ui/components.py` | Create | Shared components: sidebar filters (with cached queries), badges, empty states |
| `raceanalyzer/ui/charts.py` | Create | Plotly chart builders: pie, bar, stacked area, group structure |
| `tests/conftest.py` | Modify | Add `seeded_session` fixture with multi-year, multi-type data |
| `tests/test_queries.py` | Create | Unit tests for all query functions (~15 tests) |
| `tests/test_ui.py` | Create | Smoke tests for chart builders (~5 tests) |

**Total new files**: 10 | **Modified files**: 4 | **Estimated new tests**: ~20

---

## Definition of Done

1. `python -m raceanalyzer ui` launches a Streamlit app on localhost:8501
2. **Race Calendar**: displays PNW races chronologically; filtering by year, states (multiselect), and category works; empty DB shows friendly message
3. **Race Detail**: shows per-category finish type with color-coded confidence badge (green/yellow/red), natural language qualifier ("Likely bunch sprint"), group metrics, expandable results table, and group structure visualization
4. **Dashboard**: pie chart of distribution, bar chart of counts, stacked area trend over years; all respect sidebar filters; minimum 2 years for trend chart
5. **Category selector** in sidebar persists across page navigation
6. **States multiselect** allows selecting multiple PNW states simultaneously
7. All query layer functions have unit tests against in-memory SQLite with seeded data (multiple finish types)
8. Chart builders have smoke tests confirming valid Plotly Figure output
9. All 62 existing tests still pass (zero regressions)
10. App handles edge cases gracefully: empty DB, races with no classifications, NULL dates, NULL gap_to_second_group, single-year data
11. Python 3.9 compatible: all new files use `from __future__ import annotations`
12. `ruff check .` and `ruff format --check .` pass with zero errors
13. Confidence thresholds are configurable in Settings (not hardcoded)

---

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Streamlit `st.navigation()` API changes | UI won't load | Low | Pin `streamlit>=1.36` which stabilized the API |
| SQLAlchemy session lifecycle in Streamlit rerun model | State loss, stale data | Medium | Initialize session once in `st.session_state`; use `@st.cache_resource` for engine; each query accepts session as argument |
| `cv_of_times` thresholds poorly calibrated for confidence badges | Misleading badges | Medium | Thresholds configurable in Settings; validate against hand-labeled sample; iterate in future sprint |
| Large datasets (10K+ races) cause slow page loads | Poor UX | Medium | `get_races()` defaults to `limit=500`; aggregation queries use GROUP BY (tens of rows); filter queries cached with `@st.cache_data` |
| Category names inconsistent across races ("Men P12" vs "Men Pro/1/2") | Fragmented filters | High | Out of scope — display raw names. Sprint 003 will add category normalization |
| `st.markdown(unsafe_allow_html=True)` for badges | XSS (theoretical) | Low | Only renders trusted internal data (enum values + computed confidence); no user-supplied content; local-only tool |
| DB path not forwarded to Streamlit subprocess | CLI `--db` flag broken | Medium | Forward via `RACEANALYZER_DB_PATH` environment variable; `app.py` reads from `os.environ` |

---

## Security Considerations

- **Local-only tool**: No authentication. Streamlit runs on localhost (default `server.address=localhost`).
- **No user input to SQL**: All queries use SQLAlchemy ORM (parameterized). Sidebar filters produce constrained values from known lists.
- **`unsafe_allow_html=True`**: Used only for badge rendering with hardcoded colors and internally-generated text. No user-supplied content injected into HTML.
- **No external network calls**: UI reads from local SQLite only. Scraping remains CLI-only.
- **DB path surface area**: Only modifiable via env var or CLI `--db` flag. Default is `data/raceanalyzer.db`.

---

## Dependencies

### New Python Packages

| Package | Version | Purpose |
|---------|---------|---------|
| `streamlit` | `>=1.36` | Web UI framework; `st.navigation()` requires 1.36+ |
| `plotly` | `>=5.18` | Interactive charts (pie, bar, stacked area); native Streamlit integration |

### Existing (unchanged)
- `sqlalchemy>=2.0` — ORM queries
- `pandas>=2.0` — DataFrame intermediary between queries and charts
- `click>=8.0` — CLI launcher
- `pytest>=7.0`, `responses>=0.23` — testing (dev)

---

## Open Questions

1. **Category normalization**: Category names vary across races. **Decision**: Defer to Sprint 003. Use raw names for now.

2. **Race series grouping**: "Banana Belt RR 2022" and "Banana Belt RR 2023" as the same series. **Decision**: Out of scope. Trend chart aggregates by year across all races. Series concept deferred.

3. **Scrape trigger from UI**: **Decision**: No. UI is read-only. Scraping stays CLI-only per interview decision.

4. **Category filter source**: **Decision**: Dynamic from `get_categories()`. Shows only categories present in the DB.

5. **Minimum data for trend chart**: **Decision**: 2 distinct years minimum. Show info message otherwise.

6. **DB path forwarding**: **Decision**: `RACEANALYZER_DB_PATH` environment variable, read in `app.py` via `os.environ.get()`.

7. **Confidence mapping**: **Decision**: Use `cv_of_times` with configurable thresholds as badge driver. Consider storing the classifier's `confidence` float in `RaceClassification` in a future sprint.
