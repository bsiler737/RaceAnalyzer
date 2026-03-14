"""Tests for the query/aggregation layer."""

from __future__ import annotations

import pytest

from raceanalyzer import queries
from raceanalyzer.config import Settings


class TestGetRaces:
    def test_returns_all_races(self, seeded_session):
        df = queries.get_races(seeded_session)
        assert len(df) == 5

    def test_filter_by_year(self, seeded_session):
        df = queries.get_races(seeded_session, year=2022)
        assert len(df) == 2

    def test_filter_by_states(self, seeded_session):
        df = queries.get_races(seeded_session, states=["OR"])
        assert len(df) == 2

    def test_filter_by_multiple_states(self, seeded_session):
        df = queries.get_races(seeded_session, states=["WA", "OR"])
        assert len(df) == 5

    def test_empty_db(self, session):
        df = queries.get_races(session)
        assert df.empty

    def test_has_expected_columns(self, seeded_session):
        df = queries.get_races(seeded_session)
        assert "id" in df.columns
        assert "name" in df.columns
        assert "num_categories" in df.columns

    def test_limit(self, seeded_session):
        df = queries.get_races(seeded_session, limit=2)
        assert len(df) == 2


class TestGetRaceDetail:
    def test_returns_detail(self, seeded_session):
        detail = queries.get_race_detail(seeded_session, 1)
        assert detail is not None
        assert detail["race"]["name"] == "Banana Belt RR"
        assert len(detail["classifications"]) == 3

    def test_nonexistent_race(self, seeded_session):
        detail = queries.get_race_detail(seeded_session, 999)
        assert detail is None

    def test_classifications_have_confidence(self, seeded_session):
        detail = queries.get_race_detail(seeded_session, 1)
        cls_df = detail["classifications"]
        assert "confidence_label" in cls_df.columns
        assert "confidence_color" in cls_df.columns
        assert "qualifier" in cls_df.columns

    def test_results_included(self, seeded_session):
        detail = queries.get_race_detail(seeded_session, 1)
        assert not detail["results"].empty
        assert len(detail["results"]) == 30  # 3 categories * 10 riders


class TestGetFinishTypeDistribution:
    def test_overall_distribution(self, seeded_session):
        df = queries.get_finish_type_distribution(seeded_session)
        assert not df.empty
        assert "finish_type" in df.columns
        assert "count" in df.columns
        assert "percentage" in df.columns
        assert df["percentage"].sum() == pytest.approx(100.0, abs=0.5)

    def test_has_multiple_types(self, seeded_session):
        df = queries.get_finish_type_distribution(seeded_session)
        assert len(df) >= 2  # At least bunch_sprint and breakaway

    def test_filtered_by_category(self, seeded_session):
        df = queries.get_finish_type_distribution(
            seeded_session, category="Men Cat 1/2"
        )
        assert not df.empty

    def test_empty_db(self, session):
        df = queries.get_finish_type_distribution(session)
        assert df.empty


class TestGetFinishTypeTrend:
    def test_trend_has_multiple_years(self, seeded_session):
        df = queries.get_finish_type_trend(seeded_session)
        assert df["year"].nunique() >= 2

    def test_empty_db(self, session):
        df = queries.get_finish_type_trend(session)
        assert df.empty

    def test_filtered_by_category(self, seeded_session):
        df = queries.get_finish_type_trend(seeded_session, category="Men Cat 1/2")
        assert not df.empty


class TestGetCategories:
    def test_returns_categories(self, seeded_session):
        cats = queries.get_categories(seeded_session)
        assert "Men Cat 1/2" in cats
        assert len(cats) == 3

    def test_empty_db(self, session):
        cats = queries.get_categories(session)
        assert cats == []


class TestGetAvailableYears:
    def test_returns_years(self, seeded_session):
        years = queries.get_available_years(seeded_session)
        assert 2022 in years
        assert 2023 in years
        assert 2024 in years

    def test_descending_order(self, seeded_session):
        years = queries.get_available_years(seeded_session)
        assert years == sorted(years, reverse=True)


class TestGetAvailableStates:
    def test_returns_states(self, seeded_session):
        states = queries.get_available_states(seeded_session)
        assert "WA" in states
        assert "OR" in states


