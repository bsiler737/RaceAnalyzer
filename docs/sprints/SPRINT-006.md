# Sprint 006: Course Maps & Race Series Deduplication

## Overview

Two features that transform RaceAnalyzer from a flat race list into an intelligent race knowledge base:

1. **Course Maps via RideWithGPS.** Match races to RWGPS routes using the undocumented `/find/search.json` endpoint (no auth). Score matches with a 3-component algorithm (name similarity, geographic proximity, route length fit). Cache polyline data and render Strava-style course maps via Folium. Fall back to the existing Nominatim area map when no route match exists.

2. **Race Series Deduplication.** Group recurring races (e.g., "Banana Belt RR" 2022-2025) into a `RaceSeries` entity via name normalization. Calendar shows one tile per series. Series detail page shows overall classification badge, course map, classification trend chart, and per-category breakdowns with expandable per-edition detail.

**Duration**: ~6-7 days
**Prerequisite**: Sprint 005 complete, 250+ races scraped with classifications.
**Merged from**: Claude draft (RaceSeries table, suffix normalization, build-series), Codex draft (Folium polyline, route scoring, Roman numeral/ordinal stripping, phased rollout, manual override), Gemini draft (series detail UX, empty states, back-navigation, per-category pivot).

---

## Use Cases

1. **As a racer**, I see a Strava-style course map on the race/series detail page showing the route polyline on a clean map, so I can study the terrain before race day.
2. **As a racer**, I see races grouped by series in the calendar — "Banana Belt" is one tile, not four separate tiles for each year.
3. **As a racer**, I see overall classification badge at the top of a series page, telling me at a glance how this race usually finishes.
4. **As a racer**, I see a classification trend chart showing finish types across all editions and categories by year.
5. **As a racer**, I can select a specific category (e.g., "Men Cat 1/2") to see how that category specifically has finished across editions.
6. **As a developer**, I can run `raceanalyzer match-routes` to batch-match races to RWGPS routes.
7. **As a developer**, I can run `raceanalyzer build-series` to compute series groupings from race names.
8. **As a developer**, I can run `raceanalyzer override-route <race_id> <rwgps_route_id>` to manually fix a bad match.

---

## Architecture

```
raceanalyzer/
├── db/
│   └── models.py              # MODIFY: Add RaceSeries model, rwgps columns on Race,
│                               #          series_id FK on Race
├── queries.py                 # MODIFY: Add get_series_tiles(), get_series_detail(),
│                              #          get_series_classification_trend()
├── rwgps.py                   # CREATE: RWGPS search API client, route scoring, polyline fetch
├── series.py                  # CREATE: Name normalization, series building logic
├── ui/
│   ├── components.py          # MODIFY: Add render_series_tile(), series badge
│   ├── maps.py                # MODIFY: Add render_course_map() with Folium polyline
│   ├── charts.py              # MODIFY: Add build_series_classification_chart()
│   ├── pages/
│   │   ├── calendar.py        # MODIFY: Switch to series tiles
│   │   ├── race_detail.py     # MODIFY: Course map, "Other Editions" sidebar links
│   │   └── series_detail.py   # CREATE: Series detail page with all editions,
│   │                          #          aggregated chart, category selector
├── cli.py                     # MODIFY: Add match-routes, build-series, override-route commands

tests/
├── test_series.py             # CREATE: Name normalization, series grouping tests
├── test_rwgps.py              # CREATE: Route scoring algorithm tests
├── test_queries.py            # MODIFY: Series tile queries, series detail queries
```

### Key Design Decisions

1. **Dedicated `RaceSeries` table** with `normalized_name` as unique grouping key and `display_name` for UI. A first-class table makes aggregation queries explicit, supports future series-level metadata, and avoids the NULL handling issues of a computed column. `series_id` FK on `Race`.

2. **Custom Folium polyline rendering** via `streamlit-folium`. Strava-orange polyline on CartoDB Positron basemap, start/finish markers, route-fit zoom. Cached polyline data (encoded polyline string stored on `RaceSeries`) renders instantly. Falls back to Nominatim area map when no route match.

