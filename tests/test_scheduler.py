"""Tests for scheduler module (Sprint 023)."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from raceanalyzer.config import Settings
from raceanalyzer.db.models import Base, RefreshLog
from raceanalyzer.scheduler import RefreshScheduler


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database."""
    from raceanalyzer.db.engine import init_db

    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def settings(tmp_db):
    return Settings(db_path=tmp_db)


@pytest.fixture
def scheduler(tmp_db, settings):
    return RefreshScheduler(tmp_db, settings)


def _add_refresh_log(db_path, refresh_type, status="success", hours_ago=0, race_id=None):
    """Helper to insert a RefreshLog entry."""
    from raceanalyzer.db.engine import get_session

    session = get_session(db_path)
    entry = RefreshLog(
        race_id=race_id,
        refresh_type=refresh_type,
        refreshed_at=datetime.utcnow() - timedelta(hours=hours_ago),
        status=status,
        entry_count=10,
    )
    session.add(entry)
    session.commit()
    session.close()


class TestOverdueDetection:
    def test_first_run_daily_overdue(self, scheduler):
        """Empty RefreshLog → daily is overdue."""
        assert scheduler.is_daily_overdue() is True

    def test_first_run_weekly_overdue(self, scheduler):
        """Empty RefreshLog → weekly is overdue."""
        assert scheduler.is_weekly_overdue() is True

    def test_recent_daily_not_overdue(self, scheduler, tmp_db):
        """Recent scheduler_daily → not overdue."""
        _add_refresh_log(tmp_db, "scheduler_daily", hours_ago=1)
        assert scheduler.is_daily_overdue() is False

    def test_stale_daily_is_overdue(self, scheduler, tmp_db):
        """Scheduler_daily older than 24h → overdue."""
        _add_refresh_log(tmp_db, "scheduler_daily", hours_ago=25)
        assert scheduler.is_daily_overdue() is True

    def test_recent_weekly_not_overdue(self, scheduler, tmp_db):
        """Recent scheduler_weekly → not overdue."""
        _add_refresh_log(tmp_db, "scheduler_weekly", hours_ago=1)
        assert scheduler.is_weekly_overdue() is False

    def test_stale_weekly_is_overdue(self, scheduler, tmp_db):
        """Scheduler_weekly older than 7d → overdue."""
        _add_refresh_log(tmp_db, "scheduler_weekly", hours_ago=170)
        assert scheduler.is_weekly_overdue() is True

    def test_manual_startlist_satisfies_daily_sla(self, scheduler, tmp_db):
        """Manual fetch-startlists run satisfies daily SLA."""
        _add_refresh_log(tmp_db, "startlist", hours_ago=2, race_id=1)
        assert scheduler.is_daily_overdue() is False

    def test_weekly_run_satisfies_daily_sla(self, scheduler, tmp_db):
        """A recent weekly run also satisfies the daily SLA."""
        _add_refresh_log(tmp_db, "scheduler_weekly", hours_ago=5)
        assert scheduler.is_daily_overdue() is False

    def test_first_run_bootstrap_runs_weekly(self, scheduler, tmp_db):
        """On first run (empty RefreshLog), both daily and weekly are overdue.
        The scheduler should run weekly (superset)."""
        assert scheduler.is_weekly_overdue() is True
        assert scheduler.is_daily_overdue() is True


class TestThreadingLock:
    def test_lock_prevents_concurrent_runs(self, scheduler):
        """Threading lock prevents concurrent check_and_run_overdue calls."""
        # Acquire the lock manually
        scheduler._thread_lock.acquire()
        try:
            result = scheduler.check_and_run_overdue()
            assert result is None  # Should skip due to lock
        finally:
            scheduler._thread_lock.release()


class TestExponentialBackoff:
    def test_no_backoff_initially(self, scheduler):
        assert scheduler._backoff_seconds() == 0

    def test_backoff_after_failure(self, scheduler):
        scheduler._consecutive_failures = 1
        backoff = scheduler._backoff_seconds()
        expected = scheduler.settings.scheduler_check_interval_hours * 3600 * 2
        assert backoff == expected

    def test_backoff_capped_at_48h(self, scheduler):
        scheduler._consecutive_failures = 100
        backoff = scheduler._backoff_seconds()
        assert backoff == 48 * 3600


