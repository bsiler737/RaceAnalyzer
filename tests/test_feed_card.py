"""Tests for feed card v2 renderer (Sprint 013)."""

from __future__ import annotations

import pytest

from raceanalyzer.ui.feed_card import (
    build_card_html,
    confidence_text,
    countdown_pill_style,
    extract_key_climb,
    format_duration,
    generate_ics,
    is_beginner_friendly,
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


class TestIsBeginnerFriendly:
    def test_friendly_race(self):
        item = {
            "drop_rate_pct": 10,
            "predicted_finish_type": "bunch_sprint",
            "distance_m": 40000,
        }
        friendly, reasons = is_beginner_friendly(item)
        assert friendly is True
        assert len(reasons) >= 1

    def test_selective_race(self):
        item = {
            "drop_rate_pct": 40,
            "predicted_finish_type": "gc_selective",
            "distance_m": 120000,
        }
        friendly, reasons = is_beginner_friendly(item)
        assert friendly is False

    def test_missing_data_not_friendly(self):
        item = {}
        friendly, reasons = is_beginner_friendly(item)
        assert friendly is False


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

    def test_beginner_friendly_badge_shown(self):
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
        assert "Beginner-friendly" in card
        assert "Sprinters" in card
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
