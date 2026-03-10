# Sprint 001: Data Pipeline Foundation

## Overview

Build the foundational data pipeline for RaceAnalyzer: a Python package that scrapes race results from road-results.com via its JSON API, stores them in a normalized SQLite database, and classifies finish types using time-gap analysis. This sprint establishes the project skeleton, database schema, scraper architecture, and rule-based finish type classifier that all future sprints build upon.

**Duration**: ~2 weeks
**Primary deliverable**: A working CLI that can scrape races by ID, persist results to SQLite, and output finish type classifications.

---

## Use Cases

1. **As a developer**, I can run `python -m raceanalyzer scrape --race-id 5000` to fetch a single race's results and metadata from road-results.com and store them in SQLite.
2. **As a developer**, I can run `python -m raceanalyzer scrape --range 1 13000` to bulk-scrape all historical races with async parallel fetching, rate limiting, and resume-on-interrupt.
3. **As a developer**, I can run `python -m raceanalyzer classify --race-id 5000` to see the finish type classification (bunch sprint, breakaway, selective, etc.) for each category in a race.
4. **As an analyst**, I can query the SQLite database to answer: "Show me all P12 results at Banana Belt with finish times and gap groups."
5. **As a developer**, I can run `pytest` and get passing tests against saved JSON fixtures, without hitting road-results.com.

---

## Architecture

```
raceanalyzer/
├── __init__.py
├── __main__.py              # CLI entry point
├── cli.py                   # Click/argparse CLI commands
├── config.py                # Settings, constants, rate limits
├── db/
│   ├── __init__.py
│   ├── engine.py            # SQLAlchemy engine/session factory
│   ├── models.py            # ORM models (races, results, riders, etc.)
│   └── queries.py           # Common query helpers
├── scraper/
│   ├── __init__.py
│   ├── base.py              # Base scraper class (session, retries, rate limiting)
│   ├── race.py              # RaceScraper: JSON API + HTML metadata
│   ├── errors.py            # ExpectedParsingError, UnexpectedParsingError
│   └── fields.py            # Field definitions and validation
├── classification/
│   ├── __init__.py
│   ├── gap_grouping.py      # Time-gap grouping algorithm
│   └── finish_type.py       # Rule-based finish type classifier
└── utils/
    ├── __init__.py
    └── time_parsing.py       # RaceTime string → seconds conversion

tests/
├── conftest.py              # Shared fixtures
├── fixtures/                # Saved JSON API responses
│   ├── race_5000.json
│   ├── race_5001.json
│   └── ...
├── test_scraper.py
├── test_models.py
├── test_gap_grouping.py
├── test_finish_type.py
└── test_time_parsing.py
```

### Key Design Decisions

- **Package structure**: `raceanalyzer/` as an installable Python package with `pyproject.toml`.
- **Class-per-entity scraper** (from procyclingstats): `RaceScraper` handles one race. A `BulkScraper` orchestrates parallel fetching.
- **Two-tier errors** (from procyclingstats): `ExpectedParsingError` for missing/cancelled races, `UnexpectedParsingError` for structural changes.
- **SQLAlchemy ORM with SQLite**: Zero-config for MVP. Schema designed for future PostgreSQL migration.
- **JSON API first, HTML supplement**: Core result data from `downloadrace.php?raceID={ID}&json=1`. Only race date, location, and event name from HTML.

---

## Implementation

### Phase 1: Project Skeleton & Database Schema

**Goal**: Installable package with database models and migration support.

#### Task 1.1: Initialize project structure

Create `pyproject.toml`, package directories, and development tooling.

**File**: `pyproject.toml`
```toml
[project]
name = "raceanalyzer"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "sqlalchemy>=2.0",
    "requests>=2.31",
    "requests-futures>=1.0",
    "pandas>=2.0",
    "click>=8.0",
    "rapidfuzz>=3.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov",
    "ruff",
]

[project.scripts]
raceanalyzer = "raceanalyzer.cli:main"
```

Also create:
- `.gitignore` (Python template + `*.db`, `data/`)
- `raceanalyzer/__init__.py`
- `raceanalyzer/__main__.py` → calls `cli.main()`
- `tests/conftest.py`

#### Task 1.2: Define database schema

**File**: `raceanalyzer/db/models.py`

