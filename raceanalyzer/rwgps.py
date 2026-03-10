"""RideWithGPS route discovery, scoring, and polyline fetching."""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from math import asin, cos, radians, sin, sqrt
from typing import Optional

import requests

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

MIN_MATCH_SCORE = 0.25


def search_routes(
    keywords: str,
    limit: int = 20,
) -> list[dict]:
    """Search RWGPS for public routes matching keywords.

    Note: RWGPS search returns 0 results when lat/lng params are provided,
    so we search by keywords only and use post-hoc proximity scoring instead.
    """
    params: dict = {
        "search[keywords]": keywords,
        "search[models]": "Route",
        "search[offset]": 0,
        "search[limit]": limit,
    }

    try:
        resp = requests.get(
            _RWGPS_SEARCH_URL,
            params=params,
            headers={"User-Agent": "RaceAnalyzer/0.1"},
            timeout=10,
        )
        if resp.ok:
            data = resp.json()
            raw = data.get("results", data) if isinstance(data, dict) else data
            # Unwrap nested {"type": "route", "route": {...}} format
            return [
                item.get("route", item) if isinstance(item, dict) and "route" in item else item
                for item in raw
            ]
    except Exception:
        logger.debug("RWGPS search failed for %s", keywords)
    return []


def _clean_search_name(name: str) -> str:
    """Strip year and type suffixes from race name for better RWGPS search."""
    s = re.sub(r"\b(19|20)\d{2}\b", "", name)
    s = re.sub(
        r"\b(rr|road race|criterium|crit|tt|time trial)\b", "", s, flags=re.IGNORECASE
    )
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
            prox_score = max(0.0, 1.0 - dist_km / 50.0)

    # 3. Route length fit (race-type-aware)
    length_score = 0.5
    route_dist_km = (route.get("distance") or 0) / 1000.0
    if race_type and race_type in _DISTANCE_EXPECTATIONS and route_dist_km > 0:
        lo, hi = _DISTANCE_EXPECTATIONS[race_type]
        if lo <= route_dist_km <= hi:
            length_score = 1.0
        elif route_dist_km < lo:
            length_score = max(0.0, 1.0 - (lo - route_dist_km) / lo)
        else:
            length_score = max(0.0, 1.0 - (route_dist_km - hi) / hi)

    return _W_NAME * name_score + _W_PROXIMITY * prox_score + _W_LENGTH * length_score


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in km."""
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
            # Try track points -> encode
            track = data.get("track_points", [])
            if track:
                import polyline as pl

                coords = [
                    (p.get("y", p.get("lat")), p.get("x", p.get("lng")))
                    for p in track
                ]
                return pl.encode(coords)
    except Exception:
        logger.debug("Failed to fetch polyline for route %d", route_id)
    return None


def _compute_elevation_from_track(track_points: list[dict]) -> Optional[dict]:
    """Compute elevation stats from RWGPS track_points array.

    Sums positive elevation deltas for gain, negative for loss.
    Uses haversine for cumulative distance.
    """
    if not track_points or len(track_points) < 2:
        return None

    total_gain = 0.0
    total_loss = 0.0
    total_distance = 0.0
    elevations = []

    for i, pt in enumerate(track_points):
        elev = pt.get("e", pt.get("elevation"))
        if elev is not None:
            elevations.append(float(elev))

        if i > 0:
            lat1 = pt.get("y", pt.get("lat"))
            lon1 = pt.get("x", pt.get("lng"))
            prev = track_points[i - 1]
            lat2 = prev.get("y", prev.get("lat"))
            lon2 = prev.get("x", prev.get("lng"))

            if all(v is not None for v in [lat1, lon1, lat2, lon2]):
                total_distance += _haversine(
                    float(lat2), float(lon2), float(lat1), float(lon1)
                ) * 1000  # km to m

            prev_elev = prev.get("e", prev.get("elevation"))
            if elev is not None and prev_elev is not None:
                delta = float(elev) - float(prev_elev)
                if delta > 0:
                    total_gain += delta
                else:
                    total_loss += abs(delta)

    if not elevations:
        return None

    return {
        "distance_m": total_distance,
        "total_gain_m": total_gain,
        "total_loss_m": total_loss,
        "max_elevation_m": max(elevations),
        "min_elevation_m": min(elevations),
    }


def fetch_route_elevation(route_id: int) -> Optional[dict]:
    """Fetch elevation stats from RWGPS route detail JSON.

    Returns dict with keys: distance_m, total_gain_m, total_loss_m,
    max_elevation_m, min_elevation_m. Returns None on failure.

    Falls back to computing from track_points if summary stats
    are not present in the RWGPS response.
    """
    try:
        resp = requests.get(
            _RWGPS_ROUTE_URL.format(route_id=route_id),
            headers={"User-Agent": "RaceAnalyzer/0.1"},
            timeout=15,
        )
        if not resp.ok:
            return None

        data = resp.json()

        # Try summary fields first
        elevation_gain = data.get("elevation_gain")
        distance = data.get("distance")

        if elevation_gain is not None and distance is not None:
            return {
                "distance_m": float(distance),
                "total_gain_m": float(elevation_gain),
                "total_loss_m": float(data.get("elevation_loss", 0)),
                "max_elevation_m": float(data.get("max_elevation", 0))
                if data.get("max_elevation") is not None
                else None,
                "min_elevation_m": float(data.get("min_elevation", 0))
                if data.get("min_elevation") is not None
                else None,
            }

        # Fallback: compute from track_points
        track = data.get("track_points", [])
        return _compute_elevation_from_track(track)

    except Exception:
        logger.debug("Failed to fetch elevation for route %d", route_id)
    return None


def match_race_to_route(
    race_name: str,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    race_type: Optional[str] = None,
) -> Optional[dict]:
    """Find best RWGPS route match for a race.

    Returns {route_id, score, name} or None.
    """
    keywords = _clean_search_name(race_name)
    routes = search_routes(keywords)

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
