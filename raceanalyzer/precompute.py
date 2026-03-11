"""Pre-computation pipeline for series predictions (Sprint 011 PF-04)."""

from __future__ import annotations

import json
import logging
import statistics
from typing import Optional

from sqlalchemy.orm import Session

from raceanalyzer.db.models import (
    Race,
    RaceSeries,
    Result,
    SeriesPrediction,
)
from raceanalyzer.predictions import (
    calculate_drop_rate,
    calculate_typical_duration,
    predict_series_finish_type,
)

logger = logging.getLogger("raceanalyzer")


def _calculate_field_size(
    session: Session, series_id: int, category: Optional[str] = None
) -> dict:
    """Calculate field size statistics for a series."""
    editions = (
        session.query(Race)
        .filter(Race.series_id == series_id)
        .order_by(Race.date.desc())
        .all()
    )
    if not editions:
        return {"median": None, "min": None, "max": None}

    sizes = []
    for race in editions:
        query = session.query(Result).filter(Result.race_id == race.id)
        if category:
            query = query.filter(Result.race_category_name == category)
        count = query.count()
        if count > 0:
            sizes.append(count)

    if not sizes:
        return {"median": None, "min": None, "max": None}

    return {
        "median": int(statistics.median(sizes)),
        "min": min(sizes),
        "max": max(sizes),
    }


def precompute_series_predictions(
    session: Session,
    series_id: int,
    categories: Optional[list[str]] = None,
) -> int:
    """Pre-compute predictions for a single series across categories.

    Returns number of predictions created/updated.
    """
    from datetime import datetime

    from raceanalyzer.db.models import RaceClassification

    if categories is None:
        # Get categories from this series' classifications
        cats = (
            session.query(RaceClassification.category)
            .join(Race)
            .filter(Race.series_id == series_id)
            .distinct()
            .all()
        )
        categories = [c[0] for c in cats if c[0]]

    # Always compute for None (overall) + each category
    cat_list = [None] + categories
    count = 0

    for cat in cat_list:
        prediction = predict_series_finish_type(session, series_id, category=cat)
        dr = calculate_drop_rate(session, series_id, category=cat)
        duration = calculate_typical_duration(session, series_id, category=cat)
        field_size = _calculate_field_size(session, series_id, category=cat)

        # Upsert
        existing = (
            session.query(SeriesPrediction)
            .filter(
                SeriesPrediction.series_id == series_id,
                SeriesPrediction.category == cat,
            )
            .first()
        )

        if existing:
            row = existing
        else:
            row = SeriesPrediction(series_id=series_id, category=cat)
            session.add(row)

        row.predicted_finish_type = prediction["predicted_finish_type"]
        row.confidence = prediction["confidence"]
        row.edition_count = prediction["edition_count"]
        row.distribution_json = (
            json.dumps(prediction["distribution"])
            if prediction["distribution"]
            else None
        )
        row.drop_rate = dr["drop_rate"] if dr else None
        row.drop_rate_label = dr["label"] if dr else None
        row.typical_winner_duration_min = (
            duration["winner_duration_minutes"] if duration else None
        )
        row.typical_field_duration_min = (
            duration["field_duration_minutes"] if duration else None
        )
        row.field_size_median = field_size["median"]
        row.field_size_min = field_size["min"]
        row.field_size_max = field_size["max"]
        row.last_computed = datetime.utcnow()

        count += 1

    return count


def precompute_all(session: Session) -> dict:
    """Pre-compute predictions for all series. Returns summary stats."""
    series_list = session.query(RaceSeries).all()
    total_predictions = 0
    series_count = 0

    for series in series_list:
        n = precompute_series_predictions(session, series.id)
        total_predictions += n
        series_count += 1
        if series_count % 10 == 0:
            logger.info("Computed %d/%d series...", series_count, len(series_list))

    session.commit()
    return {
        "series_count": series_count,
        "predictions_count": total_predictions,
    }
