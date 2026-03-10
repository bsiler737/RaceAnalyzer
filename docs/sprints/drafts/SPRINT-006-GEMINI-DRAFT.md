# Sprint 006: Course Maps & Race Series Grouping

## Overview

Add course map visualization (via RideWithGPS route discovery) and race series grouping (deduplication of recurring races across years). The calendar collapses "Banana Belt RR" into one series tile linking to a new series detail page with aggregated classification history, per-edition breakdowns, and course map. The race detail page gains a route polyline map alongside the existing area pin map.

**Duration**: ~5-6 days
**Prerequisite**: Sprint 005 complete, 50+ real PNW races scraped with classifications.

---

## Use Cases

1. **As a racer**, I see a course map on the race detail page showing the route polyline overlaid on a real map, so I can understand the terrain.
2. **As a racer**, I see races grouped by name in the calendar -- "Banana Belt" is one tile, not four.
3. **As a racer**, I see aggregated classification history for a race series -- how the race has finished across all editions and categories.
4. **As a racer**, the series tile badge reflects the most common finish type across ALL editions.
5. **As a developer**, course route data is fetched from RideWithGPS and cached in the database.

---

## Architecture

```
raceanalyzer/
├── db/
│   └── models.py              # MODIFY: Add RaceSeries, RaceRoute tables
├── queries.py                 # MODIFY: Add series queries, aggregated classification,
│                              #          modify get_race_tiles() for series grouping
├── services/
│   └── rwgps.py               # CREATE: RWGPS search, route fetching, caching
├── ui/
│   ├── components.py          # MODIFY: Add series tile renderer, series badge logic
│   ├── maps.py                # MODIFY: Add render_course_map() with Folium polyline
│   ├── charts.py              # MODIFY: Add series classification charts
│   ├── pages/
│   │   ├── calendar.py        # MODIFY: Render series tiles instead of individual tiles
│   │   ├── race_detail.py     # MODIFY: Add course map, link to series page
│   │   └── series_detail.py   # CREATE: Series page with editions, aggregated stats, map

tests/
├── test_rwgps.py              # CREATE: RWGPS search/cache tests
├── test_series_queries.py     # CREATE: Series grouping, aggregation tests
```

### Key Design Decisions

1. **`RaceSeries` as a DB table, not computed at query time.** A `race_series` table holds the canonical series name and a `series_key` (normalized name). Each `Race` gains a `series_id` FK. This avoids recomputing name normalization on every calendar load, supports manual override for tricky names, and makes aggregation queries efficient. A one-time backfill command populates series from existing races.

2. **Name normalization: suffix stripping + year removal.** Strip trailing year (e.g., "2024"), normalize race-type suffixes ("RR" -> "Road Race", "Crit" -> "Criterium"), lowercase, collapse whitespace. This handles "Banana Belt RR" vs "Banana Belt Road Race." Fuzzy matching is out of scope -- exact normalized-name matching only.

3. **RWGPS route cached as polyline in DB.** Store route_id + encoded polyline string in a `race_routes` table. Fetch once from RWGPS `/find/search.json`, then render locally with Folium. No iframe dependency, works offline after first fetch, enables custom styling (elevation coloring, start/finish markers).

4. **Calendar shows series tiles; series page shows all editions.** One tile per series in the calendar. Clicking goes to a new series detail page. From there, users can drill into individual edition detail pages. The series page IS the primary landing; individual race detail becomes a sub-view.

5. **Aggregated classification: frequency across ALL editions AND categories.** For badge logic, count finish types across every category of every edition. The most frequent non-UNKNOWN type becomes the series badge. This gives the best prediction of "what will the next edition be like."

6. **Course map rendering: Folium with streamlit-folium.** Custom Leaflet map with polyline overlay, start/finish markers, and optional elevation profile. More control than RWGPS iframe embed. Falls back to area-only map if no route found.

---

## UI/UX Design

### Series Tile (Calendar View)

Each series tile in the calendar replaces what was previously N individual tiles:

```
┌──────────────────────────────────────────────────┐
│  [sprint-icon]  Banana Belt Road Race     [4 ed] │
│                                                  │
│  Mar 2022 -- Mar 2025  ·  Hillsboro, OR         │
│                                                  │
│  [Bunch Sprint]  badge                           │
│  ────────────────────────────                    │
│  ▓▓▓▓▓▓▓▓▓ bunch  ▓▓▓ break  ▒ mixed            │
│  (mini stacked bar: classification distribution) │
└──────────────────────────────────────────────────┘
```

**Tile content:**
- **Header:** Finish-type icon (from aggregated badge) + canonical series name.
- **Edition count:** Small badge in top-right corner: "4 ed" (editions). Absent if only 1 edition (series with 1 edition renders identically to a regular tile, just without the edition badge).
- **Date range:** "Mar 2022 -- Mar 2025" showing first and last edition dates. If only one edition, shows the single date as before.
- **Location:** Same as current tile -- location from the most recent edition.
- **Classification badge:** Aggregated across all editions (most frequent non-UNKNOWN).
- **Mini distribution bar:** A single-row stacked bar (8px tall, rounded corners) showing the proportion of each finish type across all edition-categories. Uses the same `FINISH_TYPE_COLORS`. Only shown if 2+ editions exist.

**Visual distinction for series vs single race:**
- Series tiles show the edition count badge and mini distribution bar.
- Single-race tiles look exactly like current tiles (no badge, no bar).

**Implementation:**