class TestCheckAndRunOverdue:
    @patch("raceanalyzer.scheduler.run_weekly_pipeline")
    def test_runs_weekly_when_both_overdue(self, mock_weekly, scheduler, tmp_db):
        """When both daily and weekly are overdue, runs weekly (superset)."""
        from raceanalyzer.pipeline import PipelineResult

        mock_weekly.return_value = PipelineResult(
            steps_total=5, steps_succeeded=5, steps_failed=0
        )
        result = scheduler.check_and_run_overdue()
        assert mock_weekly.called
        assert result is not None
        assert result.ok

    @patch("raceanalyzer.scheduler.run_daily_pipeline")
    def test_runs_daily_when_only_daily_overdue(self, mock_daily, scheduler, tmp_db):
        """When only daily is overdue, runs daily."""
        from raceanalyzer.pipeline import PipelineResult

        # Weekly at 25h ago: within 7d (weekly not overdue) but >24h (daily overdue)
        _add_refresh_log(tmp_db, "scheduler_weekly", hours_ago=25)
        mock_daily.return_value = PipelineResult(
            steps_total=2, steps_succeeded=2, steps_failed=0
        )
        result = scheduler.check_and_run_overdue()
        assert result is not None
        assert mock_daily.called

    @patch("raceanalyzer.scheduler.run_weekly_pipeline")
    @patch("raceanalyzer.scheduler.run_daily_pipeline")
    def test_skips_when_nothing_overdue(self, mock_daily, mock_weekly, scheduler, tmp_db):
        """When nothing is overdue, skip."""
        _add_refresh_log(tmp_db, "scheduler_weekly", hours_ago=5)
        _add_refresh_log(tmp_db, "scheduler_daily", hours_ago=5)
        result = scheduler.check_and_run_overdue()
        assert result is None
        assert not mock_daily.called
        assert not mock_weekly.called

    @patch("raceanalyzer.scheduler.run_weekly_pipeline")
    def test_failure_increments_counter(self, mock_weekly, scheduler, tmp_db):
        from raceanalyzer.pipeline import PipelineResult

        mock_weekly.return_value = PipelineResult(
            steps_total=5, steps_succeeded=3, steps_failed=2,
            failed_step_names=["a", "b"],
        )
        scheduler.check_and_run_overdue()
        assert scheduler._consecutive_failures == 1

    @patch("raceanalyzer.scheduler.run_weekly_pipeline")
    def test_success_resets_failure_counter(self, mock_weekly, scheduler, tmp_db):
        from raceanalyzer.pipeline import PipelineResult

        # Set failures but patch backoff to 0 so the run proceeds
        scheduler._consecutive_failures = 3
        with patch.object(scheduler, "_backoff_seconds", return_value=0):
            mock_weekly.return_value = PipelineResult(
                steps_total=5, steps_succeeded=5, steps_failed=0
            )
            scheduler.check_and_run_overdue()
        assert scheduler._consecutive_failures == 0


class TestSchedulerStatus:
    def test_get_status(self, scheduler):
        status = scheduler.get_status()
        assert status["enabled"] is True
        assert status["running"] is False
        assert "daily_overdue" in status
        assert "weekly_overdue" in status

    def test_get_refresh_status(self, scheduler, tmp_db):
        _add_refresh_log(tmp_db, "calendar", hours_ago=1)
        info = scheduler.get_refresh_status()
        assert "calendar" in info
        assert info["calendar"]["last_success"] is not None
        assert info["calendar"]["last_failure"] is None

    def test_get_refresh_status_empty(self, scheduler):
        info = scheduler.get_refresh_status()
        assert info["calendar"]["last_success"] is None
        assert info["calendar"]["last_failure"] is None
        assert info["calendar"]["records_processed"] is None


class TestStaleness:
    def test_not_stale_on_first_run(self, scheduler):
        """No RefreshLog entries → not stale (first run)."""
        assert scheduler.is_stale() is False

    def test_not_stale_with_recent_activity(self, scheduler, tmp_db):
        _add_refresh_log(tmp_db, "scheduler_daily", hours_ago=5)
        assert scheduler.is_stale() is False

    def test_stale_with_old_activity(self, scheduler, tmp_db):
        _add_refresh_log(tmp_db, "scheduler_daily", hours_ago=50)
        assert scheduler.is_stale() is True
