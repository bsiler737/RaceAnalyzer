"""Time-gap grouping algorithm for finish type classification.

Implements the UCI chain rule: consecutive riders within gap_threshold
seconds are in the same group, regardless of total group time spread.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RiderGroup:
    """A group of riders finishing together."""

    riders: list[Any] = field(default_factory=list)
    min_time: float = 0.0
    max_time: float = 0.0
    gap_to_next: float | None = None


def group_by_consecutive_gaps(
    results: list,
    gap_threshold: float = 3.0,
    time_attr: str = "race_time_seconds",
) -> list[RiderGroup]:
    """Sort results by finish time, split into groups where consecutive gap exceeds threshold.

    Args:
        results: List of objects with a time attribute (float seconds).
        gap_threshold: Maximum consecutive gap (seconds) to keep riders in the same group.
        time_attr: Name of the attribute holding time in seconds.

    Returns:
        List of RiderGroup objects, ordered by finish time.
    """
    timed = [r for r in results if getattr(r, time_attr, None) is not None]
    timed.sort(key=lambda r: getattr(r, time_attr))

    if not timed:
        return []

    groups: list[list] = []
    current_group = [timed[0]]

    for i in range(1, len(timed)):
        prev_time = getattr(timed[i - 1], time_attr)
        curr_time = getattr(timed[i], time_attr)
        gap = curr_time - prev_time

        if gap > gap_threshold:
            groups.append(current_group)
            current_group = [timed[i]]
        else:
            current_group.append(timed[i])

    groups.append(current_group)

    # Convert to RiderGroup objects
    rider_groups = []
    for idx, group in enumerate(groups):
        times = [getattr(r, time_attr) for r in group]
        gap_to_next = None
        if idx < len(groups) - 1:
            next_min = getattr(groups[idx + 1][0], time_attr)
            gap_to_next = next_min - max(times)

        rider_groups.append(
            RiderGroup(
                riders=group,
                min_time=min(times),
                max_time=max(times),
                gap_to_next=gap_to_next,
            )
        )

    return rider_groups
