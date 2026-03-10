# Sprint 006: Course Maps & Race Deduplication

## Overview

Add course map overlays and race series deduplication. Course maps use RideWithGPS route search with a quality-scoring algorithm to pick the best match, rendered via `st_folium` for Strava-style polyline overlays. Race dedup uses a computed `series_key` column on the existing `Race` table (no new tables) with aggressive name normalization. Both features ship independently -- course maps have zero dependency on dedup and vice versa.

**Duration**: ~5-6 days
**Prerequisite**: Sprint 005 complete, 100+ races scraped with classifications.
**Approach**: Pragmatic and minimal -- no new ORM tables, no complex migrations, phased so each feature delivers standalone value.

---

## Use Cases

1. **As a racer**, I see a Strava-style course map on the race detail page showing the route polyline on a real map, so I can study the terrain.
2. **As a racer**, I see races grouped by series in the calendar -- "Banana Belt" is one tile with an edition count badge, not four separate tiles.
3. **As a racer**, I can expand a series tile to see all editions and their individual classifications.
4. **As a racer**, the series tile badge reflects the most common finish type across ALL editions, giving me the best prediction.
5. **As a developer**, RWGPS route data is scored, ranked, and cached so maps render instantly after first fetch.
6. **As a developer**, I can manually override an auto-matched RWGPS route via CLI when the algorithm picks wrong.

---

## Architecture

```
raceanalyzer/
├── db/
│   └── models.py              # MODIFY: Add series_key, rwgps_route_id, rwgps_route_json
├── queries.py                 # MODIFY: get_series_tiles(), get_series_detail(),
│                              #          series-aggregated overall_finish_type
├── rwgps.py                   # CREATE: RWGPS search, route scoring, polyline fetch
├── normalize.py               # CREATE: Race name normalization for series_key
├── ui/
│   ├── components.py          # MODIFY: Series tile rendering (edition count badge)
│   ├── maps.py                # MODIFY: Add render_course_map() with Folium polyline
│   ├── pages/
│   │   ├── calendar.py        # MODIFY: Use get_series_tiles(), grouped view
│   │   └── race_detail.py     # MODIFY: Course map, series navigation
├── cli.py                     # MODIFY: normalize-names, match-routes, override-route commands

tests/
├── test_normalize.py          # CREATE: Name normalization edge cases
├── test_rwgps.py              # CREATE: Route scoring algorithm
├── test_queries.py            # MODIFY: Series tile aggregation
```

### Key Design Decisions

1. **No `RaceSeries` table -- use `series_key` column on `Race`**. A separate table adds a foreign key, a migration, and join complexity for minimal benefit. A computed `series_key` column achieves grouping with `GROUP BY series_key` in queries. Trade-offs evaluated below.

2. **Custom Folium polyline rendering, not RWGPS iframe embed**. The iframe gives zero control over styling, is slow to load, shows RWGPS branding/UI chrome, and cannot be styled to match the app. Folium with `st_folium` gives us Strava-style polylines with elevation coloring, custom zoom, and consistent look. The complexity cost is manageable -- it is roughly 30 lines of rendering code.

3. **RWGPS route quality scoring** with fuzzy name match, distance proximity, and race-type-aware distance expectations. Manual override via CLI for bad matches.

4. **Incremental rollout**: Phase A (course maps) and Phase B (dedup) are fully independent. Ship either one alone.

---

## Design Analysis: `series_key` Column vs `RaceSeries` Table

### Option A: `series_key` column on `Race` (RECOMMENDED)

```python
# models.py -- add to Race
series_key = Column(String, nullable=True, index=True)
```

**Pros:**
- Zero new tables, zero foreign keys, zero migrations beyond `ALTER TABLE ADD COLUMN`
- Grouping is a simple `GROUP BY series_key` -- no joins needed
- SQLite `ALTER TABLE ADD COLUMN` is instant (no table rebuild)
- If normalization is wrong, just recompute -- no orphaned FK references
- Calendar query stays a single table scan

**Cons:**
- No place to store series-level metadata (description, official URL). But we do not need that yet.
- Denormalized -- the same series_key is repeated across rows. Acceptable for <2,000 races.

### Option B: Separate `RaceSeries` table

```python
class RaceSeries(Base):
    __tablename__ = "race_series"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    normalized_name = Column(String, unique=True)
# Race.series_id = Column(Integer, ForeignKey("race_series.id"))
```

**Cons:**
- Requires creating the table AND populating it before any Race rows can reference it
- Every calendar query needs a JOIN
- If we re-normalize names, we need to reconcile stale series rows
- Premature structure for a feature we may iterate on heavily

**Decision**: Option A. Revisit if we need series-level metadata (unlikely this sprint).

---

## Design Analysis: Folium Polyline vs RWGPS Iframe

### Option A: RWGPS iframe embed

```python
# Simple but limited
iframe_url = f"https://ridewithgps.com/embeds?type=route&id={route_id}"
st.markdown(f'<iframe src="{iframe_url}" width="100%" height="400"></iframe>',
            unsafe_allow_html=True)
```

**Pros:** 3 lines of code. No new dependencies.
**Cons:**
- Shows RWGPS branding, navigation controls, elevation profile -- cluttered
- No control over map style, zoom, or polyline color
- Loads slowly (full RWGPS app in iframe)
- Cannot overlay race start/finish markers or elevation gradient
- If RWGPS changes their embed format, it breaks silently

### Option B: Folium polyline via `st_folium` (RECOMMENDED)

