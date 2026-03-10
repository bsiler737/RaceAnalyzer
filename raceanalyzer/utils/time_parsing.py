"""Parse road-results.com RaceTime strings to seconds."""

from __future__ import annotations

import re

TIME_PATTERN = re.compile(r"(?:(\d+):)?(?:(\d+):)?(\d+(?:\.\d+)?)")

NON_FINISH_MARKERS = ("DNF", "DQ", "DNS", "DNP", "OTL")


def parse_race_time(time_str: str | None) -> float | None:
    """Parse a RaceTime string to total seconds.

    Returns None for DNF, DQ, empty, or unparseable values.

    Examples:
        "1:23:45.67" -> 5025.67
        "23:45.67"   -> 1425.67
        "45.67"      -> 45.67
        "DNF"        -> None
        ""           -> None
    """
    if not time_str or not time_str.strip():
        return None

    time_str = time_str.strip()

    if any(marker in time_str.upper() for marker in NON_FINISH_MARKERS):
        return None

    match = TIME_PATTERN.fullmatch(time_str)
    if not match:
        return None

    groups = match.groups()
    parts = [float(g) if g else 0.0 for g in groups]

    if groups[0] is not None and groups[1] is not None:
        # H:M:S
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif groups[0] is not None:
        # M:S
        return parts[0] * 60 + parts[2]
    else:
        # S only
        return parts[2]
