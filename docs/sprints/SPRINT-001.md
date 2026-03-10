# Sprint 001: Data Pipeline Foundation

## Overview

Build the foundational data pipeline for RaceAnalyzer: a Python package that scrapes race results from road-results.com via its hidden JSON API, stores them in a normalized SQLite database, classifies finish types using time-gap analysis, and archives raw responses for future re-parsing. This sprint establishes the project skeleton, database schema, scraper architecture, rule-based finish type classifier, and developer tooling that all future sprints build upon.

The tool's purpose (from seed.md): help PNW bike racers understand race dynamics — what kind of finish to expect, who to watch, and which races match their strengths. This sprint delivers the data foundation that every subsequent feature (predictions, phenotyping, recommendations, UI) requires.

**Scope**: Data acquisition + Finish type classification + Developer tooling
**Deliverable**: A working CLI that can scrape races by ID range, persist results to SQLite, archive raw JSON/HTML, and classify finish types per race-category pair.

## Use Cases

1. **Single race scrape**: `python -m raceanalyzer scrape --race-id 5000` fetches one race's JSON results and HTML metadata, stores in SQLite, archives raw files.
2. **Bulk scrape with resume**: `python -m raceanalyzer scrape --start 1 --end 13000` scrapes all races in parallel. If interrupted, re-running resumes from where it left off via ScrapeLog.
3. **Classify single race**: `python -m raceanalyzer classify --race-id 5000` outputs finish type per category (e.g., P12: BUNCH_SPRINT, Cat 3: BREAKAWAY).
4. **Classify all races**: `python -m raceanalyzer classify --all` processes all unclassified race-category pairs.
5. **Initialize database**: `python -m raceanalyzer init` creates the SQLite database with all tables.
6. **Query foundation** (enabled, not built): Schema supports queries like "all P12 results at Banana Belt across years" and "all BUNCH_SPRINT races in WA."

## Architecture

### Data Flow

```
                            road-results.com
                                  |
                +-----------------+-----------------+
                |                                   |
          HTML Race Page                    JSON API Endpoint
       (name, date, loc)              downloadrace.php?raceID={ID}&json=1
                |                          (29 fields per result)
                v                                   v
       +----------------+                  +-----------------+
       | RacePageParser |                  | RaceResultParser|
       | (regex-based)  |                  | (JSON decode)   |
       +-------+--------+                  +--------+--------+
               |                                    |
               +------- parsed dicts -------+-------+
                                            |
                               +---> Archive raw JSON/HTML
                               |     to data/raw/{race_id}.*
                               v
                    +--------------------+
                    | ScrapeOrchestrator |
                    | (pipeline.py)      |
                    | - dedup riders     |
                    | - validate fields  |
                    | - batch upsert     |
                    | - log to scrape_log|
                    +--------+-----------+
                             |
                             v
              +------------------------------+
              |          SQLite DB            |
              |  races | riders | results    |
              |  race_classifications        |
              |  scrape_log                  |
              +------------------------------+
                             |
                             v
              +------------------------------+
              |    FinishTypeClassifier       |
              |  1. Query results by race+cat |
              |  2. Sort by time              |
              |  3. Consecutive gap grouping  |
              |  4. Compute group metrics     |
              |  5. Apply rule tree           |
              |  6. Store classification +    |
              |     metrics                  |
              +------------------------------+
```

### Package Structure

