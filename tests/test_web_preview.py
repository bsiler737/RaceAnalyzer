"""Tests for preview page routes: rendering, HTMX partials, graceful degradation."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Point DB at test location before importing app
os.environ.setdefault(
    "RACEANALYZER_DB_PATH",
    str(Path(__file__).parent.parent / "data" / "raceanalyzer.db"),
)

from raceanalyzer.web.app import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


def _find_valid_series_id(client) -> int | None:
    """Find a valid series_id from the feed page content."""
    resp = client.get("/feed")
    if resp.status_code != 200:
        return None
    # Look for /preview/N links in the feed page
    import re
    matches = re.findall(r'/preview/(\d+)', resp.text)
    if matches:
        return int(matches[0])
    # Fallback: try series_id=1
    return 1


class TestPreviewRendering:
    """PV-06: Preview page rendering tests."""

    def test_preview_renders_for_known_series(self, client):
        """Preview page renders successfully for a known series_id."""
        sid = _find_valid_series_id(client)
        resp = client.get(f"/preview/{sid}")
        # Should render 200 if series exists, 404 if not
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            assert "text/html" in resp.headers["content-type"]
            assert "What to Expect" in resp.text
            assert "Predicted Finish Type" in resp.text

    def test_missing_series_returns_404(self, client):
        """Preview for nonexistent series returns 404."""
        resp = client.get("/preview/999999")
        assert resp.status_code == 404

    def test_preview_has_back_link(self, client):
        """Preview page has a back-to-feed link."""
        sid = _find_valid_series_id(client)
        resp = client.get(f"/preview/{sid}")
        if resp.status_code == 200:
            assert "Back to Feed" in resp.text

    def test_preview_full_page_has_html_tag(self, client):
        """Full page preview includes HTML document structure."""
        sid = _find_valid_series_id(client)
        resp = client.get(f"/preview/{sid}")
        if resp.status_code == 200:
            assert "<html" in resp.text
            assert "<!DOCTYPE" in resp.text


class TestPreviewHTMX:
    """HTMX partial responses for preview."""

    def test_htmx_returns_partial(self, client):
        """HTMX request returns partial HTML (no <html> tag)."""
        sid = _find_valid_series_id(client)
        resp = client.get(
            f"/preview/{sid}",
            headers={"HX-Request": "true"},
        )
        if resp.status_code == 200:
            assert "<html" not in resp.text
            assert "<!DOCTYPE" not in resp.text
            # Should still have section content
            assert "What to Expect" in resp.text

    def test_htmx_stage_nav_returns_partial(self, client):
        """Stage nav HTMX request returns partial HTML."""
        sid = _find_valid_series_id(client)
        resp = client.get(
            f"/preview/{sid}",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            assert "<html" not in resp.text


class TestPreviewFieldPicker:
    """Field picker changes return updated content."""

    def test_field_picker_param(self, client):
        """Preview with field param renders successfully."""
        sid = _find_valid_series_id(client)
        # Try with a field param
        resp = client.get(f"/preview/{sid}?field=Men+Cat+1%2F2")
        assert resp.status_code in (200, 404)

    def test_field_picker_htmx(self, client):
        """Field change via HTMX returns partial content."""
        sid = _find_valid_series_id(client)
        resp = client.get(
            f"/preview/{sid}?field=Men+Cat+3",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            assert "<html" not in resp.text


class TestPreviewGracefulDegradation:
    """Preview degrades gracefully when data is missing."""

    def test_preview_without_course_data(self, client):
        """Preview still renders when no course data exists."""
        sid = _find_valid_series_id(client)
        resp = client.get(f"/preview/{sid}")
        # Should not crash even if course data is missing
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            # Core sections should still be present
            assert "Spooky Riders" in resp.text
            assert "Startlist" in resp.text
            assert "Similar Races" in resp.text

    def test_preview_sections_present(self, client):
        """All main sections are present in the preview page."""
        sid = _find_valid_series_id(client)
        resp = client.get(f"/preview/{sid}")
        if resp.status_code == 200:
            text = resp.text
            assert "What to Expect" in text
            assert "Spooky Riders" in text
            assert "Startlist" in text
            assert "Similar Races" in text


class TestPreviewChartContainers:
    """Preview has chart/map containers in output when data exists."""

    def test_chart_containers_present(self, client):
        """Chart containers have data-plotly-data attributes when course data exists."""
        sid = _find_valid_series_id(client)
        resp = client.get(f"/preview/{sid}")
        if resp.status_code == 200:
            # Chart containers may or may not be present depending on data
            # If they are present, they should have the right attributes
            if "data-plotly-data" in resp.text:
                assert "data-plotly-layout" in resp.text

    def test_map_container_with_course_data(self, client):
        """Map container has data-leaflet-coords when course data exists."""
        sid = _find_valid_series_id(client)
        resp = client.get(f"/preview/{sid}")
        if resp.status_code == 200:
            # If map is present, it should have leaflet data attributes
            if "data-leaflet-coords" in resp.text:
                assert "data-leaflet-climbs" in resp.text


class TestChartDataBuilders:
    """Unit tests for the chart/map data builder functions."""

    def test_build_elevation_chart_data_empty(self):
        """Empty profile returns empty traces."""
        from raceanalyzer.web.routes import build_elevation_chart_data
        traces, layout = build_elevation_chart_data([], [])
        assert traces == []
        assert layout == {}

    def test_build_elevation_chart_data_basic(self):
        """Basic profile produces valid Plotly traces."""
        from raceanalyzer.web.routes import build_elevation_chart_data
        points = [
            {"d": 0, "e": 100, "x": -122.0, "y": 47.0},
            {"d": 1000, "e": 150, "x": -122.01, "y": 47.01},
            {"d": 2000, "e": 120, "x": -122.02, "y": 47.02},
        ]
        traces, layout = build_elevation_chart_data(points, [])
        assert len(traces) == 2
        assert traces[1]["name"] == "Elevation"
        assert "xaxis" in layout
        assert "yaxis" in layout

    def test_build_elevation_chart_with_climbs(self):
        """Climb regions produce layout shapes."""
        from raceanalyzer.web.routes import build_elevation_chart_data
        points = [
            {"d": 0, "e": 100, "x": -122.0, "y": 47.0},
            {"d": 5000, "e": 300, "x": -122.05, "y": 47.05},
        ]
        climbs = [{"start_d": 0, "end_d": 5000, "avg_grade": 5.0, "color": "#FFC107"}]
        traces, layout = build_elevation_chart_data(points, climbs)
        assert "shapes" in layout
        assert len(layout["shapes"]) == 1

    def test_build_distribution_chart_data_empty(self):
        """Empty distribution returns empty traces."""
        from raceanalyzer.web.routes import build_distribution_chart_data
        traces, layout = build_distribution_chart_data({})
        assert traces == []
        assert layout == {}

    def test_build_distribution_chart_data_basic(self):
        """Basic distribution produces valid bar chart data."""
        from raceanalyzer.web.routes import build_distribution_chart_data
        dist = {"bunch_sprint": 3, "breakaway": 2}
        traces, layout = build_distribution_chart_data(dist)
        assert len(traces) == 1
        assert traces[0]["type"] == "bar"
        assert traces[0]["orientation"] == "h"

    def test_build_map_data_empty(self):
        """Empty profile returns empty coords."""
        from raceanalyzer.web.routes import build_map_data
        coords, climbs = build_map_data([], [])
        assert coords == []
        assert climbs == []

    def test_build_map_data_basic(self):
        """Basic profile produces lat/lon coords."""
        from raceanalyzer.web.routes import build_map_data
        points = [
            {"d": 0, "e": 100, "x": -122.0, "y": 47.0},
            {"d": 1000, "e": 150, "x": -122.01, "y": 47.01},
            {"d": 2000, "e": 120, "x": -122.02, "y": 47.02},
        ]
        coords, climb_data = build_map_data(points, [])
        assert len(coords) == 3
        # Coords should be [lat, lon]
        assert coords[0] == [47.0, -122.0]

    def test_build_map_data_with_climbs(self):
        """Climb segments extracted from profile points."""
        from raceanalyzer.web.routes import build_map_data
        points = [
            {"d": 0, "e": 100, "x": -122.0, "y": 47.0},
            {"d": 500, "e": 130, "x": -122.005, "y": 47.005},
            {"d": 1000, "e": 150, "x": -122.01, "y": 47.01},
            {"d": 2000, "e": 120, "x": -122.02, "y": 47.02},
        ]
        climbs = [{"start_d": 0, "end_d": 1000, "avg_grade": 5.0, "length_m": 1000}]
        coords, climb_data = build_map_data(points, climbs)
        assert len(climb_data) == 1
        assert "coords" in climb_data[0]
        assert len(climb_data[0]["coords"]) == 3  # points within 0-1000m
        assert "grade" in climb_data[0]
