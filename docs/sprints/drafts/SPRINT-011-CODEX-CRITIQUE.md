# Sprint 011 Critique (Codex)

This critique reviews the two Sprint 011 drafts against the original use cases in `docs/USE_CASES_FEED_FIRST_GLANCE.md`. For each draft, it calls out what’s strong, what’s risky or underspecified, which edge cases are missing, and where the Definition of Done (DoD) needs tightening to be unambiguous.

---

## Claude Draft Critique (`SPRINT-011-CLAUDE-DRAFT.md`)

### Strengths

1. **High fidelity to the original use cases (IDs and priorities).** The draft mirrors the FG/DD/MT/FO/PF taxonomy and uses the same priorities and “status” framing, which makes it easy to validate scope and avoid drifting from the persona-driven rationale.

2. **Concrete implementation plan with dependency-aware phasing.** The ordering (Performance → Feed container → Card redesign → My Team → Preview) is the right dependency graph for Streamlit: without PF work, everything else becomes frustrating to iterate on.

3. **Tier 1 / Tier 2 split is the right architectural move.** Treating “collapsed card” data as cheap + stable, and “expanded details” as lazy/cached, is the best fit for Streamlit’s rerun model and directly targets PF-03.

4. **Definition of Done is unusually thorough and testable.** The DoD lists specific UI rows, graceful degradation expectations, caching, performance budgets, and a non-trivial new-test inventory—this is the level of specificity that prevents “done-ish”.

5. **Risk section is real (not ceremonial).** It explicitly acknowledges overscope, caching staleness, expander density limits, and an important hidden risk: Tier 2 editions summary can still re-introduce N+1.

### Weaknesses

1. **Batch query pseudocode currently undermines PF-01.** The draft’s “batch” approach (fetch *all* races for a set of series, then group in Python) can be a performance regression versus the current approach for larger datasets. It also conflicts with PF-05 (query-layer pagination) because you’re still materializing too much data before limiting. Prefer “one upcoming + one most-recent per series” in SQL (window function / correlated subquery) rather than pulling all races.

2. **`series_predictions` scope is very broad (and partly redundant).** Storing predicted finish type, drop rate, durations, *and* field size in one table mixes: (a) deterministic aggregates, (b) model-ish predictions, and (c) UI formatting (“label”). That makes schema evolution harder and increases the chance of staleness bugs. Consider splitting:
   - “immutable aggregates” (field size stats, edition_count, drop_rate) vs
   - “predictions” (predicted finish type + confidence) vs
   - “presentation” (labels) computed at render time.

3. **Category handling is likely to get messy.** The draft proposes per-series predictions for `[None] + categories` where `None` means “all categories aggregate”. That’s useful, but it needs clearer rules for:
   - how the feed chooses which category row to display (global category filter? per-card category?),
   - what happens when a series’ historical categories don’t match upcoming categories,
   - and how to avoid double-counting results across categories in “overall”.

4. **Team badge correctness depends on startlist availability, but UX rules aren’t nailed down.** The Open Questions mention this, but the implementation and DoD mostly assume startlists exist. The sprint needs an explicit policy for “startlist missing / not yet published / partially scraped” so FG-02/MT-02 are predictable.

5. **UI feasibility risk: “4–5 collapsed cards visible” is not solely under your control.** Streamlit’s expander/spacing + sidebar + browser viewport makes FO-08 a moving target. Without agreeing on a concrete “collapsed card height” (or a screenshot-based acceptance test), FO-08 can become an unending tuning loop.

### Gaps in Risk Analysis

1. **Data migration / backfill risk is understated.** Adding `Discipline` + `SeriesPrediction` implies either a backfill job or inference at query time. If you ship “discipline derivation” first, you still need to validate that inference doesn’t misclassify edge events (e.g., mixed-discipline naming, stage races, hill climbs). If you ship a column, you need a backfill and an ongoing rule for new series.

2. **Staleness and cache invalidation is broader than TTL.** A 300s TTL helps, but the more important invalidation events are: “new scrape imported”, “precompute finished”, “user changed category filter”, and “schema changed”. The draft should specify a simple invalidation trigger (e.g., a `predictions_version` key stored in DB / file) that busts cache immediately after precompute.

3. **Performance budget is defined, but measurement method isn’t.** “<1s cold / <200ms warm” is great, but you need to define:
   - dataset assumptions (50 series vs 100+),
   - what constitutes “cold” (fresh process? cleared Streamlit cache? cleared SQLite OS cache?),
   - and where to log/observe this (stdout vs file vs Streamlit UI in dev).

