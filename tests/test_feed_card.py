"""Tests for feed card v2 renderer (Sprint 013)."""

from __future__ import annotations

import pytest

from raceanalyzer.ui.feed_card import (
    _card_has_chip,
    _chip,
    build_card_html,
    build_row_html,
    confidence_text,
    countdown_pill_style,
    extract_key_climb,
    format_duration,
    generate_ics,
    generate_share_text,
    pack_survival_text,
    racer_type_short_label,
    render_distribution_sparkline,
    render_elevation_sparkline_svg,
    render_route_trace_svg,
    what_to_expect_text,
)

# --- Derived metric helpers ---


class TestCountdownPillStyle:
    def test_none_returns_transparent(self):
        label, bg, text = countdown_pill_style(None)
        assert label == ""
        assert bg == "transparent"

    def test_today(self):
        label, bg, text = countdown_pill_style(0)
        assert label == "Today"
        assert "#D32F2F" in bg

    def test_tomorrow(self):
        label, bg, text = countdown_pill_style(1)
        assert label == "Tomorrow"

    def test_red_under_3(self):
        label, bg, text = countdown_pill_style(2)
        assert "2 days" in label
        assert "#D32F2F" in bg

    def test_amber_under_14(self):
        label, bg, text = countdown_pill_style(10)
        assert "10 days" in label
        assert "#F57C00" in bg

    def test_neutral_over_14(self):
        label, bg, text = countdown_pill_style(21)
        assert "3 weeks" in label


class TestPackSurvivalText:
    def test_none_returns_empty(self):
        assert pack_survival_text(None, None) == ""

    def test_low_drop_rate(self):
        result = pack_survival_text(8, "bunch_sprint")
        assert "everyone finishes" in result.lower()

    def test_high_drop_rate(self):
        result = pack_survival_text(55, "gc_selective")
        assert "strongest survive" in result.lower()

    def test_moderate_drop_rate(self):
        result = pack_survival_text(18, "small_group_sprint")
        assert "most riders" in result.lower()


class TestWhatToExpectText:
    def test_bunch_sprint(self):
        result = what_to_expect_text("bunch_sprint")
        assert "sprint" in result.lower()

    def test_breakaway(self):
        result = what_to_expect_text("breakaway")
        assert "move" in result.lower() or "away" in result.lower()

    def test_unknown_returns_empty(self):
        assert what_to_expect_text("unknown") == ""

    def test_none_returns_empty(self):
        assert what_to_expect_text(None) == ""

    def test_criterium_fallback(self):
        result = what_to_expect_text(None, race_type="criterium")
        assert "circuit" in result.lower() or "laps" in result.lower()


class TestRacerTypeShortLabel:
    def test_flat_sprint(self):
        assert racer_type_short_label("flat", "bunch_sprint") == "Sprinters"

    def test_hilly_breakaway(self):
        assert racer_type_short_label("hilly", "breakaway") == "Climbers"

    def test_rolling_breakaway(self):
        assert "Diesel" in racer_type_short_label("rolling", "breakaway")

    def test_none_returns_empty(self):
        assert racer_type_short_label(None, None) == ""


class TestExtractKeyClimb:
    def test_extracts_hardest(self):
        climbs = '[{"length_m": 2500, "avg_grade": 6.2}, {"length_m": 1000, "avg_grade": 3.0}]'
        result = extract_key_climb(climbs)
        assert "2.5 km" in result
        assert "6.2%" in result

    def test_none_returns_none(self):
        assert extract_key_climb(None) is None

    def test_empty_returns_none(self):
        assert extract_key_climb("[]") is None


class TestFormatDuration:
    def test_hours_and_minutes(self):
        assert format_duration(105) == "~1h 45m"

    def test_minutes_only(self):
        assert format_duration(45) == "~45m"

    def test_none(self):
        assert format_duration(None) == ""