```python
def _render_series_tile(series_row: dict, key_prefix: str = "stile"):
    """Render a series tile with aggregated info and mini classification bar."""
    edition_count = series_row.get("edition_count", 1)
    is_series = edition_count > 1

    with st.container(border=True):
        # Row 1: Icon + name + edition badge
        name = html.escape(series_row["name"])
        icon_svg = FINISH_TYPE_ICONS.get(
            series_row.get("overall_finish_type", "unknown"),
            FINISH_TYPE_ICONS["unknown"],
        )
        edition_badge = ""
        if is_series:
            edition_badge = (
                f'<span style="background:#546E7A;color:white;padding:1px 6px;'
                f'border-radius:3px;font-size:0.75em;margin-left:auto;">'
                f'{edition_count} ed</span>'
            )
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:8px;">'
            f'{icon_svg} <strong>{name}</strong>{edition_badge}</div>',
            unsafe_allow_html=True,
        )

        # Row 2: Date range + location
        if is_series:
            date_str = f"{series_row['first_date']:%b %Y} &ndash; {series_row['last_date']:%b %Y}"
        else:
            date_str = f"{series_row['last_date']:%b %d, %Y}" if series_row.get("last_date") else ""

        loc = html.escape(str(series_row.get("location", "") or ""))
        state = html.escape(str(series_row.get("state_province", "") or ""))
        loc_str = f"{loc}, {state}" if state else loc
        st.markdown(
            f'<div style="font-size:0.85em;color:#666;">{date_str} &middot; {loc_str}</div>',
            unsafe_allow_html=True,
        )

        # Row 3: Classification badge
        finish_type = series_row.get("overall_finish_type", "unknown")
        color = FINISH_TYPE_COLORS.get(finish_type, "#9E9E9E")
        display = FINISH_TYPE_DISPLAY_NAMES.get(finish_type, "Unknown")
        tooltip = html.escape(FINISH_TYPE_TOOLTIPS.get(finish_type, ""))
        st.markdown(
            f'<span style="background:{color};color:white;padding:2px 8px;'
            f'border-radius:4px;font-size:0.8em;cursor:help;" '
            f'title="{tooltip}">{display}</span>',
            unsafe_allow_html=True,
        )

        # Row 4: Mini distribution bar (series only)
        if is_series and series_row.get("classification_distribution"):
            _render_mini_distribution_bar(series_row["classification_distribution"])

        # Navigation
        series_id = series_row["series_id"]
        if st.button(
            "View Series" if is_series else "View Details",
            key=f"{key_prefix}_btn_{series_id}",
            use_container_width=True,
        ):
            if is_series:
                st.query_params["series_id"] = str(series_id)
                st.switch_page("pages/series_detail.py")
            else:
                race_id = series_row["latest_race_id"]
                st.query_params["race_id"] = str(race_id)
                st.switch_page("pages/race_detail.py")


def _render_mini_distribution_bar(distribution: dict[str, int]):
    """Render a thin stacked bar showing finish type proportions.

    distribution: {"bunch_sprint": 5, "breakaway": 2, ...}
    """
    total = sum(distribution.values())
    if total == 0:
        return

    segments = []
    for ft, count in sorted(distribution.items(), key=lambda x: -x[1]):
        if ft == "unknown" or count == 0:
            continue
        pct = count / total * 100
        color = FINISH_TYPE_COLORS.get(ft, "#9E9E9E")
        display = FINISH_TYPE_DISPLAY_NAMES.get(ft, ft)
        segments.append(
            f'<div style="width:{pct:.1f}%;background:{color};height:100%;" '
            f'title="{display}: {count}/{total}"></div>'
        )

    if not segments:
        return

    bar_html = (
        f'<div style="display:flex;height:8px;border-radius:4px;overflow:hidden;'
        f'margin-top:6px;">{"".join(segments)}</div>'
    )
    st.markdown(bar_html, unsafe_allow_html=True)
```

### Series Detail Page Layout

The series detail page is the primary landing from the calendar. It displays all editions of a race series with aggregated statistics.

```
┌─────────────────────────────────────────────────────────────────┐
│  [< Back to Calendar]                                          │
│                                                                 │
│  ══════════════════════════════════════════════                  │
│  Banana Belt Road Race                                          │
│  Hillsboro, OR  ·  4 editions (2022--2025)  ·  Road Race       │
│  ══════════════════════════════════════════════                  │
│                                                                 │
│  ┌─── Course Map ────────────────────────┐ ┌── Summary ───────┐ │
│  │                                       │ │ Most common:     │ │
│  │   [Folium map with route polyline]    │ │ [Bunch Sprint]   │ │
│  │   Start ● ─── route line ─── ● Finish │ │                  │ │
│  │                                       │ │ 4 editions       │ │
│  │   Elevation: ▁▂▃▅▇▅▃▂▁               │ │ 12 categories    │ │
│  │                                       │ │ 85 finishers avg │ │
│  │   [No route? Area pin map instead]    │ │                  │ │
│  └───────────────────────────────────────┘ └──────────────────┘ │
│                                                                 │
│  ── Classification History ─────────────────────────────────── │
│                                                                 │
│  [Stacked bar chart: year on X, finish type counts on Y]       │
│  | 2022: ████ bunch ██ break                                   │
│  | 2023: ████ bunch █ small_group █ break                      │
│  | 2024: ███ bunch ███ reduced                                 │
│  | 2025: ████ bunch ██ break                                   │
│                                                                 │
│  ── Per-Category Breakdown ─────────────────────────────────── │
│                                                                 │
│  Category        2022           2023           2024      2025   │
│  ───────────     ────────────   ────────────   ────────  ────── │
│  Men Cat 1/2    Bunch Sprint   Bunch Sprint   Reduced   Bunch  │
│  Men Cat 3      Breakaway      Bunch Sprint   Bunch     Break  │
│  Men Cat 4/5    Bunch Sprint   Small Group    Bunch     Bunch  │
│  Women 1/2      Breakaway      Breakaway      Break     Break  │
│                                                                 │
│  ── Editions ──────────────────────────────────────────────── │
│                                                                 │
│  ▼ 2025 -- March 15, 2025                                     │
│    [Bunch Sprint] badge  ·  32 finishers  ·  4 categories     │
│    [View full results →]                                       │
│                                                                 │
│  ▶ 2024 -- March 16, 2024  (collapsed)                        │
│  ▶ 2023 -- March 18, 2023  (collapsed)                        │
│  ▶ 2022 -- March 19, 2022  (collapsed)                        │
└─────────────────────────────────────────────────────────────────┘
```

