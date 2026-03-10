# Sprint 006: Course Maps via RWGPS & Race Deduplication / Series

## Overview

Two features that transform RaceAnalyzer from a flat race list into an intelligent race knowledge base:

1. **Course Maps via RWGPS.** Match races to RideWithGPS routes using the undocumented `/find/search.json` endpoint (no auth). Store matched route IDs on the Race model. Render course maps via RWGPS iframe embeds. Fall back to the existing Nominatim area map when no route match exists.

2. **Race Deduplication / Series.** Group recurring races (e.g., "Banana Belt RR" 2022-2025) into a `RaceSeries` entity via name normalization. Calendar shows one tile per series. Series detail page shows all editions with aggregated classification history (stacked bar chart by year) and an overall badge reflecting the most common finish type across ALL editions and categories.

**Duration**: ~5-6 days
**Prerequisite**: Sprint 005 complete, 269+ races scraped with classifications.

---

## Use Cases

1. **As a racer**, I see a course map on the race detail page showing the actual route (RWGPS embed), so I can study the terrain before race day.
2. **As a racer**, I see races grouped by series in the calendar -- "Banana Belt" is one tile, not four separate tiles for each year.
3. **As a racer**, I see aggregated classification history for a race series -- a stacked bar chart showing finish types across all editions and categories by year.
4. **As a racer**, the overall badge on a series tile reflects the most common finish type across ALL editions, giving me the best prediction of what the next edition will be like.
5. **As a developer**, I can run `raceanalyzer match-routes` to batch-match races to RWGPS routes.
6. **As a developer**, I can run `raceanalyzer build-series` to compute series groupings from race names.

---

## Architecture

```
raceanalyzer/
├── db/
│   └── models.py              # MODIFY: Add RaceSeries model, rwgps_route_id on Race,
│                               #          series_id FK on Race
├── queries.py                 # MODIFY: Add get_series_tiles(), get_series_detail(),
│                               #          _compute_series_overall_finish_type(),
│                               #          get_series_classification_trend()
├── rwgps.py                   # CREATE: RWGPS search API client, route matching logic
├── series.py                  # CREATE: Name normalization, series building logic
├── ui/
│   ├── components.py          # MODIFY: Add render_series_tile_grid(),
│   │                          #          render_series_badge()
│   ├── maps.py                # MODIFY: Add render_course_map() for RWGPS embed
│   ├── charts.py              # MODIFY: Add build_series_classification_chart()
│   ├── pages/
│   │   ├── calendar.py        # MODIFY: Switch to series tiles, add toggle for
│   │   │                      #          series vs individual view
│   │   ├── race_detail.py     # MODIFY: Show RWGPS course map when available,
│   │   │                      #          link to series page
│   │   └── series_detail.py   # CREATE: Series detail page with all editions,
│   │                          #          aggregated chart, expandable per-edition detail
├── cli.py                     # MODIFY: Add match-routes and build-series commands

tests/
├── test_series.py             # CREATE: Name normalization, series grouping tests
├── test_rwgps.py              # CREATE: RWGPS search, route matching tests
├── test_queries.py            # MODIFY: Series tile queries, series detail queries
```

### Key Design Decisions

1. **Dedicated `RaceSeries` table** (not a computed column). A first-class table with `normalized_name` as the grouping key and a `series_id` FK on `Race`. This allows manual overrides later and makes queries simpler than runtime grouping.

2. **RWGPS iframe embed** (not custom Leaflet/polyline). The RWGPS embed provides a polished map with elevation profile, distance markers, and turn-by-turn -- all for free with zero rendering code. Store only the `rwgps_route_id` integer on the Race model. Embed URL: `https://ridewithgps.com/embeds?type=route&id={ROUTE_ID}`.

3. **Name normalization for dedup**: Strip year patterns (4-digit years, ordinal years like "23rd"), normalize race-type suffixes (RR -> Road Race, TT -> Time Trial, etc.), lowercase, strip whitespace. This handles ~90% of duplicates. Fuzzy matching is out of scope.

4. **Series overall badge**: Most frequent non-UNKNOWN finish type across ALL editions and ALL categories of the series. Same tiebreak logic as the existing `_compute_overall_finish_type()` but spanning multiple races.

5. **Calendar shows series by default** with a toggle to see individual races. Series tile shows: series name, number of editions, date range, most recent location, overall badge.

6. **Series detail page**: Header with series name, edition count, date range. Stacked bar chart of finish types by year. Per-edition expandable sections with the existing race detail content.

---

## Implementation

### 1. `raceanalyzer/db/models.py` -- Schema Changes

Add `RaceSeries` model and new columns on `Race`:

```python
class RaceSeries(Base):
    """A grouping of recurring race editions (e.g., 'Banana Belt Road Race')."""

    __tablename__ = "race_series"

    id = Column(Integer, primary_key=True, autoincrement=True)
    normalized_name = Column(String, nullable=False, unique=True)
    display_name = Column(String, nullable=False)  # Best human-readable name

    races = relationship("Race", back_populates="series")

    __table_args__ = (
        Index("ix_race_series_normalized_name", "normalized_name"),
    )
```

Add to `Race` model:

```python
class Race(Base):
    # ... existing columns ...

    # NEW: RWGPS route matching
    rwgps_route_id = Column(Integer, nullable=True)

    # NEW: Series grouping
    series_id = Column(Integer, ForeignKey("race_series.id"), nullable=True)

    series = relationship("RaceSeries", back_populates="races")

    __table_args__ = (
        Index("ix_races_date", "date"),
        Index("ix_races_state", "state_province"),
        Index("ix_races_race_type", "race_type"),
        Index("ix_races_series_id", "series_id"),  # NEW
    )
```

