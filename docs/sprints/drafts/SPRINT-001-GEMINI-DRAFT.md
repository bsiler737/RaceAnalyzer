# Sprint 001 Draft: Data Pipeline Foundation & Finish Classification

## Overview

This sprint marks the beginning of the Race Analyzer project. The primary goal is to establish the foundational data pipeline, which is essential for all subsequent analysis and prediction tasks. This involves creating a robust scraper to acquire race data from the `road-results.com` hidden JSON API, defining a relational database schema to store this data, and implementing a first-pass, rule-based classifier to determine the finish type of each race. This sprint will deliver a populated database with classified race results, providing the core dataset for future sprints on prediction, phenotyping, and UI development.

## Use Cases

This sprint focuses on building the backend infrastructure. The primary user is the development team, and the core use case is to enable future user-facing features.

- **Developer**: As a developer, I need to reliably scrape race results and metadata from road-results.com into a structured local database.
- **Developer**: As a developer, I need to programmatically classify the finish type (e.g., "Bunch Sprint", "Breakaway") for each race based on finisher time gaps.
- **Future Analyst/User**: (Enabled by this sprint) I want to query the database to find out the most common finish type for a specific race and category (e.g., "Banana Belt Road Race, Cat 3 Men").
- **Future Analyst/User**: (Enabled by this sprint) I want to see a historical trend of finish types for a race over the last five years.

## Architecture

The architecture for Sprint 001 is a pure Python data pipeline composed of three main components: a scraper, a data store, and a classifier.

1.  **Project Structure**: A standard Python package (`raceanalyzer`) will be created, with sub-modules for `data`, `scraper`, and `classification`. All dependencies and project metadata will be managed by `pyproject.toml`.

2.  **Scraper (`raceanalyzer.scraper`)**:
    *   A central `RoadResultsScraper` class inspired by the `procyclingstats` library's class-per-entity pattern.
    *   Leverages the `requests` and `requests_futures` libraries for asynchronous parallel fetching, as demonstrated in the `road-results` reference project.
    *   Extracts race metadata (name, date, location) from HTML using compiled regex and fetches detailed results from the `downloadrace.php?raceID={ID}&json=1` endpoint.
    *   Includes robust error handling and rate-limiting best practices.

3.  **Data Store (`raceanalyzer.data`)**:
    *   A local SQLite database (`data/race_analyzer.db`) for zero-configuration setup.
    *   Schema managed by SQLAlchemy ORM.
    *   A three-table design inspired by the `road-results` project:
        *   `races`: Stores race metadata, location, date, and the classified finish type.
        *   `riders`: A deduplicated table of unique riders.
        *   `results`: The core table linking riders to races, storing their place, time, team, and other data from the JSON source.

    **Schema Definition (`raceanalyzer/data/models.py`)**:
    ```python
    from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
    from sqlalchemy.orm import relationship, declarative_base

    Base = declarative_base()

    class Race(Base):
        __tablename__ = 'races'
        id = Column(Integer, primary_key=True) # road-results.com raceID
        name = Column(String)
        date = Column(DateTime)
        location = Column(String)
        finish_type = Column(String) # e.g., 'BUNCH_SPRINT', 'BREAKAWAY'
        results = relationship("Result", back_populates="race")

    class Rider(Base):
        __tablename__ = 'riders'
        id = Column(Integer, primary_key=True, autoincrement=True)
        name = Column(String, unique=True, index=True)
        results = relationship("Result", back_populates="rider")

    class Result(Base):
        __tablename__ = 'results'
        id = Column(Integer, primary_key=True, autoincrement=True)
        race_id = Column(Integer, ForeignKey('races.id'))
        rider_id = Column(Integer, ForeignKey('riders.id'))
        place = Column(Integer)
        time_seconds = Column(Float)
        category = Column(String)
        team = Column(String)
        race = relationship("Race", back_populates="results")
        rider = relationship("Rider", back_populates="results")
    ```

4.  **Classifier (`raceanalyzer.classification`)**:
    *   A standalone module that operates on data queried from the database.
    *   Implements a `group_by_time_gaps` function based on the consecutive-gap grouping method from the `Cycling-predictions` reference, with a configurable time threshold.
    *   Implements a `classify_finish_type` function containing the rule-based logic derived from `research-findings.md` (evaluating group sizes, gaps, and field distribution).

## Implementation (Phased Tasks)

### Phase 1: Project Setup & Core Data Models
- **Task 1.1**: Initialize git repository. Create `pyproject.toml` with dependencies: `sqlalchemy`, `pandas`, `requests`, `requests-futures`, `rapidfuzz`, `pytest`.
- **Task 1.2**: Create the project directory structure: `raceanalyzer/`, `scripts/`, `tests/`, `data/`.
- **Task 1.3**: Implement the SQLAlchemy models (`Race`, `Rider`, `Result`) in `raceanalyzer/data/models.py` as defined in the Architecture section.

### Phase 2: Data Acquisition (Scraping)
- **Task 2.1**: Implement the `RoadResultsScraper` class in `raceanalyzer/scraper/scraper.py`. It will handle HTTP requests with retries and a shared session.
- **Task 2.2**: Implement `scrape_race_page(race_id)` -> `dict` function to fetch the HTML, extract metadata, and construct the JSON URL, inspired by `road-results/scraping.py`.
- **Task 2.3**: Create a database session management utility in `raceanalyzer/data/db.py` to handle creating the engine and getting sessions.
- **Task 2.4**: Implement a main script, `scripts/scrape.py`, that accepts a range of race IDs. It will use `FuturesSession` to fetch all race pages in parallel.
- **Task 2.5**: The `scrape.py` script will then use the returned JSON URLs to fetch the full race results in parallel and populate the `races`, `riders`, and `results` tables in the SQLite database, handling rider deduplication using fuzzy matching.