**Page structure (top to bottom):**

1. **Back button:** Returns to calendar with filter state preserved (same pattern as race_detail.py).

2. **Header block:** Series name (large `st.title`), location from most recent edition, edition count with date range, inferred race type.

3. **Two-column hero section** (`st.columns([3, 1])`):
   - **Left (75%):** Course map. Folium polyline if RWGPS route exists; area pin map as fallback. The course map replaces the area map when available -- they do NOT appear side by side. The map shows start/finish markers, direction arrows on the polyline, and an optional mini elevation profile below.
   - **Right (25%):** Summary stats card. Aggregated classification badge (large), edition count, total categories across all editions, average finishers per edition.

4. **Classification History chart:** A Plotly stacked bar chart with years on the X axis and finish type counts on Y. Each bar segment is colored by `FINISH_TYPE_COLORS`. Hovering shows the finish type name and count. This answers "how does this race usually finish?"

5. **Per-Category Breakdown table:** A pivot table with categories as rows and years as columns. Each cell shows the finish type badge (colored chip). This answers "does Cat 1/2 finish differently from Cat 4/5?"

6. **Editions accordion:** Each edition is a `st.expander`, most recent expanded by default. Shows: edition date, overall badge for that edition, finisher count, category count, and a "View full results" button that navigates to the existing race_detail.py page for that specific edition.

**Navigation flow:**
```
Calendar (series tiles)
    └──> Series Detail (aggregated view)
             └──> Race Detail (single edition, existing page)
                      └──> Back to Series Detail (new back target)
```

**Implementation:**

```python
# pages/series_detail.py

def render():
    session = st.session_state.db_session

    # Back navigation
    if st.button("Back to Calendar"):
        st.switch_page("pages/calendar.py")

    series_id_str = st.query_params.get("series_id")
    if not series_id_str:
        render_empty_state("No series selected.")
        return

    series_id = int(series_id_str)
    series = queries.get_series_detail(session, series_id)
    if series is None:
        render_empty_state(f"Series ID {series_id} not found.")
        return

    # Header
    st.title(series["name"])
    location = series["location"] or "Unknown"
    state = series["state_province"] or ""
    edition_count = series["edition_count"]
    date_range = (
        f"{series['first_date']:%b %Y} -- {series['last_date']:%b %Y}"
        if edition_count > 1
        else f"{series['last_date']:%B %d, %Y}"
    )
    st.caption(
        f"{location}, {state}  |  {edition_count} edition{'s' if edition_count != 1 else ''}  "
        f"({date_range})"
    )

    # Hero section: map + summary
    col_map, col_summary = st.columns([3, 1])

    with col_map:
        route = queries.get_series_route(session, series_id)
        if route and route.get("polyline"):
            render_course_map(
                route["polyline"],
                center=(route["center_lat"], route["center_lon"]),
            )
        elif series.get("course_lat") and series.get("course_lon"):
            coords = (float(series["course_lat"]), float(series["course_lon"]))
            render_location_map(*coords)
        elif location != "Unknown":
            coords = geocode_location(location, state)
            if coords:
                render_location_map(*coords)
            else:
                st.info("No map available for this location.")

    with col_summary:
        ft = series.get("overall_finish_type", "unknown")
        color = FINISH_TYPE_COLORS.get(ft, "#9E9E9E")
        display = FINISH_TYPE_DISPLAY_NAMES.get(ft, "Unknown")
        st.markdown(
            f'<div style="text-align:center;padding:12px;">'
            f'<div style="font-size:0.8em;color:#888;">Most common finish</div>'
            f'<div style="background:{color};color:white;padding:6px 12px;'
            f'border-radius:6px;font-size:1.1em;margin-top:4px;">{display}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.metric("Editions", edition_count)
        st.metric("Total Categories", series["total_categories"])
        st.metric("Avg Finishers", f"{series['avg_finishers']:.0f}")

    st.divider()

    # Classification history chart
    if edition_count > 1:
        st.subheader("Classification History")
        history_df = series["classification_history"]  # year, finish_type, count
        if not history_df.empty:
            fig = build_series_classification_chart(history_df)
            st.plotly_chart(fig, use_container_width=True)

        # Per-category breakdown table
        st.subheader("Per-Category Breakdown")
        pivot_df = series["category_pivot"]  # category x year -> finish_type
        if not pivot_df.empty:
            _render_category_pivot(pivot_df)

    st.divider()

    # Editions accordion
    st.subheader("Editions")
    for i, edition in enumerate(series["editions"]):
        expanded = i == 0  # Most recent expanded
        date_str = f"{edition['date']:%B %d, %Y}" if edition.get("date") else "Unknown date"
        year = edition["date"].year if edition.get("date") else "?"

        with st.expander(f"{year} -- {date_str}", expanded=expanded):
            edition_ft = edition.get("overall_finish_type", "unknown")
            ft_color = FINISH_TYPE_COLORS.get(edition_ft, "#9E9E9E")
            ft_display = FINISH_TYPE_DISPLAY_NAMES.get(edition_ft, "Unknown")
            st.markdown(
                f'<span style="background:{ft_color};color:white;padding:2px 8px;'
                f'border-radius:4px;font-size:0.85em;">{ft_display}</span>'
                f' &nbsp; {edition.get("num_finishers", 0)} finishers'
                f' &middot; {edition.get("num_categories", 0)} categories',
                unsafe_allow_html=True,
            )
            if st.button(
                "View full results",
                key=f"edition_btn_{edition['race_id']}",
            ):
                st.query_params["race_id"] = str(edition["race_id"])
                st.session_state["back_to_series"] = str(series_id)
                st.switch_page("pages/race_detail.py")
```

