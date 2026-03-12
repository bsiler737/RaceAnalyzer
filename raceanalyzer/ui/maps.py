"""Location geocoding, area maps, and course map rendering."""

from __future__ import annotations

import logging
import math
from pathlib import Path

import requests
import streamlit as st

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"

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


# --- Sprint 013: Utility functions ---


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate haversine distance in km between two lat/lon points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def polyline_centroid(encoded_polyline: str) -> tuple[float, float] | None:
    """Compute centroid of an encoded polyline. Returns (lat, lon) or None."""
    try:
        import polyline as pl

        coords = pl.decode(encoded_polyline)
        if not coords:
            return None
        avg_lat = sum(c[0] for c in coords) / len(coords)
        avg_lon = sum(c[1] for c in coords) / len(coords)
        return (avg_lat, avg_lon)
    except Exception:
        return None


# --- PNW state centroids (fallback for geocoding) ---

_STATE_CENTROIDS: dict[str, tuple[float, float]] = {
    "WA": (47.4, -120.7),
    "OR": (43.8, -120.5),
    "ID": (44.1, -114.7),
    "BC": (53.7, -127.6),
    "CA": (36.8, -119.4),
    "MT": (46.9, -110.4),
}


def _get_item_coords(item: dict) -> tuple[float, float] | None:
    """Get coordinates for a feed item.

    Tries polyline centroid, then geocoding, then state fallback.
    """
    # Try polyline centroid first
    polyline = item.get("rwgps_encoded_polyline")
    if polyline:
        result = polyline_centroid(polyline)
        if result:
            return result

    # Try geocoding
    loc = item.get("location", "")
    state = item.get("state_province", "")
    if loc:
        result = geocode_location(loc, state)
        if result:
            return result

    # State centroid fallback
    if state:
        return _STATE_CENTROIDS.get(state.upper())

    return None


def render_feed_map(items: list[dict]):
    """Render a Folium map with clustered pins for feed items (Sprint 013: FO-05)."""
    import folium
    from folium.plugins import MarkerCluster
    from streamlit_folium import st_folium

    from raceanalyzer.ui.components import FINISH_TYPE_COLORS

    # Collect pins
    pins = []
    for item in items:
        coords = _get_item_coords(item)
        if not coords:
            continue
        ft = item.get("predicted_finish_type") or "unknown"
        color = FINISH_TYPE_COLORS.get(ft, "#9E9E9E")
        pins.append((coords[0], coords[1], item, color))

    if not pins:
        st.info("No races could be mapped. Location data may be missing.")
        return

    # Center on pins
    avg_lat = sum(p[0] for p in pins) / len(pins)
    avg_lon = sum(p[1] for p in pins) / len(pins)

    m = folium.Map(
        location=[avg_lat, avg_lon],
        zoom_start=7,
        tiles="CartoDB positron",
    )
    cluster = MarkerCluster().add_to(m)

    for lat, lon, item, color in pins:
        name = item.get("display_name", "Race")
        popup_html = (
            f"<b>{name}</b><br>"
            f"{item.get('location', '')}<br>"
            f"{item.get('countdown_label', '')}"
        )
        folium.CircleMarker(
            location=[lat, lon],
            radius=8,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=name,
        ).add_to(cluster)

    result = st_folium(
        m,
        use_container_width=True,
        height=500,
        returned_objects=["last_object_clicked"],
    )

    # Show compact preview card for clicked pin
    if result and result.get("last_object_clicked"):
        click = result["last_object_clicked"]
        click_lat = click.get("lat")
        click_lng = click.get("lng")
        if click_lat and click_lng:
            # Find closest item
            closest = min(
                pins,
                key=lambda p: haversine_km(p[0], p[1], click_lat, click_lng),
            )
            item = closest[2]
            from raceanalyzer.ui.feed_card import build_card_html

            st.markdown(build_card_html(item), unsafe_allow_html=True)

    # --- Races near me (Sprint 013: FO-06) ---
    with st.expander("Races near me"):
        user_loc = st.text_input(
            "Enter your city or zip code",
            placeholder="e.g. Bellingham, WA",
            key="races_near_me_input",
        )
        if user_loc and len(user_loc.strip()) >= 3:
            user_coords = geocode_location(user_loc.strip())
            if user_coords:
                max_km = st.slider("Max distance (km)", 25, 300, 100, key="near_me_dist")
                nearby = [
                    (item, haversine_km(user_coords[0], user_coords[1], lat, lon))
                    for lat, lon, item, _ in pins
                ]
                nearby = [(item, d) for item, d in nearby if d <= max_km]
                nearby.sort(key=lambda x: x[1])
                if nearby:
                    st.caption(f"{len(nearby)} races within {max_km} km")
                    for item, dist in nearby[:10]:
                        st.write(f"**{item['display_name']}** — {dist:.0f} km away")
                else:
                    st.info(f"No races within {max_km} km.")
            else:
                st.warning("Could not find that location. Try a different format.")


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


