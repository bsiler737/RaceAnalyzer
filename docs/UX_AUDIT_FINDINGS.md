# UX Audit Findings — Beginner Racer Journey Testing

> **Date:** 2026-03-11
> **Tested by:** Claude Opus 4.6, walking all 10 user journeys from `docs/USER_JOURNEYS.md`
> **Method:** Playwright screenshots of live app on localhost:8501 with production DB (9,376 pre-computed predictions across 729 series)

---

## Fixed in this session

| # | Issue | Severity | Fix | Commit |
|---|-------|----------|-----|--------|
| 1 | **Duplicate location display** — every card showed "Langley Twp, BC, BC" and "Grapeview, WA, WA" | High | Skip appending `state_province` when it already appears in `location` string | a15343c |
| 2 | **Blank elevation chart** — Banana Belt preview showed a huge empty white rectangle where the course profile should be. The JS HTML template rendered silently blank in the Streamlit iframe. | High | Switched `render_interactive_course_profile` to always use the reliable Plotly + Folium fallback | a15343c |
| 3 | **Feed filters excluded all upcoming races** — filtering to Road + Criterium showed zero upcoming races, only "Past Races (130)". All 18 upcoming races have `race_type = None`, so they were filtered out. | High | Changed filter logic to pass through races with unknown type/discipline instead of excluding them | a15343c |
| 4 | **Messy state filter values** — State/Region filter showed "OR", "OR.", "Oregon", "US-OR" (all Oregon) and "WA", "Wa", "Washington" (all Washington) as separate entries | Medium | Added `normalize_state()` mapping and deduplication in `get_available_states()` | a15343c |

---

## Still broken — finish type prediction is the #1 problem

### The core issue

The **Predicted Finish Type** feature — the heart of "Can I survive this race?" and "What kind of racer does well here?" — is non-functional for the majority of races. This single problem cascades into 5 of the 13 remaining issues.

**By the numbers:**

| Metric | Count |
|--------|-------|
| Total `RaceClassification` rows | 12,058 |
| With `finish_type = UNKNOWN` | 4,761 (39%) |
| With `finish_type = INDIVIDUAL_TT` | 3,069 (25%) |
| With a meaningful finish type | 4,228 (35%) |
| Total distinct races with classifications | 1,386 |
| Races where ALL classifications are UNKNOWN | 630 (45%) |
| Races with at least one non-UNKNOWN classification | 756 (55%) |

### Why the current classifier can't help

The existing `raceanalyzer classify --all` command skips these 630 races because they already have `RaceClassification` rows (just with `finish_type = UNKNOWN`). More importantly, **the classifier requires finish time data to work** — it analyzes time gaps between riders to determine bunch sprint vs breakaway vs selective finishes.

These 630 races have **results but no finish times** (0 of their results have `race_time_seconds` populated). The data was scraped from sources that only provided placements and points, not actual times. We won't be able to get time data for these races.

### The path forward: course-based prediction

Since we can't classify by time gaps, we need a **course-based finish type predictor** that infers likely finish type from course characteristics. The signals available:

| Signal | Coverage | Predictive Value |
|--------|----------|-----------------|
| `course_type` (flat/rolling/hilly/mountainous) | Series with RWGPS routes | High — flat courses overwhelmingly produce bunch sprints |
| `total_gain_m` | Series with RWGPS routes | High — more climbing = more selective |
| `distance_m` | Series with RWGPS routes | Medium — longer races are more selective |
| `climbs_json` (climb count, max gradient) | Series with RWGPS routes | High — number and steepness of climbs |
| `race_type` (criterium/road_race/time_trial) | Historical races only | High — crits are almost always bunch sprints |
| `m_per_km` (gain per km) | Series with RWGPS routes | High — derived metric, combines distance + gain |

**Proposed approach:** Build a heuristic or simple model that predicts finish type from course profile + race type. For example:
- Criterium + flat → bunch sprint (high confidence)
- Road race + mountainous + >15 m/km → breakaway selective (high confidence)
- Road race + rolling + 8-12 m/km → small group sprint or reduced sprint (moderate confidence)
- Road race + flat + <5 m/km → bunch sprint (moderate confidence)

This would unblock issues #5, #15, #16, and #17 for any series that has course data. It wouldn't require re-scraping or new data — just a new prediction pathway using data we already have.

### What this unblocks

| Issue # | Description | How course-based prediction fixes it |
|---------|-------------|--------------------------------------|
| 5 | "No historical data for predictions yet" | Course-based predictor provides a finish type even without time data |
| 15 | "No similar races found" | Similarity scoring works when `predicted_finish_type` is populated |
| 16 | "Who does well here?" missing | `racer_type_long_form()` generates text when finish type is known |
| 17 | Inconsistent card info density | Feed cards show plain-English finish description when prediction exists |

---

## Still broken — other data pipeline issues

| # | Issue | Severity | Root Cause | Affected Journeys |
|---|-------|----------|------------|-------------------|
| 6 | **Upcoming races have no `race_type`** — all 18 upcoming `Race` rows have `race_type = None`. This means discipline/type filters can't distinguish upcoming crits from road races from gravel. When a user filters to "Criterium only", they still see all upcoming races (because we now pass through unknowns). | High | The scraper doesn't populate `race_type` for future/upcoming races. Only historical races with results get typed. Could be inherited from series history. | 4 |
| 7 | **Some series have no Course data** — "The Ridge Circuit Race" card shows no terrain, no distance, no elevation gain. Just field size and drop rate. | Medium | No `Course` row exists for these series. The RWGPS route matching or elevation extraction hasn't been run for all series. | 1, 2, 7, 9 |
| 8 | **"What to Expect" narrative says "0% drop rate" for mountainous courses** — Banana Belt (1293m gain, "Mountainous") shows "Historically 0% of starters are dropped or DNF" which seems implausible and is based on only 1 edition. | Medium | Only 1 `Race` row exists for Banana Belt despite it being a well-known multi-year series. Either editions aren't being scraped or series matching isn't linking them. | 2, 5 |