```python
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean, ForeignKey,
    UniqueConstraint, Index, Text, Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


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
    UNKNOWN = "unknown"  # When time data is missing


class Race(Base):
    """A single race event (one day, one location)."""
    __tablename__ = "races"

    id = Column(Integer, primary_key=True)  # road-results.com race ID
    name = Column(String, nullable=False)
    date = Column(DateTime, nullable=True)
    location = Column(String, nullable=True)
    state_province = Column(String, nullable=True)  # WA, OR, ID, BC
    url = Column(String, nullable=True)

    results = relationship("Result", back_populates="race", cascade="all, delete-orphan")
    classifications = relationship("RaceClassification", back_populates="race", cascade="all, delete-orphan")

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
    )


class Result(Base):
    """One rider's result in one race category."""
    __tablename__ = "results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=False)
    rider_id = Column(Integer, ForeignKey("riders.id"), nullable=True)

    # From JSON API
    place = Column(Integer, nullable=True)
    name = Column(String, nullable=False)
    team = Column(String, nullable=True)
    age = Column(Integer, nullable=True)
    city = Column(String, nullable=True)
    state_province = Column(String, nullable=True)
    license = Column(String, nullable=True)
    race_category_name = Column(String, nullable=True)
    race_time = Column(String, nullable=True)        # Raw time string from API
    race_time_seconds = Column(Float, nullable=True)  # Parsed to seconds
    field_size = Column(Integer, nullable=True)
    dnf = Column(Boolean, default=False)
    dq = Column(Boolean, default=False)
    dnp = Column(Boolean, default=False)
    points = Column(Float, nullable=True)
    carried_points = Column(Float, nullable=True)

    # Computed
    gap_group_id = Column(Integer, nullable=True)     # Which gap group this rider belongs to
    gap_to_leader = Column(Float, nullable=True)      # Seconds behind race leader

    race = relationship("Race", back_populates="results")
    rider = relationship("Rider", back_populates="results")

    __table_args__ = (
        Index("ix_results_race_cat", "race_id", "race_category_name"),
        Index("ix_results_rider", "rider_id"),
    )


class RaceClassification(Base):
    """Finish type classification for a specific race + category combination."""
    __tablename__ = "race_classifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=False)
    category = Column(String, nullable=False)
    finish_type = Column(SAEnum(FinishType), nullable=False)

    # Classification features (stored for debugging/tuning)
    num_finishers = Column(Integer, nullable=True)
    num_groups = Column(Integer, nullable=True)
    largest_group_size = Column(Integer, nullable=True)
    largest_group_ratio = Column(Float, nullable=True)
    leader_group_size = Column(Integer, nullable=True)
    gap_to_second_group = Column(Float, nullable=True)
    cv_of_times = Column(Float, nullable=True)

    race = relationship("Race", back_populates="classifications")

    __table_args__ = (
        UniqueConstraint("race_id", "category", name="uq_race_category_classification"),
    )


class ScrapeLog(Base):
    """Tracks scraping progress for resumability."""
    __tablename__ = "scrape_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, nullable=False, unique=True)
    status = Column(String, nullable=False)  # "success", "not_found", "error"
    scraped_at = Column(DateTime, default=datetime.utcnow)
    error_message = Column(Text, nullable=True)
    result_count = Column(Integer, nullable=True)
```

#### Task 1.3: Database engine and session factory

**File**: `raceanalyzer/db/engine.py`

```python
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from raceanalyzer.db.models import Base

DEFAULT_DB_PATH = Path("data/raceanalyzer.db")


def get_engine(db_path: Path = DEFAULT_DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", echo=False)


def get_session(db_path: Path = DEFAULT_DB_PATH):
    engine = get_engine(db_path)
    return sessionmaker(bind=engine)()


def init_db(db_path: Path = DEFAULT_DB_PATH):
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    return engine
```

#### Task 1.4: Configuration constants

**File**: `raceanalyzer/config.py`

```python
# road-results.com endpoints
BASE_URL = "https://www.road-results.com"
JSON_API_URL = f"{BASE_URL}/downloadrace.php"
RACE_PAGE_URL = f"{BASE_URL}/race/"

# Scraping parameters
MAX_WORKERS = 4              # Conservative; road-results reference used 8
REQUEST_TIMEOUT = 30         # seconds
RETRY_COUNT = 3
RETRY_BACKOFF_BASE = 2       # Exponential backoff: 2^attempt seconds
MIN_REQUEST_DELAY = 0.5      # Minimum seconds between requests per worker
MAX_RACE_ID = 15000          # Upper bound for sequential ID iteration

# Gap grouping
DEFAULT_GAP_THRESHOLD = 3.0  # seconds (UCI 3-second rule)

# PNW state/province filter
PNW_REGIONS = {"WA", "OR", "ID", "BC"}
```

### Phase 2: Scraper Implementation

**Goal**: Fetch race results from road-results.com JSON API with error handling, rate limiting, and resumability.

#### Task 2.1: Error types

**File**: `raceanalyzer/scraper/errors.py`

```python
class ExpectedParsingError(Exception):
    """Data unavailable for known reasons (cancelled race, no results posted).
    Silently handled during bulk scraping."""
    pass


class UnexpectedParsingError(Exception):
    """Structural change in API/HTML response. Requires developer attention.
    NOT caught during bulk scraping — forces investigation."""
    pass


class RaceNotFoundError(ExpectedParsingError):
    """Race ID does not exist on road-results.com."""
    pass


class NoResultsError(ExpectedParsingError):
    """Race exists but has no posted results."""
    pass
```

#### Task 2.2: Time parsing utility

**File**: `raceanalyzer/utils/time_parsing.py`

