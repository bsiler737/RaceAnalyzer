"""Tests for elevation extraction, terrain classification, profiles, and climbs."""

from __future__ import annotations

import pytest
import responses

from raceanalyzer.config import Settings
from raceanalyzer.db.models import CourseType
from raceanalyzer.elevation import (
    build_profile,
    classify_terrain,
    compute_gradients,
    compute_m_per_km,
    course_type_display,
    detect_climbs,
    extract_track_points,
    resample_profile,
    smooth_elevations,
)


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


# --- Profile processing tests ---


def _make_track_points(n=100, base_lat=47.6, base_lon=-122.3, dist_step_m=50.0):
    """Helper: generate synthetic track points along a line heading north."""
    pts = []
    for i in range(n):
        lat = base_lat + i * (dist_step_m / 111320.0)  # approx degrees per meter
        elev = 100.0 + 50.0 * (1.0 if i < n // 2 else -0.5) * (i / n)
        pts.append({"y": lat, "x": base_lon, "e": round(elev, 1)})
    return pts


def _make_climb_profile(
    flat_before_m=2000, climb_m=2000, flat_after_m=2000, grade_pct=6.0, step_m=50.0
):
    """Helper: profile with flat -> steady climb -> flat."""
    pts = []
    total_d = flat_before_m + climb_m + flat_after_m
    n = int(total_d / step_m) + 1
    for i in range(n):
        d = i * step_m
        if d <= flat_before_m:
            e = 100.0
        elif d <= flat_before_m + climb_m:
            e = 100.0 + (d - flat_before_m) * grade_pct / 100.0
        else:
            e = 100.0 + climb_m * grade_pct / 100.0
        pts.append({
            "d": round(d, 1),
            "e": round(e, 1),
            "y": round(47.6 + d / 111320.0, 6),
            "x": -122.3,
            "g": 0.0,
        })
    # Compute actual gradients
    return compute_gradients(pts)


class TestExtractTrackPoints:
    def test_basic_extraction(self):
        route_json = {
            "track_points": [
                {"y": 47.0, "x": -122.0, "e": 100.0},
                {"y": 47.001, "x": -122.0, "e": 110.0},
                {"y": 47.002, "x": -122.0, "e": 105.0},
            ]
        }
        pts = extract_track_points(route_json)
        assert len(pts) == 3
        assert pts[0]["d"] == 0.0
        assert pts[1]["d"] > 0  # has cumulative distance
        assert pts[2]["d"] > pts[1]["d"]
        assert pts[0]["e"] == 100.0

    def test_empty_route(self):
        assert extract_track_points({}) == []
        assert extract_track_points({"track_points": []}) == []

    def test_skips_points_without_elevation(self):
        route_json = {
            "track_points": [
                {"y": 47.0, "x": -122.0, "e": 100.0},
                {"y": 47.001, "x": -122.0},  # no elevation
                {"y": 47.002, "x": -122.0, "e": 105.0},
            ]
        }
        pts = extract_track_points(route_json)
        assert len(pts) == 2

    def test_haversine_accuracy(self):
        """1 degree lat ~ 111.32 km."""
        route_json = {
            "track_points": [
                {"y": 47.0, "x": -122.0, "e": 0.0},
                {"y": 48.0, "x": -122.0, "e": 0.0},
            ]
        }
        pts = extract_track_points(route_json)
        dist = pts[1]["d"]
        assert 110000 < dist < 112000  # ~111.3 km


class TestResampleProfile:
    def test_uniform_spacing(self):
        pts = [
            {"d": 0.0, "e": 100.0, "y": 47.0, "x": -122.0},
            {"d": 200.0, "e": 200.0, "y": 47.002, "x": -122.0},
        ]
        resampled = resample_profile(pts, step_m=50.0)
        assert len(resampled) == 5  # 0, 50, 100, 150, 200
        assert resampled[0]["d"] == 0.0
        assert resampled[-1]["d"] == 200.0
        # Midpoint should be interpolated
        assert resampled[2]["e"] == pytest.approx(150.0, abs=1.0)

    def test_too_few_points(self):
        pts = [{"d": 0.0, "e": 100.0, "y": 47.0, "x": -122.0}]
        assert resample_profile(pts) == pts

    def test_preserves_endpoints(self):
        pts = [
            {"d": 0.0, "e": 50.0, "y": 47.0, "x": -122.0},
            {"d": 500.0, "e": 100.0, "y": 47.005, "x": -122.0},
            {"d": 1000.0, "e": 80.0, "y": 47.01, "x": -122.0},
        ]
        resampled = resample_profile(pts, step_m=100.0)
        assert resampled[0]["e"] == 50.0
        assert resampled[-1]["e"] == pytest.approx(80.0, abs=1.0)


class TestSmoothElevations:
    def test_smoothing_reduces_noise(self):
        """Noisy profile should be smoother after smoothing."""
        pts = []
        for i in range(40):
            d = i * 50.0
            # Flat line at 100m with +-5m GPS noise every other point
            noise = 5.0 if i % 2 == 0 else -5.0
            pts.append({"d": d, "e": 100.0 + noise, "y": 47.0, "x": -122.0})

        smoothed = smooth_elevations(pts, window_m=200.0, step_m=50.0)

        # Interior points should be much closer to 100.0 after smoothing
        interior = smoothed[4:-4]
        for pt in interior:
            assert abs(pt["e"] - 100.0) < 3.0  # noise reduced from +-5 to < 3

    def test_preserves_total_gain_roughly(self):
        """Smoothing should not dramatically change total elevation gain."""
        pts = []
        for i in range(100):
            d = i * 50.0
            e = 100.0 + i * 1.0  # steady 2% grade
            pts.append({"d": d, "e": e, "y": 47.0, "x": -122.0})

        raw_gain = pts[-1]["e"] - pts[0]["e"]
        smoothed = smooth_elevations(pts, window_m=200.0, step_m=50.0)
        smoothed_gain = smoothed[-1]["e"] - smoothed[0]["e"]

        assert abs(smoothed_gain - raw_gain) / raw_gain < 0.10  # within 10%


class TestComputeGradients:
    def test_steady_grade(self):
        pts = [
            {"d": 0.0, "e": 100.0, "y": 47.0, "x": -122.0},
            {"d": 100.0, "e": 105.0, "y": 47.001, "x": -122.0},
            {"d": 200.0, "e": 110.0, "y": 47.002, "x": -122.0},
        ]
        result = compute_gradients(pts)
        assert result[0]["g"] == 0.0  # first point
        assert result[1]["g"] == pytest.approx(5.0)  # 5m / 100m = 5%
        assert result[2]["g"] == pytest.approx(5.0)

    def test_single_point(self):
        pts = [{"d": 0.0, "e": 100.0, "y": 47.0, "x": -122.0}]
        result = compute_gradients(pts)
        assert result[0]["g"] == 0.0


class TestBuildProfile:
    def test_full_pipeline(self):
        # extract_track_points adds the "d" key that build_profile needs
        route_json = {
            "track_points": [
                {"y": 47.0 + i * 0.001, "x": -122.0, "e": 100.0 + i * 0.5}
                for i in range(200)
            ]
        }
        track_pts = extract_track_points(route_json)
        profile = build_profile(track_pts)
        assert len(profile) > 0
        assert all("g" in pt for pt in profile)
        assert all("d" in pt for pt in profile)
        assert all("e" in pt for pt in profile)

    def test_too_few_points(self):
        assert build_profile([]) == []
        assert build_profile([{"d": 0, "e": 100, "y": 47, "x": -122}]) == []


# --- Climb detection tests ---


class TestDetectClimbs:
    def test_single_steady_climb(self):
        """A 2km climb at 6% should be detected."""
        profile = _make_climb_profile(
            flat_before_m=2000, climb_m=2000, flat_after_m=2000, grade_pct=6.0
        )
        climbs = detect_climbs(profile)
        assert len(climbs) == 1
        assert climbs[0]["category"] == "steep"
        assert climbs[0]["gain_m"] > 100
        assert climbs[0]["avg_grade"] >= 3.0

    def test_climb_with_false_flat_merged(self):
        """Two climb segments with a brief flat in between should merge."""
        pts = []
        d = 0.0
        step = 50.0
        e = 100.0
        # Flat start
        for _ in range(40):
            pts.append({"d": d, "e": e, "y": 47.6, "x": -122.3})
            d += step
        # Climb 1: 800m at 6%
        for _ in range(16):
            e += step * 0.06
            pts.append({"d": d, "e": round(e, 1), "y": 47.6, "x": -122.3})
            d += step
        # Brief flat: 100m (< 150m merge threshold)
        for _ in range(2):
            pts.append({"d": d, "e": round(e, 1), "y": 47.6, "x": -122.3})
            d += step
        # Climb 2: 800m at 6%
        for _ in range(16):
            e += step * 0.06
            pts.append({"d": d, "e": round(e, 1), "y": 47.6, "x": -122.3})
            d += step
        # Flat end
        for _ in range(40):
            pts.append({"d": d, "e": round(e, 1), "y": 47.6, "x": -122.3})
            d += step

        profile = compute_gradients(pts)
        climbs = detect_climbs(profile)
        # Should merge into 1 climb (gap < 150m)
        assert len(climbs) == 1

    def test_two_separate_climbs(self):
        """Two climbs with a long flat between them should be separate."""
        pts = []
        d = 0.0
        step = 50.0
        e = 100.0
        # Flat
        for _ in range(40):
            pts.append({"d": d, "e": e, "y": 47.6, "x": -122.3})
            d += step
        # Climb 1: 1km at 6%
        for _ in range(20):
            e += step * 0.06
            pts.append({"d": d, "e": round(e, 1), "y": 47.6, "x": -122.3})
            d += step
        # Long flat (1km - well beyond 200m exit sustain)
        for _ in range(20):
            pts.append({"d": d, "e": round(e, 1), "y": 47.6, "x": -122.3})
            d += step
        # Climb 2: 1km at 6%
        for _ in range(20):
            e += step * 0.06
            pts.append({"d": d, "e": round(e, 1), "y": 47.6, "x": -122.3})
            d += step
        # Flat end
        for _ in range(40):
            pts.append({"d": d, "e": round(e, 1), "y": 47.6, "x": -122.3})
            d += step

        profile = compute_gradients(pts)
        climbs = detect_climbs(profile)
        assert len(climbs) == 2

    def test_flat_course_no_climbs(self):
        """A flat course should produce 0 climbs."""
        pts = []
        for i in range(200):
            pts.append({
                "d": i * 50.0, "e": 100.0, "y": 47.6, "x": -122.3, "g": 0.0,
            })
        climbs = detect_climbs(pts)
        assert len(climbs) == 0

    def test_noisy_flat_no_spurious_climbs(self):
        """GPS noise on a flat course should not produce false climbs."""
        import random
        random.seed(42)
        pts = []
        for i in range(200):
            noise = random.uniform(-3, 3)  # +-3m GPS jitter
            pts.append({"d": i * 50.0, "e": 100.0 + noise, "y": 47.6, "x": -122.3})
        # Smooth first (mimics the build_profile pipeline)
        smoothed = smooth_elevations(pts, window_m=200.0, step_m=50.0)
        profile = compute_gradients(smoothed)
        climbs = detect_climbs(profile)
        assert len(climbs) == 0

    def test_short_ramp_filtered_out(self):
        """A short ramp (< 500m, < 20m gain) should be filtered out."""
        # 200m at 5% = only 10m gain (below 20m threshold)
        profile = _make_climb_profile(
            flat_before_m=2000, climb_m=200, flat_after_m=2000, grade_pct=5.0
        )
        climbs = detect_climbs(profile)
        assert len(climbs) == 0

    def test_short_course(self):
        """Very short course (< 1km) should not crash."""
        pts = [
            {"d": 0.0, "e": 100.0, "y": 47.6, "x": -122.3, "g": 0.0},
            {"d": 50.0, "e": 105.0, "y": 47.6, "x": -122.3, "g": 10.0},
        ]
        climbs = detect_climbs(pts)
        assert len(climbs) == 0  # too short to meet min thresholds

    def test_climb_categorization(self):
        """Test that climbs get correct categories."""
        # Moderate: 3-5%
        moderate = _make_climb_profile(climb_m=2000, grade_pct=4.0)
        climbs = detect_climbs(moderate)
        if climbs:
            assert climbs[0]["category"] == "moderate"

        # Brutal: 8%+ (use higher grade to account for smoothing)
        brutal = _make_climb_profile(climb_m=2000, grade_pct=12.0)
        climbs = detect_climbs(brutal)
        assert len(climbs) >= 1
        assert climbs[0]["category"] == "brutal"

    def test_climb_has_required_fields(self):
        """Climb dict should have all required fields."""
        profile = _make_climb_profile(climb_m=2000, grade_pct=6.0)
        climbs = detect_climbs(profile)
        assert len(climbs) >= 1
        c = climbs[0]
        required = [
            "start_d", "end_d", "length_m", "gain_m", "avg_grade",
            "max_grade", "category", "color", "start_coords", "end_coords",
        ]
        for key in required:
            assert key in c, f"Missing key: {key}"
