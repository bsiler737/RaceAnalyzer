"""Tests for feed item expansion logic (Sprint 017, updated Sprint 021 for DB-based stages)."""

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
        "ai_context": {
            "mode": "overall",
            "ai_sez_text": "Test prediction",
            "best_finish_type": "bunch_sprint",
            "overall_finish_type": "bunch_sprint",
            "prediction_source": "time_gap",
            "course_type": "flat",
            "selected_category": None,
            "matched_categories": [],
            "best_category": None,
        },
    }
    item.update(kw)
    return item


def _make_race(id, name, date, series_id):
    return SimpleNamespace(id=id, name=name, date=date, series_id=series_id)


# Tour de Bloom test children (DB-based)
def _make_tdb_children(parent_id=50):
    """Create DB-based children_by_parent for Tour de Bloom."""
    return {
        parent_id: [
            {
                "series_id": 807, "parent_series_id": parent_id, "stage_number": 1,
                "display_name": "Tour de Bloom: Mission Ridge Hill Climb",
                "race_type": "hill_climb", "discipline": "road",
                "course_type": "mountainous", "distance_m": 46500, "total_gain_m": 1243,
                "elevation_sparkline_points": None, "climbs_json": None,
                "rwgps_encoded_polyline": "test_poly", "predicted_finish_type": "breakaway_selective",
                "confidence": "moderate", "prediction_source": "course_profile",
                "upcoming_date": datetime(2026, 5, 14), "registration_url": None,
            },
            {
                "series_id": 808, "parent_series_id": parent_id, "stage_number": 2,
                "display_name": "Tour de Bloom: Waterville Road Race",
                "race_type": "road_race", "discipline": "road",
                "course_type": "hilly", "distance_m": 90700, "total_gain_m": 942,
                "elevation_sparkline_points": None, "climbs_json": None,
                "rwgps_encoded_polyline": "test_poly2", "predicted_finish_type": "breakaway_selective",
                "confidence": "low", "prediction_source": "course_profile",
                "upcoming_date": datetime(2026, 5, 15), "registration_url": None,
            },
            {
                "series_id": 809, "parent_series_id": parent_id, "stage_number": 3,
                "display_name": "Tour de Bloom: Downtown Wenatchee Criterium",
                "race_type": "criterium", "discipline": "road",
                "course_type": "rolling", "distance_m": 800, "total_gain_m": 7,
                "elevation_sparkline_points": None, "climbs_json": None,
                "rwgps_encoded_polyline": "test_poly3", "predicted_finish_type": "bunch_sprint",
                "confidence": "low", "prediction_source": "course_profile",
                "upcoming_date": datetime(2026, 5, 16), "registration_url": None,
            },
            {
                "series_id": 810, "parent_series_id": parent_id, "stage_number": 4,
                "display_name": "Tour de Bloom: Plain Road Race",
                "race_type": "road_race", "discipline": "road",
                "course_type": "hilly", "distance_m": 82100, "total_gain_m": 844,
                "elevation_sparkline_points": None, "climbs_json": None,
                "rwgps_encoded_polyline": "test_poly4", "predicted_finish_type": "breakaway_selective",
                "confidence": "low", "prediction_source": "course_profile",
                "upcoming_date": datetime(2026, 5, 17), "registration_url": None,
            },
            {
                "series_id": 811, "parent_series_id": parent_id, "stage_number": 5,
                "display_name": "Tour de Bloom: 19 km Time Trial (Elites)",
                "race_type": "time_trial", "discipline": "road",
                "course_type": None, "distance_m": None, "total_gain_m": None,
                "elevation_sparkline_points": None, "climbs_json": None,
                "rwgps_encoded_polyline": None, "predicted_finish_type": None,
                "confidence": None, "prediction_source": None,
                "upcoming_date": datetime(2026, 5, 18), "registration_url": None,
            },
            {
                "series_id": 812, "parent_series_id": parent_id, "stage_number": 6,
                "display_name": "Tour de Bloom: Ed Farrar Queen Stage (Elites)",
                "race_type": "road_race", "discipline": "road",
                "course_type": None, "distance_m": None, "total_gain_m": None,
                "elevation_sparkline_points": None, "climbs_json": None,
                "rwgps_encoded_polyline": None, "predicted_finish_type": None,
                "confidence": None, "prediction_source": None,
                "upcoming_date": datetime(2026, 5, 19), "registration_url": None,
            },
        ]
    }


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
    """Sprint 021: DB-based stage expansion."""

    def test_stage_race_with_db_children_expands(self):
        item = _make_base_item(
            series_id=50,
            race_type="stage_race",
            display_name="Tour de Bloom",
        )
        children = _make_tdb_children(50)
        result = _expand_feed_items([item], {50: []}, children_by_parent=children)
        # 1 header + 6 stages = 7
        assert len(result) == 7
        assert result[0]["occurrence_kind"] == "stage_header"
        assert result[0]["stage_count"] == 6
        assert "Mission Ridge Hill Climb" in result[1]["display_name"]
        assert result[1]["race_type"] == "hill_climb"
        assert result[1]["occurrence_kind"] == "stage"
        assert result[1]["occurrence_key"] == "50:stage:1"

    def test_stage_race_without_children_passthrough(self):
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
        children = _make_tdb_children(50)
        result = _expand_feed_items([item], {50: []}, children_by_parent=children)
        assert len(result) == 1
        assert result[0]["occurrence_kind"] == "series"

    def test_elites_only_name_suffix(self):
        item = _make_base_item(
            series_id=50,
            race_type="stage_race",
            display_name="Tour de Bloom",
        )
        children = _make_tdb_children(50)
        result = _expand_feed_items([item], {50: []}, children_by_parent=children)
        # Skip header (index 0), stages at indices 1-6
        assert "(Elites)" in result[5]["display_name"]  # Stage 5
        assert "(Elites)" in result[6]["display_name"]  # Stage 6
        assert "(Elites)" not in result[1]["display_name"]  # Stage 1

    def test_stage_display_name_format(self):
        item = _make_base_item(
            series_id=50,
            race_type="stage_race",
            display_name="Tour de Bloom",
        )
        children = _make_tdb_children(50)
        result = _expand_feed_items([item], {50: []}, children_by_parent=children)
        assert result[1]["display_name"] == "Tour de Bloom: Mission Ridge Hill Climb"
        assert result[3]["display_name"] == "Tour de Bloom: Downtown Wenatchee Criterium"

    def test_stage_race_types_correct(self):
        item = _make_base_item(
            series_id=50,
            race_type="stage_race",
            display_name="Tour de Bloom",
        )
        children = _make_tdb_children(50)
        result = _expand_feed_items([item], {50: []}, children_by_parent=children)
        # Skip header at index 0
        types = [r["race_type"] for r in result[1:]]
        assert types == [
            "hill_climb", "road_race", "criterium",
            "road_race", "time_trial", "road_race",
        ]

    def test_stage_children_have_own_series_id(self):
        """Sprint 021: Each stage is its own series with a unique series_id."""
        item = _make_base_item(
            series_id=50,
            race_type="stage_race",
            display_name="Tour de Bloom",
        )
        children = _make_tdb_children(50)
        result = _expand_feed_items([item], {50: []}, children_by_parent=children)
        # Stage children have their own series_id (not parent's)
        assert result[1]["series_id"] == 807  # Mission Ridge
        assert result[2]["series_id"] == 808  # Waterville
        assert result[1]["parent_series_id"] == 50

    def test_stage_children_have_per_stage_data(self):
        """Sprint 021: Each stage card shows its own course/prediction data."""
        item = _make_base_item(
            series_id=50,
            race_type="stage_race",
            display_name="Tour de Bloom",
        )
        children = _make_tdb_children(50)
        result = _expand_feed_items([item], {50: []}, children_by_parent=children)
        # Mission Ridge Hill Climb has mountainous terrain
        assert result[1]["course_type"] == "mountainous"
        assert result[1]["distance_m"] == 46500
        # Waterville Road Race has hilly terrain
        assert result[2]["course_type"] == "hilly"
        assert result[2]["distance_m"] == 90700
        # TT stage has no course data
        assert result[5]["course_type"] is None
        assert result[5]["distance_m"] is None

    def test_stage_header_included(self):
        """Sprint 021: A group header is included before stage children."""
        item = _make_base_item(
            series_id=50,
            race_type="stage_race",
            display_name="Tour de Bloom",
        )
        children = _make_tdb_children(50)
        result = _expand_feed_items([item], {50: []}, children_by_parent=children)
        assert result[0]["occurrence_kind"] == "stage_header"
        assert result[0]["display_name"] == "Tour de Bloom"
        assert result[0]["stage_count"] == 6

    def test_stage_anchor_date(self):
        """Sprint 021: Stage children have anchor date for sort grouping."""
        item = _make_base_item(
            series_id=50,
            race_type="stage_race",
            display_name="Tour de Bloom",
        )
        children = _make_tdb_children(50)
        result = _expand_feed_items([item], {50: []}, children_by_parent=children)
        # All children should have the earliest stage date as anchor
        for child in result[1:]:
            assert child["stage_anchor_date"] == datetime(2026, 5, 14)


class TestPostExpansionFiltering:
    def test_criterium_filter_shows_tdb_stage_3(self):
        """Race type filter on expanded items should include TdB Stage 3."""
        item = _make_base_item(
            series_id=50,
            race_type="stage_race",
            display_name="Tour de Bloom",
        )
        children = _make_tdb_children(50)
        expanded = _expand_feed_items([item], {50: []}, children_by_parent=children)
        # Simulate post-expansion filter for "criterium"
        filtered = [
            i for i in expanded
            if i.get("race_type") == "criterium"
        ]
        assert len(filtered) == 1
        assert "Criterium" in filtered[0]["display_name"]
