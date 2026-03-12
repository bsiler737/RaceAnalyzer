# Sprint 011 Critique: Codex Draft & Gemini Draft

This critique evaluates the two Sprint 011 drafts against the intent document (`SPRINT-011-INTENT.md`), the original use cases (`USE_CASES_FEED_FIRST_GLANCE.md`), and the actual codebase state after Sprint 010.

---

## Codex Draft Critique

### Strengths

1. **Exceptional technical depth.** The Codex draft provides concrete SQL (window functions, CTEs), SQLAlchemy implementation sketches, data contract dataclasses (`FeedCardSummary`, `FeedCardDetail`, `FeedFilters`), and function signatures for nearly every feature. This is the most implementation-ready draft — a developer could start coding from it directly.

2. **Accurate codebase observation.** The "Current implementation snapshot" section correctly identifies the actual module paths (`raceanalyzer/db/models.py` vs the nonexistent `raceanalyzer/models.py`), the expander-based feed loop, and the N+1 structure of `get_feed_items()`. This grounding in reality reduces the risk of designing against an imagined codebase.

3. **Discipline derivation is well-designed.** The two-step approach (Step A: derive at query time with no schema change; Step B: optionally persist to `RaceSeries.discipline`) is pragmatic. It delivers immediate value without requiring a migration, while leaving the door open for optimization.

4. **Batch SQL patterns are concrete and correct.** The window-function approach for "upcoming race per series" and "most recent race per series" is the right pattern for SQLite. The explicit SQLAlchemy sketch showing the JOIN structure gives high confidence that this will actually work.

5. **Tiered data model is well-articulated.** The Tier 1 (summary, always loaded) vs Tier 2 (detail, on demand) split is clean, with clear boundaries. The `FeedCardSummary` and `FeedCardDetail` dataclasses make the contract explicit.

6. **Security section is thorough.** Identifies XSS risk from `unsafe_allow_html=True` with user-provided strings (team name, location), URL privacy leakage of team names, and local prefs file sensitivity. These are real concerns that the Gemini draft mostly ignores.

7. **Open questions are well-chosen.** Each question represents a genuine architectural decision point (discipline storage, prediction granularity, team privacy, field size definition, feed default view). These are the right things to be uncertain about.

### Weaknesses

1. **Phase ordering is suboptimal.** The draft puts the card UI redesign (Phase 1) before filtering (Phase 2) and before the performance overhaul (Phase 5). But Sprint 010's N+1 query problem means the current feed is slow — building a new card layout on top of a slow data layer means every manual verification cycle during development takes multiple seconds. The intent document and the Claude draft both correctly identify performance as a prerequisite. Recommendation: performance and query restructuring should be Phase 1, not Phase 5.

2. **Phase 0 is underpowered.** "Guardrails, definitions, and instrumentation" contains only a countdown formatter and a query counter. This is fine as groundwork but doesn't address the most critical Phase 0 need: **validating the `st.container(border=True)` card pattern** actually works in Streamlit with acceptable density. The draft proposes moving away from `st.expander` (a correct decision) but doesn't spike this UI pattern change before committing 5 phases to it. If `st.container` cards don't achieve the target density of 4-5 visible cards, the entire feed redesign premise is undermined.

3. **Missing migration strategy detail.** The draft correctly identifies schema migration as a risk and mentions a "lightweight SQLite schema migration utility" but doesn't specify what this looks like. `Base.metadata.create_all()` won't add columns to existing tables or create tables that conflict with existing ones. The draft should specify: (a) are we using `ALTER TABLE ADD COLUMN` directly? (b) is there a "drop and recreate" workflow for dev? (c) how does this interact with existing user databases?

4. **Team name normalization is under-specified.** The draft provides `normalize_team_name(name: str) -> str` but doesn't define the normalization rules. Real-world team names from BikeReg/road-results are messy: "Team Rapha", "Rapha Racing", "Rapha", "RAPHA CYCLING p/b WAHOO" could all be the same team. The open question about "exact match vs fuzzy" is acknowledged but not resolved. Given that false negatives (missing your teammate) are worse than false positives (showing a stranger), the draft should at least specify a baseline: lowercased substring match, or token overlap, with test cases.

5. **The `FeedCardSummary` dataclass may be premature.** Introducing frozen dataclasses as the contract between query and UI layers is clean in theory, but the existing codebase uses plain dicts throughout (`get_feed_items()` returns `list[dict]`). Converting to dataclasses means changing every consumer. The draft should acknowledge this migration cost or justify why dicts aren't sufficient (they serialize naturally for caching, for instance).

