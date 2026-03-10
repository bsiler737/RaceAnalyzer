# Sprint 006 Merge Notes

## Interview Decisions

1. **Series grouping**: Group ALL editions (including numbered ones like Mason Lake I/II) into one UI entity. Strip Roman numerals during normalization.
2. **Calendar UX**: Aggressive grouping — one tile per series, no toggle. Click through to series detail showing editions.
3. **Course map**: Custom Folium polyline (Strava-style), not RWGPS iframe embed. Requires `streamlit-folium` dependency and polyline caching.
4. **Series detail layout priority**: (1) Overall classification badge at top, (2) course map (prominent, "looks nice"), (3) classification trend chart (stacked bars), (4) category selector for per-category view. Per-category pivot table available on demand, not shown by default.
5. **Match threshold**: Low threshold (prefer showing a possibly-wrong map over no map). Manual override mechanism needed.

## Elements Taken from Each Draft

### From Claude Draft
- `RaceSeries` table with `normalized_name` + `display_name` (all critiques agreed this is cleaner than series_key column)
- `series_id` FK on Race
- `build-series` idempotent CLI command
- Suffix normalization map (RR -> Road Race, TT -> Time Trial, etc.)
- `pick_display_name()` selecting longest/most descriptive edition name
- `get_series_detail()` returning self-contained dict with trend DataFrame

### From Codex Draft
- Phased rollout structure (maps and dedup independent, either can ship alone)
- 3-component route scoring algorithm (name similarity via SequenceMatcher 0.45, proximity 0.30, length fit 0.25 — drop popularity signal)
- Race-type-aware distance expectations for route matching
- Roman numeral and ordinal stripping in name normalization
- `lru_cache` on normalize function
- Manual override CLI (`override-route`) with `rwgps_manual_override` boolean
- Sidebar "Other Editions" links on race detail page

### From Gemini Draft
- Series detail page layout: hero section, classification chart, per-category view
- Encoded polyline storage format (compact vs full track points)
- `_clean_search_name()` for RWGPS queries
- Comprehensive error/empty state handling (8 scenarios)
- Back-navigation state preservation (`back_to_series` session state)
- Route linked to series (not individual race) since courses usually stay the same
- Skip chart for series with < 3 editions (show simple table instead)

## What Was Cut
- MapMyFitness API integration (RWGPS sufficient)
- Gemini's mini distribution bar on tiles (too small to read per Gemini critique)
- Gemini's separate `RaceRoute` table (over-normalized — store on RaceSeries instead)
- Fuzzy matching / Levenshtein (exact normalization + manual review sufficient for ~300 races)
- Toggle between series view and all-races view (user chose aggressive grouping only)
- Iframe embed (user chose Folium polyline)