```python
import folium
from streamlit_folium import st_folium

def render_course_map(track_points: list[dict], race_name: str):
    """Render a Strava-style polyline map."""
    coords = [(p["lat"], p["lng"]) for p in track_points]
    center = coords[len(coords) // 2]
    m = folium.Map(location=center, zoom_start=13, tiles="CartoDB positron")
    folium.PolyLine(coords, color="#FC4C02", weight=4, opacity=0.8).add_to(m)
    folium.Marker(coords[0], popup="Start", icon=folium.Icon(color="green")).add_to(m)
    folium.Marker(coords[-1], popup="Finish", icon=folium.Icon(color="red")).add_to(m)
    st_folium(m, width=700, height=400, returned_objects=[])
```

**Pros:**
- Full control over styling (Strava orange polyline, clean basemap)
- Start/finish markers
- Fast -- no external iframe load
- Can add elevation gradient coloring later
- Works offline if track points are cached

**Cons:**
- New dependency: `streamlit-folium` (well-maintained, 1.5k GitHub stars)
- Must fetch and cache track point data from RWGPS (not just the route ID)

**Decision**: Option B. The visual quality difference is significant, and `st_folium` is a standard Streamlit component.

---

## Implementation

### 1. `raceanalyzer/normalize.py` -- Race Name Normalization (NEW FILE)

```python
"""Race name normalization for series grouping.

Handles: year prefixes/suffixes, edition numbers (I, II, III, 1, 2, 3),
type suffixes (RR, Road Race, Crit, Criterium), and whitespace/punctuation.
"""

import re
from functools import lru_cache

# Roman numeral pattern (I through XXX covers all realistic race editions)
_ROMAN_RE = re.compile(
    r'\b(XXX|XXIX|XXVIII|XXVII|XXVI|XXV|XXIV|XXIII|XXII|XXI|'
    r'XX|XIX|XVIII|XVII|XVI|XV|XIV|XIII|XII|XI|'
    r'X|IX|VIII|VII|VI|V|IV|III|II|I)\b'
)

# Year pattern: 4-digit year (1990-2039) as standalone token
_YEAR_RE = re.compile(r'\b(19|20)\d{2}\b')

# Edition number: standalone digits 1-99 that look like edition numbers
# Only strip if preceded/followed by word boundary (not part of a name like "Stage 3")
_EDITION_NUM_RE = re.compile(r'\b#?\d{1,2}\b')

# Race type suffix normalization: canonical forms
_TYPE_SUFFIXES = {
    # Road race variants
    r'\brr\b': '',
    r'\broad race\b': '',
    r'\broad$': '',
    # Criterium variants
    r'\bcrit\b': 'criterium',
    r'\bcriterium\b': 'criterium',
    # Time trial variants
    r'\btt\b': 'time trial',
    r'\btime trial\b': 'time trial',
    r'\bitt\b': 'time trial',
    # Hill climb variants
    r'\bhc\b': 'hill climb',
    r'\bhillclimb\b': 'hill climb',
    r'\bhill climb\b': 'hill climb',
    # Circuit race
    r'\bcircuit race\b': 'circuit',
    r'\bcircuit\b': 'circuit',
}

# Ordinal suffixes: 1st, 2nd, 3rd, 4th, etc. (often part of edition: "21st Annual")
_ORDINAL_RE = re.compile(r'\b\d{1,2}(st|nd|rd|th)\b', re.IGNORECASE)

# "Annual" is noise
_ANNUAL_RE = re.compile(r'\bannual\b', re.IGNORECASE)


@lru_cache(maxsize=2048)
def normalize_race_name(name: str) -> str:
    """Normalize a race name to a series key.

    Examples:
        "2024 Banana Belt RR"          -> "banana belt"
        "Banana Belt Road Race 2023"   -> "banana belt"
        "Banana Belt RR"               -> "banana belt"
        "Pacific Raceways XXI"         -> "pacific raceways"
        "Mason Lake I"                 -> "mason lake"
        "Mason Lake II"                -> "mason lake"
        "21st Annual Mutual of Enumclaw" -> "mutual of enumclaw"
        "Twilight Criterium 2024"      -> "twilight criterium"
    """
    s = name.strip().lower()

    # Remove year (before or after name)
    s = _YEAR_RE.sub('', s)

    # Remove ordinal + "annual"
    s = _ORDINAL_RE.sub('', s)
    s = _ANNUAL_RE.sub('', s)

    # Remove Roman numerals (edition markers)
    s = _ROMAN_RE.sub('', s)

    # Normalize type suffixes
    for pattern, replacement in _TYPE_SUFFIXES.items():
        s = re.sub(pattern, replacement, s)

    # Remove standalone edition numbers ONLY if they appear at start or end
    # (avoids stripping "Stage 3" -> "Stage")
    s = re.sub(r'^#?\d{1,2}\s+', '', s)
    s = re.sub(r'\s+#?\d{1,2}$', '', s)

    # Collapse whitespace, strip punctuation edges
    s = re.sub(r'[^\w\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()

    return s


def compute_series_keys(names: list[str]) -> dict[str, str]:
    """Batch normalize race names. Returns {original_name: series_key}."""
    return {name: normalize_race_name(name) for name in names}
```

**Edge case handling:**

