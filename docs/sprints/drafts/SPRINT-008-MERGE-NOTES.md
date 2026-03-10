# Sprint 008 Merge Notes

## Claude Draft Strengths
- Best UI component design: detailed Leaflet + Plotly.js spec with SRI hashes, responsive layout, CDN pinning
- Strongest graceful degradation specification — every feature has an explicit fallback path
- Comprehensive risk table (8 risks) with specific mitigations
- Good climb detection algorithm: Gaussian smoothing + state machine with hysteresis
- Correct identification of track_points data gap (polyline only, no elevation per point)
- Well-structured narrative generator with 3 independent sentences

## Codex Draft Strengths
- Best data architecture: pre-computed `profile_json` + `climbs_json` stored on Course (not computed at render time)
- Most robust statistical approach: medians over averages, explicit outlier filtering
- Critical domain awareness: crit distance ambiguity, "front group proxy" for speed, distance plausibility filters
- Climb detection includes merge step for fragmented climbs separated by brief flats
- Uniform resampling before analysis (normalizes GPS sampling rate variance)
- Performance constraint in DoD: payload ≤ 300KB
- Phase 0 "agree on definitions" step — locks down semantics before implementation
- Strongest Definition of Done overall

## Gemini Draft Strengths
- Cleanest prose / most readable overview and use cases
- Correctly flagged track_points persistence as open question #4
- Explicit SRI hash requirement for CDN dependencies

## Valid Critiques Accepted
- **From all three:** Gemini's algorithms are underspecified; can't implement from the draft alone
- **From Claude (critiquing Codex):** Phase 5 (map sync) is underspecified relative to risk; needs explicit fallback
- **From Claude (critiquing Gemini):** No data persistence strategy is a fundamental gap
- **From Codex (critiquing Claude):** Needs a "cut ladder" for when time runs short
- **From Codex (critiquing Claude):** DQ/DNF/DNP semantics inconsistency must be resolved
- **From Codex (critiquing Gemini):** Chart.js introduces framework inconsistency; use Plotly.js
- **From Gemini (critiquing Claude):** Pre-compute climbs at extraction time, not at render time
- **From Gemini (critiquing Codex):** Linear regression grade may mask short steep kicks; prefer Gaussian smoothing
- **From all three:** Crit distance ambiguity must be handled (suppress speed for crits)

## Valid Critiques Rejected
- **Codex's "JSON blobs are a liability for Sprint 009":** True long-term, but Sprint 008 needs speed of delivery. Normalize in Sprint 009 only if cross-course querying is needed.
- **Claude's "Plotly.js is too heavy":** Plotly basic bundle (~400KB) is acceptable; Chart.js would introduce a second charting framework.

## Interview Refinements Applied
1. **Drop rate = DNF + DNP only.** Exclude DQ (rules infraction, not attrition). Locked into function signature, UI copy, and tests.
2. **Suppress speed for criteriums.** If `race_type == CRITERIUM`, skip speed calculation entirely in Sprint 008.
3. **Fallback for map-elevation sync:** Side-by-side Folium map + Plotly elevation chart (no hover sync). Ship everything else.
4. **Cut ladder:** Map+Climbs (#1/#2/#3) → Stats (#16/#17) → Narrative (#18). The interactive map with climb visualization is the highest-value deliverable.

## Merge Decisions
- **Storage:** Codex's pre-computed approach (`profile_json` + `climbs_json` on Course)
- **Climb detection:** Claude's Gaussian smoothing + state machine, with Codex's merge step
- **Grade computation:** Claude's Gaussian smoothing (simpler, preserves short kicks) over Codex's linear regression
- **Stats:** Codex's median-based approach with outlier filtering and distance plausibility checks
- **UI component:** Claude's Leaflet + Plotly.js design with SRI hashes, responsive layout
- **Fallback:** Side-by-side (Folium + Plotly) if custom component proves too complex
- **Narrative:** Claude's 3-sentence structure with Codex's qualitative bands
- **Phasing:** All three agree: 008 = map+stats+narrative, 009 = weather+odds+wind, 010 = moments+replay
- **DoD:** Merge of Codex (performance constraints, CLI verification) + Claude (degradation paths, testing)
