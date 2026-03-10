"""Tests for RWGPS route scoring algorithm."""

from __future__ import annotations

from raceanalyzer.rwgps import MIN_MATCH_SCORE, _clean_search_name, _haversine, score_route


class TestCleanSearchName:
    def test_strips_year(self):
        assert _clean_search_name("2024 Banana Belt RR") == "Banana Belt"

    def test_strips_road_race(self):
        assert _clean_search_name("Banana Belt Road Race") == "Banana Belt"

    def test_strips_criterium(self):
        assert _clean_search_name("Cherry Pie Criterium") == "Cherry Pie"

    def test_strips_combined(self):
        assert _clean_search_name("2023 Cherry Pie Crit") == "Cherry Pie"


class TestHaversine:
    def test_same_point(self):
        assert _haversine(45.0, -122.0, 45.0, -122.0) == 0.0

    def test_known_distance(self):
        # Portland to Seattle ~233 km
        dist = _haversine(45.5231, -122.6765, 47.6062, -122.3321)
        assert 230 < dist < 240


class TestScoreRoute:
    def test_exact_name_nearby(self):
        route = {
            "name": "Banana Belt Road Race",
            "first_lat": 45.67,
            "first_lng": -120.82,
            "distance": 80000,  # 80km
        }
        score = score_route(route, "Banana Belt RR", 45.68, -120.83, "road_race")
        assert score > 0.6

    def test_wrong_name_nearby(self):
        route = {
            "name": "Completely Different Route",
            "first_lat": 45.67,
            "first_lng": -120.82,
            "distance": 80000,
        }
        score = score_route(route, "Banana Belt RR", 45.68, -120.83, "road_race")
        # Wrong name but nearby + right distance still scores moderate
        # Should be significantly lower than an exact name match
        exact = score_route(
            dict(route, name="Banana Belt Road Race"),
            "Banana Belt RR", 45.68, -120.83, "road_race",
        )
        assert score < exact

    def test_right_name_far_away(self):
        route = {
            "name": "Banana Belt Road Race",
            "first_lat": 35.0,  # California
            "first_lng": -118.0,
            "distance": 80000,
        }
        score = score_route(route, "Banana Belt RR", 45.68, -120.83, "road_race")
        # Name match helps but proximity hurts
        assert 0.2 < score < 0.6

    def test_crit_rejects_long_route(self):
        route = {
            "name": "Cherry Pie Criterium",
            "first_lat": 37.77,
            "first_lng": -122.42,
            "distance": 100000,  # 100km - way too long for a crit
        }
        score = score_route(route, "Cherry Pie Crit", 37.78, -122.43, "criterium")
        # Length penalty should be significant
        route_short = dict(route, distance=2000)  # 2km crit course
        score_short = score_route(route_short, "Cherry Pie Crit", 37.78, -122.43, "criterium")
        assert score_short > score

    def test_no_coords_default_proximity(self):
        route = {"name": "Some Route", "distance": 50000}
        score = score_route(route, "Some Route", None, None)
        # Should still produce a reasonable score from name match + defaults
        assert score > 0.0

    def test_below_threshold_is_low(self):
        route = {"name": "Unrelated Thing", "distance": 0}
        score = score_route(route, "Banana Belt RR", None, None)
        assert score < 0.5