**Migration strategy**: SQLite `ALTER TABLE ADD COLUMN` for the three new columns (`rwgps_route_id`, `series_id`, plus the new `race_series` table via `CREATE TABLE`). Use `Base.metadata.create_all()` which is additive in SQLAlchemy -- new tables and columns are created, existing ones are untouched. For the FK column on an existing table, run a raw `ALTER TABLE races ADD COLUMN rwgps_route_id INTEGER` and `ALTER TABLE races ADD COLUMN series_id INTEGER REFERENCES race_series(id)` in an upgrade function.

### 2. `raceanalyzer/series.py` -- Name Normalization & Series Building (NEW FILE)

```python
"""Race series name normalization and grouping."""

from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

from raceanalyzer.db.models import Race, RaceSeries


# Suffix normalization map: abbreviation -> canonical form
_SUFFIX_MAP = {
    "rr": "road race",
    "r.r.": "road race",
    "cr": "circuit race",
    "c.r.": "circuit race",
    "tt": "time trial",
    "t.t.": "time trial",
    "itt": "individual time trial",
    "i.t.t.": "individual time trial",
    "crit": "criterium",
    "hc": "hill climb",
    "h.c.": "hill climb",
    "gp": "grand prix",
    "g.p.": "grand prix",
}

# Compiled regex for year patterns
_YEAR_PATTERNS = re.compile(
    r"""
    \b20\d{2}\b          |  # 4-digit year (2000-2099)
    \b19\d{2}\b          |  # 4-digit year (1900-1999)
    \b\d{1,2}(?:st|nd|rd|th)\s+annual\b  |  # "23rd annual"
    \b\d{1,2}(?:st|nd|rd|th)\b           |  # "23rd" (ordinal standalone)
    \bannual\b                               # "annual" standalone
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Noise words to strip
_NOISE_PATTERNS = re.compile(
    r"\b(presented by|sponsored by|powered by)\b.*",
    re.IGNORECASE,
)


def normalize_race_name(name: str) -> str:
    """Normalize a race name for series matching.

    Steps:
    1. Strip year patterns (2024, 23rd annual, etc.)
    2. Normalize race-type suffixes (RR -> road race, etc.)
    3. Strip sponsor/noise phrases ("presented by ...")
    4. Lowercase, collapse whitespace, strip
    """
    result = name

    # Strip year patterns
    result = _YEAR_PATTERNS.sub("", result)

    # Strip sponsor noise
    result = _NOISE_PATTERNS.sub("", result)

    # Lowercase for suffix matching
    result = result.lower().strip()

    # Normalize suffixes -- match as whole words at end or within name
    for abbrev, canonical in _SUFFIX_MAP.items():
        # Match abbreviation as a whole word
        pattern = re.compile(r"\b" + re.escape(abbrev) + r"\b", re.IGNORECASE)
        result = pattern.sub(canonical, result)

    # Collapse whitespace, strip punctuation edges
    result = re.sub(r"\s+", " ", result).strip()
    result = result.strip("-–—,.")

    return result


def pick_display_name(race_names: list[str]) -> str:
    """Choose the best display name from a list of edition names.

    Picks the most recent (last in list assuming chronological order),
    with year stripped.
    """
    if not race_names:
        return "Unknown Series"

    # Use the longest name (usually most descriptive), with year stripped
    best = max(race_names, key=len)
    # Strip just the 4-digit year
    best = re.sub(r"\b20\d{2}\b|\b19\d{2}\b", "", best).strip()
    # Clean up double spaces and trailing punctuation
    best = re.sub(r"\s+", " ", best).strip().strip("-–—,.")
    return best


def build_series(session: Session) -> dict:
    """Group all races into series by normalized name.

    Creates RaceSeries rows and sets series_id on each Race.
    Returns summary dict: {series_created: int, races_linked: int}.
    """
    races = session.query(Race).all()

    # Group by normalized name
    groups: dict[str, list[Race]] = {}
    for race in races:
        key = normalize_race_name(race.name)
        if key not in groups:
            groups[key] = []
        groups[key].append(race)

    series_created = 0
    races_linked = 0

    for normalized_name, race_list in groups.items():
        # Check for existing series
        existing = (
            session.query(RaceSeries)
            .filter(RaceSeries.normalized_name == normalized_name)
            .first()
        )

        if existing:
            series = existing
        else:
            display = pick_display_name([r.name for r in race_list])
            series = RaceSeries(
                normalized_name=normalized_name,
                display_name=display,
            )
            session.add(series)
            session.flush()  # Get the ID
            series_created += 1

        for race in race_list:
            if race.series_id != series.id:
                race.series_id = series.id
                races_linked += 1

    session.commit()
    return {"series_created": series_created, "races_linked": races_linked}
```

### 3. `raceanalyzer/rwgps.py` -- RWGPS Route Matching (NEW FILE)