class TestConfidenceText:
    def test_high_confidence(self):
        result = confidence_text("high", 5)
        assert "High confidence" in result
        assert "5 editions" in result

    def test_low_confidence(self):
        result = confidence_text("low", 1)
        assert "Estimate" in result

    def test_course_profile_source(self):
        result = confidence_text("low", 0, prediction_source="course_profile")
        assert "course profile" in result


# --- SVG renderers ---


class TestElevationSparklineSvg:
    def test_renders_svg(self):
        points = [{"e": 100}, {"e": 200}, {"e": 150}, {"e": 300}]
        svg = render_elevation_sparkline_svg(points)
        assert "<svg" in svg
        assert "M0" in svg

    def test_empty_returns_empty(self):
        assert render_elevation_sparkline_svg([]) == ""

    def test_single_point_returns_empty(self):
        assert render_elevation_sparkline_svg([{"e": 100}]) == ""


class TestRouteTraceSvg:
    def test_none_returns_empty(self):
        assert render_route_trace_svg(None) == ""

    def test_renders_svg_from_polyline(self):
        # A simple encoded polyline for Portland area
        try:
            import polyline as pl

            coords = [(45.5, -122.6), (45.51, -122.61), (45.52, -122.59)]
            encoded = pl.encode(coords)
            svg = render_route_trace_svg(encoded)
            assert "<svg" in svg
            assert "polyline" in svg
        except ImportError:
            pytest.skip("polyline not installed")


class TestDistributionSparkline:
    def test_renders_bars(self):
        dist = '{"bunch_sprint": 5, "breakaway": 2}'
        svg = render_distribution_sparkline(dist)
        assert "<svg" in svg
        assert "rect" in svg

    def test_empty(self):
        assert render_distribution_sparkline(None) == ""
        assert render_distribution_sparkline("{}") == ""


# --- Card HTML builder ---


class TestBuildCardHtml:
    def test_basic_card(self):
        item = {
            "display_name": "Banana Belt RR",
            "location": "Maryhill",
            "state_province": "WA",
            "is_upcoming": True,
            "upcoming_date": None,
            "days_until": 5,
            "most_recent_date": None,
            "race_type": "road_race",
            "predicted_finish_type": "bunch_sprint",
            "confidence": "high",
            "prediction_source": "time_gap",
            "course_type": "rolling",
            "distance_m": 85000,
            "total_gain_m": 850,
            "drop_rate_pct": 15,
            "drop_rate_label": "low",
            "field_size_median": 45,
            "teammate_names": [],
            "edition_count": 5,
            "elevation_sparkline_points": None,
            "climbs_json": None,
            "typical_field_duration_min": 120,
            "rwgps_encoded_polyline": None,
            "distribution_json": None,
        }
        card = build_card_html(item)
        assert "Banana Belt RR" in card
        assert "Maryhill" in card
        assert "Road Race" in card
        assert "85 km" in card
        assert "850m" in card
        assert "Drop rate" in card
        assert "sprint" in card.lower()

    def test_html_escaping(self):
        item = {
            "display_name": '<script>alert("xss")</script>',
            "location": "O'Brien & Co",
            "state_province": "WA",
            "is_upcoming": False,
            "upcoming_date": None,
            "days_until": None,
            "most_recent_date": None,
            "race_type": None,
            "predicted_finish_type": None,
            "confidence": None,
            "prediction_source": None,
            "course_type": None,
            "distance_m": None,
            "total_gain_m": None,
            "drop_rate_pct": None,
            "drop_rate_label": None,
            "field_size_median": None,
            "teammate_names": [],
            "edition_count": 0,
            "elevation_sparkline_points": None,
            "climbs_json": None,
            "typical_field_duration_min": None,
            "rwgps_encoded_polyline": None,
            "distribution_json": None,
        }
        card = build_card_html(item)
        assert "<script>" not in card
        assert "&lt;script&gt;" in card
        assert "O&#x27;Brien" in card or "O&#39;Brien" in card or "O'Brien" not in card

    def test_graceful_degradation_missing_data(self):
        item = {
            "display_name": "Test Race",
            "location": None,
            "state_province": None,
            "is_upcoming": False,
            "upcoming_date": None,
            "days_until": None,
            "most_recent_date": None,
            "race_type": None,
            "predicted_finish_type": None,
            "confidence": None,
            "prediction_source": None,
            "course_type": None,
            "distance_m": None,
            "total_gain_m": None,
            "drop_rate_pct": None,
            "drop_rate_label": None,
            "field_size_median": None,
            "teammate_names": [],
            "edition_count": 0,
            "elevation_sparkline_points": None,
            "climbs_json": None,
            "typical_field_duration_min": None,
            "rwgps_encoded_polyline": None,
            "distribution_json": None,
        }
        card = build_card_html(item)
        assert "Test Race" in card
        # Should not error out
        assert "feed-card-inner" in card

    def test_no_beginner_badge(self):
        """Sprint 018: Beginner-friendly badge removed."""
        item = {
            "display_name": "Easy Crit",
            "location": "Portland",
            "state_province": "OR",
            "is_upcoming": True,
            "upcoming_date": None,
            "days_until": 10,
            "most_recent_date": None,
            "race_type": "criterium",
            "predicted_finish_type": "bunch_sprint",
            "confidence": "high",
            "prediction_source": "time_gap",
            "course_type": "flat",
            "distance_m": 30000,
            "total_gain_m": 50,
            "drop_rate_pct": 5,
            "drop_rate_label": "low",
            "field_size_median": 40,
            "teammate_names": ["Jake"],
            "edition_count": 5,
            "elevation_sparkline_points": None,
            "climbs_json": None,
            "typical_field_duration_min": 45,
            "rwgps_encoded_polyline": None,
            "distribution_json": None,
        }
        card = build_card_html(item)
        assert "Beginner-friendly" not in card
        assert "Jake" in card


