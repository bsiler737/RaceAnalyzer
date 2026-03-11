"""CLI commands for RaceAnalyzer."""

from __future__ import annotations

import logging
from pathlib import Path

import click

from raceanalyzer.config import Settings

logger = logging.getLogger("raceanalyzer")


@click.group()
@click.option("--db", default="data/raceanalyzer.db", help="Path to SQLite database.")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging.")
@click.pass_context
def main(ctx, db, verbose):
    """RaceAnalyzer: PNW bike race analysis tool."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    ctx.ensure_object(dict)
    ctx.obj["settings"] = Settings(db_path=Path(db))


@main.command()
@click.pass_context
def init(ctx):
    """Initialize the database (create all tables)."""
    settings = ctx.obj["settings"]

    from raceanalyzer.db.engine import init_db

    init_db(settings.db_path)
    click.echo(f"Database initialized at {settings.db_path}")


@main.command()
@click.option("--race-id", type=int, help="Scrape a single race by ID.")
@click.option("--start", type=int, help="Start of race ID range.")
@click.option("--end", type=int, help="End of race ID range.")
@click.option("--no-skip", is_flag=True, help="Re-scrape already-scraped races.")
@click.pass_context
def scrape(ctx, race_id, start, end, no_skip):
    """Scrape race results from road-results.com."""
    settings = ctx.obj["settings"]

    from raceanalyzer.db.engine import get_session, init_db
    from raceanalyzer.scraper.client import RoadResultsClient
    from raceanalyzer.scraper.pipeline import ScrapeOrchestrator

    init_db(settings.db_path)
    session = get_session(settings.db_path)
    client = RoadResultsClient(settings)
    orchestrator = ScrapeOrchestrator(client, session, settings)

    if race_id:
        log_entry = orchestrator.scrape_race(race_id)
        click.echo(f"Race {race_id}: {log_entry.status} ({log_entry.result_count or 0} results)")
    elif start is not None and end is not None:
        results = orchestrator.scrape_range(start, end, skip_existing=not no_skip)
        success = sum(1 for r in results if r.status == "success")
        click.echo(f"Scraped {success}/{len(results)} races successfully.")
    else:
        click.echo("Provide --race-id or --start/--end range.", err=True)
        raise SystemExit(1)

    session.close()


@main.command()
@click.option("--race-id", type=int, help="Classify a single race.")
@click.option("--all", "classify_all", is_flag=True, help="Classify all unclassified races.")
@click.option(
    "--gap-threshold",
    type=float,
    default=3.0,
    help="Gap threshold in seconds (default: 3.0).",
)
@click.pass_context
def classify(ctx, race_id, classify_all, gap_threshold):
    """Classify finish types for scraped races."""
    settings = ctx.obj["settings"]
    settings.gap_threshold = gap_threshold

    from sqlalchemy import distinct

    from raceanalyzer.classification.finish_type import classify_finish_type
    from raceanalyzer.classification.grouping import group_by_consecutive_gaps
    from raceanalyzer.db.engine import get_session
    from raceanalyzer.db.models import Race, RaceClassification, Result

    # Load Race for metadata pass-through to classifier

    session = get_session(settings.db_path)

    if race_id:
        race_ids = [race_id]
    elif classify_all:
        # Find all race IDs that have results but no classifications
        classified = (
            session.query(distinct(RaceClassification.race_id)).all()
        )
        classified_ids = {r[0] for r in classified}
        all_ids = session.query(distinct(Result.race_id)).all()
        race_ids = [r[0] for r in all_ids if r[0] not in classified_ids]
        click.echo(f"Found {len(race_ids)} unclassified races.")
    else:
        click.echo("Provide --race-id or --all.", err=True)
        raise SystemExit(1)

    total_classified = 0

    for rid in race_ids:
        # Load race for metadata
        race_obj = session.get(Race, rid)

        # Get unique categories for this race
        categories = (
            session.query(distinct(Result.race_category_name))
            .filter(Result.race_id == rid)
            .all()
        )

        for (category,) in categories:
            if not category:
                continue

            # Get results for this race + category
            results = (
                session.query(Result)
                .filter(Result.race_id == rid, Result.race_category_name == category)
                .all()
            )

            # Filter to finishers (not DNF/DQ/DNP)
            finishers = [r for r in results if not r.dnf and not r.dq and not r.dnp]
            timed_finishers = [r for r in finishers if r.race_time_seconds is not None]
            total_finishers = len(finishers)

            # Group by time gaps
            groups = group_by_consecutive_gaps(timed_finishers, gap_threshold)

            # Classify (pass race metadata for TT detection)
            classification = classify_finish_type(
                groups, total_finishers, gap_threshold,
                race_type=race_obj.race_type if race_obj else None,
                race_name=race_obj.name if race_obj else "",
            )

            # Check for existing classification
            existing = (
                session.query(RaceClassification)
                .filter(
                    RaceClassification.race_id == rid,
                    RaceClassification.category == category,
                )
                .first()
            )

            if existing:
                existing.finish_type = classification.finish_type
                existing.num_finishers = classification.metrics.get("num_finishers")
                existing.num_groups = classification.metrics.get("num_groups")
                existing.largest_group_size = classification.metrics.get("largest_group_size")
                existing.largest_group_ratio = classification.metrics.get("largest_group_ratio")
                existing.leader_group_size = classification.metrics.get("leader_group_size")
                existing.gap_to_second_group = classification.metrics.get("gap_to_second_group")
                existing.cv_of_times = classification.metrics.get("cv_of_times")
                existing.gap_threshold_used = classification.metrics.get("gap_threshold_used")
            else:
                rc = RaceClassification(
                    race_id=rid,
                    category=category,
                    finish_type=classification.finish_type,
                    num_finishers=classification.metrics.get("num_finishers"),
                    num_groups=classification.metrics.get("num_groups"),
                    largest_group_size=classification.metrics.get("largest_group_size"),
                    largest_group_ratio=classification.metrics.get("largest_group_ratio"),
                    leader_group_size=classification.metrics.get("leader_group_size"),
                    gap_to_second_group=classification.metrics.get("gap_to_second_group"),
                    cv_of_times=classification.metrics.get("cv_of_times"),
                    gap_threshold_used=classification.metrics.get("gap_threshold_used"),
                )
                session.add(rc)

            total_classified += 1

            if race_id:
                click.echo(
                    f"  {category}: {classification.finish_type.value} "
                    f"(confidence: {classification.confidence})"
                )

    session.commit()
    session.close()

    if classify_all:
        click.echo(f"Classified {total_classified} race-category pairs.")


@main.command()
@click.option("--port", type=int, default=8501, help="Port for Streamlit server.")
@click.pass_context
def ui(ctx, port):
    """Launch the Streamlit UI."""
    import os
    import subprocess
    import sys

    app_path = Path(__file__).parent / "ui" / "app.py"
    settings = ctx.obj["settings"]

    env = os.environ.copy()
    env["RACEANALYZER_DB_PATH"] = str(settings.db_path)

    cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(app_path),
        "--server.port", str(port),
        "--server.headless", "false",
    ]
    click.echo(f"Launching RaceAnalyzer UI on port {port}...")
    subprocess.run(cmd, env=env, check=True)


@main.command("seed-demo")
@click.option("--num-races", type=int, default=50, help="Number of races to generate.")
@click.option("--seed", type=int, default=42, help="Random seed for reproducibility.")
@click.pass_context
def seed_demo(ctx, num_races, seed):
    """Populate the database with synthetic demo data."""
    settings = ctx.obj["settings"]

    from raceanalyzer.db.engine import get_session, init_db
    from raceanalyzer.demo import generate_demo_data

    init_db(settings.db_path)
    session = get_session(settings.db_path)

    click.echo(f"Seeding {num_races} demo races (seed={seed})...")
    summary = generate_demo_data(session, num_races=num_races, seed=seed)

    click.echo(
        f"Created {summary['races']} races, {summary['riders']} riders, "
        f"{summary['results']} results, {summary['classifications']} classifications."
    )
    session.close()


@main.command("ingest-raw")
@click.pass_context
def ingest_raw(ctx):
    """Re-ingest results from archived raw HTML+JSON files in data/raw/.

    Useful when the database was reset after scraping. Reads each pair of
    {id}.html and {id}.json, parses them with the standard parsers, and
    persists to the database exactly as a live scrape would.
    """
    import json
    from datetime import datetime

    from raceanalyzer.db.engine import get_session, init_db
    from raceanalyzer.db.models import ScrapeLog
    from raceanalyzer.scraper.errors import ExpectedParsingError, UnexpectedParsingError
    from raceanalyzer.scraper.parsers import RacePageParser, RaceResultParser
    from raceanalyzer.scraper.pipeline import ScrapeOrchestrator

    settings = ctx.obj["settings"]
    init_db(settings.db_path)
    session = get_session(settings.db_path)

    raw_dir = Path(settings.raw_data_dir)
    if not raw_dir.exists():
        click.echo(f"No raw data directory found at {raw_dir}", err=True)
        raise SystemExit(1)

    # Find all JSON files (each corresponds to a race)
    json_files = sorted(raw_dir.glob("*.json"), key=lambda p: int(p.stem))
    if not json_files:
        click.echo("No raw JSON files found.", err=True)
        raise SystemExit(1)

    # Skip already-ingested race IDs
    existing_ids = {
        row[0]
        for row in session.query(ScrapeLog.race_id)
        .filter(ScrapeLog.status.in_(["success", "ingest"]))
        .all()
    }

    # Build a lightweight orchestrator just for _persist_race
    from raceanalyzer.scraper.client import RoadResultsClient

    client = RoadResultsClient(settings)
    orchestrator = ScrapeOrchestrator(client, session, settings)

    success = 0
    skipped = 0
    errors = 0

    click.echo(f"Found {len(json_files)} raw files, {len(existing_ids)} already ingested.")

    for json_path in json_files:
        race_id = int(json_path.stem)
        html_path = raw_dir / f"{race_id}.html"

        if race_id in existing_ids:
            skipped += 1
            continue

        if not html_path.exists():
            logger.warning("Missing HTML for race %d, skipping.", race_id)
            errors += 1
            continue

        try:
            html = html_path.read_text(encoding="utf-8")
            raw_json = json.loads(json_path.read_text(encoding="utf-8"))

            page_parser = RacePageParser(race_id, html)
            metadata = page_parser.parse()

            result_parser = RaceResultParser(race_id, raw_json)
            results = result_parser.results()

            orchestrator._persist_race(metadata, results)

            session.add(ScrapeLog(
                race_id=race_id,
                status="ingest",
                scraped_at=datetime.utcnow(),
                result_count=len(results),
            ))
            session.commit()
            success += 1

        except (ExpectedParsingError, UnexpectedParsingError) as e:
            session.rollback()
            session.add(ScrapeLog(
                race_id=race_id,
                status="error",
                scraped_at=datetime.utcnow(),
                error_message=str(e),
            ))
            session.commit()
            errors += 1
            logger.debug("Parse error for race %d: %s", race_id, e)

        except Exception as e:
            session.rollback()
            errors += 1
            logger.warning("Error ingesting race %d: %s", race_id, e)

        if (success + errors) % 100 == 0 and (success + errors) > 0:
            click.echo(f"  Progress: {success} ingested, {errors} errors, {skipped} skipped...")

    click.echo(
        f"Done. Ingested {success} races, {errors} errors, {skipped} skipped."
    )
    session.close()


@main.command("clear-demo")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def clear_demo(ctx, yes):
    """Remove all synthetic demo data from the database."""
    settings = ctx.obj["settings"]

    from raceanalyzer.db.engine import get_session
    from raceanalyzer.demo import clear_demo_data

    if not yes:
        click.confirm("This will delete all demo data. Continue?", abort=True)

    session = get_session(settings.db_path)
    summary = clear_demo_data(session)

    click.echo(f"Removed {summary['races']} demo races and {summary['riders']} demo riders.")
    session.close()


@main.command("build-series")
@click.pass_context
def build_series_cmd(ctx):
    """Group races into series by normalized name."""
    settings = ctx.obj["settings"]

    from raceanalyzer.db.engine import get_session, init_db
    from raceanalyzer.series import build_series

    init_db(settings.db_path)
    session = get_session(settings.db_path)

    click.echo("Building race series from normalized names...")
    summary = build_series(session)
    click.echo(
        f"Created {summary['series_created']} series, "
        f"linked {summary['races_linked']} races."
    )
    session.close()


@main.command("match-routes")
@click.option("--dry-run", is_flag=True, help="Show matches without saving.")
@click.option("--min-score", type=float, default=0.25, help="Minimum match score.")
@click.pass_context
def match_routes(ctx, dry_run, min_score):
    """Match race series to RideWithGPS routes."""
    import time

    settings = ctx.obj["settings"]

    from raceanalyzer.db.engine import get_session, init_db
    from raceanalyzer.db.models import RaceSeries
    from raceanalyzer.rwgps import fetch_route_polyline, match_race_to_route
    from raceanalyzer.ui.maps import geocode_location

    init_db(settings.db_path)
    session = get_session(settings.db_path)

    # Find series without routes (and not manually overridden)
    series_list = (
        session.query(RaceSeries)
        .filter(
            RaceSeries.rwgps_route_id.is_(None),
            RaceSeries.rwgps_manual_override.is_(False),
        )
        .all()
    )
    click.echo(f"Found {len(series_list)} series without routes.")

    matched = 0
    for series in series_list:
        # Get location from most recent race in this series
        from raceanalyzer.db.models import Race

        most_recent = (
            session.query(Race)
            .filter(Race.series_id == series.id)
            .order_by(Race.date.desc())
            .first()
        )
        if not most_recent:
            continue

        # Geocode for coordinates
        lat, lon = None, None
        if most_recent.location:
            coords = geocode_location(
                most_recent.location, most_recent.state_province or ""
            )
            if coords:
                lat, lon = coords

        race_type = most_recent.race_type.value if most_recent.race_type else None

        # Search RWGPS
        result = match_race_to_route(
            series.display_name, lat=lat, lon=lon, race_type=race_type
        )

        if result and result["score"] >= min_score:
            click.echo(
                f"  {series.display_name} -> {result['name']} "
                f"(score: {result['score']:.2f}, id: {result['route_id']})"
            )
            if not dry_run:
                series.rwgps_route_id = result["route_id"]
                # Fetch polyline
                polyline = fetch_route_polyline(result["route_id"])
                if polyline:
                    series.rwgps_encoded_polyline = polyline
                    click.echo(f"    Cached polyline ({len(polyline)} chars)")
                matched += 1
                if not dry_run:
                    session.commit()
        else:
            click.echo(f"  {series.display_name} -> no match")

        # Rate limit: 1 req/sec to RWGPS
        time.sleep(1.0)

    session.close()

    click.echo(f"Matched {matched}/{len(series_list)} series.")


@main.command("elevation-extract")
@click.option("--force", is_flag=True, help="Re-extract even if course data exists.")
@click.pass_context
def elevation_extract(ctx, force):
    """Extract elevation data from RWGPS routes and populate courses table."""
    import time
    from datetime import datetime

    settings = ctx.obj["settings"]

    from raceanalyzer.db.engine import get_session, init_db
    from raceanalyzer.db.models import Course, RaceSeries
    from raceanalyzer.elevation import classify_terrain, compute_m_per_km
    from raceanalyzer.rwgps import fetch_route_elevation

    init_db(settings.db_path)
    session = get_session(settings.db_path)

    # Find series with RWGPS route IDs
    series_list = (
        session.query(RaceSeries)
        .filter(RaceSeries.rwgps_route_id.isnot(None))
        .all()
    )
    click.echo(f"Found {len(series_list)} series with RWGPS routes.")

    extracted = 0
    skipped = 0
    for series in series_list:
        # Check existing course
        existing = (
            session.query(Course)
            .filter(Course.series_id == series.id)
            .first()
        )
        if existing and not force:
            skipped += 1
            continue

        click.echo(f"  Extracting: {series.display_name} (route {series.rwgps_route_id})...")
        elev_data = fetch_route_elevation(series.rwgps_route_id)

        if elev_data is None:
            click.echo("    No elevation data available.")
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
            existing.extracted_at = datetime.utcnow()
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
                extracted_at=datetime.utcnow(),
                source="rwgps",
            )
            session.add(course)

        extracted += 1
        click.echo(
            f"    {course_type.value}: {elev_data['total_gain_m']:.0f}m gain, "
            f"{elev_data['distance_m']/1000:.1f}km"
        )

        # Rate limit
        time.sleep(settings.min_request_delay)

    session.commit()
    session.close()
    click.echo(f"Extracted {extracted} courses ({skipped} skipped).")


@main.command("course-profile-extract")
@click.option("--force", is_flag=True, help="Re-extract even if profile data exists.")
@click.pass_context
def course_profile_extract(ctx, force):
    """Extract course profiles and detect climbs from RWGPS route track points."""
    import json
    import time
    from datetime import datetime

    settings = ctx.obj["settings"]

    from raceanalyzer.db.engine import get_session, init_db
    from raceanalyzer.db.models import Course, RaceSeries
    from raceanalyzer.elevation import build_profile, detect_climbs, extract_track_points

    init_db(settings.db_path)
    session = get_session(settings.db_path)

    # Find series with RWGPS route IDs and existing Course rows
    series_list = (
        session.query(RaceSeries)
        .filter(RaceSeries.rwgps_route_id.isnot(None))
        .all()
    )
    click.echo(f"Found {len(series_list)} series with RWGPS routes.")

    extracted = 0
    skipped = 0
    for series in series_list:
        course = (
            session.query(Course)
            .filter(Course.series_id == series.id)
            .first()
        )
        if not course:
            click.echo(
                f"  Skipping {series.display_name}: no Course row yet"
                " (run elevation-extract first)."
            )
            continue

        if course.profile_json and not force:
            skipped += 1
            continue

        click.echo(
            f"  Extracting profile: {series.display_name}"
            f" (route {series.rwgps_route_id})..."
        )

        try:
            import requests as req

            resp = req.get(
                f"https://ridewithgps.com/routes/{series.rwgps_route_id}.json",
                headers={"User-Agent": "RaceAnalyzer/0.1"},
                timeout=15,
            )
            if not resp.ok:
                click.echo(f"    HTTP {resp.status_code}, skipping.")
                continue

            route_json = resp.json()
            track_points = extract_track_points(route_json)

            if not track_points:
                click.echo("    No track points with elevation, skipping.")
                continue

            profile = build_profile(track_points)
            climbs = detect_climbs(profile)

            course.profile_json = json.dumps(profile)
            course.climbs_json = json.dumps(climbs)
            course.extracted_at = datetime.utcnow()
            extracted += 1

            click.echo(
                f"    {len(profile)} profile points, {len(climbs)} climbs detected"
            )

        except Exception as exc:
            click.echo(f"    Error: {exc}")

        time.sleep(settings.min_request_delay)

    session.commit()
    session.close()
    click.echo(f"Extracted {extracted} profiles ({skipped} skipped).")


@main.command("override-route")
@click.argument("series_id", type=int)
@click.argument("rwgps_route_id", type=int)
@click.pass_context
def override_route(ctx, series_id, rwgps_route_id):
    """Manually set RWGPS route for a race series."""
    settings = ctx.obj["settings"]

    from raceanalyzer.db.engine import get_session, init_db
    from raceanalyzer.db.models import RaceSeries
    from raceanalyzer.rwgps import fetch_route_polyline

    init_db(settings.db_path)
    session = get_session(settings.db_path)

    series = session.get(RaceSeries, series_id)
    if not series:
        click.echo(f"Series {series_id} not found.", err=True)
        raise SystemExit(1)

    series.rwgps_route_id = rwgps_route_id
    series.rwgps_manual_override = True

    polyline = fetch_route_polyline(rwgps_route_id)
    if polyline:
        series.rwgps_encoded_polyline = polyline
        click.echo(f"Set route {rwgps_route_id} for '{series.display_name}' with polyline.")
    else:
        click.echo(f"Set route {rwgps_route_id} for '{series.display_name}' (no polyline fetched).")

    session.commit()
    session.close()


@main.command("fetch-calendar")
@click.option("--region", default="WA", help="State/region code (default: WA).")
@click.option("--days-ahead", type=int, default=60, help="Days to look ahead (default: 60).")
@click.option(
    "--source",
    type=click.Choice(["road-results", "bikereg"]),
    default="road-results",
    help="Data source (default: road-results).",
)
@click.pass_context
def fetch_calendar(ctx, region, days_ahead, source):
    """Discover upcoming races and match to existing series."""
    from datetime import datetime as dt

    settings = ctx.obj["settings"]

    from raceanalyzer.calendar_feed import (
        match_event_to_series,
        search_upcoming_events,
        search_upcoming_events_rr,
    )
    from raceanalyzer.db.engine import get_session, init_db
    from raceanalyzer.db.models import Race, RaceSeries
    from raceanalyzer.refresh import record_refresh

    init_db(settings.db_path)
    session = get_session(settings.db_path)

    if source == "bikereg":
        click.echo(f"Searching BikeReg for events in {region} ({days_ahead} days ahead)...")
        events = search_upcoming_events(region, days_ahead, delay=settings.bikereg_request_delay)
    else:
        click.echo("Searching road-results/GraphQL for upcoming PNW events...")
        events = search_upcoming_events_rr(settings)

    if not events:
        click.echo("No upcoming events found.")
        session.close()
        return

    click.echo(f"Found {len(events)} upcoming events.")

    # Get existing series names for matching
    all_series = session.query(RaceSeries).all()
    series_names = [s.normalized_name for s in all_series]
    series_lookup = {s.normalized_name: s for s in all_series}

    matched = 0
    created = 0
    for event in events:
        event_name = event["name"]
        match = match_event_to_series(event_name, series_names)
        series = series_lookup.get(match) if match else None

        if source == "road-results":
            # Create or update Race row
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
            click.echo(f"  {event_name} -> matched series \"{series.display_name}\"")
            matched += 1
        else:
            click.echo(f"  {event_name} -> no match")

    # Cleanup: mark past races as not upcoming
    today = dt.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    past_upcoming = (
        session.query(Race)
        .filter(Race.is_upcoming.is_(True), Race.date < today)
        .all()
    )
    for race in past_upcoming:
        race.is_upcoming = False
    if past_upcoming:
        click.echo(f"Marked {len(past_upcoming)} past races as no longer upcoming.")

    if source == "road-results":
        record_refresh(
            session, race_id=None, refresh_type="calendar", status="success",
            entry_count=len(events),
        )

    session.commit()
    session.close()
    click.echo(f"Matched {matched}/{len(events)} events to existing series.")


@main.command("fetch-startlists")
@click.option("--region", default="WA", help="State/region code (default: WA).")
@click.option(
    "--source",
    type=click.Choice(["road-results", "bikereg"]),
    default="road-results",
    help="Data source (default: road-results).",
)
@click.option("--dry-run", is_flag=True, help="Preview which races would be refreshed.")
@click.pass_context
def fetch_startlists(ctx, region, source, dry_run):
    """Fetch registered riders for upcoming races."""
    import hashlib
    from datetime import datetime as dt

    settings = ctx.obj["settings"]

    from raceanalyzer.db.engine import get_session, init_db
    from raceanalyzer.db.models import Race, Startlist
    from raceanalyzer.refresh import is_refreshable, record_refresh, should_refresh
    from raceanalyzer.startlists import fetch_startlist

    init_db(settings.db_path)
    session = get_session(settings.db_path)

    if source == "bikereg":
        # Legacy BikeReg path
        upcoming = (
            session.query(Race)
            .filter(
                Race.is_upcoming.is_(True),
                Race.registration_url.isnot(None),
            )
            .all()
        )

        if not upcoming:
            click.echo("No upcoming races with registration URLs found.")
            session.close()
            return

        click.echo(f"Fetching startlists for {len(upcoming)} upcoming races...")
        total_entries = 0

        for race in upcoming:
            riders = fetch_startlist(
                race.registration_url,
                "",
                delay=settings.bikereg_request_delay,
            )
            if riders:
                for rider_data in riders:
                    entry = Startlist(
                        race_id=race.id,
                        series_id=race.series_id,
                        rider_name=rider_data["name"],
                        team=rider_data.get("team", ""),
                        source="bikereg",
                        source_url=race.registration_url,
                        scraped_at=dt.utcnow(),
                    )
                    session.add(entry)
                    total_entries += 1
                click.echo(f"  {race.name}: {len(riders)} riders")

        session.commit()
        session.close()
        click.echo(f"Scraped {total_entries} startlist entries across {len(upcoming)} events.")
        return

    # Road-results predictor path
    from raceanalyzer.scraper.client import RoadResultsClient
    from raceanalyzer.startlists import fetch_startlist_rr

    today = dt.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    upcoming = (
        session.query(Race)
        .filter(
            Race.is_upcoming.is_(True),
            Race.date >= today,
        )
        .all()
    )

    if not upcoming:
        click.echo("No upcoming future-dated races found.")
        session.close()
        return

    if dry_run:
        click.echo(f"Dry run: {len(upcoming)} races would be refreshed:")
        for race in upcoming:
            refreshable = is_refreshable(race)
            fresh = not should_refresh(session, race.id, "startlist")
            status = "skip (recently refreshed)" if fresh else ("ready" if refreshable else "skip")
            date_str = race.date.strftime('%Y-%m-%d') if race.date else '?'
            click.echo(f"  {race.name} ({date_str}): {status}")
        session.close()
        return

    client = RoadResultsClient(settings)
    total_entries = 0
    total_races = 0

    click.echo(f"Fetching predictor startlists for {len(upcoming)} upcoming races...")

    for race in upcoming:
        riders = fetch_startlist_rr(client, race, session)

        if not riders:
            click.echo(f"  {race.name}: skipped or empty")
            continue

        # Atomic clear-and-reinsert within a savepoint
        try:
            nested = session.begin_nested()

            # Delete existing road-results startlist entries for this race
            session.query(Startlist).filter(
                Startlist.race_id == race.id,
                Startlist.source == "road-results",
            ).delete()

            # Build checksum for change detection
            rider_str = "|".join(
                f"{r['name']}:{r.get('carried_points', '')}"
                for r in sorted(riders, key=lambda x: x["name"])
            )
            checksum = hashlib.sha256(rider_str.encode()).hexdigest()

            # Insert new rows
            cats = set()
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
                if rider_data.get("category"):
                    cats.add(rider_data["category"])

            nested.commit()

            record_refresh(
                session, race_id=race.id, refresh_type="startlist",
                status="success", entry_count=len(riders), checksum=checksum,
                event_id=race.event_id,
            )
            total_races += 1

            click.echo(
                f"  {race.name}: {len(riders)} riders ({len(cats)} categories)"
            )

            # Inter-race delay
            import time
            time.sleep(3.0)

        except Exception:
            nested.rollback()
            logger.warning("Failed to persist startlist for %s", race.name, exc_info=True)
            record_refresh(
                session, race_id=race.id, refresh_type="startlist",
                status="error", error_message="persist failed",
                event_id=race.event_id,
            )

    session.commit()
    session.close()
    click.echo(
        f"Fetched {total_entries} startlist entries across {total_races} races."
    )


if __name__ == "__main__":
    main()
