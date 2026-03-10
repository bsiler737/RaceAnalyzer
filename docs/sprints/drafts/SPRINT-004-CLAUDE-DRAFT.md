# Sprint 004: Race Tiles UI + Scary Racers

## Overview

Overhaul the main calendar page from a flat table into a visual 3-wide grid of race tiles, each showing the race name, date, a race type icon, and a mini course map. Add a "Scary Racers" section to the race detail page that predicts the most dangerous competitors per category based on historical results. This sprint touches every layer: schema (new `race_type` column, course coordinate columns), demo data (course polylines, cross-race rider history becomes queryable), query layer (tile queries, scary racer scoring), and UI (tile grid, icons, mini maps, scary racer cards).

**Duration**: ~3-4 days
**Primary deliverables**: Tile grid on calendar page, race type icons, mini course maps, Scary Racers section on race detail.
**Prerequisite**: Sprint 003 complete (demo data with 50 races, 80 riders).

---

## Use Cases

1. **As a racer**, I open the calendar page and immediately see a visual grid of upcoming races with icons telling me whether each is a crit, road race, hill climb, etc. — no need to read names carefully.
2. **As a racer**, I see a small course map on each tile that gives me a quick feel for the route shape (loop, out-and-back, point-to-point) before clicking in.
3. **As a racer**, I click a tile and navigate directly to that race's detail page.
4. **As a racer**, I scroll down on a race detail page and see "Scary Racers" for my category — the riders most likely to win based on their historical results.
5. **As a racer**, I notice that Scary Racer rankings weight race type similarity — a rider who dominates crits is scarier in another crit than in a hill climb.
6. **As a developer**, I can seed demo data and see tiles with course maps and scary racers populated from synthetic history.
7. **As a tester**, I can verify that all 6 race types have distinct icons, tiles render correctly, and scary racer scores are deterministic.

---

## Architecture

```
raceanalyzer/
├── db/
│   └── models.py           # MODIFY: Add RaceType enum, race_type + course_lat/course_lon on Race
├── demo.py                 # MODIFY: Generate course polylines, assign race_type, ensure cross-race rider history
├── queries.py              # MODIFY: Add get_race_tiles(), get_scary_racers(), infer_race_type()
├── config.py               # (no changes)
├── ui/
│   ├── pages/
│   │   ├── calendar.py     # MODIFY: Replace table with 3-wide tile grid
│   │   └── race_detail.py  # MODIFY: Add Scary Racers section
│   ├── components.py       # MODIFY: Add render_race_tile(), render_race_type_icon(), render_scary_racer_card()
│   └── charts.py           # MODIFY: Add build_mini_course_map()

tests/
├── test_queries.py         # MODIFY: Add tests for get_race_tiles, get_scary_racers
├── test_demo.py            # MODIFY: Add tests for course coordinates, race_type assignment
├── test_race_type.py       # CREATE: Tests for race type inference from name
└── test_scary_racers.py    # CREATE: Tests for scoring algorithm
```

### Data Flow

```
Race tile grid:
    get_race_tiles(session, year, states)
        → joins Race + RaceClassification count
        → includes race_type, course_lat, course_lon
        → returns DataFrame with tile-ready data
        ↓
    render_race_tile(tile_data)
        → render_race_type_icon(race_type)   → inline SVG via st.markdown
        → build_mini_course_map(lat, lon)    → static Plotly scatter figure
        → click handler → st.switch_page with race_id

Scary Racers:
    get_scary_racers(session, race_id, category)
        → queries Result history for all riders in this category
        → scores: wins*3 + podiums*1 + race_type_bonus*2
        → returns top 5 per category as DataFrame
        ↓
    render_scary_racer_card(racer_data)
        → name, team, score breakdown, threat emoji
```

### Key Design Decisions

1. **`race_type` as a DB column on Race** — Derived once from the race name via `infer_race_type()` and stored. Faster than re-inferring at query time, and allows manual overrides later. The demo data generator calls `infer_race_type()` at creation time.

2. **Course coordinates as JSON text columns** — `course_lat` and `course_lon` store comma-separated float strings (e.g., `"47.61,47.62,47.63"`). This avoids a separate table and keeps the query simple. For 10-20 points per route, string parsing is negligible.

3. **Race types: 6 values** — `criterium`, `road_race`, `hill_climb`, `stage_race`, `time_trial`, `gravel`. Covers the PNW scene well. The existing `PNW_RACES` list maps cleanly: names containing "criterium/crit/grand prix/short track" → criterium, "stage race/tour de" → stage_race, "hill climb/mount" → hill_climb, "roubaix/gravel" → gravel, everything else → road_race. No time trials in the current name list, but the type exists for future data.

4. **Static mini maps (not interactive)** — Plotly `go.Scattergl` on a white background with the route as a colored line. No map tiles, no Mapbox token needed. Just the route shape — like a Strava thumbnail. Fast to render, works in `st.plotly_chart` at small sizes.

5. **Scary Racer scoring: simple weighted sum** — `wins * 3 + podiums * 1 + race_type_bonus * 2`. The race_type_bonus counts wins/podiums specifically in races of the same type. Simple, explainable, no Elo complexity. Can be refined later.

6. **Tile grid pagination** — Show 12 tiles per page (4 rows of 3) with simple "Show More" button. Avoids rendering 50+ maps at once, keeps the page snappy.

7. **Race type icons as inline SVG** — Rendered via `st.markdown(unsafe_allow_html=True)`. Each icon is a small (~24x24) SVG depicting the race character: a loop for crits, mountains for hill climbs, etc. No external image files needed.

---

## Implementation

### File: `raceanalyzer/db/models.py` — Schema additions

