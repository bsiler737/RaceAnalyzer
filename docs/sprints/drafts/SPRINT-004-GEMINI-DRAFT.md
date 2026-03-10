# Sprint 004 Draft: Race Tiles UI + Scary Racers

## Overview

This sprint overhauls the user experience by transforming the main calendar page from a text-based table into a visually rich, 3-wide grid of race "tiles." Each tile will provide an at-a-glance summary of a race, including its name, date, location, a distinctive icon for its type (e.g., Criterium, Road Race), and a mini-map of the course. Clicking a tile will navigate to the enhanced race detail page.

The race detail page will introduce a "Scary Racers" section. This feature analyzes historical rider performance to predict top contenders for each category, adding a fun and engaging analytical layer. The ranking algorithm will weigh wins and podiums, with bonuses for riders who excel at similar race types.

To support these features, this sprint involves schema changes to the `Race` model, significant extensions to the demo data generator, new backend queries, and a substantial rewrite of the UI pages for the calendar and race details.

## Use Cases

1.  **As a user, I want to see a visual overview of upcoming races** so I can quickly assess the race landscape without reading a dense table.
2.  **As a user, I want to understand a race's character at a glance** by seeing its type (crit, road race) and course shape directly on the calendar page.
3.  **As a user, I want to navigate to a race's details** by clicking on its tile.
4.  **As a user, when viewing a race's details, I want to see a list of predicted top performers ("Scary Racers") for my category** so I know who to watch out for.
5.  **As a developer, I want the demo data to include course geometry and rider history** so I can test the new UI and prediction features thoroughly.
6.  **As a developer, I want the database schema to store race type and course data** to support the new features in a robust way.

## Architecture

This sprint touches four main architectural layers:

1.  **Database Schema (`raceanalyzer/db/models.py`)**:
    *   The `Race` table will be extended with three new columns:
        *   `race_type: Enum`: To store the type of race (e.g., `criterium`, `road_race`). An `Enum` provides type safety and clarity.
        *   `course_polyline: Text`: To store an encoded polyline string representing the race course. This is more efficient for storage and transfer than a full list of coordinates.
        *   `course_centroid_lat: Float`, `course_centroid_lon: Float`: To store the central point of the course for quick map centering.

2.  **Demo Data Generation (`raceanalyzer/demo.py`)**:
    *   The data generator will be updated to populate the new schema fields.
    *   It will assign a `race_type` to each generated race, likely based on keywords in the race name (e.g., "Criterium" -> `criterium`).
    *   It will generate plausible PNW course polylines. This will be achieved by defining several bounding boxes around key PNW cycling locations (e.g., Seward Park, Maryhill) and generating random-walk polylines within them.
    *   It will generate cross-race performance history for riders, ensuring some riders accumulate wins and podiums across different race types to make the "Scary Racers" feature meaningful.

3.  **Query Layer (`raceanalyzer/queries.py`)**:
    *   A new function, `get_races_for_tiles()`, will be created to fetch all data needed for the calendar grid in a single query. It will return race ID, name, date, location, race type, and the course polyline.
    *   A new function, `get_scary_racers(race_id, category)`, will be implemented. This query will:
        1.  Fetch the `race_type` of the given `race_id`.
        2.  Find all riders registered for the given `category`.
        3.  For each rider, query their entire result history from the `results` table.
        4.  Calculate a "scary score" based on a formula: `(wins * 3) + (podiums * 1)`. A `race_type_bonus` of `* 1.5` will be applied to the score if a win/podium was in a race of the same type.
        5.  Return a ranked list of riders as a pandas DataFrame.

4.  **UI Layer (`raceanalyzer/ui/`)**:
    *   **`pages/calendar.py`**: The main `render()` function will be rewritten. It will call `queries.get_races_for_tiles()` and then iterate over the results, using `st.columns(3)` to create the tile grid. Each tile's rendering will be delegated to a new component.
    *   **`components.py`**:
        *   A new `render_race_tile(race)` function will be created. This component will be responsible for the layout of a single tile within an `st.container`. It will display the race name, date, location, and call the icon and map components.
        *   A new `render_race_type_icon(race_type)` function will generate and display an icon. It will contain a dictionary mapping `race_type` enums to inline SVG strings.
    *   **`charts.py`**:
        *   A new `build_course_map_thumbnail(polyline)` function will be created. It will take an encoded polyline, decode it into lat/lon coordinates, and use Plotly's `scatter_mapbox` to generate a static map image. The layout will be minimal (no controls, no legends) and use an open-source map style (e.g., "open-street-map") to avoid needing a Mapbox token.
    *   **`pages/race_detail.py`**:
        *   A new section will be added to the `render()` function. For each category in the race, it will call `queries.get_scary_racers()` and display the top 5 riders in a clean table or list format.

## Implementation

Key code implementations are provided below.

