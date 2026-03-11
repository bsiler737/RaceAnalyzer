"""Refresh-limiting logic for calendar and startlist operations (Sprint 009)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from raceanalyzer.db.models import RefreshLog

logger = logging.getLogger("raceanalyzer")


def should_refresh(session: Session, race_id: int, refresh_type: str) -> bool:
    """Return False if this race+type was refreshed in the last 24 hours."""
    cutoff = datetime.utcnow() - timedelta(hours=24)
    recent = (
        session.query(RefreshLog)
        .filter(
            RefreshLog.race_id == race_id,
            RefreshLog.refresh_type == refresh_type,
            RefreshLog.refreshed_at > cutoff,
        )
        .first()
    )
    return recent is None


def is_refreshable(race) -> bool:
    """Return True only if the race has a future date.

    Races with date < today or date=None are never refreshed.
    """
    if race.date is None:
        return False
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return race.date >= today


def record_refresh(
    session: Session,
    race_id: Optional[int],
    refresh_type: str,
    status: str,
    *,
    entry_count: Optional[int] = None,
    checksum: Optional[str] = None,
    error_message: Optional[str] = None,
    event_id: Optional[int] = None,
) -> RefreshLog:
    """Record a refresh attempt in the RefreshLog table."""
    entry = RefreshLog(
        race_id=race_id,
        event_id=event_id,
        refresh_type=refresh_type,
        refreshed_at=datetime.utcnow(),
        status=status,
        entry_count=entry_count,
        checksum=checksum,
        error_message=error_message,
    )
    session.add(entry)
    session.flush()
    return entry
