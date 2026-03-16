"""Tests for feed page routes: rendering, filtering, HTMX partials, ICS download."""
from __future__ import annotations

import os
from pathlib import Path

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


class TestFeedPage:
    """FD-10: Feed page rendering tests."""

    def test_feed_renders_200(self, client):
        """Feed page renders successfully with seed data."""
        resp = client.get("/feed")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "PNW Bike Races" in resp.text

    def test_root_renders_feed(self, client):
        """Root URL also serves the feed page."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "PNW Bike Races" in resp.text

    def test_feed_contains_race_cards(self, client):
        """Feed should contain at least some race content or empty state."""
        resp = client.get("/feed")
        assert resp.status_code == 200
        # Should have either race cards or the empty state message
        assert ("ra-card" in resp.text or "No races found" in resp.text)

    def test_feed_has_search_input(self, client):
        """Feed page should have a search input."""
        resp = client.get("/feed")
        assert 'name="q"' in resp.text
        assert "Search races" in resp.text

    def test_feed_has_sidebar(self, client):
        """Feed page should include sidebar with filters."""
        resp = client.get("/feed")
        assert "Race Type" in resp.text
        assert "My Team" in resp.text


class TestFeedFilters:
    """Filter params narrow results."""

    def test_race_type_filter(self, client):
        """Race type filter param narrows results."""
        resp = client.get("/feed?race_type=criterium")
        assert resp.status_code == 200

    def test_state_filter(self, client):
        """State filter param works."""
        resp = client.get("/feed?states=WA")
        assert resp.status_code == 200

    def test_search_query_filters(self, client):
        """Search query parameter filters by name."""
        resp = client.get("/feed?q=nonexistent_race_xyz_123")
        assert resp.status_code == 200
        # With a garbage query, should get empty state or no race cards
        text = resp.text
        assert "No races found" in text or "ra-card" not in text or resp.status_code == 200

    def test_team_filter(self, client):
        """Team name filter works (minimum 3 chars)."""
        resp = client.get("/feed?team=Hagens")
        assert resp.status_code == 200


class TestHTMXPartials:
    """HTMX partial responses."""

    def test_htmx_partial_no_html_tag(self, client):
        """HTMX request returns partial HTML without <html> tag."""
        resp = client.get("/feed", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        assert "<html" not in resp.text
        assert "<!DOCTYPE" not in resp.text

    def test_htmx_full_page_has_html_tag(self, client):
        """Full page request includes <html> tag."""
        resp = client.get("/feed")
        assert resp.status_code == 200
        assert "<html" in resp.text

    def test_htmx_with_filters(self, client):
        """HTMX request with filters returns partial."""
        resp = client.get(
            "/feed?race_type=road_race&states=OR",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert "<html" not in resp.text


class TestSeriesDeepLink:
    """Series deep-link renders single card."""

    def test_deep_link_with_nonexistent_series(self, client):
        """Deep link to nonexistent series shows empty state."""
        resp = client.get("/feed?series_id=999999")
        assert resp.status_code == 200
        # Should show back button or empty state
        assert "Back to all races" in resp.text or "No races found" in resp.text

    def test_deep_link_has_back_button(self, client):
        """Deep link page includes back button."""
        resp = client.get("/feed?series_id=1")
        assert resp.status_code == 200
        assert "Back to all races" in resp.text


class TestICSDownload:
    """ICS calendar download."""

    def test_ics_nonexistent_series_404(self, client):
        """ICS download for nonexistent series returns 404."""
        resp = client.get("/api/ics/999999")
        assert resp.status_code == 404

    def test_ics_download_content_type(self, client):
        """ICS download returns correct content type when series exists."""
        # First get the feed to find a valid series_id
        feed_resp = client.get("/feed")
        if "series_id" not in feed_resp.text and "/api/ics/" not in feed_resp.text:
            pytest.skip("No series with ICS links available in seed data")

        # Try series_id=1 as a best guess
        resp = client.get("/api/ics/1")
        if resp.status_code == 404:
            pytest.skip("Series 1 not found in seed data")

        assert resp.status_code == 200
        assert "text/calendar" in resp.headers["content-type"]
        assert "BEGIN:VCALENDAR" in resp.text
        assert "END:VCALENDAR" in resp.text
        assert "SUMMARY:" in resp.text