### 1. Database Model (`raceanalyzer/db/models.py`)

A new `RaceType` enum is defined, and the `Race` model is updated.

```python
# In raceanalyzer/db/models.py

import enum
# ... other imports

class RaceType(enum.Enum):
    CRITERIUM = "criterium"
    ROAD_RACE = "road_race"
    HILL_CLIMB = "hill_climb"
    STAGE_RACE = "stage_race"
    TIME_TRIAL = "time_trial"
    GRAVEL = "gravel"
    UNKNOWN = "unknown"

class Race(Base):
    """A race event on a specific date."""

    __tablename__ = "races"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    date = Column(DateTime, nullable=True)
    location = Column(String, nullable=True)
    state_province = Column(String, nullable=True)
    url = Column(String, nullable=True)

    # --- NEW COLUMNS ---
    race_type = Column(SAEnum(RaceType), nullable=False, default=RaceType.UNKNOWN)
    course_polyline = Column(Text, nullable=True)
    course_centroid_lat = Column(Float, nullable=True)
    course_centroid_lon = Column(Float, nullable=True)
    # --- END NEW COLUMNS ---


    results = relationship("Result", back_populates="race", cascade="all, delete-orphan")
    classifications = relationship(
        "RaceClassification", back_populates="race", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_races_date", "date"),
        Index("ix_races_state", "state_province"),
        Index("ix_races_race_type", "race_type"), # Index new column
    )
```

### 2. "Scary Racers" Query (`raceanalyzer/queries.py`)

A new query to calculate rider scores based on historical performance.

```python
# In raceanalyzer/queries.py
# ... other imports
from raceanalyzer.db.models import Race, Result, Rider, RaceType

def get_scary_racers(session: Session, race_id: int, category: str) -> pd.DataFrame:
    """
    Identifies top-performing riders for a given race category based on
    historical results, weighted by wins, podiums, and race type similarity.
    """
    target_race = session.query(Race.race_type).filter(Race.id == race_id).scalar()
    if not target_race:
        return pd.DataFrame()

    # Get riders in the specified category for the given race
    riders_in_category_query = (
        session.query(Result.rider_id)
        .filter(Result.race_id == race_id)
        .filter(Result.race_category_name == category)
        .distinct()
    )
    rider_ids = [r[0] for r in riders_in_category_query.all() if r[0] is not None]

    if not rider_ids:
        return pd.DataFrame()

    # Get all historical results for these riders
    history = session.query(
        Result.rider_id,
        Result.place,
        Race.race_type
    ).join(Race, Result.race_id == Race.id).filter(Result.rider_id.in_(rider_ids)).all()

    if not history:
        return pd.DataFrame()

    rider_names = {
        r.id: r.name for r in session.query(Rider).filter(Rider.id.in_(rider_ids))
    }

    scores = {rider_id: 0 for rider_id in rider_ids}
    for rider_id, place, race_type in history:
        score = 0
        if place == 1:
            score = 3  # Win
        elif place in [2, 3]:
            score = 1  # Podium

        if score > 0:
            # Apply bonus for same race type
            if race_type == target_race:
                score *= 1.5
            scores[rider_id] += score

    ranked_riders = sorted(scores.items(), key=lambda item: item[1], reverse=True)

    scary_racers_data = []
    for rider_id, score in ranked_riders:
        if score > 0:
            scary_racers_data.append({
                "name": rider_names.get(rider_id, "Unknown Rider"),
                "score": score
            })

    return pd.DataFrame(scary_racers_data).head(5)

```

### 3. Tile Rendering (`raceanalyzer/ui/pages/calendar.py`)

The calendar page is refactored to use a tile grid.

```python
# In raceanalyzer/ui/pages/calendar.py

from __future__ import annotations
import streamlit as st
from raceanalyzer import queries
from raceanalyzer.ui.components import (
    render_empty_state,
    render_sidebar_filters,
    render_race_tile, # New component
)

def render():
    session = st.session_state.db_session
    filters = render_sidebar_filters(session)

    st.title("PNW Race Calendar")

    # This query will need to be created to fetch tile-specific data
    df_races = queries.get_races_for_tiles(
        session, year=filters["year"], states=filters["states"]
    )

    if df_races.empty:
        render_empty_state("No races found. Try adjusting filters.")
        return

    # Create a 3-column grid
    cols = st.columns(3)
    for i, row in enumerate(df_races.itertuples()):
        with cols[i % 3]:
            render_race_tile(row)

render()
```

### 4. Race Tile Component (`raceanalyzer/ui/components.py`)

A new component to render a single race tile, including the icon and map.

