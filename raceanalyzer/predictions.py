"""Baseline heuristic predictions. Every future model must beat these."""

from __future__ import annotations

import statistics
from collections import Counter
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from raceanalyzer.config import Settings
from raceanalyzer.db.models import (
    Course,
    Race,
    RaceClassification,
    RaceType,
    Result,
    Startlist,
)


def predict_series_finish_type(
    session: Session,
    series_id: int,
    category: Optional[str] = None,
) -> dict:
    """Predict finish type for next edition of a series.

    Algorithm: weighted frequency of historical finish types for this series.
    Recent 2 editions weighted 2x. If category provided, filter to that
    category; otherwise use all categories.

    Returns: {
        "predicted_finish_type": FinishType value string,
        "confidence": "high" | "moderate" | "low",
        "edition_count": int,
        "distribution": dict[str, int],
    }
    """
    # Get all editions ordered by date descending
    editions = (
        session.query(Race)
        .filter(Race.series_id == series_id)
        .order_by(Race.date.desc())
        .all()
    )

    if not editions:
        return {
            "predicted_finish_type": "unknown",
            "confidence": "low",
            "edition_count": 0,
            "distribution": {},
        }

    # Get classifications for these editions
    edition_ids = [e.id for e in editions]
    query = session.query(RaceClassification).filter(
        RaceClassification.race_id.in_(edition_ids)
    )
    if category:
        query = query.filter(RaceClassification.category == category)

    classifications = query.all()

    if not classifications:
        return {
            "predicted_finish_type": "unknown",
            "confidence": "low",
            "edition_count": len(editions),
            "distribution": {},
        }

    # Build race_id -> edition index (0 = most recent)
    edition_index = {e.id: i for i, e in enumerate(editions)}

    # Weighted count: recent 2 editions get 2x weight
    weighted_counts: Counter = Counter()
    for cls in classifications:
        ft = cls.finish_type.value if cls.finish_type else "unknown"
        if ft == "unknown":
            continue
        idx = edition_index.get(cls.race_id, 999)
        weight = 2 if idx < 2 else 1
        weighted_counts[ft] += weight

    if not weighted_counts:
        return {
            "predicted_finish_type": "unknown",
            "confidence": "low",
            "edition_count": len(editions),
            "distribution": {},
        }

    # Raw (unweighted) distribution for reporting
    raw_counts: Counter = Counter()
    for cls in classifications:
        ft = cls.finish_type.value if cls.finish_type else "unknown"
        if ft != "unknown":
            raw_counts[ft] += 1

    # Prediction = highest weighted count
    predicted = weighted_counts.most_common(1)[0][0]

    # Confidence based on edition count and plurality
    total_weighted = sum(weighted_counts.values())
    plurality = weighted_counts[predicted] / total_weighted if total_weighted > 0 else 0

    # Count distinct editions that have classifications
    editions_with_data = len(set(cls.race_id for cls in classifications))

    if editions_with_data >= 4 and plurality > 0.6:
        confidence = "high"
    elif editions_with_data >= 2 and plurality >= 0.4:
        confidence = "moderate"
    else:
        confidence = "low"

    return {
        "predicted_finish_type": predicted,
        "confidence": confidence,
        "edition_count": editions_with_data,
        "distribution": dict(raw_counts),
    }


def predict_contenders(
    session: Session,
    series_id: int,
    category: str,
    *,
    top_n: int = 10,
) -> pd.DataFrame:
    """Rank likely top finishers for an upcoming race.

    Three-tier graceful degradation:
    1. If startlist exists for this series+category: rank registered riders
       by carried_points percentile.
    2. Else, find riders who've raced this series before in this category,
       ranked by max carried_points.
    3. Else, find top carried_points riders in this category regionwide.

    Columns: name, team, carried_points, source, wins_in_series, last_raced.
    """
    # Tier 1: Check startlist
    startlist_entries = (
        session.query(Startlist)
        .filter(
            Startlist.series_id == series_id,
            Startlist.category == category,
        )
        .all()
    )

    if startlist_entries:
        return _rank_from_startlist(session, startlist_entries, series_id, category, top_n)

    # Tier 2: Historical performers for this series
    result = _rank_from_series_history(session, series_id, category, top_n)
    if not result.empty:
        return result

    # Tier 3: Category-wide top riders
    return _rank_from_category(session, category, top_n)


