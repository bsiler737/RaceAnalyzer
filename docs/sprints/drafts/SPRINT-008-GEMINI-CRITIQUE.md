# Sprint 008 Draft Critique

## Claude Draft (`SPRINT-008-CLAUDE-DRAFT.md`)

### 1. Strengths
- **Implementation Detail:** Extremely granular, providing concrete code sketches for DB models, UI components, and algorithms.
- **UI Architecture:** The solution for the Streamlit/Folium latency issue (a custom HTML component bundling Leaflet and Plotly.js) is well-reasoned and definitively solves the hover-sync problem.
- **Security:** Excellent attention to detail regarding XSS prevention and CDN script integrity (SRI hashes).
- **Graceful Degradation:** Clearly defines how every UI element should behave if data is missing.

### 2. Weaknesses
- **Data Storage:** Proposes storing raw (or minimally downsampled) `track_points_json`. This could lead to significant DB bloat and slow UI rendering if large arrays are serialized/deserialized on every page load.
- **Compute at Runtime:** The draft implies that climb segments are computed on-the-fly from the track points during the request, which adds unnecessary latency.
- **Stats Algorithm:** Uses a weighted average for drop rates, which can be easily skewed by a single outlier year with terrible weather.

### 3. Gaps in Risk Analysis
- **Iframe Layout Constraints:** While it mentions explicit height, it underestimates the difficulty of making complex interactive iframe components truly responsive and scroll-friendly on mobile within Streamlit's layout engine.
- **Inaccurate Distances:** Fails to recognize that RWGPS route distances are often wrong for criteriums or circuit races (representing one lap instead of the total race distance).

### 4. Missing Edge Cases
- **Criterium Distances:** Using course distance to calculate "Typical Finishing Speed" will produce wildly inaccurate (slow) results for crits if the course is only a 1km lap but the race is 40 minutes.
- **DQ Handling:** An open question asks whether to include DQs as drops. DQs are usually rules infractions, not an indicator of course selectivity/attrition, and should ideally be excluded from "drop rate" to avoid misleading users.

### 5. Definition of Done Completeness
- Very thorough. Covers data layer, algorithms, UI integration, and specifies testing requirements well. However, it lacks a performance/payload size constraint for the UI component.

### 6. Architecture Concerns
- Storing high-resolution track points and computing climbs dynamically creates a bottleneck on the read path.

---

## Codex Draft (`SPRINT-008-CODEX-DRAFT.md`)

### 1. Strengths
- **Pre-computed Storage:** Correctly identifies that `profile_json` (downsampled) and `climbs_json` should be pre-computed and stored in the DB, optimizing the critical read path for the Race Preview page.
- **Robust Statistics:** Uses medians instead of averages for typical speeds and drop rates, making the metrics much more resilient to outlier editions (e.g., a neutralized race or a torrential downpour year).
- **Domain Awareness:** Explicitly calls out the "crit distance ambiguity" and proposes a sensible heuristic (suppressing speed for short laps).

### 2. Weaknesses
- **Climb Detection Complexity:** The linear regression approach for calculating gradient might be overly complex and could mask short, sharp, decisive kicks ("berg" style climbs) depending on the window size.
- **UI Implementation Details:** Less specific on the exact mechanics of the custom HTML component compared to Claude (e.g., no mention of CDN security or bundle size mitigation strategies like lazy loading).

### 3. Gaps in Risk Analysis
- **Algorithmic Lock-in:** By storing pre-computed `climbs_json`, any future tweaks to the climb detection algorithm will require a full database migration/re-extraction. The draft doesn't highlight this tradeoff.
- **Plotly Bundle Size:** Doesn't address the performance impact of loading Plotly.js (which can be massive) into the client browser.

### 4. Missing Edge Cases
- **Fragmented Climbs:** While it mentions merging climbs separated by a brief flattening, it doesn't clearly handle the edge case of a "stepped" climb where the flat section itself has a slight negative gradient.
- **Small Field Sizes:** Doesn't explicitly define how the "front group proxy" (top K finishers) scales if the total field size is less than K.

### 5. Definition of Done Completeness
- Strong, particularly because it includes a specific performance constraint ("Component payload ≤ ~300KB typical") which forces downsampling.

### 6. Architecture Concerns
- The decision to use Option A (JSON blobs on `Course`) is correct for Sprint 008 velocity, but the linear regression smoothing might be harder to tune than a simple Gaussian blur.

---

## Recommendation

**The merged sprint should lead with Codex's data architecture and statistical robustness, but utilize Claude's UI component design and climb detection simplicity.**

**Codex's approach is slightly stronger overall** because it pre-computes the heavy lifting (`profile_json` and `climbs_json`), ensuring the Race Preview page remains fast. Its use of medians for historical stats and its awareness of the criterium distance problem show a deeper understanding of the domain data quirks.

**What to take from Codex:**
- **Storage:** Pre-compute and store downsampled `profile_json` and `climbs_json` on the `Course` model to guarantee fast page loads.
- **Stats:** Use medians for drop rate and typical speed calculations.
- **Domain Logic:** Implement the distance heuristics (suppressing speed calculations for suspected single-lap criterium routes).
- **DoD:** Keep the strict <300KB payload constraint for the HTML component.

**What to take from Claude:**
- **UI Component:** Use the detailed Leaflet + Plotly.js iframe implementation, including SRI hashes, specific CDN versions, and responsive stacking logic.
- **Climb Algorithm:** Use the simpler Gaussian smoothing approach for elevation data before applying the state machine, rather than linear regression.
- **Security:** Adopt the strict XSS prevention guidelines for data injected into the HTML template.