class TestConfidenceLabel:
    def test_high_confidence(self):
        label, color, qualifier = queries.confidence_label(0.003)
        assert label == "High confidence"
        assert color == "green"
        assert qualifier == "Likely"

    def test_moderate_confidence(self):
        label, color, qualifier = queries.confidence_label(0.01)
        assert label == "Moderate confidence"
        assert color == "orange"
        assert qualifier == "Probable"

    def test_low_confidence(self):
        label, color, qualifier = queries.confidence_label(0.03)
        assert label == "Low confidence"
        assert color == "red"
        assert qualifier == "Possible"

    def test_none(self):
        label, color, qualifier = queries.confidence_label(None)
        assert label == "Unknown"
        assert color == "gray"

    def test_custom_thresholds(self):
        settings = Settings(confidence_high_threshold=0.01, confidence_medium_threshold=0.05)
        label, color, _ = queries.confidence_label(0.008, settings)
        assert label == "High confidence"


class TestRaceTypeDisplayName:
    def test_criterium(self):
        assert queries.race_type_display_name("criterium") == "Criterium"

    def test_road_race(self):
        assert queries.race_type_display_name("road_race") == "Road Race"

    def test_unknown_value(self):
        result = queries.race_type_display_name("some_new_type")
        assert result == "Some New Type"


class TestGetRaceTiles:
    def test_returns_tile_columns(self, seeded_session):
        df = queries.get_race_tiles(seeded_session)
        expected_cols = {
            "id", "name", "date", "location", "state_province",
            "race_type", "course_lat", "course_lon", "num_categories",
            "overall_finish_type",
        }
        assert expected_cols == set(df.columns)

    def test_returns_all_races(self, seeded_session):
        df = queries.get_race_tiles(seeded_session)
        assert len(df) == 5

    def test_year_filter(self, seeded_session):
        df = queries.get_race_tiles(seeded_session, year=2022)
        assert len(df) == 2

    def test_state_filter(self, seeded_session):
        df = queries.get_race_tiles(seeded_session, states=["OR"])
        assert len(df) == 2

    def test_empty_db(self, session):
        df = queries.get_race_tiles(session)
        assert df.empty
        assert "race_type" in df.columns


class TestGetScaryRacers:
    def test_returns_expected_columns(self, seeded_session):
        df = queries.get_scary_racers(seeded_session, 1, "Men Cat 1/2")
        assert "name" in df.columns
        assert "carried_points" in df.columns
        assert "wins" in df.columns

    def test_empty_for_missing_race(self, session):
        df = queries.get_scary_racers(session, 99999, "Men Pro/1/2")
        assert df.empty

    def test_empty_for_unknown_category(self, seeded_session):
        df = queries.get_scary_racers(seeded_session, 1, "Nonexistent Cat")
        assert df.empty

    def test_top_n_limits_results(self, seeded_session):
        df = queries.get_scary_racers(seeded_session, 1, "Men Cat 1/2", top_n=2)
        assert len(df) <= 2


class TestFinishTypeDisplayName:
    def test_bunch_sprint(self):
        assert queries.finish_type_display_name("bunch_sprint") == "Bunch Sprint"

    def test_gc_selective(self):
        assert queries.finish_type_display_name("gc_selective") == "GC Selective"

    def test_unknown_value(self):
        result = queries.finish_type_display_name("some_new_type")
        assert result == "Some New Type"


class TestGetSeriesTiles:
    def test_returns_expected_columns(self, seeded_series_session):
        df = queries.get_series_tiles(seeded_series_session)
        expected_cols = {
            "series_id", "display_name", "edition_count", "earliest_date",
            "latest_date", "location", "state_province", "overall_finish_type",
        }
        assert expected_cols == set(df.columns)

    def test_groups_banana_belt(self, seeded_series_session):
        """3 Banana Belt races -> 1 series tile."""
        df = queries.get_series_tiles(seeded_series_session)
        bb = df[df["display_name"].str.contains("Banana Belt")]
        assert len(bb) == 1
        assert bb.iloc[0]["edition_count"] == 3

    def test_total_series_count(self, seeded_series_session):
        """5 races -> 3 series (3 BB, 1 Cherry Pie, 1 PIR)."""
        df = queries.get_series_tiles(seeded_series_session)
        assert len(df) == 3

    def test_empty_db(self, session):
        df = queries.get_series_tiles(session)
        assert df.empty

    def test_year_filter(self, seeded_series_session):
        df = queries.get_series_tiles(seeded_series_session, year=2022)
        # 2022 has Banana Belt + Cherry Pie = 2 series
        assert len(df) == 2


