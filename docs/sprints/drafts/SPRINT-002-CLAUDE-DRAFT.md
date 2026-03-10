# Sprint 002: Streamlit UI & Query Layer

## Overview

Build the visualization and analysis layer for RaceAnalyzer: a Streamlit-based web UI with Plotly charts that surfaces the classified race data from Sprint 001. This sprint adds a query/aggregation layer over the existing SQLAlchemy models, three Streamlit pages (race calendar, race detail, finish type dashboard), and a CLI launcher command. Users will be able to browse PNW races chronologically, inspect per-category finish type classifications with confidence badges, and explore finish type distribution trends over time.

**Duration**: ~2 weeks
**Primary deliverable**: `python -m raceanalyzer ui` launches a Streamlit app with three pages displaying race data, classifications, and trend analysis.
**Prerequisite**: Sprint 001 complete (scraper, DB, classifier, CLI, 62 tests passing).

---

## Use Cases

1. **As a race analyst**, I can run `python -m raceanalyzer ui` to launch a local Streamlit app in my browser showing all scraped PNW races.
2. **As a racer**, I can browse all PNW races organized chronologically, filtering by year, state/province, and race category to find events I'm interested in.
3. **As a racer**, I can click on any race to see the finish type classification for each category, with color-coded confidence badges (green/yellow/red) and natural language qualifiers like "Likely sprint finish."
4. **As a racer**, I can view a stacked area chart showing how finish type distributions have changed over the last 5 years, filtered by category.
5. **As a racer**, I can see overall and per-category finish type frequency breakdowns (pie/bar charts) to understand which finish types dominate in PNW racing.
6. **As a racer**, I can select a category in the sidebar (e.g., "Men Cat 1/2", "Women Cat 3") and have it persist across all pages.
7. **As a developer**, I can import and test query layer functions independently against in-memory SQLite with seeded data.

---

## Architecture

```
raceanalyzer/
├── __init__.py
├── __main__.py              # CLI entry point (existing)
├── cli.py                   # Click CLI — add `ui` command (modify)
├── config.py                # Settings (existing, no changes)
├── db/
│   ├── engine.py            # Session factory (existing, no changes)
│   └── models.py            # ORM models (existing, no changes)
├── queries.py               # NEW: Query/aggregation layer
├── ui/
│   ├── __init__.py          # NEW: Streamlit app entry point
│   ├── app.py               # NEW: Streamlit multipage app setup
│   ├── pages/
│   │   ├── __init__.py
│   │   ├── calendar.py      # NEW: Race calendar page
│   │   ├── race_detail.py   # NEW: Single race detail page
│   │   └── dashboard.py     # NEW: Finish type dashboard page
│   ├── components.py        # NEW: Shared UI components (badges, sidebar)
│   └── charts.py            # NEW: Plotly chart builders
├── classification/          # (existing, no changes)
├── scraper/                 # (existing, no changes)
└── utils/                   # (existing, no changes)

tests/
├── conftest.py              # Add query-layer seed fixtures (modify)
├── test_queries.py          # NEW: Query layer unit tests
└── test_ui.py               # NEW: Streamlit page smoke tests
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
ui/app.py  ←── Streamlit multipage router
    │
    ▼
cli.py `ui` command  ←── `streamlit run raceanalyzer/ui/app.py`
```

### Key Design Decisions

1. **Separate `queries.py` at package root** — not inside `ui/` — so query functions are reusable from notebooks, CLI, or future API layer. Returns pandas DataFrames for easy consumption by both Plotly and future ML pipelines.
2. **Streamlit native multipage app** — uses `st.navigation()` / `st.Page()` (Streamlit 1.36+) for page routing rather than the older `pages/` directory convention, giving explicit control over page order and titles.
3. **Components module** — shared widgets (confidence badge, category selector, empty state) extracted to avoid duplication across pages.
4. **Charts module** — Plotly figure construction isolated from Streamlit layout logic, making charts testable independently.

---

## Implementation

### Phase 1: Query Layer (`raceanalyzer/queries.py`)

The query layer provides all data aggregation functions consumed by the UI. Each function accepts a SQLAlchemy `Session` and filter parameters, returning a pandas `DataFrame`.

#### File: `raceanalyzer/queries.py`