3. **3-component route scoring algorithm**: SequenceMatcher name similarity (0.45), geographic proximity (0.30), race-type-aware length fit (0.25). Low threshold (0.25) to prefer showing a possibly-wrong map over no map. Manual override via CLI.

4. **Aggressive calendar grouping**: One tile per series, no toggle. Single-edition series tiles look identical to current individual tiles. Multi-edition tiles show edition count badge.

5. **Series detail page layout** (top to bottom): Overall classification badge → course map → classification trend chart (stacked bars by year) → category selector → per-edition expandable accordions.

6. **Name normalization**: Strip years, Roman numerals, ordinals, "annual", sponsor phrases. Normalize type suffixes (RR→Road Race, TT→Time Trial, etc.). `lru_cache` for performance.

7. **Route linked to series**: Since most races reuse the same course across editions, `rwgps_route_id` and `rwgps_encoded_polyline` live on `RaceSeries`. Individual `Race` rows can override with their own `rwgps_route_id` if the course changed.

8. **Independent phases**: Course maps (Phase A) and dedup (Phase B) have zero code dependency. Either can ship alone.

---

## Implementation

### 1. `raceanalyzer/db/models.py` — Schema Changes

Add `RaceSeries` model:

```python
class RaceSeries(Base):
    """A grouping of recurring race editions (e.g., 'Banana Belt Road Race')."""

    __tablename__ = "race_series"

    id = Column(Integer, primary_key=True, autoincrement=True)
    normalized_name = Column(String, nullable=False, unique=True)
    display_name = Column(String, nullable=False)

    # Course map data (applies to all editions unless overridden)
    rwgps_route_id = Column(Integer, nullable=True)
    rwgps_encoded_polyline = Column(Text, nullable=True)  # Encoded polyline string
    rwgps_manual_override = Column(Boolean, default=False)

    races = relationship("Race", back_populates="series")

    __table_args__ = (
        Index("ix_race_series_normalized_name", "normalized_name"),
    )
```

Add to `Race` model:

```python
class Race(Base):
    # ... existing columns ...

    # NEW: Series grouping
    series_id = Column(Integer, ForeignKey("race_series.id"), nullable=True)

    # NEW: Per-race route override (if course changed from the series default)
    rwgps_route_id = Column(Integer, nullable=True)

    series = relationship("RaceSeries", back_populates="races")

    __table_args__ = (
        Index("ix_races_date", "date"),
        Index("ix_races_state", "state_province"),
        Index("ix_races_race_type", "race_type"),
        Index("ix_races_series_id", "series_id"),  # NEW
    )
```

**Migration**: `ALTER TABLE races ADD COLUMN series_id INTEGER REFERENCES race_series(id)` and `ALTER TABLE races ADD COLUMN rwgps_route_id INTEGER`. New `race_series` table via `Base.metadata.create_all()`.

### 2. `raceanalyzer/series.py` — Name Normalization & Series Building (NEW FILE)

