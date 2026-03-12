"""Tests for maps module (Sprint 013)."""

from __future__ import annotations

import pytest

from raceanalyzer.ui.maps import haversine_km, polyline_centroid


class TestHaversineKm:
    def test_same_point_is_zero(self):
        assert haversine_km(45.5, -122.6, 45.5, -122.6) == 0.0

    def test_known_distance(self):
        # Portland to Seattle is ~280 km
        dist = haversine_km(45.5, -122.6, 47.6, -122.3)
        assert 230 < dist < 250

    def test_symmetry(self):
        d1 = haversine_km(45.5, -122.6, 47.6, -122.3)
        d2 = haversine_km(47.6, -122.3, 45.5, -122.6)
        assert abs(d1 - d2) < 0.01


class TestPolylineCentroid:
    def test_none_returns_none(self):
        assert polyline_centroid(None) is None

    def test_empty_string_returns_none(self):
        assert polyline_centroid("") is None

    def test_valid_polyline(self):
        try:
            import polyline as pl

            coords = [(45.5, -122.6), (45.51, -122.61), (45.52, -122.59)]
            encoded = pl.encode(coords)
            result = polyline_centroid(encoded)
            assert result is not None
            lat, lon = result
            assert 45.49 < lat < 45.53
            assert -122.62 < lon < -122.58
        except ImportError:
            pytest.skip("polyline not installed")
