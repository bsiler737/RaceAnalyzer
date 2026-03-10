# Sprint 006 Cross-Critique (Claude reviewing all three drafts)

## Strengths of Each Draft

### Claude Draft
- **Dedicated `RaceSeries` table with FK on Race is the cleanest relational design.** The `normalized_name` on the series plus a `display_name` gives a proper place to store series-level metadata, and the `series_id` FK on Race makes aggregation queries explicit rather than relying on GROUP BY a denormalized string column. The `pick_display_name()` function that selects the longest (most descriptive) edition name is a nice touch.
- **RWGPS iframe embed is the most honest assessment of effort vs. value.** The embed gives elevation profile, distance markers, and turn-by-turn for zero rendering code. The draft correctly identifies that storing only the `rwgps_route_id` integer is sufficient -- no need to fetch and cache polyline data, no new dependencies, no fragile track point parsing.
- **Name normalization is thorough and well-tested in prose.** The suffix map covers dotted abbreviations (`r.r.`, `c.r.`, `i.t.t.`), the noise pattern strips "presented by" / "sponsored by" clauses, and the ordinal pattern handles both "23rd" standalone and "23rd annual" compound forms. This is the most complete normalization of the three drafts.
- **`build_series()` is a clean backfill function** with idempotent upsert behavior -- it checks for existing series before creating new ones and only updates `series_id` when it has changed. Re-runnable without side effects.
- **Series detail page is well-structured** with a stacked bar chart for classification trends and per-edition expandable sections. The `get_series_detail()` function returns a self-contained dict with trend DataFrame, making the UI layer thin.
- **Migration strategy is explicit** about using `ALTER TABLE ADD COLUMN` for the FK and `CREATE TABLE` for the new table, with `Base.metadata.create_all()` as the additive mechanism.

### Codex Draft
- **Phased rollout (A/B/C) is the best scoping strategy of the three.** Explicitly declaring that Phase A (course maps) and Phase B (dedup) have zero dependency on each other is valuable project management. Either can ship alone, and Phase C (polish) is clearly marked as stretch. This de-risks the sprint by guaranteeing partial value delivery even if time runs short.
- **Route scoring algorithm is the most sophisticated.** Four weighted components (name similarity 0.40, distance proximity 0.25, route length fit 0.20, popularity 0.15) with race-type-aware distance expectations is clever. The `_DISTANCE_EXPECTATIONS` dict that knows a criterium is 0.8-3km and a road race is 40-200km provides a powerful false-match filter. Neither the Claude nor Gemini draft incorporates race type into scoring.
- **SequenceMatcher for name similarity** is a better choice than Jaccard token overlap (Claude draft). SequenceMatcher handles substring matches and character transpositions; Jaccard only considers exact token overlap. "Banana Belt Road Race Course" vs "Banana Belt RR" would score poorly on Jaccard (low intersection/union of tokens) but SequenceMatcher would detect the shared substring.
- **Manual override CLI (`override-route`)** is a critical escape hatch that only the Codex draft implements fully. The `rwgps_manual_override` boolean column prevents auto-matching from overwriting a human correction. Claude's draft mentions the possibility but does not implement it; Gemini's draft does not address it.
- **`lru_cache` on `normalize_race_name()`** is a small but valuable optimization -- the calendar page may call normalization dozens of times with repeated names during a single render cycle.
- **Sidebar "Other Editions" navigation** on the race detail page is a pragmatic alternative to a full series detail page. It lets users hop between editions without leaving the familiar race detail UI. This is lower-effort than building a new page and may be sufficient for MVP.
- **Explicit design analysis sections** (series_key vs RaceSeries table, Folium vs iframe) with structured pros/cons are excellent for decision-making transparency. These sections make it easy for a reviewer to evaluate the trade-offs without re-deriving them.

