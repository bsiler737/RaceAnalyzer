"""Location geocoding, area maps, and course map rendering."""

from __future__ import annotations

import logging
from typing import Optional

import requests
import streamlit as st

logger = logging.getLogger(__name__)

_GEOCODE_CACHE: dict[str, tuple[float, float] | None] = {}


def geocode_location(
    location: str, state: str = "",
) -> tuple[float, float] | None:
    """Geocode a location string via Nominatim. Returns (lat, lon) or None.

    Results are cached in-memory for the session.
    """
    query = f"{location}, {state}" if state else location
    if not query.strip():
        return None

    if query in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[query]

    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": "RaceAnalyzer/0.1 (PNW bike race analysis)"},
            timeout=5,
        )
        if resp.ok and resp.json():
            data = resp.json()[0]
            result = (float(data["lat"]), float(data["lon"]))
            _GEOCODE_CACHE[query] = result
            return result
    except Exception:
        logger.debug("Geocoding failed for %s", query)

    _GEOCODE_CACHE[query] = None
    return None


def render_location_map(lat: float, lon: float, zoom: int = 12):
    """Render an OpenStreetMap embed centered on lat/lon using an iframe."""
    osm_url = (
        f"https://www.openstreetmap.org/export/embed.html"
        f"?bbox={lon - 0.05},{lat - 0.03},{lon + 0.05},{lat + 0.03}"
        f"&layer=mapnik&marker={lat},{lon}"
    )
    st.markdown(
        f'<iframe src="{osm_url}" width="100%" height="250" '
        f'style="border:1px solid #e0e0e0;border-radius:8px;" '
        f'loading="lazy"></iframe>',
        unsafe_allow_html=True,
    )


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
        coords, color="#FC4C02", weight=4, opacity=0.8, tooltip=race_name,
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
    m.fit_bounds([
        [min(c[0] for c in coords), min(c[1] for c in coords)],
        [max(c[0] for c in coords), max(c[1] for c in coords)],
    ])

    st_folium(m, use_container_width=True, height=400, returned_objects=[])