```python
"""Query and aggregation layer for RaceAnalyzer.

All functions accept a SQLAlchemy Session and return pandas DataFrames.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from raceanalyzer.db.models import Race, RaceClassification, Result


def get_races(
    session: Session,
    *,
    year: Optional[int] = None,
    state: Optional[str] = None,
    limit: int = 500,
) -> pd.DataFrame:
    """Return races filtered by year and/or state, ordered by date descending.

    Columns: id, name, date, location, state_province, url,
             num_categories, num_results.
    """
    ...


def get_race_detail(
    session: Session,
    race_id: int,
) -> dict:
    """Return a single race with its classifications and result summaries.

    Returns:
        {
            "race": {id, name, date, location, state_province, url},
            "classifications": DataFrame[category, finish_type, confidence_label,
                                         confidence_color, num_finishers, num_groups,
                                         largest_group_size, largest_group_ratio,
                                         leader_group_size, gap_to_second_group,
                                         cv_of_times],
            "results": DataFrame[category, place, name, team, race_time,
                                 gap_to_leader, gap_group_id, dnf],
        }
    """
    ...


def get_categories(session: Session) -> list[str]:
    """Return all distinct category names from RaceClassification, sorted."""
    ...


def get_finish_type_distribution(
    session: Session,
    *,
    category: Optional[str] = None,
    year: Optional[int] = None,
    state: Optional[str] = None,
) -> pd.DataFrame:
    """Finish type counts, optionally filtered.

    Columns: finish_type, count, percentage.
    """
    ...


def get_finish_type_trend(
    session: Session,
    *,
    category: Optional[str] = None,
    state: Optional[str] = None,
    min_year: Optional[int] = None,
) -> pd.DataFrame:
    """Finish type counts by year for stacked area chart.

    Columns: year, finish_type, count.
    """
    ...


def get_available_years(session: Session) -> list[int]:
    """Return sorted list of distinct years that have race data."""
    ...


def get_available_states(session: Session) -> list[str]:
    """Return sorted list of distinct state_province values."""
    ...


def confidence_label(cv_of_times: Optional[float]) -> tuple[str, str]:
    """Map cv_of_times to a human-readable confidence label and color.

    Returns:
        (label, color) where:
        - label: "High confidence", "Moderate confidence", "Low confidence"
        - color: "green", "orange", "red"

    Thresholds:
        cv < 0.005  → High / green
        cv < 0.015  → Moderate / orange
        cv >= 0.015 → Low / red
        None        → "Unknown" / "gray"
    """
    ...


def finish_type_display_name(finish_type_value: str) -> str:
    """Convert finish_type enum value to human-readable display name.

    E.g., "bunch_sprint" → "Bunch Sprint",
          "gc_selective" → "GC Selective".
    """
    ...
```

#### Confidence Badge Logic

The `cv_of_times` (coefficient of variation) stored in `RaceClassification` serves as a proxy for classification confidence. Lower CV means riders finished closer together, making the finish type classification more clear-cut:

| CV Range | Label | Color | Natural Language |
|----------|-------|-------|-----------------|
| < 0.005 | High confidence | Green | "Likely {finish type}" |
| 0.005–0.015 | Moderate confidence | Orange | "Probable {finish type}" |
| ≥ 0.015 | Low confidence | Red | "Possible {finish type}" |
| None | Unknown | Gray | "Insufficient data" |

### Phase 2: Streamlit UI Pages

#### File: `raceanalyzer/ui/app.py`

Main entry point for the Streamlit app. Sets up multipage navigation and shared session state.

```python
"""RaceAnalyzer Streamlit application."""

from __future__ import annotations

import streamlit as st

from raceanalyzer.db.engine import get_session
from raceanalyzer.config import Settings


def main():
    st.set_page_config(
        page_title="RaceAnalyzer",
        page_icon="🚴",
        layout="wide",
    )

    # Initialize DB session in session_state
    if "db_session" not in st.session_state:
        settings = Settings()
        st.session_state.db_session = get_session(settings.db_path)

    # Define pages
    calendar_page = st.Page(
        "pages/calendar.py", title="Race Calendar", icon="📅", default=True
    )
    detail_page = st.Page("pages/race_detail.py", title="Race Detail", icon="🏁")
    dashboard_page = st.Page(
        "pages/dashboard.py", title="Finish Type Dashboard", icon="📊"
    )

    pg = st.navigation([calendar_page, detail_page, dashboard_page])
    pg.run()


if __name__ == "__main__":
    main()
```

#### File: `raceanalyzer/ui/components.py`

Shared UI components used across pages.

