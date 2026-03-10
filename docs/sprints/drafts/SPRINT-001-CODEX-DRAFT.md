# Sprint 001 Draft: Data Pipeline Foundation & Finish Classification

*Codex Draft — Independent perspective for synthesis review*

## Overview

Sprint 001 must solve two problems simultaneously: building a reliable data acquisition pipeline from road-results.com, and establishing an extensible architecture that can absorb five more pipeline stages (classification, course profiling, rating, prediction, UI) without requiring structural rewrites. The Gemini draft treats these as a linear sequence (scrape, store, classify), but this draft argues the architecture question is actually the harder problem and should drive every decision — from package layout to schema design to how we handle missing data.

The key insight from the reference projects is that the scraper, the database, and the classifier are not independent modules wired together at the end. They form a feedback loop: the classifier's needs (time gaps, group structure, field composition) should dictate what the scraper extracts and how the schema indexes it. Rather than building a generic three-table schema and hoping it serves downstream needs, this draft proposes a **domain-event-oriented schema** with seven tables from day one — designed around the specific queries that seed.md's user questions will eventually require. The upfront cost is modest (SQLAlchemy models are cheap to define) and the payoff is avoiding a painful migration in Sprint 002 or 003.

This sprint also takes a stronger position on **project tooling and developer experience** than the Gemini draft. A greenfield project without linting, type checking, or CI will accumulate technical debt from the first commit. Since the intent document asks whether project tooling should be included, this draft says yes — pyproject.toml, ruff, mypy, pytest, and pre-commit hooks are Sprint 001 scope. The cost is roughly 2 hours of setup; the cost of retrofitting is much higher.

## Use Cases

### UC-1: Bulk Historical Scrape
**Actor**: Developer/Operator
**Flow**: Operator runs a CLI command specifying a race ID range (e.g., `python -m raceanalyzer scrape --start 1 --end 13000 --concurrency 4`). The scraper fetches race HTML pages in batches, extracts metadata via regex, fetches JSON results in parallel, deduplicates riders via fuzzy matching, and persists everything to SQLite. A `scrape_log` table tracks progress so interrupted runs resume without re-fetching.
**Acceptance**: 100 races scraped and stored in under 5 minutes with zero data loss on interruption.

### UC-2: Incremental Scrape
**Actor**: Developer/Operator
**Flow**: Operator runs `python -m raceanalyzer scrape --since 2025-01-01`. The scraper checks the `scrape_log` for the highest previously-scraped race ID, fetches only newer IDs, and appends to the existing database.
**Acceptance**: Running the command twice produces no duplicate rows.

### UC-3: Classify Finish Types for a Race Edition
**Actor**: Developer/Analyst
**Flow**: Operator runs `python -m raceanalyzer classify --race-id 12345` or `--all`. For each race-category combination with time data, the classifier groups riders by consecutive time gaps, computes group-structure metrics, applies the rule-based decision tree, and writes a `RaceClassification` record.
**Acceptance**: Classifications for 20 hand-verified races match expected labels with >= 80% agreement.

### UC-4: Query Historical Finish Patterns
**Actor**: Future analyst (enabled, not fully built this sprint)
**Flow**: A Python function `get_finish_history(race_name, category)` returns a DataFrame of finish type classifications across all editions of a named race for a given category.
**Acceptance**: `get_finish_history("Banana Belt", "Men Pro/1/2")` returns rows spanning multiple years with finish_type populated.

## Architecture

### Package Layout

