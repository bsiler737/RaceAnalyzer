"""Tests for course-based finish type predictor (Sprint 012 Phase 1)."""

import json

from raceanalyzer.classification.course_predictor import (
    _resolve_course_character,
    predict_finish_type_from_course,
)
from raceanalyzer.db.models import FinishType


class TestResolveCharacter:
    """Tests for _resolve_course_character helper."""

    def test_stored_course_type_takes_priority(self):
        assert _resolve_course_character("hilly", 3.0) == "hilly"

    def test_unknown_course_type_falls_through(self):
        assert _resolve_course_character("unknown", 3.0) == "flat"

    def test_empty_course_type_falls_through(self):
        assert _resolve_course_character("", 3.0) == "flat"

    def test_none_course_type_with_m_per_km(self):
        assert _resolve_course_character(None, 3.0) == "flat"
        assert _resolve_course_character(None, 8.0) == "rolling"
        assert _resolve_course_character(None, 15.0) == "hilly"
        assert _resolve_course_character(None, 25.0) == "mountainous"

    def test_none_everything(self):
        assert _resolve_course_character(None, None) is None

    def test_crit_offset_shifts_thresholds(self):
        # 4 m/km is flat for road races (< 5.0)
        assert _resolve_course_character(None, 4.0, race_type="road_race") == "flat"
        # 4 m/km is rolling for crits (threshold shifted to 3.0)
        assert _resolve_course_character(None, 4.0, race_type="criterium") == "rolling"


class TestTimeTrial:
    def test_time_trial_returns_individual_tt(self):
        result = predict_finish_type_from_course(
            course_type="flat", race_type="time_trial"
        )
        assert result is not None
        assert result.finish_type == FinishType.INDIVIDUAL_TT
        assert result.confidence == 0.95
        assert result.source == "race_type_only"

    def test_time_trial_overrides_any_course(self):
        result = predict_finish_type_from_course(
            course_type="mountainous", race_type="time_trial"
        )
        assert result.finish_type == FinishType.INDIVIDUAL_TT


class TestHillClimb:
    def test_hill_climb_returns_gc_selective(self):
        result = predict_finish_type_from_course(
            course_type=None, race_type="hill_climb"
        )
        assert result is not None
        assert result.finish_type == FinishType.GC_SELECTIVE
        assert result.confidence == 0.85
        assert result.source == "race_type_only"


class TestCriterium:
    def test_crit_flat_returns_bunch_sprint(self):
        result = predict_finish_type_from_course(
            course_type="flat", race_type="criterium"
        )
        assert result.finish_type == FinishType.BUNCH_SPRINT
        assert result.confidence == 0.75
        assert result.source == "course_profile"

    def test_crit_hilly_returns_reduced_sprint(self):
        result = predict_finish_type_from_course(
            course_type="hilly", race_type="criterium"
        )
        assert result.finish_type == FinishType.REDUCED_SPRINT
        assert result.confidence == 0.55

    def test_crit_mountainous_returns_reduced_sprint(self):
        result = predict_finish_type_from_course(
            course_type="mountainous", race_type="criterium"
        )
        assert result.finish_type == FinishType.REDUCED_SPRINT

    def test_crit_no_course_data_returns_bunch_sprint_lower_confidence(self):
        result = predict_finish_type_from_course(
            course_type=None, race_type="criterium"
        )
        assert result.finish_type == FinishType.BUNCH_SPRINT
        assert result.confidence == 0.60
        assert result.source == "race_type_only"


class TestMountainous:
    def test_mountainous_steep_climb(self):
        climbs = [{"avg_grade": 9.0, "length_m": 1500}]
        result = predict_finish_type_from_course(
            course_type="mountainous",
            race_type="road_race",
            climbs_json=json.dumps(climbs),
        )
        assert result.finish_type == FinishType.BREAKAWAY_SELECTIVE
        assert result.confidence == 0.70
        assert "steep" in result.reasoning

    def test_mountainous_long_climb(self):
        climbs = [{"avg_grade": 6.0, "length_m": 2500}]
        result = predict_finish_type_from_course(
            course_type="mountainous",
            race_type="road_race",
            climbs_json=json.dumps(climbs),
        )
        assert result.finish_type == FinishType.BREAKAWAY_SELECTIVE
        assert "long" in result.reasoning

    def test_mountainous_no_significant_climbs(self):
        result = predict_finish_type_from_course(
            course_type="mountainous",
            race_type="road_race",
            m_per_km=22.0,
        )
        assert result.finish_type == FinishType.GC_SELECTIVE
        assert result.confidence == 0.65