### Course Map Rendering

The course map uses Folium (via `streamlit-folium`) to render a route polyline on a terrain/satellite base layer.

**Design:**
- Base layer: OpenStreetMap with optional terrain/satellite toggle.
- Route: Decoded polyline rendered as a blue line (3px weight) with directional arrows.
- Markers: Green circle at start, red circle/flag at finish.
- Zoom: Auto-fit to polyline bounding box.
- Elevation profile (stretch goal): A small Plotly area chart below the map showing elevation vs distance, styled like Strava.

**When no route exists:** Fall back to the existing `render_location_map()` area pin. Show a subtle notice: "Course route not available. Showing approximate area."

**Implementation in `maps.py`:**

```python
import folium
from streamlit_folium import st_folium
import polyline as polyline_lib  # google polyline encoder/decoder


def render_course_map(
    encoded_polyline: str,
    center: tuple[float, float] | None = None,
    zoom_start: int = 13,
):
    """Render a Folium map with the course route polyline.

    Args:
        encoded_polyline: Google-encoded polyline string from RWGPS.
        center: Optional (lat, lon) center. Computed from polyline if absent.
        zoom_start: Initial zoom level.
    """
    coords = polyline_lib.decode(encoded_polyline)
    if not coords:
        st.warning("Course route data is empty.")
        return

    # Compute center from polyline if not provided
    if center is None:
        lats = [c[0] for c in coords]
        lons = [c[1] for c in coords]
        center = (sum(lats) / len(lats), sum(lons) / len(lons))

    m = folium.Map(location=center, zoom_start=zoom_start, tiles="OpenStreetMap")

    # Route polyline
    folium.PolyLine(
        coords,
        color="#1565C0",
        weight=3,
        opacity=0.85,
    ).add_to(m)

    # Start marker (green)
    folium.CircleMarker(
        coords[0],
        radius=8,
        color="#2E7D32",
        fill=True,
        fill_color="#4CAF50",
        fill_opacity=0.9,
        popup="Start",
    ).add_to(m)

    # Finish marker (red)
    folium.CircleMarker(
        coords[-1],
        radius=8,
        color="#C62828",
        fill=True,
        fill_color="#E53935",
        fill_opacity=0.9,
        popup="Finish",
    ).add_to(m)

    # Fit bounds
    m.fit_bounds([[min(c[0] for c in coords), min(c[1] for c in coords)],
                  [max(c[0] for c in coords), max(c[1] for c in coords)]])

    st_folium(m, use_container_width=True, height=350)
```

### Calendar Page Modifications

The calendar page changes from rendering individual race tiles to rendering series tiles:

```python
# calendar.py -- modified render()

def render():
    session = st.session_state.db_session
    filters = render_sidebar_filters(session)

    st.title("PNW Race Calendar")

    # Get series-grouped tiles instead of individual race tiles
    df = queries.get_series_tiles(session, year=filters["year"], states=filters["states"])

    if df.empty:
        render_empty_state(
            "No races found. Try adjusting your filters or run "
            "`raceanalyzer scrape` to import data."
        )
        return

    # Count unknown series before filtering
    unknown_count = len(df[df["overall_finish_type"] == "unknown"])
    total_count = len(df)

    show_unknown = st.toggle(
        f"Show unclassified races ({unknown_count} of {total_count})",
        value=False,
    )
    if not show_unknown:
        df = df[df["overall_finish_type"] != "unknown"]

    if df.empty:
        render_empty_state(
            "No classified races found. Toggle 'Show unclassified races' to see all."
        )
        return

    # Metrics
    col1, col2, col3 = st.columns(3)
    total_editions = df["edition_count"].sum()
    col1.metric("Race Series", len(df))
    col2.metric("Total Editions", int(total_editions))
    dated = df[df["last_date"].notna()]
    if not dated.empty:
        col3.metric(
            "Date Range",
            f"{dated['first_date'].min():%b %Y} -- {dated['last_date'].max():%b %Y}",
        )

    # Pagination
    if "tile_page_size" not in st.session_state:
        st.session_state.tile_page_size = TILES_PER_PAGE
    visible_count = st.session_state.tile_page_size

    visible_df = df.head(visible_count)
    render_series_tile_grid(visible_df, key_prefix="cal")

    if visible_count < len(df):
        remaining = len(df) - visible_count
        if st.button(f"Show more ({remaining} remaining)"):
            st.session_state.tile_page_size = visible_count + TILES_PER_PAGE
            st.rerun()
```

### Aggregated Classification Display

The primary visualization for "how does this race usually finish?" is a **stacked bar chart by year**:

```python
# charts.py

def build_series_classification_chart(history_df: pd.DataFrame):
    """Build a stacked bar chart of finish types across years.

    history_df columns: year, finish_type, count.
    Returns a Plotly Figure.
    """
    import plotly.express as px
    from raceanalyzer.ui.components import FINISH_TYPE_COLORS
    from raceanalyzer.queries import FINISH_TYPE_DISPLAY_NAMES

    # Map finish_type values to display names
    history_df = history_df.copy()
    history_df["display_name"] = history_df["finish_type"].map(
        lambda ft: FINISH_TYPE_DISPLAY_NAMES.get(ft, ft)
    )

    # Build color map using display names
    color_map = {
        FINISH_TYPE_DISPLAY_NAMES.get(ft, ft): color
        for ft, color in FINISH_TYPE_COLORS.items()
    }

    fig = px.bar(
        history_df,
        x="year",
        y="count",
        color="display_name",
        color_discrete_map=color_map,
        labels={"count": "Category Results", "year": "Year", "display_name": "Finish Type"},
        title="Classification Distribution by Year",
    )
    fig.update_layout(
        barmode="stack",
        xaxis=dict(dtick=1),
        legend_title_text="Finish Type",
        height=300,
        margin=dict(t=40, b=40),
    )
    return fig
```

