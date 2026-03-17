"""Tests for pipeline functions (Sprint 023)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from raceanalyzer.pipeline import (
    DAILY_STEPS,
    STEP_REGISTRY,
    WEEKLY_STEPS,
    PipelineResult,
    StepResult,
    run_daily_pipeline,
    run_weekly_pipeline,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database for pipeline tests."""
    from raceanalyzer.db.engine import init_db

    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


def _patch_registry(**overrides):
    """Return a patched STEP_REGISTRY dict with given overrides."""
    patched = dict(STEP_REGISTRY)
    patched.update(overrides)
    return patched


def _ok_step(session, settings, *, force=False):
    return 10


def _fail_step(session, settings, *, force=False):
    raise RuntimeError("boom")


class TestPipelineResult:
    def test_ok_when_no_failures(self):
        r = PipelineResult(steps_total=3, steps_succeeded=3, steps_failed=0)
        assert r.ok is True

    def test_not_ok_when_failures(self):
        r = PipelineResult(steps_total=3, steps_succeeded=2, steps_failed=1, failed_step_names=["x"])
        assert r.ok is False


class TestDailyPipeline:
    def test_daily_runs_2_steps(self):
        assert len(DAILY_STEPS) == 2
        assert DAILY_STEPS == ["fetch-startlists", "compute-predictions"]

    def test_daily_pipeline_calls_steps(self, tmp_db):
        registry = _patch_registry(**{
            "fetch-startlists": _ok_step,
            "compute-predictions": _ok_step,
        })
        with patch.dict("raceanalyzer.pipeline.STEP_REGISTRY", registry):
            result = run_daily_pipeline(tmp_db)
        assert result.steps_total == 2
        assert result.steps_succeeded == 2
        assert result.steps_failed == 0
        assert result.ok is True

    def test_failure_does_not_abort_next_step(self, tmp_db):
        """Failure in step N doesn't prevent step N+1 from running."""
        call_log = []

        def _tracking_ok(session, settings, *, force=False):
            call_log.append("predictions")
            return 10

        registry = _patch_registry(**{
            "fetch-startlists": _fail_step,
            "compute-predictions": _tracking_ok,
        })
        with patch.dict("raceanalyzer.pipeline.STEP_REGISTRY", registry):
            result = run_daily_pipeline(tmp_db)

        assert result.steps_failed == 1
        assert result.steps_succeeded == 1
        assert "fetch-startlists" in result.failed_step_names
        assert "predictions" in call_log  # compute-predictions still ran


class TestWeeklyPipeline:
    def test_weekly_runs_all_steps(self):
        assert len(WEEKLY_STEPS) == 5
        assert WEEKLY_STEPS == [
            "fetch-calendar",
            "fetch-startlists",
            "elevation-extract",
            "course-profile-extract",
            "compute-predictions",
        ]

    def test_weekly_pipeline_all_succeed(self, tmp_db):
        registry = {name: _ok_step for name in WEEKLY_STEPS}
        with patch.dict("raceanalyzer.pipeline.STEP_REGISTRY", registry):
            result = run_weekly_pipeline(tmp_db)
        assert result.steps_total == 5
        assert result.steps_succeeded == 5
        assert result.ok is True

    def test_weekly_multiple_failures(self, tmp_db):
        registry = _patch_registry(**{
            "fetch-calendar": _fail_step,
            "fetch-startlists": _ok_step,
            "elevation-extract": _fail_step,
            "course-profile-extract": _ok_step,
            "compute-predictions": _ok_step,
        })
        with patch.dict("raceanalyzer.pipeline.STEP_REGISTRY", registry):
            result = run_weekly_pipeline(tmp_db)
        assert result.steps_failed == 2
        assert result.steps_succeeded == 3
        assert "fetch-calendar" in result.failed_step_names
        assert "elevation-extract" in result.failed_step_names

    def test_pipeline_result_has_step_results(self, tmp_db):
        registry = {name: _ok_step for name in WEEKLY_STEPS}
        with patch.dict("raceanalyzer.pipeline.STEP_REGISTRY", registry):
            result = run_weekly_pipeline(tmp_db)
        assert len(result.step_results) == 5
        for sr in result.step_results:
            assert isinstance(sr, StepResult)
            assert sr.success is True
            assert sr.records_processed == 10


class TestRefreshLogRecording:
    def test_job_log_recorded(self, tmp_db):
        """Pipeline should record RefreshLog entries at start and completion."""
        from raceanalyzer.db.engine import get_session
        from raceanalyzer.db.models import RefreshLog

        registry = {name: _ok_step for name in DAILY_STEPS}
        with patch.dict("raceanalyzer.pipeline.STEP_REGISTRY", registry):
            run_daily_pipeline(tmp_db)

        session = get_session(tmp_db)
        logs = (
            session.query(RefreshLog)
            .filter(RefreshLog.refresh_type == "scheduler_daily")
            .all()
        )
        assert len(logs) == 1
        assert logs[0].status == "success"
        session.close()

    def test_job_log_records_failure(self, tmp_db):
        from raceanalyzer.db.engine import get_session
        from raceanalyzer.db.models import RefreshLog

        registry = _patch_registry(**{
            "fetch-startlists": _fail_step,
            "compute-predictions": _ok_step,
        })
        with patch.dict("raceanalyzer.pipeline.STEP_REGISTRY", registry):
            run_daily_pipeline(tmp_db)

        session = get_session(tmp_db)
        log = (
            session.query(RefreshLog)
            .filter(RefreshLog.refresh_type == "scheduler_daily")
            .first()
        )
        assert log.status == "failed"
        assert "fetch-startlists" in log.error_message
        session.close()