```python
"""Shared Streamlit UI components."""

from __future__ import annotations

from typing import Optional

import streamlit as st

from raceanalyzer import queries


def render_sidebar_filters(session) -> dict:
    """Render sidebar with category selector, year filter, state filter.

    Returns dict with keys: category, year, state (each Optional[str/int]).
    Persists selections in st.session_state.
    """
    st.sidebar.title("Filters")

    years = queries.get_available_years(session)
    states = queries.get_available_states(session)
    categories = queries.get_categories(session)

    year = st.sidebar.selectbox(
        "Year", options=[None] + years, format_func=lambda x: "All Years" if x is None else str(x)
    )
    state = st.sidebar.selectbox(
        "State/Province", options=[None] + states,
        format_func=lambda x: "All States" if x is None else x,
    )
    category = st.sidebar.selectbox(
        "Category", options=[None] + categories,
        format_func=lambda x: "All Categories" if x is None else x,
    )

    return {"year": year, "state": state, "category": category}


def render_confidence_badge(label: str, color: str):
    """Render a colored confidence badge using st.markdown with inline CSS."""
    color_map = {
        "green": "#28a745",
        "orange": "#fd7e14",
        "red": "#dc3545",
        "gray": "#6c757d",
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

#### File: `raceanalyzer/ui/pages/calendar.py` — Race Calendar Page

**Layout:**
- Sidebar: year, state, category filters (via `render_sidebar_filters`)
- Main area: title "PNW Race Calendar"
- Metrics row: total races count, total categories, date range
- Searchable/sortable data table (`st.dataframe`) of races with columns: Date, Name, Location, State, Categories, Finish Types
- Each race name is a clickable link that navigates to Race Detail page (via `st.query_params`)

```python
"""Race Calendar page — chronological list of all PNW races."""

from __future__ import annotations

import streamlit as st

from raceanalyzer import queries
from raceanalyzer.ui.components import render_empty_state, render_sidebar_filters


def render():
    session = st.session_state.db_session
    filters = render_sidebar_filters(session)

    st.title("PNW Race Calendar")

    df = queries.get_races(session, year=filters["year"], state=filters["state"])

    if df.empty:
        render_empty_state("No races found. Try adjusting your filters or scrape some data first.")
        return

    # Metrics row
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Races", len(df))
    col2.metric("States/Provinces", df["state_province"].nunique())
    if df["date"].notna().any():
        col3.metric("Date Range", f"{df['date'].min():%b %Y} – {df['date'].max():%b %Y}")

    # Race table with clickable links
    st.dataframe(
        df[["date", "name", "location", "state_province", "num_categories"]],
        column_config={
            "date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
            "name": "Race Name",
            "location": "Location",
            "state_province": "State",
            "num_categories": "Categories",
        },
        use_container_width=True,
        hide_index=True,
    )

    # Race selection for detail view
    race_options = dict(zip(df["name"] + " (" + df["date"].astype(str) + ")", df["id"]))
    selected = st.selectbox("Select a race for details:", options=list(race_options.keys()))
    if selected and st.button("View Race Details"):
        st.query_params["race_id"] = str(race_options[selected])
        st.switch_page("pages/race_detail.py")


render()
```

#### File: `raceanalyzer/ui/pages/race_detail.py` — Race Detail Page

**Layout:**
- Header: race name, date, location
- Per-category classification table: category name, finish type with confidence badge, group metrics
- Expandable section per category showing full results table (place, name, team, time, gap group)
- Group visualization: bar chart showing group sizes and gaps

```python
"""Race Detail page — per-category classifications and results for a single race."""

from __future__ import annotations

import streamlit as st

from raceanalyzer import queries
from raceanalyzer.ui.charts import build_group_structure_chart
from raceanalyzer.ui.components import render_confidence_badge, render_empty_state


