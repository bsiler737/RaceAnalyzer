"""Tests for finish type classification rules."""

from __future__ import annotations

from dataclasses import dataclass

from raceanalyzer.classification.finish_type import classify_finish_type, is_individual_tt
from raceanalyzer.classification.grouping import RiderGroup, group_by_consecutive_gaps
from raceanalyzer.db.models import FinishType, RaceType


@dataclass
class FakeResult:
    race_time_seconds: float = None
    name: str = ""


def _make_group(n_riders, base_time, spread=2.0):
    """Create a RiderGroup with n riders spread over `spread` seconds."""
    riders = []
    for i in range(n_riders):
        t = base_time + (spread * i / max(n_riders - 1, 1))
        riders.append(FakeResult(race_time_seconds=t, name=f"R{i}"))
    times = [r.race_time_seconds for r in riders]
    return RiderGroup(riders=riders, min_time=min(times), max_time=max(times))


class TestClassifyFinishType:
    def test_bunch_sprint(self):
        """Large group (>50% of field) with no gap => BUNCH_SPRINT."""
        group = _make_group(30, 3600.0, spread=2.0)
        group.gap_to_next = None
        result = classify_finish_type([group], total_finishers=30)
        assert result.finish_type == FinishType.BUNCH_SPRINT

    def test_breakaway(self):
        """Small leader group with big gap, main bunch > 40%."""
        leader = _make_group(3, 3600.0, spread=1.0)
        leader.gap_to_next = 60.0
        bunch = _make_group(40, 3661.0, spread=3.0)
        bunch.gap_to_next = None
        result = classify_finish_type([leader, bunch], total_finishers=43)
        assert result.finish_type == FinishType.BREAKAWAY

    def test_breakaway_selective(self):
        """Small leader group, big gap, but no dominant bunch."""
        leader = _make_group(3, 3600.0, spread=1.0)
        leader.gap_to_next = 60.0
        g2 = _make_group(5, 3661.0, spread=2.0)
        g2.gap_to_next = 30.0
        g3 = _make_group(5, 3693.0, spread=2.0)
        g3.gap_to_next = 20.0
        g4 = _make_group(5, 3715.0, spread=2.0)
        g4.gap_to_next = None
        result = classify_finish_type([leader, g2, g3, g4], total_finishers=18)
        assert result.finish_type == FinishType.BREAKAWAY_SELECTIVE

    def test_gc_selective(self):
        """Many small groups, no dominant group."""
        groups = []
        for i in range(7):
            g = _make_group(3, 3600.0 + i * 30, spread=2.0)
            g.gap_to_next = 28.0 if i < 6 else None
            groups.append(g)
        result = classify_finish_type(groups, total_finishers=21)
        assert result.finish_type == FinishType.GC_SELECTIVE

    def test_reduced_sprint(self):
        """Medium lead group (not majority) with small gap => REDUCED_SPRINT."""
        leader = _make_group(12, 3600.0, spread=3.0)
        leader.gap_to_next = 20.0
        g2 = _make_group(8, 3623.0, spread=5.0)
        g2.gap_to_next = 10.0
        g3 = _make_group(10, 3638.0, spread=5.0)
        g3.gap_to_next = None
        # largest group = 12, ratio = 12/30 = 0.4 (< 0.5, not bunch sprint)
        # leader_group_size = 12 > 5, < 15 (50% of 30), gap = 20 <= 30
        result = classify_finish_type([leader, g2, g3], total_finishers=30)
        assert result.finish_type == FinishType.REDUCED_SPRINT

    def test_small_group_sprint(self):
        """Lead group of 6-15 with big gap => SMALL_GROUP_SPRINT."""
        leader = _make_group(10, 3600.0, spread=3.0)
        leader.gap_to_next = 45.0
        bunch = _make_group(30, 3648.0, spread=5.0)
        bunch.gap_to_next = None
        result = classify_finish_type([leader, bunch], total_finishers=40)
        assert result.finish_type == FinishType.SMALL_GROUP_SPRINT

    def test_mixed_fallthrough(self):
        """Cases that don't match specific rules => MIXED."""
        # Leader group > half the field but with a gap (not bunch sprint)
        leader = _make_group(25, 3600.0, spread=3.0)
        leader.gap_to_next = 40.0
        tail = _make_group(5, 3643.0, spread=2.0)
        tail.gap_to_next = None
        result = classify_finish_type([leader, tail], total_finishers=30)
        assert result.finish_type == FinishType.MIXED

    def test_unknown_no_data(self):
        """No groups => UNKNOWN."""
        result = classify_finish_type([], total_finishers=0)
        assert result.finish_type == FinishType.UNKNOWN
        assert result.confidence == 1.0

    def test_single_rider(self):
        """Single finisher."""
        group = _make_group(1, 3600.0, spread=0)
        group.gap_to_next = None
        result = classify_finish_type([group], total_finishers=1)
        # Single rider is technically >50% of field
        assert result.finish_type == FinishType.BUNCH_SPRINT

    def test_metrics_stored(self):
        """Classification result contains all group metrics."""
        group = _make_group(20, 3600.0, spread=2.0)
        group.gap_to_next = None
        result = classify_finish_type([group], total_finishers=20, gap_threshold_used=3.0)
        assert "num_finishers" in result.metrics
        assert "num_groups" in result.metrics
        assert "largest_group_ratio" in result.metrics
        assert "cv_of_times" in result.metrics
        assert result.metrics["gap_threshold_used"] == 3.0

    def test_end_to_end_with_grouping(self):
        """Full pipeline: raw results -> grouping -> classification."""
        # Simulate a bunch sprint
        results = [FakeResult(race_time_seconds=3600.0 + i * 0.5, name=f"R{i}") for i in range(30)]
        groups = group_by_consecutive_gaps(results, gap_threshold=3.0)
        classification = classify_finish_type(groups, total_finishers=30)
        assert classification.finish_type == FinishType.BUNCH_SPRINT