```python
import re

# Patterns observed in road-results.com RaceTime field:
# "1:23:45.67", "23:45.67", "45.67", "DNF", "DQ", "", etc.
TIME_PATTERN = re.compile(
    r"(?:(\d+):)?(?:(\d+):)?(\d+(?:\.\d+)?)"
)


def parse_race_time(time_str: str | None) -> float | None:
    """Parse a road-results.com RaceTime string to total seconds.

    Returns None for DNF, DQ, empty strings, or unparseable values.

    Examples:
        "1:23:45.67" -> 5025.67
        "23:45.67"   -> 1425.67
        "45.67"      -> 45.67
        "DNF"        -> None
        ""           -> None
    """
    if not time_str or not time_str.strip():
        return None

    time_str = time_str.strip()

    # Check for non-finish status strings
    if any(s in time_str.upper() for s in ("DNF", "DQ", "DNS", "DNP", "OTL")):
        return None

    match = TIME_PATTERN.fullmatch(time_str)
    if not match:
        return None

    groups = match.groups()
    # Right-align: if only one group matched, it's seconds
    # Two groups: minutes:seconds; three groups: hours:minutes:seconds
    parts = [float(g) if g else 0.0 for g in groups]

    if groups[0] is not None and groups[1] is not None:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif groups[0] is not None:
        return parts[0] * 60 + parts[2]
    else:
        return parts[2]
```

#### Task 2.3: Base scraper with session management and retries

**File**: `raceanalyzer/scraper/base.py`

```python
import time
import logging
import requests
from raceanalyzer.config import (
    REQUEST_TIMEOUT, RETRY_COUNT, RETRY_BACKOFF_BASE, MIN_REQUEST_DELAY,
)
from raceanalyzer.scraper.errors import UnexpectedParsingError

logger = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "User-Agent": "RaceAnalyzer/0.1 (cycling analytics research; respectful scraping)",
    "Accept": "application/json, text/html",
}


class BaseScraper:
    """Shared HTTP session with retry logic and rate limiting."""

    _session: requests.Session | None = None
    _last_request_time: float = 0.0

    @classmethod
    def session(cls) -> requests.Session:
        if cls._session is None:
            cls._session = requests.Session()
            cls._session.headers.update(BROWSER_HEADERS)
        return cls._session

    @classmethod
    def _rate_limit(cls):
        elapsed = time.monotonic() - cls._last_request_time
        if elapsed < MIN_REQUEST_DELAY:
            time.sleep(MIN_REQUEST_DELAY - elapsed)
        cls._last_request_time = time.monotonic()

    @classmethod
    def fetch(cls, url: str) -> requests.Response:
        """Fetch URL with retries and exponential backoff."""
        for attempt in range(RETRY_COUNT):
            cls._rate_limit()
            try:
                response = cls.session().get(url, timeout=REQUEST_TIMEOUT)
                if response.status_code == 404:
                    return response
                if response.status_code == 200:
                    return response
                logger.warning(
                    "HTTP %d for %s (attempt %d/%d)",
                    response.status_code, url, attempt + 1, RETRY_COUNT,
                )
            except requests.RequestException as e:
                logger.warning(
                    "Request error for %s (attempt %d/%d): %s",
                    url, attempt + 1, RETRY_COUNT, e,
                )
            time.sleep(RETRY_BACKOFF_BASE ** attempt)
        raise UnexpectedParsingError(f"Failed after {RETRY_COUNT} retries: {url}")
```

#### Task 2.4: Race scraper (JSON API + HTML metadata)

**File**: `raceanalyzer/scraper/race.py`

```python
import re
import json
import logging
from raceanalyzer.config import JSON_API_URL, RACE_PAGE_URL
from raceanalyzer.scraper.base import BaseScraper
from raceanalyzer.scraper.errors import (
    RaceNotFoundError, NoResultsError, UnexpectedParsingError,
)
from raceanalyzer.utils.time_parsing import parse_race_time

logger = logging.getLogger(__name__)

METADATA_REGEX = re.compile(r'resultstitle" >(.*?)[\n\r]')
DATE_REGEX = re.compile(r'([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})')

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


class RaceScraper:
    """Scrapes a single race from road-results.com.

    Usage:
        scraper = RaceScraper(race_id=5000)
        race_data = scraper.fetch_all()
        # race_data = {"metadata": {...}, "results": [...]}
    """

    def __init__(self, race_id: int):
        self.race_id = race_id

    def fetch_json_results(self) -> list[dict]:
        """Fetch structured results from the JSON API endpoint.

        Returns list of result dicts with parsed time fields.
        Raises RaceNotFoundError or NoResultsError as appropriate.
        """
        url = f"{JSON_API_URL}?raceID={self.race_id}&json=1"
        response = BaseScraper.fetch(url)

        if response.status_code == 404:
            raise RaceNotFoundError(f"Race {self.race_id} not found")

        try:
            data = response.json()
        except json.JSONDecodeError:
            # Empty or invalid response often means no results
            if not response.text.strip() or response.text.strip() == "[]":
                raise NoResultsError(f"Race {self.race_id} has no results")
            raise UnexpectedParsingError(
                f"Race {self.race_id}: invalid JSON response"
            )

        if not data:
            raise NoResultsError(f"Race {self.race_id} has no results")

        # Parse time fields
        for row in data:
            raw_time = row.get("RaceTime", "")
            row["race_time_seconds"] = parse_race_time(raw_time)

        return data

    def fetch_metadata(self) -> dict:
        """Fetch race metadata (name, date, location) from HTML page.

        Returns dict with keys: name, date, location, state_province.
        """
        url = f"{RACE_PAGE_URL}{self.race_id}"
        response = BaseScraper.fetch(url)

        if response.status_code == 404:
            raise RaceNotFoundError(f"Race {self.race_id} not found")

        return self._parse_metadata(response.text)

    def _parse_metadata(self, html: str) -> dict:
        """Extract race name, date, location from HTML."""
        match = METADATA_REGEX.search(html)
        if not match:
            raise UnexpectedParsingError(
                f"Race {self.race_id}: could not find resultstitle in HTML"
            )

        raw = match.group(1)
        parts = raw.split("&bull;")
        name = parts[0].strip() if len(parts) > 0 else None
        date_str = parts[1].strip() if len(parts) > 1 else None
        location = parts[2].strip() if len(parts) > 2 else None

        parsed_date = None
        state_province = None
        if date_str:
            date_match = DATE_REGEX.search(date_str)
            if date_match:
                from datetime import datetime
                month = MONTH_MAP.get(date_match.group(1), 1)
                day = int(date_match.group(2))
                year = int(date_match.group(3))
                parsed_date = datetime(year, month, day)

        if location:
            # Location format is typically "City, ST" — extract state/province
            loc_parts = location.split(",")
            if len(loc_parts) >= 2:
                state_province = loc_parts[-1].strip().split()[0]

        return {
            "name": name,
            "date": parsed_date,
            "location": location,
            "state_province": state_province,
        }

    def fetch_all(self) -> dict:
        """Fetch both metadata and results for this race.

        Returns: {"metadata": {...}, "results": [...]}
        """
        metadata = self.fetch_metadata()
        results = self.fetch_json_results()
        return {"metadata": metadata, "results": results}
```

