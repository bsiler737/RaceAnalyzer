"""Baseline heuristic predictions. Every future model must beat these."""

from __future__ import annotations

from collections import Counter
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from raceanalyzer.db.models import (
    Race,
    RaceClassification,
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
    """Tier 1: Rank startlist riders by carried_points."""
    rows = []
    for entry in entries:
        # Look up best carried_points for this rider
        best_points = 0.0
        wins = 0
        last_raced = None
        team = entry.team or ""

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
                if r.carried_points and r.carried_points > best_points:
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
        if r.carried_points and r.carried_points > stats["carried_points"]:
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
        if r.carried_points and r.carried_points > stats["carried_points"]:
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