```
raceanalyzer/
├── __init__.py
├── __main__.py              # CLI entry point
├── cli.py                   # Click CLI: init, scrape, classify
├── config.py                # Settings dataclass
├── db/
│   ├── __init__.py
│   ├── engine.py            # SQLAlchemy engine/session factory
│   └── models.py            # ORM models (5 tables)
├── scraper/
│   ├── __init__.py
│   ├── client.py            # HTTP client: session, retries, rate limiting
│   ├── parsers.py           # RacePageParser (HTML), RaceResultParser (JSON)
│   ├── pipeline.py          # ScrapeOrchestrator: fetch → parse → persist
│   └── errors.py            # ExpectedParsingError, UnexpectedParsingError
├── classification/
│   ├── __init__.py
│   ├── grouping.py          # Time-gap grouping algorithm
│   └── finish_type.py       # Rule-based finish type classifier
└── utils/
    ├── __init__.py
    └── time_parsing.py      # RaceTime string → seconds conversion

tests/
├── conftest.py              # Shared fixtures, in-memory DB
├── fixtures/                # Saved JSON/HTML responses
│   ├── race_sprint.json
│   ├── race_breakaway.json
│   ├── race_selective.json
│   ├── race_no_times.json
│   ├── race_html_meta.html
│   └── labeled_races.json   # 20 hand-labeled races for validation
├── test_scraper.py          # Client + parsers (mocked HTTP)
├── test_pipeline.py         # Integration: scrape → DB
├── test_models.py           # ORM constraints and relationships
├── test_gap_grouping.py     # Gap grouping algorithm
├── test_finish_type.py      # Classification rule tests
└── test_time_parsing.py     # Time format edge cases
```

### Key Design Decisions

1. **JSON API first, HTML supplement**: Core result data from `downloadrace.php?raceID={ID}&json=1` (29 fields). Only race name, date, location from HTML.
2. **Class-per-entity parsers** (from procyclingstats): `RacePageParser` and `RaceResultParser` with auto-discovery `parse()` methods.
3. **Two-tier error semantics** (from procyclingstats): `ExpectedParsingError` for missing/cancelled races (silently logged), `UnexpectedParsingError` for structural changes (crashes, forces investigation).
4. **Settings dataclass** (from Codex draft): Centralized configuration instead of scattered module constants.
5. **Raw data archival**: Both JSON and HTML saved to `data/raw/{race_id}.json` and `data/raw/{race_id}.html`. Enables re-parsing without re-scraping if schema evolves.
6. **Rider dedup via RacerID**: Use the JSON API's `RacerID` field for exact-match deduplication. Fuzzy name matching deferred to Sprint 002.
7. **Per-category classification**: Finish types are properties of race+category pairs, not races alone. A P12 bunch sprint can coexist with a Cat 4 breakaway at the same event.

## Implementation

### Phase 1: Project Skeleton & Tooling (~10% of effort)

**Files:**
- `pyproject.toml` — Package definition, dependencies, ruff/mypy/pytest config
- `.gitignore` — Python template + `*.db`, `data/`
- `.pre-commit-config.yaml` — ruff format, ruff check hooks
- `raceanalyzer/__init__.py`, `raceanalyzer/__main__.py`
- `raceanalyzer/config.py` — Settings dataclass

**Tasks:**
- [ ] Initialize git repo with `.gitignore`
- [ ] Create `pyproject.toml` with all dependencies
- [ ] Set up ruff + pre-commit hooks
- [ ] Create package directory structure
- [ ] Implement `Settings` dataclass in `config.py`

```python
# raceanalyzer/config.py
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Settings:
    db_path: Path = Path("data/raceanalyzer.db")
    raw_data_dir: Path = Path("data/raw")
    base_url: str = "https://www.road-results.com"
    max_workers: int = 4
    min_request_delay: float = 0.5       # seconds between requests
    request_timeout: int = 30
    retry_count: int = 3
    retry_backoff_base: float = 2.0
    max_race_id: int = 15000
    gap_threshold: float = 3.0           # seconds (UCI standard)
    pnw_regions: tuple = ("WA", "OR", "ID", "BC")
```

### Phase 2: Database Schema & Engine (~15% of effort)

**Files:**
- `raceanalyzer/db/models.py` — 5 ORM models
- `raceanalyzer/db/engine.py` — Engine/session factory
- `tests/test_models.py` — Schema and constraint tests

**Tasks:**
- [ ] Implement all 5 SQLAlchemy models
- [ ] Implement engine/session factory with WAL mode
- [ ] Write model tests (create, query, constraint enforcement)