```python
"""RideWithGPS route search and matching."""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests
from sqlalchemy.orm import Session

from raceanalyzer.db.models import Race
from raceanalyzer.ui.maps import geocode_location

logger = logging.getLogger(__name__)

RWGPS_SEARCH_URL = "https://ridewithgps.com/find/search.json"
RWGPS_EMBED_URL = "https://ridewithgps.com/embeds"

# Rate limit: be polite to undocumented API
_REQUEST_DELAY = 1.0  # seconds between requests


def search_rwgps_routes(
    keywords: str,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    limit: int = 5,
) -> list[dict]:
    """Search RWGPS for routes matching keywords and location.

    Returns list of route dicts with keys: id, name, distance, elevation_gain,
    bounding_box, etc. Returns empty list on failure.
    """
    params = {
        "search[keywords]": keywords,
        "search[limit]": limit,
        "search[offset]": 0,
    }
    if lat is not None and lng is not None:
        params["search[lat]"] = lat
        params["search[lng]"] = lng

    try:
        resp = requests.get(
            RWGPS_SEARCH_URL,
            params=params,
            headers={"User-Agent": "RaceAnalyzer/0.1 (PNW bike race analysis)"},
            timeout=10,
        )
        if not resp.ok:
            logger.warning("RWGPS search failed: %s %s", resp.status_code, resp.reason)
            return []

        data = resp.json()
        # Response structure: {"results": [...], "results_count": N}
        results = data.get("results", [])
        return [
            {
                "id": r.get("id"),
                "name": r.get("name", ""),
                "type": r.get("type", ""),  # "route" or "trip"
                "distance": r.get("distance"),  # meters
                "elevation_gain": r.get("elevation_gain"),  # meters
                "lat": r.get("lat"),
                "lng": r.get("lng"),
            }
            for r in results
            if r.get("type") == "route"
        ]
    except Exception:
        logger.exception("RWGPS search error for keywords=%s", keywords)
        return []


def _score_route_match(
    route: dict,
    race_name: str,
    race_lat: Optional[float] = None,
    race_lng: Optional[float] = None,
) -> float:
    """Score how well a RWGPS route matches a race.

    Returns a score from 0.0 to 1.0. Higher is better.
    Factors:
    - Name overlap (Jaccard similarity of word tokens)
    - Geographic proximity (if coordinates available)
    """
    # Name similarity: Jaccard on lowercased word tokens
    race_tokens = set(race_name.lower().split())
    route_tokens = set(route.get("name", "").lower().split())

    # Remove common noise words
    noise = {"the", "a", "an", "of", "in", "at", "and", "&", "-", "race", "ride"}
    race_tokens -= noise
    route_tokens -= noise

    if race_tokens and route_tokens:
        intersection = race_tokens & route_tokens
        union = race_tokens | route_tokens
        name_score = len(intersection) / len(union) if union else 0.0
    else:
        name_score = 0.0

    # Geographic proximity score (inverse distance, capped)
    geo_score = 0.0
    if (race_lat is not None and race_lng is not None
            and route.get("lat") is not None and route.get("lng") is not None):
        # Simple Euclidean approximation (fine for nearby routes)
        dlat = abs(race_lat - route["lat"])
        dlng = abs(race_lng - route["lng"])
        dist_deg = (dlat**2 + dlng**2) ** 0.5

        # 0.1 deg ~ 11km. Score 1.0 if <5km, 0.0 if >50km
        if dist_deg < 0.045:
            geo_score = 1.0
        elif dist_deg < 0.45:
            geo_score = max(0.0, 1.0 - (dist_deg / 0.45))

    # Combined score: weight name heavily, geo as tiebreaker
    return 0.7 * name_score + 0.3 * geo_score


def match_race_to_route(
    race: Race,
    min_score: float = 0.3,
) -> Optional[int]:
    """Find the best RWGPS route for a race.

    Returns the RWGPS route ID if a match above min_score is found, else None.
    """
    # Get coordinates for geographic search
    lat, lng = None, None
    if race.location:
        coords = geocode_location(race.location, race.state_province or "")
        if coords:
            lat, lng = coords

    # Search RWGPS
    routes = search_rwgps_routes(race.name, lat=lat, lng=lng)
    if not routes:
        return None

    # Score and pick best match
    scored = [
        (route, _score_route_match(route, race.name, lat, lng))
        for route in routes
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    best_route, best_score = scored[0]
    if best_score >= min_score:
        logger.info(
            "Matched race '%s' to RWGPS route '%s' (id=%s, score=%.2f)",
            race.name, best_route["name"], best_route["id"], best_score,
        )
        return best_route["id"]

    logger.debug(
        "No RWGPS match for '%s' (best score=%.2f < %.2f)",
        race.name, best_score, min_score,
    )
    return None


def match_all_races(
    session: Session,
    *,
    force: bool = False,
) -> dict:
    """Batch-match all races to RWGPS routes.

    Args:
        session: DB session.
        force: If True, re-match races that already have a route_id.

    Returns summary dict: {matched: int, skipped: int, failed: int}.
    """
    query = session.query(Race)
    if not force:
        query = query.filter(Race.rwgps_route_id.is_(None))

    races = query.all()
    matched = 0
    skipped = 0
    failed = 0

    for race in races:
        route_id = match_race_to_route(race)
        if route_id is not None:
            race.rwgps_route_id = route_id
            matched += 1
        else:
            failed += 1

        # Rate limiting
        time.sleep(_REQUEST_DELAY)

    session.commit()
    return {"matched": matched, "skipped": skipped, "failed": failed}
```

### 4. `raceanalyzer/queries.py` -- Series Queries

Add new query functions for series tiles and series detail:

