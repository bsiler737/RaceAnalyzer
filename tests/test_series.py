"""Tests for race series name normalization and grouping."""

from __future__ import annotations

from datetime import datetime

import pytest

from raceanalyzer.db.models import Race, RaceSeries
from raceanalyzer.series import build_series, normalize_race_name, pick_display_name


class TestNormalizeRaceName:
    def test_strips_year_prefix(self):
        assert normalize_race_name("2024 Banana Belt RR") == "banana belt road race"

    def test_strips_year_suffix(self):
        assert normalize_race_name("Banana Belt Road Race 2023") == "banana belt road race"

    def test_strips_roman_numerals(self):
        assert normalize_race_name("Pacific Raceways XXI") == "pacific raceways"

    def test_strips_roman_numeral_i(self):
        assert normalize_race_name("Mason Lake I") == "mason lake"

    def test_strips_roman_numeral_ii(self):
        assert normalize_race_name("Mason Lake II") == "mason lake"

    def test_strips_ordinals(self):
        result = normalize_race_name("21st Annual Mutual of Enumclaw")
        assert result == "mutual of enumclaw"

    def test_normalizes_rr_suffix(self):
        assert normalize_race_name("Banana Belt RR") == "banana belt road race"

    def test_normalizes_crit_suffix(self):
        assert normalize_race_name("Cherry Pie Crit") == "cherry pie criterium"

    def test_normalizes_tt_suffix(self):
        assert normalize_race_name("Twilight TT") == "twilight time trial"

    def test_strips_sponsor_noise(self):
        result = normalize_race_name("Cascade Classic Presented by Acme Corp")
        assert result == "cascade classic"

    def test_preserves_meaningful_words(self):
        result = normalize_race_name("Stage Race of Champions")
        assert "stage race" in result

    def test_consistent_across_editions(self):
        """Different editions of the same race should normalize identically."""
        names = [
            "2022 Banana Belt RR",
            "2023 Banana Belt RR",
            "Banana Belt Road Race 2024",
            "Banana Belt RR",
        ]
        normalized = {normalize_race_name(n) for n in names}
        assert len(normalized) == 1

    def test_mason_lake_editions_same(self):
        """Mason Lake I and Mason Lake II should normalize to the same key."""
        assert normalize_race_name("Mason Lake I") == normalize_race_name("Mason Lake II")

    def test_empty_string(self):
        result = normalize_race_name("")
        assert result == ""


class TestPickDisplayName:
    def test_picks_longest(self):
        names = ["Banana Belt RR", "Banana Belt Road Race 2024"]
        result = pick_display_name(names)
        assert "Banana Belt Road Race" in result
        assert "2024" not in result

    def test_strips_year(self):
        result = pick_display_name(["2024 Banana Belt RR"])
        assert "2024" not in result

    def test_empty_list(self):
        assert pick_display_name([]) == "Unknown Series"


class TestBuildSeries:
    def test_creates_series(self, seeded_session):
        """Build series groups the 3 Banana Belt races together."""
        result = build_series(seeded_session)
        assert result["series_created"] > 0
        assert result["races_linked"] == 5  # All 5 races get linked

    def test_idempotent(self, seeded_session):
        """Running build_series twice doesn't create duplicates."""
        build_series(seeded_session)
        result2 = build_series(seeded_session)
        assert result2["series_created"] == 0
        assert result2["races_linked"] == 0

    def test_banana_belt_grouped(self, seeded_session):
        """All 3 Banana Belt races share the same series."""
        build_series(seeded_session)
        bb_races = (
            seeded_session.query(Race)
            .filter(Race.name.like("%Banana Belt%"))
            .all()
        )
        series_ids = {r.series_id for r in bb_races}
        assert len(series_ids) == 1
        assert None not in series_ids

    def test_different_races_separate(self, seeded_session):
        """Cherry Pie Crit and PIR Short Track are in different series."""
        build_series(seeded_session)
        cherry = seeded_session.query(Race).filter(Race.id == 2).first()
        pir = seeded_session.query(Race).filter(Race.id == 4).first()
        assert cherry.series_id != pir.series_id

    def test_series_count(self, seeded_session):
        """5 races (3 BB, 1 Cherry Pie, 1 PIR) -> 3 series."""
        build_series(seeded_session)
        count = seeded_session.query(RaceSeries).count()
        assert count == 3