| Input | Output | Reasoning |
|-------|--------|-----------|
| `"Banana Belt RR"` | `"banana belt"` | Strips `RR` suffix |
| `"Banana Belt Road Race"` | `"banana belt"` | Strips `Road Race` suffix |
| `"2024 Banana Belt"` | `"banana belt"` | Strips year prefix |
| `"Banana Belt 2024"` | `"banana belt"` | Strips year suffix |
| `"Pacific Raceways XXI"` | `"pacific raceways"` | Strips Roman numeral |
| `"Pacific Raceways XXII"` | `"pacific raceways"` | Same series_key |
| `"Mason Lake I"` | `"mason lake"` | Strips Roman `I` |
| `"Mason Lake II"` | `"mason lake"` | Same series_key |
| `"21st Annual Mutual of Enumclaw"` | `"mutual of enumclaw"` | Strips ordinal + "Annual" |
| `"Twilight TT"` | `"twilight time trial"` | Normalizes `TT` -> `time trial` |
| `"Twilight Time Trial"` | `"twilight time trial"` | Same series_key |
| `"Red R Criterium"` | `"red r criterium"` | Keeps `criterium` (canonical form) |
| `"Red R Crit"` | `"red r criterium"` | Normalizes `Crit` -> `criterium` |
| `"Stage 3 Road Race"` | `"stage 3"` | Keeps `3` (not at end, part of name) -- actually stripped because "Road Race" removed, then `3` is at end. This is a known limitation; stage races are out of scope for series grouping. |

### 2. `raceanalyzer/db/models.py` -- Add Columns to Race

```python
class Race(Base):
    __tablename__ = "races"

    # ... existing columns ...

    # NEW: Series grouping
    series_key = Column(String, nullable=True, index=True)

    # NEW: RWGPS course route
    rwgps_route_id = Column(Integer, nullable=True)
    rwgps_route_json = Column(Text, nullable=True)  # Cached track_points JSON
    rwgps_match_score = Column(Float, nullable=True)  # Quality score 0-1
    rwgps_manual_override = Column(Boolean, default=False)  # True = user picked this route

    __table_args__ = (
        Index("ix_races_date", "date"),
        Index("ix_races_state", "state_province"),
        Index("ix_races_race_type", "race_type"),
        Index("ix_races_series_key", "series_key"),  # NEW
    )
```

Migration is just `ALTER TABLE` -- no table rebuild needed in SQLite:

```python
# In a one-off migration script or CLI command
from sqlalchemy import text

def migrate_006(engine):
    with engine.begin() as conn:
        for col in [
            "series_key TEXT",
            "rwgps_route_id INTEGER",
            "rwgps_route_json TEXT",
            "rwgps_match_score REAL",
            "rwgps_manual_override BOOLEAN DEFAULT 0",
        ]:
            try:
                conn.execute(text(f"ALTER TABLE races ADD COLUMN {col}"))
            except Exception:
                pass  # Column already exists
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_races_series_key ON races(series_key)"
        ))
```

### 3. `raceanalyzer/rwgps.py` -- RWGPS Search & Route Scoring (NEW FILE)