```
raceanalyzer/
    __init__.py
    __main__.py              # CLI entry point (click or argparse)
    config.py                # Settings: DB path, concurrency, gap threshold
    db/
        __init__.py
        engine.py            # Engine/session factory, migration bootstrap
        models.py            # All SQLAlchemy ORM models
    scraper/
        __init__.py
        client.py            # HTTP client with retry, rate limit, session mgmt
        parsers.py           # RacePageParser, RaceResultParser (class-per-entity)
        pipeline.py          # Orchestrator: batch fetch -> parse -> persist
        errors.py            # ExpectedScrapeError, UnexpectedScrapeError
    classification/
        __init__.py
        grouping.py          # Time-gap grouping algorithms
        rules.py             # Rule-based finish type classifier
        types.py             # FinishType enum
    utils/
        __init__.py
        fuzzy.py             # Rider name deduplication with rapidfuzz
        time_parse.py        # Parse RaceTime strings to float seconds
scripts/
    seed_db.py               # One-time DB creation / schema init
tests/
    conftest.py              # Shared fixtures, in-memory DB session
    fixtures/
        race_sprint.json     # Known bunch sprint (e.g., Seward Park Crit)
        race_breakaway.json  # Known breakaway (e.g., Banana Belt RR stage)
        race_selective.json  # Known selective finish (e.g., Mt. Tabor HC)
        race_no_times.json   # Placement-only race (no time data)
        race_html_meta.html  # Sample HTML for metadata extraction
    test_client.py
    test_parsers.py
    test_pipeline.py
    test_grouping.py
    test_rules.py
    test_fuzzy.py
    test_models.py
```

### Data Flow

```
                                road-results.com
                                      |
                    +-----------------+-----------------+
                    |                                   |
              HTML Race Page                    JSON API Endpoint
           (name, date, loc)              (29 fields per result)
                    |                                   |
                    v                                   v
           +----------------+                  +-----------------+
           | RacePageParser |                  | RaceResultParser|
           | (regex-based)  |                  | (JSON decode)   |
           +-------+--------+                  +--------+--------+
                   |                                    |
                   +------ parsed dicts -------+--------+
                                               |
                                               v
                                    +--------------------+
                                    |  ScrapeOrchestrator |
                                    |  (pipeline.py)      |
                                    |  - dedup riders     |
                                    |  - validate fields  |
                                    |  - batch upsert     |
                                    +--------+-----------+
                                             |
                                             v
                              +------------------------------+
                              |          SQLite DB            |
                              |  races | categories | riders  |
                              |  results | scrape_log         |
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
                              +------------------------------+
                                             |
                                             v
                              +------------------------------+
                              |   race_classifications table  |
                              |  (per race+category record)   |
                              +------------------------------+
```

### Database Schema (7 Tables)

This schema differs from the Gemini draft's 3-table design in three key ways:
1. **Categories are a first-class entity** (not just a string column on results) — because finish type classification happens per-category, and future queries always filter by category.
2. **Race classifications are separate from races** — because a single race event has multiple categories, each with its own finish type. Putting `finish_type` on the `races` table (as Gemini proposes) conflates the race event with the per-category outcome.
3. **A scrape_log table** tracks ingestion state — essential for resumable scraping and data provenance.

