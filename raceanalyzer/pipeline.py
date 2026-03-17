"""Shared pipeline functions callable from both CLI and scheduler (Sprint 023).

These functions call the underlying Python functions directly — not Click
commands.  Both ``refresh-all`` and ``RefreshScheduler`` share this module.
"""

from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from raceanalyzer.config import Settings
from raceanalyzer.db.engine import get_session, init_db
from raceanalyzer.refresh import record_refresh

logger = logging.getLogger("raceanalyzer")


@dataclass
class StepResult:
    name: str
    success: bool
    records_processed: int = 0
    error_message: Optional[str] = None


@dataclass
class PipelineResult:
    steps_total: int = 0
    steps_succeeded: int = 0
    steps_failed: int = 0
    failed_step_names: list[str] = field(default_factory=list)
    step_results: list[StepResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.steps_failed == 0


def _run_step(
    name: str,
    fn,
    session: Session,
    settings: Settings,
    *,
    force: bool = False,
) -> StepResult:
    """Run a single pipeline step, catching exceptions."""
    logger.info("[pipeline] Starting step: %s", name)
    try:
        count = fn(session, settings, force=force)
        logger.info("[pipeline] Step %s completed: %d records", name, count)
        return StepResult(name=name, success=True, records_processed=count)
    except Exception:
        msg = traceback.format_exc()
        logger.error("[pipeline] Step %s failed:\n%s", name, msg)
        return StepResult(name=name, success=False, error_message=msg)


# ---------------------------------------------------------------------------
# Individual step implementations
# ---------------------------------------------------------------------------

def _step_fetch_calendar(session: Session, settings: Settings, *, force: bool = False) -> int:
    """Discover upcoming races from road-results/GraphQL."""
    from datetime import datetime as dt

    from raceanalyzer.calendar_feed import (
        match_event_to_series,
        search_upcoming_events_rr,
    )
    from raceanalyzer.db.models import Race, RaceSeries

    logger.info("[pipeline] Searching road-results for upcoming PNW events...")
    events = search_upcoming_events_rr(settings)

    if not events:
        logger.info("[pipeline] No upcoming events found.")
        record_refresh(session, race_id=None, refresh_type="calendar", status="empty", entry_count=0)
        session.commit()
        return 0

    logger.info("[pipeline] Found %d upcoming events.", len(events))

    all_series = session.query(RaceSeries).all()
    series_names = [s.normalized_name for s in all_series]
    series_lookup = {s.normalized_name: s for s in all_series}

    matched = 0
    created = 0
    for event in events:
        event_name = event["name"]
        match = match_event_to_series(event_name, series_names)
        series = series_lookup.get(match) if match else None

        event_id = event.get("event_id")
        existing_race = (
            session.query(Race).filter(Race.event_id == event_id).first()
            if event_id
            else None
        )

        if existing_race:
            existing_race.is_upcoming = True
            existing_race.registration_source = "road-results"
            if series:
                existing_race.series_id = series.id
        else:
            race = Race(
                id=event_id or (90000 + created),
                name=event_name,
                date=event.get("date"),
                location=f"{event.get('city', '')}, {event.get('state', '')}".strip(", "),
                state_province=event.get("state", ""),
                registration_url=event.get("registration_url", ""),
                registration_source="road-results",
                is_upcoming=True,
                event_id=event_id,
                series_id=series.id if series else None,
            )
            session.add(race)
            created += 1

        if series:
            matched += 1

    # Cleanup: mark past races as not upcoming
    today = dt.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    past_upcoming = (
        session.query(Race)
        .filter(Race.is_upcoming.is_(True), Race.date < today)
        .all()
    )
    for race in past_upcoming:
        race.is_upcoming = False

    record_refresh(
        session, race_id=None, refresh_type="calendar", status="success",
        entry_count=len(events),
    )
    session.commit()
    logger.info("[pipeline] Calendar: matched %d/%d events, created %d new races.", matched, len(events), created)
    return len(events)


def _step_fetch_startlists(session: Session, settings: Settings, *, force: bool = False) -> int:
    """Fetch registered riders from road-results predictor."""
    import hashlib
    import time
    from datetime import datetime as dt

    from raceanalyzer.db.models import Race, Startlist
    from raceanalyzer.refresh import is_refreshable, should_refresh
    from raceanalyzer.scraper.client import RoadResultsClient
    from raceanalyzer.startlists import fetch_startlist_rr

    today = dt.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    upcoming = (
        session.query(Race)
        .filter(Race.is_upcoming.is_(True), Race.date >= today)
        .all()
    )

    if not upcoming:
        logger.info("[pipeline] No upcoming future-dated races found.")
        return 0

    client = RoadResultsClient(settings)
    total_entries = 0
    total_races = 0

    logger.info("[pipeline] Fetching startlists for %d upcoming races...", len(upcoming))

    for race in upcoming:
        if not force and not should_refresh(session, race.id, "startlist"):
            continue

        riders = fetch_startlist_rr(client, race, session)
        if not riders:
            continue

        try:
            nested = session.begin_nested()

            session.query(Startlist).filter(
                Startlist.race_id == race.id,
                Startlist.source == "road-results",
            ).delete()

            rider_str = "|".join(
                f"{r['name']}:{r.get('carried_points', '')}"
                for r in sorted(riders, key=lambda x: x["name"])
            )
            checksum = hashlib.sha256(rider_str.encode()).hexdigest()

            for rider_data in riders:
                entry = Startlist(
                    race_id=race.id,
                    series_id=race.series_id,
                    rider_name=rider_data["name"],
                    rider_id=rider_data.get("rider_id"),
                    category=rider_data.get("category"),
                    team=rider_data.get("team", ""),
                    source="road-results",
                    scraped_at=dt.utcnow(),
                    checksum=checksum,
                    carried_points=rider_data.get("carried_points"),
                    road_results_racer_id=rider_data.get("racer_id"),
                    event_id=race.event_id,
                )
                session.add(entry)
                total_entries += 1

            nested.commit()
            record_refresh(
                session, race_id=race.id, refresh_type="startlist",
                status="success", entry_count=len(riders), checksum=checksum,
                event_id=race.event_id,
            )
            total_races += 1
            time.sleep(3.0)

        except Exception:
            nested.rollback()
            logger.warning("[pipeline] Failed to persist startlist for %s", race.name, exc_info=True)
            record_refresh(
                session, race_id=race.id, refresh_type="startlist",
                status="error", error_message="persist failed",
                event_id=race.event_id,
            )

    session.commit()
    logger.info("[pipeline] Startlists: %d entries across %d races.", total_entries, total_races)
    return total_entries


def _step_elevation_extract(session: Session, settings: Settings, *, force: bool = False) -> int:
    """Extract elevation data from RWGPS routes."""
    import time
    from datetime import datetime as dt

    from raceanalyzer.db.models import Course, RaceSeries
    from raceanalyzer.elevation import classify_terrain, compute_m_per_km
    from raceanalyzer.rwgps import fetch_route_elevation

    series_list = (
        session.query(RaceSeries)
        .filter(RaceSeries.rwgps_route_id.isnot(None))
        .all()
    )

    extracted = 0
    for series in series_list:
        existing = session.query(Course).filter(Course.series_id == series.id).first()
        if existing and not force:
            continue

        elev_data = fetch_route_elevation(series.rwgps_route_id)
        if elev_data is None:
            continue

        m_km = compute_m_per_km(elev_data["total_gain_m"], elev_data["distance_m"])
        course_type = classify_terrain(m_km, settings)

        if existing:
            existing.rwgps_route_id = series.rwgps_route_id
            existing.distance_m = elev_data["distance_m"]
            existing.total_gain_m = elev_data["total_gain_m"]
            existing.total_loss_m = elev_data["total_loss_m"]
            existing.max_elevation_m = elev_data.get("max_elevation_m")
            existing.min_elevation_m = elev_data.get("min_elevation_m")
            existing.m_per_km = m_km
            existing.course_type = course_type
            existing.extracted_at = dt.utcnow()
        else:
            course = Course(
                series_id=series.id,
                rwgps_route_id=series.rwgps_route_id,
                distance_m=elev_data["distance_m"],
                total_gain_m=elev_data["total_gain_m"],
                total_loss_m=elev_data["total_loss_m"],
                max_elevation_m=elev_data.get("max_elevation_m"),
                min_elevation_m=elev_data.get("min_elevation_m"),
                m_per_km=m_km,
                course_type=course_type,
                extracted_at=dt.utcnow(),
                source="rwgps",
            )
            session.add(course)

        extracted += 1
        time.sleep(settings.min_request_delay)

    session.commit()
    logger.info("[pipeline] Elevation: extracted %d courses.", extracted)
    return extracted


def _step_course_profile_extract(session: Session, settings: Settings, *, force: bool = False) -> int:
    """Extract course profiles and detect climbs from RWGPS track points."""
    import json
    import time
    from datetime import datetime as dt

    import requests as req

    from raceanalyzer.db.models import Course, RaceSeries
    from raceanalyzer.elevation import (
        build_profile,
        classify_terrain,
        detect_climbs,
        extract_track_points,
    )

    series_list = (
        session.query(RaceSeries)
        .filter(RaceSeries.rwgps_route_id.isnot(None))
        .all()
    )

    extracted = 0
    for series in series_list:
        course = session.query(Course).filter(Course.series_id == series.id).first()
        if not course:
            continue
        if course.profile_json and not force:
            continue

        try:
            resp = req.get(
                f"https://ridewithgps.com/routes/{series.rwgps_route_id}.json",
                headers={"User-Agent": "RaceAnalyzer/0.1"},
                timeout=15,
            )
            if not resp.ok:
                continue

            route_json = resp.json()
            track_points = extract_track_points(route_json)
            if not track_points:
                continue

            profile = build_profile(track_points)
            climbs = detect_climbs(profile)

            course.profile_json = json.dumps(profile)
            course.climbs_json = json.dumps(climbs)
            course.extracted_at = dt.utcnow()

            if course.m_per_km is not None:
                new_type = classify_terrain(course.m_per_km, settings, climbs=climbs)
                if course.course_type != new_type:
                    course.course_type = new_type

            extracted += 1

        except Exception:
            logger.warning("[pipeline] Profile extract failed for %s", series.display_name, exc_info=True)

        time.sleep(settings.min_request_delay)

    session.commit()
    logger.info("[pipeline] Profiles: extracted %d.", extracted)
    return extracted


def _step_compute_predictions(session: Session, settings: Settings, *, force: bool = False) -> int:
    """Pre-compute series predictions."""
    from sqlalchemy import inspect, text

    from raceanalyzer.precompute import precompute_all

    # Migration: add prediction_source column if missing
    insp = inspect(session.bind)
    columns = [c["name"] for c in insp.get_columns("series_predictions")]
    if "prediction_source" not in columns:
        session.execute(text("ALTER TABLE series_predictions ADD COLUMN prediction_source VARCHAR"))
        session.commit()

    summary = precompute_all(session)
    count = summary.get("predictions_count", 0)
    logger.info("[pipeline] Predictions: computed %d across %d series.", count, summary.get("series_count", 0))
    return count


# ---------------------------------------------------------------------------
# Pipeline runners
# ---------------------------------------------------------------------------

STEP_REGISTRY: dict[str, object] = {
    "fetch-calendar": _step_fetch_calendar,
    "fetch-startlists": _step_fetch_startlists,
    "elevation-extract": _step_elevation_extract,
    "course-profile-extract": _step_course_profile_extract,
    "compute-predictions": _step_compute_predictions,
}

DAILY_STEPS = ["fetch-startlists", "compute-predictions"]

WEEKLY_STEPS = [
    "fetch-calendar",
    "fetch-startlists",
    "elevation-extract",
    "course-profile-extract",
    "compute-predictions",
]


def _run_pipeline(
    step_names: list[str],
    db_path: Path,
    *,
    force: bool = False,
    refresh_type: Optional[str] = None,
) -> PipelineResult:
    """Execute a sequence of pipeline steps, recording results.

    Each step gets its own session to isolate failures.  A RefreshLog entry
    with *refresh_type* is written at job start (``running``) and updated on
    completion (``success`` / ``failed``).
    """
    settings = Settings(db_path=db_path)
    init_db(db_path)

    # Record job start if refresh_type given
    job_log_id: Optional[int] = None
    if refresh_type:
        session = get_session(db_path)
        entry = record_refresh(session, race_id=None, refresh_type=refresh_type, status="running")
        job_log_id = entry.id
        session.commit()
        session.close()

    result = PipelineResult(steps_total=len(step_names))

    for step_name in step_names:
        step_fn = STEP_REGISTRY[step_name]
        session = get_session(db_path)
        try:
            sr = _run_step(step_name, step_fn, session, settings, force=force)
            result.step_results.append(sr)
            if sr.success:
                result.steps_succeeded += 1
            else:
                result.steps_failed += 1
                result.failed_step_names.append(sr.name)
        finally:
            session.close()

    # Update job log
    if refresh_type and job_log_id is not None:
        session = get_session(db_path)
        from raceanalyzer.db.models import RefreshLog
        entry = session.get(RefreshLog, job_log_id)
        if entry:
            entry.status = "success" if result.ok else "failed"
            entry.entry_count = result.steps_succeeded
            if not result.ok:
                entry.error_message = ", ".join(result.failed_step_names)
            session.commit()
        session.close()

    return result


def run_daily_pipeline(db_path: Path, *, force: bool = False) -> PipelineResult:
    """fetch-startlists → compute-predictions"""
    logger.info("[pipeline] Starting daily pipeline...")
    result = _run_pipeline(DAILY_STEPS, db_path, force=force, refresh_type="pipeline_daily")
    logger.info(
        "[pipeline] Daily pipeline finished: %d/%d succeeded.",
        result.steps_succeeded, result.steps_total,
    )
    return result


def run_weekly_pipeline(db_path: Path, *, force: bool = False) -> PipelineResult:
    """fetch-calendar → fetch-startlists → elevation-extract → course-profile-extract → compute-predictions"""
    logger.info("[pipeline] Starting weekly pipeline...")
    result = _run_pipeline(WEEKLY_STEPS, db_path, force=force, refresh_type="pipeline_weekly")
    logger.info(
        "[pipeline] Weekly pipeline finished: %d/%d succeeded.",
        result.steps_succeeded, result.steps_total,
    )
    return result