```python
# In raceanalyzer/ui/components.py
# ... other imports
from raceanalyzer.ui.charts import build_course_map_thumbnail

def render_race_tile(race):
    """Renders a single race tile in a container."""
    with st.container(border=True):
        st.subheader(race.name)

        meta_cols = st.columns([1, 4])
        with meta_cols[0]:
            render_race_type_icon(race.race_type)
        with meta_cols[1]:
            st.caption(f"{race.date:%B %d, %Y}")
            st.caption(f"{race.location}, {race.state_province}")

        if race.course_polyline:
            fig = build_course_map_thumbnail(race.course_polyline)
            st.plotly_chart(fig, use_container_width=True, config={'staticPlot': True})
        else:
            st.text("Map not available")

        # Make the tile clickable
        if st.button("View Details", key=f"details_{race.id}"):
            st.session_state["selected_race_id"] = race.id
            st.query_params["race_id"] = str(race.id)
            st.switch_page("pages/race_detail.py")

def render_race_type_icon(race_type: str):
    """Displays a race type icon using inline SVG."""
    icons = {
        "criterium": "...", # SVG for criterium
        "road_race": "...", # SVG for road race
        # ... other icons
    }
    icon_svg = icons.get(race_type.value if hasattr(race_type, 'value') else race_type, "")
    if icon_svg:
        st.markdown(f'<div title="{race_type.name}">{icon_svg}</div>', unsafe_allow_html=True)

```

## Files Summary

*   **Modified:**
    *   `raceanalyzer/db/models.py`: Added `race_type`, `course_polyline`, and centroid columns to `Race` model.
    *   `raceanalyzer/demo.py`: Extended to generate race types, course polylines, and rider performance history.
    *   `raceanalyzer/queries.py`: Added `get_races_for_tiles()` and `get_scary_racers()`.
    *   `raceanalyzer/ui/pages/calendar.py`: Rewritten to use a 3-column tile grid.
    *   `raceanalyzer/ui/pages/race_detail.py`: Modified to add a "Scary Racers" section for each category.
    *   `raceanalyzer/ui/components.py`: Added `render_race_tile()` and `render_race_type_icon()`.
    *   `raceanalyzer/ui/charts.py`: Added `build_course_map_thumbnail()`.
*   **New:**
    *   *None*
*   **Tests:**
    *   `tests/test_queries.py`: New tests for `get_scary_racers()` logic.
    *   `tests/test_demo.py`: New tests to verify that the extended demo data is generated correctly.

## Definition of Done

1.  The main calendar page displays a 3-wide grid of race tiles.
2.  Each tile correctly shows the race name, date, location, a race type icon, and a course map thumbnail.
3.  Clicking the "View Details" button on a tile navigates to the correct race detail page.
4.  The race detail page features a "Scary Racers" section under each category, listing the top 5 predicted performers based on the new scoring logic.
5.  The database schema is updated with the new `Race` fields.
6.  The `seed-demo` command successfully generates data for the new fields, including plausible course maps and varied rider histories.
7.  New unit tests for the `get_scary_racers` query pass.
8.  All 119 existing tests continue to pass.
9.  The UI is visually clean and responsive.

## Risks

*   **Medium:** Rendering many Plotly maps on the calendar page could be slow. Mitigation: Use `st.cache_data` on the map generation function and ensure the plots are generated as static images (`config={'staticPlot': True}`) to minimize performance overhead.
*   **Low:** The "Scary Racers" logic is a simple heuristic and may not be perfectly accurate. Mitigation: This is acceptable for an initial feature. The name "Scary Racers" implies a fun, non-scientific prediction. The logic can be refined in future sprints.
*   **Low:** Generating plausible-looking random course polylines might be complex. Mitigation: Start with simple random walks within bounding boxes. The goal is a recognizable shape, not a perfectly accurate route.

## Open Questions

This draft directly addresses and resolves the open questions from the intent document:

1.  **Race Types**: We will implement the proposed set: `criterium, road_race, hill_climb, stage_race, time_trial, gravel`, plus an `unknown` default, using a DB Enum.
2.  **Course Maps**: They will be **static thumbnails**. The implementation will use Plotly `scatter_mapbox` to generate non-interactive images, prioritizing performance.
3.  **Demo Coordinates**: We will generate **random walks within predefined PNW bounding boxes**. This provides variety while keeping the locations plausible.
4.  **Scoring Formula**: The proposed formula (`wins * 3 + podiums * 1`) is adopted, with an added bonus (`* 1.5`) for performance in a race of the same type.
5.  **Race Type Storage**: Race type will be a **new DB column** (`race_type`) on the `Race` table for persistence and query efficiency.
6.  **Mapbox Token**: A token is **not required**. We will use Plotly's built-in support for the "open-street-map" tile layer.
7.  **Icon Format**: We will use **inline SVG** embedded via `st.markdown`, which is flexible and requires no extra file management.
8.  **Pagination**: The tile grid will **not be paginated** initially. With ~50 demo races, a 3x17 grid is manageable. Pagination can be added as a future enhancement if the dataset grows.
