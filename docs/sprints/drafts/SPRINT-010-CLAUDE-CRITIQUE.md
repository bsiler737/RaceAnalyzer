# Sprint 010 Draft Critiques

## Codex Draft Critique

### Strengths

1. **Non-destructive architecture is the right call.** The decision to create a new `feed.py` page rather than gutting `calendar.py` is well-reasoned and explicitly justified. The existing pages become fallbacks, which de-risks the entire sprint. If the feed ships half-baked, nothing is broken.

2. **Unusually detailed technical specificity.** The draft provides concrete code sketches for session state initialization, the `get_feed_items()` return shape, the `st.expander` pattern, sparkline downsampling, plain-English finish types, racer type descriptions, and duration calculation. This is the level of detail that prevents ambiguity during implementation. The `RACER_TYPE_DESCRIPTIONS` lookup table (mapping course_type x finish_type to a sentence) is a smart, cheap approach to UC-10.

3. **Strong scoping discipline.** The deferred use cases are explicitly justified with a clear principle: "this sprint is about reorganizing and surfacing existing data, not computing new derived data." UC-25 (field strength), UC-26 (rider types), UC-33 (course comparison), UC-37 (side-by-side), and UC-38 (season calendar) are all correctly identified as requiring new algorithms or UI paradigms. The intent document's Open Question #3 asked which "good" use cases to cut -- Codex answers this decisively.

4. **Phase effort percentages are realistic.** 30/25/25/20 across four phases, with the heaviest lift on the feed foundation. This matches the actual work distribution -- the feed query and page skeleton are the riskiest and most effort-intensive pieces.

5. **Edge case coverage is thorough.** Phase 4 explicitly lists five distinct empty states (no races, no upcoming, empty search, no course data, no historical data) with specific UI text for each. The intent document flagged these in the Verification Strategy section, and Codex addresses all of them.

6. **Security section is concrete.** It specifically addresses the search input (parameterized SQLAlchemy `ilike`, not raw SQL) and query param validation (integer parse, membership check). This is more than boilerplate.

7. **Open questions are genuinely open.** Questions like single-column vs. two-column layout, narrative sentence count, and preload vs. lazy-load are real design decisions that need to be resolved during implementation, not upfront. The draft provides a recommendation for each but doesn't over-commit.

### Weaknesses

1. **UC-25 (field strength) is deferred, but the intent document rates it "good" and the persona cares about it.** The justification ("algorithm is undefined") is valid, but the draft doesn't propose even a minimal placeholder -- e.g., showing the count of registered riders or the median carried_points value without a "strong/average/weak" label. A raw number is better than nothing for a newer racer trying to gauge what they're walking into.

2. **UC-33 (course comparison) is deferred but rated "good."** Same issue: the draft correctly identifies that a similarity algorithm is needed, but doesn't propose a lightweight approximation. Even "Similar total climbing to [other series in the same course_type bucket]" would address the spirit of the use case without DTW or Euclidean distance.

3. **The `st.expander` approach has a significant UX limitation that is acknowledged but not fully addressed.** The draft notes that `st.expander` doesn't fire a callback on toggle, so a separate "More" button is needed inside the summary to control state. This means the native expand/collapse chevron does nothing useful -- the user sees a clickable chevron that expands/collapses the visual container, AND a "More" button that loads the detail content. These are two different interactions that look like they should be one. The draft mentions `st.container(border=True)` as a fallback but doesn't specify the decision criteria for switching. This should be resolved earlier (Phase 1 prototype), not discovered during Phase 3.

4. **The "This Weekend" filter is defined as "today to today+7 days" but the UC says "this weekend."** Seven days is a full week, not a weekend. For a Saturday race, checking on Monday would show it as "this weekend" even though the weekend is five days away. The filter should probably be "today through Sunday" (or next Monday), not a rolling 7-day window. This is a small detail but it affects user trust in the filter label.

5. **Pagination is deferred to Phase 4 but the fat query in Phase 1 loads all series.** If the database has 100+ series, Phase 1 through Phase 3 will render all of them on every page load. This could cause noticeable lag during development and testing. Pagination should be part of Phase 1 alongside the query, not a Phase 4 polish item.