def render():
    session = st.session_state.db_session

    race_id = st.query_params.get("race_id")
    if not race_id:
        render_empty_state("No race selected. Go to the Race Calendar to pick one.")
        return

    race_id = int(race_id)
    detail = queries.get_race_detail(session, race_id)

    if detail is None:
        render_empty_state(f"Race ID {race_id} not found.")
        return

    race = detail["race"]
    classifications = detail["classifications"]
    results = detail["results"]

    # Header
    st.title(race["name"])
    col1, col2 = st.columns(2)
    col1.write(f"**Date:** {race['date']:%B %d, %Y}" if race["date"] else "**Date:** Unknown")
    col2.write(f"**Location:** {race['location'] or 'Unknown'}, {race['state_province'] or ''}")

    st.divider()

    if classifications.empty:
        render_empty_state("No classifications available for this race. Run `classify` first.")
        return

    # Classifications table
    st.subheader("Finish Type Classifications")
    for _, row in classifications.iterrows():
        with st.container():
            cols = st.columns([2, 2, 1, 1, 1, 1])
            cols[0].write(f"**{row['category']}**")
            display_name = queries.finish_type_display_name(row["finish_type"])
            qualifier = _qualifier(row["confidence_label"])
            cols[1].write(f"{qualifier} {display_name}")
            render_confidence_badge(row["confidence_label"], row["confidence_color"])
            cols[3].write(f"{row['num_finishers']} finishers")
            cols[4].write(f"{row['num_groups']} groups")
            cols[5].write(f"{row['gap_to_second_group']:.1f}s gap")

            # Expandable results
            cat_results = results[results["category"] == row["category"]]
            if not cat_results.empty:
                with st.expander(f"View {len(cat_results)} results"):
                    st.dataframe(
                        cat_results[["place", "name", "team", "race_time",
                                     "gap_to_leader", "gap_group_id"]],
                        use_container_width=True,
                        hide_index=True,
                    )
                    fig = build_group_structure_chart(cat_results)
                    if fig:
                        st.plotly_chart(fig, use_container_width=True)


def _qualifier(confidence_label: str) -> str:
    """Map confidence label to natural language qualifier."""
    return {
        "High confidence": "Likely",
        "Moderate confidence": "Probable",
        "Low confidence": "Possible",
    }.get(confidence_label, "")


render()
```

#### File: `raceanalyzer/ui/pages/dashboard.py` — Finish Type Dashboard

**Layout:**
- Sidebar: shared category/year/state filters
- Row 1: Finish type distribution pie chart (overall) + bar chart (per-category)
- Row 2: Stacked area chart of finish type trend over years
- Row 3: Summary statistics table

```python
"""Finish Type Dashboard — distribution charts and trend analysis."""

from __future__ import annotations

import streamlit as st

from raceanalyzer import queries
from raceanalyzer.ui.charts import (
    build_distribution_bar_chart,
    build_distribution_pie_chart,
    build_trend_stacked_area_chart,
)
from raceanalyzer.ui.components import render_empty_state, render_sidebar_filters


def render():
    session = st.session_state.db_session
    filters = render_sidebar_filters(session)

    st.title("Finish Type Dashboard")

    # Distribution
    dist_df = queries.get_finish_type_distribution(
        session, category=filters["category"], year=filters["year"], state=filters["state"]
    )

    if dist_df.empty:
        render_empty_state("No classification data available. Scrape and classify races first.")
        return

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Overall Distribution")
        fig_pie = build_distribution_pie_chart(dist_df)
        st.plotly_chart(fig_pie, use_container_width=True)
    with col2:
        st.subheader("By Count")
        fig_bar = build_distribution_bar_chart(dist_df)
        st.plotly_chart(fig_bar, use_container_width=True)

    st.divider()

    # Trend
    st.subheader("Finish Type Trend Over Time")
    trend_df = queries.get_finish_type_trend(
        session, category=filters["category"], state=filters["state"]
    )

    if trend_df.empty or trend_df["year"].nunique() < 2:
        render_empty_state("Need at least 2 years of data to show trends.")
    else:
        fig_trend = build_trend_stacked_area_chart(trend_df)
        st.plotly_chart(fig_trend, use_container_width=True)

    # Summary stats
    st.subheader("Summary")
    most_common = dist_df.loc[dist_df["count"].idxmax()]
    st.write(
        f"Most common finish type: **{queries.finish_type_display_name(most_common['finish_type'])}** "
        f"({most_common['percentage']:.1f}% of classified races)"
    )


render()
```

### Phase 3: Plotly Chart Builders (`raceanalyzer/ui/charts.py`)

```python
"""Plotly chart builders for RaceAnalyzer UI."""

from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from raceanalyzer.queries import finish_type_display_name

# Consistent color palette for finish types
FINISH_TYPE_COLORS = {
    "bunch_sprint": "#2196F3",        # Blue
    "small_group_sprint": "#03A9F4",  # Light Blue
    "breakaway": "#FF9800",           # Orange
    "breakaway_selective": "#FF5722", # Deep Orange
    "reduced_sprint": "#4CAF50",      # Green
    "gc_selective": "#9C27B0",        # Purple
    "mixed": "#607D8B",              # Blue Gray
    "unknown": "#9E9E9E",           # Gray
}