#### Task 2.5: Bulk scraper with async fetching and resume support

**File**: `raceanalyzer/scraper/bulk.py`

```python
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.orm import Session as SASession
from raceanalyzer.config import MAX_WORKERS
from raceanalyzer.db.models import Race, Result, Rider, ScrapeLog
from raceanalyzer.scraper.race import RaceScraper
from raceanalyzer.scraper.errors import ExpectedParsingError, UnexpectedParsingError
from raceanalyzer.utils.time_parsing import parse_race_time

logger = logging.getLogger(__name__)


def get_unscraped_ids(session: SASession, start_id: int, end_id: int) -> list[int]:
    """Return race IDs in range that haven't been scraped yet."""
    scraped = {
        row.race_id
        for row in session.query(ScrapeLog.race_id).filter(
            ScrapeLog.race_id.between(start_id, end_id)
        )
    }
    return [i for i in range(start_id, end_id + 1) if i not in scraped]


def scrape_single_race(race_id: int) -> dict:
    """Scrape one race, returning data dict or raising on failure."""
    scraper = RaceScraper(race_id)
    return scraper.fetch_all()


def store_race(session: SASession, race_id: int, data: dict) -> None:
    """Persist scraped race data to the database."""
    meta = data["metadata"]

    race = Race(
        id=race_id,
        name=meta["name"],
        date=meta["date"],
        location=meta["location"],
        state_province=meta["state_province"],
    )
    session.merge(race)

    for row in data["results"]:
        result = Result(
            race_id=race_id,
            place=_int_or_none(row.get("Place")),
            name=row.get("Name", ""),
            team=row.get("Team", None),
            age=_int_or_none(row.get("Age")),
            city=row.get("City", None),
            state_province=row.get("State", None),
            license=row.get("License", None),
            race_category_name=row.get("RaceCategoryName", None),
            race_time=row.get("RaceTime", None),
            race_time_seconds=row.get("race_time_seconds"),
            field_size=_int_or_none(row.get("FieldSize")),
            dnf="DNF" in str(row.get("Place", "")),
            dq="DQ" in str(row.get("Place", "")),
            dnp="DNP" in str(row.get("Place", "")),
            points=_float_or_none(row.get("Points")),
            carried_points=_float_or_none(row.get("CarriedPoints")),
        )
        session.add(result)

    session.add(ScrapeLog(
        race_id=race_id,
        status="success",
        scraped_at=datetime.utcnow(),
        result_count=len(data["results"]),
    ))


def scrape_range(
    session: SASession,
    start_id: int,
    end_id: int,
    max_workers: int = MAX_WORKERS,
) -> dict:
    """Scrape a range of race IDs with parallel fetching and resume support.

    Returns: {"success": int, "not_found": int, "error": int}
    """
    ids = get_unscraped_ids(session, start_id, end_id)
    logger.info("Scraping %d races (IDs %d-%d, %d already scraped)",
                len(ids), start_id, end_id, (end_id - start_id + 1) - len(ids))

    counts = {"success": 0, "not_found": 0, "error": 0}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_id = {
            executor.submit(scrape_single_race, rid): rid for rid in ids
        }
        for future in as_completed(future_to_id):
            race_id = future_to_id[future]
            try:
                data = future.result()
                store_race(session, race_id, data)
                session.commit()
                counts["success"] += 1
                logger.debug("Scraped race %d: %s", race_id, data["metadata"]["name"])
            except ExpectedParsingError:
                session.add(ScrapeLog(
                    race_id=race_id, status="not_found",
                    scraped_at=datetime.utcnow(),
                ))
                session.commit()
                counts["not_found"] += 1
            except (UnexpectedParsingError, Exception) as e:
                session.add(ScrapeLog(
                    race_id=race_id, status="error",
                    scraped_at=datetime.utcnow(),
                    error_message=str(e)[:500],
                ))
                session.commit()
                counts["error"] += 1
                logger.error("Error scraping race %d: %s", race_id, e)

    return counts


def _int_or_none(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _float_or_none(val) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
```

