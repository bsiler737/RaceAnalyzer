"""Tests for stage schedule YAML loader (Sprint 017)."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
import yaml

from raceanalyzer.stages import load_stage_schedule


class TestLoadStageSchedule:
    """Test the YAML stage schedule loader."""

    def setup_method(self):
        # Clear lru_cache between tests
        load_stage_schedule.cache_clear()

    def test_valid_tour_de_bloom(self):
        stages = load_stage_schedule("tour de bloom")
        assert stages is not None
        assert len(stages) == 6
        assert stages[0].name == "Mission Ridge Hill Climb"
        assert stages[0].race_type == "hill_climb"
        assert stages[0].date == date(2026, 5, 14)
        assert stages[0].number == 1

    def test_valid_the_dalles_omnium(self):
        stages = load_stage_schedule("the dalles omnium")
        assert stages is not None
        assert len(stages) == 2
        assert stages[0].race_type == "road_race"
        assert stages[1].race_type == "time_trial"

    def test_valid_baker_city(self):
        stages = load_stage_schedule("baker city cycling classic")
        assert stages is not None
        assert len(stages) == 4

    def test_missing_file_returns_none(self):
        result = load_stage_schedule("nonexistent race")
        assert result is None

    def test_elites_only_flag(self):
        stages = load_stage_schedule("tour de bloom")
        assert stages is not None
        assert stages[4].elites_only is True
        assert stages[5].elites_only is True
        assert stages[0].elites_only is False

    def test_rwgps_route_id_optional(self):
        stages = load_stage_schedule("baker city cycling classic")
        assert stages is not None
        # Stage 3 (Downtown Criterium) now has rwgps_route_id
        assert stages[2].rwgps_route_id == 27808423
        # Stage 1 has one
        assert stages[0].rwgps_route_id == 45958894

    def test_stages_sorted_by_number(self):
        stages = load_stage_schedule("tour de bloom")
        assert stages is not None
        numbers = [s.number for s in stages]
        assert numbers == [1, 2, 3, 4, 5, 6]

    def test_invalid_yaml_returns_none(self, tmp_path):
        """YAML with missing required fields returns None."""
        bad_yaml = tmp_path / "bad_race.yaml"
        bad_yaml.write_text("name: Bad Race\nstages:\n  - stage: 1\n    name: Only Name\n")
        with patch("raceanalyzer.stages._STAGES_DIR", tmp_path):
            load_stage_schedule.cache_clear()
            result = load_stage_schedule("bad race")
            assert result is None

    def test_duplicate_stage_numbers_returns_none(self, tmp_path):
        data = {
            "name": "Dup Race",
            "stages": [
                {"stage": 1, "name": "A", "race_type": "road_race", "date": "2026-06-01"},
                {"stage": 1, "name": "B", "race_type": "criterium", "date": "2026-06-02"},
            ],
        }
        (tmp_path / "dup_race.yaml").write_text(yaml.dump(data))
        with patch("raceanalyzer.stages._STAGES_DIR", tmp_path):
            load_stage_schedule.cache_clear()
            result = load_stage_schedule("dup race")
            assert result is None

    def test_invalid_race_type_returns_none(self, tmp_path):
        data = {
            "name": "Bad Type",
            "stages": [
                {"stage": 1, "name": "A", "race_type": "stage_race", "date": "2026-06-01"},
            ],
        }
        (tmp_path / "bad_type.yaml").write_text(yaml.dump(data))
        with patch("raceanalyzer.stages._STAGES_DIR", tmp_path):
            load_stage_schedule.cache_clear()
            result = load_stage_schedule("bad type")
            assert result is None

    def test_non_contiguous_stage_numbers_returns_none(self, tmp_path):
        data = {
            "name": "Gap Race",
            "stages": [
                {"stage": 1, "name": "A", "race_type": "road_race", "date": "2026-06-01"},
                {"stage": 3, "name": "B", "race_type": "criterium", "date": "2026-06-02"},
            ],
        }
        (tmp_path / "gap_race.yaml").write_text(yaml.dump(data))
        with patch("raceanalyzer.stages._STAGES_DIR", tmp_path):
            load_stage_schedule.cache_clear()
            result = load_stage_schedule("gap race")
            assert result is None

    def test_stage_definition_frozen(self):
        stages = load_stage_schedule("tour de bloom")
        assert stages is not None
        with pytest.raises(AttributeError):
            stages[0].name = "modified"