class TestGetSeriesDetail:
    def test_returns_detail(self, seeded_series_session):
        # Find the Banana Belt series
        from raceanalyzer.db.models import RaceSeries
        bb = (
            seeded_series_session.query(RaceSeries)
            .filter(RaceSeries.display_name.like("%Banana Belt%"))
            .first()
        )
        detail = queries.get_series_detail(seeded_series_session, bb.id)
        assert detail is not None
        assert detail["series"]["edition_count"] == 3
        assert len(detail["editions"]) == 3
        assert not detail["trend"].empty

    def test_nonexistent_series(self, seeded_series_session):
        detail = queries.get_series_detail(seeded_series_session, 99999)
        assert detail is None

    def test_overall_finish_type(self, seeded_series_session):
        from raceanalyzer.db.models import RaceSeries
        bb = (
            seeded_series_session.query(RaceSeries)
            .filter(RaceSeries.display_name.like("%Banana Belt%"))
            .first()
        )
        detail = queries.get_series_detail(seeded_series_session, bb.id)
        # BB has 2 bunch_sprint editions and 1 breakaway -> overall should be bunch_sprint
        assert detail["overall_finish_type"] in ("bunch_sprint", "breakaway")

    def test_categories(self, seeded_series_session):
        from raceanalyzer.db.models import RaceSeries
        bb = (
            seeded_series_session.query(RaceSeries)
            .filter(RaceSeries.display_name.like("%Banana Belt%"))
            .first()
        )
        detail = queries.get_series_detail(seeded_series_session, bb.id)
        assert "Men Cat 1/2" in detail["categories"]


class TestGetSeriesEditions:
    def test_returns_editions(self, seeded_series_session):
        from raceanalyzer.db.models import RaceSeries
        bb = (
            seeded_series_session.query(RaceSeries)
            .filter(RaceSeries.display_name.like("%Banana Belt%"))
            .first()
        )
        editions = queries.get_series_editions(seeded_series_session, bb.id)
        assert len(editions) == 3


class TestGetRacePreview:
    def test_returns_preview(self, seeded_course_session):
        from raceanalyzer.db.models import RaceSeries
        bb = (
            seeded_course_session.query(RaceSeries)
            .filter(RaceSeries.display_name.like("%Banana Belt%"))
            .first()
        )
        preview = queries.get_race_preview(seeded_course_session, bb.id)
        assert preview is not None
        assert preview["series"]["display_name"] == bb.display_name
        assert "categories" in preview
        assert "contenders" in preview
        assert "course" in preview

    def test_nonexistent_series(self, seeded_course_session):
        preview = queries.get_race_preview(seeded_course_session, 99999)
        assert preview is None

    def test_with_category(self, seeded_course_session):
        from raceanalyzer.db.models import RaceSeries
        bb = (
            seeded_course_session.query(RaceSeries)
            .filter(RaceSeries.display_name.like("%Banana Belt%"))
            .first()
        )
        preview = queries.get_race_preview(
            seeded_course_session, bb.id, category="Men Cat 1/2"
        )
        assert preview is not None
        if preview["prediction"]:
            assert preview["prediction"]["confidence"] in ("high", "moderate", "low")

    def test_course_data_present(self, seeded_course_session):
        from raceanalyzer.db.models import RaceSeries
        bb = (
            seeded_course_session.query(RaceSeries)
            .filter(RaceSeries.display_name.like("%Banana Belt%"))
            .first()
        )
        preview = queries.get_race_preview(seeded_course_session, bb.id)
        assert preview["course"] is not None
        assert preview["course"]["course_type"] == "rolling"
        assert preview["course"]["total_gain_m"] == 850.0

    def test_no_course_data(self, seeded_series_session):
        """Series without course data should return course=None."""
        from raceanalyzer.db.models import RaceSeries
        series = seeded_series_session.query(RaceSeries).first()
        preview = queries.get_race_preview(seeded_series_session, series.id)
        assert preview is not None
        assert preview["course"] is None

    def test_includes_new_fields(self, seeded_course_session):
        """Preview includes drop_rate, typical_speed, narrative, profile, climbs."""
        from raceanalyzer.db.models import RaceSeries
        bb = (
            seeded_course_session.query(RaceSeries)
            .filter(RaceSeries.display_name.like("%Banana Belt%"))
            .first()
        )
        preview = queries.get_race_preview(seeded_course_session, bb.id)
        assert preview is not None
        # These keys should always be present (may be None)
        assert "drop_rate" in preview
        assert "typical_speed" in preview
        assert "narrative" in preview
        assert "profile_points" in preview
        assert "climbs" in preview

    def test_narrative_not_empty(self, seeded_course_session):
        """Narrative should always produce some text."""
        from raceanalyzer.db.models import RaceSeries
        bb = (
            seeded_course_session.query(RaceSeries)
            .filter(RaceSeries.display_name.like("%Banana Belt%"))
            .first()
        )
        preview = queries.get_race_preview(seeded_course_session, bb.id)
        assert preview["narrative"]
        assert len(preview["narrative"]) > 10
        assert "None" not in preview["narrative"]

    def test_degrades_gracefully_no_data(self, seeded_series_session):
        """With no course data, new fields degrade gracefully."""
        from raceanalyzer.db.models import RaceSeries
        series = seeded_series_session.query(RaceSeries).first()
        preview = queries.get_race_preview(seeded_series_session, series.id)
        assert preview is not None
        # No course -> no profile or climbs
        assert preview["profile_points"] is None
        assert preview["climbs"] is None
        # Narrative still present (may say "new event" or based on predictions)
        assert preview["narrative"] is not None