6. **The file summary omits `predictions.py` test modifications.** The tasks mention adding `racer_type_description()` to `predictions.py` and testing it in `test_predictions.py`, but the Files Summary table doesn't list `test_predictions.py`. Minor but could lead to forgotten test coverage.

7. **No mention of scroll position preservation.** UC-50 mentions "scroll position," and the draft addresses category and series_id via query params, but scroll position in Streamlit is notoriously hard to control. The draft should explicitly call this out as a known limitation rather than silently dropping it.

### Gaps in Risk Analysis

1. **No risk entry for `st.expander` rendering all children eagerly.** Streamlit's `st.expander` renders its contents into the DOM even when collapsed (they're just hidden via CSS). If 20 feed items each contain an expander with a Plotly course profile and contender list, that's 20 heavy components rendered on page load even though only one is visible. The Gemini draft correctly flags this. The Codex draft's `@st.cache_data` mitigation addresses query cost but not rendering cost.

2. **No risk entry for Streamlit version compatibility.** The draft mentions `st.expander(expanded=...)` requiring Streamlit 1.28+, but the codebase doesn't pin a minimum Streamlit version in the risk table. If the deployment environment has an older version, the entire inline expansion approach fails. This should be a Phase 1 validation step.

3. **No risk around `st.rerun()` causing infinite loops or flickering.** The expansion pattern calls `st.rerun()` after setting session state. If there's a bug in the state logic (e.g., the rerun triggers another state change), this could cause an infinite rerun loop. This is a known Streamlit footgun that deserves a mitigation note.

### Missing Edge Cases

1. **Series with multiple upcoming races.** What if a series has both a March and an April edition? The draft assumes one upcoming race per series but doesn't specify how `get_feed_items()` handles this. Does it show the soonest? Both?

2. **Category filter with no matching races.** The draft covers "search returns nothing" but not "category filter returns nothing." If a user selects "Women Cat 3" and there are no upcoming races in that category, the feed should show a helpful message, not an empty page.

3. **Very long series names or narrative text.** No mention of truncation limits for the card layout. A series name like "Pacific Northwest Road Racing Association Championship Series" could break the card layout if not truncated.

4. **Races with a date in the past that was marked "upcoming" but has since occurred.** If the data pipeline hasn't been refreshed, stale "upcoming" races could appear at the top of the feed. The draft should specify whether the feed query filters on `race.date >= today` or trusts the data pipeline's classification.

### Definition of Done Completeness

The DoD is well-structured with four clear sections (Feed Experience, Inline Expansion, Search and Filtering, Backward Compatibility). Most criteria are testable. However:

- "Each feed card shows an elevation sparkline when course profile data exists" -- testable but no visual quality criterion. What if the sparkline is a flat line at zero because the profile data is corrupt?
- "Dormant series appear visually dimmed" -- not testable without a visual reference. What does "dimmed" mean? Lower opacity? Gray text? The implementation should specify a CSS value.
- Missing DoD item: "Feed loads within N seconds for a database with M series." There's no performance criterion despite the fat query risk.

### Scope Realism

The scope is realistic for 2-3 weeks. The draft includes 21 use cases across 4 phases, but the majority (Phases 1-2) are data reorganization and presentation, not new algorithms. The highest-risk item is the inline expansion pattern in Phase 3, which could eat time if `st.expander` doesn't behave as expected. The draft's fallback (`st.container` with conditional rendering) is a reasonable escape hatch. The 20% effort allocation for Phase 4 (polish, edge cases, persistence) is tight but achievable if Phases 1-3 don't overrun.

The one scope concern is UC-50 ("Remember where I left off") via URL query params. This is listed in Phase 4 but could be surprisingly fiddly -- Streamlit's `st.query_params` interacts poorly with `st.rerun()` in some versions, and encoding/decoding complex state into URLs is error-prone. If Phase 4 runs short, this should be the first item cut.

---

## Gemini Draft Critique

### Strengths

1. **Concise and readable.** At roughly one-third the length of the Codex draft, the Gemini draft is easy to scan and understand quickly. The use case groupings (A through H) map directly to the source document, making it easy to trace coverage.