6. **Precompute CLI command creates an operational burden.** The `compute-predictions` command must be run after every scrape. The draft doesn't specify how this is integrated into the scraping workflow — is it called automatically? Is there a check that warns if predictions are stale? If a user runs the app after scraping but forgets `compute-predictions`, the feed shows stale data silently. This needs a staleness check or automatic trigger.

7. **FO-08 (card density) lacks concrete verification criteria.** "At least 4 cards fit in a typical laptop viewport (qualitative check)" is vague. What viewport height? What font size? The Streamlit default theme has significant padding that may make 4 compact cards tight on a 768px viewport. The draft should specify a target card height (e.g., ~150px including padding) and whether CSS customization is in scope.

### Gaps in Risk Analysis

- **No mention of Streamlit rerun cost for filter changes.** Every sidebar filter change triggers a full script rerun. With 4+ filter widgets (discipline, race type, state, category, search), rapid filter changes could feel sluggish even with cached data. The draft should mention this and note that warm-cache performance (<200ms) mitigates it.
- **No risk around discipline derivation accuracy.** The keyword-matching approach for CX/MTB/track could produce false positives (a road race called "Mountain View Road Race" misclassified as MTB). The draft should note this and suggest validation against the actual dataset.
- **No discussion of backward compatibility with Sprint 010 deep links.** Sprint 010 established URL patterns (`?series_id=`, `?category=`). The new filters add `?disc=`, `?type=`, `?state=`, `?team=`. The draft should confirm that existing bookmarked URLs still work.

### Missing Edge Cases

- What happens when a series has an upcoming race but no course data? The card should render without the course one-liner, but this isn't stated explicitly in the Phase 1 exit criteria.
- What happens when `series_predictions` has no row for a series? Graceful degradation is mentioned in conventions but not in the precompute section.
- What if all visible series are in the same month? The month header should still render (not be hidden as redundant).
- Similar races (DD-06): what if there are fewer than 3 candidates? Show what's available, or hide the section?

### Definition of Done Completeness

The DoD covers FG, FO, MT, DD, PF, and Quality — which is comprehensive. However:

- **FG-03 (course character one-liner)** is not explicitly called out in the DoD despite being a P1 use case. The "quick-scan row" mention covers it implicitly, but "distance + gain visible on card" should be an explicit checkbox.
- **FG-07 (race type icon/label)** is missing from the DoD entirely. It's listed as a use case but has no corresponding Done criterion.
- **PF-04 (precompute predictions)** DoD says "predictions are precomputed" but doesn't specify: is the CLI command documented? Is there a staleness warning?
- **DD-04 (expanded racer type description)** is not explicitly in the DoD's DD section. "What kind of racer does well here" expanded paragraph is a distinct use case from the one-liner already on the card.

---

## Gemini Draft Critique

### Strengths

1. **Clear, well-organized overview.** The five-theme summary at the top is the most readable of any draft. A stakeholder could understand the sprint's scope in 30 seconds.

2. **Correct phase ordering.** Performance (Phase 1) comes before UI (Phase 2) and personalization (Phase 3). This is the right dependency order — you need the batch-loaded data structure before you can build the card layout on top of it, and you need the card layout before you can add teammate badges.

3. **Pragmatic decisions on open questions.** The "Similar Races Algorithm" and "Team Name Normalization" open questions include explicit decisions: "Start with the basic heuristic for Phase 3, iterate later" and "Start with case-insensitive substring matching." These decisions are reasonable and prevent analysis paralysis.

4. **Discipline modeling is complete.** Proposes adding `discipline` directly to `RaceSeries` as a column, which is simpler and faster to query than deriving at runtime. The Codex draft hedges with a two-step approach; Gemini just commits to the schema change.

5. **Acknowledges Streamlit's rerun model as a risk.** The risk about expander state collapsing on rerun during lazy-load is specific and real. This shows understanding of Streamlit's execution model.

### Weaknesses

1. **Severely under-specified technically.** The draft reads like a project manager's summary, not an engineering specification. Compare the query layer sections: Codex provides 80+ lines of SQL and SQLAlchemy code; Gemini says "Overhaul `get_feed_items` to accept `limit` and `offset`" in one sentence. A developer implementing from the Gemini draft would need to design the entire query architecture from scratch.

2. **Only 3 phases for 31 use cases is too coarse.** Phase 2 alone covers 16 use cases (all FG + all FO). This makes it impossible to ship incrementally within the phase — if any FO use case is blocked, all FG use cases are also blocked because they're in the same phase. The Codex draft's 6 phases (0-5) provide much better granularity for incremental delivery.