# --- Sprint 010: Feed queries ---


class TestFinishTypePlainEnglish:
    def test_known_type(self):
        result = queries.finish_type_plain_english("bunch_sprint")
        assert "pack stayed together" in result.lower()

    def test_unknown_type(self):
        result = queries.finish_type_plain_english("nonexistent")
        assert result == ""


class TestClimbHighlight:
    def test_with_climbs(self):
        climbs = [
            {"length_m": 1800, "avg_grade": 6.0, "start_d": 18000, "end_d": 19800},
        ]
        result = queries.climb_highlight(climbs)
        assert result is not None
        assert "km 18" in result
        assert "1.8 km" in result
        assert "6.0%" in result

    def test_no_climbs(self):
        assert queries.climb_highlight(None) is None
        assert queries.climb_highlight([]) is None

    def test_picks_hardest(self):
        climbs = [
            {"length_m": 1000, "avg_grade": 3.0, "start_d": 5000},
            {"length_m": 2000, "avg_grade": 8.0, "start_d": 15000},
        ]
        result = queries.climb_highlight(climbs)
        assert "8.0%" in result


class TestDownsampleProfile:
    def test_short_profile_unchanged(self):
        points = [{"d": i, "e": i * 10} for i in range(10)]
        result = queries._downsample_profile(points, target=50)
        assert len(result) == 10

    def test_long_profile_downsampled(self):
        points = [{"d": i, "e": i * 10} for i in range(500)]
        result = queries._downsample_profile(points, target=50)
        assert len(result) <= 60  # approximate

    def test_empty(self):
        assert queries._downsample_profile([]) == []
        assert queries._downsample_profile(None) == []


class TestSearchSeries:
    def test_finds_match(self, seeded_series_session):
        ids = queries.search_series(seeded_series_session, "banana")
        assert len(ids) >= 1

    def test_case_insensitive(self, seeded_series_session):
        ids = queries.search_series(seeded_series_session, "BANANA")
        assert len(ids) >= 1

    def test_no_match(self, seeded_series_session):
        ids = queries.search_series(seeded_series_session, "zzz_nonexistent")
        assert ids == []

    def test_empty_query(self, seeded_series_session):
        ids = queries.search_series(seeded_series_session, "")
        assert ids == []

    def test_wildcard_escaped(self, seeded_series_session):
        # % and _ should be escaped, not treated as wildcards
        ids = queries.search_series(seeded_series_session, "100%")
        assert ids == []