def _rank_from_startlist(
    session: Session,
    entries: list,
    series_id: int,
    category: str,
    top_n: int,
) -> pd.DataFrame:
    """Tier 1: Rank startlist riders by carried_points.

    When ``entry.carried_points`` is set (from road-results predictor), use it
    directly. Fall back to historical Result lookup only when it is None.
    """
    rows = []
    for entry in entries:
        wins = 0
        last_raced = None
        team = entry.team or ""

        # Prefer inline carried_points from Startlist (road-results predictor)
        if getattr(entry, "carried_points", None) is not None:
            best_points = entry.carried_points
        else:
            best_points = 0.0

        if entry.rider_id:
            rider_results = (
                session.query(Result)
                .filter(
                    Result.rider_id == entry.rider_id,
                    Result.race_category_name == category,
                    Result.dnf.is_(False),
                )
                .all()
            )
            for r in rider_results:
                # Only look up historical points if startlist didn't provide them
                if getattr(entry, "carried_points", None) is None:
                    if r.carried_points is not None and r.carried_points > best_points:
                        best_points = r.carried_points
                if r.place == 1:
                    wins += 1
                if r.team:
                    team = r.team
                race = session.get(Race, r.race_id)
                if race and race.date:
                    if last_raced is None or race.date > last_raced:
                        last_raced = race.date

        rows.append({
            "name": entry.rider_name,
            "team": team,
            "carried_points": best_points,
            "source": "startlist",
            "wins_in_series": wins,
            "last_raced": last_raced,
        })

    df = pd.DataFrame(rows)
    return df.sort_values("carried_points", ascending=False).head(top_n).reset_index(drop=True)


def _rank_from_series_history(
    session: Session,
    series_id: int,
    category: str,
    top_n: int,
) -> pd.DataFrame:
    """Tier 2: Rank riders from past editions of this series."""
    # Get race IDs for this series
    race_ids = [
        r.id
        for r in session.query(Race.id).filter(Race.series_id == series_id).all()
    ]

    if not race_ids:
        return pd.DataFrame(
            columns=["name", "team", "carried_points", "source", "wins_in_series", "last_raced"]
        )

    results = (
        session.query(Result)
        .filter(
            Result.race_id.in_(race_ids),
            Result.race_category_name == category,
            Result.rider_id.isnot(None),
            Result.dnf.is_(False),
        )
        .all()
    )

    if not results:
        return pd.DataFrame(
            columns=["name", "team", "carried_points", "source", "wins_in_series", "last_raced"]
        )

    rider_stats: dict[int, dict] = {}
    for r in results:
        if r.rider_id not in rider_stats:
            rider_stats[r.rider_id] = {
                "name": r.name,
                "team": r.team or "",
                "carried_points": 0.0,
                "wins_in_series": 0,
                "last_raced": None,
            }
        stats = rider_stats[r.rider_id]
        if r.carried_points is not None and r.carried_points > stats["carried_points"]:
            stats["carried_points"] = r.carried_points
        if r.team:
            stats["team"] = r.team
        stats["name"] = r.name
        if r.place == 1:
            stats["wins_in_series"] += 1
        race = session.get(Race, r.race_id)
        if race and race.date:
            if stats["last_raced"] is None or race.date > stats["last_raced"]:
                stats["last_raced"] = race.date

    rows = [
        {**v, "source": "series_history"}
        for v in rider_stats.values()
    ]
    df = pd.DataFrame(rows)
    return df.sort_values("carried_points", ascending=False).head(top_n).reset_index(drop=True)