```python
# raceanalyzer/db/models.py
import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean,
    ForeignKey, UniqueConstraint, Index, Text, Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class FinishType(enum.Enum):
    BUNCH_SPRINT = "bunch_sprint"
    SMALL_GROUP_SPRINT = "small_group_sprint"
    BREAKAWAY = "breakaway"
    BREAKAWAY_SELECTIVE = "breakaway_selective"
    REDUCED_SPRINT = "reduced_sprint"
    GC_SELECTIVE = "gc_selective"
    MIXED = "mixed"
    UNKNOWN = "unknown"           # Missing time data


class Race(Base):
    """A race event on a specific date."""
    __tablename__ = "races"

    id = Column(Integer, primary_key=True)  # road-results.com raceID
    name = Column(String, nullable=False)
    date = Column(DateTime, nullable=True)
    location = Column(String, nullable=True)
    state_province = Column(String, nullable=True)  # WA, OR, ID, BC
    url = Column(String, nullable=True)

    results = relationship("Result", back_populates="race",
                           cascade="all, delete-orphan")
    classifications = relationship("RaceClassification", back_populates="race",
                                   cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_races_date", "date"),
        Index("ix_races_state", "state_province"),
    )


class Rider(Base):
    """A deduplicated rider identity."""
    __tablename__ = "riders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    road_results_id = Column(Integer, nullable=True, unique=True)
    license_number = Column(String, nullable=True)

    results = relationship("Result", back_populates="rider")

    __table_args__ = (
        Index("ix_riders_name", "name"),
        Index("ix_riders_rr_id", "road_results_id"),
    )


class Result(Base):
    """One rider's result in one race category."""
    __tablename__ = "results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=False)
    rider_id = Column(Integer, ForeignKey("riders.id"), nullable=True)

    # From JSON API (29 fields available, we store the most useful)
    place = Column(Integer, nullable=True)
    name = Column(String, nullable=False)       # Raw name from API
    team = Column(String, nullable=True)
    age = Column(Integer, nullable=True)
    city = Column(String, nullable=True)
    state_province = Column(String, nullable=True)
    license = Column(String, nullable=True)
    race_category_name = Column(String, nullable=True)
    race_time = Column(String, nullable=True)         # Raw time string
    race_time_seconds = Column(Float, nullable=True)   # Parsed to seconds
    field_size = Column(Integer, nullable=True)
    dnf = Column(Boolean, default=False)
    dq = Column(Boolean, default=False)
    dnp = Column(Boolean, default=False)
    points = Column(Float, nullable=True)
    carried_points = Column(Float, nullable=True)

    # Computed during classification
    gap_group_id = Column(Integer, nullable=True)
    gap_to_leader = Column(Float, nullable=True)

    race = relationship("Race", back_populates="results")
    rider = relationship("Rider", back_populates="results")

    __table_args__ = (
        Index("ix_results_race_cat", "race_id", "race_category_name"),
        Index("ix_results_rider", "rider_id"),
    )


class RaceClassification(Base):
    """Finish type classification for a race + category pair."""
    __tablename__ = "race_classifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=False)
    category = Column(String, nullable=False)
    finish_type = Column(SAEnum(FinishType), nullable=False)

    # Group-structure metrics (stored for debugging, tuning, and future ML)
    num_finishers = Column(Integer, nullable=True)
    num_groups = Column(Integer, nullable=True)
    largest_group_size = Column(Integer, nullable=True)
    largest_group_ratio = Column(Float, nullable=True)
    leader_group_size = Column(Integer, nullable=True)
    gap_to_second_group = Column(Float, nullable=True)
    cv_of_times = Column(Float, nullable=True)
    gap_threshold_used = Column(Float, nullable=True)  # For reproducibility

    race = relationship("Race", back_populates="classifications")

    __table_args__ = (
        UniqueConstraint("race_id", "category",
                         name="uq_race_category_classification"),
    )


class ScrapeLog(Base):
    """Tracks scraping progress for resumability."""
    __tablename__ = "scrape_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, nullable=False, unique=True)
    status = Column(String, nullable=False)  # success, not_found, error
    scraped_at = Column(DateTime, default=datetime.utcnow)
    error_message = Column(Text, nullable=True)
    result_count = Column(Integer, nullable=True)
```