class TestGetFeedItems:
    def test_returns_items(self, seeded_series_session):
        items = queries.get_feed_items(seeded_series_session)
        assert len(items) > 0

    def test_each_item_has_required_keys(self, seeded_series_session):
        items = queries.get_feed_items(seeded_series_session)
        required = {
            "series_id", "display_name", "is_upcoming",
            "predicted_finish_type", "narrative_snippet",
            "editions_summary",
        }
        for item in items:
            missing = required - set(item.keys())
            assert not missing, f"Missing keys: {missing}"

    def test_search_filters(self, seeded_series_session):
        all_items = queries.get_feed_items(seeded_series_session)
        banana_items = queries.get_feed_items(
            seeded_series_session, search_query="banana"
        )
        assert len(banana_items) < len(all_items)
        assert all("banana" in i["display_name"].lower() for i in banana_items)

    def test_empty_db(self, session):
        items = queries.get_feed_items(session)
        assert items == []

    def test_search_no_match(self, seeded_series_session):
        items = queries.get_feed_items(
            seeded_series_session, search_query="zzz_nonexistent"
        )
        assert items == []

    def test_items_have_editions_summary(self, seeded_series_session):
        items = queries.get_feed_items(seeded_series_session)
        for item in items:
            assert isinstance(item["editions_summary"], list)
            for ed in item["editions_summary"]:
                assert "year" in ed
                assert "finish_type_display" in ed

    def test_items_degrade_without_course(self, seeded_series_session):
        """Feed items without course data should still work (no sparkline/terrain)."""
        items = queries.get_feed_items(seeded_series_session)
        # seeded_series_session has no course data
        for item in items:
            assert item["elevation_sparkline_points"] == []
            assert item["course_type"] is None
            assert item["climb_highlight"] is None


class TestSnippet:
    def test_two_sentences(self):
        text = "First sentence. Second sentence. Third sentence."
        result = queries._snippet(text, max_sentences=2)
        assert "First sentence." in result
        assert "Second sentence." in result
        assert "Third" not in result

    def test_single_sentence(self):
        text = "Just one sentence without period"
        result = queries._snippet(text, max_sentences=2)
        assert result == text

    def test_max_chars(self):
        text = "A" * 300
        result = queries._snippet(text, max_chars=200)
        assert len(result) <= 200
        assert result.endswith("...")

    def test_empty(self):
        assert queries._snippet("") == ""
        assert queries._snippet(None) == ""


# --- Sprint 011: New query tests ---


class TestDiscipline:
    def test_road_types(self):
        from raceanalyzer.db.models import RaceType

        assert (
            queries.discipline_for_race_type(RaceType.CRITERIUM)
            == queries.Discipline.ROAD
        )
        assert (
            queries.discipline_for_race_type(RaceType.ROAD_RACE)
            == queries.Discipline.ROAD
        )
        assert (
            queries.discipline_for_race_type(RaceType.TIME_TRIAL)
            == queries.Discipline.ROAD
        )

    def test_gravel(self):
        from raceanalyzer.db.models import RaceType

        assert (
            queries.discipline_for_race_type(RaceType.GRAVEL)
            == queries.Discipline.GRAVEL
        )

    def test_none(self):
        assert queries.discipline_for_race_type(None) == queries.Discipline.UNKNOWN

    def test_unknown_type(self):
        assert queries.discipline_for_race_type(None) == queries.Discipline.UNKNOWN


class TestCountdownLabel:
    def test_today(self):
        assert queries.countdown_label(0) == "Today"

    def test_tomorrow(self):
        assert queries.countdown_label(1) == "Tomorrow"

    def test_few_days(self):
        assert queries.countdown_label(4) == "in 4 days"

    def test_two_weeks(self):
        assert queries.countdown_label(14) == "in 14 days"

    def test_weeks(self):
        assert queries.countdown_label(21) == "in 3 weeks"

    def test_none(self):
        assert queries.countdown_label(None) == ""


class TestGroupByMonth:
    def test_groups_upcoming(self):
        from datetime import datetime

        items = [
            {"is_upcoming": True, "upcoming_date": datetime(2026, 3, 15)},
            {"is_upcoming": True, "upcoming_date": datetime(2026, 3, 20)},
            {"is_upcoming": True, "upcoming_date": datetime(2026, 4, 5)},
            {"is_upcoming": False, "most_recent_date": datetime(2025, 6, 1)},
        ]
        groups = queries.group_by_month(items)
        assert len(groups) == 3  # March, April, Past Races
        assert groups[0][0] == "March 2026"
        assert len(groups[0][1]) == 2
        assert groups[1][0] == "April 2026"
        assert groups[2][0] == "Past Races"

    def test_no_upcoming(self):
        from datetime import datetime

        items = [
            {"is_upcoming": False, "most_recent_date": datetime(2025, 6, 1)},
        ]
        groups = queries.group_by_month(items)
        assert len(groups) == 1
        assert groups[0][0] == "Past Races"

    def test_empty(self):
        groups = queries.group_by_month([])
        assert groups == []