### Phase 3: Finish Type Classification

**Goal**: Group riders by time gaps and classify race finish type per category.

#### Task 3.1: Gap grouping algorithm

**File**: `raceanalyzer/classification/gap_grouping.py`

```python
from dataclasses import dataclass
from raceanalyzer.config import DEFAULT_GAP_THRESHOLD


@dataclass
class GapGroup:
    """A group of riders finishing within the gap threshold of each other."""
    group_id: int
    size: int
    first_time: float   # seconds, earliest finisher in group
    last_time: float    # seconds, latest finisher in group
    members: list[int]  # indices into the sorted results list


def compute_gap_groups(
    times_seconds: list[float],
    threshold: float = DEFAULT_GAP_THRESHOLD,
) -> list[GapGroup]:
    """Group finishers using consecutive gap threshold (chain rule).

    Implements the UCI-style grouping: riders are in the same group if the
    gap to the rider immediately ahead is <= threshold. This means a group
    can span many seconds total as long as no consecutive gap exceeds threshold.

    Args:
        times_seconds: Finish times in seconds, must be sorted ascending.
            None values should be filtered out before calling.
        threshold: Maximum gap in seconds between consecutive riders
            to remain in the same group. Default 3.0 (UCI standard).

    Returns:
        List of GapGroup objects, ordered by finish time.
    """
    if not times_seconds:
        return []

    groups: list[GapGroup] = []
    current_members = [0]
    current_start = times_seconds[0]

    for i in range(1, len(times_seconds)):
        gap = times_seconds[i] - times_seconds[i - 1]
        if gap > threshold:
            # Close current group
            groups.append(GapGroup(
                group_id=len(groups),
                size=len(current_members),
                first_time=current_start,
                last_time=times_seconds[i - 1],
                members=current_members,
            ))
            current_members = [i]
            current_start = times_seconds[i]
        else:
            current_members.append(i)

    # Close final group
    groups.append(GapGroup(
        group_id=len(groups),
        size=len(current_members),
        first_time=current_start,
        last_time=times_seconds[-1] if times_seconds else current_start,
        members=current_members,
    ))

    return groups
```

#### Task 3.2: Rule-based finish type classifier

**File**: `raceanalyzer/classification/finish_type.py`

```python
import statistics
from raceanalyzer.db.models import FinishType
from raceanalyzer.classification.gap_grouping import GapGroup


@dataclass
class ClassificationResult:
    finish_type: FinishType
    num_finishers: int
    num_groups: int
    largest_group_size: int
    largest_group_ratio: float
    leader_group_size: int
    gap_to_second_group: float | None
    cv_of_times: float | None


def classify_finish_type(
    times_seconds: list[float],
    groups: list[GapGroup],
    total_starters: int | None = None,
) -> ClassificationResult:
    """Classify the finish type of a race category from gap groups.

    Uses the rule-based decision tree from research-findings.md:
    - BUNCH_SPRINT: largest group > 50% of field, gap to 2nd group < 30s
    - BREAKAWAY: leader group <= 5, gap to 2nd group > 30s, main group > 40%
    - BREAKAWAY_SELECTIVE: breakaway + no large main group
    - GC_SELECTIVE: many groups, no dominant group (largest < 30%)
    - REDUCED_SPRINT: leader group 5-50% of field
    - MIXED: anything else

    Args:
        times_seconds: Sorted list of finish times (no Nones).
        groups: Output from compute_gap_groups().
        total_starters: Total field size including DNF/DNS.
            Falls back to len(times_seconds) if not provided.
    """
    num_finishers = len(times_seconds)
    total = total_starters or num_finishers

    if num_finishers < 3:
        return ClassificationResult(
            finish_type=FinishType.UNKNOWN,
            num_finishers=num_finishers,
            num_groups=len(groups),
            largest_group_size=groups[0].size if groups else 0,
            largest_group_ratio=1.0 if groups else 0.0,
            leader_group_size=groups[0].size if groups else 0,
            gap_to_second_group=None,
            cv_of_times=None,
        )

    # Compute features
    largest_group = max(groups, key=lambda g: g.size)
    largest_group_ratio = largest_group.size / total
    leader_group = groups[0]
    leader_group_size = leader_group.size

    gap_to_second = None
    if len(groups) >= 2:
        gap_to_second = groups[1].first_time - groups[0].last_time

    cv = None
    if len(times_seconds) >= 2:
        mean_t = statistics.mean(times_seconds)
        if mean_t > 0:
            cv = statistics.stdev(times_seconds) / mean_t

    # Decision tree
    if largest_group_ratio > 0.5 and (gap_to_second is None or gap_to_second < 30):
        finish_type = FinishType.BUNCH_SPRINT
    elif leader_group_size <= 5 and gap_to_second is not None and gap_to_second > 30:
        if largest_group_ratio > 0.4:
            finish_type = FinishType.BREAKAWAY
        else:
            finish_type = FinishType.BREAKAWAY_SELECTIVE
    elif len(groups) > 5 and largest_group_ratio < 0.3:
        finish_type = FinishType.GC_SELECTIVE
    elif leader_group_size > 5 and leader_group_size < total * 0.5:
        finish_type = FinishType.REDUCED_SPRINT
    else:
        finish_type = FinishType.MIXED

    return ClassificationResult(
        finish_type=finish_type,
        num_finishers=num_finishers,
        num_groups=len(groups),
        largest_group_size=largest_group.size,
        largest_group_ratio=largest_group_ratio,
        leader_group_size=leader_group_size,
        gap_to_second_group=gap_to_second,
        cv_of_times=cv,
    )
```

