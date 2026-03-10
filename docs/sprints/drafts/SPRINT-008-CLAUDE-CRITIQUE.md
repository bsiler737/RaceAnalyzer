# Sprint 008 Draft Critique

## Codex Draft

### Strengths

1. **Exceptional algorithmic specificity.** The profile generation algorithm (Phase 1) is implementation-ready: haversine distance, resampling to uniform spacing, triangular smoothing, linear-regression-based grade computation. No ambiguity about what to build.

2. **Climb detection is well-designed.** The state-machine approach with enter/exit thresholds, sustained-distance gates, and post-hoc merging is significantly more robust than Gemini's simple sliding-window approach. The merge step (`merge_gap_m = 150`) prevents fragmented climbs from brief flat sections — a real problem with GPS data.

3. **Honest about Streamlit/Folium limitations.** Dedicates an entire section to explaining *why* `st_folium` hover sync is unusable (full Python rerun per interaction) and proposes the correct solution: a single embedded Leaflet+Plotly.js component with client-side JS sync. This is the right call.

4. **Strong data pipeline thinking.** Phase 1 persists the profile to the DB (`Course.profile_json`), eliminating RWGPS network calls from the page-load path. The CLI command for batch extraction follows existing patterns (`elevation-extract`, `match-routes`).

5. **Excellent edge case coverage for stats.** Drop rate handles missing `field_size` (falls back to row count), small samples (suppress below 3 editions), and uses median (robust to outliers). Speed calculation has explicit distance caveats for crits and lap-only routes, with configurable plausibility filters.

6. **Narrative generator is concrete and testable.** Five-step generation with qualitative bands (drop rate → "low/moderate/high attrition", speed → "steady/fast/very fast") follows the project's "no raw probabilities" convention. Deterministic output is unit-testable.

7. **Security section is substantive.** JSON-only data injection (`<script type="application/json">` + `JSON.parse`), CDN version pinning with integrity hashes, timeout requirements on external calls. Not boilerplate.

8. **Open questions are actionable.** Each one (crit distance ambiguity, category normalization, climb threshold tuning) identifies a specific decision with concrete options.

### Weaknesses

1. **Phase 5 (map sync) is underspecified relative to its risk.** Allocated 3–5 days and labeled "highest risk," but the implementation detail is thinner than Phase 1–4. The JS sync approach is described conceptually ("use profile index as shared key") but lacks the specificity given to, say, climb detection. No fallback JS framework if Plotly.js proves too heavy for the iframe.

2. **No time estimates for total sprint duration.** Individual phases sum to 10.5–16.5 days, but no acknowledgment of whether this fits a sprint timebox. If this is a 2-week sprint, Phase 5 alone could consume it.

3. **Storage Option A (JSON blobs on Course) has unacknowledged downsides.** The draft notes "less queryable" but doesn't address: (a) no schema validation on the JSON, (b) migration path — adding Text columns to an existing table without Alembic means manual DDL or `CREATE TABLE IF NOT EXISTS` recreation, (c) the profile JSON could be 200KB+ per course, bloating the Course table.

4. **Missing: how to handle courses that already have RWGPS data but no track_points cached locally.** `rwgps.py` currently fetches track_points and encodes them to a polyline, discarding the per-point data. The draft says "add `fetch_route_track_points(route_id)`" but doesn't address whether to re-fetch all existing routes or only process new ones.

5. **No discussion of the HTML template's development/debugging workflow.** Creating a Leaflet+Plotly.js component as a raw HTML file with no build step means no linting, no type checking, no hot reload. For a 3–5 day effort, this friction matters.

6. **Downsampling strategy is vague.** "Cap to ~1k–2k points" and "keep every nth sample" but no mention of preserving shape-critical points (peaks, valleys, gradient transitions). Uniform downsampling can flatten climbs.

### Gaps in Risk Analysis

1. **No risk entry for "climb detection produces wrong results on real data."** The algorithm is well-specified but untested against actual PNW courses. Threshold tuning (600m / 35m / 3%) is acknowledged as an open question but not listed as a risk.

