# Sprint 010 Merge Notes

## Draft Strengths Adopted

### From Claude Draft
- **High code specificity**: Near-production code for `render_feed_card()`, `render_elevation_sparkline()` (SVG), session state initialization, and `get_feed_items()` return shape. Adopted as the implementation baseline.
- **Duration calculation via `race_time_seconds`**: Directly uses timing data rather than deriving from speed/distance. Avoids compounding errors.
- **`st.expander` multi-open**: Allows multiple cards open simultaneously. Simpler state management, useful for ad-hoc comparison.
- **Principled scope cutting**: Deferral rationale is clear and per-use-case. Adopted the framing.
- **Inline SVG sparkline**: Lighter weight than Vega-Lite charts, predictable rendering, minimal DOM overhead.

### From Codex Draft
- **Non-destructive architecture (new `feed.py`)**: Creating a new page rather than rewriting `calendar.py` is strictly safer. Interview confirmed this choice.
- **UC-10 via lookup table**: `RACER_TYPE_DESCRIPTIONS` mapping (course_type, finish_type) to a sentence is cheap and directly serves the persona. Included as in-scope.
- **UC-31 via existing climb data**: Extracting a "where does it get hard?" one-liner from `climbs_json` reuses existing data. Included as in-scope.
- **URL-based state persistence (UC-50)**: Encoding category and expanded series into `st.query_params` for cross-session persistence. Better than Claude's session-only approach.
- **Open question about "This Weekend" + search interaction**: Search should clear the date filter.

### From Gemini Draft
- **Eager rendering risk in `st.expander`**: Correctly identified that `st.expander` renders contents into DOM even when collapsed. Adopted as a risk with mitigation (lazy-load heavy components).
- **Deep-link isolation pattern**: Filtering feed to show only the deep-linked race (with "Show all" button) rather than scrolling to it. Simpler for Streamlit.

## Valid Critiques Accepted

| Critique | Source | Resolution |
|----------|--------|------------|
| N+1 query problem in `get_feed_items()` | All three | Cache per-series summaries with `@st.cache_data`. Structure cache key as `(series_id, category)` for granular invalidation. |
| "This Weekend" = 7 days, not actual weekend | All three | Interview: user chose "Next 7 days" section labeled "Racing Soon." |
| Nested `st.expander` for historical editions may be buggy | Claude critique, Gemini critique | Use a bulleted list instead of nested expander for editions. |
| Plain-English finish types should reuse `FINISH_TYPE_TOOLTIPS` | Codex critique, Gemini critique | Reuse existing dict, don't create a duplicate. |
| Pagination needed from Phase 1 | Claude critique | Include "Show more" pagination in Phase 1, not deferred to Phase 4. |
| UC-50 needs URL-based persistence | Codex critique, Gemini critique | Sync state to `st.query_params` for bookmark/refresh persistence. |
| Phase 4 in Codex draft is overloaded | Gemini critique | Redistributed: UC-10 and UC-31 moved to Phase 2 (card content). |
| SVG sparkline needs early validation | Gemini critique | Add SVG rendering validation as a Phase 2 task. |
| LIKE wildcard characters in search | Codex critique | Escape `%` and `_` in search input before passing to `ilike()`. |

## Critiques Rejected (with reasoning)

| Critique | Source | Reason for Rejection |
|----------|--------|---------------------|
| Include UC-25/UC-26/UC-28 (field strength, rider types, team rep) | Gemini draft | Interview: user chose "Moderate" scope (20 UCs). These require undefined algorithms. |
| Single-open card enforcement | Codex draft | Interview: user chose multi-open `st.expander`. Simpler and avoids the button/chevron conflict. |
| `st.area_chart` for sparklines | Codex draft | Interview: user chose inline SVG. Lighter DOM weight. |
| Rewrite calendar.py in place | Claude draft | Interview: user chose new `feed.py`. Non-destructive is safer. |
| Duration via speed/distance derivation | Codex draft | Claude's direct `race_time_seconds` approach is more accurate. |

## Interview Refinements Applied

1. **Architecture**: New `feed.py` page, calendar preserved as "Browse All"
2. **Scope**: 20 UCs (Claude's 18 + UC-10 + UC-31)
3. **"This Weekend"**: "Racing Soon" section showing next 7 days, always visible when applicable
4. **Expansion**: `st.expander`, multi-open, native Streamlit behavior
5. **Sparkline**: Inline SVG, pure Python generation