class TestPerfTimer:
    def test_measures_time(self):
        import time

        with queries.PerfTimer("test") as t:
            time.sleep(0.01)
        assert t.elapsed_ms > 0


class TestGetFeedItemsBatch:
    def test_returns_items(self, seeded_series_session):
        # First precompute predictions
        from raceanalyzer.precompute import precompute_all

        precompute_all(seeded_series_session)

        items = queries.get_feed_items_batch(seeded_series_session)
        assert len(items) > 0

    def test_has_tier1_keys(self, seeded_series_session):
        from raceanalyzer.precompute import precompute_all

        precompute_all(seeded_series_session)

        items = queries.get_feed_items_batch(seeded_series_session)
        required = {
            "series_id",
            "display_name",
            "is_upcoming",
            "countdown_label",
            "discipline",
            "race_type",
            "teammate_names",
        }
        for item in items:
            missing = required - set(item.keys())
            assert not missing, f"Missing keys: {missing}"

    def test_empty_db(self, session):
        items = queries.get_feed_items_batch(session)
        assert items == []

    def test_search_filter(self, seeded_series_session):
        from raceanalyzer.precompute import precompute_all

        precompute_all(seeded_series_session)

        items = queries.get_feed_items_batch(
            seeded_series_session, search_query="banana"
        )
        assert len(items) >= 1
        assert all("banana" in i["display_name"].lower() for i in items)

    def test_state_filter(self, seeded_series_session):
        from raceanalyzer.precompute import precompute_all

        precompute_all(seeded_series_session)

        items = queries.get_feed_items_batch(
            seeded_series_session, state_filter=["WA"]
        )
        assert all(i["state_province"] == "WA" for i in items)


class TestGetFeedItemDetail:
    def test_returns_detail(self, seeded_series_session):
        from raceanalyzer.db.models import RaceSeries

        series = seeded_series_session.query(RaceSeries).first()
        detail = queries.get_feed_item_detail(seeded_series_session, series.id)
        assert detail is not None
        assert "narrative_snippet" in detail
        assert "editions_summary" in detail

    def test_editions_have_finish_type(self, seeded_series_session):
        from raceanalyzer.db.models import RaceSeries

        series = seeded_series_session.query(RaceSeries).first()
        detail = queries.get_feed_item_detail(seeded_series_session, series.id)
        for ed in detail["editions_summary"]:
            assert "finish_type_display" in ed


class TestComputeSimilarity:
    def test_identical_series(self):
        a = {
            "course_type": "flat",
            "predicted_finish_type": "bunch_sprint",
            "distance_m": 40000,
            "discipline": "road",
        }
        score = queries.compute_similarity(a, a)
        assert score == 100

    def test_different_series(self):
        a = {
            "course_type": "flat",
            "predicted_finish_type": "bunch_sprint",
            "distance_m": 40000,
            "discipline": "road",
        }
        b = {
            "course_type": "hilly",
            "predicted_finish_type": "gc_selective",
            "distance_m": 100000,
            "discipline": "road",
        }
        score = queries.compute_similarity(a, b)
        assert score < 50

    def test_missing_fields(self):
        a = {
            "course_type": None,
            "predicted_finish_type": None,
            "distance_m": None,
            "discipline": None,
        }
        b = {
            "course_type": "flat",
            "predicted_finish_type": "bunch_sprint",
            "distance_m": 40000,
            "discipline": "road",
        }
        score = queries.compute_similarity(a, b)
        assert score == 0


class TestGetTeammatesBySeriesEmpty:
    def test_short_name_rejected(self, seeded_series_session):
        result = queries.get_teammates_by_series(
            seeded_series_session, [1], None, "AB"
        )
        assert result == {}

    def test_none_name(self, seeded_series_session):
        result = queries.get_teammates_by_series(
            seeded_series_session, [1], None, None
        )
        assert result == {}

    def test_empty_name(self, seeded_series_session):
        result = queries.get_teammates_by_series(
            seeded_series_session, [1], None, ""
        )
        assert result == {}