def build_distribution_pie_chart(dist_df: pd.DataFrame) -> go.Figure:
    """Pie chart of finish type distribution.

    Args:
        dist_df: DataFrame with columns [finish_type, count, percentage].
    """
    df = dist_df.copy()
    df["display_name"] = df["finish_type"].apply(finish_type_display_name)
    fig = px.pie(
        df,
        values="count",
        names="display_name",
        color="finish_type",
        color_discrete_map=FINISH_TYPE_COLORS,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(showlegend=False, margin=dict(t=20, b=20, l=20, r=20))
    return fig


def build_distribution_bar_chart(dist_df: pd.DataFrame) -> go.Figure:
    """Horizontal bar chart of finish type counts.

    Args:
        dist_df: DataFrame with columns [finish_type, count, percentage].
    """
    df = dist_df.copy().sort_values("count", ascending=True)
    df["display_name"] = df["finish_type"].apply(finish_type_display_name)
    fig = px.bar(
        df,
        x="count",
        y="display_name",
        orientation="h",
        color="finish_type",
        color_discrete_map=FINISH_TYPE_COLORS,
    )
    fig.update_layout(
        showlegend=False,
        yaxis_title="",
        xaxis_title="Count",
        margin=dict(t=20, b=40, l=20, r=20),
    )
    return fig


def build_trend_stacked_area_chart(trend_df: pd.DataFrame) -> go.Figure:
    """Stacked area chart of finish types over years.

    Args:
        trend_df: DataFrame with columns [year, finish_type, count].
    """
    df = trend_df.copy()
    df["display_name"] = df["finish_type"].apply(finish_type_display_name)

    fig = px.area(
        df,
        x="year",
        y="count",
        color="display_name",
        color_discrete_map={
            finish_type_display_name(k): v for k, v in FINISH_TYPE_COLORS.items()
        },
        groupnorm="percent",
    )
    fig.update_layout(
        yaxis_title="Percentage",
        xaxis_title="Year",
        legend_title="Finish Type",
        margin=dict(t=20, b=40, l=60, r=20),
    )
    fig.update_xaxes(dtick=1)
    return fig


def build_group_structure_chart(results_df: pd.DataFrame) -> Optional[go.Figure]:
    """Bar chart showing group sizes for a single race category.

    Args:
        results_df: DataFrame with columns including gap_group_id.

    Returns:
        Plotly figure or None if no group data.
    """
    if "gap_group_id" not in results_df.columns or results_df["gap_group_id"].isna().all():
        return None

    group_counts = (
        results_df.groupby("gap_group_id")
        .size()
        .reset_index(name="riders")
    )
    group_counts["group_label"] = "Group " + group_counts["gap_group_id"].astype(int).astype(str)

    fig = px.bar(
        group_counts,
        x="group_label",
        y="riders",
        color="riders",
        color_continuous_scale="Blues",
    )
    fig.update_layout(
        xaxis_title="Gap Group",
        yaxis_title="Riders",
        showlegend=False,
        margin=dict(t=20, b=40, l=40, r=20),
    )
    return fig
```

### Phase 4: CLI Integration & Dependencies

#### File: `raceanalyzer/cli.py` — Add `ui` command

Add the following command to the existing Click group:

```python
@main.command()
@click.option("--port", type=int, default=8501, help="Port for Streamlit server.")
@click.pass_context
def ui(ctx, port):
    """Launch the Streamlit UI."""
    import subprocess
    import sys

    app_path = Path(__file__).parent / "ui" / "app.py"
    settings = ctx.obj["settings"]

    cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(app_path),
        "--server.port", str(port),
        "--server.headless", "false",
        "--", "--db", str(settings.db_path),
    ]
    click.echo(f"Launching RaceAnalyzer UI on port {port}...")
    subprocess.run(cmd, check=True)