# --- ICS generation ---


class TestGenerateIcs:
    def test_basic_ics(self):
        from datetime import datetime

        ics = generate_ics("Test Race", datetime(2026, 4, 15, 10, 0), "Portland, OR")
        assert "BEGIN:VCALENDAR" in ics
        assert "Test Race" in ics
        assert "Portland\\, OR" in ics
        assert "\r\n" in ics
        assert "DTSTART:20260415T100000" in ics

    def test_crlf_line_endings(self):
        from datetime import datetime

        ics = generate_ics("Race", datetime(2026, 3, 1, 8, 0))
        lines = ics.split("\r\n")
        assert len(lines) > 5

    def test_special_chars_escaped(self):
        from datetime import datetime

        ics = generate_ics("Race; with, special: chars", datetime(2026, 1, 1))
        assert "\\;" in ics
        assert "\\," in ics


# --- Sprint 014: No title attributes ---


class TestNoTitleAttributes:
    """Sprint 014: title= must not appear in _chip() output."""

    def test_chip_has_no_title(self):
        result = _chip("distance", "<svg></svg>", "85 km")
        assert 'title="' not in result
        assert "feed-card-chip" in result

    def test_card_html_has_no_title_on_chips(self):
        item = {
            "display_name": "Test",
            "location": None,
            "state_province": None,
            "is_upcoming": False,
            "upcoming_date": None,
            "days_until": None,
            "most_recent_date": None,
            "race_type": None,
            "predicted_finish_type": "bunch_sprint",
            "confidence": "high",
            "prediction_source": "time_gap",
            "course_type": "flat",
            "distance_m": 40000,
            "total_gain_m": 100,
            "drop_rate_pct": 10,
            "drop_rate_label": "low",
            "field_size_median": 40,
            "teammate_names": [],
            "edition_count": 3,
            "elevation_sparkline_points": None,
            "climbs_json": None,
            "typical_field_duration_min": 60,
            "rwgps_encoded_polyline": None,
            "distribution_json": None,
        }
        card = build_card_html(item)
        assert 'title="' not in card


# --- Sprint 014: _card_has_chip helper ---


