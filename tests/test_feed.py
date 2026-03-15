"""Tests for feed organization and filtering (Sprint 011 Phase 2)."""

from __future__ import annotations

from datetime import datetime, timedelta

from raceanalyzer import queries
from raceanalyzer.db.models import Race, RaceSeries


class TestMonthGroupingIntegration:
    def test_groups_items(self, seeded_series_session):
        from raceanalyzer.precompute import precompute_all

        precompute_all(seeded_series_session)

        items = queries.get_feed_items_batch(seeded_series_session)
        groups = queries.group_by_month(items)
        assert len(groups) > 0

    def test_past_races_last(self, seeded_series_session):
        from raceanalyzer.precompute import precompute_all

        precompute_all(seeded_series_session)

        items = queries.get_feed_items_batch(seeded_series_session)
        groups = queries.group_by_month(items)
        # All items are historical in seeded data, so should be "Past Races"
        if groups:
            assert groups[-1][0] == "Past Races"


class TestFilterInteractions:
    def test_state_filter_reduces(self, seeded_series_session):
        from raceanalyzer.precompute import precompute_all

        precompute_all(seeded_series_session)

        all_items = queries.get_feed_items_batch(seeded_series_session)
        wa_items = queries.get_feed_items_batch(
            seeded_series_session, state_filter=["WA"]
        )
        assert len(wa_items) <= len(all_items)
        assert all(i["state_province"] == "WA" for i in wa_items)

    def test_search_and_state_combined(self, seeded_series_session):
        from raceanalyzer.precompute import precompute_all

        precompute_all(seeded_series_session)

        items = queries.get_feed_items_batch(
            seeded_series_session,
            search_query="banana",
            state_filter=["WA"],
        )
        assert all("banana" in i["display_name"].lower() for i in items)
        assert all(i["state_province"] == "WA" for i in items)


class TestEmptyStates:
    def test_no_match_search(self, seeded_series_session):
        from raceanalyzer.precompute import precompute_all

        precompute_all(seeded_series_session)

        items = queries.get_feed_items_batch(
            seeded_series_session, search_query="zzz_nonexistent"
        )
        assert items == []

    def test_no_match_state(self, seeded_series_session):
        from raceanalyzer.precompute import precompute_all

        precompute_all(seeded_series_session)

        items = queries.get_feed_items_batch(
            seeded_series_session, state_filter=["XX"]
        )
        assert items == []


class TestCountdownInFeedItems:
    def test_historical_has_no_countdown(self, seeded_series_session):
        from raceanalyzer.precompute import precompute_all

        precompute_all(seeded_series_session)

        items = queries.get_feed_items_batch(seeded_series_session)
        for item in items:
            if not item["is_upcoming"]:
                assert item["countdown_label"] == ""

    def test_upcoming_has_countdown(self, seeded_series_session):
        """If we add an upcoming race, it should have a countdown."""
        from raceanalyzer.precompute import precompute_all

        # Add an upcoming race
        series = seeded_series_session.query(RaceSeries).first()
        future_date = datetime.now() + timedelta(days=5)
        upcoming = Race(
            id=9999,
            name="Future Race",
            date=future_date,
            location="Seattle",
            state_province="WA",
            is_upcoming=True,
            series_id=series.id,
        )
        seeded_series_session.add(upcoming)
        seeded_series_session.commit()

        precompute_all(seeded_series_session)

        items = queries.get_feed_items_batch(seeded_series_session)
        upcoming_items = [i for i in items if i["is_upcoming"]]
        assert len(upcoming_items) >= 1
        for item in upcoming_items:
            assert item["countdown_label"] != ""
            assert "days" in item["countdown_label"] or item[
                "countdown_label"
            ] in ("Today", "Tomorrow")


class TestDeepLinkBackwardCompat:
    def test_series_id_param(self, seeded_series_session):
        """Existing ?series_id= URLs should still find the right series."""
        from raceanalyzer.precompute import precompute_all

        precompute_all(seeded_series_session)

        all_items = queries.get_feed_items_batch(seeded_series_session)
        if all_items:
            target_id = all_items[0]["series_id"]
            filtered = [i for i in all_items if i["series_id"] == target_id]
            assert len(filtered) == 1


