# Sprint 007 Merge Notes

## Draft Strengths

### Claude Draft
- Most thorough implementation detail — nearly copy-paste-ready function signatures
- Graceful degradation deeply embedded at every layer
- Track points fallback fully implemented with multiple RWGPS field format handling
- UserLabel model with predicted + actual + is_correct + session_id dedup
- `is_upcoming` and `registration_url` columns on Race model (simple, avoids new table)
- Configurable terrain thresholds via Settings class
- Course model with dual FK (series_id + race_id) — most flexible

### Codex Draft
- Scope Ladder (Must/Should/Nice-to-Have) is the best scope management tool
- Clean data flow diagram showing the full pipeline
- Predictions in separate module from classification — correct separation of concerns
- Concrete confidence model (edition count + plurality thresholds)
- "No new dependencies" constraint
- Mobile-first design rules are specific (375px, card-based, single-column)
- Open question about demo data mix (consistent + variable series)

### Gemini Draft
- Concise phase structure, easy to skim
- Correct BikeReg rate limiting specification
- Security section identifies the right concerns
- "No new ML libraries" guardrail

## Valid Critiques Accepted

1. **Codex on Claude**: Phase 3 is overloaded (35% with 3 features). **Accepted** — split prediction from external integrations in the final doc.
2. **Codex on Claude**: `posterior_mu`/`posterior_sigma` naming deviates from spec. **Accepted** — use `mu`/`sigma` as specified in mid-plan-improvements.md.
3. **Claude on Codex**: Startlist FK should be `race_id` not `series_id`. **Accepted** — riders register for specific race editions.
4. **Claude on Codex**: Missing UserLabel uniqueness constraint. **Accepted** — add `UniqueConstraint("race_id", "category", "session_id")`.
5. **Both on Gemini**: Not enough implementation detail. **Accepted** — final doc will include full function signatures from Claude/Codex.
6. **Both on Gemini**: No scope management or explicit cut list. **Accepted** — include Codex's scope ladder (adapted per user's "ship all 6" instruction).
7. **Gemini on Codex**: Course model lacks flexibility for year-over-year changes. **Accepted** — use Claude's dual FK approach per user preference.

## Valid Critiques Rejected

1. **Codex on Claude**: Course model stores too many fields (YAGNI). **Rejected** — user explicitly chose Rich model. Fields are free at scrape time, prevent re-scraping in Sprint 008.
2. **Codex on Claude**: Separate `calendar_feed.py` is premature. **Rejected** — keeping it separate follows the one-module-per-source pattern established by `rwgps.py`.
3. **Claude on Codex**: Missing track_points fallback code. **Partially rejected** — Codex mentions it as risk mitigation; final doc will include Claude's full implementation.

## Interview Refinements

- **All 6 deliverables ship** — no scope cuts. Codex's scope ladder retained as "if time runs short" guidance but all tiers are targeted.
- **Rich Course model** with 7 elevation fields and dual FK (series_id + race_id)
- **Standalone Race Preview page** with shareable URLs
- **User feedback prompt** ("Was this prediction right?") included in Sprint 007

## Merge Strategy

- **Architecture**: Claude's module structure (elevation.py, prediction.py, startlist.py, calendar_feed.py) + Codex's separation of prediction from classification
- **Schema**: Claude's rich Course model, Claude's UserLabel with session dedup, corrected Startlist with `race_id` FK, Codex's `mu`/`sigma` naming on Result
- **Implementation**: Claude's detailed function signatures, Codex's phase split (separate prediction from external integrations), Codex's effort allocation
- **Scope**: Codex's scope ladder (adapted: all tiers are targeted, ladder is contingency only)
- **UI**: Codex's mobile-first design rules + Claude's card layout patterns
- **Testing**: Claude's test coverage detail, Codex's "beats random baseline" criterion
- **Risk**: Union of all three risk tables with Codex's BikeReg cut guidance