class TestCardHasChip:
    def test_distance_present(self):
        assert _card_has_chip({"distance_m": 40000}, "distance") is True

    def test_distance_none(self):
        assert _card_has_chip({"distance_m": None}, "distance") is False

    def test_distance_zero(self):
        assert _card_has_chip({"distance_m": 0}, "distance") is True

    def test_drop_rate_present(self):
        assert _card_has_chip({"drop_rate_pct": 10}, "drop_rate") is True

    def test_drop_rate_none(self):
        assert _card_has_chip({"drop_rate_pct": None}, "drop_rate") is False

    def test_unknown_chip_type(self):
        assert _card_has_chip({}, "nonexistent") is False


# --- Sprint 014: generate_share_text ---


class TestGenerateShareText:
    def test_includes_name_and_location(self):
        item = {
            "display_name": "Banana Belt RR",
            "location": "Maryhill",
            "state_province": "WA",
            "upcoming_date": None,
            "predicted_finish_type": "bunch_sprint",
            "race_type": "road_race",
            "typical_field_duration_min": 120,
            "series_id": 42,
        }
        text = generate_share_text(item, "Cat 4/5")
        assert "Banana Belt RR" in text
        assert "Maryhill" in text
        assert "WA" in text
        assert "series_id=42" in text
        assert "Cat 4/5" in text

    def test_includes_prediction(self):
        item = {
            "display_name": "Test Race",
            "location": "Portland",
            "state_province": "OR",
            "upcoming_date": None,
            "predicted_finish_type": "bunch_sprint",
            "race_type": "road_race",
            "typical_field_duration_min": None,
            "series_id": 1,
        }
        text = generate_share_text(item)
        assert "sprint" in text.lower()

    def test_includes_duration(self):
        item = {
            "display_name": "Test",
            "location": None,
            "state_province": None,
            "upcoming_date": None,
            "predicted_finish_type": None,
            "race_type": None,
            "typical_field_duration_min": 90,
            "series_id": 1,
        }
        text = generate_share_text(item)
        assert "~1h 30m" in text


# --- Sprint 014: Chip icon sizing ---


class TestChipIconSizing:
    """Sprint 014: VR-01 chip SVGs sized via CSS at 16px."""

    def test_css_has_16px_chip_svg(self):
        from pathlib import Path

        card_path = (
            Path(__file__).parent.parent
            / "raceanalyzer" / "ui" / "feed_card.py"
        )
        source = card_path.read_text()
        assert ".feed-card-chip svg" in source
        assert "width: 16px" in source
        assert "height: 16px" in source


# --- Sprint 014: Green drop rate bar ---


class TestGreenDropRateBar:
    def test_low_drop_rate_green_background(self):
        item = {
            "display_name": "Easy Race",
            "location": None,
            "state_province": None,
            "is_upcoming": True,
            "upcoming_date": None,
            "days_until": 10,
            "most_recent_date": None,
            "race_type": "criterium",
            "predicted_finish_type": "bunch_sprint",
            "confidence": "high",
            "prediction_source": "time_gap",
            "course_type": "flat",
            "distance_m": 30000,
            "total_gain_m": 50,
            "drop_rate_pct": 10,
            "drop_rate_label": "low",
            "field_size_median": 40,
            "teammate_names": [],
            "edition_count": 3,
            "elevation_sparkline_points": None,
            "climbs_json": None,
            "typical_field_duration_min": 45,
            "rwgps_encoded_polyline": None,
            "distribution_json": None,
        }
        card = build_card_html(item)
        assert "#E8F5E9" in card

    def test_high_drop_rate_no_green_background(self):
        item = {
            "display_name": "Hard Race",
            "location": None,
            "state_province": None,
            "is_upcoming": True,
            "upcoming_date": None,
            "days_until": 10,
            "most_recent_date": None,
            "race_type": "road_race",
            "predicted_finish_type": "gc_selective",
            "confidence": "high",
            "prediction_source": "time_gap",
            "course_type": "hilly",
            "distance_m": 120000,
            "total_gain_m": 2000,
            "drop_rate_pct": 45,
            "drop_rate_label": "high",
            "field_size_median": 30,
            "teammate_names": [],
            "edition_count": 5,
            "elevation_sparkline_points": None,
            "climbs_json": None,
            "typical_field_duration_min": 180,
            "rwgps_encoded_polyline": None,
            "distribution_json": None,
        }
        card = build_card_html(item)
        assert "#E8F5E9" not in card