2. **No risk for DB migration.** Adding columns to `Course` without Alembic is a pattern the project uses, but the draft doesn't address how existing rows get backfilled or what happens if the extraction CLI fails partway through.

3. **No risk for payload size variance.** Some RWGPS routes may have 50k+ track points; the draft mentions downsampling but doesn't address the extraction-time cost or memory usage for very long routes.

4. **Missing: CDN availability risk.** The component loads Leaflet and Plotly.js from CDNs. If the user is offline or behind a firewall, the component is blank. No mention of vendoring or offline fallback.

### Missing Edge Cases

1. **Out-and-back courses** where the polyline overlaps itself — climb detection works fine, but the map display will have overlapping gradient-colored segments.
2. **Multi-lap courses** (crits) where the RWGPS route is a single lap — profile extraction is fine, but "typical speed" using single-lap distance is wrong. The draft acknowledges this for speed but not for profile display (should the UI indicate "single lap shown"?).
3. **Courses with no elevation gain** (flat crits, track races) — climb detection returns empty, which is fine, but the narrative generator needs to handle "no climbs" gracefully. Not explicitly tested.
4. **Very short courses** (< 5km) — the 600m minimum climb length means most of the course could be a single climb. Thresholds may need adjustment.
5. **Negative elevation routes** (net downhill point-to-point) — the profile and narrative should handle this; not discussed.

### Definition of Done Completeness

The DoD is well-structured across Functional, Data+Performance, and Testing categories. However:

- **Missing: narrative content verification.** No DoD item checks that the narrative reads correctly for different course types (flat crit, hilly road race, mountainous stage).
- **Missing: mobile/responsive verification.** The risk table mentions mobile, but the DoD doesn't include a mobile rendering check.
- **Missing: CLI command works end-to-end.** The `course-profile-extract` CLI command is described in implementation but not in the DoD.
- **"pytest passes and ruff check passes"** is good but should be the baseline, not a DoD item.

### Architecture Concerns

1. **JSON blobs vs. normalized tables is the right short-term call**, but the draft should be explicit that Sprint 009's "key moments" feature will almost certainly require querying climb data across courses, at which point the JSON approach becomes a liability. A note saying "expect to normalize in Sprint 009" would help.

2. **The HTML component is a maintenance liability.** Raw HTML/JS with no build tooling, embedded in a Python project, will be hard to iterate on. The draft should acknowledge this and propose a path to a proper Streamlit custom component if the feature proves valuable.

3. **Plotly.js in the iframe is heavy.** Plotly.js minified is ~3.5MB. For a simple area chart with hover events, Chart.js (~200KB) or even a hand-rolled SVG/Canvas chart would be lighter. The draft chose Plotly for consistency with the existing stack but didn't evaluate the bundle size tradeoff.

---

## Gemini Draft

### Strengths

1. **Clean, readable structure.** The document is well-organized and easy to follow. Use cases are concise and user-focused. The phasing table is clear.

2. **Correct identification of the Streamlit/Folium problem.** Like Codex, Gemini correctly identifies that `st_folium` triggers full reruns and proposes the same solution: a custom HTML component with client-side sync.

3. **Practical phasing.** Sprint 009 groups weather + pack odds + wind (all "decision support"), Sprint 010 groups replay + key moments (all "advanced visualization"). This is a sensible thematic grouping.

4. **Open Question #4 is critical.** "Do we already persist full track_points or just the encoded polyline?" This is the right question — the answer is that `rwgps.py` fetches track_points but only encodes them to a polyline, discarding elevation and distance. Gemini flagged this as needing verification before Phase 1, which is correct.

5. **SRI hashes for CDN dependencies.** Explicitly calls for Subresource Integrity, which is a good security practice.

### Weaknesses