# --- Sprint 012: State filter whitelist ---


class TestPNWStateWhitelist:
    def test_excludes_non_pnw_states(self, session):
        """States outside PNW should be filtered out."""
        from raceanalyzer.db.models import Race

        # Add races in Ontario and WA
        session.add(Race(
            id=90001, name="Ontario Race", state_province="ON",
            location="Toronto", is_upcoming=False,
        ))
        session.add(Race(
            id=90002, name="WA Race", state_province="WA",
            location="Seattle", is_upcoming=False,
        ))
        session.commit()

        states = queries.get_available_states(session)
        assert "WA" in states
        assert "ON" not in states

    def test_pnw_states_included(self, session):
        from raceanalyzer.db.models import Race

        for i, (name, state) in enumerate([
            ("WA Race", "WA"), ("OR Race", "OR"), ("ID Race", "ID"),
            ("BC Race", "BC"), ("MT Race", "MT"),
        ]):
            session.add(Race(
                id=90010 + i, name=name, state_province=state,
                location=name, is_upcoming=False,
            ))
        session.commit()

        states = queries.get_available_states(session)
        for s in ["BC", "ID", "MT", "OR", "WA"]:
            assert s in states


# --- Sprint 012: Source-aware plain English ---


class TestFinishTypePlainEnglishWithSource:
    def test_time_gap_returns_base(self):
        result = queries.finish_type_plain_english_with_source(
            "bunch_sprint", prediction_source="time_gap"
        )
        assert result == queries.finish_type_plain_english("bunch_sprint")

    def test_course_profile_prefix(self):
        result = queries.finish_type_plain_english_with_source(
            "bunch_sprint", prediction_source="course_profile"
        )
        assert result.startswith("Course profile suggests:")

    def test_race_type_only_prefix(self):
        result = queries.finish_type_plain_english_with_source(
            "bunch_sprint", prediction_source="race_type_only",
            race_type="criterium",
        )
        assert "Criteriums" in result
        assert "typically end" in result

    def test_none_source_returns_base(self):
        result = queries.finish_type_plain_english_with_source(
            "bunch_sprint", prediction_source=None
        )
        assert result == queries.finish_type_plain_english("bunch_sprint")

    def test_unknown_finish_type_returns_none(self):
        result = queries.finish_type_plain_english_with_source(
            "nonexistent_type", prediction_source="time_gap"
        )
        assert result is None


# --- Sprint 018: Category distance & time helpers ---


class _FakeCategoryDetail:
    """Minimal stand-in for CategoryDetail ORM instances."""

    def __init__(self, race_id=1, category="Cat 3", distance=None, distance_unit=None):
        self.race_id = race_id
        self.category = category
        self.distance = distance
        self.distance_unit = distance_unit


class _FakePrediction:
    """Minimal stand-in for SeriesPrediction."""

    def __init__(self, series_id=1, category=None, typical_field_duration_min=None):
        self.series_id = series_id
        self.category = category
        self.typical_field_duration_min = typical_field_duration_min


class TestResolveCategoryDistance:
    def test_exact_match(self):
        details = [_FakeCategoryDetail(category="Cat 3", distance=50.0, distance_unit="miles")]
        dist, unit = queries._resolve_category_distance(details, "Cat 3")
        assert dist == 50.0
        assert unit == "miles"

    def test_normalized_match(self):
        details = [_FakeCategoryDetail(category="  cat  3 ", distance=40.0, distance_unit="km")]
        dist, unit = queries._resolve_category_distance(details, "cat 3")
        assert dist == 40.0
        assert unit == "km"

    def test_no_match(self):
        details = [_FakeCategoryDetail(category="Cat 1/2", distance=80.0, distance_unit="miles")]
        dist, unit = queries._resolve_category_distance(details, "Cat 5")
        assert dist is None
        assert unit is None

    def test_no_category_returns_none(self):
        details = [_FakeCategoryDetail(category="Cat 3", distance=50.0)]
        dist, unit = queries._resolve_category_distance(details, None)
        assert dist is None

    def test_empty_details(self):
        dist, unit = queries._resolve_category_distance([], "Cat 3")
        assert dist is None