```python
class RaceType(enum.Enum):
    CRITERIUM = "criterium"
    ROAD_RACE = "road_race"
    HILL_CLIMB = "hill_climb"
    STAGE_RACE = "stage_race"
    TIME_TRIAL = "time_trial"
    GRAVEL = "gravel"


class Race(Base):
    """A race event on a specific date."""

    __tablename__ = "races"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    date = Column(DateTime, nullable=True)
    location = Column(String, nullable=True)
    state_province = Column(String, nullable=True)
    url = Column(String, nullable=True)
    race_type = Column(SAEnum(RaceType), nullable=True)
    course_lat = Column(Text, nullable=True)  # Comma-separated latitudes
    course_lon = Column(Text, nullable=True)  # Comma-separated longitudes

    results = relationship("Result", back_populates="race", cascade="all, delete-orphan")
    classifications = relationship(
        "RaceClassification", back_populates="race", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_races_date", "date"),
        Index("ix_races_state", "state_province"),
    )
```

The three new columns (`race_type`, `course_lat`, `course_lon`) are all nullable, so existing data (if any real scraped data existed) would be unaffected. Since we're on demo-only data, `seed-demo` will regenerate everything cleanly.

### File: `raceanalyzer/queries.py` — New queries and race type inference

```python
from raceanalyzer.db.models import Race, RaceClassification, RaceType, Result, Rider

# --- Race type inference ---

_RACE_TYPE_PATTERNS: list[tuple[list[str], RaceType]] = [
    (["criterium", "crit ", "crit,", "grand prix", "short track"], RaceType.CRITERIUM),
    (["stage race", "tour de"], RaceType.STAGE_RACE),
    (["hill climb", "mount ", "mt ", "hillclimb"], RaceType.HILL_CLIMB),
    (["time trial", "tt ", "itt", "chrono"], RaceType.TIME_TRIAL),
    (["roubaix", "gravel", "unpaved"], RaceType.GRAVEL),
]


def infer_race_type(race_name: str) -> RaceType:
    """Infer race type from the race name using keyword matching.

    Falls back to ROAD_RACE if no pattern matches.
    """
    name_lower = race_name.lower()
    for patterns, race_type in _RACE_TYPE_PATTERNS:
        for pattern in patterns:
            if pattern in name_lower:
                return race_type
    return RaceType.ROAD_RACE


# --- Display names and icons ---

RACE_TYPE_DISPLAY_NAMES = {
    "criterium": "Criterium",
    "road_race": "Road Race",
    "hill_climb": "Hill Climb",
    "stage_race": "Stage Race",
    "time_trial": "Time Trial",
    "gravel": "Gravel",
}


def race_type_display_name(race_type_value: str) -> str:
    """Convert RaceType enum value to human-readable name."""
    return RACE_TYPE_DISPLAY_NAMES.get(
        race_type_value, race_type_value.replace("_", " ").title()
    )


# --- Tile query ---

def get_race_tiles(
    session: Session,
    *,
    year: Optional[int] = None,
    states: Optional[list[str]] = None,
    limit: int = 200,
) -> pd.DataFrame:
    """Return race tile data: id, name, date, location, state, race_type, course coords, num_categories.

    Columns: id, name, date, location, state_province, race_type, course_lat, course_lon, num_categories.
    """
    query = session.query(
        Race.id,
        Race.name,
        Race.date,
        Race.location,
        Race.state_province,
        Race.race_type,
        Race.course_lat,
        Race.course_lon,
        func.count(distinct(RaceClassification.category)).label("num_categories"),
    ).outerjoin(RaceClassification, Race.id == RaceClassification.race_id)

    if year is not None:
        query = query.filter(extract("year", Race.date) == year)
    if states:
        query = query.filter(Race.state_province.in_(states))

    query = query.group_by(Race.id).order_by(Race.date.desc()).limit(limit)

    rows = query.all()
    columns = [
        "id", "name", "date", "location", "state_province",
        "race_type", "course_lat", "course_lon", "num_categories",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)

    data = []
    for row in rows:
        data.append({
            "id": row.id,
            "name": row.name,
            "date": row.date,
            "location": row.location,
            "state_province": row.state_province,
            "race_type": row.race_type.value if row.race_type else None,
            "course_lat": row.course_lat,
            "course_lon": row.course_lon,
            "num_categories": row.num_categories,
        })
    return pd.DataFrame(data, columns=columns)


# --- Scary Racers ---

def get_scary_racers(
    session: Session,
    race_id: int,
    category: str,
    *,
    top_n: int = 5,
) -> pd.DataFrame:
    """Return the top predicted performers for a race + category.

    Scoring: wins * 3 + podiums * 1 + same_race_type_wins * 2

    Only considers riders who have raced in this category before.
    Returns DataFrame with columns: rider_id, name, team, wins, podiums,
    type_wins, score.
    """
    race = session.get(Race, race_id)
    if race is None:
        return pd.DataFrame(
            columns=["rider_id", "name", "team", "wins", "podiums", "type_wins", "score"]
        )

    target_race_type = race.race_type

    # Find all riders who have results in this category
    rider_results = (
        session.query(
            Result.rider_id,
            Result.place,
            Result.name,
            Result.team,
            Race.race_type,
        )
        .join(Race, Race.id == Result.race_id)
        .filter(
            Result.race_category_name == category,
            Result.rider_id.isnot(None),
            Result.dnf == False,
            Result.place.isnot(None),
        )
        .all()
    )

    if not rider_results:
        return pd.DataFrame(
            columns=["rider_id", "name", "team", "wins", "podiums", "type_wins", "score"]
        )

    # Aggregate per rider
    rider_stats: dict[int, dict] = {}
    for rider_id, place, name, team, r_type in rider_results:
        if rider_id not in rider_stats:
            rider_stats[rider_id] = {
                "rider_id": rider_id,
                "name": name,
                "team": team or "",
                "wins": 0,
                "podiums": 0,
                "type_wins": 0,
            }
        stats = rider_stats[rider_id]
        # Keep most recent name/team
        stats["name"] = name
        if team:
            stats["team"] = team

        if place == 1:
            stats["wins"] += 1
            if target_race_type and r_type == target_race_type:
                stats["type_wins"] += 1
        if place <= 3:
            stats["podiums"] += 1

    # Score and rank
    rows = []
    for stats in rider_stats.values():
        stats["score"] = stats["wins"] * 3 + stats["podiums"] * 1 + stats["type_wins"] * 2
        rows.append(stats)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df.sort_values("score", ascending=False).head(top_n).reset_index(drop=True)
    return df
```