2. **Correctly identifies the lazy-loading risk.** The open question about `st.expander` eagerly rendering nested Plotly/Leaflet charts is a genuine technical risk that the Codex draft misses. This is arguably the most important performance consideration for the feed page -- if 20 expanders each render a course profile, the page will be unusably slow.

3. **Proposes an interesting deep-link alternative.** The suggestion to "isolate the race at the top of the feed" instead of scrolling to it is a practical Streamlit-compatible approach. Scroll position control in Streamlit is limited, so filtering the feed to show only the deep-linked race (with a "Show all" button to return to the full feed) could be simpler to implement and less janky.

4. **Correct to include UC-25, UC-26, UC-28 in scope.** These are all rated "good" by the user. The Codex draft defers all three, but at least UC-25 (field strength) is important to the target persona. Including them signals awareness of what the user values.

### Weaknesses

1. **Critically underspecified across the board.** The draft reads like an outline, not a sprint plan. Compare the Architecture sections: Codex provides session state initialization code, query function signatures, expander patterns, and sparkline downsampling strategy. Gemini says "We will utilize Streamlit's `st.expander` (or session-state driven conditional rendering)." This "or" is doing enormous load-bearing work -- these are fundamentally different approaches with different tradeoffs, and the draft doesn't choose between them.

2. **The decision to modify `calendar.py` instead of creating a new page is risky and unjustified.** The draft says "The app will consolidate around `calendar.py` (repurposed as the 'Feed')." This means gutting the existing calendar page during development. If the feed is half-finished at any point, the app has no working landing page. The Codex draft's additive approach (new `feed.py`, keep `calendar.py` intact) is strictly safer. The Gemini draft doesn't acknowledge this risk at all.

3. **Includes UC-25 (field strength), UC-26 (contender rider types), and UC-28 (team representation) without defining how to implement them.** The intent document explicitly flags UC-25 in Open Question #6 as needing algorithm definition. UC-26 requires "inferring rider archetypes from result history" -- a classification system that doesn't exist in the codebase. UC-28 (team representation) requires parsing team affiliations from startlist data. Including all three without implementation details or effort estimates is how sprints blow up. The only mention of UC-25's undefined algorithm is buried in the Open Questions section at the very end.

4. **No new query functions are specified.** The draft mentions "Update query functions to support feed sorting, efficient bulk narrative loading, and search" but doesn't define what these functions look like, what they return, or how they differ from the existing `get_series_tiles()` and `get_race_preview()`. The feed's data requirements are fundamentally different from the existing calendar's tile data -- the draft doesn't grapple with this.

5. **Phase descriptions lack task-level detail.** Each phase is 3-5 bullet points with no file-level specificity, no effort estimates, and no acceptance criteria. Phase 2 says "Redesign the race card in `calendar.py` to include" five features, but doesn't specify which functions render them, where the data comes from, or how they're laid out. This is not actionable for implementation.

6. **No tests mentioned beyond "all existing tests pass."** The Definition of Done says nothing about new test coverage. The feed query, search filtering, sparkline downsampling, plain-English finish types, and field strength calculation all need tests. The Codex draft specifies test files and specific assertions for each phase. The Gemini draft's testing strategy is "don't break existing things."

7. **`race_preview.py` deprecation is hand-waved.** The draft says the file "may be deprecated or kept only for explicit deep-link routing." This ambiguity means the sprint could end with dead code, a half-migrated page, or broken deep links. The decision should be made upfront: keep it as a deep-link target (safe) or remove it (risky).

8. **No empty state handling.** The draft doesn't mention what happens when there are no upcoming races, no search results, no course data for a series, or no historical data. These are explicitly called out in the intent document's Verification Strategy section.

### Gaps in Risk Analysis

1. **Only two risks identified, and both are generic.** "Streamlit performance" and "data clutter" are real concerns, but the risk table misses:
   - The destructive refactoring risk of modifying `calendar.py` directly.
   - The scope risk of including UC-25/UC-26/UC-28 without defined algorithms.
   - The `st.rerun()` infinite loop risk.
   - The risk that `st.expander(expanded=...)` isn't available in the deployed Streamlit version.
   - The risk that narrative truncation cuts mid-sentence.

2. **No likelihood/impact assessment.** The Codex draft rates each risk by likelihood and impact. The Gemini draft provides narrative mitigations but no severity assessment, making it hard to prioritize which risks to address first.