```python
def get_series_tiles(
    session: Session,
    *,
    year: Optional[int] = None,
    states: Optional[list[str]] = None,
    limit: int = 200,
) -> pd.DataFrame:
    """Return series tile data for the calendar.

    Each row represents one series with aggregated info across all editions.
    Columns: series_id, display_name, edition_count, first_date, last_date,
    location, state_province, overall_finish_type.
    """
    from raceanalyzer.db.models import RaceSeries

    # Base query: series with their races
    query = (
        session.query(
            RaceSeries.id.label("series_id"),
            RaceSeries.display_name,
            func.count(Race.id).label("edition_count"),
            func.min(Race.date).label("first_date"),
            func.max(Race.date).label("last_date"),
        )
        .join(Race, Race.series_id == RaceSeries.id)
    )

    if year is not None:
        query = query.filter(func.strftime("%Y", Race.date) == str(year))
    if states:
        query = query.filter(Race.state_province.in_(states))

    query = (
        query.group_by(RaceSeries.id)
        .order_by(func.max(Race.date).desc())
        .limit(limit)
    )

    rows = query.all()
    columns = [
        "series_id", "display_name", "edition_count", "first_date",
        "last_date", "location", "state_province", "overall_finish_type",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)

    data = []
    for row in rows:
        # Get location from most recent edition
        most_recent = (
            session.query(Race.location, Race.state_province)
            .filter(Race.series_id == row.series_id)
            .order_by(Race.date.desc())
            .first()
        )

        overall_ft = _compute_series_overall_finish_type(session, row.series_id)

        data.append({
            "series_id": row.series_id,
            "display_name": row.display_name,
            "edition_count": row.edition_count,
            "first_date": row.first_date,
            "last_date": row.last_date,
            "location": most_recent[0] if most_recent else None,
            "state_province": most_recent[1] if most_recent else None,
            "overall_finish_type": overall_ft,
        })

    return pd.DataFrame(data, columns=columns)


def _compute_series_overall_finish_type(
    session: Session, series_id: int,
) -> str:
    """Most frequent non-UNKNOWN finish type across ALL editions of a series.

    Same tiebreak logic as _compute_overall_finish_type but spanning
    all races in the series.
    """
    from collections import Counter

    # Get all classifications for all races in this series
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
    """Return a series with all its editions, classifications, and results.

    Returns dict with keys:
    - series: {id, display_name, normalized_name, edition_count}
    - editions: list of race dicts (same format as get_race_detail)
    - overall_finish_type: str
    - classification_trend: DataFrame (year, finish_type, count)
    """
    from raceanalyzer.db.models import RaceSeries

    series = session.get(RaceSeries, series_id)
    if series is None:
        return None

    races = (
        session.query(Race)
        .filter(Race.series_id == series_id)
        .order_by(Race.date.desc())
        .all()
    )

    editions = []
    for race in races:
        detail = get_race_detail(session, race.id)
        if detail:
            editions.append(detail)

    overall_ft = _compute_series_overall_finish_type(session, series_id)

    # Build classification trend: finish types by year across all editions
    trend_data = []
    for race in races:
        if race.date is None:
            continue
        year = race.date.year
        for c in race.classifications:
            ft = c.finish_type.value if c.finish_type else "unknown"
            trend_data.append({
                "year": year,
                "finish_type": ft,
                "count": 1,
            })

    if trend_data:
        trend_df = pd.DataFrame(trend_data)
        trend_df = (
            trend_df.groupby(["year", "finish_type"])["count"]
            .sum()
            .reset_index()
        )
    else:
        trend_df = pd.DataFrame(columns=["year", "finish_type", "count"])

    return {
        "series": {
            "id": series.id,
            "display_name": series.display_name,
            "normalized_name": series.normalized_name,
            "edition_count": len(races),
        },
        "editions": editions,
        "overall_finish_type": overall_ft,
        "classification_trend": trend_df,
    }
```

### 5. `raceanalyzer/ui/maps.py` -- RWGPS Course Map Rendering

Add RWGPS embed rendering alongside the existing `render_location_map()`:

```python
def render_course_map(rwgps_route_id: int):
    """Render a RWGPS route embed iframe showing the full course map.

    Uses the RWGPS embed widget which provides map, elevation profile,
    and route details with no authentication required.
    """
    embed_url = (
        f"https://ridewithgps.com/embeds"
        f"?type=route&id={int(rwgps_route_id)}"
    )
    st.markdown(
        f'<iframe src="{embed_url}" width="100%" height="400" '
        f'style="border:1px solid #e0e0e0;border-radius:8px;" '
        f'loading="lazy" sandbox="allow-scripts allow-same-origin"></iframe>',
        unsafe_allow_html=True,
    )
```

### 6. `raceanalyzer/ui/pages/race_detail.py` -- Course Map Integration

Replace the area map section with course map when RWGPS route is available:

```python
# Area map -- prefer RWGPS course map, fallback to Nominatim area map
from raceanalyzer.ui.maps import geocode_location, render_course_map, render_location_map

# Load the race ORM object to check for rwgps_route_id
from raceanalyzer.db.models import Race as RaceModel
race_obj = session.get(RaceModel, race_id)

if race_obj and race_obj.rwgps_route_id:
    st.subheader("Course Map")
    render_course_map(race_obj.rwgps_route_id)
elif location and location != "Unknown":
    coords = geocode_location(location, state)
    if coords:
        render_location_map(*coords)

# Link to series page if this race belongs to a series
if race_obj and race_obj.series_id:
    st.markdown(
        f"Part of a race series -- "
        f"[View all editions](?page=series_detail&series_id={race_obj.series_id})"
    )
```

### 7. `raceanalyzer/ui/components.py` -- Series Tile Rendering

Add series-specific tile rendering:

```python
def _render_single_series_tile(tile_row: dict, key_prefix: str = "series"):
    """Render a single series tile with edition count, date range, and badge."""
    finish_type = tile_row.get("overall_finish_type", "unknown")
    color = FINISH_TYPE_COLORS.get(finish_type, "#9E9E9E")
    icon_svg = FINISH_TYPE_ICONS.get(finish_type, FINISH_TYPE_ICONS["unknown"])
    display_name = html.escape(
        FINISH_TYPE_DISPLAY_NAMES.get(finish_type, "Unknown")
    )
    tooltip = html.escape(FINISH_TYPE_TOOLTIPS.get(finish_type, ""))
    name = html.escape(str(tile_row.get("display_name", "")))

    # Date range
    first_date = tile_row.get("first_date")
    last_date = tile_row.get("last_date")
    if first_date and last_date:
        try:
            date_str = f"{first_date:%Y} -- {last_date:%Y}"
        except (TypeError, ValueError):
            date_str = f"{first_date} -- {last_date}"
    elif last_date:
        try:
            date_str = f"{last_date:%b %d, %Y}"
        except (TypeError, ValueError):
            date_str = str(last_date)
    else:
        date_str = ""

    edition_count = tile_row.get("edition_count", 1)
    edition_label = f"{edition_count} edition{'s' if edition_count != 1 else ''}"

    loc = html.escape(str(tile_row.get("location", "") or ""))
    state = html.escape(str(tile_row.get("state_province", "") or ""))
    loc_str = f"{loc}, {state}" if state else loc

    with st.container(border=True):
        # Icon + name
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:8px;">'
            f'{icon_svg} <strong>{name}</strong></div>',
            unsafe_allow_html=True,
        )

        # Edition count + date range + location
        st.markdown(
            f'<div style="font-size:0.85em;color:#666;">'
            f'{edition_label} &middot; {date_str} &middot; {loc_str}</div>',
            unsafe_allow_html=True,
        )

        # Classification badge with tooltip
        st.markdown(
            f'<div style="margin-top:4px;">'
            f'<span style="background:{color};color:white;padding:2px 8px;'
            f'border-radius:4px;font-size:0.8em;cursor:help;" '
            f'title="{tooltip}">{display_name}</span></div>',
            unsafe_allow_html=True,
        )

        # Navigation button
        series_id = int(tile_row["series_id"])
        if st.button(
            "View Series", key=f"{key_prefix}_btn_{series_id}",
            use_container_width=True,
        ):
            st.session_state["selected_series_id"] = series_id
            st.query_params["series_id"] = str(series_id)
            st.switch_page("pages/series_detail.py")


def render_series_tile_grid(tiles_df, key_prefix: str = "series"):
    """Render series tiles in a 3-wide grid using st.columns."""
    _inject_tile_css()

    for row_start in range(0, len(tiles_df), 3):
        cols = st.columns(3)
        for col_idx in range(3):
            idx = row_start + col_idx
            if idx < len(tiles_df):
                with cols[col_idx]:
                    tile_data = tiles_df.iloc[idx].to_dict()
                    _render_single_series_tile(
                        tile_data, key_prefix=f"{key_prefix}_{idx}",
                    )
```