**Per-category breakdown** is rendered as a colored table:

```python
def _render_category_pivot(pivot_df: pd.DataFrame):
    """Render a category x year pivot table with colored finish-type chips.

    pivot_df: index=category, columns=years, values=finish_type strings.
    """
    header_cols = ["Category"] + [str(y) for y in pivot_df.columns]
    header_html = "".join(f"<th style='padding:6px 12px;'>{c}</th>" for c in header_cols)

    rows_html = []
    for category in pivot_df.index:
        cells = [f"<td style='padding:6px 12px;font-weight:bold;'>{html.escape(category)}</td>"]
        for year in pivot_df.columns:
            ft = pivot_df.loc[category, year]
            if pd.isna(ft) or ft == "":
                cells.append("<td style='padding:6px 12px;color:#ccc;'>--</td>")
            else:
                color = FINISH_TYPE_COLORS.get(ft, "#9E9E9E")
                display = FINISH_TYPE_DISPLAY_NAMES.get(ft, ft)
                cells.append(
                    f"<td style='padding:6px 12px;'>"
                    f"<span style='background:{color};color:white;padding:2px 6px;"
                    f"border-radius:3px;font-size:0.8em;'>{display}</span></td>"
                )
        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    table_html = (
        f"<table style='width:100%;border-collapse:collapse;'>"
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody></table>"
    )
    st.markdown(table_html, unsafe_allow_html=True)
```

**Badge logic (aggregated):**
- Count ALL non-UNKNOWN finish types across ALL editions and ALL categories.
- Pick the most frequent. Tiebreak: total finishers, then lowest average CV.
- This reuses the same `_compute_overall_finish_type()` pattern but across multiple race_ids.

---

## Implementation

### 1. `raceanalyzer/db/models.py` -- Add RaceSeries and RaceRoute

```python
class RaceSeries(Base):
    """A logical grouping of recurring race editions."""

    __tablename__ = "race_series"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)         # Canonical display name
    series_key = Column(String, nullable=False, unique=True)  # Normalized for dedup
    location = Column(String, nullable=True)       # From most recent edition
    state_province = Column(String, nullable=True)

    races = relationship("Race", back_populates="series")

    __table_args__ = (
        Index("ix_series_key", "series_key"),
    )


# Add to Race model:
#   series_id = Column(Integer, ForeignKey("race_series.id"), nullable=True)
#   series = relationship("RaceSeries", back_populates="races")


class RaceRoute(Base):
    """Cached route data from RideWithGPS."""

    __tablename__ = "race_routes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    series_id = Column(Integer, ForeignKey("race_series.id"), nullable=True)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=True)
    rwgps_route_id = Column(Integer, nullable=True)
    encoded_polyline = Column(Text, nullable=True)
    center_lat = Column(Float, nullable=True)
    center_lon = Column(Float, nullable=True)
    distance_meters = Column(Float, nullable=True)
    elevation_gain_meters = Column(Float, nullable=True)
    fetched_at = Column(DateTime, nullable=True)
    match_confidence = Column(Float, nullable=True)  # 0.0-1.0 search quality

    __table_args__ = (
        Index("ix_routes_series", "series_id"),
        Index("ix_routes_race", "race_id"),
    )
```

### 2. `raceanalyzer/services/rwgps.py` -- RWGPS Route Discovery (NEW FILE)