```python
# raceanalyzer/db/models.py

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean,
    ForeignKey, UniqueConstraint, Index, Enum, Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class FinishType(PyEnum):
    BUNCH_SPRINT = "bunch_sprint"
    SMALL_GROUP_SPRINT = "small_group_sprint"
    BREAKAWAY = "breakaway"
    BREAKAWAY_SELECTIVE = "breakaway_selective"
    GC_SELECTIVE = "gc_selective"
    REDUCED_SPRINT = "reduced_sprint"
    MIXED = "mixed"
    UNCLASSIFIABLE = "unclassifiable"  # no time data


class Race(Base):
    """A race event on a specific date (may contain multiple categories)."""
    __tablename__ = "races"

    id = Column(Integer, primary_key=True, doc="road-results.com raceID")
    name = Column(String(256), nullable=False, index=True)
    date = Column(DateTime, nullable=True, index=True)
    location = Column(String(256), nullable=True)
    state_province = Column(
        String(4), nullable=True, index=True,
        doc="WA, OR, ID, BC — for PNW filtering"
    )
    json_url = Column(String(512), nullable=True)
    raw_html = Column(Text, nullable=True, doc="Archived HTML for re-parsing")

    results = relationship("Result", back_populates="race", cascade="all, delete-orphan")
    classifications = relationship(
        "RaceClassification", back_populates="race", cascade="all, delete-orphan"
    )


class Category(Base):
    """A racing category (e.g., Men Pro/1/2, Women 3/4, Masters 40+)."""
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False, unique=True, index=True)
    # Normalized fields for structured queries
    gender = Column(String(16), nullable=True)       # men, women, open
    ability_level = Column(String(16), nullable=True) # pro12, cat3, cat4, cat5
    age_group = Column(String(32), nullable=True)     # open, 40+, 50+, junior


class Rider(Base):
    """A deduplicated rider identity."""
    __tablename__ = "riders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False, index=True)
    road_results_id = Column(
        Integer, nullable=True, unique=True, index=True,
        doc="RacerID from JSON API, if available"
    )
    license_number = Column(String(32), nullable=True)

    results = relationship("Result", back_populates="rider")


class Result(Base):
    """A single rider's result in a specific race + category."""
    __tablename__ = "results"
    __table_args__ = (
        UniqueConstraint("race_id", "rider_id", "category_id", name="uq_result"),
        Index("ix_results_race_cat", "race_id", "category_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=False)
    rider_id = Column(Integer, ForeignKey("riders.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)

    place = Column(Integer, nullable=True, doc="Finishing position; NULL if DNF/DQ")
    time_seconds = Column(Float, nullable=True, doc="Finish time in seconds from winner")
    dnf = Column(Boolean, default=False)
    dq = Column(Boolean, default=False)
    dnp = Column(Boolean, default=False, doc="Did Not Place / DNS")
    team_name = Column(String(256), nullable=True)
    age = Column(Integer, nullable=True)
    field_size = Column(Integer, nullable=True)
    points = Column(Float, nullable=True)
    license_number = Column(String(32), nullable=True)

    race = relationship("Race", back_populates="results")
    rider = relationship("Rider", back_populates="results")
    category = relationship("Category")


class RaceClassification(Base):
    """Finish type classification for a specific race + category combination."""
    __tablename__ = "race_classifications"
    __table_args__ = (
        UniqueConstraint("race_id", "category_id", name="uq_classification"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)

    finish_type = Column(Enum(FinishType), nullable=False)
    confidence = Column(Float, nullable=True, doc="0.0-1.0 classifier confidence")

    # Group-structure metrics (stored for debugging and future ML training)
    num_finishers = Column(Integer, nullable=True)
    num_groups = Column(Integer, nullable=True)
    largest_group_size = Column(Integer, nullable=True)
    largest_group_ratio = Column(Float, nullable=True)
    leader_group_size = Column(Integer, nullable=True)
    gap_to_second_group = Column(Float, nullable=True, doc="Seconds")
    cv_of_times = Column(Float, nullable=True, doc="Coefficient of variation")

    classified_at = Column(DateTime, default=datetime.utcnow)
    gap_threshold_used = Column(Float, nullable=True, doc="Seconds; for reproducibility")

    race = relationship("Race", back_populates="classifications")
    category = relationship("Category")


class ScrapeLog(Base):
    """Tracks scraping state for resumability and data provenance."""
    __tablename__ = "scrape_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, nullable=False, index=True)
    status = Column(
        String(32), nullable=False,
        doc="success, not_found, error, rate_limited"
    )
    http_status_code = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    results_count = Column(Integer, nullable=True, doc="Number of result rows ingested")
```

### Key Schema Differences from Gemini Draft

| Aspect | Gemini Draft | This Draft | Rationale |
|--------|-------------|------------|-----------|
| Classification granularity | `finish_type` on `races` table | Separate `race_classifications` table, per race+category | A race's P12 field may sprint while Masters 50+ has a breakaway. Classification is inherently per-category. |
| Category modeling | String column on `results` | First-class `categories` table with structured fields | Enables queries like "all Women Cat 3 results" without string parsing |
| Scrape tracking | Not included | `scrape_log` table | Essential for resumable scraping, debugging failures, and knowing data provenance |
| Raw HTML archival | Not included | `raw_html` column on `races` | Allows re-parsing if regex patterns change; cheap storage for critical provenance |
| Classification metrics | Not stored | Stored on `race_classifications` | Group metrics become training features when we move to ML classification in Sprint 003+ |
| Rider identity | Name-only, autoincrement PK | `road_results_id` + `license_number` for cross-referencing | Enables joining against road-results.com Race Predictor data in future sprints |
| DNF/DQ handling | Not explicit | Separate boolean columns | Critical for accurate field size computation and classification |

