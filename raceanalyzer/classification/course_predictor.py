"""Course-based finish type predictor (Sprint 012 CP-01).

Infers likely finish outcomes from terrain data for races where
time-gap classification is impossible (no finish times available).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from raceanalyzer.db.models import FinishType


@dataclass
class CoursePrediction:
    """Result of course-based finish type prediction."""

    finish_type: FinishType
    confidence: float  # 0.0-1.0
    source: str  # "course_profile" or "race_type_only"
    reasoning: str  # human-readable explanation


# --- Thresholds ---
_THRESHOLDS = (5.0, 12.0, 20.0)  # flat/rolling, rolling/hilly, hilly/mountainous
_CRIT_OFFSET = -2.0  # shift thresholds down for crits

STEEP_CLIMB_GRADE = 8.0  # Climbs averaging 8%+ are selective
LONG_CLIMB_M = 2000.0  # Climbs >2 km are significant
LONG_ROAD_RACE_M = 80000.0  # Races >80 km are more selective


def _resolve_course_character(
    course_type: Optional[str],
    m_per_km: Optional[float],
    race_type: Optional[str] = None,
) -> Optional[str]:
    """Derive course character from stored course_type or raw m_per_km."""
    if course_type and course_type not in ("unknown", ""):
        return course_type

    if m_per_km is None:
        return None

    t1, t2, t3 = _THRESHOLDS
    if race_type == "criterium":
        t1 += _CRIT_OFFSET
        t2 += _CRIT_OFFSET
        t3 += _CRIT_OFFSET

    if m_per_km < t1:
        return "flat"
    elif m_per_km < t2:
        return "rolling"
    elif m_per_km < t3:
        return "hilly"
    else:
        return "mountainous"


def predict_finish_type_from_course(
    course_type: Optional[str],
    race_type: Optional[str],
    total_gain_m: Optional[float] = None,
    distance_m: Optional[float] = None,
    climbs_json: Optional[str] = None,
    m_per_km: Optional[float] = None,
) -> Optional[CoursePrediction]:
    """Predict finish type from course characteristics.

    Returns None if insufficient data. Uses a decision tree
    with climb-aware rules for richer predictions on hilly/
    mountainous courses.
    """
    # Parse climbs
    climbs: list[dict] = []
    if climbs_json:
        try:
            climbs = json.loads(climbs_json) if isinstance(climbs_json, str) else climbs_json
        except (json.JSONDecodeError, TypeError):
            pass

    # Compute m/km if not provided
    if m_per_km is None and total_gain_m and distance_m and distance_m > 0:
        m_per_km = (total_gain_m / distance_m) * 1000.0

    character = _resolve_course_character(course_type, m_per_km, race_type)

    # --- Rule 1: Time trials ---
    if race_type == "time_trial":
        return CoursePrediction(
            finish_type=FinishType.INDIVIDUAL_TT,
            confidence=0.95,
            source="race_type_only",
            reasoning="Race type is time trial.",
        )

    # --- Rule 2: Hill climbs -> GC_SELECTIVE (mass-start, not TT) ---
    if race_type == "hill_climb":
        return CoursePrediction(
            finish_type=FinishType.GC_SELECTIVE,
            confidence=0.85,
            source="race_type_only",
            reasoning="Hill climbs are mass-start climbing events.",
        )

    # --- Rule 3: Criteriums ---
    if race_type == "criterium":
        if character and character in ("hilly", "mountainous"):
            return CoursePrediction(
                finish_type=FinishType.REDUCED_SPRINT,
                confidence=0.55,
                source="course_profile",
                reasoning=(
                    f"Criterium on {character} terrain"
                    " — hillier than typical, likely a reduced field sprint."
                ),
            )
        return CoursePrediction(
            finish_type=FinishType.BUNCH_SPRINT,
            confidence=0.75 if character else 0.60,
            source="course_profile" if character else "race_type_only",
            reasoning="Criteriums typically end in bunch sprints.",
        )

    # --- Rule 4: Need some data for road races ---
    if character is None and race_type is None:
        return None  # Not enough data

    # Race-type-only fallback for road races without course data
    if character is None:
        if race_type == "road_race":
            return None  # Road race without course data is too ambiguous
        if race_type == "gravel":
            return CoursePrediction(
                finish_type=FinishType.REDUCED_SPRINT,
                confidence=0.50,
                source="race_type_only",
                reasoning="Gravel races typically thin the field.",
            )
        if race_type == "stage_race":
            return CoursePrediction(
                finish_type=FinishType.MIXED,
                confidence=0.45,
                source="race_type_only",
                reasoning="Stage races have varied finishes across stages.",
            )
        return None  # Unknown race type without course data

    # --- From here, character is not None ---
    m_per_km_str = f"{m_per_km:.0f} m/km" if m_per_km is not None else character

    # --- Rule 5: Mountainous terrain ---
    if character == "mountainous":
        has_steep_climb = any(
            c.get("avg_grade", 0) >= STEEP_CLIMB_GRADE for c in climbs
        )
        has_long_climb = any(
            c.get("length_m", 0) >= LONG_CLIMB_M for c in climbs
        )

        if has_steep_climb or has_long_climb:
            return CoursePrediction(
                finish_type=FinishType.BREAKAWAY_SELECTIVE,
                confidence=0.70,
                source="course_profile",
                reasoning=(
                    f"Mountainous course ({m_per_km_str}) with "
                    f"{'steep' if has_steep_climb else 'long'} climbs "
                    "— the field will likely shatter."
                ),
            )
        return CoursePrediction(
            finish_type=FinishType.GC_SELECTIVE,
            confidence=0.65,
            source="course_profile",
            reasoning=f"Mountainous course ({m_per_km_str}) — expect a selective finish.",
        )

    # --- Rule 6: Hilly terrain ---
    if character == "hilly":
        n_climbs = len(climbs)
        has_late_climb = False
        if distance_m and distance_m > 0:
            has_late_climb = any(
                c.get("start_d", 0) / distance_m > 0.6 for c in climbs
            )

        if has_late_climb and n_climbs >= 2:
            return CoursePrediction(
                finish_type=FinishType.BREAKAWAY_SELECTIVE,
                confidence=0.60,
                source="course_profile",
                reasoning=(
                    f"Hilly course ({m_per_km_str}) with "
                    f"{n_climbs} climbs including a late climb "
                    "— likely a selective breakaway finish."
                ),
            )
        if n_climbs >= 3:
            return CoursePrediction(
                finish_type=FinishType.SMALL_GROUP_SPRINT,
                confidence=0.55,
                source="course_profile",
                reasoning=(
                    f"Hilly course ({m_per_km_str}) with "
                    f"{n_climbs} climbs — expect a reduced group sprint."
                ),
            )
        return CoursePrediction(
            finish_type=FinishType.REDUCED_SPRINT,
            confidence=0.55,
            source="course_profile",
            reasoning=f"Hilly course ({m_per_km_str}) — the climbs will thin the field.",
        )

    # --- Rule 7: Rolling terrain ---
    if character == "rolling":
        is_long = distance_m is not None and distance_m > LONG_ROAD_RACE_M
        if is_long:
            return CoursePrediction(
                finish_type=FinishType.REDUCED_SPRINT,
                confidence=0.55,
                source="course_profile",
                reasoning=(
                    f"Long rolling course ({distance_m / 1000:.0f} km, "
                    f"{m_per_km_str}) — fatigue will thin the sprint group."
                ),
            )
        return CoursePrediction(
            finish_type=FinishType.BUNCH_SPRINT,
            confidence=0.55,
            source="course_profile",
            reasoning=f"Rolling course ({m_per_km_str}) — most rolling races still end in a group sprint.",
        )

    # --- Rule 8: Flat terrain ---
    if character == "flat":
        is_long = distance_m is not None and distance_m > LONG_ROAD_RACE_M
        conf = 0.70 if is_long else 0.65
        return CoursePrediction(
            finish_type=FinishType.BUNCH_SPRINT,
            confidence=conf,
            source="course_profile",
            reasoning=f"Flat course ({m_per_km_str}) — expect the pack to stay together.",
        )

    return None