def _rank_from_category(
    session: Session,
    category: str,
    top_n: int,
) -> pd.DataFrame:
    """Tier 3: Top carried_points riders in this category regionwide."""
    results = (
        session.query(Result)
        .filter(
            Result.race_category_name == category,
            Result.rider_id.isnot(None),
            Result.dnf.is_(False),
            Result.carried_points.isnot(None),
        )
        .all()
    )

    if not results:
        return pd.DataFrame(
            columns=["name", "team", "carried_points", "source", "wins_in_series", "last_raced"]
        )

    rider_stats: dict[int, dict] = {}
    for r in results:
        if r.rider_id not in rider_stats:
            rider_stats[r.rider_id] = {
                "name": r.name,
                "team": r.team or "",
                "carried_points": 0.0,
                "wins_in_series": 0,
                "last_raced": None,
            }
        stats = rider_stats[r.rider_id]
        if r.carried_points is not None and r.carried_points > stats["carried_points"]:
            stats["carried_points"] = r.carried_points
        if r.team:
            stats["team"] = r.team
        stats["name"] = r.name
        if r.place == 1:
            stats["wins_in_series"] += 1
        race = session.get(Race, r.race_id)
        if race and race.date:
            if stats["last_raced"] is None or race.date > stats["last_raced"]:
                stats["last_raced"] = race.date

    rows = [
        {**v, "source": "category"}
        for v in rider_stats.values()
    ]
    df = pd.DataFrame(rows)
    return df.sort_values("carried_points", ascending=False).head(top_n).reset_index(drop=True)


# --- Historical stats ---


