# Sprint 005 Cross-Critique (Claude reviewing Codex and Gemini drafts)

## Codex Draft -- Review

### Strengths
- **Highest-confidence overall classification** is a genuinely better idea than plurality vote. A single Cat 3 BREAKAWAY classified at 0.9 is more informative than three MIXED classifications at 0.5. This captures "what we are most sure about" rather than "what happened most often," which is the right framing for a summary tile.
- **CSS Grid via `st.markdown` HTML injection** is architecturally superior to st.columns for tile layout. It gives real control over hover, click targets, and responsive breakpoints. The responsive media queries (3-col -> 2-col -> 1-col) are a nice touch.
- **Nominatim-first map strategy** is pragmatic. Every race has a location string, so geocoding always produces something. This eliminates the "no map" state for most races, unlike the BikeReg-first approach which only works when BikeReg has a linked RideWithGPS route (a minority of cases in practice).
- **Spacing algorithm as primary TT signal** (over keyword matching) is well-reasoned. The point about "Maryhill Loops" and "Mutual of Enumclaw" -- real PNW races that are TTs but have no TT keywords in the name -- is exactly the kind of edge case that justifies statistical detection.
- **Separate `maps.py` utility module** keeps map logic cleanly separated from UI components. Good separation of concerns.
- **Confidence returned as a tuple from `is_individual_tt()`** (returning `(bool, float)`) gives the caller more information than a bare boolean. The graded confidence (0.95/0.85/0.75) based on detection method is useful for debugging and for the overall classification logic.
- **`_compute_metrics` extraction** as a shared helper is cleaner than inlining metric computation in the TT branch.

### Weaknesses
- **`_estimate_confidence_from_metrics()` is a code smell.** Reconstructing confidence from stored metrics using a hardcoded lookup table is fragile and approximate. The draft acknowledges this ("Ideally the classifier would store its confidence score") but then builds the entire overall-classification query on top of this approximation. If the confidence reconstruction is wrong, every tile's overall classification is wrong. This should either be solved properly (add a `confidence` column to `race_classifications` as part of this sprint) or the fallback should be plurality vote.
- **Gap CV threshold of 0.8 is too loose.** The Claude draft uses 0.6, the Codex draft uses 0.8. In a GC-selective race where the field shatters into 15 groups of 2-3 riders each, the gap CV can easily be in the 0.6-0.8 range if the climbs are evenly spaced. The Codex draft's threshold would produce false positives in exactly these cases. The 0.6 threshold is more conservative and appropriate for a pre-check that short-circuits the entire classifier.
- **CSS Grid tile navigation is fragile in Streamlit.** The draft includes an `onclick` attribute with `window.parent.postMessage` which assumes Streamlit's iframe message passing interface. This is undocumented and could break across Streamlit versions. The draft does mention a `_handle_tile_click()` fallback via query params, but the primary mechanism is speculative. The Claude draft's approach (hidden st.button as the reliable path, JS as enhancement) is more defensive.
- **No mention of HTML escaping in `render_tile_grid()`.** The race name is escaped with `.replace("&", "&amp;").replace("<", "&lt;")` but the location string is inserted raw. A location like `O'Brien Park` would break the HTML attribute quoting. Need `html.escape()` on all dynamic strings.
- **Nominatim rate limiting is under-addressed.** The in-memory cache helps, but on a fresh app launch with 50 races, the calendar page would fire 50 geocoding requests in rapid succession. Nominatim's usage policy requires a maximum of 1 request per second. The implementation needs a rate limiter or should batch/pre-cache results.
- **No BikeReg scraping at all.** The draft intentionally defers BikeReg scraping, which is fine architecturally, but the sprint intent explicitly asks for "source real course maps from BikeReg/RideWithGPS where possible." Shipping without even attempting course-specific maps is an incomplete delivery.
- **`Settings()` instantiation inside `get_race_tiles()`** -- this appears without explanation. Is `Settings` already used elsewhere? It is constructed but never referenced in the function body. Looks like leftover code.
- **Test file is separate (`test_individual_tt.py`)** from the existing `test_finish_type.py`. Since the TT detection is an extension of the classifier, the tests belong in the existing test file to keep related tests together. Creating a new test file fragments the test suite unnecessarily.