3. **Architecture section is shallow.** Three subsections (Data Modeling, Query Layer, Personalization State) at ~5 sentences each. Missing entirely: tiered data model, caching key design, batch SQL patterns, discipline derivation logic, similar-race scoring algorithm, precompute pipeline details, countdown label rules. These are all implementation-critical.

4. **"CSS grid layout" is not available in Streamlit.** Phase 2 says "Build a new CSS grid layout for collapsed feed cards." Streamlit does not expose CSS Grid to users — layout is controlled via `st.columns`, `st.container`, and limited `st.markdown` with `unsafe_allow_html=True`. A CSS grid approach would require injecting raw HTML/CSS, which is fragile and breaks on Streamlit updates. This reveals a gap in understanding the rendering framework.

5. **Personalization via "local browser storage via a lightweight Streamlit component"** is incorrect. Streamlit components are JS-based custom widgets that require `npm build` and a separate package. This is not lightweight — it's a dependency. The Codex draft's approach (local JSON file or URL params) is far simpler and more appropriate for "no new dependencies."

6. **`SeriesPrediction` has `unique=True` on `series_id` but also a `category` column.** If predictions are per-category (as the use cases require — different categories have different finish patterns), then `series_id` cannot be unique. The constraint should be `UniqueConstraint('series_id', 'category')`. This is a schema design bug.

7. **Files summary references `raceanalyzer/ui/pages/preview.py`** but the actual file is `raceanalyzer/ui/pages/race_preview.py`. Small but symptomatic of insufficient codebase grounding.

8. **No function signatures or data contracts.** The draft proposes no dataclasses, no typed dicts, no function signatures beyond the table of files. This makes it impossible to validate the design against the use cases without implementing it first.

### Gaps in Risk Analysis

- **No mention of schema migration.** The draft adds a `SeriesPrediction` table and a `discipline` column to `RaceSeries` but doesn't discuss how to apply these changes to existing databases. `Base.metadata.create_all()` will create the new table but will NOT add the `discipline` column to an existing `race_series` table. This is a hard blocker that the risk section completely misses.
- **No mention of `unsafe_allow_html` XSS risk.** If badges or team names are rendered via raw HTML (which the CSS grid approach implies), user-provided strings could inject HTML. Not mentioned.
- **No mention of performance budget enforcement mechanism.** The DoD says "<1.0s cold cache" but the draft doesn't describe how this is measured or enforced (logging? test assertions? manual timing?).
- **No mention of data completeness risks.** What happens when a series has no course data, no startlists, no predictions? The use case doc emphasizes graceful degradation, but the Gemini draft doesn't address it anywhere.
- **No discussion of `ILIKE` on SQLite.** The team name normalization decision says "ILIKE %user_input%", but SQLite's `LIKE` is case-insensitive for ASCII only. Non-ASCII team names (accented characters) would fail to match. Should use Python-side normalization or `COLLATE NOCASE`.

### Missing Edge Cases