## Implementation

### Phase 1: Project Skeleton & Tooling (10% of effort)

| Task | Description | Output |
|------|-------------|--------|
| 1.1 | Initialize git repo, `.gitignore`, `CLAUDE.md` | Repo with initial commit |
| 1.2 | Create `pyproject.toml` with all dependencies and tool config (ruff, mypy, pytest) | Build configuration |
| 1.3 | Set up pre-commit hooks: ruff format, ruff check, mypy | `.pre-commit-config.yaml` |
| 1.4 | Create package directory structure per Architecture section | Empty `__init__.py` files |
| 1.5 | Create `raceanalyzer/config.py` with `Settings` dataclass | Centralized configuration |

**Key function signatures:**
```python
# raceanalyzer/config.py
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Settings:
    db_path: Path = Path("data/race_analyzer.db")
    base_url: str = "https://www.road-results.com"
    max_workers: int = 4
    rate_limit_delay: float = 0.5  # seconds between batches
    gap_threshold_seconds: float = 3.0
    fuzzy_match_threshold: int = 90  # rapidfuzz score
    retry_attempts: int = 3
    retry_backoff_base: float = 2.0
```

### Phase 2: Database Layer (15% of effort)

| Task | Description | Output |
|------|-------------|--------|
| 2.1 | Implement all 7 SQLAlchemy models in `db/models.py` | ORM models |
| 2.2 | Implement `db/engine.py`: `get_engine()`, `get_session()`, `init_db()` | Session factory |
| 2.3 | Write `test_models.py`: schema creation, basic CRUD, constraint enforcement | Passing tests |

**Key function signatures:**
```python
# raceanalyzer/db/engine.py
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from raceanalyzer.config import Settings
from raceanalyzer.db.models import Base

def get_engine(settings: Settings | None = None) -> Engine:
    """Create SQLAlchemy engine from settings. Defaults to SQLite."""
    ...

def get_session(engine: Engine) -> Session:
    """Create a new session bound to the given engine."""
    ...

def init_db(engine: Engine) -> None:
    """Create all tables. Idempotent."""
    Base.metadata.create_all(engine)
```

### Phase 3: Scraper — HTTP Client & Parsers (30% of effort)

| Task | Description | Output |
|------|-------------|--------|
| 3.1 | Implement `scraper/errors.py` with two-tier error hierarchy | Error classes |
| 3.2 | Implement `scraper/client.py`: shared session, retry with exponential backoff, rate limiting | HTTP client |
| 3.3 | Implement `scraper/parsers.py`: `RacePageParser` (HTML->metadata), `RaceResultParser` (JSON->dicts) | Parser classes |
| 3.4 | Implement `utils/time_parse.py`: parse `RaceTime` strings (e.g., "1:23:45.67") to float seconds | Time parser |
| 3.5 | Implement `utils/fuzzy.py`: `find_or_create_rider(session, name, road_results_id)` with rapidfuzz dedup | Fuzzy matching |
| 3.6 | Write tests for client (mocked HTTP), parsers (fixture JSON/HTML), time parsing, fuzzy matching | Passing tests |