### File: `raceanalyzer/demo.py` — Course coordinates and race type

Add course coordinate generation and race type assignment to the existing demo data generator.

```python
import math

from raceanalyzer.db.models import RaceType
from raceanalyzer.queries import infer_race_type

# --- PNW city center coordinates for route generation ---

PNW_CITY_COORDS: dict[str, tuple[float, float]] = {
    "Maryhill": (45.68, -120.85),
    "Niles": (45.52, -122.68),     # near Portland
    "Shelton": (47.21, -123.10),
    "Enumclaw": (47.20, -121.99),
    "Seattle": (47.61, -122.33),
    "Ridgefield": (45.81, -122.74),
    "Wenatchee": (47.42, -120.31),
    "Boise": (43.62, -116.21),
    "The Dalles": (45.60, -121.18),
    "Portland": (45.52, -122.68),
    "Redmond": (47.67, -122.12),
    "Hood River": (45.71, -121.52),
    "Medford": (42.33, -122.87),
    "Whidbey Island": (48.22, -122.68),
    "Twin Falls": (42.56, -114.46),
    "Vancouver": (49.28, -123.12),
    "Delta": (49.09, -123.06),
    "White Rock": (49.02, -122.80),
    "Baker City": (44.77, -117.83),
    "Bend": (44.06, -121.31),
    "Bainbridge Island": (47.63, -122.52),
}


def _generate_course_coords(
    location: str,
    race_type: RaceType,
    rng: random.Random,
) -> tuple[list[float], list[float]]:
    """Generate a plausible course polyline near a PNW city.

    Returns (latitudes, longitudes) as lists of ~12-20 floats.
    Route shape varies by race type:
    - Criterium: small rectangular loop
    - Road race: elongated out-and-back or loop
    - Hill climb: upward line (increasing lat variation)
    - Stage race: larger loop with waypoints
    - Time trial: straight-ish line
    - Gravel: irregular loop
    """
    center = PNW_CITY_COORDS.get(location, (47.0, -122.0))
    center_lat, center_lon = center

    lats = []
    lons = []

    if race_type == RaceType.CRITERIUM:
        # Small rectangular loop ~0.01 degree (~1km)
        scale = 0.008 + rng.uniform(0, 0.004)
        corners = [
            (0, 0), (scale, 0.2 * scale), (scale, scale),
            (0.2 * scale, scale * 1.1), (0, 0),
        ]
        for dlat, dlon in corners:
            lats.append(center_lat + dlat)
            lons.append(center_lon + dlon)
        # Add midpoints for smoother look
        smooth_lats, smooth_lons = [], []
        for i in range(len(lats) - 1):
            smooth_lats.append(lats[i])
            smooth_lons.append(lons[i])
            smooth_lats.append((lats[i] + lats[i + 1]) / 2 + rng.uniform(-0.001, 0.001))
            smooth_lons.append((lons[i] + lons[i + 1]) / 2 + rng.uniform(-0.001, 0.001))
        smooth_lats.append(lats[-1])
        smooth_lons.append(lons[-1])
        lats, lons = smooth_lats, smooth_lons

    elif race_type == RaceType.HILL_CLIMB:
        # Upward line with slight winding, ~0.05 degree (~5km)
        num_points = 15
        for i in range(num_points):
            t = i / (num_points - 1)
            lats.append(center_lat + t * 0.04 + rng.uniform(-0.002, 0.002))
            lons.append(center_lon + t * 0.01 + rng.uniform(-0.003, 0.003))

    elif race_type == RaceType.TIME_TRIAL:
        # Straight-ish out-and-back
        num_points = 10
        for i in range(num_points):
            t = i / (num_points - 1)
            lats.append(center_lat + t * 0.03 + rng.uniform(-0.001, 0.001))
            lons.append(center_lon + t * 0.02 + rng.uniform(-0.001, 0.001))

    elif race_type == RaceType.STAGE_RACE:
        # Larger irregular loop with ~15 waypoints
        num_points = 16
        for i in range(num_points):
            angle = 2 * math.pi * i / (num_points - 1)
            radius_lat = 0.06 + rng.uniform(-0.02, 0.02)
            radius_lon = 0.08 + rng.uniform(-0.02, 0.02)
            lats.append(center_lat + radius_lat * math.sin(angle))
            lons.append(center_lon + radius_lon * math.cos(angle))
        lats.append(lats[0])
        lons.append(lons[0])

    elif race_type == RaceType.GRAVEL:
        # Irregular loop with more variation
        num_points = 14
        for i in range(num_points):
            angle = 2 * math.pi * i / (num_points - 1)
            radius = 0.03 + rng.uniform(-0.01, 0.015)
            lats.append(center_lat + radius * math.sin(angle) + rng.uniform(-0.005, 0.005))
            lons.append(center_lon + radius * 1.3 * math.cos(angle) + rng.uniform(-0.005, 0.005))
        lats.append(lats[0])
        lons.append(lons[0])

    else:  # ROAD_RACE (default)
        # Elongated loop ~0.04 degree (~4km)
        num_points = 14
        for i in range(num_points):
            angle = 2 * math.pi * i / (num_points - 1)
            radius_lat = 0.03 + rng.uniform(-0.005, 0.005)
            radius_lon = 0.05 + rng.uniform(-0.01, 0.01)
            lats.append(center_lat + radius_lat * math.sin(angle))
            lons.append(center_lon + radius_lon * math.cos(angle))
        lats.append(lats[0])
        lons.append(lons[0])

    return lats, lons


def _coords_to_text(coords: list[float]) -> str:
    """Convert list of floats to comma-separated string for DB storage."""
    return ",".join(f"{c:.5f}" for c in coords)
```

