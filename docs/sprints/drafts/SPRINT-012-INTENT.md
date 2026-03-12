# Sprint 012 Intent: UX Audit Fix — Course-Based Prediction & Data Quality

## Seed

Fix all 13 remaining issues found in `docs/UX_AUDIT_FINDINGS.md`. The UX audit tested 10 beginner-racer user journeys and identified 17 issues (4 already fixed in commit a15343c). The remaining issues span three categories:

1. **Finish type prediction gap** (Issues #5, #15, #16, #17) — 45% of races have UNKNOWN finish type because the classifier requires time-gap data that doesn't exist. Build a course-based predictor using terrain, elevation gain, m/km, climb count, and race_type.
2. **Data pipeline gaps** (Issues #6, #7, #8) — Upcoming races lack race_type; some series lack course data; some series have too few linked editions.
3. **UI/UX issues** (Issues #9, #10, #11, #12, #13, #14) — Deep-link to past-only series shows empty page; search for past-only series shows collapsed expander; startlist label contradicts content; Ontario in state filter; register button on races without URL; elevation chart sizing.

## Context

- **Project:** RaceAnalyzer — bike race analysis tool for PNW racers (WA, OR, ID, BC). Streamlit + SQLAlchemy + PostgreSQL/SQLite.
- **Current state:** Sprint 011 (feed redesign + performance + team personalization) is complete. 9,376 pre-computed predictions across 729 series. Feed is the primary landing page.
- **Recent work themes:** Evolved from data pipeline → course intelligence → event discovery → unified feed → performance/UX polish. Now tackling data quality and prediction gaps.
- **Key data constraint:** 39% of RaceClassification rows have finish_type=UNKNOWN; 45% of races have ALL classifications UNKNOWN. These races have results but no finish times — time-gap classification is impossible.
- **Architecture patterns:** Batch-loading (≤6 SQL queries), Streamlit caching (5-min TTL), lazy Tier 2 evaluation, graceful degradation, query param ↔ session state sync.

## Recent Sprint Context

- **Sprint 011** (completed): Feed redesign with container cards, batch queries, PerfTimer instrumentation, team matching, discipline filtering, countdown labels. 5 phases executed.
- **Sprint 010**: Feed page, deep linking, URL state persistence.
- **Sprint 009**: road-results GraphQL calendar + predictor.aspx startlists.
- **Sprint 008**: RWGPS elevation profiles, climb detection, interactive course maps.
- **Commit a15343c** (today): Fixed 4 UX audit issues — duplicate location display, blank elevation chart, feed filter exclusion of unknown types, messy state filter values.

## Relevant Codebase Areas

| Domain | Files |
|--------|-------|
| Finish type classification | `classification/finish_type.py`, `classification/grouping.py` |
| Predictions & narratives | `predictions.py` (predict_series_finish_type, racer_type_description, generate_narrative) |
| Pre-computation pipeline | `precompute.py` (SeriesPrediction table) |
| Course & elevation data | `elevation.py`, `rwgps.py`, `db/models.py` (Course table) |
| Similarity scoring | `queries.py` (compute_similarity, get_similar_series) |
| Race type & discipline | `db/models.py` (RaceType, Discipline enums), `queries.py` (discipline_for_race_type) |
| Feed & cards | `ui/pages/feed.py`, `ui/components.py`, `queries.py` (get_feed_items_batch) |
| Deep linking | `ui/app.py`, `ui/pages/feed.py` |
| Startlist display | `queries.py` (get_startlist_team_blocks), `ui/components.py` |
| CLI commands | `cli.py` (scrape, classify, compute-predictions) |
| Tests | `tests/conftest.py`, 25 test files (~2000 LOC) |

## Constraints

- Must follow existing ruff lint rules (E, F, I, W; 100-char line limit)
- Must integrate with existing `SeriesPrediction` pre-computation pipeline
- Must preserve batch-loading pattern (≤6 SQL queries for feed)
- Must maintain graceful degradation when data is missing
- Must use pytest with in-memory SQLite fixtures (no external DB in tests)
- Course-based predictor must work with existing `Course` table fields (course_type, total_gain_m, distance_m, climbs_json) — no new data sources required
- Must not break existing time-gap classifier; course-based predictor is a fallback/supplement

## Success Criteria

1. **Finish type coverage increases from 55% to 80%+** of races with at least one non-UNKNOWN classification
2. **All 18 upcoming races have a populated race_type** inherited from series history
3. **Deep-link to past-only series shows useful content** (expanded preview, not collapsed expander)
4. **Search for past-only series shows preview summary** instead of just "Past Races (N)" collapsed
5. **Startlist label says "Likely contenders based on past editions"** when showing historical fallback
6. **Feed cards consistently show finish type description** for all series with course data
7. **Similar races found for series with course data** (similarity scoring works with course-predicted finish types)
8. **"Who does well here?" racer type description appears** for series with course-predicted finish types
9. **Minor UI fixes:** Ontario removed from state filter, register button guarded, elevation chart sizing improved

## Verification Strategy

- **Unit tests:** New test class `TestCourseBasedPrediction` — test each rule (crit+flat→sprint, mountainous+high_gain→breakaway_selective, etc.)
- **Integration tests:** Run `compute-predictions` CLI on test DB and verify SeriesPrediction rows populated for previously-UNKNOWN series
- **Coverage check:** Query DB to confirm finish_type=UNKNOWN percentage drops from 45% to <20% of races
- **UI verification:** Deep-link to past-only series_id shows expanded content; search "Banana Belt" shows preview
- **Regression:** All existing tests pass; feed load time remains <1s cold / <200ms warm
- **Edge cases:** Series with no course data still gracefully degrade; races with both time-gap and course predictions prefer time-gap (higher confidence)

## Uncertainty Assessment

- **Correctness uncertainty: Medium** — The course-based predictor rules are heuristic. We have good domain knowledge (flat crits = bunch sprints, mountainous = selective) but the boundary thresholds (e.g., 8-12 m/km = rolling) need tuning. Confidence levels should reflect this.
- **Scope uncertainty: Low** — The 13 issues are well-documented with clear root causes and proposed fixes. The audit document includes specific recommendations.
- **Architecture uncertainty: Low** — Extends existing patterns (classification module, predictions pipeline, pre-computation). No new tables or external integrations needed.

## Open Questions

1. Should the course-based predictor be a separate module (e.g., `classification/course_predictor.py`) or added to the existing `classification/finish_type.py`?
2. What confidence level should course-based predictions use? Lower than time-gap-based predictions? (e.g., 0.6 vs 0.85)
3. For races that have BOTH time-gap classifications AND course data, should we prefer time-gap, average them, or use the higher-confidence one?
4. Should we add a `prediction_source` field to track whether a finish type came from time-gap analysis vs course-based inference?
5. How aggressively should we populate race_type from series history? (e.g., if 90% of historical editions are criteriums, is that enough?)
6. For issue #12 (Ontario in state filter), should we just exclude non-PNW states entirely, or clean the data?
7. Should the course-based predictor also attempt to predict for series WITHOUT course data by using only race_type? (e.g., criterium → bunch sprint even without elevation data)