#### Task 3.3: Classification pipeline (ties scraper + classifier together)

**File**: `raceanalyzer/classification/__init__.py`

```python
from sqlalchemy.orm import Session as SASession
from raceanalyzer.db.models import Result, RaceClassification, FinishType
from raceanalyzer.classification.gap_grouping import compute_gap_groups
from raceanalyzer.classification.finish_type import classify_finish_type


def classify_race(session: SASession, race_id: int, gap_threshold: float = 3.0):
    """Classify finish types for all categories in a race.

    Reads results from the database, computes gap groups, classifies finish type,
    and stores classifications back to the database.
    """
    categories = (
        session.query(Result.race_category_name)
        .filter(Result.race_id == race_id)
        .distinct()
        .all()
    )

    for (category,) in categories:
        results = (
            session.query(Result)
            .filter(Result.race_id == race_id, Result.race_category_name == category)
            .order_by(Result.place)
            .all()
        )

        # Extract valid finish times
        timed_results = [
            (r, r.race_time_seconds)
            for r in results
            if r.race_time_seconds is not None and not r.dnf and not r.dq
        ]
        timed_results.sort(key=lambda x: x[1])

        times = [t for _, t in timed_results]
        total_starters = len(results)

        if not times:
            # No time data — classify as UNKNOWN
            session.merge(RaceClassification(
                race_id=race_id,
                category=category,
                finish_type=FinishType.UNKNOWN,
                num_finishers=0,
            ))
            continue

        groups = compute_gap_groups(times, threshold=gap_threshold)

        # Update gap_group_id on individual results
        for group in groups:
            for idx in group.members:
                result_obj = timed_results[idx][0]
                result_obj.gap_group_id = group.group_id
                result_obj.gap_to_leader = times[idx] - times[0]

        classification = classify_finish_type(times, groups, total_starters)

        session.merge(RaceClassification(
            race_id=race_id,
            category=category,
            finish_type=classification.finish_type,
            num_finishers=classification.num_finishers,
            num_groups=classification.num_groups,
            largest_group_size=classification.largest_group_size,
            largest_group_ratio=classification.largest_group_ratio,
            leader_group_size=classification.leader_group_size,
            gap_to_second_group=classification.gap_to_second_group,
            cv_of_times=classification.cv_of_times,
        ))

    session.commit()
```

### Phase 4: CLI & Integration Testing

**Goal**: Working CLI commands and pytest suite.

#### Task 4.1: CLI

**File**: `raceanalyzer/cli.py`

```python
import click
import logging
from raceanalyzer.db.engine import get_session, init_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


@click.group()
@click.option("--db", default="data/raceanalyzer.db", help="Path to SQLite database")
@click.pass_context
def main(ctx, db):
    """RaceAnalyzer: PNW bike race analysis tool."""
    from pathlib import Path
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = Path(db)


@main.command()
@click.pass_context
def init(ctx):
    """Initialize the database."""
    init_db(ctx.obj["db_path"])
    click.echo(f"Database initialized at {ctx.obj['db_path']}")


@main.command()
@click.option("--race-id", type=int, help="Single race ID to scrape")
@click.option("--start", type=int, help="Start of race ID range")
@click.option("--end", type=int, help="End of race ID range")
@click.option("--workers", type=int, default=4, help="Parallel workers")
@click.pass_context
def scrape(ctx, race_id, start, end, workers):
    """Scrape race results from road-results.com."""
    from raceanalyzer.scraper.bulk import scrape_range, scrape_single_race, store_race
    init_db(ctx.obj["db_path"])
    session = get_session(ctx.obj["db_path"])

    if race_id:
        from raceanalyzer.scraper.race import RaceScraper
        data = RaceScraper(race_id).fetch_all()
        store_race(session, race_id, data)
        session.commit()
        click.echo(f"Scraped race {race_id}: {data['metadata']['name']} "
                    f"({len(data['results'])} results)")
    elif start and end:
        counts = scrape_range(session, start, end, max_workers=workers)
        click.echo(f"Done: {counts['success']} scraped, "
                    f"{counts['not_found']} not found, {counts['error']} errors")
    else:
        click.echo("Provide --race-id or --start/--end range", err=True)


@main.command()
@click.option("--race-id", type=int, required=True, help="Race ID to classify")
@click.option("--gap-threshold", type=float, default=3.0, help="Gap threshold in seconds")
@click.pass_context
def classify(ctx, race_id, gap_threshold):
    """Classify finish types for a race."""
    from raceanalyzer.classification import classify_race
    from raceanalyzer.db.models import RaceClassification
    session = get_session(ctx.obj["db_path"])
    classify_race(session, race_id, gap_threshold)

    classifications = (
        session.query(RaceClassification)
        .filter(RaceClassification.race_id == race_id)
        .all()
    )
    for c in classifications:
        click.echo(f"  {c.category}: {c.finish_type.value} "
                    f"({c.num_finishers} finishers, {c.num_groups} groups)")
```