**Key function signatures:**
```python
# raceanalyzer/scraper/errors.py
class ExpectedScrapeError(Exception):
    """Race doesn't exist, was cancelled, or has no results. Silently logged."""

class UnexpectedScrapeError(Exception):
    """HTML structure changed or API returned unexpected format. Propagates."""

# raceanalyzer/scraper/client.py
class RoadResultsClient:
    """HTTP client with shared session, retry, and rate limiting."""

    def __init__(self, settings: Settings):
        self._session: requests.Session
        self._settings: Settings

    def fetch_race_page(self, race_id: int) -> str:
        """GET /race/{race_id} -> HTML string. Raises on non-200 after retries."""

    def fetch_race_json(self, race_id: int) -> list[dict]:
        """GET /downloadrace.php?raceID={race_id}&json=1 -> list of result dicts."""

    async def fetch_batch(
        self, race_ids: list[int], callback: Callable[[int, dict], None]
    ) -> dict[int, str]:
        """Fetch multiple race pages concurrently with FuturesSession."""

# raceanalyzer/scraper/parsers.py
class RacePageParser:
    """Extracts metadata from a road-results.com race HTML page."""

    def __init__(self, race_id: int, html: str):
        self._html = html
        self.race_id = race_id

    def name(self) -> str: ...
    def date(self) -> datetime | None: ...
    def location(self) -> str | None: ...
    def state_province(self) -> str | None: ...
    def parse(self) -> dict: ...  # auto-discovers all public methods

class RaceResultParser:
    """Parses the JSON API response into normalized result dicts."""

    def __init__(self, race_id: int, raw_json: list[dict]):
        self._data = raw_json

    def results(self, *fields: str) -> list[dict]:
        """Parse results, optionally selecting specific fields."""

    def categories(self) -> list[str]:
        """Extract unique category names from the result set."""

    def field_sizes(self) -> dict[str, int]:
        """Return {category_name: count} for each category."""
```

### Phase 4: Scraper — Orchestration & Persistence (20% of effort)

| Task | Description | Output |
|------|-------------|--------|
| 4.1 | Implement `scraper/pipeline.py`: `ScrapeOrchestrator` that ties client, parsers, DB together | Pipeline orchestrator |
| 4.2 | Implement `__main__.py` CLI with `scrape` and `classify` subcommands | CLI entry point |
| 4.3 | Implement scrape_log recording (success/failure/skip per race_id) | Resumable scraping |
| 4.4 | Integration test: scrape 5 fixture races end-to-end into in-memory SQLite | Passing tests |

**Key function signatures:**
```python
# raceanalyzer/scraper/pipeline.py
class ScrapeOrchestrator:
    """Coordinates fetching, parsing, deduplication, and persistence."""

    def __init__(self, client: RoadResultsClient, session: Session, settings: Settings):
        ...

    def scrape_race(self, race_id: int) -> ScrapeLog:
        """Scrape a single race: fetch HTML + JSON, parse, persist. Returns log entry."""

    def scrape_range(
        self, start_id: int, end_id: int, skip_existing: bool = True
    ) -> list[ScrapeLog]:
        """Scrape a range of race IDs with progress tracking and resumability."""

    def _persist_race(self, metadata: dict, results: list[dict]) -> Race:
        """Insert/update Race, create Results, deduplicate Riders."""

    def _get_scraped_ids(self) -> set[int]:
        """Query scrape_log for already-processed race IDs."""
```

### Phase 5: Finish Type Classification (15% of effort)

| Task | Description | Output |
|------|-------------|--------|
| 5.1 | Implement `classification/types.py`: `FinishType` enum (already in models) | Enum definition |
| 5.2 | Implement `classification/grouping.py`: `group_by_consecutive_gaps()` | Grouping algorithm |
| 5.3 | Implement `classification/rules.py`: `classify_finish_type()` with the decision tree from research-findings.md | Rule-based classifier |
| 5.4 | Wire classifier into CLI `classify` subcommand | CLI integration |
| 5.5 | Write tests with synthetic time data covering all 7 finish types + edge cases (no times, 1 rider, all DNF) | Passing tests |