### Gemini Draft
- **Most complete UI/UX specification.** The ASCII wireframe for the series tile (with mini stacked distribution bar) and the full series detail page layout (hero section with map + summary, classification history chart, per-category pivot table, edition accordions) are the most detailed of the three drafts. A developer could implement the UI from these wireframes alone.
- **Per-category breakdown pivot table** (category x year -> finish type) is a unique insight from this draft. Neither Claude nor Codex proposes this view. It directly answers "does Cat 1/2 finish differently from Cat 4/5?" which is a genuinely useful question for racers choosing a category.
- **Mini distribution bar on series tiles** provides at-a-glance information density. A thin stacked bar showing finish type proportions across all editions communicates more than a single badge. The implementation with proportional CSS widths and tooltips is well thought out.
- **Separate `RaceRoute` table** decouples route caching from the Race model. This is architecturally cleaner than storing `rwgps_route_json` (potentially 50KB+ of track points) as a TEXT column on the Race table. It also allows linking a route to a series (not just a single race), which is correct -- the same course route typically applies to all editions of a race.
- **Error and empty states table** is the most comprehensive treatment of edge cases. The table covers: no RWGPS match, network failure, single-edition series, classification conflicts, no classifications at all, geocoding failure, unassigned races, and polyline decode failure. Each scenario has an explicit behavior specification.
- **Mobile responsiveness section** is unique to this draft. The table mapping components to desktop/tablet/mobile breakpoints, plus the CSS for horizontal-scroll pivot tables, shows production awareness.
- **`_clean_search_name()` for RWGPS queries** -- stripping year and normalizing suffixes before sending to RWGPS search -- is a practical improvement over sending the raw race name. RWGPS search is keyword-based; removing "2024" from "2024 Banana Belt RR" yields better results.
- **Navigation flow diagram** (Calendar -> Series Detail -> Race Detail -> back to Series) is a clear specification of the information architecture. The `back_to_series` session state for proper back-navigation is a nice detail.
- **Scope cut guidance** with a prioritized cut list (keep series grouping, cut pivot table and distribution bar, cut course maps last) gives the implementer a clear decision tree if time is short.

---

## Key Disagreements

### 1. RaceSeries Table vs series_key Column

**Claude and Gemini: Dedicated `RaceSeries` table with FK.**
**Codex: `series_key` column on Race, no new table.**

**Recommendation: `RaceSeries` table (Claude/Gemini approach), but simplified.**

The Codex draft argues that a separate table "adds a foreign key, a migration, and join complexity for minimal benefit." This understates the benefits and overstates the costs:

- **Benefits of a table:** A canonical `display_name` that does not depend on which edition's raw name you happen to query. Series-level metadata (location from most recent edition, overall route) has a natural home. The series detail page needs a stable ID to link to; a normalized string in a URL is fragile and ugly. Manual override of series assignments is cleaner with a FK than with a freeform string column.
- **Costs are low:** SQLite `CREATE TABLE` is trivial. The JOIN is a single equijoin on an indexed FK -- negligible for <2,000 races. `Base.metadata.create_all()` handles creation. The migration is ~10 lines of SQL.
- **The Codex `group_concat` approach is SQLite-specific** and produces a comma-separated string of race IDs that must be parsed in Python. This is fragile (what if an ID contains a comma?) and performs poorly if the grouping query is re-run on every page load.

However, Gemini's addition of a **separate `RaceRoute` table** is over-engineering for this sprint. Storing `rwgps_route_id` directly on Race (as Claude and Codex propose) is simpler and sufficient. A route table makes sense if routes are shared across races, but in practice the RWGPS search is per-race-name, and the same route ID will naturally be stored on multiple Race rows in the same series.

### 2. RWGPS Iframe Embed vs Folium Polyline Rendering

**Claude: RWGPS iframe embed (3 lines of code, no new dependencies).**
**Codex and Gemini: Folium polyline via `st_folium` (new dependency, ~30-60 lines).**

**Recommendation: Start with iframe embed (Claude), plan Folium as a Phase C upgrade.**

The Codex and Gemini drafts make valid points about iframe limitations (RWGPS branding, no style control, load speed). But they underestimate the risks of the Folium path:

- **Track point fetching is the real cost.** The `/routes/{id}.json` endpoint may require authentication for some routes (Codex acknowledges this: "The .json endpoint may require auth for some routes"). If it does, Folium rendering is dead on arrival. The iframe embed works with just the route ID.
- **Data volume:** Track point JSON for a single route can be 20-100KB. For 269 races, that is potentially 27MB of JSON stored in SQLite TEXT columns. The iframe approach stores only a 4-byte integer per race.
- **New dependency risk:** `streamlit-folium` is a third-party package. The Codex draft pins it at "1.5k GitHub stars" but does not specify version compatibility with the project's Streamlit version. The iframe embed has zero dependencies.
- **The iframe is actually good for a cycling audience.** The RWGPS embed shows elevation profile, distance markers, and route details that are genuinely useful for race preparation. Recreating these features in Folium would be substantial additional work.

The iframe is the right MVP. If user feedback indicates that style control or offline rendering is needed, upgrade to Folium in a future sprint when the RWGPS track point endpoint has been validated against real routes.

### 3. Name Normalization Approach Differences

**Claude:** Comprehensive regex-based normalization with suffix map (`_SUFFIX_MAP`), year patterns, noise patterns ("presented by"), and ordinal stripping. Normalizes abbreviations to their full form (e.g., "rr" -> "road race").
**Codex:** Similar approach but more aggressive. Strips race type suffixes entirely (e.g., "rr" -> empty string, "road race" -> empty string). Also handles Roman numerals and edition numbers at start/end of name. Uses `lru_cache` for performance.
**Gemini:** Lightest normalization. Strips year, normalizes "RR" -> "Road Race", "Crit" -> "Criterium", "TT" -> "Time Trial". No ordinal handling, no Roman numeral handling, no sponsor stripping.

**Recommendation: Codex approach for normalization logic, but keep suffixes (Claude-style) rather than stripping them.**

The critical question is whether "Banana Belt RR" and "Banana Belt Road Race" should map to the same series key. All three drafts say yes. But Codex strips the suffix entirely (`"banana belt"`), while Claude normalizes it (`"banana belt road race"`). Codex's approach risks false positives: if there were both a "Banana Belt Road Race" and a "Banana Belt Criterium," stripping all type suffixes would group them together as "banana belt." Claude's approach of normalizing to canonical form (`"banana belt road race"` vs `"banana belt criterium"`) keeps them separate, which is correct.

However, Codex's handling of Roman numerals ("Mason Lake I" vs "Mason Lake II") and ordinals ("21st Annual") is essential and missing from Gemini's draft. The Claude draft handles ordinals but not Roman numerals.

The recommended merge: Use Codex's regex patterns for year, ordinal, Roman numeral, and edition number stripping. Use Claude's suffix normalization (abbreviation -> canonical form, not deletion). Add Codex's `lru_cache` optimization. Add Claude's noise pattern stripping ("presented by ...").

### 4. Route Matching/Scoring Differences

**Claude:** Simple two-factor scoring: Jaccard token similarity (0.7 weight) + geographic proximity (0.3 weight). Min score threshold of 0.3.
**Codex:** Four-factor scoring: SequenceMatcher name similarity (0.40) + distance proximity (0.25) + route length fit by race type (0.20) + popularity/trip count (0.15). Min score threshold of 0.3.
**Gemini:** No scoring algorithm -- picks the first result from the RWGPS proximity-sorted search with a hardcoded `match_confidence = 0.7`.

**Recommendation: Codex scoring algorithm with Claude's simplicity as fallback.**

Gemini's approach of trusting RWGPS's default sort order with no quality assessment is too naive. RWGPS search returns results by proximity, not by relevance. A popular training ride near the race venue would outrank the actual race course.

Codex's four-factor scoring is genuinely better than Claude's two-factor approach. The route length fit component is particularly valuable: it prevents matching a 100km century ride to a 1.2km criterium course, which is a real failure mode when searching by name + location near the same area. The popularity signal (trip count) is a reasonable quality proxy -- race courses uploaded by organizers tend to accumulate more trips.

However, the scoring should be behind a simple interface so it can be upgraded without changing call sites. Store the match score in the database (as Codex proposes with `rwgps_match_score`) so low-confidence matches can be reviewed later.

### 5. Calendar UX: Series Tiles vs Toggle

**Claude:** Calendar shows series by default with a toggle to switch to individual races.
**Codex:** Calendar shows series tiles only (no toggle). Individual races are accessed via the series tile -> race detail navigation.
**Gemini:** Calendar shows a radio button toggle between "Series (grouped)" and "Individual races" views.

