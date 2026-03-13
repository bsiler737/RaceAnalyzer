"""Tests for feed item expansion logic (Sprint 017)."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from raceanalyzer.queries import _expand_feed_items, countdown_label


def _make_base_item(series_id=1, race_type="road_race", upcoming_date=None, **kw):
    """Create a minimal feed item dict for testing."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if upcoming_date is None:
        upcoming_date = datetime(2026, 6, 15)
    days = (upcoming_date - today).days if upcoming_date else None
    item = {
        "series_id": series_id,
        "display_name": kw.get("display_name", "Test Race"),
        "location": "Portland",
        "state_province": "OR",
        "is_upcoming": upcoming_date is not None,
        "upcoming_date": upcoming_date,
        "days_until": days,
        "countdown_label": countdown_label(days),
        "most_recent_date": datetime(2025, 6, 15),
        "race_type": race_type,
        "discipline": "road",
        "predicted_finish_type": "bunch_sprint",
        "confidence": "high",
        "prediction_source": "time_gap",
        "course_type": "flat",
        "distance_m": 40000,
        "total_gain_m": 100,
        "drop_rate_pct": 10,
        "drop_rate_label": "low",
        "field_size_display": "Usually 40 starters",
        "field_size_median": 40,
        "teammate_names": [],
        "elevation_sparkline_points": None,
        "climbs_json": None,
        "typical_field_duration_min": 60,
        "rwgps_encoded_polyline": None,
        "distribution_json": None,
        "registration_url": None,
        "edition_count": 3,
    }
    item.update(kw)
    return item


def _make_race(id, name, date, series_id):
    return SimpleNamespace(id=id, name=name, date=date, series_id=series_id)


class TestPassthrough:
    def test_single_upcoming_race_passthrough(self):
        item = _make_base_item(series_id=1)
        race = _make_race(10, "Test Race", datetime(2026, 6, 15), 1)
        result = _expand_feed_items([item], {1: [race]})
        assert len(result) == 1
        assert result[0]["occurrence_key"] == "1:series"
        assert result[0]["occurrence_kind"] == "series"

    def test_historical_only_passthrough(self):
        item = _make_base_item(series_id=1, upcoming_date=None)
        item["is_upcoming"] = False
        item["days_until"] = None
        race = _make_race(10, "Test Race", datetime(2024, 6, 15), 1)
        result = _expand_feed_items([item], {1: [race]})
        assert len(result) == 1
        assert result[0]["occurrence_kind"] == "series"


class TestMultiEditionExpansion:
    def test_two_upcoming_races_expand(self):
        item = _make_base_item(series_id=42, display_name="Mason Lake")
        race1 = _make_race(100, "Mason Lake 1", datetime(2026, 3, 21), 42)
        race2 = _make_race(101, "Mason Lake 2", datetime(2026, 3, 28), 42)
        result = _expand_feed_items([item], {42: [race1, race2]})
        assert len(result) == 2
        assert result[0]["display_name"] == "Mason Lake 1"
        assert result[1]["display_name"] == "Mason Lake 2"
        assert result[0]["occurrence_kind"] == "edition"
        assert result[0]["occurrence_key"] == "42:edition:100"
        assert result[1]["occurrence_key"] == "42:edition:101"
        # Both share same series_id
        assert result[0]["series_id"] == 42
        assert result[1]["series_id"] == 42

    def test_single_upcoming_not_expanded(self):
        item = _make_base_item(series_id=42, display_name="Mason Lake")
        race1 = _make_race(100, "Mason Lake 1", datetime(2026, 3, 21), 42)
        race_past = _make_race(99, "Mason Lake 2025", datetime(2025, 3, 22), 42)
        result = _expand_feed_items([item], {42: [race1, race_past]})
        assert len(result) == 1
        assert result[0]["occurrence_kind"] == "series"

    def test_edition_dates_correct(self):
        item = _make_base_item(series_id=42, display_name="Mason Lake")
        race1 = _make_race(100, "Mason Lake 1", datetime(2026, 3, 21), 42)
        race2 = _make_race(101, "Mason Lake 2", datetime(2026, 3, 28), 42)
        result = _expand_feed_items([item], {42: [race1, race2]})
        assert result[0]["upcoming_date"] == datetime(2026, 3, 21)
        assert result[1]["upcoming_date"] == datetime(2026, 3, 28)


class TestStageRaceExpansion:
    def test_stage_race_with_yaml_expands(self):
        item = _make_base_item(
            series_id=50,
            race_type="stage_race",
            display_name="Tour de Bloom",
        )
        result = _expand_feed_items([item], {50: []})
        assert len(result) == 6
        assert "Mission Ridge Hill Climb" in result[0]["display_name"]
        assert result[0]["race_type"] == "hill_climb"
        assert result[0]["occurrence_kind"] == "stage"
        assert result[0]["occurrence_key"] == "50:stage:1"

    def test_stage_race_without_yaml_passthrough(self):
        item = _make_base_item(
            series_id=99,
            race_type="stage_race",
            display_name="Unknown Stage Race",
        )
        result = _expand_feed_items([item], {99: []})
        assert len(result) == 1
        assert result[0]["occurrence_kind"] == "series"

    def test_stage_race_no_upcoming_date_passthrough(self):
        item = _make_base_item(
            series_id=50,
            race_type="stage_race",
            display_name="Tour de Bloom",
            upcoming_date=None,
        )
        item["is_upcoming"] = False
        item["upcoming_date"] = None
        result = _expand_feed_items([item], {50: []})
        assert len(result) == 1
        assert result[0]["occurrence_kind"] == "series"

    def test_elites_only_name_suffix(self):
        item = _make_base_item(
            series_id=50,
            race_type="stage_race",
            display_name="Tour de Bloom",
        )
        result = _expand_feed_items([item], {50: []})
        # Stages 5 and 6 are elites_only
        assert "(Elites)" in result[4]["display_name"]
        assert "(Elites)" in result[5]["display_name"]
        assert "(Elites)" not in result[0]["display_name"]

    def test_stage_display_name_format(self):
        item = _make_base_item(
            series_id=50,
            race_type="stage_race",
            display_name="Tour de Bloom",
        )
        result = _expand_feed_items([item], {50: []})
        assert result[0]["display_name"] == "Tour de Bloom: Mission Ridge Hill Climb"
        assert result[2]["display_name"] == "Tour de Bloom: Downtown Wenatchee Criterium"

    def test_stage_race_types_correct(self):
        item = _make_base_item(
            series_id=50,
            race_type="stage_race",
            display_name="Tour de Bloom",
        )
        result = _expand_feed_items([item], {50: []})
        types = [r["race_type"] for r in result]
        assert types == [
            "hill_climb", "road_race", "criterium",
            "road_race", "time_trial", "road_race",
        ]

    def test_stage_shares_parent_series_id(self):
        item = _make_base_item(
            series_id=50,
            race_type="stage_race",
            display_name="Tour de Bloom",
        )
        result = _expand_feed_items([item], {50: []})
        for r in result:
            assert r["series_id"] == 50


class TestPostExpansionFiltering:
    def test_criterium_filter_shows_tdb_stage_3(self):
        """Race type filter on expanded items should include TdB Stage 3."""
        item = _make_base_item(
            series_id=50,
            race_type="stage_race",
            display_name="Tour de Bloom",
        )
        expanded = _expand_feed_items([item], {50: []})
        # Simulate post-expansion filter for "criterium"
        filtered = [
            i for i in expanded
            if i.get("race_type") == "criterium"
        ]
        assert len(filtered) == 1
        assert "Criterium" in filtered[0]["display_name"]