3. **The `@st.fragment` suggestion in the performance mitigation is speculative.** `st.fragment` is a relatively new Streamlit feature and the draft doesn't verify whether it's available in the project's Streamlit version or whether it actually solves the eager rendering problem for expanders. This mitigation could be a dead end.

### Missing Edge Cases

1. **Everything the Codex draft covers in Phase 4 is missing here.** No mention of: series with no course data, series with no predictions, series with no upcoming edition, empty search results, very long series names, stale upcoming dates, races with multiple upcoming editions, or category filter yielding zero results.

2. **No consideration of how the "consolidated" calendar.py interacts with existing deep links.** If calendar.py is repurposed as the feed, do existing links/bookmarks to the calendar page still work? Do they now show the feed? Is that confusing?

3. **No discussion of how the persistent category filter interacts with pages that have their own category selectors.** The existing Race Preview, Series Detail, and Race Detail pages all have local category selectors. If the feed sets a global category in session state, what takes precedence on those pages?

### Definition of Done Completeness

The DoD has seven items, all at a high level. Key gaps:

- No criterion for inline expansion (the core UC-46 feature).
- No criterion for deep linking (UC-47).
- No criterion for "This Weekend" actually filtering correctly.
- No criterion for backward compatibility of individual pages (Race Preview, Series Detail, etc.).
- No performance criterion.
- No test coverage criterion beyond "existing tests pass."
- "Expanding a race card shows full preview details (map, contenders) without navigating to a new page" -- this is the only expansion criterion, and it doesn't specify the collapse behavior, the "only one card at a time" constraint, or what "full preview details" includes.

Compare to the Codex draft's DoD, which has 20+ specific checkable items across four categories. The Gemini DoD would not provide sufficient guidance for a reviewer to determine whether the sprint is actually done.

### Scope Realism

**The scope is not realistic for 2-3 weeks.** The draft includes UC-25 (field strength), UC-26 (contender rider types), and UC-28 (team representation) -- all of which require new algorithms or data parsing that doesn't exist in the codebase. UC-26 in particular requires building a rider classification system from scratch. These three use cases alone could consume an entire sprint.

Meanwhile, the core feed architecture (the actual hard part) is underspecified, which means implementation will surface design decisions that should have been made during planning. Underspecified plans almost always take longer than detailed ones because the implementer has to do the design work in real time.

The Gemini draft would benefit from either (a) cutting UC-25/UC-26/UC-28 and adding implementation detail for the remaining scope, or (b) defining concrete minimal implementations for those features (e.g., UC-25 = count of registered riders, UC-28 = team name frequency from startlist).

---

## Comparative Summary

| Dimension | Codex | Gemini |
|-----------|-------|--------|
| **Technical depth** | Excellent -- code sketches, function signatures, specific Streamlit patterns | Insufficient -- high-level bullets, no code, ambiguous "or" choices |
| **Scope discipline** | Strong -- 21 UCs with clear cut rationale | Overcommitted -- includes 3 UCs requiring undefined algorithms |
| **Risk analysis** | Good (7 risks with likelihood/impact) but misses eager rendering | Minimal (2 risks, no severity, speculative mitigations) |
| **Edge cases** | Thorough (5 explicit empty states, pagination) | Not addressed |
| **DoD** | 20+ specific, testable criteria | 7 high-level criteria, key features missing |
| **Test strategy** | Specific test files and assertions per phase | "Existing tests pass" only |
| **Architecture safety** | Non-destructive (new page, old pages preserved) | Destructive (gutting calendar.py) |
| **Readability** | Dense but navigable | Concise but underspecified |
| **Coverage of "good" UCs** | Defers UC-25/26/28/33 (some arguably too aggressively) | Includes UC-25/26/28 but without implementation plans |

**Overall assessment:** The Codex draft is substantially more implementable. Its main weakness is over-caution on UC-25 (field strength), which matters to the persona and could have a minimal implementation. The Gemini draft needs significant expansion before it could guide implementation -- in its current form, it is more of a vision statement than a sprint plan. The Gemini draft's inclusion of UC-25/26/28 is directionally correct but practically dangerous without algorithm definitions and effort estimates.