### Gaps in Risk Analysis
- No risk identified for Nominatim Terms of Service compliance (they explicitly prohibit bulk geocoding without a custom server or commercial license for heavy use).
- No risk around the `_estimate_confidence_from_metrics` approximation being wrong for specific finish types -- what if a BREAKAWAY is estimated at 0.8 but the real classifier confidence was 0.6?
- No mention of the risk that existing `race_classifications` rows have no stored confidence, so re-running the classifier is needed to get accurate overall classifications. Without re-classification, the approximation is the only path.

### Definition of Done Gaps
- Missing: "BikeReg scraping attempts to find course-specific maps" -- this is in the sprint intent but not in the DoD.
- Missing: "Scraped URLs are validated against an allowlist of safe domains."
- Missing: "Toggle label shows the count of hidden UNKNOWN races" -- the Codex draft's calendar.py has this but the DoD does not specify it.
- The DoD specifies gap_cv < 0.8, which is different from the Claude draft's 0.6 and the Gemini draft's approach. This needs resolution before the sprint starts.

---

## Gemini Draft -- Review

### Strengths
- **Clear, structured Architecture section** with numbered layers (Data, Classification, Query, UI, Scraping). Easy to follow the impact of each change without reading code.
- **Coefficient of variation (CV) of finish times** as an additional statistical signal is interesting -- it measures the overall spread of times rather than just consecutive gaps. A TT has high CV of absolute times (riders are spread over minutes) while a bunch sprint has low CV (everyone finishes within seconds).
- **Security section** calls out URL validation for scraped links and responsible crawl rates. Good operational hygiene that the other drafts mention but Gemini makes it a first-class section.
- **Open Questions are direct and actionable**: the overall classification tiebreaker question and the interactive vs static fallback map question are both things that should be decided before implementation.
- **Use Cases are user-centric** ("As a user, I want...") and cover all the sprint intent requirements without over-specifying implementation details.
- **Concise implementation plan** -- does not over-specify code, leaving room for the implementer to make reasonable choices. This is a valid approach for a sprint plan (vs. the Claude and Codex drafts which provide full code).

### Weaknesses
- **Severely under-specified implementation.** The draft describes what to do but not how. For example, the ITT detection algorithm says "number of groups is high (> 0.7 * total_finishers)" and "CV is high (> 0.9)" but does not provide actual function signatures, threshold justification, or code. Compare to Claude and Codex drafts which provide complete, reviewable implementations. A developer picking up this sprint plan would need to make many design decisions that should have been settled in planning.
- **CV of finish times > 0.9 as a TT signal is wrong.** The coefficient of variation of absolute finish times in a TT is not reliably high. Consider a 10-mile TT where riders finish between 22 and 28 minutes: mean=25min, stdev=2min, CV=0.08. That is nowhere near 0.9. The CV of *consecutive gaps* (as Claude and Codex propose) is the right metric, not the CV of absolute times. This would cause the statistical detection to fail on real TT data.
- **"Most frequently occurring FinishType" (MODE()) for overall classification** has the same problem as Claude's plurality vote: it favors the most common type regardless of classification quality. A race with Cat 4/5 MIXED, Cat 4/5 MIXED, and Cat 3 BREAKAWAY would show MIXED even though BREAKAWAY is the more informative classification.
- **`title` attribute for tooltips** is the lowest-fidelity tooltip mechanism available. Native browser tooltips appear after a ~500ms delay, are unstyled (system font, no colors), and cannot contain any formatting. For a UI-focused sprint that aims to explain classification types to non-cyclists, this is inadequate. Even a CSS `::after` tooltip would be a significant improvement.
- **No test plan at all.** The DoD says "new unit tests for the ITT classification logic are added" but the draft provides zero test cases, no test structure, and no indication of what scenarios to test. Claude's draft has 6 specific test cases; Codex has 7. Gemini has none.
- **BikeReg scraping implementation is thin.** The function signature is provided (`get_course_map_url(bikereg_race_url)`) but there is no discussion of: how to find the BikeReg URL from the race data, what to do about Cloudflare/anti-bot protection, robots.txt compliance, or rate limiting. The "Feasibility: scraping is feasible but potentially brittle" note does not constitute a plan.
- **No mention of Streamlit version requirements.** `st.toggle` was added in Streamlit 1.28. `st.switch_page` was added in 1.30. Neither version is specified or checked.
- **No pagination.** The calendar page renders all tiles at once. With 50+ races, this could be slow, especially with map embeds or geocoding.
- **Files Summary is incomplete.** Does not mention the classification pipeline caller that needs updating to pass `race_name` and `race_type` to the classifier.