**Key function signatures:**
```python
# raceanalyzer/classification/grouping.py
from dataclasses import dataclass

@dataclass
class RiderGroup:
    """A group of riders finishing together."""
    riders: list[Result]
    min_time: float
    max_time: float
    gap_to_next: float | None  # seconds to next group, None if last

def group_by_consecutive_gaps(
    results: list[Result],
    gap_threshold: float = 3.0,
) -> list[RiderGroup]:
    """
    Sort results by time, split into groups wherever the gap between
    consecutive finishers exceeds gap_threshold seconds.

    Implements the UCI chain rule: a stretched group with small inter-rider
    gaps stays together even if total spread exceeds the threshold.
    """

# raceanalyzer/classification/rules.py
@dataclass
class ClassificationResult:
    finish_type: FinishType
    confidence: float
    metrics: dict  # All computed group metrics, stored for provenance

def classify_finish_type(
    groups: list[RiderGroup],
    total_finishers: int,
) -> ClassificationResult:
    """
    Apply rule-based decision tree to grouped results.

    Decision logic (from research-findings.md):
    - BUNCH_SPRINT: largest_group_ratio > 0.5 AND gap_to_second < 30s
    - BREAKAWAY: leader_group <= 5 AND gap_to_second > 30s AND largest_group_ratio > 0.4
    - BREAKAWAY_SELECTIVE: leader_group <= 5 AND gap_to_second > 30s AND largest_group_ratio <= 0.4
    - GC_SELECTIVE: num_groups > 5 AND largest_group_ratio < 0.3
    - REDUCED_SPRINT: leader_group in (6, total*0.5) range
    - MIXED: everything else
    - UNCLASSIFIABLE: no time data available
    """
```

### Phase 6: Verification, Testing & Documentation (10% of effort)

| Task | Description | Output |
|------|-------------|--------|
| 6.1 | Save 5 real JSON API responses as test fixtures (sprint, breakaway, selective, no-times, edge case) | `tests/fixtures/` |
| 6.2 | Hand-label 20 PNW races for classifier validation | `tests/fixtures/labeled_races.json` |
| 6.3 | Write integration test: full pipeline from fixture JSON to classified DB | End-to-end test |
| 6.4 | Run classifier against 20 labeled races, log accuracy | Validation report |
| 6.5 | Verify edge cases: empty results, all-DNF, single rider, placement-only | Edge case tests |

## Files Summary

| File Path | Purpose | New/Modified |
|-----------|---------|-------------|
| `pyproject.toml` | Project metadata, dependencies, tool config | Modified |
| `.pre-commit-config.yaml` | Linting/formatting hooks | New |
| `raceanalyzer/__init__.py` | Package init with `__version__` | New |
| `raceanalyzer/__main__.py` | CLI entry point (scrape, classify subcommands) | New |
| `raceanalyzer/config.py` | `Settings` dataclass | New |
| `raceanalyzer/db/__init__.py` | Package init | New |
| `raceanalyzer/db/engine.py` | Engine/session factory, `init_db()` | New |
| `raceanalyzer/db/models.py` | 7 SQLAlchemy ORM models | New |
| `raceanalyzer/scraper/__init__.py` | Package init | New |
| `raceanalyzer/scraper/client.py` | `RoadResultsClient` with retry/rate-limit | New |
| `raceanalyzer/scraper/parsers.py` | `RacePageParser`, `RaceResultParser` | New |
| `raceanalyzer/scraper/pipeline.py` | `ScrapeOrchestrator` | New |
| `raceanalyzer/scraper/errors.py` | Two-tier error hierarchy | New |
| `raceanalyzer/classification/__init__.py` | Package init | New |
| `raceanalyzer/classification/grouping.py` | `group_by_consecutive_gaps()` | New |
| `raceanalyzer/classification/rules.py` | `classify_finish_type()` rule engine | New |
| `raceanalyzer/classification/types.py` | `FinishType` enum (shared with models) | New |
| `raceanalyzer/utils/__init__.py` | Package init | New |
| `raceanalyzer/utils/fuzzy.py` | `find_or_create_rider()` with rapidfuzz | New |
| `raceanalyzer/utils/time_parse.py` | RaceTime string -> float seconds | New |
| `tests/conftest.py` | Shared fixtures, in-memory DB session factory | New |
| `tests/fixtures/race_sprint.json` | Known bunch sprint fixture | New |
| `tests/fixtures/race_breakaway.json` | Known breakaway fixture | New |
| `tests/fixtures/race_selective.json` | Known selective finish fixture | New |
| `tests/fixtures/race_no_times.json` | Placement-only race fixture | New |
| `tests/fixtures/race_html_meta.html` | HTML metadata extraction fixture | New |
| `tests/fixtures/labeled_races.json` | 20 hand-labeled races for validation | New |
| `tests/test_client.py` | HTTP client tests (mocked) | New |
| `tests/test_parsers.py` | Parser tests against fixtures | New |
| `tests/test_pipeline.py` | Integration: scrape -> DB | New |
| `tests/test_grouping.py` | Time-gap grouping tests | New |
| `tests/test_rules.py` | Classification rule tests | New |
| `tests/test_fuzzy.py` | Rider deduplication tests | New |
| `tests/test_models.py` | Schema creation, constraints | New |