# --- Sprint 014: Missing data chips ---


class TestMissingDataChips:
    def _make_item(self, is_upcoming=True, **overrides):
        base = {
            "display_name": "Test Race",
            "location": None,
            "state_province": None,
            "is_upcoming": is_upcoming,
            "upcoming_date": None,
            "days_until": 10 if is_upcoming else None,
            "most_recent_date": None,
            "race_type": None,
            "predicted_finish_type": None,
            "confidence": None,
            "prediction_source": None,
            "course_type": None,
            "distance_m": None,
            "total_gain_m": None,
            "drop_rate_pct": None,
            "drop_rate_label": None,
            "field_size_median": None,
            "teammate_names": [],
            "edition_count": 0,
            "elevation_sparkline_points": None,
            "climbs_json": None,
            "typical_field_duration_min": None,
            "rwgps_encoded_polyline": None,
            "distribution_json": None,
        }
        base.update(overrides)
        return base

    def test_upcoming_missing_distance_shows_placeholder(self):
        item = self._make_item(is_upcoming=True, distance_m=None)
        card = build_card_html(item)
        assert "-- km" in card

    def test_upcoming_missing_elevation_shows_placeholder(self):
        item = self._make_item(is_upcoming=True, total_gain_m=None)
        card = build_card_html(item)
        assert "-- m" in card

    def test_upcoming_missing_duration_shows_placeholder(self):
        item = self._make_item(
            is_upcoming=True, typical_field_duration_min=None
        )
        card = build_card_html(item)
        assert "~? min" in card

    def test_past_missing_distance_hidden(self):
        item = self._make_item(is_upcoming=False, distance_m=None)
        card = build_card_html(item)
        assert "-- km" not in card

    def test_past_missing_elevation_hidden(self):
        item = self._make_item(is_upcoming=False, total_gain_m=None)
        card = build_card_html(item)
        assert "-- m" not in card

    def test_zero_distance_still_shows(self):
        """Truthy check fix: distance_m=0 should still render."""
        item = self._make_item(is_upcoming=True, distance_m=0)
        card = build_card_html(item)
        assert "0 km" in card


# --- Sprint 015: Two-column layout tests ---


