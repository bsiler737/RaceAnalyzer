"""Tests for race type inference from race names."""

from __future__ import annotations

from raceanalyzer.db.models import RaceType
from raceanalyzer.queries import infer_race_type


class TestInferRaceType:
    def test_criterium_from_name(self):
        assert infer_race_type("Cherry Pie Criterium") == RaceType.CRITERIUM
        assert infer_race_type("Seward Park Criterium") == RaceType.CRITERIUM
        assert infer_race_type("PIR Short Track Criterium") == RaceType.CRITERIUM

    def test_grand_prix_is_criterium(self):
        assert infer_race_type("Gastown Grand Prix") == RaceType.CRITERIUM
        assert infer_race_type("Marymoor Grand Prix") == RaceType.CRITERIUM

    def test_stage_race_from_name(self):
        assert infer_race_type("Mutual of Enumclaw Stage Race") == RaceType.STAGE_RACE
        assert infer_race_type("Tour de Bloom Stage Race") == RaceType.STAGE_RACE
        assert infer_race_type("Tour de Delta") == RaceType.STAGE_RACE

    def test_hill_climb_from_name(self):
        assert infer_race_type("Mount Tabor Hill Climb") == RaceType.HILL_CLIMB

    def test_gravel_from_name(self):
        assert infer_race_type("Gorge Roubaix") == RaceType.GRAVEL

    def test_road_race_default(self):
        assert infer_race_type("Banana Belt Road Race") == RaceType.ROAD_RACE
        assert infer_race_type("Mason Lake Road Race") == RaceType.ROAD_RACE
        assert infer_race_type("Some Unknown Race") == RaceType.ROAD_RACE

    def test_case_insensitive(self):
        assert infer_race_type("TWILIGHT CRITERIUM") == RaceType.CRITERIUM
        assert infer_race_type("mount baker hill climb") == RaceType.HILL_CLIMB

    def test_all_pnw_races_classified(self):
        """Every race in the demo list gets a non-None type."""
        from raceanalyzer.demo import PNW_RACES

        for name, _, _ in PNW_RACES:
            result = infer_race_type(name)
            assert result is not None
            assert isinstance(result, RaceType)

    def test_expected_distribution(self):
        """The 25 PNW race names should produce a reasonable distribution."""
        from raceanalyzer.demo import PNW_RACES

        types = [infer_race_type(name) for name, _, _ in PNW_RACES]
        assert types.count(RaceType.CRITERIUM) >= 6
        assert types.count(RaceType.ROAD_RACE) >= 4
        assert types.count(RaceType.STAGE_RACE) >= 2
        assert types.count(RaceType.HILL_CLIMB) >= 1