Then in `generate_demo_data`, where we create each Race object, add:

```python
            race_type = infer_race_type(race_name)
            course_lats, course_lons = _generate_course_coords(
                location, race_type, random.Random(race_id),
            )

            race = Race(
                id=race_id,
                name=race_name,
                date=race_date,
                location=location,
                state_province=state,
                url=f"https://www.road-results.com/Race/{race_id}",
                race_type=race_type,
                course_lat=_coords_to_text(course_lats),
                course_lon=_coords_to_text(course_lons),
            )
```

### File: `raceanalyzer/ui/components.py` — Tile, icon, and scary racer rendering

```python
import math
from typing import Optional

import plotly.graph_objects as go


# --- Race type SVG icons (24x24) ---

RACE_TYPE_ICONS: dict[str, str] = {
    "criterium": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<rect x="3" y="3" width="18" height="18" rx="3" fill="none" stroke="#E53935" '
        'stroke-width="2"/>'
        '<path d="M7 7 L17 7 L17 17 L7 17 Z" fill="none" stroke="#E53935" stroke-width="1.5" '
        'stroke-dasharray="2,1"/>'
        '<circle cx="12" cy="12" r="2" fill="#E53935"/>'
        '</svg>'
    ),
    "road_race": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<path d="M3 18 Q8 6 12 12 Q16 18 21 6" fill="none" stroke="#1E88E5" '
        'stroke-width="2" stroke-linecap="round"/>'
        '</svg>'
    ),
    "hill_climb": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<path d="M2 20 L10 8 L15 14 L22 4" fill="none" stroke="#43A047" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        '<polygon points="22,4 22,8 18,8" fill="#43A047" opacity="0.5"/>'
        '</svg>'
    ),
    "stage_race": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="6" cy="12" r="3" fill="none" stroke="#FB8C00" stroke-width="1.5"/>'
        '<circle cx="12" cy="8" r="3" fill="none" stroke="#FB8C00" stroke-width="1.5"/>'
        '<circle cx="18" cy="14" r="3" fill="none" stroke="#FB8C00" stroke-width="1.5"/>'
        '<path d="M8.5 10.5 L10 9.5 M14 10 L16 12.5" stroke="#FB8C00" stroke-width="1.5"/>'
        '</svg>'
    ),
    "time_trial": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="12" cy="12" r="9" fill="none" stroke="#8E24AA" stroke-width="2"/>'
        '<line x1="12" y1="12" x2="12" y2="6" stroke="#8E24AA" stroke-width="2" '
        'stroke-linecap="round"/>'
        '<line x1="12" y1="12" x2="16" y2="12" stroke="#8E24AA" stroke-width="1.5" '
        'stroke-linecap="round"/>'
        '</svg>'
    ),
    "gravel": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<path d="M3 18 Q6 10 10 14 Q14 18 18 10 Q20 6 21 8" fill="none" stroke="#6D4C41" '
        'stroke-width="2" stroke-linecap="round"/>'
        '<circle cx="6" cy="16" r="1" fill="#6D4C41" opacity="0.4"/>'
        '<circle cx="14" cy="11" r="1" fill="#6D4C41" opacity="0.4"/>'
        '<circle cx="19" cy="13" r="1" fill="#6D4C41" opacity="0.4"/>'
        '</svg>'
    ),
}

RACE_TYPE_COLORS = {
    "criterium": "#E53935",
    "road_race": "#1E88E5",
    "hill_climb": "#43A047",
    "stage_race": "#FB8C00",
    "time_trial": "#8E24AA",
    "gravel": "#6D4C41",
}


def render_race_type_icon(race_type: Optional[str]):
    """Render an inline SVG icon for the race type."""
    if race_type and race_type in RACE_TYPE_ICONS:
        st.markdown(RACE_TYPE_ICONS[race_type], unsafe_allow_html=True)
    else:
        # Fallback: generic bike icon placeholder
        st.markdown(
            '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
            '<circle cx="12" cy="12" r="8" fill="none" stroke="#9E9E9E" stroke-width="2"/>'
            '<text x="12" y="16" text-anchor="middle" font-size="10" fill="#9E9E9E">?</text>'
            '</svg>',
            unsafe_allow_html=True,
        )


def render_race_tile(tile_row: dict, key_prefix: str = "tile"):
    """Render a single race tile in a styled container.

    tile_row should have: id, name, date, location, state_province,
    race_type, course_lat, course_lon, num_categories.
    """
    race_type = tile_row.get("race_type")
    color = RACE_TYPE_COLORS.get(race_type, "#9E9E9E")

    with st.container(border=True):
        # Header row: icon + name
        icon_col, name_col = st.columns([1, 5])
        with icon_col:
            render_race_type_icon(race_type)
        with name_col:
            st.markdown(f"**{tile_row['name']}**")

        # Mini course map
        course_lat = tile_row.get("course_lat")
        course_lon = tile_row.get("course_lon")
        if course_lat and course_lon:
            fig = _build_mini_course_map(course_lat, course_lon, color)
            st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_map_{tile_row['id']}")

        # Footer: date, location, type badge
        date_str = ""
        if tile_row.get("date"):
            try:
                date_str = f"{tile_row['date']:%b %d, %Y}"
            except (TypeError, ValueError):
                date_str = str(tile_row["date"])

        location = tile_row.get("location", "")
        state = tile_row.get("state_province", "")
        loc_str = f"{location}, {state}" if state else location

        type_label = race_type_display_name(race_type) if race_type else "Race"
        badge_html = (
            f'<span style="background-color:{color};color:white;padding:1px 6px;'
            f'border-radius:3px;font-size:0.75em;">{type_label}</span>'
        )

        st.markdown(
            f'<div style="font-size:0.85em;color:#666;">{date_str} &middot; {loc_str}</div>'
            f'<div style="margin-top:4px;">{badge_html}</div>',
            unsafe_allow_html=True,
        )

        # Navigation button
        if st.button("View Details", key=f"{key_prefix}_btn_{tile_row['id']}"):
            st.session_state["selected_race_id"] = int(tile_row["id"])
            st.query_params["race_id"] = str(tile_row["id"])
            st.switch_page("pages/race_detail.py")


def _parse_coords(text: str) -> list[float]:
    """Parse comma-separated coordinate string to list of floats."""
    return [float(x) for x in text.split(",") if x.strip()]


def _build_mini_course_map(
    course_lat: str,
    course_lon: str,
    color: str = "#1E88E5",
) -> go.Figure:
    """Build a small static Plotly figure showing the course outline.

    No map tiles — just the route shape on a white background.
    """
    lats = _parse_coords(course_lat)
    lons = _parse_coords(course_lon)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=lons,
        y=lats,
        mode="lines",
        line=dict(color=color, width=2.5),
        hoverinfo="skip",
    ))
    # Start/finish marker
    if lats and lons:
        fig.add_trace(go.Scatter(
            x=[lons[0]],
            y=[lats[0]],
            mode="markers",
            marker=dict(color=color, size=6),
            hoverinfo="skip",
        ))

    fig.update_layout(
        height=120,
        margin=dict(t=5, b=5, l=5, r=5),
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
        yaxis=dict(visible=False),
        showlegend=False,
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return fig


# --- Scary Racer rendering ---

_THREAT_LEVELS = [
    (15, "Apex Predator", "red"),
    (10, "Very Dangerous", "orange"),
    (5, "Dangerous", "#FFC107"),
    (0, "One to Watch", "gray"),
]


def render_scary_racer_card(racer: dict):
    """Render a single scary racer card.

    racer dict keys: name, team, wins, podiums, type_wins, score.
    """
    score = racer.get("score", 0)
    threat_label = "One to Watch"
    threat_color = "gray"
    for threshold, label, color in _THREAT_LEVELS:
        if score >= threshold:
            threat_label = label
            threat_color = color
            break

    badge_html = (
        f'<span style="background-color:{threat_color};color:white;padding:2px 8px;'
        f'border-radius:4px;font-size:0.8em;">{threat_label}</span>'
    )

    name = racer.get("name", "Unknown")
    team = racer.get("team", "")
    team_str = f" ({team})" if team else ""

    st.markdown(
        f"**{name}**{team_str} {badge_html}",
        unsafe_allow_html=True,
    )
    st.caption(
        f"Score: {score} | "
        f"Wins: {racer.get('wins', 0)} | "
        f"Podiums: {racer.get('podiums', 0)} | "
        f"Type wins: {racer.get('type_wins', 0)}"
    )
```

