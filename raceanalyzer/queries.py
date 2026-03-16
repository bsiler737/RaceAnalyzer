"""Query and aggregation layer for RaceAnalyzer.

All functions accept a SQLAlchemy Session and return pandas DataFrames.
Separated from the UI for testability and reuse.
"""

from __future__ import annotations

import enum
import logging
import re as _re
import time
from datetime import date, datetime
from itertools import groupby
from typing import Optional

import pandas as pd
from sqlalchemy import distinct, extract, func
from sqlalchemy.orm import Session

from raceanalyzer.config import Settings
from raceanalyzer.db.models import (
    CategoryDetail,
    Course,
    Race,
    RaceClassification,
    RaceSeries,
    RaceType,
    Result,
    Startlist,
)

logger = logging.getLogger("raceanalyzer")


class Discipline(str, enum.Enum):
    ROAD = "road"
    GRAVEL = "gravel"
    CYCLOCROSS = "cyclocross"
    MTB = "mtb"
    TRACK = "track"
    UNKNOWN = "unknown"


RACE_TYPE_TO_DISCIPLINE = {
    RaceType.CRITERIUM: Discipline.ROAD,
    RaceType.ROAD_RACE: Discipline.ROAD,
    RaceType.HILL_CLIMB: Discipline.ROAD,
    RaceType.STAGE_RACE: Discipline.ROAD,
    RaceType.TIME_TRIAL: Discipline.ROAD,
    RaceType.GRAVEL: Discipline.GRAVEL,
}


def discipline_for_race_type(race_type):
    if race_type is None:
        return Discipline.UNKNOWN
    return RACE_TYPE_TO_DISCIPLINE.get(race_type, Discipline.UNKNOWN)


class PerfTimer:
    def __init__(self, label):
        self.label = label
        self.elapsed_ms = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000
        logger.info("[perf] %s: %.1fms", self.label, self.elapsed_ms)


PERF_BUDGET_COLD_MS = 1000
PERF_BUDGET_WARM_MS = 200


def countdown_label(days_until):
    if days_until is None:
        return ""
    if days_until == 0:
        return "Today"
    if days_until == 1:
        return "Tomorrow"
    if days_until <= 14:
        return f"in {days_until} days"
    weeks = days_until // 7
    return f"in {weeks} weeks"


def group_by_month(items):
    upcoming = sorted(
        [i for i in items if i["is_upcoming"]],
        key=lambda i: i["upcoming_date"] or date.max,
    )
    historical = [i for i in items if not i["is_upcoming"]]

    def month_key(i):
        # Sprint 021: Stage race children use anchor date for month grouping
        # so the entire stage race group stays in one month section
        anchor = i.get("stage_anchor_date")
        d = anchor or i.get("upcoming_date")
        if d:
            return (d.year, d.month)
        return (9999, 12)

    groups = []
    for (year, month), group_items in groupby(upcoming, key=month_key):
        header = f"{date(year, month, 1):%B %Y}"
        groups.append((header, list(group_items)))

    if historical:
        groups.append(("Past Races", historical))
    return groups

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


# Masters age bracket lower bounds (USAC standard)
_MASTERS_BRACKETS = [35, 40, 45, 50, 55, 60, 65, 70, 75, 80]


def resolve_racer_profile_matches(
    all_categories: list[str],
    cat_level: Optional[str] = None,
    gender: Optional[str] = None,
    masters_on: bool = False,
    masters_age: Optional[int] = None,
) -> list[str]:
    """Return all category strings compatible with the current racer profile.

    Returns empty list if no filters are set or no matches found.
    Results are sorted alphabetically for stable ordering.
    """
    if not cat_level and not gender and not masters_on:
        return []

    candidates = list(all_categories)

    # Filter by cat level (e.g., "3" matches "Cat 3", "CAT 3-4", "cat 1/2/3")
    if cat_level:
        level_filtered = []
        for c in candidates:
            c_lower = c.lower()
            if _re.search(r'cat\w*\s*' + cat_level, c_lower):
                level_filtered.append(c)
            elif _re.search(r'\b' + cat_level + r'\b', c_lower) and 'cat' in c_lower:
                level_filtered.append(c)
        if level_filtered:
            candidates = level_filtered

    # Filter by gender
    if gender == "W":
        gender_filtered = [
            c for c in candidates
            if _re.search(r'\bwom[ae]n\b', c, _re.IGNORECASE)
        ]
        if gender_filtered:
            candidates = gender_filtered
    elif gender == "M":
        men_filtered = [
            c for c in candidates
            if _re.search(r'\bmen\b', c, _re.IGNORECASE)
            and not _re.search(r'\bwom[ae]n\b', c, _re.IGNORECASE)
        ]
        if men_filtered:
            candidates = men_filtered
        else:
            candidates = [
                c for c in candidates
                if not _re.search(r'\bwom[ae]n\b', c, _re.IGNORECASE)
            ]
    elif gender == "NB":
        nb_filtered = [
            c for c in candidates
            if _re.search(r'\bnon[\s-]?binary\b|\bNB\b|\benby\b', c, _re.IGNORECASE)
        ]
        if nb_filtered:
            candidates = nb_filtered

    # Filter by masters
    if masters_on:
        if masters_age:
            bracket = max(
                (b for b in _MASTERS_BRACKETS if b <= masters_age),
                default=35,
            )
        else:
            bracket = 35

        # Masters racer can race both non-masters AND age-eligible masters fields
        non_masters = [
            c for c in candidates
            if not _re.search(r'master', c, _re.IGNORECASE)
        ]
        masters_filtered = [
            c for c in candidates
            if _re.search(r'master', c, _re.IGNORECASE)
        ]
        # Filter masters to age-eligible brackets (bracket+ means age >= bracket)
        age_eligible = []
        for c in masters_filtered:
            # Find all age numbers in the category string
            ages = _re.findall(r'(\d{2})\+', c)
            if ages:
                # Eligible if racer meets the youngest bracket requirement
                min_required = min(int(a) for a in ages)
                if masters_age and masters_age >= min_required:
                    age_eligible.append(c)
                elif not masters_age:
                    # No age specified, include all masters
                    age_eligible.append(c)
            else:
                # Masters field with no age bracket (e.g., "Masters Open")
                age_eligible.append(c)

        candidates = non_masters + age_eligible
    else:
        # Non-masters racer: exclude masters-only fields
        candidates = [
            c for c in candidates
            if not _re.search(r'master', c, _re.IGNORECASE)
        ]

    return sorted(candidates)


def resolve_racer_profile(
    all_categories: list[str],
    cat_level: Optional[str] = None,
    gender: Optional[str] = None,
    masters_on: bool = False,
    masters_age: Optional[int] = None,
) -> tuple[Optional[str], bool]:
    """Map racer profile filters to the best-matching category string.

    Returns (category_string, is_exact_match).
    Thin wrapper over resolve_racer_profile_matches() for backward compat.
    """
    if not cat_level and not gender and not masters_on:
        return (None, True)

    matches = resolve_racer_profile_matches(
        all_categories,
        cat_level=cat_level,
        gender=gender,
        masters_on=masters_on,
        masters_age=masters_age,
    )
    if not matches:
        return (None, False)

    best = min(matches, key=len)
    is_exact = len(matches) == 1
    return (best, is_exact)


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


_STATE_NORMALIZE = {
    "Oregon": "OR",
    "OR.": "OR",
    "US-OR": "OR",
    "Washington": "WA",
    "Wa": "WA",
}


def normalize_state(raw: str) -> str:
    """Normalize state/province values to standard abbreviations."""
    return _STATE_NORMALIZE.get(raw, raw)


PNW_STATES = {"WA", "OR", "ID", "BC", "MT"}