4. **Concurrency / rerun thrash risk.** With many widgets synced to query params, it’s easy to accidentally trigger “rerun loops” (set query params → rerun → widget updates → set params again). The draft should explicitly call out idempotence guards for query-param writes.

5. **Startlist/team matching privacy & harassment considerations.** Security mentions “public startlists”, but showing teammate names can still be socially sensitive (e.g., revealing attendance). A mitigation could be: default to showing counts on cards with an opt-in toggle to show names, or only show names after expanding.

### Missing Edge Cases

1. **Series with multiple upcoming dates.** Many series can have multiple future editions; the feed should clearly define “upcoming_date” as “next upcoming” and handle “two races this month” without implying the series is a single event.

2. **Stage races / multi-day events.** Countdown rules (FO-05) and month grouping (FO-06) need to clarify: use start date? show date range? how to group if it spans months?

3. **Missing/partial course data.** The Tier 2 loader tries to parse JSON and “pass” on errors, but UX needs a consistent fallback:
   - missing profile_json,
   - climbs_json present but malformed,
   - distance/gain unknown,
   - course_type unknown.

4. **No upcoming races.** What does the agenda view show when there are zero upcoming items after filters? The DoD should require an explicit empty state (and not fall back to “Past Races” as the only content).

5. **Filter combinations that yield zero results.** Similar to above, but specifically: search + discipline + state can easily hit zero; you want a “clear filters” affordance.

6. **Timezone boundary for “Today/Tomorrow”.** If race dates are naive dates this may be fine, but you should specify whether “today” is local timezone, UTC, or event-local (and be consistent).

### Definition of Done Completeness

The DoD is strong, but it still leaves a few “acceptance traps”:

1. **PF-01 “≤6 queries” needs a testable measurement contract.** For example: “assert SQLAlchemy executed statements count via event listener in a unit/integration test”. Otherwise this becomes subjective.

2. **PF-04 precompute needs runtime constraints.** “precompute_all runs after scrape” is not enough; add: “for current dataset, precompute_all completes within X minutes” or “supports incremental per-series compute”.

3. **FO-08 should be reframed into measurable UI criteria.** Replace “4–5 cards visible” with “collapsed card shows exactly N lines” (or “collapsed card height ≤ X px on standard desktop viewport”) plus a screenshot in the PR description.

4. **DD-02 ‘race context narrative’ needs a truth constraint.** Ensure the narrative does not imply certainty (“this is where the field splits”) unless backed by historical evidence; otherwise it’s a trust risk for beginner users.

### Under-specified or Missing Use Cases (vs original)

Most use cases are present, but a few are under-specified in implementation terms:

1. **DD-05 (historical finish type visualization):** The draft proposes a timeline of icons, but doesn’t define the source of truth for “finish type per year” (existing computation can be expensive and inconsistent). If Tier 2 still computes this per edition, it conflicts with PF goals unless precomputed.

2. **DD-06 (similar races):** The heuristic is outlined, but success criteria are missing: what constitutes a “good” match, how to avoid obvious junk (same course_type but completely different discipline/region), and how to handle missing predictions/course fields.

3. **FO-01 (discipline) when inference fails:** Open Questions mention adding a column. The sprint should explicitly pick one approach for Sprint 011 and treat the other as follow-up; otherwise you risk building UI/filtering on unstable semantics.

---

## Gemini Draft Critique (`SPRINT-011-GEMINI-DRAFT.md`)

### Strengths

1. **Clear, concise framing.** The overview correctly describes the transformation (“list → decision engine”) and keeps the five themes aligned with the persona.

2. **Acknowledges Streamlit constraints.** It calls out the rerun model as a real consideration for “lazy loading”, and correctly points to caching as the practical mitigation.

3. **Calls out SQLite compatibility risk explicitly.** Noting window-function availability is useful because the “latest/upcoming per series” pattern often relies on them.

### Weaknesses

1. **Implementation detail is too thin for execution.** Most sections are intention-level (“massive rewrite”, “build CSS grid layout”) without enough specificity to prevent major design thrash in the first 1–2 days.

2. **Data model proposal is internally inconsistent.** The `SeriesPrediction` sketch sets `series_id` as `unique=True` while also including `category`; that would forbid per-category rows. Either remove uniqueness or define a composite unique constraint (`(series_id, category)`).