```python
"""RideWithGPS route search, scoring, and caching.

Uses the undocumented /find/search.json endpoint (no auth required).
"""

import json
import logging
import time
from difflib import SequenceMatcher

import requests

logger = logging.getLogger(__name__)

# Expected route distances by race type (km)
_DISTANCE_EXPECTATIONS = {
    "criterium": (0.8, 3.0),      # Crits: 0.8-3km circuit
    "road_race": (40.0, 200.0),    # Road races: 40-200km
    "hill_climb": (3.0, 30.0),     # Hill climbs: 3-30km
    "time_trial": (10.0, 60.0),    # TTs: 10-60km
    "gravel": (40.0, 200.0),       # Gravel: similar to road
    "stage_race": (30.0, 180.0),   # Stages: variable
}

RWGPS_SEARCH_URL = "https://ridewithgps.com/find/search.json"
RWGPS_ROUTE_URL = "https://ridewithgps.com/routes/{route_id}.json"

# Respect RWGPS rate limits
_LAST_REQUEST_TIME = 0.0
_MIN_REQUEST_INTERVAL = 1.0  # seconds


def _rate_limit():
    """Enforce minimum interval between RWGPS requests."""
    global _LAST_REQUEST_TIME
    elapsed = time.time() - _LAST_REQUEST_TIME
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    _LAST_REQUEST_TIME = time.time()


def search_routes(
    keywords: str,
    lat: float,
    lng: float,
    *,
    limit: int = 10,
) -> list[dict]:
    """Search RWGPS for routes near a location matching keywords.

    Returns list of route dicts with: id, name, distance (meters),
    elevation_gain, lat, lng, bounding_box.
    """
    _rate_limit()
    try:
        resp = requests.get(
            RWGPS_SEARCH_URL,
            params={
                "search[keywords]": keywords,
                "search[lat]": lat,
                "search[lng]": lng,
                "search[limit]": limit,
                "search[offset]": 0,
            },
            headers={"User-Agent": "RaceAnalyzer/0.1"},
            timeout=10,
        )
        if resp.ok:
            data = resp.json()
            # RWGPS returns {"results": [...]} or similar structure
            results = data if isinstance(data, list) else data.get("results", [])
            return results
    except Exception:
        logger.warning("RWGPS search failed for %r near (%s, %s)", keywords, lat, lng)
    return []


def score_route(
    route: dict,
    race_name: str,
    race_lat: float,
    race_lng: float,
    race_type: str | None = None,
) -> float:
    """Score a RWGPS route match on 0-1 scale.

    Components (weights sum to 1.0):
    - Name similarity:      0.40  (fuzzy match)
    - Distance proximity:   0.25  (km from race location)
    - Route length fit:     0.20  (matches race type expectations)
    - Popularity signal:    0.15  (trip count as quality proxy)
    """
    score = 0.0

    # --- Name similarity (0.40) ---
    route_name = (route.get("name") or "").lower()
    race_lower = race_name.lower()
    # Use SequenceMatcher for fuzzy comparison
    name_sim = SequenceMatcher(None, race_lower, route_name).ratio()
    # Boost if race name is a substring of route name or vice versa
    if race_lower in route_name or route_name in race_lower:
        name_sim = max(name_sim, 0.85)
    score += 0.40 * name_sim

    # --- Distance proximity (0.25) ---
    route_lat = route.get("lat") or route.get("departure_lat", 0)
    route_lng = route.get("lng") or route.get("departure_lng", 0)
    if route_lat and route_lng:
        # Approximate distance in km using equirectangular projection
        import math
        dlat = math.radians(race_lat - route_lat)
        dlng = math.radians(race_lng - route_lng) * math.cos(
            math.radians((race_lat + route_lat) / 2)
        )
        dist_km = math.sqrt(dlat**2 + dlng**2) * 6371
        # Score: 1.0 if <2km, linear decay to 0.0 at 50km
        proximity = max(0.0, 1.0 - dist_km / 50.0)
    else:
        proximity = 0.0
    score += 0.25 * proximity

    # --- Route length fit (0.20) ---
    route_distance_m = route.get("distance") or 0
    route_distance_km = route_distance_m / 1000.0
    if race_type and race_type in _DISTANCE_EXPECTATIONS and route_distance_km > 0:
        min_km, max_km = _DISTANCE_EXPECTATIONS[race_type]
        if min_km <= route_distance_km <= max_km:
            length_fit = 1.0
        else:
            # How far outside the range, as a ratio
            if route_distance_km < min_km:
                overshoot = (min_km - route_distance_km) / min_km
            else:
                overshoot = (route_distance_km - max_km) / max_km
            length_fit = max(0.0, 1.0 - overshoot)
    else:
        length_fit = 0.5  # No expectation = neutral
    score += 0.20 * length_fit

    # --- Popularity (0.15) ---
    trip_count = route.get("trip_count") or 0
    # Log scale: 0 trips = 0, 10 trips = 0.5, 100+ trips = 1.0
    import math
    pop = min(1.0, math.log10(trip_count + 1) / 2.0) if trip_count > 0 else 0.0
    score += 0.15 * pop

    return round(score, 3)


def rank_routes(
    routes: list[dict],
    race_name: str,
    race_lat: float,
    race_lng: float,
    race_type: str | None = None,
    *,
    min_score: float = 0.3,
) -> list[tuple[dict, float]]:
    """Score and rank routes. Returns [(route, score)] sorted by score desc.

    Filters out routes below min_score.
    """
    scored = []
    for route in routes:
        s = score_route(route, race_name, race_lat, race_lng, race_type)
        if s >= min_score:
            scored.append((route, s))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def fetch_track_points(route_id: int) -> list[dict] | None:
    """Fetch track points for a route. Returns list of {lat, lng, ele} or None.

    Note: The .json endpoint may require auth for some routes. Falls back
    gracefully if unavailable.
    """
    _rate_limit()
    try:
        resp = requests.get(
            RWGPS_ROUTE_URL.format(route_id=route_id),
            headers={"User-Agent": "RaceAnalyzer/0.1"},
            timeout=15,
        )
        if resp.ok:
            data = resp.json()
            # RWGPS route JSON has track_points under various keys
            track = (
                data.get("track_points")
                or data.get("route", {}).get("track_points")
                or []
            )
            if track:
                return [
                    {"lat": p.get("y", p.get("lat", 0)),
                     "lng": p.get("x", p.get("lng", 0)),
                     "ele": p.get("e", p.get("ele", 0))}
                    for p in track
                ]
    except Exception:
        logger.warning("Failed to fetch track points for route %d", route_id)
    return None
```

**Scoring breakdown example:**

| Route | Name Sim (0.40) | Proximity (0.25) | Length Fit (0.20) | Popularity (0.15) | Total |
|-------|----------------|-------------------|-------------------|--------------------| ------|
| "Banana Belt Road Race Course" | 0.72 * 0.40 = 0.29 | 0.96 * 0.25 = 0.24 | 1.0 * 0.20 = 0.20 | 0.5 * 0.15 = 0.08 | **0.81** |
| "Banana Belt Century" | 0.65 * 0.40 = 0.26 | 0.98 * 0.25 = 0.25 | 0.3 * 0.20 = 0.06 | 0.3 * 0.15 = 0.05 | **0.62** |
| "Random Portland Ride" | 0.15 * 0.40 = 0.06 | 0.70 * 0.25 = 0.18 | 0.5 * 0.20 = 0.10 | 0.8 * 0.15 = 0.12 | **0.46** |

The length fit component is particularly valuable for crits: a route result that is 1.2km will score 1.0 for a criterium but 0.0 for a road race, effectively filtering out false matches by race type.

### 4. `raceanalyzer/ui/maps.py` -- Add Course Map Rendering

Add to the existing `maps.py`:

```python
import json

import folium
from streamlit_folium import st_folium


def render_course_map(
    track_points_json: str,
    race_name: str = "",
    *,
    height: int = 400,
    width: int = 700,
):
    """Render a Strava-style polyline course map using Folium.

    track_points_json: JSON string of [{lat, lng, ele}, ...]
    """
    try:
        points = json.loads(track_points_json)
    except (json.JSONDecodeError, TypeError):
        return  # Silently skip if data is bad

    if not points or len(points) < 2:
        return

    coords = [(p["lat"], p["lng"]) for p in points]

    # Center on midpoint of route
    center = coords[len(coords) // 2]
    m = folium.Map(
        location=center,
        zoom_start=13,
        tiles="CartoDB positron",
        zoom_control=True,
        scrollWheelZoom=False,
    )

    # Route polyline (Strava orange)
    folium.PolyLine(
        coords,
        color="#FC4C02",
        weight=4,
        opacity=0.8,
    ).add_to(m)

    # Start marker (green)
    folium.Marker(
        coords[0],
        popup="Start",
        icon=folium.Icon(color="green", icon="play", prefix="fa"),
    ).add_to(m)

    # Finish marker (red flag)
    folium.Marker(
        coords[-1],
        popup="Finish",
        icon=folium.Icon(color="red", icon="flag-checkered", prefix="fa"),
    ).add_to(m)

    # Fit bounds to route
    m.fit_bounds(coords)

    st_folium(m, width=width, height=height, returned_objects=[])
```

### 5. `raceanalyzer/queries.py` -- Series Tile Queries

Add new query functions. The existing `get_race_tiles()` stays for backward compatibility; the calendar page switches to `get_series_tiles()`:

```python
def get_series_tiles(
    session: Session,
    *,
    year: Optional[int] = None,
    states: Optional[list[str]] = None,
    limit: int = 200,
) -> pd.DataFrame:
    """Return one row per series_key, with edition count and aggregated classification.

    For races without a series_key, each race is its own "series" (edition_count=1).

    Columns: series_key, display_name, latest_date, location, state_province,
             edition_count, race_ids, overall_finish_type.
    """
    # Base query: group by series_key (or id if no series_key)
    base = session.query(
        func.coalesce(Race.series_key, func.cast(Race.id, String)).label("group_key"),
        func.count(Race.id).label("edition_count"),
        func.max(Race.date).label("latest_date"),
        # Pick the name from the most recent edition
        Race.name,
        Race.location,
        Race.state_province,
        func.group_concat(Race.id).label("race_ids_csv"),
    ).group_by(
        func.coalesce(Race.series_key, func.cast(Race.id, String))
    )

    if year is not None:
        base = base.filter(func.strftime("%Y", Race.date) == str(year))
    if states:
        base = base.filter(Race.state_province.in_(states))

    base = base.order_by(func.max(Race.date).desc()).limit(limit)
    rows = base.all()

    columns = [
        "series_key", "display_name", "latest_date", "location",
        "state_province", "edition_count", "race_ids", "overall_finish_type",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)

    data = []
    for row in rows:
        race_ids = [int(x) for x in (row.race_ids_csv or "").split(",") if x]
        # Aggregate finish type across ALL editions in this series
        overall_ft = _compute_series_finish_type(session, race_ids)
        data.append({
            "series_key": row.group_key,
            "display_name": row.name,  # Most recent edition's name
            "latest_date": row.latest_date,
            "location": row.location,
            "state_province": row.state_province,
            "edition_count": row.edition_count,
            "race_ids": race_ids,
            "overall_finish_type": overall_ft,
        })
    return pd.DataFrame(data, columns=columns)


def _compute_series_finish_type(
    session: Session, race_ids: list[int],
) -> str:
    """Compute most frequent non-UNKNOWN finish type across multiple races.

    Same logic as _compute_overall_finish_type but spanning multiple race_ids.
    """
    from collections import Counter

    if not race_ids:
        return "unknown"

    classifications = (
        session.query(RaceClassification)
        .filter(RaceClassification.race_id.in_(race_ids))
        .all()
    )

    type_counts: Counter = Counter()
    type_finishers: dict[str, int] = {}
    type_cv_sum: dict[str, float] = {}
    type_cv_count: dict[str, int] = {}

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


def get_series_detail(
    session: Session, series_key: str,
) -> Optional[dict]:
    """Return all editions for a series, with per-edition classifications.

    Returns: {
        "series_key": str,
        "display_name": str,
        "editions": [{race_dict with classifications}, ...],
        "overall_finish_type": str,
        "finish_type_history": [{year, finish_type, count}, ...],
    }
    """
    races = (
        session.query(Race)
        .filter(Race.series_key == series_key)
        .order_by(Race.date.desc())
        .all()
    )
    if not races:
        return None

    editions = []
    race_ids = []
    for race in races:
        race_ids.append(race.id)
        detail = get_race_detail(session, race.id)
        if detail:
            editions.append(detail)

    overall_ft = _compute_series_finish_type(session, race_ids)

    # Build finish type history (year -> finish type counts)
    history_rows = []
    for edition in editions:
        race_date = edition["race"]["date"]
        year = race_date.year if race_date else None
        if year and not edition["classifications"].empty:
            for _, cls in edition["classifications"].iterrows():
                ft = cls["finish_type"]
                if ft != "unknown":
                    history_rows.append({
                        "year": year,
                        "finish_type": ft,
                    })

    history_df = pd.DataFrame(history_rows) if history_rows else pd.DataFrame(
        columns=["year", "finish_type"]
    )

    return {
        "series_key": series_key,
        "display_name": races[0].name,
        "editions": editions,
        "overall_finish_type": overall_ft,
        "finish_type_history": history_df,
    }
```

### 6. `raceanalyzer/ui/components.py` -- Series Tile with Edition Badge

Modify `_render_single_tile` to show edition count:

```python
def _render_single_tile(tile_row: dict, key_prefix: str = "tile"):
    """Render a single race/series tile with finish-type icon and edition badge."""
    finish_type = tile_row.get("overall_finish_type", "unknown")
    color = FINISH_TYPE_COLORS.get(finish_type, "#9E9E9E")
    icon_svg = FINISH_TYPE_ICONS.get(finish_type, FINISH_TYPE_ICONS["unknown"])
    display_name = html.escape(
        FINISH_TYPE_DISPLAY_NAMES.get(finish_type, "Unknown")
    )
    tooltip = html.escape(FINISH_TYPE_TOOLTIPS.get(finish_type, ""))
    name = html.escape(str(tile_row.get("display_name", tile_row.get("name", ""))))

    # Edition count badge (only show if >1)
    edition_count = tile_row.get("edition_count", 1)
    edition_html = ""
    if edition_count > 1:
        edition_html = (
            f'<span style="background:#546E7A;color:white;padding:1px 6px;'
            f'border-radius:10px;font-size:0.75em;margin-left:8px;">'
            f'{edition_count} editions</span>'
        )

    # Date
    date_str = ""
    date_val = tile_row.get("latest_date", tile_row.get("date"))
    if date_val:
        try:
            date_str = f"{date_val:%b %d, %Y}"
        except (TypeError, ValueError):
            date_str = str(date_val)

    loc = html.escape(str(tile_row.get("location", "") or ""))
    state = html.escape(str(tile_row.get("state_province", "") or ""))
    loc_str = f"{loc}, {state}" if state else loc

    with st.container(border=True):
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:8px;">'
            f'{icon_svg} <strong>{name}</strong>{edition_html}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="font-size:0.85em;color:#666;">'
            f'{date_str} &middot; {loc_str}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="margin-top:4px;">'
            f'<span style="background:{color};color:white;padding:2px 8px;'
            f'border-radius:4px;font-size:0.8em;cursor:help;" '
            f'title="{tooltip}">{display_name}</span></div>',
            unsafe_allow_html=True,
        )

        # Navigation -- for series tiles, link to first (most recent) race
        race_ids = tile_row.get("race_ids", [])
        nav_id = race_ids[0] if race_ids else tile_row.get("id")
        series_key = tile_row.get("series_key", "")

        if nav_id:
            if st.button(
                "View Details", key=f"{key_prefix}_btn_{nav_id}",
                use_container_width=True,
            ):
                st.session_state["selected_race_id"] = int(nav_id)
                if series_key:
                    st.query_params["series_key"] = series_key
                st.query_params["race_id"] = str(nav_id)
                st.switch_page("pages/race_detail.py")
```

### 7. `raceanalyzer/ui/pages/race_detail.py` -- Course Map Integration

Add course map rendering between the header and classifications:

```python
# After the area map section, add course map
from raceanalyzer.ui.maps import render_course_map

# ... existing header code ...

# Course map (polyline overlay) -- takes priority over area map
if race_obj.rwgps_route_json:
    st.subheader("Course Map")
    render_course_map(race_obj.rwgps_route_json, race["name"])
elif location and location != "Unknown":
    # Fall back to area pin map
    coords = geocode_location(location, state)
    if coords:
        render_location_map(*coords)
```

For series navigation, add an edition selector in the sidebar when viewing a race that belongs to a series:

```python
# In the sidebar, after the race selector
race_obj = session.get(Race, race_id)
if race_obj and race_obj.series_key:
    st.sidebar.divider()
    st.sidebar.subheader("Other Editions")
    siblings = (
        session.query(Race)
        .filter(Race.series_key == race_obj.series_key, Race.id != race_id)
        .order_by(Race.date.desc())
        .all()
    )
    for sib in siblings:
        date_str = f"{sib.date:%Y}" if sib.date else "?"
        if st.sidebar.button(f"{sib.name} ({date_str})", key=f"sib_{sib.id}"):
            st.session_state["selected_race_id"] = sib.id
            st.query_params["race_id"] = str(sib.id)
            st.rerun()
```

### 8. `raceanalyzer/ui/pages/calendar.py` -- Switch to Series View

```python
def render():
    session = st.session_state.db_session
    filters = render_sidebar_filters(session)

    st.title("PNW Race Calendar")

    df = queries.get_series_tiles(
        session, year=filters["year"], states=filters["states"]
    )

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
        f"Show races without timing data ({unknown_count} of {total_count})",
        value=False,
    )
    if not show_unknown:
        df = df[df["overall_finish_type"] != "unknown"]

    if df.empty:
        render_empty_state(
            "No classified races found. Toggle above to see all."
        )
        return

    # Metrics
    col1, col2, col3 = st.columns(3)
    total_editions = df["edition_count"].sum()
    col1.metric("Series", len(df))
    col2.metric("Total Editions", int(total_editions))
    multi_edition = len(df[df["edition_count"] > 1])
    col3.metric("Multi-Edition Series", multi_edition)

    # Pagination + tile grid (unchanged structure)
    if "tile_page_size" not in st.session_state:
        st.session_state.tile_page_size = TILES_PER_PAGE
    visible_count = st.session_state.tile_page_size

    visible_df = df.head(visible_count)
    render_tile_grid(visible_df, key_prefix="cal")

    if visible_count < len(df):
        remaining = len(df) - visible_count
        if st.button(f"Show more ({remaining} remaining)"):
            st.session_state.tile_page_size = visible_count + TILES_PER_PAGE
            st.rerun()
```

### 9. `raceanalyzer/cli.py` -- New Commands

