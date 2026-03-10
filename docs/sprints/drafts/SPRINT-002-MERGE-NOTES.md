# Sprint 002 Merge Notes

## Draft Strengths

### Claude Draft (1058 lines)
- Near-complete implementation code for every file — copy-paste ready
- Modern Streamlit APIs (`st.navigation()`, `st.query_params`)
- Thorough test code: ~20 test methods, chart smoke tests, seeded fixture
- Group structure visualization on race detail page (unique to this draft)
- Expandable per-category results tables
- Both pie and bar charts for distribution view
- 11-item Definition of Done, specific and measurable

### Codex Draft (633 lines)
- Configurable confidence thresholds in Settings dataclass (unique to this draft)
- State multiselect (`st.multiselect`) instead of single selectbox
- Comprehensive risk analysis (7 risks with severity ratings)
- Detailed function signatures with return type documentation
- Consistent finish type color palette with hex values
- Explicit `limit`/`offset` pagination parameters on queries
- Natural language qualifier mapping clearly defined

### Gemini Draft (160 lines)
- Explicitly states "UI is read-only" architectural principle (adopted)
- Clear, concise writing accessible to non-technical stakeholders
- Correct decision to keep scraping CLI-only with good rationale

## Valid Critiques Accepted

1. **Configurable confidence thresholds** (all critiques): Claude draft hardcodes thresholds. Adopted Codex's approach of adding `confidence_high_threshold` and `confidence_medium_threshold` to Settings.
2. **State multiselect** (Codex critique of Claude): PNW users want WA+OR together. Changed from `st.selectbox` to `st.multiselect` for states.
3. **`@st.cache_data` for filter queries** (Claude critique): Neither draft cached filter-populating queries. Added caching for `get_categories`, `get_available_years`, `get_available_states`.
4. **Nullable field guards** (Codex critique): `gap_to_second_group` can be None, causing formatting errors. Added None checks.
5. **Multiple finish types in test fixture** (Codex critique): Claude's seeded_session only has BUNCH_SPRINT. Added variety for meaningful distribution/trend tests.
6. **`finish_type_display_name` fragility** (Codex critique): Replace/title-case breaks on abbreviations. Changed to lookup dict.
7. **Deprecated `st.experimental_get_query_params`** (all critiques of Gemini): Used `st.query_params` instead.
8. **Read-only UI principle** (Gemini draft): Explicitly stated in architecture section.
9. **DB path forwarding via env var** (Claude critique): Added `RACEANALYZER_DB_PATH` environment variable approach.

## Valid Critiques Rejected

1. **Split components into separate files** (Codex architecture): User chose single `components.py` in interview. Each sub-module would be ~20 lines — premature splitting for Sprint 002.
2. **Return `list[dict]` instead of DataFrames** (Codex draft): User chose DataFrames in interview. Less conversion friction with Plotly and Streamlit.
3. **Use `st.radio` fallback** (Codex draft): Pin `streamlit>=1.36` instead. The `st.navigation()` API is stable and the version is widely available. Compatibility fallback adds complexity for minimal benefit.
4. **Pie chart instead of bar chart** (Gemini draft): Include both (Claude's approach). Pie for proportion intuition, bar for count comparison.

## Interview Refinements Applied

1. **DataFrames from query layer** — all query functions return `pd.DataFrame`
2. **Single `components.py`** — not split into components/ package
3. **CLI-only for data mutation** — UI is strictly read-only