1. **Algorithms are underspecified.** Climb detection is described as "sliding window with gradient > 4% for > 500m" — this is a sketch, not an algorithm. No smoothing window size, no merge logic, no handling of brief flat sections within a climb. The point-to-point gradient approach (without smoothing first) will produce extremely noisy results on real GPS data.

2. **Drop rate formula is oversimplified.** `(DNF + DQ + DNP) / Total Starters` is the right idea, but: what is "Total Starters"? The `Result` model doesn't have a separate "starters" count; you'd need `field_size` (which may be missing) or `count(Result rows)` (which may undercount if only top finishers are scraped). Codex addresses this; Gemini does not.

3. **Speed calculation lacks distance validation.** "Query `Result.race_time_seconds` for the top 10 finishers and calculate speed using `Course.distance_m`" — but no mention of what happens when `distance_m` is wrong (crit lap routes), missing, or implausibly small. Codex has explicit plausibility filters; Gemini does not.

4. **No data persistence strategy.** Gemini describes computing climb segments and stats at query time but never discusses caching/persisting the results. This means every Race Preview page load would re-fetch RWGPS track_points and re-compute everything. Codex's DB-backed cache (Phase 1) is essential and entirely missing here.

5. **No profile resampling/downsampling.** RWGPS routes can have 10k–50k+ track_points. Gemini sends them directly to the HTML component as JSON. No discussion of payload size, downsampling, or performance impact.

6. **Narrative generator is hand-waved.** "A dynamic, plain-English summary" with one example, but no algorithm, no template structure, no handling of missing inputs, no qualitative bands. Codex provides a concrete five-step generation process with specific thresholds.

7. **Files summary is incomplete.** Missing: `raceanalyzer/queries.py` (needs new query functions), `raceanalyzer/db/models.py` (needs schema changes if persisting data), `raceanalyzer/cli.py` (batch extraction), `tests/test_queries.py`. Codex covers all of these.

8. **Chart.js vs. Plotly.js inconsistency.** The architecture section mentions "Chart.js or Plotly.js" and later commits to Chart.js. The existing codebase uses Plotly throughout. Introducing Chart.js adds a second charting library with different APIs, increasing maintenance burden. Should use Plotly.js for consistency or explicitly justify the switch.

9. **No phase timing or effort estimates.** Three phases listed but no indication of relative complexity or duration.

### Gaps in Risk Analysis

