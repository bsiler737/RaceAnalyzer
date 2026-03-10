# Sprint 006 Cross-Critique: Engineering Trade-Offs

**Reviewer**: Claude Opus 4.6 (Codex perspective critique)
**Drafts reviewed**: Claude, Codex, Gemini
**Date**: 2026-03-09

---

## 1. Schema Design: RaceSeries Table vs series_key Column

### The proposals

- **Claude**: New `RaceSeries` table (`id`, `normalized_name`, `display_name`) with `series_id` FK on `Race`. Two new columns on Race: `rwgps_route_id`, `series_id`.
- **Codex**: No new tables. Add `series_key` (computed string column) plus four RWGPS columns directly on `Race`. Grouping is pure `GROUP BY series_key`.
- **Gemini**: New `RaceSeries` table (with `name`, `series_key`, `location`, `state_province`) AND a separate `RaceRoute` table. Three new tables/FKs total.

### Query complexity

The `series_key` approach (Codex) avoids JOINs entirely -- `GROUP BY series_key` on a single table is the simplest possible calendar query. Claude/Gemini require a JOIN through `race_series` for every calendar load. With SQLite and under 2,000 rows, the JOIN cost is negligible in absolute terms, but the Codex approach is genuinely simpler to write, debug, and explain.

However, the Codex `GROUP BY` query has a subtle problem: SQLite's `GROUP BY` on a nullable column means races without a `series_key` each become their own group (NULL != NULL in SQL). The draft handles this with `COALESCE(series_key, CAST(id AS TEXT))`, which works but produces an ugly hybrid key that mixes semantic strings with opaque IDs. Any downstream code that consumes `series_key` must handle both cases. The RaceSeries FK approach (Claude/Gemini) naturally handles single-edition races: every race gets a series, even if that series has only one member.

### Migration risk

All three approaches use `ALTER TABLE ADD COLUMN`, which is safe in SQLite. Codex wins slightly here: adding columns to an existing table has zero risk of data inconsistency, while creating a new table + FK requires a backfill step where every Race gets linked. If the backfill crashes midway, you have orphaned races with no series. Claude addresses this with `build_series` as an idempotent CLI command, which mitigates the risk.

Gemini adds the most migration surface: three new entities (RaceSeries, RaceRoute, plus FK columns on Race). The separate `RaceRoute` table is the most normalized but creates a third table to manage. For a dataset this small, the extra table is overhead without clear benefit.

### Data integrity

The `series_key` column is a computed denormalization. If normalization logic changes (and it will -- see Section 4), you must recompute every row's `series_key`. Codex acknowledges this: "just recompute -- no orphaned FK references." This is true, but it also means there is no source-of-truth for "what is the canonical name of this series?" The display name must be derived at query time from the raw race names, which is fragile.

Claude's `RaceSeries.display_name` solves this: there is one authoritative display name per series, stored once, updateable independently of the normalization pipeline. This matters for user-facing text quality.

### Future flexibility

When the user eventually wants to add series-level metadata (official website, notes, manual grouping overrides, a "favorite" flag), the `series_key`-only approach requires adding a table anyway. Claude/Gemini are future-proof here. Codex's pragmatism is well-reasoned for THIS sprint, but may create a migration-then-migration situation within 1-2 sprints.

### Verdict