3. **DoD is broad and mixes unrelated acceptance criteria.** “Preview page contains functional hero profile, climb breakdown, team-grouped startlist, and similar races” is not precise enough to validate and doesn’t include degradation rules for missing data.

4. **Phase bundling increases risk.** Phase 2 combines FO and FG (feed container + card redesign) which is realistic from a UI perspective, but risky without the very detailed Tier 1/2 spec that Claude includes. The first time you implement “dense cards”, you’ll discover missing data and query needs.

### Gaps in Risk Analysis

1. **No explicit overscope risk.** The draft is still trying to deliver all 31 use cases, but it doesn’t include a “must-have vs stretch” line. Without that, you’ll burn time perfecting UI density while performance work is unfinished.

2. **No cache invalidation strategy.** It mentions caching but not how caches are busted after scrape/precompute or when schema changes.

3. **No risk called out for missing data.** Most of these use cases depend on optional data (course profiles, climbs, startlists, historical results). The draft doesn’t identify that as a top risk, despite it being the most common source of UI breakage.

4. **No widget/query-param rerun-loop risk.** Syncing multiple filters + team name to URL is a known Streamlit footgun; the draft doesn’t mention idempotence or guarding param writes.

### Missing Edge Cases

1. **No empty-state UX.** What happens when filters yield zero series, or there are zero upcoming races?

2. **Multi-upcoming editions, stage races, date ranges.** Same as for Claude’s draft, but Gemini’s draft doesn’t mention them at all.

3. **Team matching ambiguity.** It raises normalization, but doesn’t define behavior for:
   - “team” field missing,
   - multiple riders with same name,
   - substring false positives (e.g., “RAD” matches “Colorado”).

4. **Search input edge cases.** No mention of escaping, extremely long queries, or special characters.

### Definition of Done Completeness

The DoD is directionally correct but not implementer-proof. Missing:

1. **Query-count and performance measurement mechanism.** “3 or fewer SQL queries” needs to specify how to count (tests vs logging) and what queries “don’t count” (e.g., Streamlit’s own state reads, ancillary dropdown queries).

2. **Graceful degradation requirements.** For each FG item, require behavior when inputs are missing (distance/gain unknown, predicted finish type unknown, no startlist, no historical results).

3. **Data correctness constraints for narrative/climb context.** Without guardrails, you risk generating confident-sounding text from weak signals.

4. **Test scope specificity.** “Covered by pytest fixtures” is vague; specify which new tests exist and what they assert (pagination, month grouping, countdown rules, discipline derivation, teammate matching).

### Under-specified or Missing Use Cases (vs original)

All use case IDs are listed, but several are not specified enough to implement faithfully:

1. **FG-08 (priority-ordered layout):** The draft says “CSS grid layout” but doesn’t specify the exact content ordering/rows described in the original use cases (header + quick-scan row + “how it plays out” row, etc.). Without that, you can satisfy FG-08 while still violating the persona ordering.

2. **FO-07 (de-emphasize next race):** It states “remove auto-expanded Racing Soon”, but doesn’t address the follow-on: what replaces it (countdown + month grouping) and how the default view behaves for users who previously relied on the “soon” bucket.

3. **DD-05 (finish type pattern visualization):** It’s referenced, but the data source and UI representation are not defined (icons? bar? sequence?).

---

## Cross-Draft Recommendations

1. **Use Claude as the execution backbone, but tighten the “batch query” to be truly batch.** Keep the Tier 1/2 split, caching, and DoD structure, but ensure PF-01 is implemented as “fetch the minimum rows” rather than “fetch everything then group”.

2. **Make “missing data” a first-class acceptance criterion.** Add explicit empty-state + graceful-degradation sections to DoD for both feed and preview. Most user-facing failures will be absent startlists / absent course profiles / absent historical results.

3. **Pick one discipline strategy for Sprint 011.** Either:
   - infer discipline from race_type for now (and accept UNKNOWN), or
   - add a `RaceSeries.discipline` column + backfill.
   Don’t leave both half-done, because FO-01 correctness depends on it.

4. **Define measurement contracts.** For PF budgets and query counts, decide “how we will know” (automated tests + logged metrics) so performance doesn’t regress silently after the sprint.

5. **Guard narrative truthfulness.** For DD-02/DD-04 narrative expansions, require “hedged language” unless backed by sufficient historical evidence (and consider surfacing the evidence count to build trust).