```python
# raceanalyzer/db/engine.py
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from raceanalyzer.db.models import Base

DEFAULT_DB_PATH = Path("data/raceanalyzer.db")


def get_engine(db_path: Path = DEFAULT_DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", echo=False)

    # Enable WAL mode for better concurrent write handling
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine


def get_session(db_path: Path = DEFAULT_DB_PATH) -> Session:
    engine = get_engine(db_path)
    return sessionmaker(bind=engine)()


def init_db(db_path: Path = DEFAULT_DB_PATH):
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    return engine
```

### Phase 3: Scraper Implementation (~30% of effort)

**Files:**
- `raceanalyzer/scraper/errors.py` — Two-tier error hierarchy
- `raceanalyzer/scraper/client.py` — HTTP client with retry/rate-limit
- `raceanalyzer/scraper/parsers.py` — HTML + JSON parsers
- `raceanalyzer/scraper/pipeline.py` — Orchestrator: fetch → parse → persist → archive
- `raceanalyzer/utils/time_parsing.py` — RaceTime → seconds
- `tests/test_scraper.py`, `tests/test_time_parsing.py`

**Tasks:**
- [ ] Implement `ExpectedParsingError` / `UnexpectedParsingError` hierarchy
- [ ] Implement `RoadResultsClient` with shared session, retry, exponential backoff, rate limiting
- [ ] Implement `RacePageParser` (regex for name/date/location from HTML)
- [ ] Implement `RaceResultParser` (JSON decode, field validation)
- [ ] Implement `parse_race_time()` for all observed time formats
- [ ] Implement `ScrapeOrchestrator` with parallel fetching, rider dedup via RacerID, ScrapeLog tracking
- [ ] Implement raw JSON/HTML archival to `data/raw/`
- [ ] Write scraper tests with mocked HTTP and fixture responses

```python
# raceanalyzer/scraper/errors.py
class ExpectedParsingError(Exception):
    """Data unavailable for known reasons (cancelled race, no results).
    Silently handled during bulk scraping."""

class UnexpectedParsingError(Exception):
    """Structural change in API/HTML. Requires developer attention.
    NOT caught during bulk scraping — forces investigation."""

class RaceNotFoundError(ExpectedParsingError):
    """Race ID does not exist on road-results.com."""

class NoResultsError(ExpectedParsingError):
    """Race exists but has no posted results."""
```

```python
# raceanalyzer/scraper/client.py
import time
import logging
import requests
from raceanalyzer.config import Settings

logger = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "User-Agent": "RaceAnalyzer/0.1 (cycling analytics research; respectful scraping)",
    "Accept": "application/json, text/html",
}


class RoadResultsClient:
    """HTTP client with retry, exponential backoff, and rate limiting."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._session = requests.Session()
        self._session.headers.update(BROWSER_HEADERS)
        self._last_request_time = 0.0  # Instance-level, not class-level

    def _rate_limit(self):
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self._settings.min_request_delay:
            time.sleep(self._settings.min_request_delay - elapsed)
        self._last_request_time = time.monotonic()

    def _request_with_retry(self, url: str) -> requests.Response:
        for attempt in range(self._settings.retry_count):
            try:
                self._rate_limit()
                response = self._session.get(
                    url, timeout=self._settings.request_timeout
                )
                if response.status_code == 200:
                    return response
                if response.status_code == 404:
                    from raceanalyzer.scraper.errors import RaceNotFoundError
                    raise RaceNotFoundError(f"Race not found: {url}")
                # Retry on 5xx or rate limit
                if response.status_code >= 500 or response.status_code == 429:
                    wait = self._settings.retry_backoff_base ** attempt
                    logger.warning(f"HTTP {response.status_code}, retry in {wait}s")
                    time.sleep(wait)
                    continue
                response.raise_for_status()
            except requests.RequestException as e:
                if attempt == self._settings.retry_count - 1:
                    raise
                wait = self._settings.retry_backoff_base ** attempt
                logger.warning(f"Request error: {e}, retry in {wait}s")
                time.sleep(wait)
        raise ConnectionError(f"Failed after {self._settings.retry_count} retries: {url}")

    def fetch_race_page(self, race_id: int) -> str:
        """GET /race/{race_id} → HTML string."""
        url = f"{self._settings.base_url}/race/{race_id}"
        return self._request_with_retry(url).text

    def fetch_race_json(self, race_id: int) -> list[dict]:
        """GET /downloadrace.php?raceID={race_id}&json=1 → list of result dicts."""
        url = f"{self._settings.base_url}/downloadrace.php?raceID={race_id}&json=1"
        response = self._request_with_retry(url)
        return response.json()
```