### 8. `raceanalyzer/ui/charts.py` -- Series Classification Chart

Add stacked bar chart for series classification trends:

```python
def build_series_classification_chart(trend_df: pd.DataFrame):
    """Build a stacked bar chart of finish types by year for a series.

    Args:
        trend_df: DataFrame with columns (year, finish_type, count).

    Returns plotly Figure or None if no data.
    """
    if trend_df.empty:
        return None

    import plotly.express as px

    from raceanalyzer.ui.components import FINISH_TYPE_COLORS

    # Pivot to get finish types as columns
    fig = px.bar(
        trend_df,
        x="year",
        y="count",
        color="finish_type",
        color_discrete_map=FINISH_TYPE_COLORS,
        barmode="stack",
        labels={"count": "Categories", "year": "Year", "finish_type": "Finish Type"},
        title="Classification History by Year",
    )
    fig.update_layout(
        xaxis_type="category",
        legend_title_text="Finish Type",
        height=350,
    )
    return fig
```

### 9. `raceanalyzer/ui/pages/series_detail.py` -- Series Detail Page (NEW FILE)

```python
"""Series Detail page -- all editions of a race series with aggregated stats."""

from __future__ import annotations

import streamlit as st

from raceanalyzer import queries
from raceanalyzer.ui.charts import build_group_structure_chart, build_series_classification_chart
from raceanalyzer.ui.components import (
    FINISH_TYPE_COLORS,
    FINISH_TYPE_ICONS,
    render_confidence_badge,
    render_empty_state,
    render_scary_racer_card,
)
from raceanalyzer.ui.maps import geocode_location, render_course_map, render_location_map


def render():
    session = st.session_state.db_session

    # Back navigation
    if st.button("Back to Calendar"):
        st.switch_page("pages/calendar.py")

    # Get series ID from query params or session state
    series_id_str = st.query_params.get("series_id")
    if not series_id_str and "selected_series_id" in st.session_state:
        series_id_str = str(st.session_state["selected_series_id"])

    if not series_id_str:
        render_empty_state("No series selected.")
        return

    try:
        series_id = int(series_id_str)
    except (ValueError, TypeError):
        render_empty_state("Invalid series ID.")
        return

    detail = queries.get_series_detail(session, series_id)
    if detail is None:
        render_empty_state(f"Series ID {series_id} not found.")
        return

    series_info = detail["series"]
    editions = detail["editions"]
    overall_ft = detail["overall_finish_type"]
    trend_df = detail["classification_trend"]

    # Header
    st.title(series_info["display_name"])

    col1, col2, col3 = st.columns(3)
    col1.metric("Editions", series_info["edition_count"])

    # Date range from editions
    dates = [e["race"]["date"] for e in editions if e["race"].get("date")]
    if dates:
        col2.metric("First Edition", f"{min(dates):%Y}")
        col3.metric("Latest Edition", f"{max(dates):%Y}")

    # Overall classification badge
    from raceanalyzer.queries import FINISH_TYPE_DISPLAY_NAMES, FINISH_TYPE_TOOLTIPS
    ft_display = FINISH_TYPE_DISPLAY_NAMES.get(overall_ft, "Unknown")
    ft_color = FINISH_TYPE_COLORS.get(overall_ft, "#9E9E9E")
    ft_icon = FINISH_TYPE_ICONS.get(overall_ft, FINISH_TYPE_ICONS["unknown"])
    st.markdown(
        f'<div style="margin:8px 0;">'
        f'{ft_icon} <span style="background:{ft_color};color:white;padding:4px 12px;'
        f'border-radius:4px;font-size:1em;">{ft_display}</span>'
        f' <span style="color:#666;font-size:0.9em;">Most common outcome</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.divider()

    # Classification trend chart (stacked bar by year)
    if not trend_df.empty:
        st.subheader("Classification History")
        fig = build_series_classification_chart(trend_df)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Per-edition expandable sections
    st.subheader("Editions")
    for edition in editions:
        race = edition["race"]
        classifications = edition["classifications"]
        results = edition["results"]

        date_str = f"{race['date']:%B %d, %Y}" if race.get("date") else "Unknown date"
        loc = race.get("location", "")
        state = race.get("state_province", "")
        loc_str = f"{loc}, {state}" if state else (loc or "")

        # Compute edition-level overall finish type
        edition_ft = queries._compute_overall_finish_type(session, race["id"])
        ft_badge_color = FINISH_TYPE_COLORS.get(edition_ft, "#9E9E9E")
        ft_badge_name = FINISH_TYPE_DISPLAY_NAMES.get(edition_ft, "Unknown")

        expander_label = (
            f"{race['name']} -- {date_str} -- {ft_badge_name}"
        )

        with st.expander(expander_label, expanded=False):
            # Course map for this edition
            from raceanalyzer.db.models import Race as RaceModel
            race_obj = session.get(RaceModel, race["id"])

            if race_obj and race_obj.rwgps_route_id:
                render_course_map(race_obj.rwgps_route_id)
            elif loc and loc != "Unknown":
                coords = geocode_location(loc, state)
                if coords:
                    render_location_map(*coords)

            # Classifications table
            if not classifications.empty:
                for _, row in classifications.iterrows():
                    cols = st.columns([2, 3, 1])
                    cols[0].write(f"**{row['category']}**")
                    display = queries.finish_type_display_name(row["finish_type"])
                    cols[1].write(display)
                    with cols[2]:
                        render_confidence_badge(
                            row["confidence_label"], row["confidence_color"],
                        )

            # Results
            if not results.empty:
                st.dataframe(
                    results[["category", "place", "name", "team", "race_time"]],
                    use_container_width=True,
                    hide_index=True,
                )


render()
```