#### Task 4.2: Test fixtures and test suite

**File**: `tests/conftest.py`

```python
import json
import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from raceanalyzer.db.models import Base

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def db_session():
    """In-memory SQLite session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def sample_json_response():
    """Load a saved JSON API response fixture."""
    fixture_path = FIXTURES_DIR / "race_sample.json"
    if fixture_path.exists():
        return json.loads(fixture_path.read_text())
    # Fallback: minimal synthetic fixture
    return [
        {"Place": "1", "Name": "Rider A", "RaceTime": "2:30:00.00",
         "RaceCategoryName": "Pro/1/2", "FieldSize": "40", "Team": "Team X"},
        {"Place": "2", "Name": "Rider B", "RaceTime": "2:30:01.50",
         "RaceCategoryName": "Pro/1/2", "FieldSize": "40", "Team": "Team Y"},
        {"Place": "3", "Name": "Rider C", "RaceTime": "2:30:02.00",
         "RaceCategoryName": "Pro/1/2", "FieldSize": "40", "Team": "Team Z"},
        # ... gap ...
        {"Place": "10", "Name": "Rider J", "RaceTime": "2:30:02.80",
         "RaceCategoryName": "Pro/1/2", "FieldSize": "40", "Team": ""},
    ]
```

Key test cases to implement in `tests/`:

- **`test_time_parsing.py`**: All time formats (H:M:S, M:S, S), DNF/DQ strings, edge cases (empty, None)
- **`test_gap_grouping.py`**: Bunch sprint (all within 3s), breakaway (gap > 30s), selective (many groups), single rider, empty list
- **`test_finish_type.py`**: Each `FinishType` variant with synthetic time data matching the decision tree
- **`test_models.py`**: ORM round-trip (create Race + Results, query back, verify relationships)
- **`test_scraper.py`**: Mock HTTP responses, verify parsing of JSON API response and HTML metadata extraction

---

## Files Summary

| File | Purpose |
|------|---------|
| `pyproject.toml` | Package definition, dependencies, scripts |
| `.gitignore` | Ignore patterns for Python, SQLite, data/ |
| `raceanalyzer/__init__.py` | Package marker |
| `raceanalyzer/__main__.py` | `python -m raceanalyzer` entry point |
| `raceanalyzer/cli.py` | Click CLI: `init`, `scrape`, `classify` commands |
| `raceanalyzer/config.py` | URLs, rate limits, gap threshold, PNW regions |
| `raceanalyzer/db/__init__.py` | Package marker |
| `raceanalyzer/db/engine.py` | SQLAlchemy engine/session factory |
| `raceanalyzer/db/models.py` | ORM models: Race, Rider, Result, RaceClassification, ScrapeLog |
| `raceanalyzer/db/queries.py` | Common query helpers (future) |
| `raceanalyzer/scraper/__init__.py` | Package marker |
| `raceanalyzer/scraper/base.py` | BaseScraper: shared session, retries, rate limiting |
| `raceanalyzer/scraper/race.py` | RaceScraper: JSON API + HTML metadata |
| `raceanalyzer/scraper/bulk.py` | Bulk scraper: parallel fetching, resume, persistence |
| `raceanalyzer/scraper/errors.py` | ExpectedParsingError, UnexpectedParsingError hierarchy |
| `raceanalyzer/classification/__init__.py` | classify_race() pipeline function |
| `raceanalyzer/classification/gap_grouping.py` | Consecutive gap threshold grouping |
| `raceanalyzer/classification/finish_type.py` | Rule-based finish type classifier |
| `raceanalyzer/utils/__init__.py` | Package marker |
| `raceanalyzer/utils/time_parsing.py` | RaceTime string → seconds parser |
| `tests/conftest.py` | Shared fixtures: in-memory DB, sample JSON |
| `tests/fixtures/` | Saved JSON API responses for offline testing |
| `tests/test_time_parsing.py` | Time parsing unit tests |
| `tests/test_gap_grouping.py` | Gap grouping unit tests |
| `tests/test_finish_type.py` | Finish type classification tests |
| `tests/test_models.py` | ORM model tests |
| `tests/test_scraper.py` | Scraper tests with mocked HTTP |

---

## Definition of Done