class TestTwoColumnLayout:
    """Sprint 015: CL-01 through CL-05."""

    def _make_item(self, **overrides):
        base = {
            "display_name": "Test Race",
            "location": "Portland",
            "state_province": "OR",
            "is_upcoming": True,
            "upcoming_date": None,
            "days_until": 5,
            "most_recent_date": None,
            "race_type": "road_race",
            "predicted_finish_type": "bunch_sprint",
            "confidence": "high",
            "prediction_source": "time_gap",
            "course_type": "rolling",
            "distance_m": 85000,
            "total_gain_m": 850,
            "drop_rate_pct": 15,
            "drop_rate_label": "low",
            "field_size_median": 45,
            "teammate_names": [],
            "edition_count": 5,
            "elevation_sparkline_points": None,
            "climbs_json": None,
            "typical_field_duration_min": 120,
            "rwgps_encoded_polyline": None,
            "distribution_json": None,
        }
        base.update(overrides)
        return base

    def test_two_column_when_visuals_present(self):
        """CL-01: Card uses two-column grid when visuals exist."""
        item = self._make_item(
            elevation_sparkline_points=[{"e": 100}, {"e": 200}, {"e": 150}],
        )
        card = build_card_html(item)
        assert "grid-template-columns:1fr auto" in card
        assert "feed-card-left" in card
        assert "feed-card-right" in card

    def test_single_column_no_visuals(self):
        """CL-04: Card collapses to single column when no visuals."""
        item = self._make_item()
        card = build_card_html(item)
        assert "grid-template-columns:1fr;" in card
        assert "feed-card-right" not in card

    def test_countdown_pill_inline_with_name(self):
        """CL-02: Countdown pill appears inline next to race name."""
        from datetime import date

        item = self._make_item(
            is_upcoming=True,
            upcoming_date=date(2026, 4, 1),
            days_until=3,
        )
        card = build_card_html(item)
        # Pill should have margin-left (inline with name)
        assert "margin-left:6px" in card
        assert "in 3 days" in card

    def test_no_prediction_details_section(self):
        """Sprint 018: Prediction details <details> section removed."""
        item = self._make_item(
            drop_rate_pct=15,
            predicted_finish_type="bunch_sprint",
            course_type="flat",
            distance_m=30000,
        )
        card = build_card_html(item)
        assert "feed-card-prediction-details" not in card
        assert "Beginner-friendly" not in card

    def test_no_info_icon(self):
        """Sprint 018: Info icon removed."""
        item = self._make_item()
        card = build_card_html(item)
        assert "feed-card-info" not in card

    def test_responsive_css_in_styles(self):
        """Sprint 019: Responsive CSS rule exists for mobile collapse at 700px."""
        from pathlib import Path

        card_path = (
            Path(__file__).parent.parent / "raceanalyzer" / "ui" / "feed_card.py"
        )
        source = card_path.read_text()
        assert "@media (max-width: 700px)" in source
        assert "grid-template-columns: 56px 1fr !important" in source


# --- Sprint 015: resolve_racer_profile tests ---


class TestResolveRacerProfile:
    """Sprint 015: FG-01 through FG-04."""

    SAMPLE_CATS = [
        "Cat 3",
        "Cat 3 Women",
        "Cat 4/5",
        "Cat 4/5 Women",
        "Cat 1/2/3 Masters 35+",
        "Cat 4/5 Masters 35+",
        "Master 45+",
        "Men Cat 3",
        "Women Cat 4",
    ]

    def test_no_filters_returns_none(self):
        from raceanalyzer.queries import resolve_racer_profile

        result, exact = resolve_racer_profile(self.SAMPLE_CATS)
        assert result is None
        assert exact is True

    def test_cat_level_filter(self):
        from raceanalyzer.queries import resolve_racer_profile

        result, exact = resolve_racer_profile(self.SAMPLE_CATS, cat_level="3")
        assert result is not None
        assert "3" in result

    def test_gender_women_filter(self):
        from raceanalyzer.queries import resolve_racer_profile

        result, exact = resolve_racer_profile(self.SAMPLE_CATS, gender="W")
        assert result is not None
        assert "Women" in result or "women" in result.lower()

    def test_masters_filter(self):
        from raceanalyzer.queries import resolve_racer_profile

        result, exact = resolve_racer_profile(
            self.SAMPLE_CATS, masters_on=True, masters_age=45
        )
        assert result is not None
        # Masters racer matches both masters and non-masters fields;
        # wrapper picks shortest (most specific) for query filtering
        assert "3" in result or "aster" in result

    def test_combined_cat_and_gender(self):
        from raceanalyzer.queries import resolve_racer_profile

        result, exact = resolve_racer_profile(
            self.SAMPLE_CATS, cat_level="3", gender="W"
        )
        assert result is not None
        # Should match "Cat 3 Women"
        assert "3" in result
        assert "Women" in result or "women" in result.lower()

    def test_no_match_returns_none(self):
        from raceanalyzer.queries import resolve_racer_profile

        # Empty category list should return None
        result, exact = resolve_racer_profile(
            [], cat_level="5", gender="W"
        )
        assert result is None
        assert exact is False


# --- Sprint 018: Race length display tests ---