```

#### File: `pyproject.toml` — Add dependencies

Add to `dependencies`:
```toml
dependencies = [
    "sqlalchemy>=2.0",
    "requests>=2.31",
    "requests-futures>=1.0",
    "pandas>=2.0",
    "click>=8.0",
    "streamlit>=1.36",
    "plotly>=5.18",
]
```

### Phase 5: Tests

#### File: `tests/conftest.py` — Add seed data fixture

```python
@pytest.fixture
def seeded_session(session):
    """Session pre-populated with sample races, results, and classifications."""
    from datetime import datetime
    from raceanalyzer.db.models import (
        Race, Result, RaceClassification, FinishType, Rider
    )

    races = [
        Race(id=1, name="Banana Belt RR", date=datetime(2023, 3, 5),
             location="Maryhill", state_province="WA"),
        Race(id=2, name="Cherry Pie Crit", date=datetime(2023, 2, 19),
             location="Niles", state_province="OR"),
        Race(id=3, name="Banana Belt RR", date=datetime(2024, 3, 3),
             location="Maryhill", state_province="WA"),
    ]
    session.add_all(races)

    # Add results and classifications for each race
    for race in races:
        for cat in ["Men Cat 1/2", "Men Cat 3", "Women Cat 1/2/3"]:
            for i in range(10):
                session.add(Result(
                    race_id=race.id, name=f"Rider {i}", place=i + 1,
                    race_category_name=cat,
                    race_time_seconds=3600.0 + i * 2.0,
                    field_size=10, dnf=False,
                ))
            session.add(RaceClassification(
                race_id=race.id, category=cat,
                finish_type=FinishType.BUNCH_SPRINT,
                num_finishers=10, num_groups=1,
                largest_group_size=10, largest_group_ratio=1.0,
                leader_group_size=10, gap_to_second_group=0.0,
                cv_of_times=0.003,
            ))

    session.commit()
    return session
```

#### File: `tests/test_queries.py`

```python
"""Tests for the query/aggregation layer."""

from __future__ import annotations

from raceanalyzer import queries


class TestGetRaces:
    def test_returns_all_races(self, seeded_session):
        df = queries.get_races(seeded_session)
        assert len(df) == 3

    def test_filter_by_year(self, seeded_session):
        df = queries.get_races(seeded_session, year=2023)
        assert len(df) == 2

    def test_filter_by_state(self, seeded_session):
        df = queries.get_races(seeded_session, state="OR")
        assert len(df) == 1

    def test_empty_db(self, session):
        df = queries.get_races(session)
        assert df.empty


class TestGetRaceDetail:
    def test_returns_detail(self, seeded_session):
        detail = queries.get_race_detail(seeded_session, 1)
        assert detail is not None
        assert detail["race"]["name"] == "Banana Belt RR"
        assert len(detail["classifications"]) == 3

    def test_nonexistent_race(self, seeded_session):
        detail = queries.get_race_detail(seeded_session, 999)
        assert detail is None


class TestGetFinishTypeDistribution:
    def test_overall_distribution(self, seeded_session):
        df = queries.get_finish_type_distribution(seeded_session)
        assert not df.empty
        assert "finish_type" in df.columns
        assert "count" in df.columns
        assert "percentage" in df.columns

    def test_filtered_by_category(self, seeded_session):
        df = queries.get_finish_type_distribution(
            seeded_session, category="Men Cat 1/2"
        )
        assert not df.empty


class TestGetFinishTypeTrend:
    def test_trend_has_multiple_years(self, seeded_session):
        df = queries.get_finish_type_trend(seeded_session)
        assert df["year"].nunique() == 2  # 2023 and 2024

    def test_empty_db(self, session):
        df = queries.get_finish_type_trend(session)
        assert df.empty


class TestGetCategories:
    def test_returns_categories(self, seeded_session):
        cats = queries.get_categories(seeded_session)
        assert "Men Cat 1/2" in cats
        assert len(cats) == 3


class TestConfidenceLabel:
    def test_high_confidence(self):
        label, color = queries.confidence_label(0.003)
        assert label == "High confidence"
        assert color == "green"

    def test_moderate_confidence(self):
        label, color = queries.confidence_label(0.01)
        assert label == "Moderate confidence"
        assert color == "orange"

    def test_low_confidence(self):
        label, color = queries.confidence_label(0.02)
        assert label == "Low confidence"
        assert color == "red"

    def test_none(self):
        label, color = queries.confidence_label(None)
        assert color == "gray"


class TestFinishTypeDisplayName:
    def test_conversion(self):
        assert queries.finish_type_display_name("bunch_sprint") == "Bunch Sprint"
        assert queries.finish_type_display_name("gc_selective") == "GC Selective"