1. **Only three risks listed.** Major omissions:
   - No risk for data persistence / caching (because it's not in the plan).
   - No risk for payload size / mobile performance.
   - No risk for RWGPS availability or rate limiting.
   - No risk for tile usage (OpenStreetMap fair-use policy).
   - No risk for category naming inconsistency across years.
   - No risk for missing `field_size` affecting drop rate accuracy.

2. **"Noisy GPS Elevation Data" is listed as a risk but the mitigation is circular.** "Apply a moving average / smoothing function" — yes, but the algorithm section already assumes smoothing happens. The risk should be "smoothing may not be sufficient for very noisy data" or "smoothing parameters may need per-route tuning."

3. **No risk for the HTML component failing or being unmaintainable.** Both drafts propose this approach, but only Codex includes a fallback path (render existing Folium map + non-synced Plotly chart).

### Missing Edge Cases

1. **All the same edge cases missing from Codex**, plus:
2. **No graceful degradation specification.** Codex's DoD has explicit degradation paths (no RWGPS → show Folium; no history → suppress stats). Gemini's DoD says "Features degrade gracefully" but doesn't specify how.
3. **No handling of races with very few results** (< 5 finishers). The draft says "degrade if Total Starters < 10" but what about categories with only 3–4 finishers per edition?
4. **No handling of `race_time_seconds` being NULL** for many finishers (common in scraped data where only place is recorded).

### Definition of Done Completeness

The DoD is significantly weaker than Codex's:

- **">85% coverage" is a vanity metric** without specifying *what* needs coverage. Are we measuring function coverage? Branch coverage? The climb detection state machine has many branches that need explicit testing.
- **Missing: data persistence verification.** No DoD item for the profile/climb data being cached.
- **Missing: performance criteria.** No payload size limit, no page-load time expectation.
- **Missing: CLI/batch extraction.** No mention of a batch process to populate data.
- **Missing: specific degradation scenarios.** "Features degrade gracefully" is a wish, not a testable criterion.
- **Missing: ruff/linting check.**

### Architecture Concerns

1. **No data persistence is the biggest architectural gap.** Computing everything on-the-fly from RWGPS on every page load is unacceptable for production use. This is not a minor omission — it's a fundamental architectural decision that Gemini skipped.

2. **No profile resampling means the component will be slow or crash on long routes.** Sending 30k+ raw track_points as JSON to an iframe is a non-starter.

3. **Chart.js introduces framework inconsistency.** The project uses Plotly everywhere. Adding Chart.js means two charting libraries with different event models, different configuration patterns, and different bundle characteristics. If the goal is a lightweight alternative to Plotly.js, it should be explicitly justified.

4. **`extract_climb_segments` operating on raw track_points** (without resampling to uniform spacing first) means gradient calculations are sensitive to GPS sampling rate variations. Points close together produce wild gradient swings; points far apart miss short steep sections.

---

## Recommendation

**The Codex draft is substantially stronger and should serve as the primary basis for the merged sprint.**

### Why Codex wins

1. **Implementation readiness.** Codex's algorithms are concrete enough to code from directly. Gemini's require significant design work before implementation can begin — the climb detection, stats calculations, and narrative generator all need fleshing out.

2. **Data architecture.** Codex's Phase 1 (persist profile to DB, CLI batch extraction) is essential infrastructure that Gemini entirely omits. Without it, every feature downstream is slower, flakier, and harder to test.

3. **Edge case handling.** Codex systematically addresses data quality issues (missing field_size, implausible distances, crit lap ambiguity, small sample sizes) that Gemini ignores.

4. **Risk awareness.** Codex identifies 6 specific risks with Streamlit-specific context; Gemini identifies 3 generic risks. Codex includes fallback paths; Gemini does not.

5. **Definition of Done.** Codex's DoD is testable and specific (payload ≤ 300KB, profile extraction for 10 series, explicit degradation paths). Gemini's is vague (">85% coverage", "degrade gracefully").

### What to take from Gemini

1. **Open Question #4** (track_points persistence gap) is a genuine catch that Codex doesn't flag as prominently. The merged sprint should make this a Phase 0 task: verify that track_point data (with elevation and distance) can be retrieved for existing routes, and update `rwgps.py` if needed.

2. **SRI hashes** for CDN dependencies — Codex mentions this but Gemini is more explicit about it.

3. **Sprint 010 phasing of #11 (Enhanced Finish Type UX).** Gemini defers #11 to Sprint 010 alongside #19 and #28, while Codex puts it in Sprint 009. Gemini's placement is arguably better — #11 is a UX enhancement to an existing feature, not a prediction capability, so it fits better with the visualization sprint.

4. **Simpler language.** Gemini's use cases and overview are more accessible. The merged sprint should adopt Gemini's cleaner prose style for the overview/use-case sections while keeping Codex's technical depth for implementation.

### Key items for the merged sprint to address (from both drafts' gaps)

1. **Explicitly plan the track_points data recovery.** Existing routes had track_points fetched but only polylines stored. The profile extraction CLI must re-fetch route detail JSON from RWGPS for all matched routes.
2. **Choose Plotly.js over Chart.js** for the HTML component — consistency with the existing stack matters more than bundle size savings.
3. **Add shape-preserving downsampling** (e.g., Ramer-Douglas-Peucker or visvalingam) instead of naive nth-point sampling.
4. **Add a DoD item for the CLI batch command** and for narrative content review across course types.
5. **Acknowledge the HTML component's maintenance cost** and define when it would be promoted to a proper Streamlit custom component package.
6. **Add CDN offline fallback** or vendoring plan to the risk mitigations.