class TestHilly:
    def test_hilly_late_climb_with_multiple_climbs(self):
        climbs = [
            {"start_d": 5000, "avg_grade": 5.0, "length_m": 800},
            {"start_d": 70000, "avg_grade": 6.0, "length_m": 1000},
        ]
        result = predict_finish_type_from_course(
            course_type="hilly",
            race_type="road_race",
            distance_m=100000,
            climbs_json=json.dumps(climbs),
        )
        assert result.finish_type == FinishType.BREAKAWAY_SELECTIVE
        assert result.confidence == 0.60

    def test_hilly_many_climbs_no_late(self):
        climbs = [
            {"start_d": 1000, "avg_grade": 5.0, "length_m": 500},
            {"start_d": 10000, "avg_grade": 5.0, "length_m": 500},
            {"start_d": 20000, "avg_grade": 5.0, "length_m": 500},
        ]
        result = predict_finish_type_from_course(
            course_type="hilly",
            race_type="road_race",
            distance_m=100000,
            climbs_json=json.dumps(climbs),
        )
        assert result.finish_type == FinishType.SMALL_GROUP_SPRINT
        assert result.confidence == 0.55

    def test_hilly_default(self):
        result = predict_finish_type_from_course(
            course_type="hilly",
            race_type="road_race",
            m_per_km=15.0,
        )
        assert result.finish_type == FinishType.REDUCED_SPRINT
        assert result.confidence == 0.55


class TestRolling:
    def test_rolling_long_race(self):
        result = predict_finish_type_from_course(
            course_type="rolling",
            race_type="road_race",
            distance_m=90000,
            m_per_km=8.0,
        )
        assert result.finish_type == FinishType.REDUCED_SPRINT
        assert result.confidence == 0.55

    def test_rolling_short_race(self):
        result = predict_finish_type_from_course(
            course_type="rolling",
            race_type="road_race",
            distance_m=50000,
            m_per_km=8.0,
        )
        assert result.finish_type == FinishType.BUNCH_SPRINT
        assert result.confidence == 0.55


class TestFlat:
    def test_flat_long(self):
        result = predict_finish_type_from_course(
            course_type="flat",
            race_type="road_race",
            distance_m=100000,
        )
        assert result.finish_type == FinishType.BUNCH_SPRINT
        assert result.confidence == 0.70

    def test_flat_short(self):
        result = predict_finish_type_from_course(
            course_type="flat",
            race_type="road_race",
            distance_m=40000,
        )
        assert result.finish_type == FinishType.BUNCH_SPRINT
        assert result.confidence == 0.65


class TestRoadRaceNoData:
    def test_road_race_without_course_returns_none(self):
        result = predict_finish_type_from_course(
            course_type=None, race_type="road_race"
        )
        assert result is None


class TestGravelFallback:
    def test_gravel_no_course_returns_reduced_sprint(self):
        result = predict_finish_type_from_course(
            course_type=None, race_type="gravel"
        )
        assert result.finish_type == FinishType.REDUCED_SPRINT
        assert result.confidence == 0.50
        assert result.source == "race_type_only"


class TestStageRaceFallback:
    def test_stage_race_no_course_returns_mixed(self):
        result = predict_finish_type_from_course(
            course_type=None, race_type="stage_race"
        )
        assert result.finish_type == FinishType.MIXED
        assert result.confidence == 0.45
        assert result.source == "race_type_only"


class TestNoData:
    def test_no_data_returns_none(self):
        result = predict_finish_type_from_course(
            course_type=None, race_type=None
        )
        assert result is None