class TestFormatDistanceRange:
    def test_single_unit_range(self):
        details = [
            _FakeCategoryDetail(distance=30.0, distance_unit="miles"),
            _FakeCategoryDetail(distance=60.0, distance_unit="miles"),
        ]
        result = queries._format_distance_range(details)
        assert result == "30-60 mi"

    def test_equal_distance_collapse(self):
        details = [
            _FakeCategoryDetail(distance=50.0, distance_unit="miles"),
            _FakeCategoryDetail(distance=50.0, distance_unit="miles"),
        ]
        result = queries._format_distance_range(details)
        assert result == "50 mi"

    def test_time_based_range(self):
        details = [
            _FakeCategoryDetail(distance=30.0, distance_unit="minutes"),
            _FakeCategoryDetail(distance=60.0, distance_unit="minutes"),
        ]
        result = queries._format_distance_range(details)
        assert result == "30-60 min"

    def test_empty_returns_none(self):
        assert queries._format_distance_range([]) is None

    def test_no_distance_returns_none(self):
        details = [_FakeCategoryDetail(distance=None)]
        assert queries._format_distance_range(details) is None

    def test_mixed_units_uses_dominant(self):
        details = [
            _FakeCategoryDetail(distance=30.0, distance_unit="miles"),
            _FakeCategoryDetail(distance=50.0, distance_unit="miles"),
            _FakeCategoryDetail(distance=80.0, distance_unit="km"),
        ]
        result = queries._format_distance_range(details)
        assert "mi" in result  # miles is dominant (2 vs 1)

    def test_km_unit(self):
        details = [
            _FakeCategoryDetail(distance=40.0, distance_unit="km"),
            _FakeCategoryDetail(distance=80.0, distance_unit="km"),
        ]
        result = queries._format_distance_range(details)
        assert result == "40-80 km"


class TestIsDurationRace:
    def test_time_based(self):
        details = [_FakeCategoryDetail(distance_unit="minutes")]
        assert queries._is_duration_race(details) is True

    def test_distance_based(self):
        details = [_FakeCategoryDetail(distance_unit="miles")]
        assert queries._is_duration_race(details) is False

    def test_empty(self):
        assert queries._is_duration_race([]) is False

    def test_mixed(self):
        details = [
            _FakeCategoryDetail(distance_unit="miles"),
            _FakeCategoryDetail(distance_unit="min"),
        ]
        assert queries._is_duration_race(details) is True


class TestFormatTimeRange:
    def test_with_category(self):
        pred_map = {
            (1, "Cat 3"): _FakePrediction(1, "Cat 3", 120.0),
        }
        result = queries._format_time_range(pred_map, 1, "Cat 3")
        assert result == "~2h 00m"

    def test_without_category_range(self):
        pred_map = {
            (1, "Cat 3"): _FakePrediction(1, "Cat 3", 90.0),
            (1, "Cat 4/5"): _FakePrediction(1, "Cat 4/5", 60.0),
        }
        result = queries._format_time_range(pred_map, 1, None)
        assert "~1h 00m" in result
        assert "~1h 30m" in result

    def test_without_category_single(self):
        pred_map = {
            (1, None): _FakePrediction(1, None, 120.0),
        }
        result = queries._format_time_range(pred_map, 1, None)
        assert result == "~2h 00m"

    def test_no_data_returns_none(self):
        result = queries._format_time_range({}, 1, "Cat 3")
        assert result is None

    def test_fallback_to_null_category(self):
        pred_map = {
            (1, None): _FakePrediction(1, None, 105.0),
        }
        result = queries._format_time_range(pred_map, 1, "Cat 3")
        assert result == "~1h 45m"


class TestBuildCatDetailMap:
    def test_maps_by_series(self):
        class FakeRace:
            def __init__(self, id, series_id):
                self.id = id
                self.series_id = series_id
                self.is_upcoming = True

        races_by_series = {
            10: [FakeRace(100, 10), FakeRace(101, 10)],
            20: [FakeRace(200, 20)],
        }
        cat_details = [
            _FakeCategoryDetail(race_id=100, category="Cat 3"),
            _FakeCategoryDetail(race_id=200, category="Cat 4/5"),
        ]
        result = queries._build_cat_detail_map(cat_details, races_by_series)
        assert 10 in result
        assert 20 in result
        assert len(result[10]) == 1
        assert result[10][0].category == "Cat 3"