```python
"""Race series name normalization and grouping."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

from sqlalchemy.orm import Session

from raceanalyzer.db.models import Race, RaceSeries


# Suffix normalization: abbreviation -> canonical form
_SUFFIX_MAP = {
    "rr": "road race", "r.r.": "road race",
    "cr": "circuit race", "c.r.": "circuit race",
    "tt": "time trial", "t.t.": "time trial",
    "itt": "individual time trial", "i.t.t.": "individual time trial",
    "crit": "criterium",
    "hc": "hill climb", "h.c.": "hill climb",
    "gp": "grand prix", "g.p.": "grand prix",
}

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_ORDINAL_RE = re.compile(r"\b\d{1,2}(?:st|nd|rd|th)\b", re.IGNORECASE)
_ANNUAL_RE = re.compile(r"\bannual\b", re.IGNORECASE)
_NOISE_RE = re.compile(r"\b(presented by|sponsored by|powered by)\b.*", re.IGNORECASE)

# Roman numerals I-XXX (longest first to match greedily)
_ROMAN_RE = re.compile(
    r"\b(XXX|XXIX|XXVIII|XXVII|XXVI|XXV|XXIV|XXIII|XXII|XXI|"
    r"XX|XIX|XVIII|XVII|XVI|XV|XIV|XIII|XII|XI|"
    r"X|IX|VIII|VII|VI|V|IV|III|II|I)\b"
)


@lru_cache(maxsize=2048)
def normalize_race_name(name: str) -> str:
    """Normalize a race name to a series key.

    Examples:
        "2024 Banana Belt RR"          -> "banana belt road race"
        "Banana Belt Road Race 2023"   -> "banana belt road race"
        "Pacific Raceways XXI"         -> "pacific raceways"
        "Mason Lake I"                 -> "mason lake"
        "21st Annual Mutual of Enumclaw" -> "mutual of enumclaw"
    """
    s = name.strip()

    # Strip year patterns
    s = _YEAR_RE.sub("", s)

    # Strip ordinals and "annual"
    s = _ORDINAL_RE.sub("", s)
    s = _ANNUAL_RE.sub("", s)

    # Strip Roman numerals
    s = _ROMAN_RE.sub("", s)

    # Strip sponsor noise
    s = _NOISE_RE.sub("", s)

    # Lowercase for suffix matching
    s = s.lower().strip()

    # Normalize suffixes
    for abbrev, canonical in _SUFFIX_MAP.items():
        pattern = re.compile(r"\b" + re.escape(abbrev) + r"\b")
        s = pattern.sub(canonical, s)

    # Collapse whitespace, strip punctuation edges
    s = re.sub(r"\s+", " ", s).strip().strip("-–—,.")

    return s


def pick_display_name(race_names: list[str]) -> str:
    """Choose the best display name from edition names.

    Picks the longest (most descriptive) name with year stripped.
    """
    if not race_names:
        return "Unknown Series"
    best = max(race_names, key=len)
    best = _YEAR_RE.sub("", best).strip()
    best = re.sub(r"\s+", " ", best).strip().strip("-–—,.")
    return best


def build_series(session: Session) -> dict:
    """Group all races into series by normalized name. Idempotent.

    Creates RaceSeries rows and sets series_id on each Race.
    Returns: {series_created: int, races_linked: int}.
    """
    races = session.query(Race).all()
    groups: dict[str, list[Race]] = {}
    for race in races:
        key = normalize_race_name(race.name)
        groups.setdefault(key, []).append(race)

    series_created = 0
    races_linked = 0

    for norm_name, edition_races in groups.items():
        # Find or create series
        series = (
            session.query(RaceSeries)
            .filter(RaceSeries.normalized_name == norm_name)
            .first()
        )
        if series is None:
            display = pick_display_name([r.name for r in edition_races])
            series = RaceSeries(normalized_name=norm_name, display_name=display)
            session.add(series)
            session.flush()  # Get ID
            series_created += 1

        for race in edition_races:
            if race.series_id != series.id:
                race.series_id = series.id
                races_linked += 1

    session.commit()
    return {"series_created": series_created, "races_linked": races_linked}
```

### 3. `raceanalyzer/rwgps.py` — RWGPS Search & Route Matching (NEW FILE)