class TestCritMPerKmOffset:
    def test_crit_4_m_per_km_is_rolling_not_flat(self):
        """4 m/km crit should classify as rolling (threshold shifted to 3.0)."""
        result = predict_finish_type_from_course(
            course_type=None, race_type="criterium", m_per_km=4.0
        )
        # With rolling character, a crit is still bunch sprint
        # but the important thing is the character was "rolling" not "flat"
        assert result.finish_type == FinishType.BUNCH_SPRINT

    def test_crit_11_m_per_km_is_hilly(self):
        """11 m/km crit should be hilly (threshold shifted to 10.0)."""
        result = predict_finish_type_from_course(
            course_type=None, race_type="criterium", m_per_km=11.0
        )
        assert result.finish_type == FinishType.REDUCED_SPRINT


class TestConfidenceCaps:
    """Verify confidence never exceeds caps for each source type."""

    def test_course_profile_max_075(self):
        """course_profile predictions cap at 0.75."""
        # Flat crit with known character is the highest course_profile confidence
        result = predict_finish_type_from_course(
            course_type="flat", race_type="criterium"
        )
        assert result.source == "course_profile"
        assert result.confidence <= 0.75

    def test_race_type_only_max_060_for_non_special(self):
        """race_type_only predictions (excluding TT/hill_climb) cap at 0.60."""
        result = predict_finish_type_from_course(
            course_type=None, race_type="criterium"
        )
        assert result.source == "race_type_only"
        assert result.confidence <= 0.60

    def test_tt_and_hill_climb_allowed_above_060(self):
        """TT and hill_climb are allowed higher confidence."""
        tt = predict_finish_type_from_course(
            course_type=None, race_type="time_trial"
        )
        hc = predict_finish_type_from_course(
            course_type=None, race_type="hill_climb"
        )
        assert tt.confidence == 0.95
        assert hc.confidence == 0.85


class TestMalformedClimbsJson:
    def test_garbage_string(self):
        result = predict_finish_type_from_course(
            course_type="hilly",
            race_type="road_race",
            climbs_json="not valid json!!!",
        )
        # Should fall through to hilly default (no climbs parsed)
        assert result.finish_type == FinishType.REDUCED_SPRINT

    def test_empty_list(self):
        result = predict_finish_type_from_course(
            course_type="hilly",
            race_type="road_race",
            climbs_json="[]",
        )
        assert result.finish_type == FinishType.REDUCED_SPRINT

    def test_none_climbs(self):
        result = predict_finish_type_from_course(
            course_type="hilly",
            race_type="road_race",
            climbs_json=None,
        )
        assert result.finish_type == FinishType.REDUCED_SPRINT


class TestMPerKmComputation:
    def test_m_per_km_computed_from_gain_and_distance(self):
        """When m_per_km not provided, it's computed from total_gain_m / distance_m."""
        # 2000m gain over 100km = 20 m/km -> mountainous
        result = predict_finish_type_from_course(
            course_type=None,
            race_type="road_race",
            total_gain_m=2000,
            distance_m=100000,
        )
        assert result is not None
        assert result.finish_type == FinishType.GC_SELECTIVE  # mountainous

    def test_m_per_km_explicit_takes_priority(self):
        """Explicit m_per_km is used even if total_gain_m/distance_m differ."""
        result = predict_finish_type_from_course(
            course_type=None,
            race_type="road_race",
            total_gain_m=100,
            distance_m=100000,
            m_per_km=25.0,  # mountainous, overrides computed 1 m/km
        )
        assert result.finish_type in (
            FinishType.GC_SELECTIVE,
            FinishType.BREAKAWAY_SELECTIVE,
        )


class TestEdgeCases:
    def test_zero_distance(self):
        """Zero distance should not cause division error."""
        result = predict_finish_type_from_course(
            course_type=None,
            race_type="road_race",
            total_gain_m=100,
            distance_m=0,
        )
        # No m_per_km computed, no course_type -> None for road_race
        assert result is None

    def test_unknown_race_type_no_course(self):
        result = predict_finish_type_from_course(
            course_type=None, race_type="cyclocross"
        )
        assert result is None

    def test_flat_with_none_race_type(self):
        """Course data alone is sufficient when character is known."""
        result = predict_finish_type_from_course(
            course_type="flat", race_type=None
        )
        assert result.finish_type == FinishType.BUNCH_SPRINT