class TestRaceLengthDisplay:
    """Sprint 020: Feed chips always show cross-field range, never category-specific."""

    def _make_item(self, **overrides):
        base = {
            "display_name": "Test Race",
            "location": None,
            "state_province": None,
            "is_upcoming": True,
            "upcoming_date": None,
            "days_until": 5,
            "most_recent_date": None,
            "race_type": "road_race",
            "predicted_finish_type": "bunch_sprint",
            "confidence": "high",
            "prediction_source": "time_gap",
            "course_type": "rolling",
            "distance_m": 85000,
            "total_gain_m": 850,
            "drop_rate_pct": 15,
            "drop_rate_label": "low",
            "field_size_median": 45,
            "teammate_names": [],
            "edition_count": 5,
            "elevation_sparkline_points": None,
            "climbs_json": None,
            "typical_field_duration_min": 120,
            "rwgps_encoded_polyline": None,
            "distribution_json": None,
            "distance_range": None,
            "estimated_time_range": None,
            "hide_estimated_time": False,
        }
        base.update(overrides)
        return base

    def test_distance_range(self):
        item = self._make_item(distance_range="30-60 mi")
        card = build_card_html(item)
        assert "30-60 mi" in card

    def test_fallback_to_course_distance(self):
        item = self._make_item(distance_m=85000)
        card = build_card_html(item)
        assert "85 km" in card

    def test_range_takes_priority_over_course_distance(self):
        """Sprint 020: distance_range always wins over Course.distance_m."""
        item = self._make_item(
            distance_range="30-60 mi",
            distance_m=85000,
        )
        card = build_card_html(item)
        assert "30-60 mi" in card
        assert "85 km" not in card


class TestEstimatedTime:
    """Sprint 018: Estimated time display in chips."""

    def _make_item(self, **overrides):
        base = {
            "display_name": "Test Race",
            "location": None,
            "state_province": None,
            "is_upcoming": True,
            "upcoming_date": None,
            "days_until": 5,
            "most_recent_date": None,
            "race_type": "road_race",
            "predicted_finish_type": "bunch_sprint",
            "confidence": "high",
            "prediction_source": "time_gap",
            "course_type": "rolling",
            "distance_m": 85000,
            "total_gain_m": 850,
            "drop_rate_pct": 15,
            "drop_rate_label": "low",
            "field_size_median": 45,
            "teammate_names": [],
            "edition_count": 5,
            "elevation_sparkline_points": None,
            "climbs_json": None,
            "typical_field_duration_min": 120,
            "rwgps_encoded_polyline": None,
            "distribution_json": None,
            "category_distance": None,
            "category_distance_unit": None,
            "distance_range": None,
            "estimated_time_range": None,
            "hide_estimated_time": False,
        }
        base.update(overrides)
        return base

    def test_estimated_time_range_shown(self):
        item = self._make_item(estimated_time_range="~1h 30m - ~3h 00m")
        card = build_card_html(item)
        assert "~1h 30m - ~3h 00m" in card

    def test_hidden_for_crits(self):
        item = self._make_item(
            race_type="criterium",
            hide_estimated_time=True,
            typical_field_duration_min=45,
        )
        card = build_card_html(item)
        assert "~45m" not in card
        assert "~? min" not in card

    def test_hidden_for_duration_races(self):
        item = self._make_item(
            hide_estimated_time=True,
            typical_field_duration_min=60,
        )
        card = build_card_html(item)
        assert "~1h 00m" not in card


class TestCardSimplification:
    """Sprint 018: Verify removed elements are gone."""

    def _make_item(self, **overrides):
        base = {
            "display_name": "Test Race",
            "location": "Portland",
            "state_province": "OR",
            "is_upcoming": True,
            "upcoming_date": None,
            "days_until": 5,
            "most_recent_date": None,
            "race_type": "road_race",
            "predicted_finish_type": "bunch_sprint",
            "confidence": "high",
            "prediction_source": "time_gap",
            "course_type": "flat",
            "distance_m": 30000,
            "total_gain_m": 50,
            "drop_rate_pct": 5,
            "drop_rate_label": "low",
            "field_size_median": 40,
            "teammate_names": [],
            "edition_count": 5,
            "elevation_sparkline_points": None,
            "climbs_json": None,
            "typical_field_duration_min": 45,
            "rwgps_encoded_polyline": None,
            "distribution_json": None,
            "category_distance": None,
            "category_distance_unit": None,
            "distance_range": None,
            "estimated_time_range": None,
            "hide_estimated_time": False,
        }
        base.update(overrides)
        return base

    def test_no_info_icon(self):
        card = build_card_html(self._make_item())
        assert "feed-card-info" not in card

    def test_no_beginner_badge(self):
        card = build_card_html(self._make_item())
        assert "Beginner-friendly" not in card
        assert "feed-card-beginner" not in card

    def test_no_prediction_details(self):
        card = build_card_html(self._make_item())
        assert "feed-card-prediction-details" not in card
        assert "More</summary>" not in card


