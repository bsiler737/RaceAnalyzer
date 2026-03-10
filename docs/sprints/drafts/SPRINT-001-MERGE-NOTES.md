# Sprint 001 Merge Notes

## Draft Strengths

### Claude Draft (strongest overall)
- Exceptional implementation depth — near-complete code for every module
- Correct per-category classification via `RaceClassification` table
- `ScrapeLog` for resumability
- Two-tier error hierarchy adopted from procyclingstats
- Rich Result schema capturing most of the JSON API's 29 fields
- 10-point Definition of Done, specific and testable

### Codex Draft (strongest architecture)
- 7-table schema with Category as first-class entity
- `Settings` dataclass for centralized configuration
- Explicit separation: client.py / parsers.py / pipeline.py
- Classification metrics stored on RaceClassification
- Includes project tooling (ruff, mypy, pre-commit) in Sprint 001 scope
- Raw HTML archival on races table
- ASCII data flow diagram

### Gemini Draft (most concise)
- Accessible overview — easy for newcomers to understand
- Practical race ID subset strategy (12000-13000 first)
- Correct PK decision (use road-results.com raceID)
- Clean 4-phase breakdown

## Valid Critiques Accepted

1. **Gemini's 3-table schema is insufficient** (all three critiques flagged this) — finish_type per-race is wrong, must be per-category. → Use Claude's RaceClassification approach.
2. **Claude's Rider table is dead in Sprint 001** — created but never populated. → Accept user's decision: use RacerID for basic dedup in Sprint 001.
3. **Claude's BaseScraper has thread-safety bug** — class-level `_last_request_time` shared across threads. → Use instance-level state or a lock.
4. **No raw data archival in Claude draft** — → Accept user's decision: archive both JSON and HTML.
5. **Claude's classify CLI lacks batch mode** — → Add `--all` flag from Codex draft.
6. **Gemini lacks scrape resumability** — → Use Claude's ScrapeLog.
7. **Classification metrics not stored in Gemini** — → Use Codex's approach of storing all group metrics.
8. **No project tooling in Gemini** — → Accept user's decision: include ruff, pre-commit.

## Valid Critiques Rejected

1. **Codex's Category as first-class entity with parsed gender/ability_level** — Over-engineered for Sprint 001. User chose 5-table schema. Store raw category strings; normalize in Sprint 002.
2. **Codex's 7-table schema** — User chose Claude's 5-table schema. Categories stay as strings on Result/RaceClassification for now.
3. **Codex includes fuzzy rider dedup in Sprint 001** — Scope creep risk. User chose RacerID exact-match only.

## Interview Refinements Applied

1. **Scope**: Scrape + Classify + Tooling (ruff, pre-commit, pyproject.toml, git init)
2. **Schema**: 5 tables (Race, Rider, Result, RaceClassification, ScrapeLog) — Claude's design
3. **Rider identity**: Use RacerID from JSON API for exact-match dedup now; fuzzy matching deferred
4. **Raw data archival**: Archive both JSON (to `data/raw/{race_id}.json`) and HTML (to `data/raw/{race_id}.html`)

## Synthesis Decisions

- **Package structure**: Claude's layout with Codex's client/parsers/pipeline split in scraper module
- **Config**: Codex's `Settings` dataclass pattern (cleaner than scattered constants)
- **Schema**: Claude's 5 tables with Codex's metric storage on RaceClassification
- **Error handling**: Claude's two-tier hierarchy
- **CLI**: Claude's Click-based approach with Codex's `--all` flag on classify
- **Testing**: Claude's fixture-based approach + Codex's edge case list
- **Data flow diagram**: Codex's ASCII diagram (clearest)
- **Definition of Done**: Merged from Claude (most testable) + Codex (tooling criteria)
- **Time parsing**: Claude's implementation (most complete with regex and edge cases)
- **Gap threshold**: Store `gap_threshold_used` on each classification (from Codex) for reproducibility