**Recommendation: Series-only view (Codex approach), with the existing individual view preserved as a fallback until backfill is complete.**

A toggle adds UI complexity and doubles the surface area to test. The series view subsumes the individual view: a single-edition series tile renders identically to a current individual tile (as all three drafts agree). The only reason to keep the individual view is during the transition period before `build-series` has been run.

Rather than a permanent toggle, show the individual view automatically when no series exist (i.e., `build-series` has not been run yet), and show the series view once series are populated. This is a graceful degradation rather than a permanent UX choice.

However, Codex's approach of not having a series detail page at all (just sidebar "Other Editions" links) is too minimal. The Gemini wireframe for the series detail page -- with classification history chart, per-category pivot, and edition accordions -- is the right landing page for a series tile click. It directly answers the user story "I see aggregated classification history for a race series."

---

## Risks and Gaps

### What All Three Drafts Miss or Underestimate

**1. RWGPS API reliability is a single point of failure for course maps.**
All three drafts use the undocumented `/find/search.json` endpoint. None proposes a fallback data source if RWGPS changes the endpoint, adds authentication, or rate-limits aggressively. The intent document mentions MapMyFitness as an alternative, but all drafts exclude it. The risk is not just "no new course maps" but also "existing cached route IDs become invalid if RWGPS changes their ID scheme." Mitigation: cache the actual polyline/track data (not just the route ID) so the map survives an API change. This favors the Codex/Gemini approach of storing polyline data, contradicting the iframe-only recommendation above. A compromise: store the route ID for iframe rendering AND cache the polyline as a backup, but only render from polyline if the iframe fails.

**2. Name normalization false positives are higher risk than any draft acknowledges.**
All three drafts handle the "Banana Belt RR" -> "Banana Belt Road Race" case. None addresses:
- **Same name, different organizer/venue:** "Summer Criterium" could be run by different clubs in different cities across years. Normalization would group them. Location comparison should be part of series building, not just name matching.
- **Name changes mid-series:** A race rebrands from "Smith Memorial Road Race" to "Smith Classic Road Race." These are the same series but normalization would split them.
- **Sub-events within a stage race:** "Tour de Bloom Stage 1 Road Race" and "Tour de Bloom Stage 2 Time Trial" would both normalize to something containing "tour de bloom" and could be incorrectly grouped depending on how aggressively stages are stripped.
- Mitigation: the `build-series --dry-run` review step (Codex) is essential. The sprint plan should specify that the dry-run output is reviewed by a human before committing.

**3. Performance concerns with aggregation queries are unaddressed.**
The `_compute_series_overall_finish_type()` function in all three drafts loads ALL `RaceClassification` rows for ALL races in a series, iterates in Python, and computes the mode. For the series tile grid (which renders ~50-100 series), this means ~50-100 separate queries each loading potentially dozens of classification rows. This is an N+1 query problem. At 269 races this is manageable; at 1,385 (the scraping target mentioned in the intent) it will be noticeably slow on the calendar page.
- Mitigation: precompute the series overall finish type during `build-series` and store it on the `RaceSeries` row. Recompute only when classifications change.

**4. RWGPS track point endpoint authentication is unknown.**
The Codex draft notes that `/routes/{id}.json` "may require auth for some routes" but treats this as a minor fallback case. In practice, RWGPS has increasingly locked down their API. If track points require auth for most routes, the entire Folium rendering path is blocked. The Claude iframe approach degrades more gracefully here, but even the iframe embed could require the route to be public.
- Mitigation: before committing to a rendering strategy, test the track point endpoint against 10-20 real RWGPS route IDs matching PNW races. This should be a Day 1 spike.

**5. No draft addresses what happens when a race moves venues.**
"Pacific Raceways Circuit Race" could move from Kent to Shelton between editions. All editions would be grouped into one series, but the course map from the most recent edition would be misleading for historical editions. The series detail page should show the course map per-edition, not per-series.
- The Gemini draft partially addresses this by linking routes to both series and individual races, but the UI only shows the series-level route on the series detail page.