```python
"""RideWithGPS route discovery, scoring, and polyline fetching."""

from __future__ import annotations

import logging
import time
from difflib import SequenceMatcher
from typing import Optional

import requests

from raceanalyzer.db.models import RaceType

logger = logging.getLogger(__name__)

_RWGPS_SEARCH_URL = "https://ridewithgps.com/find/search.json"
_RWGPS_ROUTE_URL = "https://ridewithgps.com/routes/{route_id}.json"

# Race-type -> expected route distance range in km
_DISTANCE_EXPECTATIONS: dict[str, tuple[float, float]] = {
    "criterium": (0.8, 5.0),
    "road_race": (30.0, 200.0),
    "hill_climb": (2.0, 30.0),
    "time_trial": (5.0, 60.0),
    "gravel": (30.0, 200.0),
    "stage_race": (20.0, 200.0),
}

# Score weights
_W_NAME = 0.45
_W_PROXIMITY = 0.30
_W_LENGTH = 0.25

MIN_MATCH_SCORE = 0.25  # Low threshold per user preference


def search_routes(
    keywords: str,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    limit: int = 10,
) -> list[dict]:
    """Search RWGPS for public routes matching keywords + location."""
    params = {
        "search[keywords]": keywords,
        "search[models]": "Route",
        "search[offset]": 0,
        "search[limit]": limit,
    }
    if lat is not None and lon is not None:
        params["search[lat]"] = lat
        params["search[lng]"] = lon

    try:
        resp = requests.get(
            _RWGPS_SEARCH_URL,
            params=params,
            headers={"User-Agent": "RaceAnalyzer/0.1"},
            timeout=10,
        )
        if resp.ok:
            data = resp.json()
            return data.get("results", data) if isinstance(data, dict) else data
    except Exception:
        logger.debug("RWGPS search failed for %s", keywords)
    return []


def _clean_search_name(name: str) -> str:
    """Strip year and type suffixes from race name for better RWGPS search."""
    import re
    s = re.sub(r"\b(19|20)\d{2}\b", "", name)
    s = re.sub(r"\b(rr|road race|criterium|crit|tt|time trial)\b", "", s, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", s).strip()


def score_route(
    route: dict,
    race_name: str,
    race_lat: Optional[float],
    race_lon: Optional[float],
    race_type: Optional[str] = None,
) -> float:
    """Score a RWGPS route against a race. Returns 0.0-1.0."""
    # 1. Name similarity (SequenceMatcher)
    route_name = (route.get("name") or "").lower()
    cleaned_race = _clean_search_name(race_name).lower()
    name_score = SequenceMatcher(None, cleaned_race, route_name).ratio()

    # 2. Geographic proximity
    prox_score = 0.5  # Default if no coordinates
    if race_lat and race_lon:
        rlat = route.get("first_lat") or route.get("sw_lat")
        rlon = route.get("first_lng") or route.get("sw_lng")
        if rlat and rlon:
            dist_km = _haversine(race_lat, race_lon, float(rlat), float(rlon))
            prox_score = max(0.0, 1.0 - dist_km / 50.0)  # Linear decay over 50km

    # 3. Route length fit (race-type-aware)
    length_score = 0.5  # Default
    route_dist_km = (route.get("distance") or 0) / 1000.0
    if race_type and race_type in _DISTANCE_EXPECTATIONS and route_dist_km > 0:
        lo, hi = _DISTANCE_EXPECTATIONS[race_type]
        if lo <= route_dist_km <= hi:
            length_score = 1.0
        else:
            # Penalize based on how far outside the expected range
            if route_dist_km < lo:
                length_score = max(0.0, 1.0 - (lo - route_dist_km) / lo)
            else:
                length_score = max(0.0, 1.0 - (route_dist_km - hi) / hi)

    return _W_NAME * name_score + _W_PROXIMITY * prox_score + _W_LENGTH * length_score


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in km."""
    from math import asin, cos, radians, sin, sqrt
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(a))


def fetch_route_polyline(route_id: int) -> Optional[str]:
    """Fetch encoded polyline for a RWGPS route. Returns None on failure."""
    try:
        resp = requests.get(
            _RWGPS_ROUTE_URL.format(route_id=route_id),
            headers={"User-Agent": "RaceAnalyzer/0.1"},
            timeout=15,
        )
        if resp.ok:
            data = resp.json()
            # Try encoded polyline first, then build from track points
            if "encoded_polyline" in data:
                return data["encoded_polyline"]
            track = data.get("track_points", [])
            if track:
                return _encode_track_points(track)
    except Exception:
        logger.debug("Failed to fetch polyline for route %d", route_id)
    return None


def _encode_track_points(points: list[dict]) -> str:
    """Encode track points as a Google-format encoded polyline."""
    import polyline as pl  # pip install polyline
    coords = [(p.get("y", p.get("lat")), p.get("x", p.get("lng"))) for p in points]
    return pl.encode(coords)


def match_race_to_route(
    race_name: str,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    race_type: Optional[str] = None,
) -> Optional[dict]:
    """Find best RWGPS route match for a race. Returns {route_id, score, name} or None."""
    keywords = _clean_search_name(race_name)
    routes = search_routes(keywords, lat=lat, lon=lon)

    if not routes:
        return None

    scored = []
    for r in routes:
        s = score_route(r, race_name, lat, lon, race_type)
        scored.append((s, r))

    scored.sort(key=lambda x: -x[0])
    best_score, best_route = scored[0]

    if best_score < MIN_MATCH_SCORE:
        return None

    return {
        "route_id": best_route.get("id"),
        "score": best_score,
        "name": best_route.get("name"),
    }
```