## Definition of Done

- [ ] `python -m raceanalyzer scrape --start 12500 --end 12600` completes without error, populating `races`, `results`, `riders`, `categories`, and `scrape_log` tables
- [ ] Interrupting and rerunning the scrape command resumes from where it left off (no duplicate rows, no re-fetching)
- [ ] `python -m raceanalyzer classify --all` populates `race_classifications` for every race+category with time data
- [ ] Classifier produces correct labels for >= 16/20 (80%) hand-labeled PNW races
- [ ] Edge cases handled without crashes: empty results, all-DNF races, single-rider categories, placement-only data (classified as UNCLASSIFIABLE)
- [ ] All tests pass: `pytest tests/ -v` with >= 85% line coverage on `raceanalyzer/` package
- [ ] `ruff check .` and `mypy raceanalyzer/` pass with zero errors
- [ ] Pre-commit hooks configured and enforced
- [ ] Database schema supports future sprint queries: "all P12 results at Banana Belt across years", "all races classified as BUNCH_SPRINT in WA"

## Risks & Mitigations

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| road-results.com JSON API is discontinued or rate-limited aggressively | High | Low | Archive raw HTML on `races.raw_html` for re-parsing fallback. Implement respectful rate limiting (0.5s delay between batches, max 4 workers). Add User-Agent header identifying the tool. |
| road-results.com HTML structure changes, breaking metadata regex | Medium | Medium | Archive raw HTML. Parser tests against fixtures will catch regressions. Regex patterns are isolated in `RacePageParser` for easy updates. |
| Rule-based classifier has poor accuracy on amateur races | Medium | High | Store all group metrics on `race_classifications` so we can train an ML model later without re-computing. Make gap threshold configurable. Plan manual labeling as a Sprint 002 task. |
| Rider deduplication produces false merges (e.g., "John Smith" = "John Smith") | Medium | Medium | Use `road_results_id` as primary dedup key when available; fall back to fuzzy name matching only when ID is missing. Log all fuzzy matches above threshold but below 100% for manual review. |
| Scope creep: trying to build too much in Sprint 001 | Medium | Medium | Strict scope boundary: scrape, store, classify. No ratings, no predictions, no UI. Course profiling is explicitly deferred. |
| Time parsing fails on unexpected `RaceTime` formats | Low | Medium | Build a comprehensive test suite with real-world time strings. Log unparseable times and mark those results as `time_seconds=NULL`. |
| SQLite write contention during parallel scraping | Low | Low | Use `check_same_thread=False` and WAL journal mode. Batch commits (one transaction per race, not per result row). If still problematic, serialize writes through a queue. |

## Security Considerations

