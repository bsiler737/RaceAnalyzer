# Sprint 005 Merge Notes

## Draft Strengths

**Claude**: Most implementation-ready draft. Complete code for every function. Conservative gap_cv threshold (0.6). Hidden st.button fallback for reliable Streamlit navigation. URL domain allowlisting for scraped map URLs.

**Codex**: Best architectural decisions. CSS Grid for tiles (most flexible). Nominatim-first maps (always works). Statistical spacing algorithm well-justified with real PNW examples (Maryhill Loops, Mutual of Enumclaw). Confidence-based overall classification. Query params for filter state preservation.

**Gemini**: Most readable sprint plan. Clean architecture section. Security as first-class concern. But fatally under-specified for implementation and uses wrong CV metric (absolute times instead of consecutive gaps).

## Interview Decisions (User Input)

1. **Overall classification**: Use **most frequent** (mode) non-UNKNOWN finish type. Tiebreak by highest confidence. User rationale: this will work better when adding past editions of the same race.
2. **TT detection**: Use **Codex approach** — three-tier (metadata, keywords, statistical spacing with gap_cv < 0.8).
3. **Maps**: **Nominatim geocoding first** (always works), BikeReg/RideWithGPS as optional enhancement.
4. **Tile implementation**: **CSS Grid** via st.markdown HTML injection (Codex approach).
5. **Scope cuts if constrained**: Tooltips and real course maps from bikereg can be cut. Core: classification icons, TT detection, UNKNOWN toggle, clickable tiles, back navigation.

## Valid Critiques Accepted

- Gemini's CV > 0.9 on absolute times is **wrong** (Claude/Codex critique). Use consecutive gap CV.
- Claude's hardcoded Seattle fallback for maps is bad (Codex critique). Use Nominatim geocoding.
- Codex's gap_cv < 0.8 may be too loose (Claude critique). BUT user chose Codex approach, so keeping 0.8. Can tighten later with real data.
- Hidden st.button rendering issue (Codex critique of Claude). Solve by using CSS Grid with proper click handling instead.
- Nominatim rate limiting concern (Claude critique of Codex). Address with st.cache_data and sequential geocoding.
- HTML escaping needed for race names/locations in tile HTML (Claude critique of Codex). Use html.escape().
- SQLite has no MODE() function (Codex critique of Gemini). Do aggregation in Python.
- `title` attribute tooltips are low-fidelity (Claude/Codex critique of Gemini). BUT tooltips are a cut candidate per user, so keep simple `title` approach if implemented.

## Critiques Rejected

- Codex critique that plurality vote is wrong for overall classification — user explicitly chose frequency-based approach for multi-year data reasons.
- Claude critique that 0.8 gap_cv threshold is too loose — user chose Codex approach. Can tune later.

## Final Architecture

- **TT detection**: Codex three-tier with gap_cv < 0.8
- **Overall classification**: Mode (most frequent non-UNKNOWN), tiebreak by total finishers then lowest CV
- **Tiles**: CSS Grid via st.markdown (Codex)
- **Maps**: Nominatim geocoding + OSM static tiles (Codex/Claude). BikeReg best-effort if time allows.
- **Navigation**: CSS Grid `<a>` tags + hidden st.button fallback (Claude safety net)
- **Back button**: st.button with st.switch_page, query_params for filter state (Codex)
- **Tooltips**: HTML `title` attribute (simple, cuttable)
- **Icons**: Finish-type SVGs (Claude's icon descriptions, 9 types)
