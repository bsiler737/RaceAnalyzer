"""Automated refresh scheduler for RaceAnalyzer (Sprint 023).

Runs overdue pipeline jobs in background threads on FastAPI startup and
periodically while the server is awake.  Uses filesystem + threading locks
to prevent concurrent runs.
"""

from __future__ import annotations

import asyncio
import fcntl
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from raceanalyzer.config import Settings
from raceanalyzer.db.engine import get_session
from raceanalyzer.db.models import RefreshLog
from raceanalyzer.pipeline import PipelineResult, run_daily_pipeline, run_weekly_pipeline

logger = logging.getLogger("raceanalyzer")


class RefreshScheduler:
    """Detects overdue refresh jobs and runs them in background threads."""

    def __init__(self, db_path: Path, settings: Settings) -> None:
        self.db_path = db_path
        self.settings = settings
        self._thread_lock = threading.Lock()
        self._running = False
        self._shutting_down = False
        self._current_thread: Optional[threading.Thread] = None
        self._consecutive_failures = 0

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Overdue detection
    # ------------------------------------------------------------------

    def _last_success_for_type(self, session: Session, refresh_type: str) -> Optional[datetime]:
        """Return the most recent successful refresh timestamp for *refresh_type*."""
        row = (
            session.query(func.max(RefreshLog.refreshed_at))
            .filter(
                RefreshLog.refresh_type == refresh_type,
                RefreshLog.status.in_(("success", "running")),
                RefreshLog.race_id.is_(None),
            )
            .scalar()
        )
        return row

    def _last_success_for_step(self, session: Session, step_type: str) -> Optional[datetime]:
        """Check underlying step rows (e.g. 'startlist') — manual runs satisfy SLA."""
        row = (
            session.query(func.max(RefreshLog.refreshed_at))
            .filter(
                RefreshLog.refresh_type == step_type,
                RefreshLog.status == "success",
            )
            .scalar()
        )
        return row

    def is_daily_overdue(self, session: Optional[Session] = None) -> bool:
        """True if a daily refresh is overdue (>daily_interval since last)."""
        own_session = session is None
        if own_session:
            session = get_session(self.db_path)
        try:
            cutoff = datetime.utcnow() - timedelta(hours=self.settings.refresh_daily_interval_hours)

            # Check scheduler-level daily runs
            last_scheduler = self._last_success_for_type(session, "pipeline_daily")
            if last_scheduler and last_scheduler > cutoff:
                return False

            # A weekly run also covers the daily SLA
            last_weekly = self._last_success_for_type(session, "pipeline_weekly")
            if last_weekly and last_weekly > cutoff:
                return False

            # Manual startlist fetch also satisfies daily SLA
            last_startlist = self._last_success_for_step(session, "startlist")
            if last_startlist and last_startlist > cutoff:
                return False

            return True
        finally:
            if own_session:
                session.close()

    def is_weekly_overdue(self, session: Optional[Session] = None) -> bool:
        """True if a weekly refresh is overdue (>weekly_interval since last)."""
        own_session = session is None
        if own_session:
            session = get_session(self.db_path)
        try:
            cutoff = datetime.utcnow() - timedelta(hours=self.settings.refresh_weekly_interval_hours)

            last_weekly = self._last_success_for_type(session, "pipeline_weekly")
            if last_weekly and last_weekly > cutoff:
                return False

            return True
        finally:
            if own_session:
                session.close()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _backoff_seconds(self) -> float:
        """Exponential backoff based on consecutive failure count."""
        if self._consecutive_failures == 0:
            return 0
        base = self.settings.scheduler_check_interval_hours * 3600
        delay = base * (2 ** self._consecutive_failures)
        max_delay = 48 * 3600  # 48 hours
        return min(delay, max_delay)

    def check_and_run_overdue(self) -> Optional[PipelineResult]:
        """Check for overdue jobs and run them if the lock is available.

        Returns the PipelineResult if a job ran, or None if nothing was needed
        or the lock was unavailable.
        """
        if self._shutting_down:
            logger.info("[scheduler] Shutting down, skipping check.")
            return None

        if not self._thread_lock.acquire(blocking=False):
            logger.info("[scheduler] Another job is already running, skipping.")
            return None

        try:
            self._running = True

            # Backoff check
            backoff = self._backoff_seconds()
            if backoff > 0:
                logger.info(
                    "[scheduler] Backoff active (%d consecutive failures), "
                    "delaying %.0f seconds.",
                    self._consecutive_failures, backoff,
                )
                return None

            session = get_session(self.db_path)
            try:
                weekly_overdue = self.is_weekly_overdue(session)
                daily_overdue = self.is_daily_overdue(session)
            finally:
                session.close()

            if not weekly_overdue and not daily_overdue:
                logger.info("[scheduler] No overdue jobs.")
                return None

            # Acquire filesystem lock
            lock_path = self.db_path.parent / "refresh.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_fd = None
            try:
                lock_fd = open(lock_path, "w")
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                logger.info("[scheduler] Filesystem lock held, skipping.")
                if lock_fd:
                    lock_fd.close()
                return None

            try:
                if weekly_overdue:
                    logger.info("[scheduler] Weekly refresh overdue, running weekly pipeline...")
                    result = run_weekly_pipeline(self.db_path)
                else:
                    logger.info("[scheduler] Daily refresh overdue, running daily pipeline...")
                    result = run_daily_pipeline(self.db_path)

                if result.ok:
                    self._consecutive_failures = 0
                else:
                    self._consecutive_failures += 1
                    logger.warning(
                        "[scheduler] Pipeline had failures (%d consecutive).",
                        self._consecutive_failures,
                    )

                return result
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()

        finally:
            self._running = False
            self._thread_lock.release()

    async def check_and_run_overdue_async(self) -> Optional[PipelineResult]:
        """Run check_and_run_overdue in a thread pool (non-blocking)."""
        return await asyncio.to_thread(self.check_and_run_overdue)

    def shutdown(self, timeout: float = 30.0) -> None:
        """Signal graceful shutdown and wait for in-flight job."""
        self._shutting_down = True
        if self._current_thread and self._current_thread.is_alive():
            logger.info("[scheduler] Waiting up to %.0fs for in-flight job...", timeout)
            self._current_thread.join(timeout=timeout)
            if self._current_thread.is_alive():
                logger.warning("[scheduler] In-flight job did not finish within timeout.")

    # ------------------------------------------------------------------
    # Status for /health
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """Return scheduler status dict for the /health endpoint."""
        session = get_session(self.db_path)
        try:
            daily_overdue = self.is_daily_overdue(session)
            weekly_overdue = self.is_weekly_overdue(session)
        finally:
            session.close()

        next_check = self.settings.scheduler_check_interval_hours * 3600
        backoff = self._backoff_seconds()
        if backoff > 0:
            next_check = max(next_check, backoff)

        return {
            "enabled": self.settings.scheduler_enabled,
            "running": self._running,
            "next_check_in_seconds": int(next_check),
            "daily_overdue": daily_overdue,
            "weekly_overdue": weekly_overdue,
        }

    def get_refresh_status(self) -> dict:
        """Return per-step last_refresh info for /health."""
        session = get_session(self.db_path)
        try:
            result = {}
            for step_type in ("calendar", "startlist", "elevation", "course_profile", "predictions"):
                # Map step types to what's actually recorded in RefreshLog
                query_type = step_type
                if step_type in ("elevation", "course_profile", "predictions"):
                    # These don't have per-step RefreshLog entries yet;
                    # use scheduler job-level entries
                    query_type = step_type

                last_success_row = (
                    session.query(RefreshLog)
                    .filter(
                        RefreshLog.refresh_type == query_type,
                        RefreshLog.status == "success",
                    )
                    .order_by(RefreshLog.refreshed_at.desc())
                    .first()
                )

                last_failure_row = (
                    session.query(RefreshLog)
                    .filter(
                        RefreshLog.refresh_type == query_type,
                        RefreshLog.status.in_(("error", "failed")),
                    )
                    .order_by(RefreshLog.refreshed_at.desc())
                    .first()
                )

                result[step_type] = {
                    "last_success": (
                        last_success_row.refreshed_at.isoformat() + "Z"
                        if last_success_row
                        else None
                    ),
                    "last_failure": (
                        last_failure_row.refreshed_at.isoformat() + "Z"
                        if last_failure_row
                        else None
                    ),
                    "records_processed": (
                        last_success_row.entry_count
                        if last_success_row
                        else None
                    ),
                }

            return result
        finally:
            session.close()

    def is_stale(self) -> bool:
        """True if daily refresh is more than 48 hours stale."""
        session = get_session(self.db_path)
        try:
            cutoff = datetime.utcnow() - timedelta(hours=48)

            # Check any recent successful refresh activity
            for rtype in ("pipeline_daily", "pipeline_weekly", "startlist"):
                last = self._last_success_for_type(session, rtype) if rtype.startswith("scheduler") else self._last_success_for_step(session, rtype)
                if last and last > cutoff:
                    return False

            # If no RefreshLog entries at all, not stale (first run)
            any_entry = session.query(RefreshLog).first()
            if any_entry is None:
                return False

            return True
        finally:
            session.close()