### 4. `raceanalyzer/ui/maps.py` — Course Map Rendering

Add Folium polyline rendering alongside existing geocode/area map:

```python
def render_course_map(encoded_polyline: str, race_name: str = ""):
    """Render a Strava-style route polyline map via Folium."""
    import folium
    import polyline as pl
    from streamlit_folium import st_folium

    coords = pl.decode(encoded_polyline)
    if not coords:
        return

    center = coords[len(coords) // 2]
    m = folium.Map(location=center, zoom_start=13, tiles="CartoDB positron")
    folium.PolyLine(
        coords, color="#FC4C02", weight=4, opacity=0.8,
        tooltip=race_name,
    ).add_to(m)

    # Start/finish markers
    folium.Marker(
        coords[0], popup="Start",
        icon=folium.Icon(color="green", icon="play", prefix="fa"),
    ).add_to(m)
    folium.Marker(
        coords[-1], popup="Finish",
        icon=folium.Icon(color="red", icon="flag-checkered", prefix="fa"),
    ).add_to(m)

    # Fit bounds to route
    m.fit_bounds([[min(c[0] for c in coords), min(c[1] for c in coords)],
                  [max(c[0] for c in coords), max(c[1] for c in coords)]])

    st_folium(m, use_container_width=True, height=400, returned_objects=[])
```

### 5. `raceanalyzer/queries.py` — Series Queries

```python
def get_series_tiles(
    session: Session,
    *,
    year: Optional[int] = None,
    states: Optional[list[str]] = None,
    limit: int = 200,
) -> pd.DataFrame:
    """Return one row per series with aggregated data for calendar tiles.

    Columns: series_id, display_name, edition_count, earliest_date,
    latest_date, location, state_province, overall_finish_type.
    """
    from raceanalyzer.db.models import RaceSeries

    query = (
        session.query(
            RaceSeries.id.label("series_id"),
            RaceSeries.display_name,
            func.count(Race.id).label("edition_count"),
            func.min(Race.date).label("earliest_date"),
            func.max(Race.date).label("latest_date"),
            # Use the most recent race's location
            Race.location,
            Race.state_province,
        )
        .join(Race, Race.series_id == RaceSeries.id)
    )

    if year is not None:
        query = query.filter(extract("year", Race.date) == year)
    if states:
        query = query.filter(Race.state_province.in_(states))

    query = (
        query.group_by(RaceSeries.id)
        .order_by(func.max(Race.date).desc())
        .limit(limit)
    )

    rows = query.all()
    columns = [
        "series_id", "display_name", "edition_count", "earliest_date",
        "latest_date", "location", "state_province", "overall_finish_type",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)

    data = []
    for row in rows:
        overall_ft = _compute_series_overall_finish_type(session, row.series_id)
        data.append({
            "series_id": row.series_id,
            "display_name": row.display_name,
            "edition_count": row.edition_count,
            "earliest_date": row.earliest_date,
            "latest_date": row.latest_date,
            "location": row.location,
            "state_province": row.state_province,
            "overall_finish_type": overall_ft,
        })
    return pd.DataFrame(data, columns=columns)


def _compute_series_overall_finish_type(session: Session, series_id: int) -> str:
    """Most frequent non-UNKNOWN finish type across ALL editions of a series."""
    from collections import Counter

    classifications = (
        session.query(RaceClassification)
        .join(Race, Race.id == RaceClassification.race_id)
        .filter(Race.series_id == series_id)
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


def get_series_detail(session: Session, series_id: int) -> Optional[dict]:
    """Return series info with all editions and aggregated classifications."""
    from raceanalyzer.db.models import RaceSeries

    series = session.get(RaceSeries, series_id)
    if series is None:
        return None

    editions = (
        session.query(Race)
        .filter(Race.series_id == series_id)
        .order_by(Race.date.desc())
        .all()
    )

    # Build per-edition detail
    edition_details = []
    for race in editions:
        detail = get_race_detail(session, race.id)
        if detail:
            edition_details.append(detail)

    # Build classification trend (year x finish_type -> count)
    trend_rows = []
    for race in editions:
        year = race.date.year if race.date else None
        if year is None:
            continue
        for cls in race.classifications:
            ft = cls.finish_type.value if cls.finish_type else "unknown"
            trend_rows.append({
                "year": year,
                "finish_type": ft,
                "category": cls.category,
            })

    trend_df = pd.DataFrame(trend_rows) if trend_rows else pd.DataFrame(
        columns=["year", "finish_type", "category"]
    )

    # Get categories across all editions
    all_categories = sorted(set(
        cls.category for race in editions for cls in race.classifications
    ))

    overall_ft = _compute_series_overall_finish_type(session, series_id)

    # Get polyline (series-level, or from most recent race override)
    polyline = series.rwgps_encoded_polyline
    if not polyline:
        # Check individual race overrides
        for race in editions:
            if race.rwgps_route_id:
                # Would need to fetch — for now, series-level is primary
                break

    return {
        "series": {
            "id": series.id,
            "display_name": series.display_name,
            "normalized_name": series.normalized_name,
            "edition_count": len(editions),
            "rwgps_route_id": series.rwgps_route_id,
            "encoded_polyline": polyline,
        },
        "editions": edition_details,
        "trend": trend_df,
        "categories": all_categories,
        "overall_finish_type": overall_ft,
    }
```