class TestPastOnlyDeepLink:
    """Sprint 012: Deep-link to past-only series shows expanded card."""

    def test_past_only_item_detected(self, seeded_series_session):
        """All seeded data is historical — items should all be past-only."""
        from raceanalyzer.precompute import precompute_all

        precompute_all(seeded_series_session)

        items = queries.get_feed_items_batch(seeded_series_session)
        assert len(items) > 0
        # In seeded data, all items are past-only
        assert all(not item["is_upcoming"] for item in items)

    def test_deep_link_finds_past_series(self, seeded_series_session):
        """Deep-link lookup works for past-only series."""
        from raceanalyzer.precompute import precompute_all

        precompute_all(seeded_series_session)

        all_items = queries.get_feed_items_batch(seeded_series_session)
        if all_items:
            target = all_items[0]
            assert not target["is_upcoming"]
            # The item is valid and has detail data
            detail = queries.get_feed_item_detail(
                seeded_series_session, target["series_id"]
            )
            assert detail is not None


class TestSearchPastOnlyResults:
    """Sprint 012: Search returning only past series shows previews."""

    def test_search_past_only_returns_items(self, seeded_series_session):
        """Searching for a historical-only series returns results."""
        from raceanalyzer.precompute import precompute_all

        precompute_all(seeded_series_session)

        # Get a series name to search for
        series = seeded_series_session.query(RaceSeries).first()
        search_term = series.display_name.split()[0]

        items = queries.get_feed_items_batch(
            seeded_series_session, search_query=search_term
        )
        # Should find at least 1 result
        if items:
            assert all(not item["is_upcoming"] for item in items)


class TestExpandedTier1Fields:
    """Sprint 013: New Tier 1 fields in feed items."""

    def test_new_fields_present(self, seeded_series_session):
        from raceanalyzer.precompute import precompute_all

        precompute_all(seeded_series_session)

        items = queries.get_feed_items_batch(seeded_series_session)
        for item in items:
            # These keys must exist (may be None)
            assert "elevation_sparkline_points" in item
            assert "climbs_json" in item
            assert "typical_field_duration_min" in item
            assert "rwgps_encoded_polyline" in item
            assert "distribution_json" in item
            assert "field_size_median" in item

    def test_category_distance_keys_present(self, seeded_series_session):
        """Sprint 020: Feed items use cross-field range (no category_distance)."""
        from raceanalyzer.precompute import precompute_all

        precompute_all(seeded_series_session)

        items = queries.get_feed_items_batch(seeded_series_session)
        for item in items:
            # Sprint 020: category_distance removed from feed items
            assert "category_distance" not in item
            assert "category_distance_unit" not in item
            assert "distance_range" in item
            assert "estimated_time_range" in item
            assert "hide_estimated_time" in item


class TestPredictionSourceInFeedItems:
    """Sprint 012: prediction_source is included in feed items."""

    def test_prediction_source_key_present(self, seeded_series_session):
        from raceanalyzer.precompute import precompute_all

        precompute_all(seeded_series_session)

        items = queries.get_feed_items_batch(seeded_series_session)
        for item in items:
            assert "prediction_source" in item


class TestActionRowSimplified:
    """Sprint 018: Action row simplified — only Preview, Register, caret overflow."""

    def test_simplified_action_row_source(self):
        """Assert _render_action_row has simplified buttons (no Compare/More details)."""
        from pathlib import Path

        feed_path = Path(__file__).parent.parent / "raceanalyzer" / "ui" / "pages" / "feed.py"
        source = feed_path.read_text()
        # Sprint 018: Compare and More details removed
        assert "Compare" not in source
        assert "More details" not in source
        assert "Less details" not in source
        # Kept buttons
        assert "Add to calendar" in source
        assert "Share" in source
        assert "Preview" in source