### 10. `raceanalyzer/ui/pages/calendar.py` -- Series View Toggle

Update the calendar to show series tiles by default:

```python
def render():
    session = st.session_state.db_session
    filters = render_sidebar_filters(session)

    st.title("PNW Race Calendar")

    # View toggle: series (grouped) vs individual races
    view_mode = st.radio(
        "View",
        ["Series (grouped)", "Individual races"],
        horizontal=True,
        index=0,
    )

    if view_mode == "Series (grouped)":
        df = queries.get_series_tiles(
            session, year=filters["year"], states=filters["states"],
        )

        if df.empty:
            # Fall back to individual if no series exist yet
            st.info(
                "No series found. Run `raceanalyzer build-series` to group races, "
                "or switch to Individual view."
            )
            return

        # Count unknown series
        unknown_count = len(df[df["overall_finish_type"] == "unknown"])
        total_count = len(df)

        show_unknown = st.toggle(
            f"Show unclassified series ({unknown_count} of {total_count})",
            value=False,
        )
        if not show_unknown:
            df = df[df["overall_finish_type"] != "unknown"]

        if df.empty:
            render_empty_state(
                "No classified series. Toggle 'Show unclassified' to see all."
            )
            return

        # Metrics
        col1, col2, col3 = st.columns(3)
        col1.metric("Series", len(df))
        col2.metric("Total Editions", df["edition_count"].sum())
        col3.metric("States", df["state_province"].nunique())

        # Pagination
        if "series_page_size" not in st.session_state:
            st.session_state.series_page_size = TILES_PER_PAGE
        visible_count = st.session_state.series_page_size

        visible_df = df.head(visible_count)
        render_series_tile_grid(visible_df, key_prefix="series")

        if visible_count < len(df):
            remaining = len(df) - visible_count
            if st.button(f"Show more ({remaining} remaining)"):
                st.session_state.series_page_size = visible_count + TILES_PER_PAGE
                st.rerun()

    else:
        # Original individual race view (existing code)
        df = queries.get_race_tiles(
            session, year=filters["year"], states=filters["states"],
        )
        # ... existing individual tile logic unchanged ...
```

### 11. `raceanalyzer/cli.py` -- New Commands

Add `match-routes` and `build-series` commands:

```python
@main.command("match-routes")
@click.option("--force", is_flag=True, help="Re-match races that already have a route.")
@click.option(
    "--min-score",
    type=float,
    default=0.3,
    help="Minimum match score (0.0-1.0, default: 0.3).",
)
@click.pass_context
def match_routes(ctx, force, min_score):
    """Match races to RideWithGPS routes for course maps."""
    settings = ctx.obj["settings"]

    from raceanalyzer.db.engine import get_session
    from raceanalyzer.rwgps import match_all_races

    session = get_session(settings.db_path)
    click.echo("Matching races to RWGPS routes (this may take a while)...")

    summary = match_all_races(session, force=force)
    click.echo(
        f"Done: {summary['matched']} matched, "
        f"{summary['failed']} unmatched, "
        f"{summary['skipped']} skipped."
    )
    session.close()


@main.command("build-series")
@click.pass_context
def build_series_cmd(ctx):
    """Group races into series by normalized name."""
    settings = ctx.obj["settings"]

    from raceanalyzer.db.engine import get_session
    from raceanalyzer.series import build_series

    session = get_session(settings.db_path)
    click.echo("Building race series from normalized names...")

    summary = build_series(session)
    click.echo(
        f"Created {summary['series_created']} series, "
        f"linked {summary['races_linked']} races."
    )
    session.close()
```

### 12. DB Migration Helper

Add to `raceanalyzer/db/engine.py` or a new migration utility:

```python
def migrate_006(engine):
    """Sprint 006 migration: add rwgps_route_id, series_id columns and race_series table."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    with engine.begin() as conn:
        # Create race_series table if not exists
        if "race_series" not in existing_tables:
            conn.execute(text("""
                CREATE TABLE race_series (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    normalized_name VARCHAR NOT NULL UNIQUE,
                    display_name VARCHAR NOT NULL
                )
            """))
            conn.execute(text(
                "CREATE INDEX ix_race_series_normalized_name "
                "ON race_series (normalized_name)"
            ))

        # Add columns to races if not present
        race_columns = {col["name"] for col in inspector.get_columns("races")}

        if "rwgps_route_id" not in race_columns:
            conn.execute(text(
                "ALTER TABLE races ADD COLUMN rwgps_route_id INTEGER"
            ))

        if "series_id" not in race_columns:
            conn.execute(text(
                "ALTER TABLE races ADD COLUMN series_id INTEGER "
                "REFERENCES race_series(id)"
            ))
            conn.execute(text(
                "CREATE INDEX ix_races_series_id ON races (series_id)"
            ))
```

---

## Files Summary

