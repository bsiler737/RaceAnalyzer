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
