"""Query and aggregation layer for RaceAnalyzer.

All functions accept a SQLAlchemy Session and return pandas DataFrames.
Separated from the UI for testability and reuse.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
from sqlalchemy import distinct, extract, func
from sqlalchemy.orm import Session

from raceanalyzer.config import Settings
from raceanalyzer.db.models import Course, Race, RaceClassification, RaceSeries, RaceType, Result

# --- Race type inference ---

_RACE_TYPE_PATTERNS: list[tuple[list[str], RaceType]] = [
    (["criterium", "crit ", "crit,", "grand prix", "short track"], RaceType.CRITERIUM),
    (["stage race", "tour de"], RaceType.STAGE_RACE),
    (["hill climb", "mount ", "mt ", "hillclimb"], RaceType.HILL_CLIMB),
    (["time trial", "tt ", "itt", "chrono"], RaceType.TIME_TRIAL),
    (["roubaix", "gravel", "unpaved"], RaceType.GRAVEL),
]


def infer_race_type(race_name: str) -> RaceType:
    """Infer race type from the race name using keyword matching.

    Falls back to ROAD_RACE if no pattern matches.
    """
    name_lower = race_name.lower()
    for patterns, race_type in _RACE_TYPE_PATTERNS:
        for pattern in patterns:
            if pattern in name_lower:
                return race_type
    return RaceType.ROAD_RACE


# --- Race type display names ---

RACE_TYPE_DISPLAY_NAMES = {
    "criterium": "Criterium",
    "road_race": "Road Race",
    "hill_climb": "Hill Climb",
    "stage_race": "Stage Race",
    "time_trial": "Time Trial",
    "gravel": "Gravel",
    "unknown": "Unknown",
}


def race_type_display_name(race_type_value: str) -> str:
    """Convert RaceType enum value to human-readable name."""
    return RACE_TYPE_DISPLAY_NAMES.get(
        race_type_value, race_type_value.replace("_", " ").title()
    )


def get_races(
    session: Session,
    *,
    year: Optional[int] = None,
    states: Optional[list[str]] = None,
    limit: int = 500,
) -> pd.DataFrame:
    """Return races ordered by date descending, with optional filters.

    Columns: id, name, date, location, state_province, num_categories.
    """
    query = session.query(
        Race.id,
        Race.name,
        Race.date,
        Race.location,
        Race.state_province,
        func.count(distinct(RaceClassification.category)).label("num_categories"),
    ).outerjoin(RaceClassification, Race.id == RaceClassification.race_id)

    if year is not None:
        query = query.filter(extract("year", Race.date) == year)
    if states:
        query = query.filter(Race.state_province.in_(states))

    query = query.group_by(Race.id).order_by(Race.date.desc()).limit(limit)

    rows = query.all()
    if not rows:
        return pd.DataFrame(columns=[
            "id", "name", "date", "location", "state_province", "num_categories",
        ])

    return pd.DataFrame(rows, columns=[
            "id", "name", "date", "location", "state_province", "num_categories",
        ])


def get_race_detail(session: Session, race_id: int) -> Optional[dict]:
    """Return a single race with its classifications and results.

    Returns None if race not found.
    """
    race = session.get(Race, race_id)
    if race is None:
        return None

    settings = Settings()
    race_dict = {
        "id": race.id,
        "name": race.name,
        "date": race.date,
        "location": race.location,
        "state_province": race.state_province,
        "url": race.url,
    }

    classifications = (
        session.query(RaceClassification)
        .filter(RaceClassification.race_id == race_id)
        .all()
    )

    class_rows = []
    for c in classifications:
        label, color, qualifier = confidence_label(c.cv_of_times, settings)
        class_rows.append({
            "category": c.category,
            "finish_type": c.finish_type.value if c.finish_type else "unknown",
            "confidence_label": label,
            "confidence_color": color,
            "qualifier": qualifier,
            "num_finishers": c.num_finishers,
            "num_groups": c.num_groups,
            "largest_group_size": c.largest_group_size,
            "largest_group_ratio": c.largest_group_ratio,
            "leader_group_size": c.leader_group_size,
            "gap_to_second_group": c.gap_to_second_group,
            "cv_of_times": c.cv_of_times,
        })

    class_df = pd.DataFrame(class_rows) if class_rows else pd.DataFrame(
        columns=["category", "finish_type", "confidence_label", "confidence_color",
                 "qualifier", "num_finishers", "num_groups", "largest_group_size",
                 "largest_group_ratio", "leader_group_size", "gap_to_second_group",
                 "cv_of_times"]
    )

    results = (
        session.query(Result)
        .filter(Result.race_id == race_id)
        .order_by(Result.race_category_name, Result.place)
        .all()
    )

    result_rows = []
    for r in results:
        result_rows.append({
            "category": r.race_category_name,
            "place": r.place,
            "name": r.name,
            "team": r.team,
            "race_time": r.race_time,
            "gap_to_leader": r.gap_to_leader,
            "gap_group_id": r.gap_group_id,
            "dnf": r.dnf,
        })

    results_df = pd.DataFrame(result_rows) if result_rows else pd.DataFrame(
        columns=["category", "place", "name", "team", "race_time",
                 "gap_to_leader", "gap_group_id", "dnf"]
    )

    return {
        "race": race_dict,
        "classifications": class_df,
        "results": results_df,
    }


def get_finish_type_distribution(
    session: Session,
    *,
    category: Optional[str] = None,
    states: Optional[list[str]] = None,
    year: Optional[int] = None,
) -> pd.DataFrame:
    """Finish type counts with percentages.

    Columns: finish_type, count, percentage.
    """
    query = (
        session.query(
            RaceClassification.finish_type,
            func.count().label("count"),
        )
        .join(Race, Race.id == RaceClassification.race_id)
    )

    if category is not None:
        query = query.filter(RaceClassification.category == category)
    if states:
        query = query.filter(Race.state_province.in_(states))
    if year is not None:
        query = query.filter(extract("year", Race.date) == year)

    query = query.group_by(RaceClassification.finish_type)
    rows = query.all()

    if not rows:
        return pd.DataFrame(columns=["finish_type", "count", "percentage"])

    data = [{"finish_type": r[0].value, "count": r[1]} for r in rows]
    df = pd.DataFrame(data)
    total = df["count"].sum()
    df["percentage"] = (df["count"] / total * 100).round(1) if total > 0 else 0.0
    return df.sort_values("count", ascending=False).reset_index(drop=True)


def get_finish_type_trend(
    session: Session,
    *,
    category: Optional[str] = None,
    states: Optional[list[str]] = None,
) -> pd.DataFrame:
    """Yearly finish type counts for stacked area chart.

    Columns: year, finish_type, count.
    """
    year_col = extract("year", Race.date).label("year")
    query = (
        session.query(
            year_col,
            RaceClassification.finish_type,
            func.count().label("count"),
        )
        .join(Race, Race.id == RaceClassification.race_id)
        .filter(Race.date.isnot(None))
    )

    if category is not None:
        query = query.filter(RaceClassification.category == category)
    if states:
        query = query.filter(Race.state_province.in_(states))

    query = query.group_by("year", RaceClassification.finish_type).order_by("year")
    rows = query.all()

    if not rows:
        return pd.DataFrame(columns=["year", "finish_type", "count"])

    data = [{"year": int(r[0]), "finish_type": r[1].value, "count": r[2]} for r in rows]
    return pd.DataFrame(data)


def get_categories(session: Session) -> list[str]:
    """All distinct category names from RaceClassification, sorted."""
    rows = (
        session.query(distinct(RaceClassification.category))
        .order_by(RaceClassification.category)
        .all()
    )
    return [r[0] for r in rows if r[0]]


def get_available_years(session: Session) -> list[int]:
    """Distinct years with race data, sorted descending."""
    year_col = func.strftime("%Y", Race.date).label("year")
    rows = (
        session.query(distinct(year_col))
        .filter(Race.date.isnot(None))
        .order_by(year_col.desc())
        .all()
    )
    return [int(r[0]) for r in rows if r[0]]


def get_available_states(session: Session) -> list[str]:
    """Distinct state_province values, sorted."""
    rows = (
        session.query(distinct(Race.state_province))
        .filter(Race.state_province.isnot(None))
        .order_by(Race.state_province)
        .all()
    )
    return [r[0] for r in rows if r[0]]


def confidence_label(
    cv_of_times: Optional[float],
    settings: Optional[Settings] = None,
) -> tuple[str, str, str]:
    """Map cv_of_times to (label, color, qualifier).

    Returns: ("High confidence", "green", "Likely") etc.
    """
    if settings is None:
        settings = Settings()

    if cv_of_times is None:
        return ("Unknown", "gray", "")

    if cv_of_times < settings.confidence_high_threshold:
        return ("High confidence", "green", "Likely")
    elif cv_of_times < settings.confidence_medium_threshold:
        return ("Moderate confidence", "orange", "Probable")
    else:
        return ("Low confidence", "red", "Possible")


def _compute_overall_finish_type(
    session: Session, race_id: int,
) -> str:
    """Compute the most frequent non-UNKNOWN finish type for a race.

    Tiebreak: total finishers, then lowest average CV.
    Returns the finish_type value string, or "unknown" if all are UNKNOWN.
    """
    from collections import Counter

    classifications = (
        session.query(RaceClassification)
        .filter(RaceClassification.race_id == race_id)
        .all()
    )

    # Count non-UNKNOWN finish types, tracking finishers and CV for tiebreak
    type_counts: Counter = Counter()
    type_finishers: dict[str, int] = {}
    type_cv_sum: dict[str, float] = {}
    type_cv_count: dict[str, int] = {}

    for c in classifications:
        ft = c.finish_type.value if c.finish_type else "unknown"
        if ft == "unknown":
            continue
        type_counts[ft] += 1
        type_finishers[ft] = type_finishers.get(ft, 0) + (c.num_finishers or 0)
        if c.cv_of_times is not None:
            type_cv_sum[ft] = type_cv_sum.get(ft, 0.0) + c.cv_of_times
            type_cv_count[ft] = type_cv_count.get(ft, 0) + 1

    if not type_counts:
        return "unknown"

    # Sort by count desc, finishers desc, avg CV asc
    def sort_key(ft: str) -> tuple:
        avg_cv = (
            type_cv_sum.get(ft, 0.0) / type_cv_count[ft]
            if type_cv_count.get(ft, 0) > 0
            else float("inf")
        )
        return (-type_counts[ft], -type_finishers.get(ft, 0), avg_cv)

    return min(type_counts.keys(), key=sort_key)


def get_race_tiles(
    session: Session,
    *,
    year: Optional[int] = None,
    states: Optional[list[str]] = None,
    limit: int = 200,
) -> pd.DataFrame:
    """Return race tile data including overall_finish_type.

    Columns: id, name, date, location, state_province, race_type,
    course_lat, course_lon, num_categories, overall_finish_type.
    """
    query = session.query(
        Race.id,
        Race.name,
        Race.date,
        Race.location,
        Race.state_province,
        Race.race_type,
        Race.course_lat,
        Race.course_lon,
        func.count(distinct(RaceClassification.category)).label("num_categories"),
    ).outerjoin(RaceClassification, Race.id == RaceClassification.race_id)

    if year is not None:
        query = query.filter(func.strftime("%Y", Race.date) == str(year))
    if states:
        query = query.filter(Race.state_province.in_(states))

    query = query.group_by(Race.id).order_by(Race.date.desc()).limit(limit)

    rows = query.all()
    columns = [
        "id", "name", "date", "location", "state_province",
        "race_type", "course_lat", "course_lon", "num_categories",
        "overall_finish_type",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)

    data = []
    for row in rows:
        overall_ft = _compute_overall_finish_type(session, row.id)
        data.append({
            "id": row.id,
            "name": row.name,
            "date": row.date,
            "location": row.location,
            "state_province": row.state_province,
            "race_type": row.race_type.value if row.race_type else None,
            "course_lat": row.course_lat,
            "course_lon": row.course_lon,
            "num_categories": row.num_categories,
            "overall_finish_type": overall_ft,
        })
    return pd.DataFrame(data, columns=columns)


def get_scary_racers(
    session: Session,
    race_id: int,
    category: str,
    *,
    top_n: int = 5,
) -> pd.DataFrame:
    """Return top predicted performers for a race + category.

    Ranks riders by their carried_points (road-results Elo-like system).
    Only considers riders who have results in this category.
    Columns: name, team, carried_points, wins.
    """
    race = session.get(Race, race_id)
    if race is None:
        return pd.DataFrame(columns=["name", "team", "carried_points", "wins"])

    # Find riders with results in this category, get their best carried_points
    rider_results = (
        session.query(
            Result.rider_id,
            Result.name,
            Result.team,
            Result.carried_points,
            Result.place,
        )
        .filter(
            Result.race_category_name == category,
            Result.rider_id.isnot(None),
            Result.dnf.is_(False),
            Result.place.isnot(None),
        )
        .all()
    )

    if not rider_results:
        return pd.DataFrame(columns=["name", "team", "carried_points", "wins"])

    # Aggregate per rider: max carried_points, count wins
    rider_stats: dict[int, dict] = {}
    for rider_id, name, team, points, place in rider_results:
        if rider_id not in rider_stats:
            rider_stats[rider_id] = {
                "name": name,
                "team": team or "",
                "carried_points": 0.0,
                "wins": 0,
            }
        stats = rider_stats[rider_id]
        stats["name"] = name
        if team:
            stats["team"] = team
        if points is not None and points > stats["carried_points"]:
            stats["carried_points"] = points
        if place == 1:
            stats["wins"] += 1

    rows = list(rider_stats.values())
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df.sort_values("carried_points", ascending=False).head(top_n).reset_index(drop=True)
    return df


FINISH_TYPE_DISPLAY_NAMES = {
    "bunch_sprint": "Bunch Sprint",
    "small_group_sprint": "Small Group Sprint",
    "breakaway": "Breakaway",
    "breakaway_selective": "Breakaway Selective",
    "reduced_sprint": "Reduced Sprint",
    "gc_selective": "GC Selective",
    "mixed": "Mixed",
    "individual_tt": "Individual TT",
    "unknown": "Unknown",
}

FINISH_TYPE_TOOLTIPS = {
    "bunch_sprint": "The whole pack stayed together and sprinted for the line.",
    "small_group_sprint": "A select group broke clear and sprinted among themselves.",
    "breakaway": "A solo rider or tiny group escaped and held on to the finish.",
    "breakaway_selective": "Attackers rode away and the chase groups shattered behind them.",
    "reduced_sprint": "The hard pace dropped many riders, but the survivors sprinted it out.",
    "gc_selective": "The race blew apart — small groups everywhere, no pack left.",
    "individual_tt": "Riders started one at a time and raced the clock, not each other.",
    "mixed": "A bit of everything happened — no single pattern dominated.",
    "unknown": "Not enough timing data to classify this race.",
}


def finish_type_display_name(finish_type_value: str) -> str:
    """Convert enum value to human-readable name via lookup dict."""
    return FINISH_TYPE_DISPLAY_NAMES.get(
        finish_type_value, finish_type_value.replace("_", " ").title()
    )


# --- Series queries ---


def _compute_series_overall_finish_type(
    session: Session, series_id: int,
) -> str:
    """Most frequent non-UNKNOWN finish type across ALL editions of a series."""
    from collections import Counter

    classifications = (
        session.query(RaceClassification)
        .join(Race, Race.id == RaceClassification.race_id)
        .filter(Race.series_id == series_id)
        .all()
    )

    type_counts: Counter = Counter()
    type_finishers: dict[str, int] = {}
    type_cv_sum: dict[str, float] = {}
    type_cv_count: dict[str, int] = {}

    for c in classifications:
        ft = c.finish_type.value if c.finish_type else "unknown"
        if ft == "unknown":
            continue
        type_counts[ft] += 1
        type_finishers[ft] = type_finishers.get(ft, 0) + (c.num_finishers or 0)
        if c.cv_of_times is not None:
            type_cv_sum[ft] = type_cv_sum.get(ft, 0.0) + c.cv_of_times
            type_cv_count[ft] = type_cv_count.get(ft, 0) + 1

    if not type_counts:
        return "unknown"

    def sort_key(ft: str) -> tuple:
        avg_cv = (
            type_cv_sum.get(ft, 0.0) / type_cv_count[ft]
            if type_cv_count.get(ft, 0) > 0
            else float("inf")
        )
        return (-type_counts[ft], -type_finishers.get(ft, 0), avg_cv)

    return min(type_counts.keys(), key=sort_key)


def get_series_tiles(
    session: Session,
    *,
    year: Optional[int] = None,
    states: Optional[list[str]] = None,
    limit: int = 200,
) -> pd.DataFrame:
    """Return one row per series with aggregated data for calendar tiles.

    Columns: series_id, display_name, edition_count, earliest_date,
    latest_date, location, state_province, overall_finish_type.
    """
    query = (
        session.query(
            RaceSeries.id.label("series_id"),
            RaceSeries.display_name,
            func.count(Race.id).label("edition_count"),
            func.min(Race.date).label("earliest_date"),
            func.max(Race.date).label("latest_date"),
        )
        .join(Race, Race.series_id == RaceSeries.id)
    )

    if year is not None:
        query = query.filter(extract("year", Race.date) == year)
    if states:
        query = query.filter(Race.state_province.in_(states))

    query = (
        query.group_by(RaceSeries.id)
        .order_by(func.max(Race.date).desc())
        .limit(limit)
    )

    rows = query.all()
    columns = [
        "series_id", "display_name", "edition_count", "earliest_date",
        "latest_date", "location", "state_province", "overall_finish_type",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)

    data = []
    for row in rows:
        # Get location from most recent edition
        most_recent = (
            session.query(Race)
            .filter(Race.series_id == row.series_id)
            .order_by(Race.date.desc())
            .first()
        )
        overall_ft = _compute_series_overall_finish_type(session, row.series_id)
        data.append({
            "series_id": row.series_id,
            "display_name": row.display_name,
            "edition_count": row.edition_count,
            "earliest_date": row.earliest_date,
            "latest_date": row.latest_date,
            "location": most_recent.location if most_recent else None,
            "state_province": most_recent.state_province if most_recent else None,
            "overall_finish_type": overall_ft,
        })
    return pd.DataFrame(data, columns=columns)


def get_series_detail(session: Session, series_id: int) -> Optional[dict]:
    """Return series info with all editions and aggregated classifications."""
    series = session.get(RaceSeries, series_id)
    if series is None:
        return None

    editions = (
        session.query(Race)
        .filter(Race.series_id == series_id)
        .order_by(Race.date.desc())
        .all()
    )

    # Build per-edition detail
    edition_details = []
    for race in editions:
        detail = get_race_detail(session, race.id)
        if detail:
            edition_details.append(detail)

    # Build classification trend (year x finish_type -> count)
    trend_rows = []
    for race in editions:
        year = race.date.year if race.date else None
        if year is None:
            continue
        for cls in race.classifications:
            ft = cls.finish_type.value if cls.finish_type else "unknown"
            trend_rows.append({
                "year": year,
                "finish_type": ft,
                "category": cls.category,
            })

    trend_df = pd.DataFrame(trend_rows) if trend_rows else pd.DataFrame(
        columns=["year", "finish_type", "category"]
    )

    # Get categories across all editions
    all_categories = sorted(set(
        cls.category for race in editions for cls in race.classifications
    ))

    overall_ft = _compute_series_overall_finish_type(session, series_id)

    polyline = series.rwgps_encoded_polyline

    return {
        "series": {
            "id": series.id,
            "display_name": series.display_name,
            "normalized_name": series.normalized_name,
            "edition_count": len(editions),
            "rwgps_route_id": series.rwgps_route_id,
            "encoded_polyline": polyline,
        },
        "editions": edition_details,
        "trend": trend_df,
        "categories": all_categories,
        "overall_finish_type": overall_ft,
    }


def get_race_preview(
    session: Session,
    series_id: int,
    category: Optional[str] = None,
) -> Optional[dict]:
    """Assemble all data for the Race Preview page.

    Returns: {
        "series": dict,
        "course": dict | None,        # terrain, distance, gain, map polyline
        "prediction": dict | None,     # predicted finish type + confidence
        "contenders": pd.DataFrame,    # ranked contender list
        "categories": list[str],
        "has_startlist": bool,
    }
    """
    from raceanalyzer.db.models import Startlist
    from raceanalyzer.predictions import predict_contenders, predict_series_finish_type

    series = session.get(RaceSeries, series_id)
    if series is None:
        return None

    # Series info
    series_dict = {
        "id": series.id,
        "display_name": series.display_name,
        "normalized_name": series.normalized_name,
        "rwgps_route_id": series.rwgps_route_id,
        "encoded_polyline": series.rwgps_encoded_polyline,
    }

    # Course data
    course_row = (
        session.query(Course)
        .filter(Course.series_id == series_id)
        .first()
    )
    course_dict = None
    if course_row:
        course_dict = {
            "distance_m": course_row.distance_m,
            "total_gain_m": course_row.total_gain_m,
            "total_loss_m": course_row.total_loss_m,
            "max_elevation_m": course_row.max_elevation_m,
            "min_elevation_m": course_row.min_elevation_m,
            "m_per_km": course_row.m_per_km,
            "course_type": course_row.course_type.value if course_row.course_type else "unknown",
        }

    # Prediction
    prediction = predict_series_finish_type(session, series_id, category=category)
    if prediction["predicted_finish_type"] == "unknown":
        prediction = None

    # Categories across all editions
    all_categories = sorted(set(
        cls.category
        for race in series.races
        for cls in race.classifications
    ))

    # Contenders (need a category)
    contenders = pd.DataFrame(
        columns=["name", "team", "carried_points", "source", "wins_in_series", "last_raced"]
    )
    if category:
        contenders = predict_contenders(session, series_id, category)
    elif all_categories:
        # Default to first category
        contenders = predict_contenders(session, series_id, all_categories[0])

    # Startlist check
    has_startlist = (
        session.query(Startlist)
        .filter(Startlist.series_id == series_id)
        .first()
    ) is not None

    # Most recent race date (for post-race feedback check)
    most_recent = (
        session.query(Race)
        .filter(Race.series_id == series_id)
        .order_by(Race.date.desc())
        .first()
    )
    latest_date = most_recent.date if most_recent else None

    return {
        "series": series_dict,
        "course": course_dict,
        "prediction": prediction,
        "contenders": contenders,
        "categories": all_categories,
        "has_startlist": has_startlist,
        "latest_date": latest_date,
    }


def get_series_editions(session: Session, series_id: int) -> list[dict]:
    """Return basic info for all editions in a series (for sidebar links)."""
    editions = (
        session.query(Race.id, Race.name, Race.date)
        .filter(Race.series_id == series_id)
        .order_by(Race.date.desc())
        .all()
    )
    return [
        {"id": e.id, "name": e.name, "date": e.date}
        for e in editions
    ]