| File | Action | Description |
|------|--------|-------------|
| `raceanalyzer/db/models.py` | **Modify** | Add `RaceSeries` model, `rwgps_route_id` and `series_id` columns on `Race` |
| `raceanalyzer/db/engine.py` | **Modify** | Add `migrate_006()` for schema migration |
| `raceanalyzer/series.py` | **Create** | Name normalization (`normalize_race_name`), `build_series()` |
| `raceanalyzer/rwgps.py` | **Create** | RWGPS search API client, route matching and scoring |
| `raceanalyzer/queries.py` | **Modify** | Add `get_series_tiles()`, `get_series_detail()`, `_compute_series_overall_finish_type()` |
| `raceanalyzer/ui/maps.py` | **Modify** | Add `render_course_map()` for RWGPS iframe embed |
| `raceanalyzer/ui/components.py` | **Modify** | Add `_render_single_series_tile()`, `render_series_tile_grid()` |
| `raceanalyzer/ui/charts.py` | **Modify** | Add `build_series_classification_chart()` (stacked bar) |
| `raceanalyzer/ui/pages/calendar.py` | **Modify** | Series/individual toggle, series tile rendering |
| `raceanalyzer/ui/pages/race_detail.py` | **Modify** | RWGPS course map, series link |
| `raceanalyzer/ui/pages/series_detail.py` | **Create** | Series detail page with editions, chart, expandable detail |
| `raceanalyzer/cli.py` | **Modify** | Add `match-routes` and `build-series` commands |
| `tests/test_series.py` | **Create** | Name normalization tests, series building tests |
| `tests/test_rwgps.py` | **Create** | RWGPS search mocking, route scoring tests |
| `tests/test_queries.py` | **Modify** | Series tile queries, series overall finish type |

**Total new files**: 4 (`series.py`, `rwgps.py`, `series_detail.py`, `test_series.py`, `test_rwgps.py`)
**Total modified files**: 10
**Estimated new tests**: ~15-20

---

## Test Plan

### `tests/test_series.py` (NEW)

```python
class TestNormalizeRaceName:
    def test_strips_four_digit_year(self):
        assert normalize_race_name("Banana Belt RR 2024") == "banana belt road race"

    def test_strips_ordinal_annual(self):
        assert normalize_race_name("23rd Annual Banana Belt RR") == "banana belt road race"

    def test_normalizes_rr_suffix(self):
        assert normalize_race_name("Banana Belt RR") == "banana belt road race"

    def test_normalizes_tt_suffix(self):
        assert normalize_race_name("Twilight TT") == "twilight time trial"

    def test_normalizes_crit_suffix(self):
        assert normalize_race_name("Red R Crit") == "red r criterium"

    def test_strips_sponsor(self):
        assert normalize_race_name(
            "Banana Belt RR presented by Bike Shop"
        ) == "banana belt road race"

    def test_consistent_across_years(self):
        """Same race in different years normalizes to same key."""
        assert (
            normalize_race_name("Banana Belt RR 2022")
            == normalize_race_name("Banana Belt RR 2024")
        )

    def test_rr_vs_road_race_match(self):
        """'RR' and 'Road Race' normalize to the same key."""
        assert (
            normalize_race_name("Banana Belt RR")
            == normalize_race_name("Banana Belt Road Race")
        )

    def test_empty_string(self):
        assert normalize_race_name("") == ""

    def test_no_change_needed(self):
        assert normalize_race_name("mason lake") == "mason lake"


class TestBuildSeries:
    def test_groups_same_normalized_name(self, session_with_races):
        """Two races with same normalized name end up in one series."""
        summary = build_series(session_with_races)
        assert summary["series_created"] >= 1

    def test_different_races_separate_series(self, session_with_races):
        """Races with different normalized names get separate series."""
        # Verify distinct normalized names -> distinct series
        ...

    def test_idempotent(self, session_with_races):
        """Running build_series twice doesn't create duplicates."""
        build_series(session_with_races)
        summary2 = build_series(session_with_races)
        assert summary2["series_created"] == 0
```

### `tests/test_rwgps.py` (NEW)

```python
class TestScoreRouteMatch:
    def test_exact_name_match_high_score(self):
        route = {"name": "Banana Belt Road Race", "lat": 45.5, "lng": -122.6}
        score = _score_route_match(route, "Banana Belt Road Race", 45.5, -122.6)
        assert score > 0.8

    def test_no_name_overlap_low_score(self):
        route = {"name": "Portland Century Ride", "lat": 45.5, "lng": -122.6}
        score = _score_route_match(route, "Banana Belt RR", 45.5, -122.6)
        assert score < 0.5

    def test_nearby_location_boosts_score(self):
        route = {"name": "Banana Belt", "lat": 45.50, "lng": -122.60}
        score_near = _score_route_match(route, "Banana Belt", 45.51, -122.61)
        score_far = _score_route_match(route, "Banana Belt", 47.0, -120.0)
        assert score_near > score_far


class TestSearchRwgpsRoutes:
    @patch("raceanalyzer.rwgps.requests.get")
    def test_returns_routes_on_success(self, mock_get):
        mock_get.return_value.ok = True
        mock_get.return_value.json.return_value = {
            "results": [
                {"id": 123, "name": "Test Route", "type": "route",
                 "distance": 50000, "elevation_gain": 500,
                 "lat": 45.5, "lng": -122.6}
            ],
            "results_count": 1,
        }
        results = search_rwgps_routes("Test Route")
        assert len(results) == 1
        assert results[0]["id"] == 123

    @patch("raceanalyzer.rwgps.requests.get")
    def test_returns_empty_on_failure(self, mock_get):
        mock_get.return_value.ok = False
        results = search_rwgps_routes("Nothing")
        assert results == []

    @patch("raceanalyzer.rwgps.requests.get")
    def test_filters_out_trips(self, mock_get):
        """Only routes (not trips) should be returned."""
        mock_get.return_value.ok = True
        mock_get.return_value.json.return_value = {
            "results": [
                {"id": 1, "name": "A Route", "type": "route"},
                {"id": 2, "name": "A Trip", "type": "trip"},
            ],
        }
        results = search_rwgps_routes("test")
        assert len(results) == 1
        assert results[0]["type"] == "route"
```