The import for `race_type_display_name` comes from `raceanalyzer.queries`.

### File: `raceanalyzer/ui/pages/calendar.py` — Tile grid

```python
"""Race Calendar page -- visual tile grid of all PNW races."""

from __future__ import annotations

import streamlit as st

from raceanalyzer import queries
from raceanalyzer.ui.components import render_empty_state, render_race_tile, render_sidebar_filters

TILES_PER_PAGE = 12


def render():
    session = st.session_state.db_session
    filters = render_sidebar_filters(session)

    st.title("PNW Race Calendar")

    df = queries.get_race_tiles(session, year=filters["year"], states=filters["states"])

    if df.empty:
        render_empty_state(
            "No races found. Try adjusting your filters or run "
            "`raceanalyzer scrape` to import data."
        )
        return

    # Metrics row
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Races", len(df))
    col2.metric("States/Provinces", df["state_province"].nunique())
    dated = df[df["date"].notna()]
    if not dated.empty:
        col3.metric(
            "Date Range",
            f"{dated['date'].min():%b %Y} -- {dated['date'].max():%b %Y}",
        )

    # Pagination state
    if "tile_page_size" not in st.session_state:
        st.session_state.tile_page_size = TILES_PER_PAGE
    visible_count = st.session_state.tile_page_size

    # Tile grid (3 columns)
    visible_df = df.head(visible_count)
    for row_start in range(0, len(visible_df), 3):
        cols = st.columns(3)
        for col_idx in range(3):
            idx = row_start + col_idx
            if idx < len(visible_df):
                with cols[col_idx]:
                    tile_data = visible_df.iloc[idx].to_dict()
                    render_race_tile(tile_data, key_prefix=f"cal_{idx}")

    # Show more button
    if visible_count < len(df):
        remaining = len(df) - visible_count
        if st.button(f"Show more ({remaining} remaining)"):
            st.session_state.tile_page_size = visible_count + TILES_PER_PAGE
            st.rerun()


render()
```

