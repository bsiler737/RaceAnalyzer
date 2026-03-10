# Sprint 001 Intent: Data Pipeline Foundation

## Seed

Build an analysis tool that helps bike racers understand the results of road races in the Pacific Northwest (WA, OR, ID, BC). The tool should classify race finishes by type (sprint, breakaway, individual/selective), predict race outcomes, and recommend races to riders based on their cycling phenotype. Primary data source: road-results.com.

Key user questions from `seed.md`:
- What is the most common finish type for each race/category?
- Given registered riders, what kind of finish do you expect?
- If I'm a sprinter/rouleur/attacker, which PNW races are good for me?
- Who are the top candidates for podium given the expected finish type?

Reference documents:
- `seed.md` — project goals and user stories
- `research-findings.md` — best approaches across 7 research areas
- `exemplary-code.md` — top 5 reference projects with code patterns to adopt

## Context

- **Greenfield project**: No source code, no git repo, no database. Only research docs and 17 cloned reference repos in `examples/`.
- **Research complete**: Deep research across data acquisition, finish type classification, race prediction, rider phenotype, course profiles, UI/UX, and tech stack. All documented in `research-findings.md`.
- **Key discovery**: road-results.com exposes a hidden JSON API at `downloadrace.php?raceID={ID}&json=1` returning 29 structured fields per result. This eliminates most HTML parsing.
- **Reference implementations identified**: `road-results` (scraper + TrueSkill), `PerfoRank` (race clustering + ranking), `procyclingstats` (scraper architecture), `skelo` (Elo/Glicko with sklearn), `Cycling-predictions` (feature engineering).
- **Recommended tech stack**: Python 3.11+, SQLite/SQLAlchemy, Pandas, scikit-learn, XGBoost, Streamlit, Plotly, rapidfuzz.

## Recent Sprint Context

No prior sprints. This is Sprint 001 — the first implementation sprint.

## Relevant Codebase Areas

### Reference Code (in `examples/`)
- `examples/road-results/scraping.py` — JSON API construction, async fetching with FuturesSession
- `examples/road-results/model.py` — Three-table schema (Races, Results, Racers) with TrueSkill columns
- `examples/road-results/ratings.py` — Chronological TrueSkill processing per category
- `examples/procyclingstats/procyclingstats/scraper.py` — Class-per-entity pattern, auto-discovery parse(), retry logic
- `examples/procyclingstats/procyclingstats/errors.py` — Two-tier error semantics (Expected vs Unexpected)
- `examples/skelo/skelo/model/base.py` — Temporal validity intervals, sklearn-compatible interface
- `examples/PerfoRank/FEClustering.ipynb` — Elevation-based race clustering with scipy peak detection
- `examples/PerfoRank/CaseStudy.ipynb` — XGBoost LambdaMART ranking with cluster-specific TrueSkill
- `examples/Cycling-predictions/` — Multi-timescale features, race-level train/test split, time-gap grouping

### Patterns to Adopt (from `exemplary-code.md`)
1. JSON API over HTML scraping (road-results)
2. Async parallel fetching (road-results)
3. Class-per-entity scraper architecture (procyclingstats)
4. Two-tier error semantics (procyclingstats)
5. Flexible field selection with `*args` (procyclingstats)
6. Temporal validity intervals (skelo)
7. sklearn-compatible rating interface (skelo)
8. Time-gap grouping for finish type (Cycling-predictions, 10s threshold)
9. Finish type classification rules from research-findings.md (CV, group ratios)
10. Race-level train/test split (Cycling-predictions)

## Constraints

- **Python only** — entire stack is Python (no JS/TS frontend)
- **SQLite for MVP** — zero config, swap to PostgreSQL later if needed
- **road-results.com is primary data source** — JSON API + HTML for metadata
- **Must be respectful scraper** — rate limiting, exponential backoff, avoid overwhelming the site
- **PNW scope** — WA, OR, ID, BC races only (filter after scraping)
- **Must handle amateur racing specifics** — smaller fields, wider ability range, sparse data, no leadout trains
- **No labeled training data exists** — finish type classification must start rule-based, with manual labeling planned later

## Success Criteria

1. **Data pipeline works end-to-end**: Can scrape race results from road-results.com, store in SQLite, and query them
2. **Finish type classification**: Given a set of race results with times, correctly classify the finish type using gap-based grouping
3. **Database schema supports all downstream use cases**: Races, riders, results, categories, courses, classifications, ratings
4. **Scraper is robust**: Handles errors, rate limits, missing data, and can resume interrupted scrapes
5. **Foundation is extensible**: Architecture supports adding prediction, phenotyping, and UI layers in future sprints

## Verification Strategy

- **Scraper**: Fetch 10-20 known races by ID, compare JSON output to what's visible on road-results.com
- **Database**: Insert scraped data, run queries that answer seed.md questions (e.g., "all P12 results at Banana Belt")
- **Finish type classifier**: Hand-label 20 races from known PNW events, compare classifier output to labels
- **Gap grouping**: Verify against UCI 3-second rule on races with known bunch sprint outcomes
- **Edge cases**: Empty results, DNF/DQ/DNP handling, races with placement-only data (no times), single-rider categories
- **Testing**: pytest with fixtures from saved JSON API responses

## Uncertainty Assessment

- **Correctness uncertainty: Low** — JSON API structure is documented, scraping approach is proven by `road-results` reference repo
- **Scope uncertainty: Medium** — First sprint needs to lay foundation for 6 pipeline stages; risk of trying to do too much
- **Architecture uncertainty: Medium** — Greenfield project, need to establish package structure, schema design, and patterns that will carry through all future sprints

## Open Questions

1. Should Sprint 001 cover just data acquisition, or also include finish type classification? (Research suggests they're tightly coupled — classification needs time data from scraping)
2. How should we handle the ~13,000 sequential race IDs? Scrape all upfront vs. incremental by region/date?
3. Should we initialize a git repo and set up project tooling (pyproject.toml, pre-commit, CI) as part of this sprint?
4. What's the right gap threshold for amateur racing? Research says 3s (UCI pro) but amateur racing at lower speeds may need 2-4s.
5. Should the schema use integer race IDs from road-results.com as primary keys, or generate our own?