### `tests/test_queries.py` (MODIFY)

Add tests for series tile queries and series overall finish type:

```python
class TestSeriesTiles:
    def test_returns_series_with_editions(self, session_with_series):
        df = get_series_tiles(session_with_series)
        assert not df.empty
        assert "edition_count" in df.columns
        assert df.iloc[0]["edition_count"] > 0

    def test_filters_by_year(self, session_with_series):
        df = get_series_tiles(session_with_series, year=2024)
        # Only series with editions in 2024
        assert all(df["last_date"].dt.year >= 2024)


class TestSeriesOverallFinishType:
    def test_most_common_across_editions(self, session_with_series):
        ft = _compute_series_overall_finish_type(session_with_series, series_id=1)
        assert ft != "unknown"

    def test_unknown_when_no_classifications(self, session_with_empty_series):
        ft = _compute_series_overall_finish_type(
            session_with_empty_series, series_id=1,
        )
        assert ft == "unknown"
```

---

## Definition of Done

1. `RaceSeries` table exists with `normalized_name` (unique) and `display_name`
2. `Race` model has `rwgps_route_id` (nullable int) and `series_id` FK (nullable)
3. `normalize_race_name()` strips years, normalizes suffixes (RR->Road Race, TT->Time Trial, etc.), strips sponsors
4. `"Banana Belt RR 2022"` and `"Banana Belt Road Race 2024"` normalize to the same key
5. `raceanalyzer build-series` groups all races into series by normalized name; idempotent
6. `raceanalyzer match-routes` searches RWGPS for each race and stores best route_id; rate-limited at 1 req/sec
7. RWGPS route scoring uses 0.7 * name_similarity + 0.3 * geo_proximity; minimum score threshold of 0.3
8. Race detail page shows RWGPS iframe embed when `rwgps_route_id` is set; falls back to Nominatim area map
9. Calendar defaults to series view with one tile per series showing: display name, edition count, date range, location, overall badge
10. Calendar has toggle to switch between "Series (grouped)" and "Individual races" views
11. Series detail page shows: header with edition count/date range, overall badge, stacked bar chart of finish types by year, expandable per-edition detail
12. Series overall badge = most frequent non-UNKNOWN finish type across all editions and categories
13. `migrate_006()` handles schema upgrade for existing databases (additive ALTER TABLE + CREATE TABLE)
14. All existing tests pass (zero regressions)
15. New tests: name normalization (10+), series building (3+), RWGPS search/scoring (5+), series queries (3+)

---

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| RWGPS undocumented API changes or rate limits | No course maps | Medium | Graceful fallback to Nominatim area map; store route_id so re-fetch not needed |
| RWGPS search returns irrelevant routes | Wrong course maps | Medium | Scoring threshold (min 0.3); manual override column possible in future sprint |
| Name normalization misgroups different races | Wrong series grouping | Low | Conservative approach (exact normalized match, no fuzzy); sponsor stripping is aggressive but safe |
| Name normalization fails to group variants | Some duplicates remain | Medium | Handle most common suffixes (RR, TT, CR, GP); manual merge can be added later |
| RWGPS embed iframe blocked by CSP | Blank map frame | Low | Test in Streamlit iframe context; RWGPS embeds are designed for third-party embedding |
| Batch route matching takes long (269+ races at 1 req/sec) | ~5 min CLI wait | Low | Progress output; --force flag for re-runs; only unmatched races by default |
| SQLite ALTER TABLE limitations | Migration fails | Very Low | Only adding nullable columns (no NOT NULL, no default needed) |
| Nominatim geocoding needed for RWGPS search coords | Slower matching | Low | Geocode cache already exists in maps.py; one-time cost per unique location |

---

## Security

- RWGPS route IDs are integers validated with `int()` before embedding in iframe URLs
- RWGPS iframe uses `sandbox="allow-scripts allow-same-origin"` to restrict embed capabilities
- All dynamic strings in HTML tiles continue to be escaped via `html.escape()`
- RWGPS API requests use descriptive User-Agent per best practice
- No user-controlled data flows into SQL queries beyond parameterized SQLAlchemy ORM calls
- Series normalized names are derived server-side from existing race names, not user input

---

## Dependencies

- No new Python packages required
- `requests` already in dependencies (for RWGPS API and Nominatim)
- `plotly` already in dependencies (for stacked bar chart)
- External APIs: RWGPS `/find/search.json` (undocumented, no auth), Nominatim (free, no key)

---

## Scope Cut Guidance

If constrained, cut in this order (last = cut first):

1. **Keep**: Race series grouping (normalize + build-series), series tiles on calendar, series detail page with aggregated badge
2. **Keep**: RWGPS route matching (match-routes CLI), course map embed on race detail
3. **Cut if needed**: Stacked bar classification trend chart on series detail (can show flat list instead)
4. **Cut if needed**: Series/individual toggle on calendar (just show series view, link to individual from series detail)
5. **Cut last**: RWGPS geographic search (can search by name only without geocoding lat/lng)

---

## Open Questions

1. **RWGPS response schema**: The `/find/search.json` endpoint is undocumented. The response shape (`results`, `results_count`, field names) needs validation against a live request before finalizing the client code. Run a test query early in the sprint.
2. **Multiple editions per year**: Some races (Mason Lake, Pacific Raceways) have 2+ editions in the same year. These will be grouped into the same series correctly, but the stacked bar chart should show them as additive counts within the same year bar -- confirmed by the `groupby` aggregation approach.
3. **Series display name selection**: Currently picks the longest edition name with year stripped. May want to use the most recent edition's name instead. Low stakes, easy to adjust.
4. **Streamlit page routing for series_detail**: Need to register `series_detail.py` in the Streamlit multipage app config if using `st.switch_page()`. Verify the app structure supports dynamic page addition.