---

## Still broken — UI/UX issues

| # | Issue | Severity | Details | Affected Journeys |
|---|-------|----------|---------|-------------------|
| 9 | **Deep-link to past-only series shows near-empty page** — `/?series_id=9` (Gorge Roubaix) shows only "Show all races" button and "Past Races (1)" collapsed. The entire main content area is blank. A shared link should show something useful. | High | The feed page puts past-only series into a collapsed expander. If someone shares a link to a race that's not upcoming, the recipient sees essentially nothing. | 6, 10 |
| 10 | **Banana Belt search shows only "Past Races (15)" collapsed** — searching "Banana Belt" returns results but they're all past, so the user sees a collapsed section and empty space. No preview or summary of what Banana Belt is. | Medium | Search results that are entirely in the past get hidden behind a collapsed expander. There's no "here's what this race is" summary for past-only series. | 5 |
| 11 | **Startlist header contradicts content** — Gorge Roubaix preview shows "Based on past editions (no startlist available)" as a caption, then immediately lists rider names with points below it. Confusing mixed message. | Medium | The source label says "no startlist" but the fallback to historical contenders does populate the list. The label is technically accurate but UX-misleading. Should say something like "Likely contenders based on past editions". | 3 |
| 12 | **"Ontario" in state filter** — irrelevant for PNW bike racers. Likely a data quality issue from scraping. | Low | A race in the DB has `state_province = "Ontario"`. The filter shows all distinct values. | 4 |
| 13 | **Register button shows on cards that may have no registration URL** — the button renders for all upcoming races but clicking may do nothing if `registration_url` is null. | Low | The card code checks `item.get("is_upcoming") and item.get("registration_url")` so this should be guarded — but worth verifying all upcoming races actually have URLs. | 1, 10 |
| 14 | **Elevation chart is small relative to map** — on the Plotly+Folium fallback, the map takes most of the vertical space and the elevation chart is a small strip below. The elevation profile is arguably more important for course study. | Low | The fallback renders Folium map first (full width, ~400px tall) then Plotly chart (250px). The chart-to-map ratio should probably be inverted. | 9 |
| 15 | **No "Similar Races" data for most series** — the Similar Races section on race preview pages shows "No similar races found." for races checked. | Medium | The similarity scoring function (`compute_similarity`) requires `course_type` and `predicted_finish_type` to score well. With most finish types unknown and some series lacking course data, the scoring can't find good matches. Unblocked by course-based prediction (#5). | 6 |
| 16 | **"Who does well here?" racer type description missing** — the expanded racer type paragraph in "What to Expect" doesn't appear because it requires a non-unknown `predicted_finish_type`. | Medium | Same root cause as #5 — finish types aren't classified. The `racer_type_long_form()` function returns `None` when finish type is unknown. Unblocked by course-based prediction (#5). | 5 |
| 17 | **Feed cards missing finish type plain-English description for many races** — some cards show the finish description ("The whole pack stayed together and sprinted for the line") but others don't. Inconsistent information density across cards. | Medium | Cards only show the plain-English description when `predicted_finish_type` is set in the pre-computed `SeriesPrediction` row. Races with unknown finish type show nothing. Unblocked by course-based prediction (#5). | 1, 7, 10 |

---

## Summary by user journey

| Journey | Status | Blocking Issues |
|---------|--------|----------------|
| 1. "What's happening this weekend?" | Works well | #7 (some cards sparse), #17 (inconsistent info) |
| 2. "Can I survive this race?" | Partially works | #5 (no finish prediction), #8 (bad drop rate data) |
| 3. "Are my friends doing this one?" | Works (can't fully verify) | #11 (startlist label) |
| 4. "I only race crits" | Partially works | #6 (can't filter upcoming by type) |
| 5. "What kind of racer does well at Banana Belt?" | Partially works | #5, #10, #16 (no finish prediction, no racer type) |
| 6. "This race looks like that crit I did last month" | Broken | #9 (deep-link empty), #15 (no similar races) |
| 7. "Plan my spring season" | Works well | #17 (inconsistent card info) |
| 8. "How big is the field?" | Works well | — |
| 9. "I want to study the course before race day" | Works well | #14 (chart sizing) |
| 10. "First time user" | Works | #9 (shared links), #17 (inconsistent) |

---

## Recommended priority for next sprint

1. **Build course-based finish type predictor** — unblocks #5, #15, #16, #17 (most impactful single change). Uses course profile data (terrain, gain, m/km, climb count, race type) to predict finish type for races that lack time-gap data. See "The path forward" section above.
2. **Populate `race_type` on upcoming races** — unblocks #6. Inherit from series history (if a series has always been a criterium, the next edition is a criterium).
3. **Improve deep-link / search for past-only series** — fixes #9, #10. Show the race preview card expanded instead of a collapsed expander.
4. **Link more series to RWGPS routes / extract elevation** — fixes #7. Increases coverage for the course-based predictor.
5. **Fix startlist labels** — fixes #11. Quick copy change: "Likely contenders based on past editions".
6. **Scrape or link additional Banana Belt editions** — fixes #8.
