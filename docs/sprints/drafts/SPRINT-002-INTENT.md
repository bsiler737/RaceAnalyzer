# Sprint 002 Intent: Streamlit UI & Query Layer

## Seed

Build a Streamlit-based UI that shows all PNW bike races organized by time, with per-category analysis meaningful to users. From seed.md, users should be able to:

1. View all PNW races organized chronologically
2. See the most common finish type (overall and per selected category)
3. See frequency of each finish type
4. Given race predictor registrations, predict expected finish type for upcoming races
5. If I'm a sprinter/rouleur/attacker, which races suit me?
6. Finish type trend over the last 5 years (stacked area chart)
7. Top 10 podium candidates with probabilities (future sprint — out of scope unless simple)

This sprint covers items 1-3 and 6 fully, with foundational backend support for 4-5.

## Context

- Sprint 001 delivered: scraper (road-results.com JSON API + HTML), SQLite DB (5 tables: races, riders, results, race_classifications, scrape_log), gap-grouping finish type classifier (8 types), Click CLI (`init`, `scrape`, `classify`), 62 tests passing at 70% coverage.
- No UI layer exists. No query helpers. No visualization code.
- Backend has raw data but no aggregation queries (e.g., finish type distribution per race across years, category-level stats, calendar views).
- Python 3.9 compatibility required (`from __future__ import annotations`).
- research-findings.md recommends: Streamlit + Plotly, color-coded confidence badges, stacked area charts for trends, progressive disclosure of probabilities.

## Recent Sprint Context

- Sprint 001 established the full data pipeline: scrape → parse → DB → classify → CLI
- All 62 tests passing. Core modules at 82-100% coverage.
- DB schema already supports: Race (with date, location, state_province), Result (with race_category_name, race_time_seconds, dnf), RaceClassification (with finish_type, group metrics, confidence via cv_of_times)
- Config already has `pnw_regions = ("WA", "OR", "ID", "BC")`

## Relevant Codebase Areas

| Module | Relevance |
|--------|-----------|
| `raceanalyzer/db/models.py` | Race, Result, RaceClassification, FinishType enum — all query targets |
| `raceanalyzer/db/engine.py` | `get_session()`, `get_engine()` — session management |
| `raceanalyzer/config.py` | Settings with pnw_regions, db_path |
| `raceanalyzer/classification/finish_type.py` | ClassificationResult, classify_finish_type — may need to expose confidence |
| `raceanalyzer/cli.py` | May add `streamlit` launcher command |
| `pyproject.toml` | Needs streamlit, plotly dependencies |
| `tests/conftest.py` | Session fixture for query layer tests |

## Constraints

- Must use Streamlit + Plotly per research-findings.md recommendation
- Must work with Python 3.9+ (use `from __future__ import annotations`)
- Must use existing SQLAlchemy models — no schema changes unless truly necessary
- Color-coded confidence badges for finish type (green/yellow/red)
- Natural language qualifiers ("Likely sprint finish") — not raw decimals
- Responsive to reasonable data volumes (hundreds to low thousands of races)
- No authentication needed (local tool)

## Success Criteria

1. `python -m raceanalyzer ui` launches a Streamlit app
2. Race calendar page: all PNW races displayed chronologically, filterable by year, state, category
3. Race detail page: finish type classification per category with confidence badge, group metrics
4. Finish type dashboard: distribution charts (overall + per category), stacked area trend over years
5. Category selector persists across pages (sidebar)
6. Query layer has tests covering aggregation functions
7. All existing 62 tests still pass
8. App works with empty database (graceful empty states)

## Verification Strategy

- **Unit tests**: Query layer functions tested against in-memory SQLite with seeded data
- **Integration tests**: Streamlit pages render without errors (using `streamlit.testing` or manual verification)
- **Visual verification**: Screenshots/manual check of charts, badges, calendar
- **Edge cases**: Empty DB, races with no classifications, categories with single result, races with all DNFs
- **Regression**: All 62 existing tests pass

## Uncertainty Assessment

- Correctness uncertainty: **Low** — Well-defined queries against known schema, Streamlit is straightforward
- Scope uncertainty: **Medium** — The "meaningful analysis" requirement is open-ended; need to draw a clear line on what's in/out for this sprint
- Architecture uncertainty: **Low** — Streamlit + Plotly is a proven pattern, query layer extends existing SQLAlchemy models

## Open Questions

1. Should the query layer be a separate module (`raceanalyzer/queries.py`) or integrated into a `raceanalyzer/ui/` package?
2. How should race names be grouped across years? (e.g., "Banana Belt RR 2022" and "Banana Belt RR 2023" are the same race series — do we need a `series` concept now?)
3. Should the UI include a "scrape" trigger button, or keep scraping CLI-only?
4. What categories should appear in the category selector? Dynamic from data, or a curated PNW-relevant list?
5. For the trend chart, what's the minimum number of years of data before showing it?