def render_course_map(encoded_polyline: str, race_name: str = "", climbs=None, profile_points=None):
    """Render a Strava-style route polyline map via Folium."""
    import folium
    import polyline as pl
    from streamlit_folium import st_folium

    coords = pl.decode(encoded_polyline)
    if not coords:
        return

    center = coords[len(coords) // 2]
    m = folium.Map(
        location=center, zoom_start=13, tiles="CartoDB positron",
        scrollWheelZoom=False,
    )
    folium.PolyLine(
        coords, color="#2563EB", weight=4, opacity=0.85, tooltip=race_name,
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

    # DD-07: Overlay colored climb segments on the route
    if climbs and profile_points:
        for i, climb in enumerate(climbs):
            start_d = climb.get("start_d", 0)
            end_d = climb.get("end_d", start_d)
            grade = climb.get("avg_grade", 0)
            color = "#FFC107" if grade < 5 else "#FF5722" if grade < 8 else "#B71C1C"
            # Extract lat/lon points within the climb's distance range
            segment = [
                (p["y"], p["x"]) for p in profile_points
                if start_d <= p.get("d", 0) <= end_d
            ]
            if len(segment) >= 2:
                length_km = climb.get("length_m", 0) / 1000
                popup_text = (
                    f"Climb {i + 1}: {length_km:.1f}km at {grade:.1f}%"
                )
                folium.PolyLine(
                    segment, color=color, weight=7, opacity=0.9,
                    tooltip=popup_text,
                ).add_to(m)

    # Fit bounds to route
    m.fit_bounds([
        [min(c[0] for c in coords), min(c[1] for c in coords)],
        [max(c[0] for c in coords), max(c[1] for c in coords)],
    ])

    st_folium(m, use_container_width=True, height=300, returned_objects=[])


def render_interactive_course_profile(
    profile_points: list[dict],
    climbs: list[dict],
    race_name: str = "",
):
    """Render course map + Plotly elevation chart.

    Uses Folium map + Plotly chart for reliable rendering across all courses.
    """
    _render_fallback_profile(profile_points, climbs, race_name)


def _render_fallback_profile(
    profile_points: list[dict],
    climbs: list[dict],
    race_name: str = "",
):
    """Fallback: Folium map + separate Plotly elevation chart (no hover sync)."""
    import plotly.graph_objects as go

    # Build encoded polyline from profile points for Folium
    try:
        import polyline as pl

        coords = [(p["y"], p["x"]) for p in profile_points]
        encoded = pl.encode(coords)
        render_course_map(encoded, race_name, climbs=climbs, profile_points=profile_points)
    except Exception:
        st.info("Map unavailable.")

    # Plotly elevation chart
    distances = [p["d"] / 1000 for p in profile_points]
    elevations = [p["e"] for p in profile_points]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=distances, y=elevations,
        mode="lines", fill="tozeroy",
        fillcolor="rgba(37, 99, 235, 0.12)",
        line=dict(color="#2563EB", width=2),
        name="Elevation",
    ))

    # Add climb regions
    for climb in (climbs or []):
        fig.add_vrect(
            x0=climb["start_d"] / 1000,
            x1=climb["end_d"] / 1000,
            fillcolor=climb["color"],
            opacity=0.35, line_width=0,
        )

    fig.update_layout(
        xaxis_title="Distance (km)",
        yaxis_title="Elevation (m)",
        margin=dict(l=40, r=10, t=10, b=40),
        height=400,
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)
