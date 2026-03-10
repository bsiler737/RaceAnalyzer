# Sprint 003: Synthetic Demo Data

## Overview

Generate realistic synthetic race data so the RaceAnalyzer UI can be demonstrated and iterated on while road-results.com blocks our IP. Adds a single new module (`raceanalyzer/demo.py`) and two CLI commands (`seed-demo`, `clear-demo`). The demo data covers ~50 races across 5 years (2020–2024), 4 PNW states/provinces, 6 categories, and all 8 finish types with realistic time distributions. This is disposable scaffolding — expected to be removed once real scraping resumes.

**Merged from**: Claude draft (primary), Codex draft (ID ranges, idempotency), Gemini draft (architecture validation)

## Architecture

- **`raceanalyzer/demo.py`** — NEW: Demo data generation + cleanup (~300 lines)
- **`raceanalyzer/cli.py`** — MODIFY: Add `seed-demo` and `clear-demo` commands
- **`tests/test_demo.py`** — NEW: ~18 tests

### Key Design Decisions

1. **Reserved ID range (900_001+)** for demo races/riders — well above `max_race_id=15000`
2. **ScrapeLog with `status="demo"`** for cleanup tracking
3. **No external dependencies** — stdlib `random` only
4. **Deterministic** — `random.seed(42)` by default, `--seed` CLI option
5. **Auto-clear before re-seed** for idempotency
6. **Finish-type-aware time generation** — each of 8 types has distinct distribution

## Success Criteria

1. `python -m raceanalyzer seed-demo` populates DB with ~50 races across 5 years, 4 states, 6 categories, all 8 finish types
2. `python -m raceanalyzer clear-demo` removes all demo data; real data untouched
3. UI shows meaningful data on all 3 pages after seeding
4. CV values span all 3 confidence badge colors (green/yellow/red)
5. Trend chart shows interesting patterns across years
6. All existing tests pass (zero regressions)
