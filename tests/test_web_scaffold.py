"""Tests for FastAPI scaffold: health check, static files, error pages, HTMX detection."""
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


def test_root_returns_200(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_static_css_returns_200(client):
    resp = client.get("/static/css/style.css")
    assert resp.status_code == 200


def test_static_htmx_returns_200(client):
    resp = client.get("/static/js/htmx.min.js")
    assert resp.status_code == 200


def test_health_returns_json(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "series_count" in data
    assert isinstance(data["series_count"], int)


def test_404_returns_html(client):
    resp = client.get("/nonexistent-page-xyz")
    assert resp.status_code == 404
    assert "text/html" in resp.headers["content-type"]
    assert "<html" in resp.text


def test_htmx_partial_detection(client):
    """HTMX requests with HX-Request header should return partial HTML."""
    # Full page request should include <html> tag
    full = client.get("/")
    assert "<html" in full.text

    # HTMX request should return partial (no <html>) when supported by route
    htmx_resp = client.get("/", headers={"HX-Request": "true"})
    assert htmx_resp.status_code == 200
