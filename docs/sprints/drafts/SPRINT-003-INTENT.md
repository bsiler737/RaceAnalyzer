# Sprint 003 Intent: Synthetic Demo Data

## Seed

Create synthetic/demo data to hydrate the RaceAnalyzer UI while IP-blocked by road-results.com. This is disposable work — expected to be irrelevant once real scraping resumes. The demo data should exercise every UI feature: calendar filtering, race detail with confidence badges, distribution charts, and trend analysis.

## Context

- Sprint 001 delivered the data pipeline (scraper, DB, classifier, CLI)
- Sprint 002 delivered the Streamlit UI (calendar, detail, dashboard pages)
- road-results.com is currently blocking our IP (403 on all requests)
- The UI works but shows empty states because the DB has no data
- We need realistic fake data to demo and iterate on the UI

## Relevant Codebase Areas

- `raceanalyzer/db/models.py` — Race, Rider, Result, RaceClassification, ScrapeLog, FinishType enum
- `raceanalyzer/db/engine.py` — get_session(), init_db()
- `raceanalyzer/cli.py` — Click CLI (add seed-demo / clear-demo commands)
- `raceanalyzer/config.py` — Settings with pnw_regions
- `tests/conftest.py` — seeded_session fixture (similar pattern)

## Constraints

- Python 3.9+, `from __future__ import annotations`
- Must use existing ORM models — no schema changes
- Data should be realistic enough to look good in the UI (real PNW race names, realistic times, proper finish type distributions)
- Must be easy to add and remove (CLI commands)
- No external dependencies (use stdlib random/faker-free)

## Success Criteria

1. `python -m raceanalyzer seed-demo` populates DB with ~50 races across 5 years, 4 states, 5+ categories, all 8 finish types
2. `python -m raceanalyzer clear-demo` removes all demo data
3. UI shows meaningful data on all 3 pages after seeding
4. Trend chart shows interesting patterns across years
5. Confidence badges show all 3 colors (green/yellow/red)

## Uncertainty Assessment

- Correctness: **Low** — straightforward data generation
- Scope: **Low** — bounded and disposable
- Architecture: **Low** — extends existing patterns