### 6. `raceanalyzer/ui/pages/series_detail.py` — Series Detail Page (NEW FILE)

```python
"""Series Detail page — aggregated view across all editions of a race."""

from __future__ import annotations

import streamlit as st

from raceanalyzer import queries
from raceanalyzer.ui.charts import build_series_classification_chart
from raceanalyzer.ui.components import render_confidence_badge, render_empty_state
from raceanalyzer.ui.maps import render_course_map, geocode_location, render_location_map


def render():
    session = st.session_state.db_session

    # Back navigation
    if st.button("Back to Calendar"):
        st.switch_page("pages/calendar.py")

    series_id = st.query_params.get("series_id")
    if not series_id:
        series_id = st.session_state.get("selected_series_id")
    if not series_id:
        render_empty_state("No series selected.")
        return

    detail = queries.get_series_detail(session, int(series_id))
    if detail is None:
        render_empty_state("Series not found.")
        return

    series = detail["series"]
    editions = detail["editions"]
    trend_df = detail["trend"]

    # --- Header: Overall badge + name ---
    st.title(series["display_name"])

    col1, col2, col3 = st.columns([2, 1, 1])
    overall_ft = detail["overall_finish_type"]
    display_name = queries.finish_type_display_name(overall_ft)
    col1.markdown(f"**Overall Classification: {display_name}**")
    col2.write(f"**{series['edition_count']} editions**")

    # --- Course map (prominent) ---
    if series.get("encoded_polyline"):
        render_course_map(series["encoded_polyline"], series["display_name"])
    else:
        # Fallback to area map from most recent edition
        if editions:
            race = editions[0]["race"]
            location = race.get("location")
            state = race.get("state_province", "")
            if location and location != "Unknown":
                coords = geocode_location(location, state)
                if coords:
                    render_location_map(*coords)

    st.divider()

    # --- Classification trend chart ---
    if not trend_df.empty and trend_df["year"].nunique() >= 3:
        st.subheader("Classification Trends")
        fig = build_series_classification_chart(trend_df)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
    elif not trend_df.empty:
        # Fewer than 3 editions: show simple summary table
        st.subheader("Classification Summary")
        summary = (
            trend_df.groupby("finish_type")
            .size()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
        )
        summary["finish_type"] = summary["finish_type"].map(queries.finish_type_display_name)
        st.dataframe(summary, hide_index=True, use_container_width=True)

    # --- Category selector ---
    categories = detail["categories"]
    if categories:
        selected_cat = st.selectbox(
            "Filter by category:",
            options=[None] + categories,
            format_func=lambda x: "All Categories" if x is None else x,
        )
        if selected_cat and not trend_df.empty:
            cat_trend = trend_df[trend_df["category"] == selected_cat]
            if not cat_trend.empty:
                st.subheader(f"Classification Trend: {selected_cat}")
                fig = build_series_classification_chart(cat_trend)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # --- Per-edition expandable sections ---
    st.subheader("Race Editions")
    for edition in editions:
        race = edition["race"]
        date_str = f"{race['date']:%B %d, %Y}" if race.get("date") else "Unknown date"
        with st.expander(f"{race['name']} — {date_str}", expanded=(edition == editions[0])):
            # Classifications for this edition
            cls_df = edition["classifications"]
            if not cls_df.empty:
                for _, row in cls_df.iterrows():
                    cols = st.columns([2, 2, 1])
                    cols[0].write(f"**{row['category']}**")
                    ft_display = queries.finish_type_display_name(row["finish_type"])
                    cols[1].write(ft_display)
                    with cols[2]:
                        render_confidence_badge(row["confidence_label"], row["confidence_color"])
            else:
                st.caption("No classification data for this edition.")

            # Link to full detail
            if st.button("View Full Detail", key=f"edition_{race['id']}"):
                st.session_state["selected_race_id"] = race["id"]
                st.session_state["back_to_series"] = series["id"]
                st.query_params["race_id"] = str(race["id"])
                st.switch_page("pages/race_detail.py")


render()
```