1. **Project installs cleanly**: `pip install -e .` succeeds, `raceanalyzer --help` shows CLI commands
2. **Database initializes**: `raceanalyzer init` creates SQLite DB with all 5 tables
3. **Single race scrape works**: `raceanalyzer scrape --race-id <ID>` fetches JSON + HTML, stores Race + Results
4. **Bulk scrape works**: `raceanalyzer scrape --start 1 --end 100` runs parallel, skips already-scraped, handles errors gracefully
5. **Resume works**: Interrupted bulk scrape picks up where it left off via ScrapeLog
6. **Finish type classification works**: `raceanalyzer classify --race-id <ID>` produces correct classifications for each category
7. **Classification matches hand-labeled samples**: Correctly classifies at least 15/20 hand-labeled PNW races
8. **All tests pass**: `pytest` passes with ≥90% coverage on classification and time parsing modules
9. **Rate limiting is respectful**: Scraper enforces minimum delay between requests, exponential backoff on errors
10. **Edge cases handled**: DNF/DQ/DNP results, missing times (→ UNKNOWN classification), empty categories, single-rider categories

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| road-results.com JSON API changes or gets rate-limited | Low | High | Store raw JSON responses in fixtures/; implement backoff; use conservative worker count (4) |
| HTML metadata format changes | Medium | Medium | Regex-based parsing is fragile; store raw HTML alongside parsed data; monitor for UnexpectedParsingError |
| Gap threshold (3s) doesn't work for amateur racing | Medium | Medium | Make threshold configurable; test with 2s, 3s, 4s on hand-labeled sample; can switch to HDBSCAN in future sprint |
| Sequential race IDs have gaps or non-PNW races | Low | Low | ScrapeLog tracks 404s; PNW filtering happens at query time, not scrape time |
| Scope creep into rider identity resolution | Medium | Medium | Sprint 001 stores raw names only; defer fuzzy matching to Sprint 002 |
| Schema needs changes for future sprints | Medium | Low | SQLAlchemy + SQLite makes migrations simple; schema designed with nullable FK to riders for deferred linking |

---

## Security Considerations

- **No secrets in code**: No API keys required (road-results.com JSON API is unauthenticated)
- **User-Agent transparency**: Custom UA string identifies the tool and its purpose
- **Rate limiting enforced**: `MIN_REQUEST_DELAY` prevents overwhelming the server; exponential backoff on errors
- **No user input to SQL**: All database operations use SQLAlchemy ORM (parameterized queries), preventing SQL injection
- **Data directory excluded from git**: `.gitignore` excludes `data/`, `*.db` to prevent accidental commits of scraped data
- **No PII concerns for MVP**: Race results are publicly available on road-results.com; no private data is scraped

---

## Dependencies

### Python packages (runtime)
- `sqlalchemy>=2.0` — ORM and database engine
- `requests>=2.31` — HTTP client
- `requests-futures>=1.0` — Async parallel HTTP (ThreadPoolExecutor wrapper)
- `pandas>=2.0` — Tabular data manipulation (used in queries, classification analysis)
- `click>=8.0` — CLI framework
- `rapidfuzz>=3.0` — Fuzzy string matching (installed now, used in Sprint 002)

### Python packages (dev)
- `pytest>=7.0` — Test runner
- `pytest-cov` — Coverage reporting
- `ruff` — Linting and formatting

### External services
- `road-results.com` — Primary data source (no authentication required)

### System requirements
- Python 3.11+
- SQLite 3 (included with Python)

---

## Open Questions

1. **Gap threshold tuning**: Should we start with 3s (UCI pro standard) or 4s (adjusted for amateur speeds ~35-45 km/h)? The intent doc suggests testing 2-4s. **Recommendation**: Default to 3s but make it a CLI argument; validate against hand-labeled sample.

2. **Race ID range**: The reference repo used `max_id=13000`. Current max is likely higher (the site has been active since the reference was written). **Recommendation**: Start with a small known range (e.g., recent PNW races), expand later. Config uses 15000 as upper bound.

3. **Rider deduplication timing**: The schema includes a `riders` table but Sprint 001 doesn't populate `rider_id` on Results (only stores raw `name`). Should we defer entirely or do basic exact-match dedup? **Recommendation**: Defer to Sprint 002. Store `road_results_id` (from JSON `RacerID` field) when available — this gives us exact matches for free.

4. **PNW filtering strategy**: Scrape everything and filter at query time, or skip non-PNW races during scrape? **Recommendation**: Scrape all (we need the data for ratings anyway — PNW riders race nationally), filter in queries using `state_province`.

5. **Git repo initialization**: Should this sprint include `git init`, pre-commit hooks, CI setup? **Recommendation**: Yes — `git init` + `.gitignore` + basic `ruff` pre-commit at minimum. Defer CI (no hosting target yet).

6. **Handling races with placement-only data (no times)**: These races can't be gap-grouped. **Recommendation**: Classify as `UNKNOWN` and track the percentage. If >30% of PNW races lack times, we'll need a placement-based classifier in a future sprint.

7. **Should we save raw JSON responses to disk?** This enables re-parsing without re-scraping if the schema evolves. **Recommendation**: Yes — save to `data/raw/{race_id}.json`. Low storage cost (~1-5KB per race × 15K races = ~50MB), high optionality value.
