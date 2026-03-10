"""Rule-based finish type classifier.

Decision tree from research-findings.md, operating on gap-grouped results.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from raceanalyzer.classification.grouping import RiderGroup
from raceanalyzer.db.models import FinishType, RaceType


@dataclass
class ClassificationResult:
    finish_type: FinishType
    confidence: float
    metrics: dict


def is_individual_tt(
    groups: list[RiderGroup],
    total_finishers: int,
    race_type: RaceType | None = None,
    race_name: str = "",
) -> tuple[bool, float]:
    """Detect individual TT/hill climb via three-tier analysis.

    Returns (is_tt, confidence):
    - Tier 1: race_type metadata (TIME_TRIAL, HILL_CLIMB) -> 0.95
    - Tier 2: name keywords -> 0.85
    - Tier 3: statistical spacing (group_ratio > 0.7, gap_cv < 0.8) -> 0.75
    """
    # Tier 1: Race type metadata
    if race_type in (RaceType.TIME_TRIAL, RaceType.HILL_CLIMB):
        return (True, 0.95)

    # Tier 2: Name keywords
    name_lower = race_name.lower()
    tt_keywords = [
        "time trial", "tt ", " tt", "hill climb", "hillclimb",
        "chrono", "itt", "contre la montre",
    ]
    if any(kw in name_lower for kw in tt_keywords):
        return (True, 0.85)

    # Tier 3: Statistical spacing
    if not groups or total_finishers < 5:
        return (False, 0.0)

    group_ratio = len(groups) / total_finishers
    if group_ratio <= 0.7:
        return (False, 0.0)

    # CV of consecutive inter-rider gaps (NOT absolute times)
    all_times = sorted(
        t for g in groups for r in g.riders
        if (t := getattr(r, "race_time_seconds", None)) is not None
    )
    if len(all_times) < 5:
        return (False, 0.0)

    gaps = [
        all_times[i] - all_times[i - 1]
        for i in range(1, len(all_times))
        if all_times[i] > all_times[i - 1]
    ]
    if not gaps:
        return (False, 0.0)

    gap_mean = statistics.mean(gaps)
    if gap_mean <= 0:
        return (False, 0.0)

    gap_cv = statistics.stdev(gaps) / gap_mean
    if gap_cv < 0.8:
        return (True, 0.75)

    return (False, 0.0)


def _compute_metrics(
    groups: list[RiderGroup],
    total_finishers: int,
    gap_threshold_used: float,
) -> dict:
    """Extract group-structure metrics from classified groups."""
    group_sizes = [len(g.riders) for g in groups]
    largest_group_size = max(group_sizes)
    largest_group_ratio = largest_group_size / total_finishers
    leader_group_size = len(groups[0].riders)
    gap_to_second = groups[0].gap_to_next if groups[0].gap_to_next is not None else 0.0
    num_groups = len(groups)

    all_times = []
    for g in groups:
        for r in g.riders:
            t = getattr(r, "race_time_seconds", None)
            if t is not None:
                all_times.append(t)

    cv_of_times = 0.0
    if len(all_times) > 1:
        mean = statistics.mean(all_times)
        if mean > 0:
            cv_of_times = statistics.stdev(all_times) / mean

    return {
        "num_finishers": total_finishers,
        "num_groups": num_groups,
        "largest_group_size": largest_group_size,
        "largest_group_ratio": round(largest_group_ratio, 4),
        "leader_group_size": leader_group_size,
        "gap_to_second_group": round(gap_to_second, 2),
        "cv_of_times": round(cv_of_times, 6),
        "gap_threshold_used": gap_threshold_used,
    }


def classify_finish_type(
    groups: list[RiderGroup],
    total_finishers: int,
    gap_threshold_used: float = 3.0,
    race_type: RaceType | None = None,
    race_name: str = "",
) -> ClassificationResult:
    """Apply rule-based decision tree to grouped results.

    Rules:
    - INDIVIDUAL_TT:       detected via is_individual_tt() pre-check
    - BUNCH_SPRINT:        largest group > 50% of field AND gap to second < 30s
    - BREAKAWAY:           leader group <= 5 AND gap > 30s AND main bunch > 40%
    - BREAKAWAY_SELECTIVE: leader group <= 5 AND gap > 30s AND main bunch <= 40%
    - SMALL_GROUP_SPRINT:  leader group 6-15 AND gap > 30s (select group sprints)
    - GC_SELECTIVE:        > 5 groups AND largest < 30%
    - REDUCED_SPRINT:      leader group > 5 AND < 50% of field AND gap <= 30s
    - MIXED:               everything else
    - UNKNOWN:             no time data
    """
    if not groups or total_finishers == 0:
        return ClassificationResult(
            finish_type=FinishType.UNKNOWN,
            confidence=1.0,
            metrics={"reason": "no_time_data"},
        )

    # Pre-check: Individual TT / Hill Climb
    is_tt, tt_confidence = is_individual_tt(
        groups, total_finishers, race_type, race_name
    )
    if is_tt:
        metrics = _compute_metrics(groups, total_finishers, gap_threshold_used)
        return ClassificationResult(
            finish_type=FinishType.INDIVIDUAL_TT,
            confidence=round(tt_confidence, 2),
            metrics=metrics,
        )

    metrics = _compute_metrics(groups, total_finishers, gap_threshold_used)

    largest_group_ratio = metrics["largest_group_ratio"]
    leader_group_size = metrics["leader_group_size"]
    gap_to_second = metrics["gap_to_second_group"]
    num_groups = metrics["num_groups"]

    # Decision tree
    if largest_group_ratio > 0.5 and gap_to_second < 30:
        ft = FinishType.BUNCH_SPRINT
        confidence = 0.9 if largest_group_ratio > 0.8 else 0.75
    elif leader_group_size <= 5 and gap_to_second > 30:
        if largest_group_ratio > 0.4:
            ft = FinishType.BREAKAWAY
        else:
            ft = FinishType.BREAKAWAY_SELECTIVE
        confidence = 0.8
    elif 6 <= leader_group_size <= 15 and gap_to_second > 30:
        ft = FinishType.SMALL_GROUP_SPRINT
        confidence = 0.75
    elif num_groups > 5 and largest_group_ratio < 0.3:
        ft = FinishType.GC_SELECTIVE
        confidence = 0.7
    elif leader_group_size > 5 and leader_group_size < total_finishers * 0.5:
        ft = FinishType.REDUCED_SPRINT
        confidence = 0.65
    else:
        ft = FinishType.MIXED
        confidence = 0.5

    if num_groups == 1:
        confidence = min(confidence + 0.1, 1.0)

    return ClassificationResult(
        finish_type=ft,
        confidence=round(confidence, 2),
        metrics=metrics,
    )