### 7. `raceanalyzer/ui/pages/calendar.py` — Switch to Series Tiles

Replace `get_race_tiles()` with `get_series_tiles()`. Series tiles show: display name, edition count badge, date range, location, overall classification badge. Single-edition series tiles render identically to current individual tiles.

### 8. `raceanalyzer/ui/pages/race_detail.py` — Course Map + Edition Sidebar

- Add course map (Folium polyline) when available, replacing or alongside the area pin map
- Add "Other Editions" sidebar links when race belongs to a multi-edition series
- Add back-to-series navigation when `back_to_series` is in session state

### 9. `raceanalyzer/cli.py` — New Commands

```python
@cli.command()
@click.option("--dry-run", is_flag=True, help="Show matches without saving")
@click.option("--min-score", default=0.25, help="Minimum match score")
def match_routes(dry_run, min_score):
    """Match races/series to RWGPS routes."""
    # For each series without a route (and not manually overridden):
    #   1. Get coordinates from most recent edition (geocode if needed)
    #   2. Search RWGPS with cleaned series name + coordinates
    #   3. Score results, pick best above min_score
    #   4. Fetch encoded polyline
    #   5. Store on RaceSeries (rwgps_route_id, rwgps_encoded_polyline)
    # Rate limit: 1 request/second to RWGPS

@cli.command()
def build_series():
    """Group races into series by normalized name."""
    # Calls series.build_series(session)

@cli.command()
@click.argument("race_id", type=int)
@click.argument("rwgps_route_id", type=int)
def override_route(race_id, rwgps_route_id):
    """Manually set RWGPS route for a race's series."""
    # Sets rwgps_route_id + rwgps_manual_override=True on RaceSeries
    # Fetches and caches polyline
```

### 10. `raceanalyzer/ui/charts.py` — Series Classification Chart

```python
def build_series_classification_chart(trend_df: pd.DataFrame):
    """Build stacked bar chart: year (x) x finish_type counts (y)."""
    import plotly.express as px
    from raceanalyzer.ui.components import FINISH_TYPE_COLORS

    if trend_df.empty:
        return None

    counts = (
        trend_df.groupby(["year", "finish_type"])
        .size()
        .reset_index(name="count")
    )
    counts["display_name"] = counts["finish_type"].map(
        queries.finish_type_display_name
    )

    fig = px.bar(
        counts,
        x="year",
        y="count",
        color="finish_type",
        color_discrete_map=FINISH_TYPE_COLORS,
        labels={"count": "Categories", "year": "Year"},
        barmode="stack",
    )
    fig.update_layout(
        legend_title="Finish Type",
        xaxis=dict(dtick=1),
        margin=dict(t=20, b=40, l=40, r=20),
        height=300,
    )
    return fig
```

