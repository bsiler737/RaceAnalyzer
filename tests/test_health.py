"""Tests for enhanced /health endpoint (Sprint 023)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from raceanalyzer.db.engine import get_session, init_db
from raceanalyzer.db.models import RefreshLog


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def client(tmp_db, monkeypatch):
    """Create a test client with scheduler disabled to avoid background tasks."""
    monkeypatch.setenv("RACEANALYZER_DB_PATH", str(tmp_db))
    monkeypatch.setenv("RACEANALYZER_SCHEDULER_ENABLED", "0")

    from raceanalyzer.web.app import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "series_count" in data

    def test_health_includes_last_refresh(self, client):
        resp = client.get("/health")
        data = resp.json()
        assert "last_refresh" in data
        assert "calendar" in data["last_refresh"]
        assert "startlist" in data["last_refresh"]

    def test_health_includes_scheduler_status(self, client):
        resp = client.get("/health")
        data = resp.json()
        assert "scheduler" in data
        assert "enabled" in data["scheduler"]
        assert "running" in data["scheduler"]
        assert "daily_overdue" in data["scheduler"]
        assert "weekly_overdue" in data["scheduler"]

    def test_health_null_values_when_empty(self, client):
        """Empty RefreshLog returns null timestamps."""
        resp = client.get("/health")
        data = resp.json()
        for step in ("calendar", "startlist"):
            assert data["last_refresh"][step]["last_success"] is None
            assert data["last_refresh"][step]["last_failure"] is None
            assert data["last_refresh"][step]["records_processed"] is None

    def test_health_with_refresh_data(self, client, tmp_db):
        session = get_session(tmp_db)
        session.add(RefreshLog(
            race_id=None,
            refresh_type="calendar",
            refreshed_at=datetime.utcnow(),
            status="success",
            entry_count=23,
        ))
        session.commit()
        session.close()

        resp = client.get("/health")
        data = resp.json()
        assert data["last_refresh"]["calendar"]["last_success"] is not None
        assert data["last_refresh"]["calendar"]["records_processed"] == 23

    def test_health_503_when_stale(self, client, tmp_db):
        """Return 503 if daily refresh is >48h stale."""
        session = get_session(tmp_db)
        # Add an old entry to make it stale (has entries but all old)
        session.add(RefreshLog(
            race_id=None,
            refresh_type="pipeline_daily",
            refreshed_at=datetime.utcnow() - timedelta(hours=50),
            status="success",
            entry_count=5,
        ))
        session.commit()
        session.close()

        resp = client.get("/health")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "stale"

    def test_health_200_when_not_stale(self, client, tmp_db):
        """Recent activity → 200."""
        session = get_session(tmp_db)
        session.add(RefreshLog(
            race_id=None,
            refresh_type="pipeline_daily",
            refreshed_at=datetime.utcnow(),
            status="success",
            entry_count=5,
        ))
        session.commit()
        session.close()

        resp = client.get("/health")
        assert resp.status_code == 200