### File: `raceanalyzer/ui/pages/race_detail.py` — Add Scary Racers section

Add the following after the existing classifications section (after the `for _, row in classifications.iterrows()` loop):

```python
    # --- Scary Racers Section ---
    st.divider()
    st.subheader("Scary Racers")
    st.caption(
        "Predicted top performers based on historical results. "
        "Riders who win races of the same type score even higher."
    )

    if classifications.empty:
        st.info("No categories available for scary racer analysis.")
    else:
        for _, cls_row in classifications.iterrows():
            category = cls_row["category"]
            scary_df = queries.get_scary_racers(session, race_id, category)

            if scary_df.empty:
                continue

            with st.expander(f"Scary Racers: {category}", expanded=True):
                for _, racer in scary_df.iterrows():
                    render_scary_racer_card(racer.to_dict())
                    st.markdown("---")
```

The import line at the top adds `render_scary_racer_card`:

```python
from raceanalyzer.ui.components import (
    render_confidence_badge,
    render_empty_state,
    render_scary_racer_card,
)
```

### File: `tests/test_race_type.py` — Race type inference tests

```python
"""Tests for race type inference from race names."""

from __future__ import annotations

from raceanalyzer.db.models import RaceType
from raceanalyzer.queries import infer_race_type


class TestInferRaceType:
    def test_criterium_from_name(self):
        assert infer_race_type("Cherry Pie Criterium") == RaceType.CRITERIUM
        assert infer_race_type("Seward Park Criterium") == RaceType.CRITERIUM
        assert infer_race_type("PIR Short Track Criterium") == RaceType.CRITERIUM

    def test_grand_prix_is_criterium(self):
        assert infer_race_type("Gastown Grand Prix") == RaceType.CRITERIUM
        assert infer_race_type("Marymoor Grand Prix") == RaceType.CRITERIUM

    def test_stage_race_from_name(self):
        assert infer_race_type("Mutual of Enumclaw Stage Race") == RaceType.STAGE_RACE
        assert infer_race_type("Tour de Bloom Stage Race") == RaceType.STAGE_RACE
        assert infer_race_type("Tour de Delta") == RaceType.STAGE_RACE

    def test_hill_climb_from_name(self):
        assert infer_race_type("Mount Tabor Hill Climb") == RaceType.HILL_CLIMB

    def test_gravel_from_name(self):
        assert infer_race_type("Gorge Roubaix") == RaceType.GRAVEL

    def test_road_race_default(self):
        assert infer_race_type("Banana Belt Road Race") == RaceType.ROAD_RACE
        assert infer_race_type("Mason Lake Road Race") == RaceType.ROAD_RACE
        assert infer_race_type("Some Unknown Race") == RaceType.ROAD_RACE

    def test_case_insensitive(self):
        assert infer_race_type("TWILIGHT CRITERIUM") == RaceType.CRITERIUM
        assert infer_race_type("mount baker hill climb") == RaceType.HILL_CLIMB

    def test_all_pnw_races_classified(self):
        """Every race in the demo list gets a non-None type."""
        from raceanalyzer.demo import PNW_RACES

        for name, _, _ in PNW_RACES:
            result = infer_race_type(name)
            assert result is not None
            assert isinstance(result, RaceType)

    def test_expected_distribution(self):
        """The 25 PNW race names should produce a reasonable distribution."""
        from raceanalyzer.demo import PNW_RACES

        types = [infer_race_type(name) for name, _, _ in PNW_RACES]
        assert types.count(RaceType.CRITERIUM) >= 6  # Many crits in PNW
        assert types.count(RaceType.ROAD_RACE) >= 4
        assert types.count(RaceType.STAGE_RACE) >= 2
        assert types.count(RaceType.HILL_CLIMB) >= 1
```

### File: `tests/test_scary_racers.py` — Scoring algorithm tests