```python
# raceanalyzer/utils/time_parsing.py
import re

TIME_PATTERN = re.compile(
    r"(?:(\d+):)?(?:(\d+):)?(\d+(?:\.\d+)?)"
)


def parse_race_time(time_str: str | None) -> float | None:
    """Parse a road-results.com RaceTime string to total seconds.

    Returns None for DNF, DQ, empty, or unparseable values.

    Examples:
        "1:23:45.67" → 5025.67
        "23:45.67"   → 1425.67
        "45.67"      → 45.67
        "DNF"        → None
    """
    if not time_str or not time_str.strip():
        return None

    time_str = time_str.strip()

    if any(s in time_str.upper() for s in ("DNF", "DQ", "DNS", "DNP", "OTL")):
        return None

    match = TIME_PATTERN.fullmatch(time_str)
    if not match:
        return None

    groups = match.groups()
    parts = [float(g) if g else 0.0 for g in groups]

    if groups[0] is not None and groups[1] is not None:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif groups[0] is not None:
        return parts[0] * 60 + parts[2]
    else:
        return parts[2]
```

### Phase 4: Finish Type Classification (~25% of effort)

**Files:**
- `raceanalyzer/classification/grouping.py` — Gap grouping algorithm
- `raceanalyzer/classification/finish_type.py` — Rule-based classifier
- `tests/test_gap_grouping.py`, `tests/test_finish_type.py`

**Tasks:**
- [ ] Implement `group_by_consecutive_gaps()` with configurable threshold
- [ ] Implement `classify_finish_type()` with the decision tree from research-findings.md
- [ ] Store classification result + all group metrics to `RaceClassification`
- [ ] Write tests covering all 8 `FinishType` variants
- [ ] Write edge case tests: no times, single rider, all DNF, empty results

```python
# raceanalyzer/classification/grouping.py
from dataclasses import dataclass


@dataclass
class RiderGroup:
    """A group of riders finishing together."""
    riders: list  # list of Result-like objects with race_time_seconds
    min_time: float
    max_time: float
    gap_to_next: float | None  # seconds to next group; None if last


def group_by_consecutive_gaps(
    results: list,
    gap_threshold: float = 3.0,
) -> list[RiderGroup]:
    """Sort results by finish time, split into groups where consecutive
    gap exceeds threshold.

    Implements the UCI chain rule: a stretched group with small inter-rider
    gaps stays together even if total spread exceeds the threshold.
    """
    timed = [r for r in results if r.race_time_seconds is not None]
    timed.sort(key=lambda r: r.race_time_seconds)

    if not timed:
        return []

    groups = []
    current_group = [timed[0]]

    for i in range(1, len(timed)):
        gap = timed[i].race_time_seconds - timed[i - 1].race_time_seconds
        if gap > gap_threshold:
            groups.append(current_group)
            current_group = [timed[i]]
        else:
            current_group.append(timed[i])

    groups.append(current_group)

    # Convert to RiderGroup objects with gap info
    rider_groups = []
    for idx, group in enumerate(groups):
        times = [r.race_time_seconds for r in group]
        gap_to_next = None
        if idx < len(groups) - 1:
            next_min = min(r.race_time_seconds for r in groups[idx + 1])
            gap_to_next = next_min - max(times)
        rider_groups.append(RiderGroup(
            riders=group,
            min_time=min(times),
            max_time=max(times),
            gap_to_next=gap_to_next,
        ))

    return rider_groups
```

