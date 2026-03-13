"""Stage race schedule loader from YAML files."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

from raceanalyzer.db.models import RaceType

logger = logging.getLogger("raceanalyzer")

_STAGES_DIR = Path(__file__).resolve().parent.parent / "data" / "stages"

# Valid race types for individual stages (stage_race is not valid for a stage)
_VALID_STAGE_TYPES = {rt.value for rt in RaceType if rt != RaceType.STAGE_RACE}


@dataclass(frozen=True)
class StageDefinition:
    number: int
    name: str
    race_type: str
    date: date
    rwgps_route_id: int | None = None
    elites_only: bool = False


@lru_cache(maxsize=64)
def load_stage_schedule(normalized_name: str) -> tuple[StageDefinition, ...] | None:
    """Load stage schedule from data/stages/{name}.yaml.

    Returns tuple of StageDefinition (hashable for lru_cache), or None if
    no file exists or validation fails.
    """
    filename = normalized_name.replace(" ", "_") + ".yaml"
    filepath = _STAGES_DIR / filename

    if not filepath.is_file():
        return None

    try:
        with open(filepath) as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, OSError) as e:
        logger.warning("Failed to load stage schedule %s: %s", filepath, e)
        return None

    if not isinstance(data, dict) or "stages" not in data:
        logger.warning("Invalid stage schedule format in %s", filepath)
        return None

    stages_data = data["stages"]
    if not isinstance(stages_data, list) or not stages_data:
        logger.warning("Empty or invalid stages list in %s", filepath)
        return None

    stages = []
    seen_numbers = set()

    for entry in stages_data:
        # Validate required fields
        if not isinstance(entry, dict):
            logger.warning("Invalid stage entry in %s: %s", filepath, entry)
            return None

        for field in ("stage", "name", "race_type", "date"):
            if field not in entry:
                logger.warning("Missing required field '%s' in %s", field, filepath)
                return None

        stage_num = entry["stage"]
        if not isinstance(stage_num, int) or stage_num < 1:
            logger.warning("Invalid stage number %s in %s", stage_num, filepath)
            return None

        if stage_num in seen_numbers:
            logger.warning("Duplicate stage number %d in %s", stage_num, filepath)
            return None
        seen_numbers.add(stage_num)

        race_type = entry["race_type"]
        if race_type not in _VALID_STAGE_TYPES:
            logger.warning("Invalid race_type '%s' in %s", race_type, filepath)
            return None

        try:
            stage_date = date.fromisoformat(str(entry["date"]))
        except (ValueError, TypeError):
            logger.warning("Invalid date '%s' in %s", entry["date"], filepath)
            return None

        stages.append(StageDefinition(
            number=stage_num,
            name=str(entry["name"]),
            race_type=race_type,
            date=stage_date,
            rwgps_route_id=entry.get("rwgps_route_id"),
            elites_only=bool(entry.get("elites_only", False)),
        ))

    # Validate contiguous numbering from 1
    expected = set(range(1, len(stages) + 1))
    if seen_numbers != expected:
        logger.warning(
            "Non-contiguous stage numbers in %s: got %s, expected %s",
            filepath, sorted(seen_numbers), sorted(expected),
        )
        return None

    # Sort by stage number
    stages.sort(key=lambda s: s.number)
    return tuple(stages)