```

#### File: `tests/test_ui.py`

Smoke tests verifying Streamlit pages can be imported and chart builders produce valid Plotly figures.

```python
"""Smoke tests for UI components and chart builders."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from raceanalyzer.ui.charts import (
    build_distribution_bar_chart,
    build_distribution_pie_chart,
    build_group_structure_chart,
    build_trend_stacked_area_chart,
)


class TestChartBuilders:
    def test_pie_chart(self):
        df = pd.DataFrame({
            "finish_type": ["bunch_sprint", "breakaway"],
            "count": [10, 5],
            "percentage": [66.7, 33.3],
        })
        fig = build_distribution_pie_chart(df)
        assert isinstance(fig, go.Figure)

    def test_bar_chart(self):
        df = pd.DataFrame({
            "finish_type": ["bunch_sprint", "breakaway"],
            "count": [10, 5],
            "percentage": [66.7, 33.3],
        })
        fig = build_distribution_bar_chart(df)
        assert isinstance(fig, go.Figure)

    def test_stacked_area_chart(self):
        df = pd.DataFrame({
            "year": [2022, 2022, 2023, 2023],
            "finish_type": ["bunch_sprint", "breakaway", "bunch_sprint", "breakaway"],
            "count": [10, 5, 12, 8],
        })
        fig = build_trend_stacked_area_chart(df)
        assert isinstance(fig, go.Figure)

    def test_group_structure_chart(self):
        df = pd.DataFrame({
            "gap_group_id": [1, 1, 1, 2, 2],
            "place": [1, 2, 3, 4, 5],
        })
        fig = build_group_structure_chart(df)
        assert isinstance(fig, go.Figure)

    def test_group_structure_chart_no_data(self):
        df = pd.DataFrame({"gap_group_id": [None, None], "place": [1, 2]})
        fig = build_group_structure_chart(df)
        assert fig is None
```

---

## Files Summary

| File | Action | Description |
|------|--------|-------------|
| `raceanalyzer/queries.py` | **Create** | Query/aggregation layer: 8 functions returning DataFrames + 2 helper functions |
| `raceanalyzer/ui/__init__.py` | **Create** | Package init (empty) |
| `raceanalyzer/ui/app.py` | **Create** | Streamlit multipage app entry point with session management |
| `raceanalyzer/ui/pages/__init__.py` | **Create** | Package init (empty) |
| `raceanalyzer/ui/pages/calendar.py` | **Create** | Race calendar page: filterable chronological race list |
| `raceanalyzer/ui/pages/race_detail.py` | **Create** | Race detail page: per-category classifications with badges, expandable results |
| `raceanalyzer/ui/pages/dashboard.py` | **Create** | Finish type dashboard: pie chart, bar chart, stacked area trend |
| `raceanalyzer/ui/components.py` | **Create** | Shared components: sidebar filters, confidence badge, empty state |
| `raceanalyzer/ui/charts.py` | **Create** | Plotly chart builders: pie, bar, stacked area, group structure |
| `raceanalyzer/cli.py` | **Modify** | Add `ui` command to launch Streamlit |
| `pyproject.toml` | **Modify** | Add `streamlit>=1.36` and `plotly>=5.18` dependencies |
| `tests/conftest.py` | **Modify** | Add `seeded_session` fixture with sample races/results/classifications |
| `tests/test_queries.py` | **Create** | Unit tests for all query layer functions (~15 tests) |
| `tests/test_ui.py` | **Create** | Smoke tests for chart builders (~5 tests) |

**Total new files**: 10
**Total modified files**: 4
**Estimated new test count**: ~20

---

## Definition of Done

1. `python -m raceanalyzer ui` launches a Streamlit app on localhost:8501
2. **Race Calendar page**: displays all PNW races chronologically; filtering by year, state, and category works; empty DB shows a friendly message
3. **Race Detail page**: shows per-category finish type with color-coded confidence badge (green/yellow/red), natural language qualifier ("Likely sprint finish"), group metrics, and expandable results table
4. **Finish Type Dashboard**: pie chart of overall distribution, bar chart of counts, stacked area trend chart over years; all respect sidebar filters
5. **Category selector** in sidebar persists across page navigation via `st.session_state`
6. All query layer functions have unit tests against in-memory SQLite with seeded data
7. Chart builders have smoke tests confirming valid Plotly Figure output
8. All 62 existing tests still pass (zero regressions)
9. App handles edge cases gracefully: empty DB, races with no classifications, single-year data (trend chart shows message instead of error)
10. Python 3.9 compatible: all new files use `from __future__ import annotations`
11. Code passes `ruff` linting (line length 100, py39 target)

---

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Streamlit `st.navigation` API changed in recent versions | UI won't load | Low | Pin `streamlit>=1.36` which stabilized the API; fall back to `pages/` directory convention if needed |
| Large datasets (10K+ races) cause slow page loads | Poor UX | Medium | `get_races()` defaults to `limit=500`; add pagination in a future sprint; query layer uses indexed columns (date, state_province) |
| Confidence thresholds (CV ranges) don't map well to actual classification quality | Misleading badges | Medium | Thresholds are configurable in `confidence_label()`; validate against hand-labeled sample; iterate in future sprint |
| Streamlit session management across pages is fragile | State loss, DB connection issues | Low | Use `st.session_state` for DB session; initialize once in `app.py`; each query function accepts session as argument (no global state) |
| Category names are inconsistent across races ("Men P12" vs "Men Pro/1/2") | Fragmented filters | High | Out of scope for this sprint; note as open question for Sprint 003 category normalization |
| `python -m raceanalyzer ui` fails because Streamlit expects to be launched via `streamlit run` | CLI doesn't work | Low | `ui` command uses `subprocess.run` to invoke `streamlit run` properly, passing DB path as CLI arg |

---

## Security Considerations

- **Local-only tool**: No authentication required. Streamlit runs on localhost only (default `server.address=localhost`).
- **No user input to SQL**: All queries use SQLAlchemy ORM (parameterized queries). No raw SQL strings constructed from user input.
- **`unsafe_allow_html`**: Used only for confidence badge rendering with hardcoded color values — no user-supplied content is injected into HTML.
- **No external network calls**: UI reads from local SQLite only. Scraping remains CLI-only.
- **File paths**: DB path comes from `Settings` dataclass with a hardcoded default. The `--db` CLI flag is the only way to change it.

---

## Dependencies

### New Python Packages

| Package | Version | Purpose |
|---------|---------|---------|
| `streamlit` | `>=1.36` | Web UI framework; multipage app API requires 1.36+ |
| `plotly` | `>=5.18` | Interactive charts (pie, bar, area); Streamlit has built-in Plotly support |

### Existing Packages (no changes)

- `sqlalchemy>=2.0` — ORM queries
- `pandas>=2.0` — DataFrame intermediary between queries and charts
- `click>=8.0` — CLI launcher
- `pytest>=7.0` — testing

### No New System Dependencies

Streamlit and Plotly are pure Python. No Node.js, npm, or system-level packages required.

---

## Open Questions

1. **Category normalization**: Category names vary across races (e.g., "Men P12", "Men Pro/1/2", "Cat 1/2 Men"). Should this sprint include basic normalization, or defer to Sprint 003? **Recommendation**: Defer — use raw category names for now, note it as tech debt.

2. **Race series grouping**: The intent mentions grouping races across years (e.g., "Banana Belt RR 2022" and "Banana Belt RR 2023"). This requires a `series` concept or fuzzy name matching. **Recommendation**: Out of scope for Sprint 002. The trend chart aggregates by year across all races, not per-series.

3. **Scrape trigger from UI**: Should the dashboard include a "Scrape" button? **Recommendation**: No — keep scraping CLI-only for now. Adding a scrape trigger introduces long-running background tasks and progress tracking complexity.

4. **Category filter source**: Should the sidebar category list be dynamic (from data) or curated? **Recommendation**: Dynamic from `get_categories()` — shows only categories that exist in the DB. No hardcoded list.

5. **Minimum data for trend chart**: The intent asks about minimum years. **Recommendation**: Require at least 2 distinct years to show the stacked area chart; otherwise show an info message. This is implemented in the dashboard page.

6. **DB path passing to Streamlit**: Streamlit runs as a subprocess, so the `--db` path from the CLI needs to be forwarded. **Recommendation**: Pass via Streamlit CLI args (`--` separator) and parse in `app.py` using `sys.argv` or `st.query_params`. Alternative: use an environment variable `RACEANALYZER_DB_PATH`.

7. **Confidence mapping**: The intent says "color-coded confidence badges" but the DB stores `cv_of_times`, not a pre-computed confidence score. The `classify_finish_type` function returns a `confidence` float (0.5–1.0) but this isn't stored in `RaceClassification`. **Recommendation**: Use `cv_of_times` as the badge driver for Sprint 002 since it's already in the DB. Consider adding a `confidence` column to `RaceClassification` in a future sprint.