**Use the `RaceSeries` table (Claude's schema), but with Codex's migration simplicity.** Keep the table minimal (id, normalized_name, display_name -- no location/state duplication as Gemini proposes). Do NOT add a separate `RaceRoute` table (Gemini); store `rwgps_route_id` directly on `Race` (Claude/Codex agree here). The incremental cost of one small table is low, and it provides a clean anchor for display names, future metadata, and FK integrity.

---

## 2. Route Rendering: iframe Embed vs Folium Polyline

### The proposals

- **Claude**: RWGPS iframe embed (`ridewithgps.com/embeds?type=route&id=ID`). Store only `rwgps_route_id` on Race. Zero rendering code.
- **Codex**: Folium polyline via `st_folium`. Fetch and cache full track point JSON on Race. ~30 lines of rendering code.
- **Gemini**: Folium polyline (same as Codex), but stores encoded polyline string in a separate `RaceRoute` table. Adds `polyline` Python package as a dependency.

### Dependency weight

Claude's iframe approach has zero new dependencies. Codex/Gemini add `folium` + `streamlit-folium` (and Gemini adds `polyline`). These are well-maintained packages, but `streamlit-folium` has had compatibility issues across Streamlit versions historically. This is a real maintenance risk for a personal project where dependency updates may happen infrequently.

Counterpoint: the existing codebase already uses Streamlit + Plotly, so the team is already in the "complex UI dependency" world. One more Streamlit component is incremental.

### Rendering quality

This is where the iframe loses badly. The RWGPS embed loads the full RWGPS web app in a frame: it shows branding, navigation controls, elevation profile, comments section, and other chrome that has nothing to do with the RaceAnalyzer UX. It cannot be styled to match the app's color scheme. Load time is 2-4 seconds as the full RWGPS SPA boots.

Folium gives a clean polyline on a minimal basemap, with start/finish markers, Strava-orange styling, and sub-second rendering from cached data. The visual quality difference is significant and directly serves the "study the terrain" use case.

### Offline capability

The iframe requires a live internet connection to RWGPS on every page load. Folium renders from cached track points -- once fetched, the map works offline forever. For a personal analysis tool that might be used on spotty race-venue wifi, offline capability has real value.

### Data storage implications

Claude stores only an integer (`rwgps_route_id`). Codex stores full track point JSON (potentially 50-200KB per route for a long road race with ~1000 track points). Gemini stores an encoded polyline string (typically 2-10KB). At 1,385 races with ~60% match rate, that is:

- Claude: ~830 integers = negligible
- Codex: ~830 * 100KB avg = ~83MB of JSON blobs in SQLite
- Gemini: ~830 * 5KB avg = ~4MB of encoded polyline in SQLite

Codex's approach is the most storage-heavy. The raw track point JSON is also redundant -- you only need lat/lng for rendering, not the full RWGPS metadata per point. Gemini's encoded polyline is the right compromise: compact, decodable, sufficient for rendering.

### Maintenance burden

The iframe is zero maintenance until RWGPS changes their embed URL structure (which has happened before with other services). At that point, it is a single string change. Folium rendering code is ~30 lines that rarely need changing, but the `fetch_track_points` / `fetch_route_polyline` logic depends on the undocumented RWGPS JSON response structure, which could change at any time. Both approaches share the same API fragility for the data-fetching step.

### Verdict

**Use Folium polyline rendering (Codex/Gemini) with Gemini's encoded polyline storage format.** Store the encoded polyline on the `Race` model directly (not in a separate table). The rendering quality advantage is decisive for the core use case. Use encoded polyline strings, not raw track point JSON, to keep storage reasonable.

However, consider implementing the iframe as a **3-line fallback**: if polyline data is not available but `rwgps_route_id` exists, show the iframe. This gives coverage during the initial data-fetching period and for routes where track point fetching fails.

---

## 3. Matching Algorithm: Simple Jaccard vs Weighted 4-Component Scoring

### The proposals

- **Claude**: Jaccard similarity on word tokens (0.7 weight) + Euclidean geographic proximity (0.3 weight). Minimum score threshold of 0.3. ~20 lines of scoring code.
- **Codex**: 4-component weighted scoring: name similarity via `SequenceMatcher` (0.40) + geographic proximity (0.25) + route length fit by race type (0.20) + popularity/trip count (0.15). Minimum score 0.3. ~50 lines of scoring code.
- **Gemini**: No scoring algorithm specified. Takes the first RWGPS search result (proximity-sorted by RWGPS) with a hardcoded confidence of 0.7. Effectively trusts RWGPS's ranking entirely.

### Analysis for ~300 races (current) scaling to ~1,385

Gemini's "take the first result" approach is dangerously naive. RWGPS search returns routes by geographic proximity, not by name relevance. A search for "Banana Belt RR" near Hillsboro will return every route near Hillsboro, and the first one might be "Sunday Coffee Ride" if it happens to start 0.1km closer. With 1,385 races, this will produce many false matches that silently poison the course map feature.

Claude's Jaccard approach is a solid baseline but has a known weakness: Jaccard treats all tokens equally and is sensitive to token count asymmetry. "Banana Belt RR" vs "Banana Belt Road Race Course 2024" produces a low Jaccard score because the union is large (7 tokens) while the intersection is small (2 tokens: "banana", "belt"). The noise word stripping helps, but it removes only a fixed set -- it cannot handle domain-specific noise.

Codex's `SequenceMatcher` handles partial matches and substring containment better than Jaccard. The substring boost (`if race_lower in route_name: name_sim = max(name_sim, 0.85)`) is a smart heuristic. The route-length-fit component is genuinely valuable: it prevents matching a criterium to a century ride just because they share a name and location. The popularity signal (trip count) is a reasonable proxy for "is this a real, well-known route?"

### Is the complexity justified?

For ~300 races, the difference between Claude and Codex may be <5 false matches. For ~1,385 races across a broader geography, the route-length-fit component alone probably prevents 20-40 bad matches (criteriums matched to road routes, or vice versa). The marginal ~30 lines of code are justified.

However, the popularity component (0.15 weight) is speculative. RWGPS does not document what fields are returned in search results, and `trip_count` may not be present. If the field is absent, the component scores 0.0 for every route, effectively redistributing weight to the other three components. This is harmless but misleading. The draft should note this as a "best-effort" signal.

### Verdict

**Use Codex's 4-component scoring, but drop the popularity component to 3 components (name 0.45, proximity 0.30, length fit 0.25).** The `SequenceMatcher` + substring boost is better than Jaccard. The length-fit component is the most valuable differentiator. Drop popularity until the RWGPS response structure is validated empirically. Add Codex's manual override CLI (`raceanalyzer override-route RACE_ID ROUTE_ID`) as a release-valve for bad matches.

---

## 4. Name Normalization: Comparing Approaches

### The proposals

- **Claude**: Strip years (4-digit, ordinal + "annual"), normalize suffixes via a map (RR -> road race, TT -> time trial, etc.), strip sponsor noise ("presented by ..."), collapse whitespace. ~40 lines. No fuzzy matching.
- **Codex**: Same year/suffix stripping PLUS Roman numeral removal (I-XXX), edition number stripping (at start/end only), `lru_cache` for performance, punctuation removal. ~60 lines. No fuzzy matching, but explicitly documents the "Stage 3" edge case.
- **Gemini**: Minimal normalization in `queries.py`: year stripping, three suffix replacements (RR, Crit, TT), punctuation removal. ~10 lines. Duplicates normalization logic in `rwgps.py` for search name cleaning.

### Edge cases each misses

**All three miss:**
- Races with different naming over time: "OBRA Banana Belt" (2022) vs "Banana Belt RR" (2024). The "OBRA" prefix would create two different series keys. This requires either fuzzy matching or manual override.
- Races where the location IS the name: "Pacific Raceways Circuit Race" vs "Pacific Raceways Criterium". These are different races at the same venue, and normalization correctly keeps them separate. But "Pacific Raceways" alone (if the race type suffix is stripped) would incorrectly merge them. Claude and Codex both strip race-type suffixes, which could cause this collision. Codex's approach of stripping "road race" to empty but keeping "criterium" as a canonical form is slightly better here.

**Claude misses:**
- Roman numerals: "Pacific Raceways XXI" and "Pacific Raceways XXII" would not match.
- Edition numbers: "Tour de Blast #3" and "Tour de Blast #4" would not match.

**Codex misses:**
- The `_EDITION_NUM_RE` at start/end is too aggressive: "Stage 3 Road Race" -> after suffix stripping -> "Stage 3" -> after end-number stripping -> "Stage". The draft acknowledges this and declares stage races out of scope, which is honest but not ideal.
- Roman numeral stripping in lowercase is fragile: "Mason Lake I" becomes "mason lake" after Roman numeral removal, but "I" is also the English pronoun. In practice this is fine for race names, but it is worth noting.

**Gemini misses:**
- Everything Claude and Codex handle: no ordinals, no Roman numerals, no sponsor noise, no edition numbers. The normalization is too thin for real-world PNW race data.
- Duplicated logic: normalization exists in both `queries.py` and `rwgps.py`, creating a maintenance risk where one is updated and the other is not.

### Is fuzzy matching worth it?

The intent document says "start with exact normalized name matching." For ~300 races, exact matching after normalization will handle ~85-90% of groupings correctly. The remaining 10-15% are edge cases like prefix variations ("OBRA Banana Belt" vs "Banana Belt") that exact normalization cannot solve.

Adding `difflib.SequenceMatcher` or Levenshtein distance at the series-building step (not at the name normalization step) would catch these. The cost is ~10 lines of code and a potential for false merges (two genuinely different races with similar names). At this dataset size, a manual review step after fuzzy matching (print the proposed merges and let the user confirm) is practical and would give better results than any automated threshold.

### Verdict

**Use Codex's normalization as the base (most comprehensive), but add Claude's sponsor-noise stripping.** Keep the Roman numeral handling. Accept the "Stage 3" limitation and document it. Add a post-normalization "proposed merges" review step to the `build-series` CLI command that prints groups before committing, allowing the user to reject false merges. Defer fuzzy matching to a future sprint -- the manual review step is a better investment of complexity budget.

---

## 5. Performance Implications at 1,385 Races

### Calendar loading

- **Codex (series_key GROUP BY)**: Single table scan + GROUP BY on an indexed column. At 1,385 rows, this is <10ms. The `_compute_series_finish_type` call inside the loop is the bottleneck: one IN query per series group to fetch classifications. With ~200 unique series, that is 200 DB queries. Total: ~200-500ms.
- **Claude (RaceSeries JOIN)**: JOIN is negligible overhead. Same `_compute_series_overall_finish_type` bottleneck: 200 queries. Total: ~200-500ms.
- **Gemini (RaceSeries JOIN)**: Same pattern as Claude. Also adds a sub-query per series for location from most recent edition, adding ~200 more queries. Total: ~400-800ms.

All three drafts share the N+1 query problem on classification aggregation. The fix is straightforward: precompute the aggregated finish type and cache it (on the RaceSeries table or as a series_key-indexed materialized column). None of the drafts propose this optimization, but it would reduce calendar load to a single query regardless of schema choice.

### Series aggregation

The `get_series_detail` query (all three drafts) loads all editions and their classifications. For a series with 4 editions and 4 categories each, that is 16 classification rows -- trivial. The Claude/Gemini `get_race_detail` reuse pattern (call `get_race_detail()` per edition inside `get_series_detail`) is clean but creates N+1 queries again. For 4 editions this is 4 queries -- acceptable. For a hypothetical series with 20 editions (possible for long-running races), it becomes noticeable. An eager-load JOIN would be better.

### Route matching (batch)

All three drafts rate-limit RWGPS API calls to ~1/second. At 1,385 races, batch matching takes ~23 minutes. This is a one-time offline operation, so it is acceptable. Codex's approach of scoring all results locally means each race gets one API call (search) plus one API call (track points) = 2 calls. Claude's simpler scoring also makes 2 calls per race. Gemini's "take first result" makes the same 2 calls but with lower accuracy, so re-runs are more likely.

The real performance difference is storage: Codex caches full track point JSON (~100KB/route), so repeated page loads are fast but the DB grows. Gemini caches encoded polylines (~5KB/route) -- better. Claude caches nothing (iframe), so every page load hits RWGPS -- worst for user experience.

### Verdict

**All three approaches perform adequately at 1,385 races.** The N+1 classification query is the shared bottleneck, and it can be solved the same way regardless of schema: precompute aggregated finish types and store them. Route data caching (encoded polyline) is important for page-load performance. The batch matching time (~23 minutes) is a one-time cost and not a differentiator.

---

## Recommended Merge Decisions

1. **Schema**: Use Claude's `RaceSeries` table (minimal: id, normalized_name, display_name) with `series_id` FK on Race. Store `rwgps_route_id` on Race (no separate RaceRoute table).

2. **Route rendering**: Use Folium polyline (Codex/Gemini). Store encoded polyline string on Race (add `rwgps_polyline TEXT` column). Fall back to iframe if polyline is absent but route_id exists.

3. **Route matching**: Use Codex's 3-component scoring (name via SequenceMatcher, proximity, length fit). Drop popularity until RWGPS response is validated. Add manual override CLI.

4. **Name normalization**: Use Codex's normalization (most comprehensive) plus Claude's sponsor-noise stripping. Add a "review proposed merges" step to the build-series CLI command.

5. **Calendar query**: Use Codex's series tile query pattern (single table + GROUP BY via series_key derived from RaceSeries.normalized_name), but query through RaceSeries for display_name. Precompute aggregated finish type on RaceSeries to avoid N+1 queries.

6. **File organization**: Follow Codex's flat module layout (`rwgps.py`, `normalize.py` at package root) rather than Gemini's `services/` subdirectory. The project is small; subdirectories add import path complexity without benefit.

---

## Interview Questions for the User

1. **How important is offline capability for course maps?** If you primarily use RaceAnalyzer at home on a stable connection, the iframe approach is simpler. If you might use it at race venues or on travel, cached polyline rendering is worth the extra dependency. This decision drives the rendering approach and storage requirements.

2. **How many races do you expect to manually review or override?** If you are willing to spend 15 minutes reviewing proposed series groupings after the initial build, we can skip fuzzy matching entirely and rely on exact normalization + manual corrections. If you want it to "just work" without review, we should invest in fuzzy matching now.

3. **Do you anticipate adding series-level metadata (notes, favorite flag, official URL) in the next 2-3 sprints?** If yes, the RaceSeries table is clearly correct. If not, the series_key column is defensible as a simpler starting point. Your answer determines whether the extra table is premature or prescient.

4. **For the calendar view, do you prefer one tile per series (collapsed, click to expand) or a toggle between "series view" and "all races" view?** Claude proposes a toggle; Codex and Gemini propose series-only with expansion. The UX choice affects how much query and component code we write.

5. **What is your tolerance for false course map matches?** Would you rather see no map (false negative) or occasionally see a wrong route (false positive)? This determines the minimum match score threshold. A threshold of 0.3 (all three drafts) is aggressive and will produce some false matches. Raising it to 0.5 reduces false positives but leaves more races without maps.