```python
"""Tests for Scary Racers scoring and ranking."""

from __future__ import annotations

from datetime import datetime

from raceanalyzer.db.models import (
    Base,
    Race,
    RaceClassification,
    RaceType,
    Result,
    Rider,
)
from raceanalyzer.queries import get_scary_racers


def _seed_rider_history(session, race_type=RaceType.CRITERIUM):
    """Create a minimal dataset with known rider histories for scoring tests."""
    # Two riders: Alice (strong) and Bob (moderate)
    alice = Rider(id=1, name="Alice Strong")
    bob = Rider(id=2, name="Bob Decent")
    session.add_all([alice, bob])
    session.flush()

    # 3 past crit races where Alice won and Bob placed
    for i in range(3):
        race = Race(
            id=100 + i,
            name=f"Past Crit {i}",
            date=datetime(2023, 3 + i, 1),
            race_type=RaceType.CRITERIUM,
        )
        session.add(race)
        session.flush()

        # Alice: 1st place in all 3
        session.add(Result(
            race_id=race.id, rider_id=alice.id, name="Alice Strong",
            place=1, race_category_name="Men Pro/1/2", dnf=False,
            field_size=20,
        ))
        # Bob: 2nd in first, 3rd in second, 5th in third
        session.add(Result(
            race_id=race.id, rider_id=bob.id, name="Bob Decent",
            place=[2, 3, 5][i], race_category_name="Men Pro/1/2", dnf=False,
            field_size=20,
        ))

    # 1 road race where Bob won
    road_race = Race(
        id=200, name="Road Classic", date=datetime(2023, 7, 1),
        race_type=RaceType.ROAD_RACE,
    )
    session.add(road_race)
    session.flush()
    session.add(Result(
        race_id=road_race.id, rider_id=bob.id, name="Bob Decent",
        place=1, race_category_name="Men Pro/1/2", dnf=False,
        field_size=15,
    ))

    # Target race (upcoming crit)
    target = Race(
        id=300, name="Upcoming Crit", date=datetime(2024, 5, 1),
        race_type=RaceType.CRITERIUM,
    )
    session.add(target)
    session.commit()

    return target.id


class TestScaryRacerScoring:
    def test_higher_wins_rank_first(self, session):
        target_id = _seed_rider_history(session)
        df = get_scary_racers(session, target_id, "Men Pro/1/2")

        assert len(df) == 2
        assert df.iloc[0]["name"] == "Alice Strong"
        assert df.iloc[1]["name"] == "Bob Decent"

    def test_score_calculation(self, session):
        target_id = _seed_rider_history(session)
        df = get_scary_racers(session, target_id, "Men Pro/1/2")

        alice = df[df["name"] == "Alice Strong"].iloc[0]
        # Alice: 3 wins * 3 + 3 podiums * 1 + 3 type_wins (all crits) * 2 = 9 + 3 + 6 = 18
        assert alice["wins"] == 3
        assert alice["podiums"] == 3
        assert alice["type_wins"] == 3
        assert alice["score"] == 18

    def test_race_type_bonus_for_matching_type(self, session):
        target_id = _seed_rider_history(session)
        df = get_scary_racers(session, target_id, "Men Pro/1/2")

        bob = df[df["name"] == "Bob Decent"].iloc[0]
        # Bob: 1 road win + 0 crit wins = 1 win total
        # Podiums: place 2 + place 3 = 2 podiums (from crits), plus 1 road win podium = 3
        # Type wins (crit-specific): 0 (his win was a road race)
        # Score: 1*3 + 3*1 + 0*2 = 6
        assert bob["wins"] == 1
        assert bob["type_wins"] == 0  # His win was road race, not crit
        assert bob["score"] == 6

    def test_empty_for_unknown_category(self, session):
        target_id = _seed_rider_history(session)
        df = get_scary_racers(session, target_id, "Women Cat 4")
        assert df.empty

    def test_empty_for_missing_race(self, session):
        df = get_scary_racers(session, 99999, "Men Pro/1/2")
        assert df.empty

    def test_top_n_limits_results(self, session):
        target_id = _seed_rider_history(session)
        df = get_scary_racers(session, target_id, "Men Pro/1/2", top_n=1)
        assert len(df) == 1
        assert df.iloc[0]["name"] == "Alice Strong"

    def test_dnf_results_excluded(self, session):
        """DNF results should not count toward scoring."""
        rider = Rider(id=10, name="DNF Dave")
        session.add(rider)
        session.flush()

        race = Race(
            id=400, name="Test Crit", date=datetime(2023, 6, 1),
            race_type=RaceType.CRITERIUM,
        )
        session.add(race)
        session.flush()

        session.add(Result(
            race_id=race.id, rider_id=rider.id, name="DNF Dave",
            place=None, race_category_name="Men Cat 3", dnf=True,
            field_size=20,
        ))

        target = Race(
            id=401, name="Next Crit", date=datetime(2024, 6, 1),
            race_type=RaceType.CRITERIUM,
        )
        session.add(target)
        session.commit()

        df = get_scary_racers(session, target.id, "Men Cat 3")
        assert df.empty  # DNF Dave has no valid results
```

### File: `tests/test_queries.py` — Tile query tests (additions)

```python
class TestGetRaceTiles:
    def test_returns_tile_columns(self, session):
        generate_demo_data(session, num_races=5, seed=42)
        df = queries.get_race_tiles(session)
        expected_cols = {
            "id", "name", "date", "location", "state_province",
            "race_type", "course_lat", "course_lon", "num_categories",
        }
        assert expected_cols == set(df.columns)

    def test_race_type_populated(self, session):
        generate_demo_data(session, num_races=10, seed=42)
        df = queries.get_race_tiles(session)
        assert df["race_type"].notna().all()

    def test_course_coords_populated(self, session):
        generate_demo_data(session, num_races=5, seed=42)
        df = queries.get_race_tiles(session)
        assert df["course_lat"].notna().all()
        assert df["course_lon"].notna().all()

    def test_year_filter(self, session):
        generate_demo_data(session, num_races=50, seed=42)
        df = queries.get_race_tiles(session, year=2023)
        years = df["date"].dt.year.unique()
        assert all(y == 2023 for y in years)

    def test_state_filter(self, session):
        generate_demo_data(session, num_races=50, seed=42)
        df = queries.get_race_tiles(session, states=["WA"])
        assert all(s == "WA" for s in df["state_province"])

    def test_empty_db(self, session):
        df = queries.get_race_tiles(session)
        assert df.empty
        assert "race_type" in df.columns
```

---

## Files Summary

| File | Action | Description |
|------|--------|-------------|
| `raceanalyzer/db/models.py` | **Modify** | Add `RaceType` enum, `race_type`/`course_lat`/`course_lon` columns to Race |
| `raceanalyzer/queries.py` | **Modify** | Add `infer_race_type()`, `get_race_tiles()`, `get_scary_racers()`, `race_type_display_name()` |
| `raceanalyzer/demo.py` | **Modify** | Add `PNW_CITY_COORDS`, `_generate_course_coords()`, `_coords_to_text()`, assign race_type and course coords during generation |
| `raceanalyzer/ui/components.py` | **Modify** | Add `RACE_TYPE_ICONS`, `render_race_type_icon()`, `render_race_tile()`, `_build_mini_course_map()`, `render_scary_racer_card()` |
| `raceanalyzer/ui/pages/calendar.py` | **Modify** | Replace table with 3-wide tile grid using `get_race_tiles()` + `render_race_tile()`, add pagination |
| `raceanalyzer/ui/pages/race_detail.py` | **Modify** | Add Scary Racers section after classifications |
| `tests/test_race_type.py` | **Create** | 9 tests for race type inference |
| `tests/test_scary_racers.py` | **Create** | 7 tests for scoring algorithm |
| `tests/test_queries.py` | **Modify** | 6 tests for `get_race_tiles()` |