### Phase 3: Finish Type Classification
- **Task 3.1**: In `raceanalyzer/classification/classifier.py`, create a function `group_by_time_gaps(results: list[Result], gap_threshold_seconds: int = 3) -> list[list[Result]]`. This function will sort results by time and split them into groups whenever the gap between two consecutive riders exceeds the threshold.
- **Task 3.2**: Implement the main classification function: `classify_finish_type(race_id: int) -> str`. This function will:
    1.  Query all results for a given race category from the database.
    2.  Use `group_by_time_gaps` to segment the finishers.
    3.  Calculate metrics: `largest_group_ratio`, `leader_group_size`, `gap_to_second_group`, etc.
    4.  Apply the rule-based decision tree from `research-findings.md` to return a classification string (e.g., "BUNCH_SPRINT", "BREAKAWAY", "GC_SELECTIVE").
- **Task 3.3**: Create a script `scripts/classify.py` that iterates over unclassified races in the database, runs the classifier, and updates the `finish_type` column in the `races` table.

### Phase 4: Verification & Testing
- **Task 4.1**: Create a `tests/fixtures/` directory and save the JSON API output for 3-5 known races (e.g., a known sprint, a known breakaway-friendly race).
- **Task 4.2**: Write unit tests in `tests/test_scraper.py` that use the fixtures to verify that the scraper correctly parses JSON and populates data models without making live HTTP requests.
- **Task 4.3**: Write unit tests in `tests/test_classifier.py` that create in-memory database entries for various finish scenarios and assert that `classify_finish_type` returns the expected classification.

## Files Summary

**New Files to be Created**:
- `pyproject.toml`
- `raceanalyzer/__init__.py`
- `raceanalyzer/data/__init__.py`
- `raceanalyzer/data/models.py`
- `raceanalyzer/data/db.py`
- `raceanalyzer/scraper/__init__.py`
- `raceanalyzer/scraper/scraper.py`
- `raceanalyzer/classification/__init__.py`
- `raceanalyzer/classification/classifier.py`
- `scripts/scrape.py`
- `scripts/classify.py`
- `tests/fixtures/race_123.json`
- `tests/test_scraper.py`
- `tests/test_classifier.py`
- `.gitignore` (to exclude `data/*.db`, `__pycache__/`, etc.)

## Definition of Done

- The `scripts/scrape.py` script can successfully scrape and populate the database for a given range of 100 race IDs from road-results.com.
- The `scripts/classify.py` script successfully populates the `finish_type` field for all scraped races.
- The classification logic correctly identifies finish types for at least 10 hand-verified races.
- Unit tests for the scraper and classifier pass with 100% coverage for their respective modules.
- The project is fully set up with a `pyproject.toml` and a git repository, and all code is committed.
- The SQLite database file (`data/race_analyzer.db`) is created and contains verified data.

## Risks & Mitigations

- **Risk (High)**: The `road-results.com` JSON API is unofficial and could change, break, or be disabled.
  - **Mitigation**: Our scraper will be architected with a clear separation between fetching and parsing, allowing us to swap the fetching strategy (e.g., to HTML parsing) without rewriting the entire pipeline. Implement robust error logging to detect API changes immediately.
- **Risk (Medium)**: The rule-based classifier is not nuanced enough for the wide variety of amateur race dynamics.
  - **Mitigation**: Acknowledge that this is a first-pass implementation. Make the time-gap threshold and other classification parameters easily configurable. Plan for a manual labeling effort and a transition to an ML-based model in a future sprint.
- **Risk (Low)**: Rider name variations lead to poor deduplication.
  - **Mitigation**: Use `rapidfuzz` library for fuzzy string matching when creating new rider entries. Log ambiguous matches for potential manual review.

## Security Considerations

- **Dependencies**: All Python dependencies will be specified with versions in `pyproject.toml` to ensure reproducible builds and prevent supply-chain attacks. A lock file should be used.
- **Data Privacy**: The data being scraped is publicly available race results. No private user information is being handled or stored.
- **Network**: As an internal data pipeline with no exposed services, the attack surface is minimal. Outbound requests from the scraper should use TLS.

## Dependencies

- **External**: The availability and stability of `road-results.com`.
- **Internal**: None. This is a greenfield project.

## Open Questions

1.  **What is the optimal time-gap threshold for amateur racing?**
    *   *Initial Decision*: We will start with a default of 3 seconds (inspired by UCI rules but noted as potentially needing adjustment in research). The implementation will make this parameter easily configurable for future tuning.
2.  **What is the strategy for the initial mass scrape of ~13,000 races?**
    *   *Initial Decision*: For this sprint, we will focus on a smaller, targeted subset (e.g., `raceID` range 12000-13000) to prove the pipeline. The full historical scrape will be conducted after the pipeline is validated, likely as a long-running background task.
3.  **Should we use the road-results.com integer `raceID` as our primary key?**
    *   *Initial Decision*: Yes. Using the source `raceID` as the primary key for the `races` table simplifies data mapping, avoids an unnecessary lookup table, and makes debugging against the website trivial.