def get_available_states(session: Session) -> list[str]:
    """Distinct state_province values, normalized, filtered to PNW, and sorted."""
    rows = (
        session.query(distinct(Race.state_province))
        .filter(Race.state_province.isnot(None))
        .order_by(Race.state_province)
        .all()
    )
    raw_states = [r[0] for r in rows if r[0]]
    # Normalize, deduplicate, and filter to PNW states
    seen = set()
    result = []
    for s in raw_states:
        norm = normalize_state(s)
        if norm not in seen and norm in PNW_STATES:
            seen.add(norm)
            result.append(norm)
    return sorted(result)


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
    category: Optional[str] = None,
    categories: Optional[list[str]] = None,
    *,
    top_n: int = 10,
) -> pd.DataFrame:
    """Return top predicted performers for a race + category.

    Strategy:
    1. If a startlist exists for this race, return only registered riders
       ranked by their carried_points (lower = stronger).
    2. If no startlist, fall back to historical performers from past
       editions of the same series.

    Columns: name, team, carried_points, wins, source.
    """
    empty = pd.DataFrame(
        columns=["name", "team", "carried_points", "wins", "source"],
    )
    race = session.get(Race, race_id)
    if race is None:
        return empty

    # --- Strategy 1: Startlist-based scary riders ---
    sl_q = session.query(
        Startlist.rider_name,
        Startlist.team,
        Startlist.carried_points,
        Startlist.rider_id,
    ).filter(Startlist.race_id == race_id)

    if categories:
        sl_rows = sl_q.filter(Startlist.category.in_(categories)).all()
    elif category:
        exact = sl_q.filter(Startlist.category == category).all()
        if exact:
            sl_rows = exact
        else:
            sl_rows = sl_q.filter(
                Startlist.category.ilike(f"%{category}%"),
            ).all()
    else:
        sl_rows = sl_q.all()

    if sl_rows:
        # Cross-reference with historical wins from this series
        series_race_ids = [
            r[0] for r in session.query(Race.id)
            .filter(Race.series_id == race.series_id)
            .all()
        ]
        # Build a rider_id -> win count map
        win_counts: dict[int, int] = {}
        if series_race_ids:
            wins_q = (
                session.query(Result.rider_id, func.count())
                .filter(
                    Result.race_id.in_(series_race_ids),
                    Result.rider_id.isnot(None),
                    Result.place == 1,
                )
                .group_by(Result.rider_id)
                .all()
            )
            win_counts = {rid: cnt for rid, cnt in wins_q}

        rows = []
        for rname, team, points, rider_id in sl_rows:
            if points is None:
                continue
            rows.append({
                "name": rname,
                "team": team or "",
                "carried_points": points,
                "wins": win_counts.get(rider_id, 0) if rider_id else 0,
                "source": "startlist",
            })
        if rows:
            df = pd.DataFrame(rows)
            df = (
                df.sort_values("carried_points", ascending=True)
                .drop_duplicates(subset=["name"], keep="first")
                .head(top_n)
                .reset_index(drop=True)
            )
            return df

    # --- Strategy 2: Historical fallback ---
    series_race_ids = [
        r[0] for r in session.query(Race.id)
        .filter(Race.series_id == race.series_id)
        .all()
    ]
    if not series_race_ids:
        return empty

    q = (
        session.query(
            Result.rider_id,
            Result.name,
            Result.team,
            Result.carried_points,
            Result.place,
        )
        .filter(
            Result.race_id.in_(series_race_ids),
            Result.rider_id.isnot(None),
            Result.dnf.is_(False),
            Result.place.isnot(None),
        )
    )

    if categories:
        rider_results = q.filter(Result.race_category_name.in_(categories)).all()
    elif category:
        exact = q.filter(Result.race_category_name == category).all()
        if exact:
            rider_results = exact
        else:
            rider_results = q.filter(
                Result.race_category_name.ilike(f"%{category}%"),
            ).all()
    else:
        rider_results = q.all()

    if not rider_results:
        return empty

    rider_stats: dict[int, dict] = {}
    for rider_id, name, team, points, place in rider_results:
        if rider_id not in rider_stats:
            rider_stats[rider_id] = {
                "name": name,
                "team": team or "",
                "carried_points": float("inf"),
                "wins": 0,
                "source": "history",
            }
        stats = rider_stats[rider_id]
        stats["name"] = name
        if team:
            stats["team"] = team
        if points is not None and points < stats["carried_points"]:
            stats["carried_points"] = points
        if place == 1:
            stats["wins"] += 1

    rows = list(rider_stats.values())
    df = pd.DataFrame(rows)
    if df.empty:
        return empty

    df = (
        df.sort_values("carried_points", ascending=True)
        .head(top_n)
        .reset_index(drop=True)
    )
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
    matched_categories: Optional[list[str]] = None,
    racer_profile_label: str = "",
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
    import json

    from raceanalyzer.db.models import Startlist
    from raceanalyzer.predictions import (
        calculate_drop_rate,
        calculate_typical_speeds,
        generate_narrative,
        predict_contenders,
        predict_series_finish_type,
    )

    series = session.get(RaceSeries, series_id)
    if series is None:
        return None

    # Sprint 021: Stage-aware series info
    is_stage = series.parent_series_id is not None
    parent = None
    siblings = []
    if is_stage:
        parent = session.get(RaceSeries, series.parent_series_id)
        sibling_rows = (
            session.query(RaceSeries)
            .filter(RaceSeries.parent_series_id == series.parent_series_id)
            .order_by(RaceSeries.stage_number)
            .all()
        )
        siblings = [
            {
                "series_id": s.id,
                "display_name": s.display_name,
                "stage_number": s.stage_number,
                "is_current": s.id == series_id,
            }
            for s in sibling_rows
        ]

    # Series info
    series_dict = {
        "id": series.id,
        "display_name": series.display_name,
        "normalized_name": series.normalized_name,
        "rwgps_route_id": series.rwgps_route_id,
        "encoded_polyline": series.rwgps_encoded_polyline,
        # Sprint 021: Stage info
        "parent_series_id": series.parent_series_id,
        "stage_number": series.stage_number,
        "parent_display_name": parent.display_name if parent else None,
        "siblings": siblings,
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

    # Prediction: prefer pre-computed SeriesPrediction (has prediction_source)
    from raceanalyzer.db.models import SeriesPrediction

    pred_row = (
        session.query(SeriesPrediction)
        .filter(
            SeriesPrediction.series_id == series_id,
            SeriesPrediction.category == category,
        )
        .first()
    )
    if not pred_row:
        pred_row = (
            session.query(SeriesPrediction)
            .filter(
                SeriesPrediction.series_id == series_id,
                SeriesPrediction.category.is_(None),
            )
            .first()
        )

    if pred_row and pred_row.predicted_finish_type and pred_row.predicted_finish_type != "unknown":
        import json as _json

        prediction = {
            "predicted_finish_type": pred_row.predicted_finish_type,
            "confidence": pred_row.confidence,
            "edition_count": pred_row.edition_count or 0,
            "distribution": (
                _json.loads(pred_row.distribution_json)
                if pred_row.distribution_json
                else {}
            ),
            "prediction_source": getattr(pred_row, "prediction_source", None),
        }
    else:
        prediction = predict_series_finish_type(session, series_id, category=category)
        if prediction["predicted_finish_type"] == "unknown":
            prediction = None
        else:
            prediction["prediction_source"] = None

    # Categories: prefer current registration fields (CategoryDetail) over
    # historical classifications, so the dropdown only shows fields you can
    # actually register for.
    all_categories = []
    upcoming_race = (
        session.query(Race)
        .filter(Race.series_id == series_id, Race.is_upcoming.is_(True))
        .order_by(Race.date.asc())
        .first()
    )
    if upcoming_race:
        reg_cats = (
            session.query(CategoryDetail.category)
            .filter(CategoryDetail.race_id == upcoming_race.id)
            .all()
        )
        if reg_cats:
            all_categories = sorted(set(c[0] for c in reg_cats))
    if not all_categories:
        # Fallback to historical classifications
        for race in sorted(series.races, key=lambda r: r.date or datetime.min, reverse=True):
            cats = [cls.category for cls in race.classifications]
            if cats:
                all_categories = sorted(set(cats))
                break

    # Contenders (need a category)
    contenders = pd.DataFrame(
        columns=["name", "team", "carried_points", "source", "wins_in_series", "last_raced"]
    )
    if category:
        contenders = predict_contenders(session, series_id, category)
    elif all_categories:
        # Default to first category
        contenders = predict_contenders(session, series_id, all_categories[0])

    # Startlist check — Sprint 021: fall back to parent's startlist for stages
    has_startlist = (
        session.query(Startlist)
        .filter(Startlist.series_id == series_id)
        .first()
    ) is not None
    startlist_source_id = series_id
    if not has_startlist and is_stage and parent:
        parent_has = (
            session.query(Startlist)
            .filter(Startlist.series_id == parent.id)
            .first()
        ) is not None
        if parent_has:
            has_startlist = True
            startlist_source_id = parent.id

    # Most recent race date (for post-race feedback check)
    most_recent = (
        session.query(Race)
        .filter(Race.series_id == series_id)
        .order_by(Race.date.desc())
        .first()
    )
    latest_date = most_recent.date if most_recent else None

    # Historical stats
    drop_rate = calculate_drop_rate(session, series_id, category=category)
    typical_speed = calculate_typical_speeds(session, series_id, category=category)

    # When showing overall (no specific category), compute speed range across fields
    if not category and typical_speed and all_categories:
        field_speeds = []
        for cat in all_categories:
            fs = calculate_typical_speeds(session, series_id, category=cat)
            if fs:
                field_speeds.append(fs["median_winner_speed_mph"])
        if len(field_speeds) >= 2:
            lo = min(field_speeds)
            hi = max(field_speeds)
            if lo != hi:
                lo_kph = round(lo / 0.621371, 1)
                hi_kph = round(hi / 0.621371, 1)
                typical_speed["speed_range_mph"] = (lo, hi)
                typical_speed["speed_range_kph"] = (lo_kph, hi_kph)

    # Profile and climbs data
    profile_points = None
    climbs = None
    if course_row:
        if course_row.profile_json:
            try:
                profile_points = json.loads(course_row.profile_json)
            except (json.JSONDecodeError, TypeError):
                pass
        if course_row.climbs_json:
            try:
                climbs = json.loads(course_row.climbs_json)
            except (json.JSONDecodeError, TypeError):
                pass

    # Narrative
    distance_km = (
        course_row.distance_m / 1000.0
        if course_row and course_row.distance_m
        else None
    )
    total_gain_m = course_row.total_gain_m if course_row else None
    ct = course_row.course_type.value if course_row and course_row.course_type else None
    pred_ft = prediction["predicted_finish_type"] if prediction else None
    edition_count = prediction["edition_count"] if prediction else 0
    pred_source = prediction.get("prediction_source") if prediction else None
    narrative = generate_narrative(
        course_type=ct,
        predicted_finish_type=pred_ft,
        drop_rate=drop_rate,
        typical_speed=typical_speed,
        distance_km=distance_km,
        total_gain_m=total_gain_m,
        climbs=climbs,
        edition_count=edition_count,
        prediction_source=pred_source,
    )

    # Sprint 018: Category-aware distance and estimated time for preview
    # Load category details for the latest upcoming race
    latest_upcoming = (
        session.query(Race)
        .filter(Race.series_id == series_id, Race.is_upcoming.is_(True))
        .order_by(Race.date.asc())
        .first()
    )
    preview_cat_details = []
    if latest_upcoming:
        preview_cat_details = (
            session.query(CategoryDetail)
            .filter(CategoryDetail.race_id == latest_upcoming.id)
            .all()
        )
    cat_distance, cat_distance_unit = _resolve_category_distance(
        preview_cat_details, category
    )
    distance_range = _format_distance_range(preview_cat_details)

    # Build a pred_map subset for this series to reuse _format_time_range
    from raceanalyzer.db.models import SeriesPrediction as _SP
    series_preds = session.query(_SP).filter(_SP.series_id == series_id).all()
    _pred_map = {(p.series_id, p.category): p for p in series_preds}
    is_duration = _is_duration_race(preview_cat_details)
    race_type_val = most_recent.race_type if most_recent else None
    is_crit = race_type_val == RaceType.CRITERIUM
    hide_est_time = is_crit or is_duration
    est_time_range = (
        None if hide_est_time
        else _format_time_range(_pred_map, series_id, category)
    )

    # Sprint 019: Category-aware AI context and field forecasts
    from raceanalyzer.predictions import finish_type_teaser

    # Build pred_map for _select_feed_prediction_context
    preview_pred_map = {(p.series_id, p.category): p for p in series_preds}

    # Scope matched_categories to current registration fields only.
    # This prevents showing forecasts for historical field names that
    # don't exist in the current edition's registration.
    current_reg_fields = {cd.category for cd in preview_cat_details}
    scoped_matched = [
        c for c in (matched_categories or [])
        if c in current_reg_fields
    ] if current_reg_fields else (matched_categories or [])

    ai_context = _select_feed_prediction_context(
        preview_pred_map, series_id,
        matched_categories=scoped_matched,
        course_type=ct,
        racer_profile_label=racer_profile_label,
        race_type=race_type_val.value if race_type_val else None,
    )

    # Build field_forecasts for multi-match preview
    field_forecasts = []
    if scoped_matched:
        for cat in scoped_matched:
            cat_pred = preview_pred_map.get((series_id, cat))
            if (
                cat_pred
                and cat_pred.predicted_finish_type
                and cat_pred.predicted_finish_type != "unknown"
            ):
                field_forecasts.append({
                    "category": cat,
                    "finish_type": cat_pred.predicted_finish_type,
                    "teaser": finish_type_teaser(
                        cat_pred.predicted_finish_type,
                        prediction_source=getattr(cat_pred, "prediction_source", None),
                        race_type=(
                            race_type_val.value if race_type_val else None
                        ),
                        course_type=ct,
                    ),
                    "confidence": cat_pred.confidence,
                })

    # Sprint 021: Registration URL inheritance for stages
    reg_url = None
    if latest_upcoming:
        reg_url = latest_upcoming.registration_url
    if not reg_url and is_stage and parent:
        parent_upcoming = (
            session.query(Race)
            .filter(Race.series_id == parent.id, Race.is_upcoming.is_(True))
            .first()
        )
        if parent_upcoming:
            reg_url = parent_upcoming.registration_url

    # Sprint 021: Historical data fallback for stages
    history_banner = None
    if is_stage and parent:
        # Check if child has its own historical data
        child_historical = (
            session.query(Race)
            .filter(
                Race.series_id == series_id,
                Race.is_upcoming.is_(False),
            )
            .first()
        )
        if not child_historical:
            history_banner = (
                f"Showing overall {parent.display_name} history "
                f"\u2014 no stage-specific historical data available yet."
            )

    return {
        "series": series_dict,
        "course": course_dict,
        "prediction": prediction,
        "contenders": contenders,
        "categories": all_categories,
        "has_startlist": has_startlist,
        "startlist_source_id": startlist_source_id,
        "latest_date": latest_date,
        "drop_rate": drop_rate,
        "typical_speed": typical_speed,
        "profile_points": profile_points,
        "climbs": climbs,
        "narrative": narrative,
        # Sprint 018
        "category_distance": cat_distance,
        "category_distance_unit": cat_distance_unit,
        "distance_range": distance_range,
        "estimated_time_range": est_time_range,
        "hide_estimated_time": hide_est_time,
        # Sprint 019
        "ai_context": ai_context,
        "field_forecasts": field_forecasts,
        # Sprint 021: Stage race support
        "registration_url": reg_url,
        "history_banner": history_banner,
        "race_type": race_type_val.value if race_type_val else None,
        "state_province": most_recent.state_province if most_recent else None,
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


# --- Feed queries (Sprint 010) ---


def finish_type_plain_english(finish_type_value: str) -> str:
    """Return the full plain-English tooltip for a finish type."""
    return FINISH_TYPE_TOOLTIPS.get(finish_type_value, "")


def finish_type_plain_english_with_source(
    finish_type: str,
    prediction_source: Optional[str] = None,
    race_type: Optional[str] = None,
) -> Optional[str]:
    """Return plain English finish description with source-appropriate framing."""
    base = finish_type_plain_english(finish_type)
    if not base:
        return None

    if prediction_source == "course_profile":
        return f"Course profile suggests: {base[0].lower()}{base[1:]}"
    elif prediction_source == "race_type_only":
        rt_display = race_type_display_name(race_type) if race_type else "This race type"
        return f"{rt_display}s typically end this way: {base[0].lower()}{base[1:]}"
    else:
        return base


def climb_highlight(climbs: Optional[list]) -> Optional[str]:
    """Return a one-liner about the hardest climb, or None."""
    if not climbs:
        return None
    hardest = max(climbs, key=lambda c: c.get("avg_grade", 0))
    length_km = hardest.get("length_m", 0) / 1000.0
    grade = hardest.get("avg_grade", 0)
    if length_km <= 0 or grade <= 0:
        return None
    start_km = hardest.get("start_d", 0) / 1000.0
    return (
        f"The race gets hard at km {start_km:.0f}"
        f" \u2014 a {length_km:.1f} km climb averaging {grade:.1f}%"
    )


def _downsample_profile(profile_points: list, target: int = 50) -> list:
    """Downsample profile points to approximately `target` points."""
    if not profile_points or len(profile_points) <= target:
        return profile_points or []
    step = max(1, len(profile_points) // target)
    sampled = profile_points[::step]
    # Always include the last point
    if sampled[-1] != profile_points[-1]:
        sampled.append(profile_points[-1])
    return sampled


def search_series(
    session: Session,
    query_str: str,
) -> list[int]:
    """Return series IDs matching a search string (case-insensitive).

    Escapes SQL LIKE wildcards in user input.
    """
    if not query_str or not query_str.strip():
        return []
    escaped = (
        query_str.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    pattern = f"%{escaped}%"
    rows = (
        session.query(RaceSeries.id)
        .filter(RaceSeries.display_name.ilike(pattern))
        .all()
    )
    return [r[0] for r in rows]


def get_feed_items(
    session: Session,
    *,
    category: Optional[str] = None,
    search_query: Optional[str] = None,
    racing_soon_only: bool = False,
) -> list[dict]:
    """Return feed items: one per series, enriched with preview data.

    Each item contains series metadata, upcoming edition info, prediction,
    narrative snippet, drop rate, course info, and sort-relevant flags.
    Sorted: racing-soon upcoming first, then other upcoming, then historical.
    """
    import json
    from datetime import timedelta

    from raceanalyzer.predictions import predict_series_finish_type

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    soon_cutoff = today + timedelta(days=7)

    # Get all series (optionally filtered by search)
    if search_query and search_query.strip():
        matching_ids = search_series(session, search_query)
        if not matching_ids:
            return []
        series_list = (
            session.query(RaceSeries)
            .filter(RaceSeries.id.in_(matching_ids))
            .all()
        )
    else:
        series_list = session.query(RaceSeries).all()

    if not series_list:
        return []

    items = []
    for series in series_list:
        # Find upcoming edition (date >= today)
        upcoming_race = (
            session.query(Race)
            .filter(
                Race.series_id == series.id,
                Race.date >= today,
            )
            .order_by(Race.date.asc())
            .first()
        )

        # Most recent edition (for non-upcoming sort)
        most_recent = (
            session.query(Race)
            .filter(Race.series_id == series.id)
            .order_by(Race.date.desc())
            .first()
        )

        if most_recent is None:
            continue

        is_upcoming = upcoming_race is not None
        is_racing_soon = (
            is_upcoming
            and upcoming_race.date is not None
            and upcoming_race.date <= soon_cutoff
        )

        if racing_soon_only and not is_racing_soon:
            continue

        # Edition count
        edition_count = (
            session.query(func.count(Race.id))
            .filter(Race.series_id == series.id)
            .scalar()
        )

        # Prediction
        prediction = predict_series_finish_type(session, series.id, category=category)
        predicted_ft = prediction["predicted_finish_type"]
        confidence = prediction["confidence"]

        # Course data
        course_row = (
            session.query(Course)
            .filter(Course.series_id == series.id)
            .first()
        )
        course_type = None
        distance_m = None
        total_gain_m = None
        sparkline_points = []
        climbs_data = None

        if course_row:
            course_type = course_row.course_type.value if course_row.course_type else None
            distance_m = course_row.distance_m
            total_gain_m = course_row.total_gain_m
            if course_row.profile_json:
                try:
                    profile = json.loads(course_row.profile_json)
                    sparkline_points = _downsample_profile(profile)
                except (json.JSONDecodeError, TypeError):
                    pass
            if course_row.climbs_json:
                try:
                    climbs_data = json.loads(course_row.climbs_json)
                except (json.JSONDecodeError, TypeError):
                    pass

        # Racer type description
        from raceanalyzer.predictions import racer_type_description
        racer_desc = racer_type_description(course_type, predicted_ft)

        # Duration
        from raceanalyzer.predictions import calculate_typical_duration
        duration = calculate_typical_duration(session, series.id, category=category)

        # Drop rate (lightweight: just percentage + label)
        drop_rate_pct = None
        drop_rate_label = None
        from raceanalyzer.predictions import calculate_drop_rate
        dr = calculate_drop_rate(session, series.id, category=category)
        if dr:
            drop_rate_pct = round(dr["drop_rate"] * 100)
            drop_rate_label = dr["label"]

        # Narrative snippet (first 2 sentences, capped at 200 chars)
        from raceanalyzer.predictions import generate_narrative
        distance_km = distance_m / 1000.0 if distance_m else None
        narrative = generate_narrative(
            course_type=course_type,
            predicted_finish_type=predicted_ft if predicted_ft != "unknown" else None,
            drop_rate=dr,
            distance_km=distance_km,
            total_gain_m=total_gain_m,
            climbs=climbs_data,
            edition_count=prediction["edition_count"],
        )
        narrative_snippet = _snippet(narrative, max_sentences=2, max_chars=200)

        # Editions summary (year + finish type)
        editions = (
            session.query(Race)
            .filter(Race.series_id == series.id)
            .order_by(Race.date.desc())
            .all()
        )
        editions_summary = []
        for ed in editions:
            year = ed.date.year if ed.date else None
            ed_ft = _compute_overall_finish_type(session, ed.id)
            editions_summary.append({
                "year": year,
                "finish_type_display": finish_type_display_name(ed_ft),
            })

        item = {
            "series_id": series.id,
            "display_name": series.display_name,
            "location": most_recent.location,
            "state_province": most_recent.state_province,
            "edition_count": edition_count,
            "is_upcoming": is_upcoming,
            "is_racing_soon": is_racing_soon,
            "upcoming_date": upcoming_race.date if upcoming_race else None,
            "registration_url": upcoming_race.registration_url if upcoming_race else None,
            "most_recent_date": most_recent.date,
            "predicted_finish_type": predicted_ft if predicted_ft != "unknown" else None,
            "confidence": confidence,
            "course_type": course_type,
            "distance_m": distance_m,
            "total_gain_m": total_gain_m,
            "drop_rate_pct": drop_rate_pct,
            "drop_rate_label": drop_rate_label,
            "narrative_snippet": narrative_snippet,
            "elevation_sparkline_points": sparkline_points,
            "climb_highlight": climb_highlight(climbs_data),
            "racer_type_description": racer_desc,
            "duration_minutes": duration,
            "editions_summary": editions_summary,
        }
        items.append(item)

    # Sort: racing-soon first, then upcoming by date, then historical by recency
    def sort_key(item):
        # Tier 0: racing soon (by date asc)
        # Tier 1: upcoming (by date asc)
        # Tier 2: not upcoming (by most_recent_date desc)
        if item["is_racing_soon"]:
            tier = 0
        elif item["is_upcoming"]:
            tier = 1
        else:
            tier = 2

        date_for_sort = item["upcoming_date"] or item["most_recent_date"]
        if tier <= 1:
            # Upcoming: sort ascending (soonest first)
            return (tier, date_for_sort or datetime.max, item["display_name"])
        else:
            # Historical: sort descending (most recent first)
            # Negate by using a large date minus actual date
            epoch = datetime(1970, 1, 1)
            inv = datetime.max - (date_for_sort - epoch) if date_for_sort else datetime.min
            return (tier, inv, item["display_name"])

    items.sort(key=sort_key)
    return items


def _snippet(text: str, max_sentences: int = 2, max_chars: int = 200) -> str:
    """Extract the first N sentences from text, capped at max_chars."""
    if not text:
        return ""
    sentences = []
    remaining = text
    for _ in range(max_sentences):
        # Find sentence boundary (". " followed by uppercase or end)
        idx = remaining.find(". ")
        if idx == -1:
            sentences.append(remaining)
            break
        sentences.append(remaining[: idx + 1])
        remaining = remaining[idx + 2 :]
    result = " ".join(sentences)
    if len(result) > max_chars:
        result = result[: max_chars - 3].rstrip() + "..."
    return result


# --- Sprint 017: Feed item expansion ---


def _expand_feed_items(
    items: list[dict],
    races_by_series: dict,
    route_polyline_map: dict[int, str] | None = None,
    *,
    children_by_parent: dict[int, list[dict]] | None = None,
) -> list[dict]:
    """Expand multi-edition and stage race entries into occurrence-level feed items.

    Processing order per item:
    1. Stage races (DB children) → one item per child stage series
    2. Multi-edition (≥2 upcoming Race rows) → one item per upcoming race
    3. Passthrough → original item with occurrence_key added

    Pure Python — no DB queries. Returns new list; input list is not mutated.
    route_polyline_map maps rwgps_route_id → encoded_polyline for per-stage overrides.
    children_by_parent maps parent_series_id → list of child stage info dicts.
    """
    if route_polyline_map is None:
        route_polyline_map = {}
    if children_by_parent is None:
        children_by_parent = {}

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    expanded = []

    for item in items:
        sid = item["series_id"]
        rt = item.get("race_type")

        # 1. Stage race expansion (DB-based child series)
        db_children = children_by_parent.get(sid, [])
        if db_children and item.get("upcoming_date") is not None:
            # Compute anchor date (earliest child date) for sort grouping
            child_dates = [c["upcoming_date"] for c in db_children if c.get("upcoming_date")]
            anchor_date = min(child_dates) if child_dates else item["upcoming_date"]

            # Add group header marker (not a real card — used by feed UI)
            header = dict(item)
            header["occurrence_key"] = f"{sid}:stage_header"
            header["occurrence_kind"] = "stage_header"
            header["stage_count"] = len(db_children)
            header["stage_anchor_date"] = anchor_date
            header["parent_series_id"] = None  # header is "parent-level"
            expanded.append(header)

            for child_info in db_children:
                child = dict(item)  # inherit parent location, teammates, etc.
                # Override with child-specific data
                child["series_id"] = child_info["series_id"]
                child["parent_series_id"] = child_info["parent_series_id"]
                child["stage_number"] = child_info["stage_number"]
                child["display_name"] = child_info["display_name"]
                child["race_type"] = child_info["race_type"]
                child["discipline"] = child_info["discipline"]
                child["course_type"] = child_info["course_type"]
                child["distance_m"] = child_info["distance_m"]
                child["total_gain_m"] = child_info["total_gain_m"]
                child["elevation_sparkline_points"] = child_info["elevation_sparkline_points"]
                child["climbs_json"] = child_info["climbs_json"]
                child["rwgps_encoded_polyline"] = child_info["rwgps_encoded_polyline"]
                child["predicted_finish_type"] = child_info["predicted_finish_type"]
                child["confidence"] = child_info["confidence"]
                child["prediction_source"] = child_info["prediction_source"]
                if child_info.get("upcoming_date"):
                    child["upcoming_date"] = child_info["upcoming_date"]
                    days = (child_info["upcoming_date"] - today).days
                    child["days_until"] = days
                    child["countdown_label"] = countdown_label(days)
                    child["is_upcoming"] = days >= 0
                if child_info.get("registration_url"):
                    child["registration_url"] = child_info["registration_url"]
                child["occurrence_key"] = f"{sid}:stage:{child_info['stage_number']}"
                child["occurrence_kind"] = "stage"
                child["source_race_id"] = None
                child["stage_anchor_date"] = anchor_date
                # Override AI context with stage-specific prediction
                from raceanalyzer.predictions import build_ai_sez_text
                if child_info.get("predicted_finish_type"):
                    child["ai_context"] = {
                        "mode": "overall",
                        "selected_category": None,
                        "matched_categories": [],
                        "best_category": None,
                        "best_finish_type": child_info["predicted_finish_type"],
                        "overall_finish_type": child_info["predicted_finish_type"],
                        "prediction_source": child_info.get("prediction_source"),
                        "course_type": child_info.get("course_type"),
                        "ai_sez_text": "",
                    }
                    child["ai_context"]["ai_sez_text"] = build_ai_sez_text(
                        child["ai_context"], race_type=child_info.get("race_type"),
                    )
                else:
                    # No prediction — use race type fallback
                    child["ai_context"] = {
                        "mode": "fallback",
                        "selected_category": None,
                        "matched_categories": [],
                        "best_category": None,
                        "best_finish_type": None,
                        "overall_finish_type": None,
                        "prediction_source": None,
                        "course_type": child_info.get("course_type"),
                        "ai_sez_text": "",
                    }
                    child["ai_context"]["ai_sez_text"] = build_ai_sez_text(
                        child["ai_context"], race_type=child_info.get("race_type"),
                    )
                expanded.append(child)
            continue

        # Stage race without DB children — fall back to single card
        if rt == "stage_race" and not db_children:
            logger.debug(
                "No DB children for stage race '%s', rendering as single card",
                item.get("display_name", ""),
            )

        # 2. Multi-edition expansion
        races = races_by_series.get(sid, [])
        upcoming_races = [
            r for r in races
            if r.date and r.date >= today
        ]
        if len(upcoming_races) >= 2:
            for race in sorted(upcoming_races, key=lambda r: r.date):
                child = dict(item)
                child["display_name"] = race.name
                child["upcoming_date"] = race.date
                days = (race.date - today).days
                child["days_until"] = days
                child["countdown_label"] = countdown_label(days)
                child["is_upcoming"] = True
                child["occurrence_key"] = f"{sid}:edition:{race.id}"
                child["occurrence_kind"] = "edition"
                child["source_race_id"] = race.id
                expanded.append(child)
            continue

        # 3. Passthrough
        child = dict(item)
        child["occurrence_key"] = f"{sid}:series"
        child["occurrence_kind"] = "series"
        expanded.append(child)

    return expanded


# --- Sprint 018: Category distance & time helpers ---


def _build_cat_detail_map(
    cat_details: list,
    races_by_series: dict[int, list],
) -> dict[int, list]:
    """Map series_id -> [CategoryDetail, ...] using race_id -> series_id lookup."""
    race_to_series = {}
    for sid, races in races_by_series.items():
        for race in races:
            race_to_series[race.id] = sid

    result: dict[int, list] = {}
    for cd in cat_details:
        sid = race_to_series.get(cd.race_id)
        if sid is not None:
            result.setdefault(sid, []).append(cd)
    return result


_TIME_UNITS = {"minutes", "min", "minute", "hours", "hour", "hrs", "hr"}


def _is_time_unit(unit: str | None) -> bool:
    """Check if a distance_unit value represents time rather than distance."""
    if not unit:
        return False
    return unit.strip().lower() in _TIME_UNITS


def _normalize_category(name: str) -> str:
    """Normalize category name for matching: lowercase, collapse whitespace."""
    return " ".join(name.lower().split())


import re as _re

# Patterns for normalize_field_name
_GENDER_PATS = [
    (_re.compile(r"\bwom[ae]n'?s?\b", _re.I), "Women"),
    (_re.compile(r"\bmen'?s?\b", _re.I), "Men"),
    (_re.compile(r"\bmixed\b", _re.I), "Mixed"),
]
_MASTERS_PAT = _re.compile(
    r"\b(?:masters?|mst|mstr)\b", _re.I
)
_JUNIOR_PAT = _re.compile(
    r"\b(?:juniors?|jrs?\.?)\b", _re.I
)
_SENIOR_PAT = _re.compile(r"\bsenior\b", _re.I)
_PRO_PAT = _re.compile(r"\bpro\b", _re.I)
_CAT_LABEL_PAT = _re.compile(r"\b(?:cat(?:egory)?|categories)\b", _re.I)
# Cat levels like "1/2", "3-4", "1,2,3", "1/2/3/4/5"
_CAT_LEVELS_PAT = _re.compile(r"(?<!\d)([1-5])(?:\s*[/\-,]\s*([1-5])(?:\s*[/\-,]\s*([1-5])(?:\s*[/\-,]\s*([1-5])(?:\s*[/\-,]\s*([1-5]))?)?)?)?\b")
# Age bracket like "35+", "40-49", "35-99"
_AGE_PAT = _re.compile(r"\b(\d{2,3})\s*[\-\+]\s*(\d{2,3})?\+?(?=\s|$)")
# Noise patterns to strip
_NOISE_PATS = [
    _re.compile(r"\b(?:open|combined|overall|field)\b", _re.I),
    _re.compile(r"\(\d+(?:\.\d+)?[`']?\s*(?:miles?|mi)\)", _re.I),  # "(26.5 Miles)"
    _re.compile(r"\b\d+(?:am|pm)\b", _re.I),  # "10am", "530pm"
    _re.compile(r"\b(?:hc|road race|stage race|time trial)\b", _re.I),
]


def normalize_field_name(raw: str) -> str:
    """Normalize a category/field name into a canonical display form.

    Collapses variants like "Men Cat 1/2 Senior", "Men Senior Cat Pro/1/2",
    "Men Category 1/2" into "Men Cat 1/2".

    Rules:
    - "Senior" is stripped (it means non-masters, non-junior — the default)
    - "Pro" combined with cat levels is absorbed (Pro races with 1/2)
    - "Category" → "Cat"
    - Separators normalized: "1-2" → "1/2"
    - Word order standardized: Gender [Masters age+] Cat levels [Junior age]
    """
    s = raw.strip()
    if not s:
        return s

    # Extract gender
    gender = ""
    for pat, label in _GENDER_PATS:
        if pat.search(s):
            gender = label
            s = pat.sub("", s)
            break

    # Extract masters
    is_masters = bool(_MASTERS_PAT.search(s))
    s = _MASTERS_PAT.sub("", s)

    # Extract junior
    is_junior = bool(_JUNIOR_PAT.search(s))
    s = _JUNIOR_PAT.sub("", s)

    # Strip "Senior" (default, not informative)
    s = _SENIOR_PAT.sub("", s)

    # Strip "Pro" (absorbed into cat levels)
    s = _PRO_PAT.sub("", s)

    # Strip "Cat"/"Category" label (we'll re-add it)
    s = _CAT_LABEL_PAT.sub("", s)

    # Strip noise words
    for pat in _NOISE_PATS:
        s = pat.sub("", s)

    # Extract age bracket (e.g., "35+", "40-49")
    age_str = ""
    age_match = _AGE_PAT.search(s)
    if age_match:
        lo = age_match.group(1)
        hi = age_match.group(2)
        if hi and int(hi) >= 90:
            # "35-99" style → treat as "35+"
            age_str = f"{lo}+"
        elif hi:
            age_str = f"{lo}-{hi}"
        else:
            age_str = f"{lo}+"
        s = s[:age_match.start()] + s[age_match.end():]

    # Extract cat levels
    cat_levels = ""
    # Clean separators for level extraction
    s_clean = " ".join(s.split())
    level_match = _CAT_LEVELS_PAT.search(s_clean)
    if level_match:
        levels = [g for g in level_match.groups() if g]
        cat_levels = "/".join(levels)
        s_clean = s_clean[:level_match.start()] + s_clean[level_match.end():]

    # Build canonical form
    parts = []
    if gender:
        parts.append(gender)
    if is_masters:
        parts.append("Masters")
        if age_str:
            parts.append(age_str)
    elif is_junior:
        parts.append("Junior")
        if age_str:
            parts.append(age_str)
    if cat_levels:
        parts.append(f"Cat {cat_levels}")

    if not parts:
        # Couldn't parse — return cleaned original
        return " ".join(raw.split())

    return " ".join(parts)


def deduplicate_field_names(raw_categories: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    """Deduplicate category names by normalizing them.

    Returns:
        (canonical_list, canonical_to_raw_map)
        - canonical_list: deduplicated list of canonical field names, in order
        - canonical_to_raw_map: maps each canonical name to all raw names that
          normalize to it (for querying with any of the raw names)
    """
    canonical_to_raws: dict[str, list[str]] = {}
    seen_order: list[str] = []

    for raw in raw_categories:
        canon = normalize_field_name(raw)
        if canon not in canonical_to_raws:
            canonical_to_raws[canon] = []
            seen_order.append(canon)
        canonical_to_raws[canon].append(raw)

    return seen_order, canonical_to_raws


def _resolve_category_distance(
    cat_details: list, category: str | None
) -> tuple[float | None, str | None]:
    """Match a category to a CategoryDetail and return (distance, unit).

    Returns (None, None) if no match found.
    """
    if not category or not cat_details:
        return (None, None)

    norm_cat = _normalize_category(category)
    field_norm = normalize_field_name(category)

    # Exact match first
    for cd in cat_details:
        if cd.category == category and cd.distance is not None:
            return (cd.distance, cd.distance_unit)

    # Normalized match (simple whitespace/case)
    for cd in cat_details:
        if _normalize_category(cd.category) == norm_cat and cd.distance is not None:
            return (cd.distance, cd.distance_unit)

    # Field-name normalized match (handles Senior/Pro/Category variants)
    for cd in cat_details:
        if normalize_field_name(cd.category) == field_norm and cd.distance is not None:
            return (cd.distance, cd.distance_unit)

    return (None, None)


def _format_unit_label(unit: str | None) -> str:
    """Format a distance_unit for display."""
    if not unit:
        return "km"
    u = unit.strip().lower()
    if u in ("miles", "mile", "mi"):
        return "mi"
    if u in ("km", "kilometers", "kilometer"):
        return "km"
    if u in _TIME_UNITS:
        return "min"
    return u


def _format_distance_range(cat_details: list) -> str | None:
    """Build a display-ready distance range from CategoryDetail rows.

    Groups by unit; if all same unit, formats as range.
    If min == max, collapses to single value.
    Returns None if no data.
    """
    with_distance = [cd for cd in cat_details if cd.distance is not None]
    if not with_distance:
        return None

    # Group by unit label
    by_unit: dict[str, list[float]] = {}
    for cd in with_distance:
        label = _format_unit_label(cd.distance_unit)
        by_unit.setdefault(label, []).append(cd.distance)

    if not by_unit:
        return None

    # Pick dominant unit (most entries)
    dominant_unit = max(by_unit, key=lambda u: len(by_unit[u]))
    values = by_unit[dominant_unit]

    lo = min(values)
    hi = max(values)

    # Format as integer if whole numbers, else one decimal
    def _fmt(v: float) -> str:
        return str(int(v)) if v == int(v) else f"{v:.1f}"

    if lo == hi:
        return f"{_fmt(lo)} {dominant_unit}"
    return f"{_fmt(lo)}-{_fmt(hi)} {dominant_unit}"


def _is_duration_race(cat_details: list) -> bool:
    """Return True if any category has a time-based distance unit."""
    return any(_is_time_unit(cd.distance_unit) for cd in cat_details if cd.distance_unit)


def _format_time_range(
    pred_map: dict, series_id: int, category: str | None
) -> str | None:
    """Format estimated time from SeriesPrediction.typical_field_duration_min.

    If category is specified, return that category's time.
    Otherwise, return range across all predictions for this series.
    """
    def _fmt_duration(minutes: float) -> str:
        hours = int(minutes) // 60
        mins = int(minutes) % 60
        if hours:
            return f"~{hours}h {mins:02d}m"
        return f"~{mins}m"

    if category:
        pred = pred_map.get((series_id, category))
        if pred and pred.typical_field_duration_min:
            return _fmt_duration(pred.typical_field_duration_min)
        # Fall back to null-category prediction
        pred = pred_map.get((series_id, None))
        if pred and pred.typical_field_duration_min:
            return _fmt_duration(pred.typical_field_duration_min)
        return None

    # No category: range across all predictions for this series
    # Filter out implausibly short durations (< 30 min) — likely bad data
    _MIN_PLAUSIBLE_DURATION = 30.0
    durations = []
    for (sid, _cat), pred in pred_map.items():
        if sid == series_id and pred.typical_field_duration_min:
            if pred.typical_field_duration_min >= _MIN_PLAUSIBLE_DURATION:
                durations.append(pred.typical_field_duration_min)
    if not durations:
        return None
    lo = min(durations)
    hi = max(durations)
    if lo == hi:
        return _fmt_duration(lo)
    return f"{_fmt_duration(lo)} - {_fmt_duration(hi)}"


def build_racer_profile_label(
    cat_level: Optional[str] = None,
    gender: Optional[str] = None,
    masters_on: bool = False,
    masters_age: Optional[int] = None,
) -> str:
    """Build a human-readable label from racer profile selections.

    Examples: "Cat 3 men", "Cat 4/5 women", "Cat 3 masters 45+"
    """
    parts = []
    if cat_level:
        parts.append(f"Cat {cat_level}")
    if gender == "M":
        parts.append("men")
    elif gender == "W":
        parts.append("women")
    elif gender == "NB":
        parts.append("non-binary")
    if masters_on:
        if masters_age:
            parts.append(f"masters {masters_age}+")
        else:
            parts.append("masters")
    return " ".join(parts) if parts else ""


# --- Sprint 019: Category-aware prediction context ---

_CONFIDENCE_RANK = {"high": 3, "moderate": 2, "low": 1, None: 0}


def _prediction_sort_key(pred):
    """Deterministic ranking: edition_count then confidence."""
    return (pred.edition_count or 0, _CONFIDENCE_RANK.get(pred.confidence, 0))


def _select_feed_prediction_context(
    pred_map: dict,
    series_id: int,
    matched_categories: list[str],
    course_type: Optional[str] = None,
    racer_profile_label: str = "",
    force_overall: bool = False,
    race_type: Optional[str] = None,
) -> dict:
    """Build an ai_context dict for a feed item.

    Four modes:
    - overall: no category context
    - single_match: one matched category with a prediction
    - multi_match: multiple matched categories
    - fallback: no usable prediction rows
    """
    from raceanalyzer.predictions import build_ai_sez_text

    null_pred = pred_map.get((series_id, None))

    # Sprint 020: force_overall skips matched_categories logic entirely
    if force_overall or not matched_categories:
        # Overall mode
        pred = null_pred
        if not pred:
            # Find any prediction for this series
            for (sid, cat), p in pred_map.items():
                if sid == series_id:
                    if pred is None or _prediction_sort_key(p) > _prediction_sort_key(pred):
                        pred = p
        if pred and pred.predicted_finish_type and pred.predicted_finish_type != "unknown":
            ctx = {
                "mode": "overall",
                "selected_category": None,
                "matched_categories": [],
                "best_category": None,
                "best_finish_type": pred.predicted_finish_type,
                "overall_finish_type": pred.predicted_finish_type,
                "prediction_source": getattr(pred, "prediction_source", None),
                "course_type": course_type,
                "edition_count": getattr(pred, "edition_count", None),
                "ai_sez_text": "",
            }
            ctx["ai_sez_text"] = build_ai_sez_text(ctx, race_type=race_type)
            return ctx
        return _fallback_context(course_type=course_type)

    # Find predictions for matched categories that exist for THIS series
    cat_preds = {}
    for cat in matched_categories:
        p = pred_map.get((series_id, cat))
        if p and p.predicted_finish_type and p.predicted_finish_type != "unknown":
            cat_preds[cat] = p

    # The real set of fields the user can race in this specific event
    race_fields = sorted(cat_preds.keys())

    overall_pred = null_pred
    overall_ft = (
        overall_pred.predicted_finish_type
        if overall_pred and overall_pred.predicted_finish_type != "unknown"
        else None
    )
    overall_source = (
        getattr(overall_pred, "prediction_source", None)
        if overall_pred
        else None
    )

    if len(race_fields) == 1:
        # Single field for this race — show field-specific prediction
        cat = race_fields[0]
        pred = cat_preds[cat]
        ctx = {
            "mode": "single_match",
            "selected_category": cat,
            "matched_categories": race_fields,
            "best_category": cat,
            "best_finish_type": pred.predicted_finish_type,
            "overall_finish_type": overall_ft,
            "prediction_source": getattr(pred, "prediction_source", None),
            "course_type": course_type,
            "edition_count": getattr(pred, "edition_count", None),
            "ai_sez_text": "",
        }
        ctx["ai_sez_text"] = build_ai_sez_text(ctx, race_type=race_type)
        return ctx

    if len(race_fields) > 1:
        # Multiple fields for this race — show count + overall prediction
        best_ft = overall_ft
        best_source = overall_source
        if not best_ft:
            best_cat_pred = max(cat_preds.values(), key=_prediction_sort_key)
            best_ft = best_cat_pred.predicted_finish_type
            best_source = getattr(best_cat_pred, "prediction_source", None)

        ctx = {
            "mode": "multi_match",
            "selected_category": racer_profile_label or "",
            "matched_categories": race_fields,
            "best_category": None,
            "best_finish_type": best_ft,
            "overall_finish_type": best_ft,
            "prediction_source": best_source,
            "course_type": course_type,
            "edition_count": getattr(overall_pred, "edition_count", None) if overall_pred else None,
            "ai_sez_text": "",
        }
        ctx["ai_sez_text"] = build_ai_sez_text(ctx, race_type=race_type)
        return ctx

    # No matching fields for this race — fall back to overall
    if overall_ft:
        ctx = {
            "mode": "overall",
            "selected_category": None,
            "matched_categories": [],
            "best_category": None,
            "best_finish_type": overall_ft,
            "overall_finish_type": overall_ft,
            "prediction_source": overall_source,
            "course_type": course_type,
            "edition_count": getattr(overall_pred, "edition_count", None) if overall_pred else None,
            "ai_sez_text": "",
        }
        ctx["ai_sez_text"] = build_ai_sez_text(ctx, race_type=race_type)
        return ctx

    return _fallback_context(course_type=course_type)


def _fallback_context(
    selected_category: Optional[str] = None,
    matched_categories: Optional[list[str]] = None,
    course_type: Optional[str] = None,
) -> dict:
    """Build a fallback ai_context when no predictions exist."""
    ctx = {
        "mode": "fallback",
        "selected_category": selected_category,
        "matched_categories": matched_categories or [],
        "best_category": None,
        "best_finish_type": None,
        "overall_finish_type": None,
        "prediction_source": None,
        "course_type": course_type,
        "ai_sez_text": "",
    }
    return ctx


# --- Sprint 011: Batch feed queries ---


def get_feed_items_batch(
    session,
    *,
    category=None,
    matched_categories=None,
    racer_profile_label="",
    search_query=None,
    discipline_filter=None,
    race_type_filter=None,
    state_filter=None,
    team_name=None,
):
    """Batch-load feed items in <=6 SQL queries. Returns list[dict] with Tier 1 data."""
    from raceanalyzer.db.models import Course, SeriesPrediction

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # Query 1: Top-level series only (exclude child stage series)
    with PerfTimer("Q1: series"):
        if search_query and search_query.strip():
            matching_ids = search_series(session, search_query)
            if not matching_ids:
                return []
            series_rows = (
                session.query(RaceSeries)
                .filter(
                    RaceSeries.id.in_(matching_ids),
                    RaceSeries.parent_series_id.is_(None),
                )
                .all()
            )
        else:
            series_rows = (
                session.query(RaceSeries)
                .filter(RaceSeries.parent_series_id.is_(None))
                .all()
            )

    if not series_rows:
        return []

    # Sprint 021: Filter out old stage-named series that are superseded by
    # DB children. Find parents that have children, then exclude standalone
    # series whose name starts with the parent's name + separator.
    parent_ids_with_children = set(
        row[0] for row in
        session.query(RaceSeries.parent_series_id)
        .filter(RaceSeries.parent_series_id.isnot(None))
        .distinct()
        .all()
    )
    if parent_ids_with_children:
        parent_names = {
            s.id: s.display_name for s in series_rows
            if s.id in parent_ids_with_children
        }
        superseded_ids = set()
        for s in series_rows:
            if s.id in parent_ids_with_children:
                continue  # keep parents
            for pid, pname in parent_names.items():
                if s.id != pid and (
                    s.display_name.startswith(f"{pname}:")
                    or s.display_name.startswith(f"{pname} -")
                    or s.display_name.startswith(f"{pname} Stage")
                ):
                    superseded_ids.add(s.id)
                    break
        if superseded_ids:
            series_rows = [s for s in series_rows if s.id not in superseded_ids]
            logger.info(
                "Filtered %d superseded stage-named series from feed",
                len(superseded_ids),
            )

    series_ids = [s.id for s in series_rows]
    series_map = {s.id: s for s in series_rows}

    # Query 2: All races for these series (batch)
    with PerfTimer("Q2: races"):
        all_races = (
            session.query(Race)
            .filter(Race.series_id.in_(series_ids))
            .order_by(Race.date.desc())
            .all()
        )

    # Group races by series
    races_by_series = {}
    for race in all_races:
        races_by_series.setdefault(race.series_id, []).append(race)

    # Query 3: All courses (batch)
    with PerfTimer("Q3: courses"):
        courses = (
            session.query(Course)
            .filter(Course.series_id.in_(series_ids))
            .all()
        )
    course_map = {c.series_id: c for c in courses}

    # Query 4: Pre-computed predictions (batch) — widened for field matching
    with PerfTimer("Q4: predictions"):
        pred_query = session.query(SeriesPrediction).filter(
            SeriesPrediction.series_id.in_(series_ids)
        )
        if matched_categories:
            from sqlalchemy import or_
            pred_query = pred_query.filter(
                or_(
                    SeriesPrediction.category.in_(matched_categories),
                    SeriesPrediction.category.is_(None),
                )
            )
        elif category:
            pred_query = pred_query.filter(
                (SeriesPrediction.category == category)
                | (SeriesPrediction.category.is_(None))
            )
        predictions = pred_query.all()

    # Build prediction map: (series_id, category) -> prediction
    pred_map = {}
    for p in predictions:
        key = (p.series_id, p.category)
        pred_map[key] = p

    # Query 5: Teammate matches (if team_name set)
    teammates_map = {}
    if team_name and len(team_name.strip()) >= 3:
        with PerfTimer("Q5: teammates"):
            teammates_map = get_teammates_by_series(
                session, series_ids, category, team_name
            )

    # Query 6: Category details for distance/unit (Sprint 018)
    upcoming_race_ids = [
        r.id for races in races_by_series.values() for r in races if r.is_upcoming
    ]
    cat_detail_by_series: dict[int, list] = {}
    if upcoming_race_ids:
        with PerfTimer("Q6: category details"):
            cat_details = (
                session.query(CategoryDetail)
                .filter(CategoryDetail.race_id.in_(upcoming_race_ids))
                .all()
            )
            cat_detail_by_series = _build_cat_detail_map(cat_details, races_by_series)

    # Build most-recent-race category map (for per-series field matching)
    # Uses classifications already loaded by Q2 races — no extra query
    most_recent_race_ids = []
    _series_most_recent = {}
    for sid, races_list in races_by_series.items():
        if races_list:
            mr = races_list[0]  # already sorted desc
            most_recent_race_ids.append(mr.id)
            _series_most_recent[sid] = mr.id

    recent_cats_by_series: dict[int, set[str]] = {}
    if most_recent_race_ids:
        recent_cls = (
            session.query(RaceClassification.race_id, RaceClassification.category)
            .filter(RaceClassification.race_id.in_(most_recent_race_ids))
            .all()
        )
        # Map race_id back to series_id
        race_to_series = {rid: sid for sid, rid in _series_most_recent.items()}
        for rc in recent_cls:
            sid = race_to_series.get(rc.race_id)
            if sid and rc.category:
                recent_cats_by_series.setdefault(sid, set()).add(rc.category)

    # Build items
    items = []
    for sid in series_ids:
        series = series_map[sid]
        races = races_by_series.get(sid, [])
        if not races:
            continue

        # Find upcoming and most recent
        upcoming_race = None
        most_recent = races[0]  # already sorted desc
        for race in races:
            if race.date and race.date >= today:
                if upcoming_race is None or race.date < upcoming_race.date:
                    upcoming_race = race

        is_upcoming = upcoming_race is not None
        days_until = None
        if upcoming_race and upcoming_race.date:
            days_until = (upcoming_race.date - today).days

        # Pre-expansion filters: state only (race_type/discipline moved to post-expansion)
        race_type_val = most_recent.race_type
        disc = discipline_for_race_type(race_type_val)
        raw_st = most_recent.state_province
        norm_state = normalize_state(raw_st) if raw_st else None
        if state_filter and norm_state not in state_filter:
            continue

        # Course data (expanded for Sprint 013)
        course_row = course_map.get(sid)
        course_type = None
        distance_m = None
        total_gain_m = None
        elevation_sparkline_points = None
        climbs_json = None
        if course_row:
            course_type = (
                course_row.course_type.value if course_row.course_type else None
            )
            distance_m = course_row.distance_m
            total_gain_m = course_row.total_gain_m
            # Sparkline points (~20 downsampled) for collapsed card
            if course_row.profile_json:
                try:
                    import json as _json
                    profile = _json.loads(course_row.profile_json)
                    elevation_sparkline_points = _downsample_profile(profile, target=20)
                except (ValueError, TypeError):
                    pass
            # Climbs JSON for key climb teaser
            climbs_json = course_row.climbs_json

        # Predictions from pre-computed table
        pred = pred_map.get((sid, category)) or pred_map.get((sid, None))
        predicted_ft = pred.predicted_finish_type if pred else None
        confidence = pred.confidence if pred else None
        prediction_source = getattr(pred, "prediction_source", None) if pred else None
        drop_rate_pct = (
            round(pred.drop_rate * 100)
            if pred and pred.drop_rate is not None
            else None
        )
        drop_rate_label_val = pred.drop_rate_label if pred else None
        field_size_display = None
        if pred and pred.field_size_median:
            if (
                pred.field_size_min
                and pred.field_size_max
                and pred.field_size_min != pred.field_size_max
            ):
                field_size_display = (
                    f"Usually {pred.field_size_min}-{pred.field_size_max} starters"
                )
            else:
                field_size_display = f"Usually {pred.field_size_median} starters"

        # Teammate names
        teammate_names = teammates_map.get(sid, [])

        race_type_str = race_type_val.value if race_type_val else None

        # Sprint 013: additional Tier 1 fields
        field_size_median = pred.field_size_median if pred else None
        typical_field_duration = pred.typical_field_duration_min if pred else None
        distribution_json_val = pred.distribution_json if pred else None
        edition_count = pred.edition_count if pred else len(races)
        encoded_polyline = series.rwgps_encoded_polyline

        # Sprint 020: Always show cross-field ranges on feed (not category-specific)
        series_cat_details = cat_detail_by_series.get(sid, [])
        distance_range = _format_distance_range(series_cat_details)
        is_duration = _is_duration_race(series_cat_details)
        is_crit = race_type_str == "criterium"
        hide_est_time = is_crit or is_duration
        est_time_range = (
            None if hide_est_time
            else _format_time_range(pred_map, sid, category=None)
        )

        item = {
            "series_id": sid,
            "display_name": series.display_name,
            "location": most_recent.location,
            "state_province": most_recent.state_province,
            "edition_count": edition_count,
            "is_upcoming": is_upcoming,
            "upcoming_date": upcoming_race.date if upcoming_race else None,
            "days_until": days_until,
            "countdown_label": countdown_label(days_until),
            "registration_url": (
                upcoming_race.registration_url if upcoming_race else None
            ),
            "most_recent_date": most_recent.date,
            "race_type": race_type_str,
            "discipline": disc.value,
            "predicted_finish_type": (
                predicted_ft
                if predicted_ft and predicted_ft != "unknown"
                else None
            ),
            "confidence": confidence,
            "prediction_source": prediction_source,
            "course_type": course_type,
            "distance_m": distance_m,
            "total_gain_m": total_gain_m,
            "drop_rate_pct": drop_rate_pct,
            "drop_rate_label": drop_rate_label_val,
            "field_size_display": field_size_display,
            "field_size_median": field_size_median,
            "teammate_names": teammate_names,
            # Sprint 013 new Tier 1 fields
            "elevation_sparkline_points": elevation_sparkline_points,
            "climbs_json": climbs_json,
            "typical_field_duration_min": typical_field_duration,
            "rwgps_encoded_polyline": encoded_polyline,
            "distribution_json": distribution_json_val,
            # Sprint 020: Always cross-field ranges on feed
            "distance_range": distance_range,
            "estimated_time_range": est_time_range,
            "hide_estimated_time": hide_est_time,
        }

        # Sprint 019: Category-aware AI context
        # Scope matched categories to fields in most recent edition
        series_recent_cats = recent_cats_by_series.get(sid, set())
        scoped_matches = [
            c for c in (matched_categories or [])
            if c in series_recent_cats
        ]
        # Sprint 020: Feed always uses overall AI sez mode
        ai_context = _select_feed_prediction_context(
            pred_map, sid,
            matched_categories=scoped_matches,
            course_type=course_type,
            racer_profile_label=racer_profile_label,
            force_overall=True,
            race_type=race_type_str,
        )
        item["ai_context"] = ai_context

        items.append(item)

    # Sprint 021: Batch-load child stage series for any parent with DB children
    all_item_ids = [item["series_id"] for item in items]
    children_by_parent: dict[int, list[dict]] = {}
    if all_item_ids:
        with PerfTimer("Q7: child stage series"):
            child_series_rows = (
                session.query(RaceSeries)
                .filter(RaceSeries.parent_series_id.in_(all_item_ids))
                .order_by(RaceSeries.parent_series_id, RaceSeries.stage_number)
                .all()
            )
        child_ids = [c.id for c in child_series_rows]
        # Batch-load child courses, predictions, races
        child_courses = {}
        child_preds = {}
        child_races_map = {}
        if child_ids:
            for c in session.query(Course).filter(Course.series_id.in_(child_ids)).all():
                child_courses[c.series_id] = c
            for p in session.query(SeriesPrediction).filter(
                SeriesPrediction.series_id.in_(child_ids),
                SeriesPrediction.category.is_(None),
            ).all():
                child_preds[p.series_id] = p
            for r in session.query(Race).filter(Race.series_id.in_(child_ids)).all():
                child_races_map.setdefault(r.series_id, []).append(r)

        for child in child_series_rows:
            parent_id = child.parent_series_id
            c_course = child_courses.get(child.id)
            c_pred = child_preds.get(child.id)
            c_races = child_races_map.get(child.id, [])
            c_upcoming = next((r for r in c_races if r.is_upcoming), None)

            c_course_type = c_course.course_type.value if c_course and c_course.course_type else None
            c_distance_m = c_course.distance_m if c_course else None
            c_total_gain_m = c_course.total_gain_m if c_course else None
            c_sparkline = None
            c_climbs = None
            if c_course and c_course.profile_json:
                try:
                    import json as _json
                    profile = _json.loads(c_course.profile_json)
                    c_sparkline = _downsample_profile(profile, target=20)
                except (ValueError, TypeError):
                    pass
            if c_course:
                c_climbs = c_course.climbs_json

            c_race_type = c_upcoming.race_type.value if c_upcoming and c_upcoming.race_type else None
            c_disc = discipline_for_race_type(c_upcoming.race_type if c_upcoming else None).value

            child_info = {
                "series_id": child.id,
                "parent_series_id": parent_id,
                "stage_number": child.stage_number,
                "display_name": child.display_name,
                "race_type": c_race_type,
                "discipline": c_disc,
                "course_type": c_course_type,
                "distance_m": c_distance_m,
                "total_gain_m": c_total_gain_m,
                "elevation_sparkline_points": c_sparkline,
                "climbs_json": c_climbs,
                "rwgps_encoded_polyline": child.rwgps_encoded_polyline,
                "predicted_finish_type": (
                    c_pred.predicted_finish_type
                    if c_pred and c_pred.predicted_finish_type and c_pred.predicted_finish_type != "unknown"
                    else None
                ),
                "confidence": c_pred.confidence if c_pred else None,
                "prediction_source": getattr(c_pred, "prediction_source", None) if c_pred else None,
                "upcoming_date": c_upcoming.date if c_upcoming else None,
                "registration_url": c_upcoming.registration_url if c_upcoming else None,
            }
            children_by_parent.setdefault(parent_id, []).append(child_info)

    # Build route_id → polyline map for per-stage polyline lookups
    route_polyline_map = {
        s.rwgps_route_id: s.rwgps_encoded_polyline
        for s in series_map.values()
        if s.rwgps_route_id and s.rwgps_encoded_polyline
    }

    # Sprint 017→021: Expand multi-edition and stage race items (DB-based)
    items = _expand_feed_items(
        items, races_by_series, route_polyline_map,
        children_by_parent=children_by_parent,
    )

    # Post-expansion filters: race_type and discipline (now see expanded stage types)
    if race_type_filter or discipline_filter:
        filtered = []
        for item in items:
            rt_val = item.get("race_type")
            item_disc = discipline_for_race_type(
                RaceType(rt_val) if rt_val else None
            )
            if discipline_filter and item_disc != Discipline.UNKNOWN:
                if item_disc.value not in discipline_filter:
                    continue
            if race_type_filter and rt_val is not None:
                if rt_val not in race_type_filter:
                    continue
            filtered.append(item)
        items = filtered

    # Sort: upcoming by date asc, then historical by most_recent desc
    # Stage race children anchor at earliest child date, grouped by parent
    def sort_key(item):
        if item["is_upcoming"]:
            # Stage children: anchor to earliest sibling date, then sort by stage_number
            anchor = item.get("stage_anchor_date") or item["upcoming_date"] or datetime.max
            is_child = 1 if item.get("parent_series_id") else 0
            parent_key = item.get("parent_series_id") or item["series_id"]
            stage_num = item.get("stage_number") or 0
            return (0, anchor, is_child, parent_key, stage_num, item["display_name"])
        else:
            epoch = datetime(1970, 1, 1)
            d = item["most_recent_date"]
            inv = datetime.max - (d - epoch) if d else datetime.min
            return (1, inv, 0, 0, 0, item["display_name"])

    items.sort(key=sort_key)
    return items


def get_feed_item_detail(session, series_id, category=None):
    """Load Tier 2 detail data for a single series (on demand)."""
    import json

    from raceanalyzer.predictions import (
        calculate_drop_rate,
        calculate_typical_duration,
        generate_narrative,
        predict_series_finish_type,
        racer_type_description,
    )

    # Course data for sparkline and climbs
    course_row = session.query(Course).filter(Course.series_id == series_id).first()
    sparkline_points = []
    climbs_data = None
    course_type = None
    distance_m = None
    total_gain_m = None

    if course_row:
        course_type = (
            course_row.course_type.value if course_row.course_type else None
        )
        distance_m = course_row.distance_m
        total_gain_m = course_row.total_gain_m
        if course_row.profile_json:
            try:
                profile = json.loads(course_row.profile_json)
                sparkline_points = _downsample_profile(profile)
            except (json.JSONDecodeError, TypeError):
                pass
        if course_row.climbs_json:
            try:
                climbs_data = json.loads(course_row.climbs_json)
            except (json.JSONDecodeError, TypeError):
                pass

    # Prediction: prefer pre-computed SeriesPrediction (has prediction_source)
    from raceanalyzer.db.models import SeriesPrediction

    pred_row = (
        session.query(SeriesPrediction)
        .filter(
            SeriesPrediction.series_id == series_id,
            SeriesPrediction.category == category,
        )
        .first()
    )
    if not pred_row:
        pred_row = (
            session.query(SeriesPrediction)
            .filter(
                SeriesPrediction.series_id == series_id,
                SeriesPrediction.category.is_(None),
            )
            .first()
        )

    if pred_row:
        predicted_ft = pred_row.predicted_finish_type or "unknown"
        prediction_source = getattr(pred_row, "prediction_source", None)
        edition_count = pred_row.edition_count or 0
    else:
        prediction = predict_series_finish_type(session, series_id, category=category)
        predicted_ft = prediction["predicted_finish_type"]
        prediction_source = None
        edition_count = prediction["edition_count"]

    # Drop rate
    dr = calculate_drop_rate(session, series_id, category=category)

    # Duration
    duration = calculate_typical_duration(session, series_id, category=category)

    # Racer type description
    racer_desc = racer_type_description(course_type, predicted_ft)

    # Narrative
    distance_km = distance_m / 1000.0 if distance_m else None
    narrative = generate_narrative(
        course_type=course_type,
        predicted_finish_type=predicted_ft if predicted_ft != "unknown" else None,
        drop_rate=dr,
        distance_km=distance_km,
        total_gain_m=total_gain_m,
        climbs=climbs_data,
        edition_count=edition_count,
        prediction_source=prediction_source,
    )
    narrative_snippet = _snippet(narrative, max_sentences=2, max_chars=200)

    # Editions summary
    editions = (
        session.query(Race)
        .filter(Race.series_id == series_id)
        .order_by(Race.date.desc())
        .all()
    )
    editions_summary = []
    for ed in editions:
        year = ed.date.year if ed.date else None
        ed_ft = _compute_overall_finish_type(session, ed.id)
        editions_summary.append(
            {
                "year": year,
                "finish_type": ed_ft,
                "finish_type_display": finish_type_display_name(ed_ft),
            }
        )

    return {
        "narrative_snippet": narrative_snippet,
        "narrative": narrative,
        "elevation_sparkline_points": sparkline_points,
        "climb_highlight": climb_highlight(climbs_data),
        "racer_type_description": racer_desc,
        "duration_minutes": duration,
        "editions_summary": editions_summary,
    }


def get_teammates_by_series(session, series_ids, category, team_name):
    """Find teammates across multiple series by team name substring match."""
    from raceanalyzer.db.models import Startlist

    if not team_name or len(team_name.strip()) < 3:
        return {}
    normalized = team_name.strip()
    query = session.query(Startlist.series_id, Startlist.rider_name).filter(
        Startlist.series_id.in_(series_ids),
        func.lower(Startlist.team).contains(normalized.lower()),
    )
    if category:
        query = query.filter(Startlist.category == category)

    result = {}
    for sid, name in query.all():
        result.setdefault(sid, []).append(name)
    return result


def compute_similarity(series_a, series_b):
    """Score similarity between two series (0-100)."""
    score = 0.0
    if series_a.get("course_type") and series_a["course_type"] == series_b.get(
        "course_type"
    ):
        score += 40
    if series_a.get("predicted_finish_type") and series_a[
        "predicted_finish_type"
    ] == series_b.get("predicted_finish_type"):
        score += 30
    da, db = series_a.get("distance_m"), series_b.get("distance_m")
    if da and db and da > 0 and db > 0:
        ratio = min(da, db) / max(da, db)
        if ratio > 0.75:
            score += 20 * ((ratio - 0.75) / 0.25)
    if series_a.get("discipline") and series_a["discipline"] == series_b.get(
        "discipline"
    ):
        score += 10
    return score


def get_latest_race_for_series(session: Session, series_id: int) -> Optional[Race]:
    """Return the most recent Race row for a series, or None."""
    return (
        session.query(Race)
        .filter(Race.series_id == series_id)
        .order_by(Race.date.desc())
        .first()
    )


def get_similar_series(session, series_id, all_items=None, top_n=3, min_score=50):
    """Find similar series to the given one."""
    if all_items is None:
        all_items = get_feed_items_batch(session)

    target = None
    candidates = []
    for item in all_items:
        if item["series_id"] == series_id:
            target = item
        else:
            candidates.append(item)

    if target is None:
        return []

    scored = []
    for c in candidates:
        s = compute_similarity(target, c)
        if s >= min_score:
            scored.append((s, c))

    scored.sort(key=lambda x: -x[0])
    return [(score, item) for score, item in scored[:top_n]]


def get_startlist_team_blocks(session, series_id, category=None, categories=None, team_name=None):
    """Get startlist grouped by team for a series.

    Args:
        category: Single category name (exact match).
        categories: List of category name variants to match (any of them).
        When both are None (All Fields mode), includes category info per rider
        and deduplicates riders registered for multiple fields.
    """
    from raceanalyzer.db.models import Startlist

    query = session.query(Startlist).filter(Startlist.series_id == series_id)
    if categories:
        query = query.filter(Startlist.category.in_(categories))
    elif category:
        query = query.filter(Startlist.category == category)
    entries = query.all()

    if not entries:
        return []

    # Group by team, dedup riders by name within each team
    teams: dict[str, dict[str, dict]] = {}  # team -> {rider_name -> rider_info}
    for e in entries:
        team = e.team or "Unattached"
        rider_name = e.rider_name
        team_riders = teams.setdefault(team, {})
        if rider_name not in team_riders:
            team_riders[rider_name] = {
                "name": rider_name,
                "categories": [],
            }
        if e.category:
            cats = team_riders[rider_name]["categories"]
            if e.category not in cats:
                cats.append(e.category)

    # Build blocks; count = unique riders, not registrations
    is_all_categories = category is None and categories is None
    blocks = []
    for team_name_val, riders_dict in sorted(teams.items(), key=lambda x: -len(x[1])):
        riders = list(riders_dict.values())
        if is_all_categories:
            # Sort by first category name for grouping
            riders.sort(key=lambda r: (r["categories"][0] if r["categories"] else ""))
        blocks.append(
            {
                "team": team_name_val,
                "riders": riders,
                "count": len(riders),
                "show_categories": is_all_categories,
            }
        )

    return blocks