# --- Sprint 019: Row HTML tests ---


class TestBuildRowHtml:
    def _make_item(self, **overrides):
        from datetime import date

        base = {
            "display_name": "Banana Belt RR",
            "location": "Maryhill",
            "state_province": "WA",
            "is_upcoming": True,
            "upcoming_date": date(2026, 3, 15),
            "days_until": 5,
            "most_recent_date": None,
            "race_type": "road_race",
            "predicted_finish_type": "bunch_sprint",
            "confidence": "high",
            "prediction_source": "time_gap",
            "course_type": "rolling",
            "distance_m": 85000,
            "total_gain_m": 850,
            "drop_rate_pct": 15,
            "drop_rate_label": "low",
            "field_size_median": 45,
            "teammate_names": [],
            "edition_count": 5,
            "elevation_sparkline_points": None,
            "climbs_json": None,
            "typical_field_duration_min": 120,
            "rwgps_encoded_polyline": None,
            "distribution_json": None,
            "category_distance": None,
            "category_distance_unit": None,
            "distance_range": None,
            "estimated_time_range": None,
            "hide_estimated_time": False,
        }
        base.update(overrides)
        return base

    def test_feed_row_class(self):
        row = build_row_html(self._make_item())
        assert "feed-row" in row

    def test_date_contains_month_and_day(self):
        row = build_row_html(self._make_item())
        assert "feed-row-date" in row
        assert "MAR" in row
        assert "15" in row

    def test_ai_sez_before_chips(self):
        row = build_row_html(self._make_item())
        ai_pos = row.find("feed-row-ai")
        chips_pos = row.find("feed-card-chips")
        assert ai_pos > 0
        assert chips_pos > 0
        assert ai_pos < chips_pos

    def test_visuals_present_with_polyline(self):
        try:
            import polyline as pl
            coords = [(45.5, -122.6), (45.51, -122.61), (45.52, -122.59)]
            encoded = pl.encode(coords)
        except ImportError:
            pytest.skip("polyline not installed")
        row = build_row_html(self._make_item(rwgps_encoded_polyline=encoded))
        assert "feed-row-visuals" in row
        assert "168px" in row

    def test_no_visuals_two_column(self):
        row = build_row_html(self._make_item())
        assert "feed-row-visuals" not in row
        assert "grid-template-columns:72px 1fr" in row

    def test_html_escaping_category_in_ai_sez(self):
        row = build_row_html(self._make_item(
            ai_context={
                "mode": "single_match",
                "best_category": "Cat <3> & 'evil'",
                "ai_sez_text": 'For Cat <3> & \'evil\': the group sprints',
            },
        ))
        assert "<3>" not in row
        assert "&lt;3&gt;" in row or "&#" in row

    def test_past_date_reduced_opacity(self):
        from datetime import date

        row = build_row_html(self._make_item(
            is_upcoming=False,
            upcoming_date=None,
            most_recent_date=date(2025, 6, 15),
            days_until=None,
        ))
        assert "opacity:0.45" in row

    def test_ai_context_text_used(self):
        row = build_row_html(self._make_item(
            ai_context={
                "mode": "overall",
                "ai_sez_text": "Custom AI text here",
            },
        ))
        assert "Custom AI text here" in row