- **Respectful scraping**: Rate limiting, exponential backoff, and a descriptive User-Agent header. No credential stuffing or session hijacking. The JSON API is publicly accessible without authentication.
- **Dependency pinning**: All dependencies specified with minimum versions in `pyproject.toml`. Use `pip-audit` or `safety` to check for known vulnerabilities before release.
- **No secrets in code**: Database path and configuration via `Settings` dataclass, not hardcoded. No API keys required for road-results.com. If future sprints need API keys (Strava, Google Elevation), use environment variables, never committed files.
- **Data privacy**: All scraped data is publicly available race results. Rider names and license numbers are already public on road-results.com. No PII beyond what the source publishes. Consider whether storing `license_number` locally creates any obligation under state privacy laws (probably not, but worth noting).
- **SQL injection**: Mitigated by exclusive use of SQLAlchemy ORM (parameterized queries). No raw SQL strings.
- **Input validation**: Race IDs from CLI are validated as positive integers. JSON API responses are validated before insertion (unexpected fields logged, not silently dropped).

## Dependencies

### External
- **road-results.com** — Primary data source. No SLA, no API documentation, no guarantee of stability.
- **Python 3.11+** — Required for `datetime.fromisoformat()` improvements, `tomllib`, and `|` union syntax in type hints.

### Python Packages
| Package | Version | Purpose |
|---------|---------|---------|
| `sqlalchemy` | >= 2.0 | ORM and database management |
| `requests` | >= 2.31 | HTTP client |
| `requests-futures` | >= 1.0 | Async parallel fetching |
| `rapidfuzz` | >= 3.0 | Fuzzy string matching for rider dedup |
| `pandas` | >= 2.0 | Data manipulation (classification, queries) |
| `click` | >= 8.0 | CLI framework |
| `pytest` | >= 7.0 | Testing (dev dependency) |
| `pytest-cov` | >= 4.0 | Coverage reporting (dev dependency) |
| `responses` | >= 0.23 | HTTP mocking for tests (dev dependency) |
| `ruff` | >= 0.3 | Linting and formatting (dev dependency) |
| `mypy` | >= 1.8 | Type checking (dev dependency) |
| `pre-commit` | >= 3.0 | Git hooks (dev dependency) |

### Internal
None. Greenfield project.

## Open Questions

1. **Gap threshold for amateur racing**: The UCI uses 3 seconds at pro speeds (~60 km/h). Amateur fields at 35-45 km/h cover less distance per second, so the equivalent physical gap is smaller. Should we use 2 seconds instead? Or make it speed-dependent if we ever get average speed data? **Recommendation**: Start with 3 seconds as a default, but store the `gap_threshold_used` on each classification so we can re-classify later with a different threshold without losing the original.

2. **Race ID strategy**: road-results.com appears to use sequential integer IDs. Should we scrape all 13,000+ or target PNW only? **Recommendation**: Scrape a broad range (the API call is cheap), but add a `state_province` column and filter at query time. Non-PNW data may be useful for training classification models with more diverse examples.

3. **Rider identity across years**: The same rider may have different `RacerID` values across years, or the same name with different IDs. How aggressively should we merge? **Recommendation**: Use `road_results_id` as the primary key when available. Only apply fuzzy name matching when ID is absent. Never auto-merge riders with different IDs — log them for manual review.

4. **Category normalization**: road-results.com uses inconsistent category names ("Men P/1/2", "Men Pro/1/2", "Men Pro 1/2", "M P12"). How do we normalize? **Recommendation**: Build a mapping table (`category_aliases`) in Sprint 002. For Sprint 001, store the raw category string and create the `categories` table with dedup as a best-effort pass using fuzzy matching on category names.

5. **Should we archive raw JSON responses?** The Gemini draft doesn't address this. **Recommendation**: Yes, store raw JSON as files in `data/raw/{race_id}.json` during the initial scrape. Disk is cheap; re-fetching 13,000 races is not. This also provides ground truth for debugging parser issues.

6. **Placement-only races**: Some races have finishing positions but no times. The classifier cannot group by time gaps. **Recommendation**: Classify as `UNCLASSIFIABLE` with a note. In Sprint 003+, consider inferring finish type from place distributions (e.g., if many riders share the same time, it was likely a sprint), but this is speculative and out of scope for Sprint 001.
