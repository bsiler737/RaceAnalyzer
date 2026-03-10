"""Tests for time-gap grouping algorithm."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from raceanalyzer.classification.grouping import group_by_consecutive_gaps


@dataclass
class FakeResult:
    """Minimal result object for testing."""
    race_time_seconds: float = None
    name: str = ""


class TestGroupByConsecutiveGaps:
    def test_bunch_sprint_all_together(self):
        """All riders within 3 seconds = one group."""
        results = [
            FakeResult(race_time_seconds=3600.0, name="A"),
            FakeResult(race_time_seconds=3601.0, name="B"),
            FakeResult(race_time_seconds=3601.5, name="C"),
            FakeResult(race_time_seconds=3602.0, name="D"),
            FakeResult(race_time_seconds=3602.5, name="E"),
        ]
        groups = group_by_consecutive_gaps(results, gap_threshold=3.0)
        assert len(groups) == 1
        assert len(groups[0].riders) == 5

    def test_breakaway_two_groups(self):
        """Leader group, then gap, then main bunch."""
        results = [
            FakeResult(race_time_seconds=3600.0, name="Break1"),
            FakeResult(race_time_seconds=3601.0, name="Break2"),
            # 60 second gap
            FakeResult(race_time_seconds=3661.0, name="Bunch1"),
            FakeResult(race_time_seconds=3662.0, name="Bunch2"),
            FakeResult(race_time_seconds=3663.0, name="Bunch3"),
        ]
        groups = group_by_consecutive_gaps(results, gap_threshold=3.0)
        assert len(groups) == 2
        assert len(groups[0].riders) == 2
        assert len(groups[1].riders) == 3
        assert groups[0].gap_to_next == pytest.approx(60.0)

    def test_selective_many_groups(self):
        """Mountain stage: riders spread out."""
        results = [
            FakeResult(race_time_seconds=3600.0, name="A"),
            FakeResult(race_time_seconds=3610.0, name="B"),
            FakeResult(race_time_seconds=3620.0, name="C"),
            FakeResult(race_time_seconds=3630.0, name="D"),
            FakeResult(race_time_seconds=3640.0, name="E"),
            FakeResult(race_time_seconds=3650.0, name="F"),
        ]
        groups = group_by_consecutive_gaps(results, gap_threshold=3.0)
        assert len(groups) == 6  # Each rider in own group

    def test_empty_results(self):
        groups = group_by_consecutive_gaps([], gap_threshold=3.0)
        assert groups == []

    def test_single_rider(self):
        results = [FakeResult(race_time_seconds=3600.0, name="Solo")]
        groups = group_by_consecutive_gaps(results, gap_threshold=3.0)
        assert len(groups) == 1
        assert len(groups[0].riders) == 1
        assert groups[0].gap_to_next is None

    def test_no_timed_results(self):
        """All riders have None times."""
        results = [
            FakeResult(race_time_seconds=None, name="A"),
            FakeResult(race_time_seconds=None, name="B"),
        ]
        groups = group_by_consecutive_gaps(results, gap_threshold=3.0)
        assert groups == []

    def test_mixed_timed_and_untimed(self):
        """Only timed riders are grouped."""
        results = [
            FakeResult(race_time_seconds=3600.0, name="A"),
            FakeResult(race_time_seconds=None, name="DNF"),
            FakeResult(race_time_seconds=3601.0, name="B"),
        ]
        groups = group_by_consecutive_gaps(results, gap_threshold=3.0)
        assert len(groups) == 1
        assert len(groups[0].riders) == 2

    def test_chain_rule_stretched_group(self):
        """UCI chain rule: total spread > threshold but each consecutive gap < threshold."""
        results = [
            FakeResult(race_time_seconds=3600.0, name="A"),
            FakeResult(race_time_seconds=3602.5, name="B"),  # 2.5s gap
            FakeResult(race_time_seconds=3605.0, name="C"),  # 2.5s gap
            FakeResult(race_time_seconds=3607.5, name="D"),  # 2.5s gap
        ]
        # Total spread is 7.5s but each consecutive gap is 2.5s < 3.0s
        groups = group_by_consecutive_gaps(results, gap_threshold=3.0)
        assert len(groups) == 1
        assert len(groups[0].riders) == 4

    def test_unsorted_input(self):
        """Results should be sorted by time internally."""
        results = [
            FakeResult(race_time_seconds=3602.0, name="C"),
            FakeResult(race_time_seconds=3600.0, name="A"),
            FakeResult(race_time_seconds=3601.0, name="B"),
        ]
        groups = group_by_consecutive_gaps(results, gap_threshold=3.0)
        assert len(groups) == 1
        assert groups[0].riders[0].name == "A"

    def test_custom_threshold(self):
        """Different gap thresholds produce different groupings."""
        results = [
            FakeResult(race_time_seconds=3600.0, name="A"),
            FakeResult(race_time_seconds=3604.0, name="B"),  # 4s gap
        ]
        # 3s threshold: two groups
        groups_3 = group_by_consecutive_gaps(results, gap_threshold=3.0)
        assert len(groups_3) == 2

        # 5s threshold: one group
        groups_5 = group_by_consecutive_gaps(results, gap_threshold=5.0)
        assert len(groups_5) == 1