```python
# raceanalyzer/classification/finish_type.py
from dataclasses import dataclass
from raceanalyzer.db.models import FinishType
from raceanalyzer.classification.grouping import RiderGroup
import statistics


@dataclass
class ClassificationResult:
    finish_type: FinishType
    confidence: float
    metrics: dict  # All computed metrics, stored for provenance


def classify_finish_type(
    groups: list[RiderGroup],
    total_finishers: int,
    gap_threshold_used: float = 3.0,
) -> ClassificationResult:
    """Apply rule-based decision tree to grouped results.

    Decision logic from research-findings.md:
    - BUNCH_SPRINT:        largest_group > 50% of field, gap < 30s
    - SMALL_GROUP_SPRINT:  leader group 2-10, gap to bunch > 30s
    - BREAKAWAY:           leader group ≤ 5, gap > 30s, main bunch > 40%
    - BREAKAWAY_SELECTIVE: leader group ≤ 5, gap > 30s, main bunch ≤ 40%
    - GC_SELECTIVE:        > 5 groups, largest < 30% of field
    - REDUCED_SPRINT:      leader group 6 to half of field
    - MIXED:               everything else
    - UNKNOWN:             no time data
    """
    if not groups or total_finishers == 0:
        return ClassificationResult(
            finish_type=FinishType.UNKNOWN,
            confidence=1.0,
            metrics={"reason": "no_time_data"},
        )

    # Compute group-structure metrics
    group_sizes = [len(g.riders) for g in groups]
    largest_group_size = max(group_sizes)
    largest_group_ratio = largest_group_size / total_finishers
    leader_group_size = len(groups[0].riders)
    gap_to_second = groups[0].gap_to_next if groups[0].gap_to_next else 0.0
    num_groups = len(groups)

    # CV of finish times
    all_times = []
    for g in groups:
        all_times.extend([r.race_time_seconds for r in g.riders])
    cv_of_times = 0.0
    if len(all_times) > 1 and statistics.mean(all_times) > 0:
        cv_of_times = statistics.stdev(all_times) / statistics.mean(all_times)

    metrics = {
        "num_finishers": total_finishers,
        "num_groups": num_groups,
        "largest_group_size": largest_group_size,
        "largest_group_ratio": round(largest_group_ratio, 4),
        "leader_group_size": leader_group_size,
        "gap_to_second_group": round(gap_to_second, 2),
        "cv_of_times": round(cv_of_times, 6),
        "gap_threshold_used": gap_threshold_used,
    }

    # Decision tree
    if largest_group_ratio > 0.5 and gap_to_second < 30:
        ft = FinishType.BUNCH_SPRINT
    elif leader_group_size <= 5 and gap_to_second > 30:
        if largest_group_ratio > 0.4:
            ft = FinishType.BREAKAWAY
        else:
            ft = FinishType.BREAKAWAY_SELECTIVE
    elif num_groups > 5 and largest_group_ratio < 0.3:
        ft = FinishType.GC_SELECTIVE
    elif leader_group_size > 5 and leader_group_size < total_finishers * 0.5:
        ft = FinishType.REDUCED_SPRINT
    elif leader_group_size >= 2 and leader_group_size <= 10 and gap_to_second > 30:
        ft = FinishType.SMALL_GROUP_SPRINT
    else:
        ft = FinishType.MIXED

    # Rough confidence based on how clearly it fits the rule
    confidence = 0.7  # Default for rule-based
    if largest_group_ratio > 0.8:
        confidence = 0.9  # Very clear bunch sprint
    if num_groups == 1:
        confidence = 0.95  # Everyone together

    return ClassificationResult(
        finish_type=ft,
        confidence=confidence,
        metrics=metrics,
    )
```