### Gaps in Risk Analysis
- Only three risks identified (BikeReg scraping, ITT accuracy, CSS customization). Missing: Nominatim/geocoding reliability, Streamlit iframe navigation issues, performance of rendering 50+ tiles, existing test breakage from enum changes.
- The "ITT Detection Accuracy (Medium)" risk does not discuss specific failure modes. What kinds of races would produce false positives? What about team time trials where riders finish in groups of 4-8?
- No mention of backward compatibility risk for the `classify_finish_type()` signature change.

### Definition of Done Gaps
- Missing: specific threshold values for the statistical ITT detection (the other drafts specify exact numbers).
- Missing: hover effects on tiles (mentioned in sprint intent but not in Gemini's DoD).
- Missing: tile clickability covering the full tile surface (Gemini's DoD says "single clickable link" but does not specify hover feedback).
- Missing: specific number of test cases expected.
- Missing: backward compatibility requirement for the classifier function signature.

---

## Head-to-Head: Key Decision Comparison

### TT Detection Algorithm
- **Best approach: Claude's three-signal OR logic with conservative thresholds.** Name keywords + race_type enum + statistical fingerprint. The OR logic means any single signal is sufficient, which is correct -- a race named "Time Trial" should be classified as ITT even if the statistics are noisy.
- **Codex** is similar but with a looser gap_cv threshold (0.8 vs Claude's 0.6). The 0.6 threshold is safer.
- **Gemini** proposes CV of absolute finish times, which is the wrong metric entirely. This needs to be corrected to CV of consecutive gaps.

### Overall Classification Strategy
- **Best approach: Codex's highest-confidence method**, but only if confidence is stored properly. The `_estimate_confidence_from_metrics` workaround undermines the whole approach. If we add a `confidence` column to `race_classifications` in this sprint (a small schema change), Codex's approach is clearly superior. Otherwise, Claude's plurality vote is more honest about what we actually know.

### Map Strategy
- **Best approach: Hybrid.** Use Codex's Nominatim geocoding as the universal fallback (every race gets at least a location pin) AND Claude's BikeReg scraping for course-specific maps as an enhancement layer. Neither draft alone is complete: Claude skips geocoding for the fallback (hardcoded PNW bounding box), Codex skips BikeReg scraping entirely.

### Tile Clickability
- **Best approach: Claude's hidden st.button with CSS enhancement.** The CSS Grid anchor approach (Codex) and the HTML `title` attribute approach (Gemini) both have Streamlit compatibility concerns. The hidden button is the most reliable Streamlit navigation mechanism; CSS injection provides the visual hover effects. This is the safest path.

### Tooltips
- **Best approach: Claude's approach (CSS class + title attr)**, with a future enhancement path to CSS-only styled tooltips. Native `title` is acceptable for v1 but the CSS class structure supports upgrading later. Gemini's bare `title` attribute works but looks cheap. Codex's tooltips are well-written but use the same `title` mechanism.

### Tooltip Content
- **Best approach: Codex's tooltip text.** The conversational analogies ("Think NASCAR but on bikes", "Like a breakaway in basketball but with more lycra") are more accessible to non-cyclists than Claude's racing-jargon explanations. Claude's text assumes the reader knows what "hold your line" and "the move" mean. Codex's text does not.

---

## Synthesis Recommendations

1. **Use Claude draft as the implementation base** -- it has the most complete, copy-paste-ready code with the most conservative thresholds.
2. **Adopt Codex's highest-confidence overall classification** but add a `confidence` column to `race_classifications` rather than reconstructing it. This is a one-column schema addition, not a migration headache.
3. **Adopt Codex's Nominatim geocoding for map fallback** instead of Claude's hardcoded PNW bounding box. Add it alongside BikeReg scraping (Claude's implementation), not instead of it.
4. **Use Claude's gap_cv < 0.6 threshold** for statistical TT detection. Codex's 0.8 is too loose.
5. **Use Codex's tooltip text** -- more accessible to non-cyclists.
6. **Add Gemini's security section** as a checklist item: URL allowlisting, responsible User-Agent, rate limiting.
7. **Fix Gemini's CV metric** -- must be CV of consecutive gaps, not CV of absolute finish times.
8. **Add pagination** (present in Claude and Codex, missing from Gemini).
9. **Add test cases** from both Claude (6 cases) and Codex (7 cases). Gemini provides none.