def calculate_drop_rate(
    session: Session,
    series_id: int,
    category: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> Optional[dict]:
    """Calculate historical attrition rate (DNF + DNP only; excludes DQ).

    Returns median drop rate across editions with label and confidence.
    Returns None if no historical data.
    """
    if settings is None:
        settings = Settings()

    editions = (
        session.query(Race)
        .filter(Race.series_id == series_id)
        .order_by(Race.date.desc())
        .all()
    )
    if not editions:
        return None

    per_edition_rates = []
    total_starters = 0
    total_dropped = 0

    for race in editions:
        query = session.query(Result).filter(Result.race_id == race.id)
        if category:
            query = query.filter(Result.race_category_name == category)
        results = query.all()

        if not results:
            continue

        starters = len(results)
        dropped = sum(1 for r in results if r.dnf or r.dnp)
        total_starters += starters
        total_dropped += dropped

        if starters > 0:
            per_edition_rates.append(dropped / starters)

    if not per_edition_rates:
        return None

    drop_rate = statistics.median(per_edition_rates)

    # Label mapping
    if drop_rate < settings.drop_rate_low_max:
        label = "low"
    elif drop_rate < settings.drop_rate_moderate_max:
        label = "moderate"
    elif drop_rate < settings.drop_rate_high_max:
        label = "high"
    else:
        label = "extreme"

    # Confidence
    editions_with_data = len(per_edition_rates)
    min_starters = min(
        len([r for r in session.query(Result).filter(Result.race_id == e.id).all()])
        for e in editions
        if session.query(Result).filter(Result.race_id == e.id).count() > 0
    ) if editions_with_data > 0 else 0

    if editions_with_data >= 3 and min_starters >= 10:
        confidence = "high"
    elif editions_with_data >= 2:
        confidence = "moderate"
    else:
        confidence = "low"

    return {
        "drop_rate": round(drop_rate, 3),
        "total_starters": total_starters,
        "total_dropped": total_dropped,
        "edition_count": editions_with_data,
        "label": label,
        "confidence": confidence,
    }


def calculate_typical_speeds(
    session: Session,
    series_id: int,
    category: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> Optional[dict]:
    """Calculate historical finishing speeds.

    Suppressed for criteriums (single-lap distance unreliable).
    Returns None if distance, timing data, or race type makes speed unreliable.
    """
    if settings is None:
        settings = Settings()

    # Get course distance
    course = (
        session.query(Course)
        .filter(Course.series_id == series_id)
        .first()
    )
    if not course or not course.distance_m:
        return None

    distance_m = course.distance_m

    # Check race type - suppress for criteriums
    editions = (
        session.query(Race)
        .filter(Race.series_id == series_id)
        .order_by(Race.date.desc())
        .all()
    )
    if not editions:
        return None

    # If any edition is a criterium, suppress
    for race in editions:
        if race.race_type == RaceType.CRITERIUM:
            return None

    # Suppress for very short non-crit courses (likely single lap)
    if distance_m < 5000:
        return None

    per_edition_winner_speeds = []
    per_edition_field_speeds = []

    for race in editions:
        query = (
            session.query(Result)
            .filter(
                Result.race_id == race.id,
                Result.dnf.is_(False),
                Result.dnp.is_(False),
                Result.dq.is_(False),
                Result.race_time_seconds.isnot(None),
            )
        )
        if category:
            query = query.filter(Result.race_category_name == category)

        results = query.order_by(Result.place).all()

        # Check if enough results have timing
        total_results_query = session.query(Result).filter(
            Result.race_id == race.id,
            Result.dnf.is_(False),
        )
        if category:
            total_results_query = total_results_query.filter(
                Result.race_category_name == category
            )
        total_count = total_results_query.count()
        timed_count = len(results)

        if total_count == 0 or timed_count / total_count < 0.5:
            continue

        if not results:
            continue

        # Front group proxy: top K finishers
        top_k = results[:settings.speed_top_k]
        speeds = []
        for r in top_k:
            if r.race_time_seconds and r.race_time_seconds > 0:
                speed_kph = distance_m / r.race_time_seconds * 3.6
                if settings.speed_min_kph <= speed_kph <= settings.speed_max_kph:
                    speeds.append(speed_kph)

        if speeds:
            per_edition_winner_speeds.append(speeds[0])  # fastest
            per_edition_field_speeds.append(statistics.median(speeds))

    if not per_edition_winner_speeds:
        return None

    median_winner_kph = statistics.median(per_edition_winner_speeds)
    median_field_kph = statistics.median(per_edition_field_speeds)

    # Confidence
    editions_with_data = len(per_edition_winner_speeds)
    if editions_with_data >= 3:
        confidence = "high"
    elif editions_with_data >= 2:
        confidence = "moderate"
    else:
        confidence = "low"

    return {
        "median_winner_speed_mph": round(median_winner_kph * 0.621371, 1),
        "median_field_speed_mph": round(median_field_kph * 0.621371, 1),
        "median_winner_speed_kph": round(median_winner_kph, 1),
        "median_field_speed_kph": round(median_field_kph, 1),
        "edition_count": editions_with_data,
        "confidence": confidence,
    }


# --- Narrative generator ---


def generate_narrative(
    course_type: Optional[str] = None,
    predicted_finish_type: Optional[str] = None,
    drop_rate: Optional[dict] = None,
    typical_speed: Optional[dict] = None,
    distance_km: Optional[float] = None,
    total_gain_m: Optional[float] = None,
    climbs: Optional[list] = None,
    edition_count: int = 0,
) -> str:
    """Generate a template-based 'What to Expect' narrative.

    Each sentence is independently optional based on data availability.
    Returns 1-5 sentences of plain English.
    """
    sentences = []

    # 1. Course sentence
    if distance_km is not None and course_type:
        dist_str = f"{distance_km:.0f}" if distance_km >= 10 else f"{distance_km:.1f}"
        if course_type == "flat":
            sentences.append(
                f"This {dist_str} km flat course has minimal climbing"
                " — positioning and pack tactics matter more than raw power."
            )
        elif course_type == "rolling":
            gain_str = f" with {total_gain_m:.0f}m of climbing" if total_gain_m else ""
            sentences.append(
                f"This {dist_str} km rolling course{gain_str}"
                " rewards strong all-rounders and punchy riders."
            )
        elif course_type == "hilly":
            n_climbs = len(climbs) if climbs else 0
            climb_phrase = (
                f" across {n_climbs} significant climb"
                + ("s" if n_climbs != 1 else "")
                if n_climbs
                else ""
            )
            gain_str = f"{total_gain_m:.0f}m" if total_gain_m else "significant"
            sentences.append(
                f"This {dist_str} km course packs"
                f" {gain_str} of climbing{climb_phrase}."
            )
        elif course_type == "mountainous":
            gain_str = f"{total_gain_m:.0f}m" if total_gain_m else "massive"
            sentences.append(
                f"This {dist_str} km mountain course packs"
                f" {gain_str} of climbing"
                " — expect the field to shatter on the climbs."
            )

    # 2. Climb sentence (highlight hardest or last significant climb)
    if climbs:
        hardest = max(climbs, key=lambda c: c.get("avg_grade", 0))
        length_str = f"{hardest['length_m']:.0f}m"
        grade_str = f"{hardest['avg_grade']:.0f}%"
        cat = hardest.get("category", "")
        # Check if it's in the final quarter
        if distance_km and hardest.get("end_d"):
            total_m = distance_km * 1000
            if hardest["end_d"] > total_m * 0.75:
                sentences.append(
                    f"The hardest climb is a {length_str} {cat} effort"
                    f" averaging {grade_str}"
                    " — and it comes in the final quarter of the race."
                )
            else:
                sentences.append(
                    f"The hardest climb is a {length_str} {cat} effort"
                    f" averaging {grade_str}."
                )
        else:
            sentences.append(
                f"The hardest climb is a {length_str} {cat} effort"
                f" averaging {grade_str}."
            )

    # 3. History sentence
    if predicted_finish_type and edition_count > 0:
        from raceanalyzer.queries import finish_type_display_name

        ft_name = finish_type_display_name(predicted_finish_type).lower()
        sentences.append(
            f"Based on {edition_count} previous"
            f" edition{'s' if edition_count != 1 else ''},"
            f" this race typically ends in a {ft_name}."
        )

    if drop_rate:
        rate_pct = round(drop_rate["drop_rate"] * 100)
        if rate_pct < 15:
            qualifier = "fairly typical"
        elif rate_pct < 30:
            qualifier = "moderately selective"
        elif rate_pct < 45:
            qualifier = "quite selective"
        else:
            qualifier = "brutally selective"
        sentences.append(
            f"Historically {rate_pct}% of starters are dropped or DNF"
            f" — {qualifier} for the category."
        )

    # 4. Pacing sentence
    if typical_speed:
        mph = typical_speed["median_winner_speed_mph"]
        kph = typical_speed["median_winner_speed_kph"]
        sentences.append(
            f"The winning group usually averages around"
            f" {mph} mph ({kph} kph)."
        )

    # 5. Caveat
    if edition_count == 1:
        sentences.append(
            "Based on limited history (1 edition)"
            " — take these numbers with a grain of salt."
        )

    if not sentences:
        return (
            "This is a new event"
            " — no historical data is available yet."
        )

    return " ".join(sentences)


# --- Racer type description (Sprint 010) ---

RACER_TYPE_DESCRIPTIONS: dict[tuple[str, str], str] = {
    ("flat", "bunch_sprint"): "Sprinters and pack riders thrive here.",
    ("flat", "breakaway"): "Strong riders who can sustain a solo effort have an edge.",
    ("flat", "small_group_sprint"): "Fast finishers who can follow moves do well.",
    ("flat", "reduced_sprint"): "All-rounders with a strong kick have the advantage.",
    ("rolling", "bunch_sprint"): "Riders who can handle surges and still sprint do well.",
    ("rolling", "reduced_sprint"): "Punchy riders who can handle repeated surges do well.",
    ("rolling", "breakaway"): "Strong all-rounders who can attack on the hills thrive.",
    ("rolling", "small_group_sprint"): "Tactical riders who can bridge gaps excel here.",
    ("hilly", "breakaway"): "Pure climbers and aggressive attackers dominate.",
    ("hilly", "gc_selective"): "Pure climbers dominate this race.",
    ("hilly", "reduced_sprint"): "Climbers with a finishing kick do well.",
    ("mountainous", "gc_selective"): "Only the strongest climbers survive this race.",
}


def racer_type_description(
    course_type: Optional[str], finish_type: Optional[str]
) -> Optional[str]:
    """Return a sentence describing what kind of racer does well.

    Returns None if the combination isn't in the lookup table.
    """
    if not course_type or not finish_type:
        return None
    return RACER_TYPE_DESCRIPTIONS.get((course_type, finish_type))


def racer_type_long_form(
    course_type: Optional[str],
    finish_type: Optional[str],
    drop_rate: Optional[dict] = None,
    edition_count: int = 0,
) -> Optional[str]:
    """Expanded racer type paragraph with course-specific reasoning."""
    short = racer_type_description(course_type, finish_type)
    if not short:
        # Fallback: generate from components
        if not course_type or not finish_type:
            return None
        short = "This race suits versatile riders."

    parts = [short]

    # Add historical context
    if edition_count >= 3:
        parts.append(
            f"This pattern has held across {edition_count} previous editions."
        )
    elif edition_count >= 1:
        parts.append(
            f"Based on {edition_count} previous edition{'s' if edition_count != 1 else ''}"
            " — the pattern may evolve."
        )

    # Add drop rate context
    if drop_rate:
        rate_pct = round(drop_rate["drop_rate"] * 100)
        if rate_pct >= 30:
            parts.append(
                f"With a {rate_pct}% drop rate, fitness is non-negotiable"
                " — expect to be tested."
            )
        elif rate_pct >= 15:
            parts.append(
                f"The {rate_pct}% drop rate suggests the race is moderately selective."
            )

    return " ".join(parts)


def climb_context_line(
    climb: dict,
    total_distance_m: Optional[float] = None,
    finish_type: Optional[str] = None,
    drop_rate: Optional[dict] = None,
) -> str:
    """Generate a hedged race-context narrative for a single climb."""
    parts = []
    start_km = climb.get("start_d", 0) / 1000.0
    length_km = climb.get("length_m", 0) / 1000.0
    avg_grade = climb.get("avg_grade", 0)
    max_grade = climb.get("max_grade", 0)

    # Basic stats
    end_km = start_km + length_km
    stats = f"Km {start_km:.0f}\u2013{end_km:.0f}: {length_km:.1f} km at {avg_grade:.1f}% avg"
    if max_grade and max_grade > avg_grade + 2:
        stats += f" (max {max_grade:.0f}%)"
    parts.append(stats)

    # Race context (hedged language)
    if total_distance_m and total_distance_m > 0:
        position_ratio = climb.get("start_d", 0) / total_distance_m
        is_late = position_ratio > 0.6

        selective_types = {"gc_selective", "breakaway_selective", "breakaway"}
        sprint_types = {"bunch_sprint", "small_group_sprint", "reduced_sprint"}
        high_drop = drop_rate and drop_rate.get("drop_rate", 0) >= 0.25

        if is_late and finish_type in selective_types:
            parts.append("Likely where the field splits.")
        elif is_late and high_drop:
            parts.append("This climb sheds riders.")
        elif not is_late and avg_grade < 5 and finish_type in sprint_types:
            parts.append("Unlikely to be decisive.")
        elif is_late and avg_grade >= 6:
            parts.append("Could be where the selection happens.")
        elif high_drop:
            parts.append("This climb sheds riders.")

    return " — ".join(parts)


def calculate_typical_duration(
    session: Session,
    series_id: int,
    category: Optional[str] = None,
) -> Optional[dict]:
    """Calculate typical race duration from historical Results.

    Uses race_time_seconds directly. Suppressed for time trials.
    Returns None if insufficient data.
    """
    editions = (
        session.query(Race)
        .filter(Race.series_id == series_id)
        .order_by(Race.date.desc())
        .all()
    )
    if not editions:
        return None

    # Suppress for TTs
    for race in editions:
        if race.race_type == RaceType.TIME_TRIAL:
            return None

    per_edition_winner = []
    per_edition_field = []

    for race in editions:
        query = (
            session.query(Result)
            .filter(
                Result.race_id == race.id,
                Result.dnf.is_(False),
                Result.dnp.is_(False),
                Result.dq.is_(False),
                Result.race_time_seconds.isnot(None),
            )
        )
        if category:
            query = query.filter(Result.race_category_name == category)

        results = query.order_by(Result.place).all()
        if not results:
            continue

        times = [
            r.race_time_seconds for r in results
            if r.race_time_seconds and r.race_time_seconds > 0
        ]
        if not times:
            continue

        per_edition_winner.append(times[0] / 60.0)  # minutes
        per_edition_field.append(statistics.median(times) / 60.0)

    if not per_edition_winner:
        return None

    return {
        "winner_duration_minutes": round(statistics.median(per_edition_winner), 1),
        "field_duration_minutes": round(statistics.median(per_edition_field), 1),
        "edition_count": len(per_edition_winner),
    }
