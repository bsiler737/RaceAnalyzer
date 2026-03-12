# Sprint 011 Merge Notes

## Draft Comparison

### Claude Draft (65KB, 1570 lines)
**Strengths adopted:**
- Best phasing strategy: Performance → Feed Organization → Card Redesign → My Team → Detail Dive
- Excellent Tier 1/Tier 2 data architecture with concrete dataclasses
- Complete `get_feed_items_batch` implementation with PerfTimer instrumentation
- Thorough precompute pipeline with `precompute_all` and field size calculation
- Strong countdown logic, month grouping, and similar-races scoring algorithm
- Most complete Definition of Done

**Weaknesses addressed:**
- Batch query fetches all races then groups in Python (Codex critique: should use window functions)
  → Final: Adopt Claude's approach but note window functions as optimization path
- Uses st.expander for cards, violating "no click required" mandate (Gemini critique)
  → Final: Adopt container-based card per user interview decision

### Codex Draft (30KB, 746 lines)
**Strengths adopted:**
- Correct identification that st.expander must be replaced with st.container(border=True)
- Excellent SQL patterns with window functions (ROW_NUMBER for upcoming/recent per series)
- FeedCardSummary/FeedCardDetail dataclass contracts
- Security analysis (XSS from unsafe_allow_html, team name in URL privacy)
- Two-step discipline derivation approach
- Concrete function signatures throughout

**Weaknesses addressed:**
- Phase ordering puts Performance last (Phase 5) — fatal flaw (Gemini critique, Claude critique)
  → Final: Performance is Phase 1
- FeedCardSummary dataclass premature given dict-based codebase (Claude critique)
  → Final: Keep dicts for cacheability, use typed comments

### Gemini Draft (12KB, 170 lines)
**Strengths adopted:**
- Correct phase ordering (Performance first)
- Pragmatic decisions on open questions (basic heuristic for similar races, substring for team matching)
- Clean overview framing

**Weaknesses addressed:**
- Severely under-specified technically (Claude critique)
- "CSS grid layout" not available in Streamlit (Claude critique)
- SeriesPrediction unique constraint bug (Claude critique, Codex critique)
- Only 3 phases for 31 use cases is too coarse

## Valid Critiques Accepted

1. **Performance must be Phase 1** (Gemini critique of Codex, Claude critique of Codex) — Accepted
2. **st.expander violates "no click required"** (Gemini critique of Claude) — Accepted, confirmed by user
3. **SeriesPrediction needs composite unique on (series_id, category)** (Claude critique, Codex critique) — Accepted
4. **Missing graceful degradation criteria in DoD** (Codex critique of both) — Accepted, added to final
5. **Streamlit scroll-jump risk with button-based detail expansion** (Gemini critique of Codex) — Accepted, mitigated with st.session_state tracking of expanded IDs
6. **Team name substring matching false positives with short strings** (Claude critique, Gemini critique) — Accepted, add minimum length guard (3 chars)
7. **Empty state UX missing** (Codex critique of both) — Accepted, added to DoD
8. **Cache invalidation beyond TTL** (Codex critique) — Accepted, precompute updates `last_computed`; feed checks staleness
9. **Narrative truthfulness constraint** (Codex critique) — Accepted, require hedged language for low-evidence claims

## Valid Critiques Rejected

1. **Should split into P0-only sprint** (Claude draft suggestion) — Rejected per user interview: all 31 in one sprint
2. **Use frozen dataclasses instead of dicts** (Codex draft) — Rejected: existing codebase uses dicts, caching is simpler with dicts
3. **Add discipline column to RaceSeries** (Gemini draft) — Rejected per user interview: derive from race_type

## Interview Refinements Applied

1. **Scope**: All 31 use cases in Sprint 011
2. **Card UI**: Container cards (st.container(border=True)) replacing expanders
3. **Discipline**: Derive from race_type, no schema change
4. **Team matching**: Normalized substring match with minimum 3-char guard