### Phase 5: CLI Integration (~10% of effort)

**Files:**
- `raceanalyzer/cli.py` — Click commands: init, scrape, classify
- `raceanalyzer/__main__.py` — Entry point

**Tasks:**
- [ ] Implement `init` command (create DB)
- [ ] Implement `scrape` command with `--race-id`, `--start/--end` args
- [ ] Implement `classify` command with `--race-id` and `--all` flags
- [ ] Add `--gap-threshold` argument to classify (default 3.0)

### Phase 6: Testing & Validation (~10% of effort)

**Files:**
- `tests/fixtures/` — 5+ saved JSON/HTML responses
- `tests/fixtures/labeled_races.json` — 20 hand-labeled PNW races
- All test files listed in package structure

**Tasks:**
- [ ] Save 5 real JSON API responses as test fixtures (sprint, breakaway, selective, no-times, edge case)
- [ ] Hand-label 20 PNW races for classifier validation
- [ ] Write integration test: full pipeline from fixture JSON to classified DB
- [ ] Verify classifier against 20 labeled races (target: ≥ 15/20 correct)
- [ ] Test edge cases: empty results, all-DNF, single rider, placement-only

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `pyproject.toml` | Create | Package definition, dependencies, tool config |
| `.gitignore` | Create | Python + SQLite + data/ exclusions |
| `.pre-commit-config.yaml` | Create | ruff format + check hooks |
| `raceanalyzer/__init__.py` | Create | Package marker |
| `raceanalyzer/__main__.py` | Create | CLI entry point |
| `raceanalyzer/cli.py` | Create | Click CLI commands |
| `raceanalyzer/config.py` | Create | Settings dataclass |
| `raceanalyzer/db/engine.py` | Create | SQLAlchemy engine with WAL mode |
| `raceanalyzer/db/models.py` | Create | 5 ORM models + FinishType enum |
| `raceanalyzer/scraper/client.py` | Create | HTTP client with retry/rate-limit |
| `raceanalyzer/scraper/parsers.py` | Create | HTML + JSON parsers |
| `raceanalyzer/scraper/pipeline.py` | Create | Scrape orchestrator |
| `raceanalyzer/scraper/errors.py` | Create | Two-tier error hierarchy |
| `raceanalyzer/classification/grouping.py` | Create | Gap grouping algorithm |
| `raceanalyzer/classification/finish_type.py` | Create | Rule-based classifier |
| `raceanalyzer/utils/time_parsing.py` | Create | Time string → seconds |
| `tests/conftest.py` | Create | Shared fixtures, in-memory DB |
| `tests/fixtures/` | Create | Saved API responses + labeled races |
| `tests/test_*.py` (6 files) | Create | Unit + integration tests |

## Definition of Done

- [ ] `pip install -e .` succeeds; `python -m raceanalyzer --help` shows commands
- [ ] `python -m raceanalyzer init` creates SQLite DB with all 5 tables
- [ ] `python -m raceanalyzer scrape --race-id <ID>` fetches JSON + HTML, stores Race + Results + Rider (via RacerID dedup), archives raw files
- [ ] `python -m raceanalyzer scrape --start 1 --end 100` runs parallel, skips already-scraped (via ScrapeLog), handles errors gracefully
- [ ] Interrupted scrape resumes without re-fetching or duplicate rows
- [ ] `python -m raceanalyzer classify --race-id <ID>` classifies each category in a race
- [ ] `python -m raceanalyzer classify --all` processes all unclassified race-category pairs
- [ ] Classifier matches ≥ 15/20 hand-labeled PNW races
- [ ] All tests pass: `pytest` with ≥ 85% coverage on `raceanalyzer/`
- [ ] `ruff check .` passes with zero errors
- [ ] Edge cases handled: DNF/DQ/DNP, missing times (→ UNKNOWN), empty categories, single-rider categories
- [ ] Raw JSON and HTML archived to `data/raw/`

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| road-results.com JSON API changes or gets rate-limited | Low | High | Archive raw JSON/HTML; conservative 4 workers + 0.5s delay; exponential backoff; descriptive User-Agent |
| HTML metadata regex breaks on structure change | Medium | Medium | Raw HTML archived for re-parsing; regex patterns isolated in `RacePageParser`; `UnexpectedParsingError` surfaces changes |
| Gap threshold (3s) doesn't work for amateur racing | Medium | Medium | Configurable via CLI arg; `gap_threshold_used` stored on each classification; can re-classify with different values |
| SQLite write contention during parallel scraping | Low | Low | WAL journal mode enabled; batch commits (one transaction per race); serialize writes if needed |
| Rule-based classifier has poor accuracy on amateur races | High | Medium | Store all group metrics on `race_classifications` for future ML training; hand-label 20 races for validation; upgrade path to HDBSCAN/ML in Sprint 003 |
| Scope creep into rider fuzzy matching | Medium | Medium | Sprint 001 uses RacerID exact-match only; fuzzy matching explicitly deferred to Sprint 002 |
| Time parsing fails on unexpected formats | Medium | Low | Comprehensive test suite; unparseable times → `race_time_seconds=NULL`; logged for investigation |

