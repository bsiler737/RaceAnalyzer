"""Terrain classification from elevation data."""

from __future__ import annotations

from typing import Optional

from raceanalyzer.config import Settings
from raceanalyzer.db.models import CourseType


def compute_m_per_km(
    total_gain_m: Optional[float], distance_m: Optional[float]
) -> Optional[float]:
    """Compute meters of climbing per kilometer. Returns None if inputs missing."""
    if total_gain_m is None or distance_m is None or distance_m <= 0:
        return None
    return total_gain_m / (distance_m / 1000.0)


def classify_terrain(
    m_per_km: Optional[float], settings: Optional[Settings] = None
) -> CourseType:
    """Classify terrain into 4-bin system. Returns UNKNOWN if m_per_km is None."""
    if m_per_km is None:
        return CourseType.UNKNOWN

    if settings is None:
        settings = Settings()

    if m_per_km < settings.terrain_flat_max:
        return CourseType.FLAT
    elif m_per_km < settings.terrain_rolling_max:
        return CourseType.ROLLING
    elif m_per_km < settings.terrain_hilly_max:
        return CourseType.HILLY
    else:
        return CourseType.MOUNTAINOUS


COURSE_TYPE_DISPLAY_NAMES = {
    "flat": "Flat",
    "rolling": "Rolling",
    "hilly": "Hilly",
    "mountainous": "Mountainous",
    "unknown": "Unknown Terrain",
}

COURSE_TYPE_DESCRIPTIONS = {
    "flat": "Minimal climbing. Expect bunch finishes unless wind or tactics break it up.",
    "rolling": "Moderate climbing. Strong all-rounders and punchy riders thrive.",
    "hilly": "Significant climbing. Climbers and breakaway artists have the advantage.",
    "mountainous": "Major climbing. Pure climbers dominate; the field will shatter.",
    "unknown": "No elevation data available for this course.",
}


def course_type_display(course_type_value: str) -> str:
    """Convert CourseType enum value to human-readable name."""
    return COURSE_TYPE_DISPLAY_NAMES.get(
        course_type_value, course_type_value.replace("_", " ").title()
    )
