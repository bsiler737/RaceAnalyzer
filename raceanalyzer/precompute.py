"""Pre-computation pipeline for series predictions (Sprint 011 PF-04, Sprint 012 CP)."""

from __future__ import annotations

import json
import logging
import statistics
from collections import Counter
from typing import Optional

from sqlalchemy.orm import Session

from raceanalyzer.classification.course_predictor import predict_finish_type_from_course
from raceanalyzer.db.models import (
    Course,
    Race,
    RaceClassification,
    RaceSeries,
    RaceType,
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


def _confidence_label(numeric_conf: float) -> str:
    """Convert numeric confidence to label. Course-based caps at 'moderate'."""
    if numeric_conf >= 0.65:
        return "moderate"
    return "low"


def _get_series_race_type(session: Session, series_id: int) -> Optional[str]:
    """Infer race_type from series history. >50% threshold, min 2 editions."""
    historical = (
        session.query(Race.race_type)
        .filter(
            Race.series_id == series_id,
            Race.is_upcoming.is_(False),
            Race.race_type.isnot(None),
        )
        .all()
    )
    if len(historical) < 2:
        return None

    type_counts = Counter(r[0].value for r in historical)
    total = sum(type_counts.values())
    most_common, count = type_counts.most_common(1)[0]
    if count / total > 0.50:
        return most_common
    return None


def _get_series_course(session: Session, series_id: int) -> Optional[Course]:
    """Get the most recent Course for a series (by extracted_at)."""
    return (
        session.query(Course)
        .filter(Course.series_id == series_id)
        .order_by(Course.extracted_at.desc().nullslast())
        .first()
    )


def _resolve_prediction(
    session: Session,
    series_id: int,
    category: Optional[str],
    course: Optional[Course],
) -> dict:
    """Resolve finish type with source priority.

    1. Time-gap (highest fidelity, empirical data)
    2. Course profile (terrain + race type heuristic)
    3. Race type only (lowest fidelity)
    """
    # 1. Time-gap prediction
    time_gap = predict_series_finish_type(session, series_id, category)
    if time_gap["predicted_finish_type"] != "unknown":
        return {**time_gap, "prediction_source": "time_gap"}

    # 2. Course-based prediction
    race_type = _get_series_race_type(session, series_id)
    if course:
        course_pred = predict_finish_type_from_course(
            course_type=course.course_type.value if course.course_type else None,
            race_type=race_type,
            total_gain_m=course.total_gain_m,
            distance_m=course.distance_m,
            climbs_json=course.climbs_json,
            m_per_km=course.m_per_km,
        )
        if course_pred:
            # Log disagreements between time-gap and course for data quality
            if time_gap["edition_count"] > 0:
                logger.debug(
                    "Series %d: time-gap=unknown, course-based=%s (source=%s)",
                    series_id, course_pred.finish_type.value, course_pred.source,
                )
            return {
                "predicted_finish_type": course_pred.finish_type.value,
                "confidence": _confidence_label(course_pred.confidence),
                "edition_count": time_gap["edition_count"],
                "distribution": time_gap["distribution"],
                "prediction_source": course_pred.source,
            }

    # 3. Race-type-only fallback (no course data)
    if race_type:
        rt_pred = predict_finish_type_from_course(
            course_type=None, race_type=race_type,
        )
        if rt_pred:
            return {
                "predicted_finish_type": rt_pred.finish_type.value,
                "confidence": _confidence_label(rt_pred.confidence),
                "edition_count": time_gap["edition_count"],
                "distribution": time_gap["distribution"],
                "prediction_source": "race_type_only",
            }

    # 4. Unknown
    return {**time_gap, "prediction_source": None}


def precompute_series_predictions(
    session: Session,
    series_id: int,
    categories: Optional[list[str]] = None,
) -> int:
    """Pre-compute predictions for a single series across categories.

    Returns number of predictions created/updated.
    """
    from datetime import datetime

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

    # Get course data once for the series
    course = _get_series_course(session, series_id)

    # Always compute for None (overall) + each category
    cat_list = [None] + categories
    count = 0

    for cat in cat_list:
        prediction = _resolve_prediction(session, series_id, cat, course)
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
        row.prediction_source = prediction.get("prediction_source")
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


def populate_upcoming_race_types(session: Session) -> int:
    """Inherit race_type for upcoming races from series history.

    Uses simple majority (>50%) with minimum 2 historical editions.
    """
    upcoming = (
        session.query(Race)
        .filter(Race.is_upcoming.is_(True), Race.race_type.is_(None))
        .all()
    )
    updated = 0
    for race in upcoming:
        if not race.series_id:
            continue
        inferred = _get_series_race_type(session, race.series_id)
        if inferred:
            race.race_type = RaceType(inferred)
            updated += 1
    session.commit()
    return updated


def precompute_all(session: Session) -> dict:
    """Pre-compute predictions for all series. Returns summary stats."""
    # Pre-step: populate race_type on upcoming races
    rt_updated = populate_upcoming_race_types(session)
    if rt_updated:
        logger.info("Inherited race_type for %d upcoming races.", rt_updated)

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
        "race_types_inherited": rt_updated,
    }