**6. SQLite `group_concat` ordering is not guaranteed.**
The Codex draft uses `group_concat(Race.id)` to collect race IDs per series. SQLite's `group_concat` does not guarantee order unless you use a window function or subquery with ORDER BY. The "most recent edition's name" logic depends on the last ID in the concatenated string, which may not correspond to the most recent date.

---

## Recommended Merge Strategy

### Take from Claude Draft
- **`RaceSeries` table schema** with `normalized_name` and `display_name` columns, `series_id` FK on Race. (Simpler than Gemini's version -- no need for `location`/`state_province` on the series table since those are derivable from the most recent edition.)
- **RWGPS iframe embed** as the MVP course map renderer. Store only `rwgps_route_id` on Race.
- **`build_series()` backfill function** with idempotent upsert logic.
- **`pick_display_name()` function** for choosing the best human-readable series name.
- **Suffix normalization map** (abbreviation -> canonical form, not deletion).
- **Migration helper** using `ALTER TABLE ADD COLUMN` + `CREATE TABLE`.

### Take from Codex Draft
- **Phased rollout structure** (Phase A: course maps, Phase B: dedup, Phase C: polish). Ship each independently.
- **Route scoring algorithm** with four weighted factors (name similarity, proximity, length fit, popularity). Store `rwgps_match_score` on Race.
- **SequenceMatcher** for name similarity instead of Jaccard.
- **`override-route` CLI command** with `rwgps_manual_override` boolean to protect manual corrections.
- **`normalize-names --dry-run`** for reviewing normalization before committing.
- **`lru_cache` on normalization function.**
- **Roman numeral and edition number stripping** from normalization logic.
- **Race-type-aware distance expectations** for route scoring.
- **Sidebar "Other Editions" links** on race detail page (in addition to the series detail page, not instead of).

### Take from Gemini Draft
- **Series detail page layout** with classification history chart, per-category pivot table, and edition accordions. This is the most complete UI specification.
- **Mini distribution bar** on series tiles (stretch goal -- cut if time is short).
- **Error and empty states table** as the canonical specification for edge case handling.
- **Navigation flow** (Calendar -> Series Detail -> Race Detail -> back to Series) with `back_to_series` session state.
- **Scope cut guidance** (keep series grouping, cut pivot table and mini bar, cut course maps last).
- **`_clean_search_name()`** for preprocessing race names before sending to RWGPS search.

### Cut for Scope
1. **Folium polyline rendering** -- defer to a future sprint. Use iframe embed for MVP.
2. **`RaceRoute` table** (Gemini) -- store `rwgps_route_id` directly on Race for now. Add a route cache table only if track point storage is needed.
3. **Elevation profile** -- mentioned as a stretch goal by Gemini, not needed for MVP.
4. **Per-category pivot table on series detail page** -- nice to have but can ship in a follow-up. The stacked bar chart is sufficient for MVP.
5. **Mobile responsiveness CSS** (Gemini) -- Streamlit handles basic responsiveness. Custom breakpoints are polish.
6. **Phase C** (Codex) -- "Compare courses across editions" is out of scope.

### Recommended Interview Questions for the User (max 5)

1. **Do Mason Lake I and Mason Lake II use the same course, or are they different courses run on the same day?** This determines whether Roman numeral stripping in name normalization is correct (grouping as one series) or a false positive (they should stay separate). The same question applies to Pacific Raceways numbered events.

2. **When you look at a series like Banana Belt (4 editions), is the most useful summary "how does this race usually finish" (stacked bar chart across years) or "what did the most recent edition look like" (single edition detail)?** This determines how much effort to invest in the aggregated classification history vs. just showing the latest edition prominently.

3. **For the course map, is an embedded RWGPS map (with their elevation profile and turn-by-turn) sufficient, or do you want a custom-styled map that matches the app's look and feel?** This settles the iframe vs Folium question based on actual user preference rather than engineering opinion.

4. **Are there races in your dataset that changed their name across years (e.g., rebranded, changed sponsors)?** If so, name normalization alone will not catch these, and we may need a manual series assignment mechanism from Day 1 rather than deferring it.

5. **Should the calendar default to the series-grouped view, or should users be able to toggle between grouped and individual views?** This determines whether we build the toggle UX or just ship series-only with individual view as a fallback for unassigned races.
