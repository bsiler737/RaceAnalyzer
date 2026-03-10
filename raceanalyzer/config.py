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

    # BikeReg settings
    bikereg_base_url: str = "https://www.bikereg.com"
    bikereg_request_delay: float = 2.0

    # Prediction settings
    prediction_min_editions: int = 2
    prediction_min_results: int = 5