```python
"""RideWithGPS route search and caching service."""

import logging
import re
from datetime import datetime

import requests
from sqlalchemy.orm import Session

from raceanalyzer.db.models import RaceRoute, RaceSeries

logger = logging.getLogger(__name__)

RWGPS_SEARCH_URL = "https://ridewithgps.com/find/search.json"
RWGPS_ROUTE_URL = "https://ridewithgps.com/routes/{route_id}.json"


def search_route(
    race_name: str,
    lat: float,
    lon: float,
    *,
    max_results: int = 5,
) -> list[dict]:
    """Search RWGPS for routes matching a race name near a location.

    Returns list of route dicts with keys: id, name, distance, elevation_gain,
    bounding_box, first_lat, first_lng.
    """
    # Clean race name: strip year, "RR", "Crit" etc. for broader matching
    clean_name = _clean_search_name(race_name)

    try:
        resp = requests.get(
            RWGPS_SEARCH_URL,
            params={
                "search[keywords]": clean_name,
                "search[lat]": lat,
                "search[lng]": lon,
                "search[offset]": 0,
                "search[limit]": max_results,
            },
            headers={"User-Agent": "RaceAnalyzer/0.1 (PNW bike race analysis)"},
            timeout=10,
        )
        if resp.ok:
            data = resp.json()
            results = data.get("results", [])
            return [
                {
                    "id": r.get("id"),
                    "name": r.get("name", ""),
                    "distance": r.get("distance"),
                    "elevation_gain": r.get("elevation_gain"),
                    "first_lat": r.get("first_lat"),
                    "first_lng": r.get("first_lng"),
                }
                for r in results
                if r.get("type") == "route"
            ]
    except Exception:
        logger.warning("RWGPS search failed for %s", race_name)

    return []


def fetch_route_polyline(route_id: int) -> str | None:
    """Fetch encoded polyline for a specific RWGPS route.

    Returns Google-encoded polyline string, or None on failure.
    """
    try:
        resp = requests.get(
            RWGPS_ROUTE_URL.format(route_id=route_id),
            headers={"User-Agent": "RaceAnalyzer/0.1 (PNW bike race analysis)"},
            timeout=10,
        )
        if resp.ok:
            data = resp.json()
            # RWGPS may return track_points or an encoded polyline
            if "encoded_polyline" in data.get("route", {}):
                return data["route"]["encoded_polyline"]
            # Fallback: encode track_points ourselves
            track_points = data.get("route", {}).get("track_points", [])
            if track_points:
                import polyline as polyline_lib
                coords = [(p["y"], p["x"]) for p in track_points]
                return polyline_lib.encode(coords)
    except Exception:
        logger.warning("RWGPS polyline fetch failed for route %d", route_id)

    return None


def cache_route_for_series(
    session: Session,
    series: RaceSeries,
    lat: float,
    lon: float,
) -> RaceRoute | None:
    """Search RWGPS, pick best match, cache route in DB.

    Returns the cached RaceRoute or None if no match found.
    """
    # Check if already cached
    existing = (
        session.query(RaceRoute)
        .filter(RaceRoute.series_id == series.id)
        .first()
    )
    if existing and existing.encoded_polyline:
        return existing

    results = search_route(series.name, lat, lon)
    if not results:
        return None

    # Pick best match (first result from RWGPS proximity-sorted search)
    best = results[0]
    polyline_str = fetch_route_polyline(best["id"])
    if not polyline_str:
        return None

    route = existing or RaceRoute(series_id=series.id)
    route.rwgps_route_id = best["id"]
    route.encoded_polyline = polyline_str
    route.center_lat = best.get("first_lat")
    route.center_lon = best.get("first_lng")
    route.distance_meters = best.get("distance")
    route.elevation_gain_meters = best.get("elevation_gain")
    route.fetched_at = datetime.utcnow()
    route.match_confidence = 0.7  # Heuristic; improve later

    if not existing:
        session.add(route)
    session.commit()

    return route


def _clean_search_name(name: str) -> str:
    """Strip year, race-type suffixes, and extra whitespace for RWGPS search."""
    # Remove trailing year
    name = re.sub(r"\b20\d{2}\b", "", name)
    # Normalize suffixes
    name = re.sub(r"\bRR\b", "Road Race", name, flags=re.IGNORECASE)
    name = re.sub(r"\bTT\b", "Time Trial", name, flags=re.IGNORECASE)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name
```

### 3. `raceanalyzer/queries.py` -- Series Queries

Add the following functions:

```python
def normalize_series_key(name: str) -> str:
    """Normalize a race name to a series key for deduplication.

    Strips year, normalizes suffixes, lowercases, collapses whitespace.
    """
    import re
    key = name.lower()
    key = re.sub(r"\b20\d{2}\b", "", key)              # Remove year
    key = re.sub(r"\brr\b", "road race", key)           # RR -> Road Race
    key = re.sub(r"\bcrit\b", "criterium", key)          # Crit -> Criterium
    key = re.sub(r"\btt\b", "time trial", key)           # TT -> Time Trial
    key = re.sub(r"[^\w\s]", "", key)                    # Remove punctuation
    key = re.sub(r"\s+", " ", key).strip()               # Collapse whitespace
    return key


def get_series_tiles(
    session: Session,
    *,
    year: Optional[int] = None,
    states: Optional[list[str]] = None,
    limit: int = 200,
) -> pd.DataFrame:
    """Return series-grouped tile data for the calendar.

    When year filter is set, only include series that have an edition in that year.
    Columns: series_id, name, first_date, last_date, location, state_province,
             edition_count, overall_finish_type, classification_distribution,
             latest_race_id.
    """
    # Query series with their races and classifications
    # ... implementation joins RaceSeries -> Race -> RaceClassification
    # ... groups by series, computes aggregated finish type
    pass  # Full implementation follows pattern of get_race_tiles()


def get_series_detail(session: Session, series_id: int) -> Optional[dict]:
    """Return full series detail: editions, aggregated classifications, history.

    Returns dict with keys: name, location, state_province, edition_count,
    first_date, last_date, overall_finish_type, total_categories,
    avg_finishers, classification_history (DataFrame), category_pivot (DataFrame),
    editions (list of dicts).
    """
    pass  # Implementation queries all races in series, builds aggregation


def get_series_route(session: Session, series_id: int) -> Optional[dict]:
    """Return cached route data for a series.

    Returns dict with keys: polyline, center_lat, center_lon,
    distance_meters, elevation_gain_meters. Or None.
    """
    route = (
        session.query(RaceRoute)
        .filter(RaceRoute.series_id == series_id)
        .first()
    )
    if route and route.encoded_polyline:
        return {
            "polyline": route.encoded_polyline,
            "center_lat": route.center_lat,
            "center_lon": route.center_lon,
            "distance_meters": route.distance_meters,
            "elevation_gain_meters": route.elevation_gain_meters,
        }
    return None


def _compute_series_overall_finish_type(
    session: Session, series_id: int,
) -> str:
    """Compute the most frequent non-UNKNOWN finish type across all editions.

    Same algorithm as _compute_overall_finish_type but spans multiple race_ids.
    """
    from collections import Counter

    race_ids = [
        r.id for r in
        session.query(Race.id).filter(Race.series_id == series_id).all()
    ]

    type_counts: Counter = Counter()
    type_finishers: dict[str, int] = {}
    type_cv_sum: dict[str, float] = {}
    type_cv_count: dict[str, int] = {}

    for rid in race_ids:
        classifications = (
            session.query(RaceClassification)
            .filter(RaceClassification.race_id == rid)
            .all()
        )
        for c in classifications:
            ft = c.finish_type.value if c.finish_type else "unknown"
            if ft == "unknown":
                continue
            type_counts[ft] += 1
            type_finishers[ft] = type_finishers.get(ft, 0) + (c.num_finishers or 0)
            if c.cv_of_times is not None:
                type_cv_sum[ft] = type_cv_sum.get(ft, 0.0) + c.cv_of_times
                type_cv_count[ft] = type_cv_count.get(ft, 0) + 1

    if not type_counts:
        return "unknown"

    def sort_key(ft: str) -> tuple:
        avg_cv = (
            type_cv_sum.get(ft, 0.0) / type_cv_count[ft]
            if type_cv_count.get(ft, 0) > 0
            else float("inf")
        )
        return (-type_counts[ft], -type_finishers.get(ft, 0), avg_cv)

    return min(type_counts.keys(), key=sort_key)
```