**Total new files**: 2
**Total modified files**: 7
**Estimated new test count**: ~22

---

## Definition of Done

1. Calendar page shows a 3-wide grid of race tiles instead of a data table
2. Each tile displays: race name, date, location, race type icon (6 distinct types), and a mini course map
3. Clicking a tile's "View Details" button navigates to that race's detail page
4. Race detail page includes a "Scary Racers" section per category showing top 5 predicted performers
5. Scary Racers scoring uses: `wins * 3 + podiums * 1 + same_type_wins * 2`
6. All 6 race types have distinct inline SVG icons with unique colors
7. Mini course maps render as static Plotly line charts (no Mapbox token needed)
8. Demo data generator produces course coordinates (10-20 points per route) and assigns race_type
9. Race type is inferred from race name — crits, stage races, hill climbs, gravel, time trials, and road races (default) are all handled
10. Tile grid paginates at 12 tiles with "Show more" button
11. Dashboard page still works (no regressions)
12. All existing 119 tests pass
13. New tests pass: race type inference (~9), scary racer scoring (~7), tile queries (~6)
14. Python 3.9 compatible: `from __future__ import annotations` in all new/modified files
15. No new external dependencies — uses existing streamlit, plotly, sqlalchemy, pandas

---

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Mini course maps slow to render for 50+ races | Laggy calendar page | Medium | Pagination caps at 12 visible tiles; maps are minimal Plotly figures (no map tiles); can lazy-load if needed |
| Inline SVG icons not rendering in some Streamlit versions | Missing icons | Low | `unsafe_allow_html=True` is well-supported in Streamlit 1.36+; fallback to text labels if needed |
| `st.button` inside a loop creates key uniqueness issues | Broken navigation | Low | Each button has a unique key using `f"{prefix}_{idx}"` pattern |
| Race type inference misclassifies ambiguous names | Wrong icon shown | Low | Keyword patterns are conservative; "Oregon Trail Classic" → road_race (correct default); can add manual overrides |
| Schema migration needed if real data existed | Data loss | Very Low | All new columns are nullable; currently demo-only data; `seed-demo` auto-clears and regenerates |
| Scary Racer scoring too simplistic — everyone has similar scores | Uninformative rankings | Medium | Demo data naturally creates varied histories since riders are randomly sampled per field; scoring weights are tuned to create spread |
| `st.switch_page` path must match actual file location | Broken navigation | Low | Existing calendar.py already uses this pattern successfully |

---

## Open Questions — Resolved

1. **What race types should exist?** → **6 types**: `criterium`, `road_race`, `hill_climb`, `stage_race`, `time_trial`, `gravel`. This covers the PNW scene well. The 25 demo race names map to: ~10 criteriums, ~7 road races, ~4 stage races, 1 hill climb, 1 gravel, 0 time trials (type exists for future real data). "Tour de Whidbey" and "Oregon Trail Classic" classify as road_race (the default), which is correct for those events.

2. **Should course maps be interactive or static?** → **Static thumbnails.** Plotly `go.Scatter` on a white background with route shape only. No map tiles, no zoom/pan, no Mapbox token. This is fast, simple, and gives the visual "route shape at a glance" effect like Strava thumbnails. Interactive maps can be a future enhancement on the detail page.

3. **How to generate PNW course coordinates?** → **Algorithmic routes near real city coordinates.** Each of the 21 locations has hardcoded lat/lon. Route shape varies by race type: small loops for crits, elongated loops for road races, upward lines for hill climbs, large loops for stage races. Each route gets 10-20 points with controlled randomness seeded per race_id for determinism.

4. **Scary Racer scoring formula?** → **Simple weighted sum: `wins * 3 + podiums * 1 + same_type_wins * 2`.** Explainable, testable, creates meaningful differentiation. The race_type_bonus (2 points per win in the same race type) is the key distinguishing feature — it means a crit specialist scores higher in another crit. Elo-style ratings are deferred to a future sprint.

5. **Should race type be a DB column or derived at query time?** → **DB column.** Stored on Race as `race_type` (nullable `SAEnum(RaceType)`). Inferred once from the name via `infer_race_type()` during demo data generation (or scraping in the future). Avoids repeated string matching at query time and enables future manual overrides.

6. **Do we need a Mapbox token?** → **No.** We use plain Plotly `go.Scatter` (not scattermapbox). The route is drawn as an x/y line chart with hidden axes and a white background. This shows the course shape clearly without any tile server.

7. **Icon format?** → **Inline SVG via `st.markdown(unsafe_allow_html=True)`.** Each race type gets a 24x24 SVG with a distinct color. SVGs are hardcoded strings in `components.py` — no external files. Colors: criterium (red), road_race (blue), hill_climb (green), stage_race (orange), time_trial (purple), gravel (brown).

8. **Should the tile grid be paginated?** → **Yes, simple "Show More" pagination.** Start with 12 tiles (4 rows of 3), show a "Show more (N remaining)" button. Uses `st.session_state` to track how many to display. Avoids rendering 50+ mini maps on initial load. No infinite scroll (not natively supported in Streamlit).