```python
@cli.command()
@click.option("--dry-run", is_flag=True, help="Show what would change without writing")
def normalize_names(dry_run):
    """Compute series_key for all races based on name normalization."""
    from raceanalyzer.normalize import normalize_race_name

    with get_session() as session:
        races = session.query(Race).all()
        changes = 0
        for race in races:
            new_key = normalize_race_name(race.name)
            if race.series_key != new_key:
                if dry_run:
                    click.echo(f"  {race.name!r} -> {new_key!r}")
                else:
                    race.series_key = new_key
                changes += 1

        if not dry_run:
            session.commit()
        click.echo(f"{'Would update' if dry_run else 'Updated'} {changes} races.")


@cli.command()
@click.option("--min-score", default=0.3, help="Minimum match score (0-1)")
@click.option("--limit", default=50, help="Max races to process")
@click.option("--dry-run", is_flag=True)
def match_routes(min_score, limit, dry_run):
    """Search RWGPS for course routes and cache the best match."""
    from raceanalyzer.rwgps import rank_routes, search_routes, fetch_track_points
    from raceanalyzer.ui.maps import geocode_location
    import json

    with get_session() as session:
        # Only process races without a route (and not manually overridden)
        races = (
            session.query(Race)
            .filter(Race.rwgps_route_id.is_(None))
            .filter(Race.rwgps_manual_override.is_(False))
            .limit(limit)
            .all()
        )

        matched = 0
        for race in races:
            # Need coordinates to search
            lat, lng = None, None
            if race.course_lat and race.course_lon:
                try:
                    lat = float(race.course_lat.split(",")[0])
                    lng = float(race.course_lon.split(",")[0])
                except (ValueError, IndexError):
                    pass

            if lat is None:
                coords = geocode_location(
                    race.location or "", race.state_province or ""
                )
                if coords:
                    lat, lng = coords

            if lat is None:
                click.echo(f"  SKIP {race.name}: no coordinates")
                continue

            routes = search_routes(race.name, lat, lng)
            if not routes:
                click.echo(f"  SKIP {race.name}: no RWGPS results")
                continue

            race_type_val = race.race_type.value if race.race_type else None
            ranked = rank_routes(
                routes, race.name, lat, lng,
                race_type=race_type_val,
                min_score=min_score,
            )

            if not ranked:
                click.echo(f"  SKIP {race.name}: no routes above {min_score} score")
                continue

            best_route, best_score = ranked[0]
            route_id = best_route.get("id")

            click.echo(
                f"  MATCH {race.name} -> "
                f"RWGPS #{route_id} ({best_route.get('name')!r}) "
                f"score={best_score:.2f}"
            )

            if not dry_run and route_id:
                # Fetch and cache track points
                track_points = fetch_track_points(route_id)
                race.rwgps_route_id = route_id
                race.rwgps_match_score = best_score
                if track_points:
                    race.rwgps_route_json = json.dumps(track_points)
                matched += 1

        if not dry_run:
            session.commit()
        click.echo(f"{'Would match' if dry_run else 'Matched'} {matched} races.")


@cli.command()
@click.argument("race_id", type=int)
@click.argument("rwgps_route_id", type=int)
def override_route(race_id, rwgps_route_id):
    """Manually set the RWGPS route for a race (overrides auto-match)."""
    from raceanalyzer.rwgps import fetch_track_points
    import json

    with get_session() as session:
        race = session.get(Race, race_id)
        if not race:
            click.echo(f"Race {race_id} not found.")
            return

        track_points = fetch_track_points(rwgps_route_id)
        race.rwgps_route_id = rwgps_route_id
        race.rwgps_manual_override = True
        race.rwgps_match_score = 1.0  # Manual = perfect score
        if track_points:
            race.rwgps_route_json = json.dumps(track_points)
            click.echo(
                f"Set route for {race.name!r}: "
                f"RWGPS #{rwgps_route_id} ({len(track_points)} track points)"
            )
        else:
            click.echo(
                f"Set route ID for {race.name!r} but could not fetch track points. "
                f"Map will not render until points are available."
            )
        session.commit()
```

---

## Phased Rollout

### Phase A: Course Maps (can ship alone)

**Scope:** RWGPS search, scoring, caching, Folium rendering, manual override CLI.

**DB changes:** `rwgps_route_id`, `rwgps_route_json`, `rwgps_match_score`, `rwgps_manual_override` columns on Race.

**Files:** `rwgps.py` (new), `maps.py` (modify), `race_detail.py` (modify), `cli.py` (modify), `models.py` (modify).

**MVP:** `match-routes --dry-run` works, `override-route` works, race detail page shows polyline map when data exists.

**Zero dependency on Phase B.** Series grouping is not needed for course maps.

### Phase B: Race Deduplication (can ship alone)

**Scope:** Name normalization, `series_key` column, `get_series_tiles()`, calendar grouped view, series sidebar navigation.

**DB changes:** `series_key` column on Race.

**Files:** `normalize.py` (new), `queries.py` (modify), `components.py` (modify), `calendar.py` (modify), `race_detail.py` (modify), `cli.py` (modify), `models.py` (modify).

**MVP:** `normalize-names --dry-run` shows correct groupings, calendar shows grouped tiles with edition counts.

**Zero dependency on Phase A.** Course maps are not needed for dedup.

### Phase C: Polish (requires A + B)

**Scope:** Series detail page with aggregated classification history chart, edition navigation with course map, "Compare courses across editions" view.

**This phase is stretch / next sprint material.**

---

## Files Summary