## Security Considerations

- **Respectful scraping**: Rate limiting (0.5s min delay), exponential backoff, descriptive User-Agent. No authentication required.
- **No secrets in code**: No API keys needed. DB path via Settings, not hardcoded.
- **SQL injection prevention**: Exclusive SQLAlchemy ORM usage (parameterized queries).
- **Data privacy**: All scraped data is publicly available on road-results.com. No PII beyond what the source publishes.
- **Dependency management**: Versions pinned in `pyproject.toml`. Run `pip-audit` before release.
- **Data directory excluded from git**: `.gitignore` excludes `data/`, `*.db`.

## Dependencies

### Python Packages (Runtime)
| Package | Version | Purpose |
|---------|---------|---------|
| `sqlalchemy` | >= 2.0 | ORM and database engine |
| `requests` | >= 2.31 | HTTP client |
| `requests-futures` | >= 1.0 | Async parallel HTTP fetching |
| `pandas` | >= 2.0 | Data manipulation |
| `click` | >= 8.0 | CLI framework |

### Python Packages (Dev)
| Package | Version | Purpose |
|---------|---------|---------|
| `pytest` | >= 7.0 | Test runner |
| `pytest-cov` | >= 4.0 | Coverage reporting |
| `responses` | >= 0.23 | HTTP mocking |
| `ruff` | >= 0.3 | Linting and formatting |
| `pre-commit` | >= 3.0 | Git hooks |

### External
- **road-results.com** — Primary data source (unauthenticated JSON API)
- **Python 3.11+** — Required for `|` union syntax, `tomllib`
- **SQLite 3** — Included with Python

## Open Questions

1. **Gap threshold tuning**: Default 3s (UCI standard). Store `gap_threshold_used` on each classification for reproducibility. Validate against hand-labeled sample; adjust if accuracy is below 75% at 3s.

2. **Race ID range**: Start with a targeted subset (e.g., 12000-13000) to validate the pipeline. Expand to full historical range after validation. Store all races (not just PNW) — non-PNW data useful for classification training.

3. **Rider identity across years**: Same rider may have different RacerIDs across years. Sprint 001 uses RacerID for exact-match only. Never auto-merge riders with different IDs. Log potential duplicates (same name, different ID) for Sprint 002 fuzzy matching review.

4. **Category normalization**: road-results.com uses inconsistent category names ("Men P/1/2", "Men Pro/1/2", "M P12"). Sprint 001 stores raw strings. Sprint 002 adds a category alias mapping table.

5. **Placement-only races**: Races with positions but no times cannot be gap-grouped. Classified as UNKNOWN. Track percentage — if >30% of PNW races lack times, consider a placement-based heuristic in a future sprint.

6. **Raw JSON archival**: Yes — save to `data/raw/{race_id}.json` and `data/raw/{race_id}.html`. ~50MB total storage. High optionality value for schema evolution.
