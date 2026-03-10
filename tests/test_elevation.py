"""Tests for elevation extraction and terrain classification."""

from __future__ import annotations

import pytest
import responses

from raceanalyzer.config import Settings
from raceanalyzer.db.models import CourseType
from raceanalyzer.elevation import classify_terrain, compute_m_per_km, course_type_display


class TestComputeMPerKm:
    def test_normal_values(self):
        assert compute_m_per_km(500.0, 50000.0) == pytest.approx(10.0)

    def test_zero_distance(self):
        assert compute_m_per_km(500.0, 0.0) is None

    def test_negative_distance(self):
        assert compute_m_per_km(500.0, -100.0) is None

    def test_none_gain(self):
        assert compute_m_per_km(None, 50000.0) is None

    def test_none_distance(self):
        assert compute_m_per_km(500.0, None) is None

    def test_both_none(self):
        assert compute_m_per_km(None, None) is None

    def test_zero_gain(self):
        assert compute_m_per_km(0.0, 50000.0) == pytest.approx(0.0)


class TestClassifyTerrain:
    def test_flat(self):
        assert classify_terrain(4.9) == CourseType.FLAT

    def test_flat_zero(self):
        assert classify_terrain(0.0) == CourseType.FLAT

    def test_rolling_boundary(self):
        assert classify_terrain(5.0) == CourseType.ROLLING

    def test_rolling_mid(self):
        assert classify_terrain(7.5) == CourseType.ROLLING

    def test_hilly_boundary(self):
        assert classify_terrain(10.0) == CourseType.HILLY

    def test_hilly_mid(self):
        assert classify_terrain(12.0) == CourseType.HILLY

    def test_mountainous_boundary(self):
        assert classify_terrain(15.0) == CourseType.MOUNTAINOUS

    def test_mountainous_high(self):
        assert classify_terrain(25.0) == CourseType.MOUNTAINOUS

    def test_unknown_none(self):
        assert classify_terrain(None) == CourseType.UNKNOWN

    def test_custom_thresholds(self):
        settings = Settings()
        settings.terrain_flat_max = 3.0
        settings.terrain_rolling_max = 6.0
        settings.terrain_hilly_max = 12.0
        assert classify_terrain(4.0, settings) == CourseType.ROLLING
        assert classify_terrain(2.9, settings) == CourseType.FLAT


class TestCourseTypeDisplay:
    def test_known_types(self):
        assert course_type_display("flat") == "Flat"
        assert course_type_display("mountainous") == "Mountainous"
        assert course_type_display("unknown") == "Unknown Terrain"

    def test_fallback(self):
        assert course_type_display("some_new_type") == "Some New Type"


class TestFetchRouteElevation:
    @responses.activate
    def test_summary_stats_present(self):
        from raceanalyzer.rwgps import fetch_route_elevation

        responses.add(
            responses.GET,
            "https://ridewithgps.com/routes/12345.json",
            json={
                "elevation_gain": 500.0,
                "elevation_loss": 480.0,
                "distance": 50000.0,
                "max_elevation": 300.0,
                "min_elevation": 50.0,
            },
            status=200,
        )

        result = fetch_route_elevation(12345)
        assert result is not None
        assert result["distance_m"] == 50000.0
        assert result["total_gain_m"] == 500.0
        assert result["total_loss_m"] == 480.0
        assert result["max_elevation_m"] == 300.0
        assert result["min_elevation_m"] == 50.0

    @responses.activate
    def test_track_points_fallback(self):
        from raceanalyzer.rwgps import fetch_route_elevation

        responses.add(
            responses.GET,
            "https://ridewithgps.com/routes/99999.json",
            json={
                "track_points": [
                    {"y": 47.0, "x": -122.0, "e": 100.0},
                    {"y": 47.001, "x": -122.001, "e": 150.0},
                    {"y": 47.002, "x": -122.002, "e": 120.0},
                ]
            },
            status=200,
        )

        result = fetch_route_elevation(99999)
        assert result is not None
        assert result["total_gain_m"] == 50.0
        assert result["total_loss_m"] == 30.0
        assert result["max_elevation_m"] == 150.0
        assert result["min_elevation_m"] == 100.0
        assert result["distance_m"] > 0

    @responses.activate
    def test_both_missing(self):
        from raceanalyzer.rwgps import fetch_route_elevation

        responses.add(
            responses.GET,
            "https://ridewithgps.com/routes/11111.json",
            json={},
            status=200,
        )

        result = fetch_route_elevation(11111)
        assert result is None

    @responses.activate
    def test_http_error(self):
        from raceanalyzer.rwgps import fetch_route_elevation

        responses.add(
            responses.GET,
            "https://ridewithgps.com/routes/00000.json",
            status=404,
        )

        result = fetch_route_elevation(0)
        assert result is None


class TestComputeElevationFromTrack:
    def test_empty_track(self):
        from raceanalyzer.rwgps import _compute_elevation_from_track

        assert _compute_elevation_from_track([]) is None

    def test_single_point(self):
        from raceanalyzer.rwgps import _compute_elevation_from_track

        assert _compute_elevation_from_track([{"y": 47, "x": -122, "e": 100}]) is None