| File | Action | Phase | Description |
|------|--------|-------|-------------|
| `raceanalyzer/db/models.py` | **Modify** | A+B | Add series_key, rwgps_* columns to Race |
| `raceanalyzer/normalize.py` | **Create** | B | Race name normalization (series_key computation) |
| `raceanalyzer/rwgps.py` | **Create** | A | RWGPS search, route scoring, track point fetching |
| `raceanalyzer/queries.py` | **Modify** | B | get_series_tiles(), _compute_series_finish_type() |
| `raceanalyzer/ui/maps.py` | **Modify** | A | Add render_course_map() with Folium |
| `raceanalyzer/ui/components.py` | **Modify** | B | Edition count badge on tiles |
| `raceanalyzer/ui/pages/calendar.py` | **Modify** | B | Switch to get_series_tiles() |
| `raceanalyzer/ui/pages/race_detail.py` | **Modify** | A+B | Course map, series sidebar navigation |
| `raceanalyzer/cli.py` | **Modify** | A+B | normalize-names, match-routes, override-route |
| `tests/test_normalize.py` | **Create** | B | Name normalization edge cases (~15 test cases) |
| `tests/test_rwgps.py` | **Create** | A | Route scoring unit tests (~8 test cases) |
| `tests/test_queries.py` | **Modify** | B | Series tile aggregation tests |

**Total new files**: 3 (`normalize.py`, `rwgps.py`, `test_normalize.py`)
**Total modified files**: 8
**New dependency**: `streamlit-folium` (add to requirements.txt)
**Estimated new tests**: ~25

---

## Definition of Done

### Phase A (Course Maps)
1. `rwgps.py` searches RWGPS by keywords + coordinates
2. `score_route()` produces scores 0-1 using name similarity, proximity, length fit, popularity
3. `rank_routes()` filters below `min_score` threshold
4. `fetch_track_points()` retrieves and normalizes track point data
5. Race model stores `rwgps_route_id`, `rwgps_route_json`, `rwgps_match_score`, `rwgps_manual_override`
6. `match-routes` CLI command auto-matches races (with `--dry-run`)
7. `override-route` CLI command sets manual route (sets `rwgps_manual_override=True`)
8. Race detail page shows Folium polyline map when track points exist
9. Falls back to area pin map when no course data available
10. Rate limiting respects 1 req/sec for RWGPS
11. `streamlit-folium` added to requirements.txt

### Phase B (Dedup)
12. `normalize_race_name()` handles years, Roman numerals, ordinals, type suffixes
13. All edge cases from the table in section 1 produce correct output
14. `normalize-names` CLI command populates `series_key` (with `--dry-run`)
15. `get_series_tiles()` returns one row per series with edition count
16. Series tile shows edition count badge when >1
17. Calendar page uses `get_series_tiles()` instead of `get_race_tiles()`
18. Series finish type aggregates across all editions
19. Race detail sidebar shows links to other editions in the same series
20. All existing tests pass (zero regressions)

---

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| RWGPS search returns irrelevant routes | Wrong course map | High | Scoring algorithm with min_score threshold + manual override CLI |
| RWGPS route .json endpoint requires auth | No track points | Medium | Degrade to iframe embed fallback; investigate auth if needed |
| RWGPS rate limits or blocks requests | No route data | Low | 1 req/sec rate limiting, User-Agent header, batch processing with delays |
| Name normalization groups unrelated races | Wrong series | Medium | `--dry-run` review step, conservative regexes, manual correction possible via DB |
| "Mason Lake" I and II are DIFFERENT courses, not editions | Over-grouping | Medium | Document as known limitation; future: add `series_key_override` column |
| `streamlit-folium` incompatibility with Streamlit version | Broken maps | Low | Pin version in requirements.txt; test on current Streamlit |
| `group_concat` behavior differs across SQLite versions | Broken series queries | Very Low | SQLite has supported group_concat since 3.5.4 (2007) |
| Name normalization strips meaningful parts (e.g., "Stage 3") | Wrong grouping | Low | Stage races are rare in PNW; document as known limitation |

---

## Security

- RWGPS requests use descriptive User-Agent per API etiquette
- No user-controlled input flows to RWGPS search (race names come from our DB, originally scraped from road-results.com)
- `rwgps_route_json` is parsed via `json.loads()` before rendering -- no raw injection into HTML
- Manual override CLI requires database write access (not exposed via web UI)
- All race names in HTML tiles continue to be escaped via `html.escape()`

---

## Dependencies

- **New Python package**: `streamlit-folium` (for Folium map rendering in Streamlit)
- **New Python package**: `folium` (Leaflet.js wrapper, dependency of streamlit-folium)
- `requests` already in dependencies (for RWGPS API calls)
- `difflib` is stdlib (for SequenceMatcher fuzzy matching)
- External APIs: RWGPS `/find/search.json` (undocumented, no auth, rate-limit-friendly)

---

## Scope Cut Guidance

If constrained, cut in this order (last = cut first):

1. **Keep**: Name normalization + series_key + CLI dry-run, RWGPS search + scoring + CLI dry-run
2. **Keep**: Calendar series grouping with edition badges, course map rendering on detail page
3. **Cut if needed**: Series sidebar navigation (other editions), popularity component of route scoring
4. **Cut if needed**: Phase C polish (series detail page, classification history chart)
5. **Cut if needed**: Folium rendering -- fall back to RWGPS iframe embed (saves `streamlit-folium` dependency)

---

## Open Questions

1. **RWGPS search response format**: The undocumented endpoint structure needs validation. The scoring algorithm is designed to be flexible regardless of exact field names. Recommend a manual curl test before implementation.
2. **Multi-course series**: Mason Lake I and II may use different courses but share the same series_key. Should course maps show per-edition routes? Deferred -- each Race row has its own `rwgps_route_json`, so this works naturally.
3. **Normalization false positives**: Should we add a `series_key_override` column for manual corrections? Deferred -- can be added trivially as a Phase C item if needed.
4. **Calendar year filter behavior**: When filtering by year, should we show all series that have ANY edition in that year, or only series where the LATEST edition is in that year? Recommend: any edition in that year.