class TestIndividualTT:
    """Tests for Individual TT detection."""

    def test_tt_by_race_type_metadata(self):
        """race_type = TIME_TRIAL -> INDIVIDUAL_TT with highest confidence."""
        group = _make_group(10, 3600.0, spread=2.0)
        group.gap_to_next = None
        is_tt, conf = is_individual_tt(
            [group], 10, race_type=RaceType.TIME_TRIAL
        )
        assert is_tt is True
        assert conf == 0.95

    def test_tt_by_hill_climb_type(self):
        """race_type = HILL_CLIMB -> INDIVIDUAL_TT."""
        is_tt, conf = is_individual_tt(
            [], 0, race_type=RaceType.HILL_CLIMB
        )
        assert is_tt is True
        assert conf == 0.95

    def test_tt_by_name_keyword(self):
        """Name containing 'time trial' -> INDIVIDUAL_TT."""
        group = _make_group(10, 3600.0, spread=2.0)
        group.gap_to_next = None
        is_tt, conf = is_individual_tt(
            [group], 10, race_name="Banana Belt Time Trial"
        )
        assert is_tt is True
        assert conf == 0.85

    def test_tt_by_hill_climb_name(self):
        """Name containing 'hill climb' -> INDIVIDUAL_TT."""
        is_tt, conf = is_individual_tt(
            [], 0, race_name="Mt. Tabor Hill Climb"
        )
        assert is_tt is True
        assert conf == 0.85

    def test_tt_by_statistical_spacing(self):
        """Evenly spaced riders (group_ratio > 0.7, low gap CV) -> INDIVIDUAL_TT."""
        # Simulate 20 riders each finishing ~30s apart (TT pattern)
        results = [
            FakeResult(race_time_seconds=1200.0 + i * 30.0, name=f"R{i}")
            for i in range(20)
        ]
        groups = group_by_consecutive_gaps(results, gap_threshold=3.0)
        # Each rider is their own group (gap_threshold=3s, gaps=30s)
        is_tt, conf = is_individual_tt(groups, 20)
        assert is_tt is True
        assert conf == 0.75

    def test_not_tt_bunch_sprint(self):
        """Bunch sprint should NOT be detected as TT."""
        group = _make_group(30, 3600.0, spread=2.0)
        group.gap_to_next = None
        is_tt, _ = is_individual_tt([group], 30)
        assert is_tt is False

    def test_not_tt_small_field(self):
        """Small field (< 5) should not trigger statistical detection."""
        results = [
            FakeResult(race_time_seconds=1200.0 + i * 30.0, name=f"R{i}")
            for i in range(3)
        ]
        groups = group_by_consecutive_gaps(results, gap_threshold=3.0)
        is_tt, _ = is_individual_tt(groups, 3)
        assert is_tt is False

    def test_classify_produces_individual_tt(self):
        """Full classify_finish_type returns INDIVIDUAL_TT for TT race."""
        results = [
            FakeResult(race_time_seconds=1200.0 + i * 30.0, name=f"R{i}")
            for i in range(20)
        ]
        groups = group_by_consecutive_gaps(results, gap_threshold=3.0)
        classification = classify_finish_type(
            groups, 20, race_name="Some Time Trial"
        )
        assert classification.finish_type == FinishType.INDIVIDUAL_TT