- What happens when the user enters a team name that matches every team? (e.g., single letter "T"). This would produce false-positive teammate badges everywhere.
- What happens when `days_until_str` is called for a race that was yesterday? (Race date just passed, feed hasn't refreshed.) Should show "Yesterday" or be filtered out?
- Multiple upcoming races for the same series — which date is shown in the card header?
- Series with editions spanning multiple disciplines (a race that was road one year and gravel the next).
- Pagination edge: user is on page 3, applies a new filter, total results drop to 1 page — does the UI reset to page 1?

### Definition of Done Completeness

The DoD has 6 items, which is concise but incomplete:

- **MT-02 (specific teammate names)** is not in the DoD. Item 4 says "highlights races where teammates are registered" but doesn't specify that individual names should appear (1-2 names shown, 3+ shows count).
- **FG-03 (course character one-liner)** — no DoD item mentions distance or elevation gain on the card.
- **FG-05 (field size)** — not mentioned in any DoD item.
- **FG-06 (drop rate label emphasis)** — not mentioned.
- **FG-07 (race type icon/label)** — not mentioned.
- **DD-02 through DD-07** are collapsed into "functional hero course profile, climb breakdown, team-grouped startlist, and similar race recommendations" — but DD-04 (expanded racer type description) and DD-05 (finish type pattern visualization) are omitted.
- **FO-04 (persistent preferences)** says "persist in the URL" but the use case also requires persistence across sessions (when the user opens the app fresh, without a bookmarked URL). The DoD only mentions URL persistence.
- **PF-03 (lazy loading)** — not mentioned in the DoD at all.
- **PF-05 (query-layer pagination)** — not mentioned.

---

## Cross-Draft Comparison

### Phase Ordering

| Aspect | Codex | Gemini | Recommendation |
|--------|-------|--------|----------------|
| Performance phase | Phase 5 (last) | Phase 1 (first) | **Gemini is correct.** Performance must come first — it restructures the data layer that everything else depends on. |
| Filter + org phase | Phase 2 | Phase 2 | Agreement. |
| Card redesign | Phase 1 | Phase 2 (combined with FO) | Codex's separation of card layout from filters is better for incremental delivery. |
| My Team | Phase 3 | Phase 3 | Agreement. |
| Detail Dive | Phase 4 | Phase 3 (combined with MT) | Codex's separation is better — DD has 7 use cases and deserves its own phase. |

### Technical Depth

Codex provides 5-10x more implementation detail. For a sprint of this scope (31 use cases), this level of detail is necessary to avoid discovering design problems during implementation. Gemini's brevity would require a separate design phase before coding begins.

### Scope Management

Both drafts attempt all 31 use cases in a single sprint, which the intent document flags as a scope risk. Neither draft proposes a concrete cut line — "if we run out of time, cut these P2 use cases." The intent document's open question #1 asks whether this should be split into 2-3 sprints. Both drafts answer "no" implicitly by including everything. A more realistic approach: commit to P0 use cases (14 items) as the sprint scope, with P1 (12 items) as stretch goals and P2 (5 items) deferred to Sprint 012.

### Use Cases Under-Specified or Missing

Both drafts under-specify these use cases from the original document:

1. **FG-08 (card layout reorder)** — Both drafts describe a layout but neither provides a concrete pixel/line budget or validates against Streamlit's actual rendering. The use case says "Row 1 — Quick-scan badges" but Streamlit columns have minimum widths that may not accommodate 4-5 badges in a single row on mobile or narrow viewports.

2. **FO-04 (persistent preferences)** — The use case says "remembers them across sessions." URL params only persist if the user bookmarks the URL. Neither draft fully solves cross-session persistence without cookies or local file storage. Codex mentions `data/user_prefs.json` which is better, but the interaction between URL params and file-based prefs (which takes precedence?) is unresolved.

3. **DD-07 (course map with race features)** — Both drafts mention it exists from Sprint 008 but neither specifies what "race features" (climb markers, sprint points) need to be added. The use case says "major climbs highlighted on the route, and sprint points." Sprint 008's map doesn't have these markers. This is net-new work that both drafts treat as already done.

4. **PF-06 (performance budget)** — Both drafts mention <1s cold / <200ms warm but neither specifies: what dataset size? The intent says "50+ series" but the actual dataset may be larger. How is this measured in CI? Is it a hard test failure or a log warning?

---

## Recommendations for the Final Sprint Document

1. **Adopt Gemini's phase ordering** (performance first) **with Codex's phase granularity** (5-6 phases, not 3).

2. **Use Codex's technical detail** for the query layer, data contracts, and SQL patterns. Discard Gemini's shallow architecture section.

3. **Add a concrete cut line.** P0 use cases are the committed scope. P1 is stretch. P2 is deferred. This makes the sprint achievable.

4. **Spike the card layout early.** Before committing to `st.container(border=True)` or any other pattern, build a single prototype card with all FG fields and verify it meets the density target. This is a 1-hour task that de-risks the entire sprint.

5. **Specify the migration strategy.** Choose one: (a) `ALTER TABLE` statements in a migration script, (b) "delete and recreate DB" for dev with a documented workflow, or (c) conditional `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ADD COLUMN` wrapped in try/except for robustness.

6. **Define team name normalization rules** with test cases. At minimum: case-insensitive, strip leading/trailing whitespace, strip common suffixes ("Racing", "Cycling", "p/b ..."). Provide 5-6 test pairs from real BikeReg data.

7. **Add explicit graceful degradation criteria** to the DoD: "Cards render correctly when any of {course data, startlists, predictions, climb data} are missing."

8. **Fix the `SeriesPrediction` schema** to use a composite unique constraint on `(series_id, category)`, not `unique=True` on `series_id` alone.

9. **Integrate `compute-predictions` into the scrape workflow** or add a staleness check at feed render time that warns when predictions are older than the latest race result.

10. **Don't use CSS Grid or browser localStorage components.** Stick to Streamlit's native layout primitives (`st.columns`, `st.container`, `st.metric`) and file-based persistence for user preferences.