---

## New Dependencies

- `streamlit-folium` — Folium map component for Streamlit (well-maintained, 1.5k+ GitHub stars)
- `polyline` — Google encoded polyline codec (tiny, no dependencies)
- `folium` — Python Leaflet wrapper (pulled in by streamlit-folium)

---

## Error & Empty States

| Scenario | Behavior |
|----------|----------|
| No RWGPS match found | Show Nominatim area map fallback |
| RWGPS search fails (network) | Log warning, show area map |
| Single-edition series | Tile looks identical to current individual tile; click goes to race detail directly |
| Series with < 3 editions | Show simple summary table instead of stacked bar chart |
| No classifications for any edition | Show "Run `classify --all` first" message |
| Some editions have data, others don't | Show available data; skip unknown editions in trend chart |
| RWGPS returns wrong route | User runs `override-route` CLI to fix |
| No geocode for race location | Skip map entirely, show "Location not available" |

---

## Test Plan

### `tests/test_series.py` (NEW)
- `test_normalize_strips_year` — "2024 Banana Belt RR" → "banana belt road race"
- `test_normalize_strips_roman_numerals` — "Mason Lake I" → "mason lake", "Pacific Raceways XXI" → "pacific raceways"
- `test_normalize_strips_ordinals` — "21st Annual Mutual of Enumclaw" → "mutual of enumclaw"
- `test_normalize_suffix_map` — "Banana Belt RR" → "banana belt road race"
- `test_normalize_sponsor_noise` — "Race Presented by Acme" → "race"
- `test_normalize_preserves_meaningful_words` — "Stage Race" stays "stage race" (not stripped)
- `test_pick_display_name` — picks longest, year-stripped name
- `test_build_series_creates_groups` — groups races by normalized name
- `test_build_series_idempotent` — running twice produces same result

### `tests/test_rwgps.py` (NEW)
- `test_score_exact_name_nearby` — high score for matching name + close location
- `test_score_wrong_name_nearby` — low name score, some proximity score
- `test_score_right_name_far_away` — good name, low proximity
- `test_score_length_fit_crit` — criterium rejects 100km route
- `test_score_length_fit_road_race` — road race accepts 80km route
- `test_clean_search_name` — strips year and type suffixes
- `test_match_returns_none_below_threshold` — no match if all scores < MIN_MATCH_SCORE

### `tests/test_queries.py` (MODIFY)
- `test_get_series_tiles_returns_expected_columns`
- `test_get_series_tiles_groups_correctly`
- `test_compute_series_overall_finish_type`
- `test_get_series_detail`

---

## Phased Rollout

**Phase A: Course Maps** (Days 1-3)
- `rwgps.py` — search, scoring, polyline fetch
- `maps.py` — Folium rendering
- `cli.py` — `match-routes` and `override-route` commands
- Schema: `rwgps_*` columns on RaceSeries and Race
- Race detail page gains course map
- Tests: `test_rwgps.py`

**Phase B: Series Deduplication** (Days 3-5)
- `series.py` — normalization, build_series
- `models.py` — RaceSeries table, series_id FK
- `queries.py` — series queries
- `calendar.py` — series tiles
- `series_detail.py` — new page
- `charts.py` — series classification chart
- Tests: `test_series.py`, query tests

**Phase C: Polish** (Days 5-7)
- Race detail: "Other Editions" sidebar links
- Back-navigation state (back_to_series)
- Category selector on series page
- Empty state refinements
- Per-category pivot table (stretch)

---

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| RWGPS `/find/search.json` is undocumented and could change | Course maps break | Store polyline data locally; map still renders from cache. Add monitoring for search failures. |
| Name normalization false positives (different races with similar names) | Wrong grouping | `build-series` outputs a review list. Add `override-series` CLI for manual correction. |
| RWGPS route data auth requirement for polyline fetch | Can't get polylines | Fall back to RWGPS iframe embed as secondary option. |
| Folium rendering performance on large route files | Slow page load | Simplify polylines (Douglas-Peucker) if > 5000 points. |
| N+1 query for series overall_finish_type | Slow calendar | Precompute and cache; acceptable for <500 series. |
