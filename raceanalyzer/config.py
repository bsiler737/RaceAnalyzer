"""Centralized configuration for RaceAnalyzer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    db_path: Path = Path("data/raceanalyzer.db")
    raw_data_dir: Path = Path("data/raw")
    base_url: str = "https://www.road-results.com"
    max_workers: int = 4
    min_request_delay: float = 3.0
    request_timeout: int = 30
    retry_count: int = 3
    retry_backoff_base: float = 2.0
    max_race_id: int = 15000
    gap_threshold: float = 3.0
    pnw_regions: tuple[str, ...] = field(default_factory=lambda: ("WA", "OR", "ID", "BC"))
    confidence_high_threshold: float = 0.005
    confidence_medium_threshold: float = 0.02

    # Terrain classification thresholds (m/km)
    terrain_flat_max: float = 5.0
    terrain_rolling_max: float = 10.0
    terrain_hilly_max: float = 15.0

    # BikeReg settings (deprecated — use road-results pipeline; retained for --source bikereg)
    bikereg_base_url: str = "https://www.bikereg.com"
    bikereg_request_delay: float = 2.0

    # Road-results calendar & predictor settings (Sprint 009)
    road_results_search_lat: float = 47.6  # Seattle
    road_results_search_lon: float = -122.3
    road_results_search_radius_miles: int = 300
    road_results_calendar_days_ahead: int = 90
    road_results_predictor_delay: float = 1.0

    # Prediction settings
    prediction_min_editions: int = 2
    prediction_min_results: int = 5

    # Climb detection thresholds
    climb_entry_grade: float = 2.5
    climb_entry_sustain_m: float = 150.0
    climb_exit_grade: float = 1.0
    climb_exit_sustain_m: float = 200.0
    climb_merge_gap_m: float = 150.0
    climb_min_length_m: float = 500.0
    climb_min_gain_m: float = 20.0
    climb_min_avg_grade: float = 3.0

    # Speed outlier bounds (kph)
    speed_min_kph: float = 15.0
    speed_max_kph: float = 55.0
    speed_top_k: int = 10

    # Drop rate label thresholds
    drop_rate_low_max: float = 0.10
    drop_rate_moderate_max: float = 0.25
    drop_rate_high_max: float = 0.40

    # Scheduler settings (Sprint 023)
    scheduler_enabled: bool = True
    scheduler_startup_delay_seconds: int = 10
    scheduler_check_interval_hours: float = 6.0
    refresh_daily_interval_hours: float = 24.0
    refresh_weekly_interval_hours: float = 168.0  # 7 days