### 4. CLI -- Backfill Series

Add a `backfill-series` CLI command that:
1. Iterates all races in the DB.
2. Computes `normalize_series_key(race.name)`.
3. Creates or finds a `RaceSeries` with that key.
4. Sets `race.series_id`.
5. Sets canonical series name (from the most recent edition's name).
6. Sets location/state from most recent edition.

```python
# cli.py -- new command

@cli.command()
def backfill_series():
    """Group races into series by normalized name."""
    session = get_session()
    races = session.query(Race).order_by(Race.date.desc()).all()

    series_map: dict[str, RaceSeries] = {}
    for race in races:
        key = normalize_series_key(race.name)
        if key not in series_map:
            existing = session.query(RaceSeries).filter_by(series_key=key).first()
            if existing:
                series_map[key] = existing
            else:
                series_map[key] = RaceSeries(
                    name=race.name,  # First seen = most recent (sorted desc)
                    series_key=key,
                    location=race.location,
                    state_province=race.state_province,
                )
                session.add(series_map[key])
        race.series_id = series_map[key].id

    session.commit()
    click.echo(f"Created {len(series_map)} series from {len(races)} races.")
```

### 5. Race Detail Page -- Course Map + Series Back-Navigation

Modify `race_detail.py` to:
- Show course map if route data exists for the race's series.
- Support "Back to Series" navigation when coming from a series page.

```python
# At top of render():
back_target = st.session_state.pop("back_to_series", None)
if back_target:
    if st.button("Back to Series"):
        st.query_params["series_id"] = back_target
        st.switch_page("pages/series_detail.py")
else:
    if st.button("Back to Calendar"):
        st.switch_page("pages/calendar.py")

# Replace area map section with:
if race.get("series_id"):
    route = queries.get_series_route(session, race["series_id"])
    if route and route.get("polyline"):
        render_course_map(route["polyline"])
    elif location and location != "Unknown":
        coords = geocode_location(location, state)
        if coords:
            st.caption("Course route not available. Showing approximate area.")
            render_location_map(*coords)
elif location and location != "Unknown":
    coords = geocode_location(location, state)
    if coords:
        render_location_map(*coords)
```

---

## Error and Empty States

| Scenario | Behavior |
|----------|----------|
| **RWGPS returns no matching route** | Series detail page shows area pin map with caption: "Course route not available. Showing approximate area." No error. Route search can be retried via a future CLI command. |
| **RWGPS route fetch fails (network)** | Log warning, serve from cache if available, fall back to area map. Never block page load on RWGPS. |
| **Series has only 1 edition** | Tile renders identically to current individual tiles (no edition badge, no distribution bar). Series detail page omits "Classification History" chart and "Per-Category Breakdown" table; just shows the single edition's details inline. |
| **Classifications conflict across years** | No conflict resolution needed. The stacked bar chart explicitly shows the variation. The aggregated badge picks the most frequent type, which naturally handles disagreement. |
| **Series with no classifications at all** | Badge shows "Unknown". Distribution bar is absent. Classification History section shows "No classification data available." |
| **Geocoding fails** | Map section absent (same as current behavior). No error shown to user. |
| **Race not yet assigned to a series** | Tile renders as individual race (old behavior). `backfill-series` must be run. Calendar shows a mix of series tiles and individual tiles until backfill is complete. |
| **Polyline decode fails** | Log error, fall back to area map. Never crash the page. |

---

## Mobile Responsiveness

| Component | Desktop (>768px) | Tablet (480-768px) | Mobile (<480px) |
|-----------|-------------------|--------------------|-----------------|
| **Calendar tiles** | 3-column CSS Grid | 2-column Grid | 1-column Grid (already handled by existing `@media` rules) |
| **Series tile mini-bar** | Full width within tile | Same | Same (bar scales with tile width) |
| **Series detail hero** | `st.columns([3, 1])` -- map left, summary right | Streamlit auto-stacks columns vertically | Summary card stacks below map |
| **Course map (Folium)** | 350px height, full width | Same | `use_container_width=True` handles this. Consider reducing height to 250px via CSS `@media`. |
| **Classification chart** | Full-width Plotly bar | Plotly responsive by default | Bar chart works at narrow widths; legend may wrap below chart. Use `legend_orientation="h"` for horizontal legend below chart. |
| **Category pivot table** | Horizontal scroll if many years | Same | `overflow-x: auto` wrapper div. Years scroll horizontally, category names stay visible. |
| **Edition accordions** | Full width | Same | Same (native `st.expander` is responsive) |

Key CSS addition for pivot table:

```css
.category-pivot-wrapper {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
}
```

---

## Files Summary

| File | Action | Description |
|------|--------|-------------|
| `raceanalyzer/db/models.py` | **Modify** | Add `RaceSeries`, `RaceRoute` tables; add `series_id` FK to `Race` |
| `raceanalyzer/queries.py` | **Modify** | Add `normalize_series_key()`, `get_series_tiles()`, `get_series_detail()`, `get_series_route()`, `_compute_series_overall_finish_type()` |
| `raceanalyzer/services/rwgps.py` | **Create** | RWGPS search, polyline fetch, route caching |
| `raceanalyzer/ui/components.py` | **Modify** | Add `_render_series_tile()`, `_render_mini_distribution_bar()`, `render_series_tile_grid()` |
| `raceanalyzer/ui/maps.py` | **Modify** | Add `render_course_map()` with Folium polyline rendering |
| `raceanalyzer/ui/charts.py` | **Modify** | Add `build_series_classification_chart()` |
| `raceanalyzer/ui/pages/calendar.py` | **Modify** | Switch to `get_series_tiles()`, render series tiles, update metrics |
| `raceanalyzer/ui/pages/race_detail.py` | **Modify** | Course map, "Back to Series" navigation, series_id in query |
| `raceanalyzer/ui/pages/series_detail.py` | **Create** | Full series detail page with history chart, pivot table, edition list |
| `raceanalyzer/cli.py` | **Modify** | Add `backfill-series` and `fetch-routes` commands |
| `tests/test_rwgps.py` | **Create** | RWGPS search/cache tests with mocked HTTP |
| `tests/test_series_queries.py` | **Create** | Series grouping, normalization, aggregation tests |

**Total new files**: 3 (`rwgps.py`, `series_detail.py`, tests)
**Total modified files**: 8
**Estimated new tests**: ~12-15

---

## Definition of Done

1. `RaceSeries` table exists with `series_key` unique index
2. `RaceRoute` table exists, linked to series and optionally to individual races
3. `Race.series_id` FK populated by `backfill-series` CLI command
4. Name normalization strips year, normalizes suffixes (RR, Crit, TT), lowercases
5. Calendar renders one tile per series, not one per edition
6. Series tile shows: edition count badge, date range, aggregated classification badge, mini distribution bar
7. Single-edition "series" tiles render identically to current individual tiles
8. Clicking a multi-edition series tile navigates to series detail page
9. Series detail page shows: header, course map or area map, summary stats, classification history chart, per-category pivot table, expandable editions
10. Classification history stacked bar chart uses `FINISH_TYPE_COLORS`, shows years on X axis
11. Per-category breakdown table shows colored finish-type chips per year
12. Edition accordions link to individual race detail pages
13. Race detail page shows course map (Folium polyline) when route data available
14. Race detail page falls back to area pin map with "Course route not available" caption
15. RWGPS search uses race name + geocoded coordinates, caches route in DB
16. `fetch-routes` CLI command discovers and caches routes for all series
17. Mobile: tiles collapse to 1-column, maps use container width, pivot table scrolls horizontally
18. All error/empty states handled gracefully (no crashes, friendly messages)
19. All existing tests pass (zero regressions)
20. New tests: name normalization, series aggregation, RWGPS mock, empty/edge cases

---

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| RWGPS undocumented API changes or rate limits | No course maps | Medium | Cache aggressively; route fetch is CLI-driven, not on page load. Fallback to area map always available. |
| RWGPS search returns wrong route (name mismatch) | Misleading course map | Medium | Store `match_confidence` score; future UI could show "verify route" prompt. Start with conservative matching. |
| Name normalization groups unrelated races | Wrong series grouping | Low | Exact normalized match only (no fuzzy). Manual override via DB possible. Edge cases caught in testing. |
| `streamlit-folium` version compatibility | Broken map rendering | Low | Pin version in requirements. Folium is mature. Fall back to area map on error. |
| Large polyline data in SQLite | Slow queries | Very Low | Polylines are typically <50KB. Index on series_id. Single polyline per series. |
| Migration needed for new tables | Existing DB breaks | Low | Alembic migration or `Base.metadata.create_all()`. New tables are additive; existing tables unchanged except new nullable `series_id` column on Race. |
| Series page slow with many editions | Bad UX | Low | Limit initial query to 20 most recent editions. Lazy-load older ones. |

---

## Dependencies

- **New package**: `streamlit-folium` (Folium map rendering in Streamlit)
- **New package**: `folium` (Leaflet.js Python wrapper)
- **New package**: `polyline` (Google encoded polyline encoder/decoder)
- `requests` already in dependencies (for RWGPS API)
- External APIs: RideWithGPS `/find/search.json` (free, no auth), Nominatim (existing)

---

## Scope Cut Guidance

If constrained, cut in this order (last = cut first):

1. **Keep**: Race series grouping (DB model + backfill + calendar tiles + series detail page), aggregated classification badge
2. **Cut if needed**: Per-category pivot table, elevation profile on course map, mini distribution bar on tiles
3. **Cut if needed**: Course maps entirely (RWGPS integration + Folium rendering). Series grouping alone is high-value without maps.

---

## Open Questions

1. **Folium vs RWGPS iframe embed?** This draft recommends Folium for control and offline capability. The iframe alternative is simpler (one line of HTML) but depends on RWGPS uptime and offers no customization. Decision needed.
2. **Should `backfill-series` run automatically on scrape?** Or require explicit CLI invocation? Automatic is more convenient but couples scraping to dedup logic.
3. **Alembic migration vs create_all()?** New tables need a migration strategy. If the project already uses `create_all()` on startup, that may suffice. If Alembic is in use, a migration script is needed.
4. **Should the calendar support both views (series grouped vs individual)?** A toggle could let users switch. This draft assumes series-only view. Individual view would be a future enhancement.
5. **Polyline encoding format**: RWGPS may return track points instead of encoded polyline. The implementation handles both, but should be validated against real RWGPS responses.
