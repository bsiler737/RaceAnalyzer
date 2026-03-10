# Sprint 008: P0 Race Intelligence (Foundation) — Course Profile, Climbs, Historical Stats, Narrative

## Overview

Sprint 008 is the first of a phased delivery of the 12 P0 “Race Intelligence” stories defined in `docs/sprints/drafts/SPRINT-008-INTENT.md` (sourced from `best_user_stories.md`). The P0 set is too large for a single sprint, so this draft deliberately scopes Sprint 008 to a self-contained, foundational deliverable: a Race Preview that (1) lets a rider *interactively* connect the course geography to its elevation profile, (2) highlights meaningful climbs, and (3) augments the existing finish-type prediction (Sprint 007) with the two most defensible historical stats (drop rate + typical speeds) plus a deterministic “What to Expect” narrative.

This sprint’s “done” state should feel like a product, not a demo: a rider can open a series preview on a phone and immediately answer:

- Where are the climbs, how steep are they, and where do they occur?
- How fast does my category typically finish here?
- How selective is the race (drop/attrition rate)?
- What is the likely race script (plain language), with graceful degradation when data is missing?

### Phasing the 12 P0 Stories across 3 sprints

Sprint 008 must be shippable on its own; subsequent sprints can iterate on the same surfaces.

**Sprint 008 (Foundations; self-contained deliverable)**
- #1 Interactive Course Map (upgrade from “static polyline” to course-point aware interactions)
- #2 Elevation Profile Overlaid on Map (map ↔ elevation sync within one component)
- #3 Climb Segments on Map (detected segments, gradient coloring)
- #16 Typical Finishing Speeds (historical by category, robust to noisy data)
- #17 Drop Rate (historical attrition by category)
- #18 “What to Expect” Summary (template-based narrative generator; deterministic)

**Sprint 009 (Decision support; weather + rider-facing probabilities)**
- #11 Predicted Finish Type — enhanced UX (confidence explanation, calibration language)
- #12 Pack Odds (probability-of-finishing-with-main-group; uses drop rate + difficulty)
- #20 Weather-Adjusted Predictions (Open-Meteo integration; adjusts speeds/attrition/finish-type confidence)
- #10 Wind Exposure Zones (coarse heuristic first; optional OSM refinement)

**Sprint 010 (Advanced visualization + “where it splits”)**
- #19 Predicted Key Moments on Map (pins based on terrain triggers + historical selection zones)
- #28 Animated Race Replay (lightweight replay from historical results; honest about data limits)

> Note on conventions: A top-level `CLAUDE.md` is not present in the repository at time of writing; this draft follows observable conventions from existing sprint drafts, `README.md`, `pyproject.toml` (ruff/pytest), and current module boundaries (`queries.py` as a testable aggregation layer; Streamlit UI composition; graceful degradation).

---

## Use Cases

1. **As a racer**, I can pan/zoom the course map and see my position on the elevation profile as I hover the profile, so I understand where climbs occur geographically.
2. **As a racer**, I can see detected climbs labeled with length, gain, and avg/max gradient, so I know where the decisive efforts are.
3. **As a racer**, I can see “Typical finishing speed” for my category (with a clear definition), so I know whether to expect a 23 mph or 28 mph day.
4. **As a racer**, I can see historical drop rate for my category, so I can plan fueling/pacing and set expectations (finish with pack vs. survive selection).
5. **As a racer**, I can read a short “What to Expect” narrative that translates the above into a practical race script.
6. **As a developer**, I can run a deterministic extraction step that persists a course elevation profile and climbs to the DB so the UI is fast and reproducible.
7. **As a developer**, I can unit test climb detection, drop rate, and speed computations with fixtures and edge cases (missing distance, missing times, small sample sizes).

---

## Architecture

### Current state (relevant)
- `raceanalyzer/ui/maps.py` renders a Folium map from `RaceSeries.rwgps_encoded_polyline` (no per-point distance/elevation).
- `raceanalyzer/db/models.py` has a `Course` row with aggregate elevation stats only (distance/gain/loss/etc), but does **not** store an elevation profile.
- `raceanalyzer/predictions.py` already provides:
  - `predict_series_finish_type()` (weighted historical frequency)
  - `predict_contenders()` (startlist → series history → category fallback)
- `raceanalyzer/ui/pages/race_preview.py` is the primary surface.

### Sprint 008 target state (minimal new “plumbing” + maximal user value)

**Key decision:** implement map↔elevation sync as a single Streamlit HTML component (Leaflet + Plotly.js inside an iframe) rather than trying to force bidirectional hover sync between Folium and a separate Streamlit chart.

Why:
- `streamlit-folium` interactions cause a full Streamlit rerun; hover-based sync becomes laggy and flickery.
- Folium is Python-rendered Leaflet; it does not naturally expose the JS event stream needed for “hover profile → move marker” without custom plumbing.
- A single embedded component can do instant hover/click sync entirely client-side.

**High-level data flow**

```
RWGPS route detail JSON (track_points) ──> persist_course_profile()
    ├── course_profile points (distance_m, lat, lon, elev_m, grade_pct_smooth)
    └── detected climbs (start/end distance, gain, length, grades, label)

DB ──> queries.get_race_preview()
    ├── course aggregates (already)
    ├── course profile + climbs (new)
    ├── historical stats (drop rate, speeds) (new)
    └── narrative (new, deterministic)

Race Preview (Streamlit) ──> render_course_profile_component(profile, climbs)
```

### Proposed storage (choose one; Sprint 008 recommends the simplest)

Option A (recommended for Sprint 008): **Add JSON blobs on `Course`**
- `Course.profile_json` (Text): downsampled array of points
- `Course.climbs_json` (Text): climb segments + summary stats
- Pros: no new tables, minimal ORM/query surface area, easy caching.
- Cons: less queryable for future analytics; JSON size management needed.

Option B: New table `course_points` + `course_climbs`
- Pros: queryable, scalable.
- Cons: more schema changes, more joins, more migration complexity without Alembic.

Given the “deliver value quickly” convention in prior sprints, Sprint 008 should use **Option A** and revisit normalization later if needed.

---

## Implementation

### Phase 0: Agree on definitions and guardrails (½ day)

Lock in user-facing definitions so the UI remains honest and consistent:
- **Typical finishing speed**: median of “front group speed proxy” across editions (see algorithm below), shown only when sample size ≥ `N_min` (default 3 editions).
- **Drop rate**: fraction of starters flagged DNF/DQ/DNP (or missing placing) in the results feed; shown with caveats if `field_size` is missing or inconsistent.
- **Climb**: sustained positive elevation gain meeting minimum gain/length/grade thresholds on a smoothed profile; designed to be stable across noisy RWGPS elevation.

### Phase 1: Persist a course elevation profile (DB-backed cache) (2–3 days)

**Goal:** eliminate “fetch RWGPS + compute profile” from the request path of the Race Preview page.

1. Add profile/climb JSON storage to `Course` (Option A).
2. Add a CLI command to populate/rebuild these for all courses with RWGPS ids (pattern consistent with existing CLI-per-feature).
3. Ensure graceful fallback: if no profile exists, still render map (existing) and stats.

**Profile generation algorithm (concrete)**

Input: RWGPS `track_points` (lat/lon/elevation). Output: downsampled points with distance + smoothed elevation + grade.

Steps:
1. **Parse points:** for each track point `i`, read `(lat_i, lon_i, elev_i)`.
2. **Compute cumulative distance:** haversine distance between successive points; `dist_i = dist_{i-1} + d(i-1,i)`.
3. **Resample to uniform spacing:** choose `step_m = 25–50m`. Interpolate lat/lon/elev to points at `0, step_m, 2*step_m, ...`.
4. **Smooth elevation:** moving average or triangular smoothing over `window_m = 200–300m` (in samples, `k = window_m/step_m`).
5. **Compute grade:** slope over a window using linear regression (more stable than point-to-point deltas):
   - For each index `i`, take points in `[i-k, i+k]`, fit `elev = a*dist + b`, grade_pct = `100*a`.
6. **Downsample for UI payload:** cap to ~1k–2k points (e.g., keep every `n`th sample), preserving shape.

Code sketch (pure Python; no new heavy deps):

```python
from dataclasses import dataclass
import json
from math import radians, sin, cos, asin, sqrt

@dataclass(frozen=True)
class CoursePoint:
    d_m: float
    lat: float
    lon: float
    elev_m: float
    elev_smooth_m: float
    grade_pct: float

def haversine_m(lat1, lon1, lat2, lon2) -> float:
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 6371000.0 * 2 * asin(sqrt(a))

def linreg_slope(xs: list[float], ys: list[float]) -> float:
    # returns slope a in y = a*x + b
    n = len(xs)
    if n < 2:
        return 0.0
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den = sum((x - x_mean) ** 2 for x in xs)
    return (num / den) if den > 0 else 0.0
```

### Phase 2: Climb detection + gradient coloring (2–3 days)

**Goal:** detect climbs that are meaningful to amateur racers (stable, not noisy), label them, and display them on both the profile and the map.

#### Climb detection algorithm (concrete)

Operate on the **smoothed, uniformly spaced** profile (from Phase 1). Use a state machine plus merging to avoid fragmentation.

Definitions:
- `min_len_m = 600`
- `min_gain_m = 35`
- `min_avg_grade_pct = 3.0`
- `enter_grade_pct = 2.5` (must be sustained for `enter_sustain_m = 150`)
- `exit_grade_pct = 1.0` (sustained for `exit_sustain_m = 200`)
- `merge_gap_m = 150` (merge climbs separated by brief flattening)

Algorithm:
1. Compute `grade_pct[i]` (already).
2. Walk the profile:
   - Enter climb when grade exceeds `enter_grade_pct` for `enter_sustain_m`.
   - Exit when grade drops below `exit_grade_pct` for `exit_sustain_m`.
3. For each candidate segment, compute:
   - length, gain, avg_grade = gain/length * 100
   - max_grade = max within segment
   - start/end distance; start/end lat/lon
4. Filter by thresholds (`min_len_m`, `min_gain_m`, `min_avg_grade_pct`).
5. Merge adjacent segments if gap ≤ `merge_gap_m` and combined avg_grade still ≥ threshold.

Grade-to-color mapping (for both map segments and profile shading):
- `< 0%`: blue (descent)
- `0–2%`: light gray (flat)
- `2–4%`: green (false flat / gentle climb)
- `4–7%`: orange (moderate)
- `7–10%`: red (steep)
- `>= 10%`: dark red (very steep)

Code sketch:

```python
@dataclass(frozen=True)
class Climb:
    start_d_m: float
    end_d_m: float
    length_m: float
    gain_m: float
    avg_grade_pct: float
    max_grade_pct: float
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float

def detect_climbs(points: list[CoursePoint]) -> list[Climb]:
    # 1) state-machine to find candidate segments
    # 2) compute metrics; filter; merge
    ...
```

### Phase 3: Drop rate + typical speeds (queries + predictions) (2–3 days)

**Goal:** compute two “hard-to-game” stats from existing `Result` rows and surface them as cards on Race Preview.

#### Drop rate (#17) algorithm (concrete)

For a given `(series_id, category)`:
1. Find races in the series with results in that category.
2. For each race:
   - `rows = all Result where race_id == race.id and race_category_name == category`
   - `denom = max(field_size)` if present and plausible else `len(rows)`
   - `drops = count(dnf or dq or dnp or place is NULL)`
   - `drop_rate_race = drops / denom` (skip if denom < 5)
3. Aggregate: median drop rate across editions (more robust than mean).
4. Output: `{median_drop_rate, sample_editions, methodology, caveats}`

Edge cases:
- If `field_size` is missing/inconsistent, note “based on observed result rows”.
- If sample size < 3 editions, show “insufficient history”.

#### Typical finishing speeds (#16) algorithm (concrete)

We need a defensible proxy given available data:
- We have `Result.race_time_seconds` for finishers.
- We have `Course.distance_m` (series-level) but may be missing or may represent a lap for crits.

Proposed definition (Sprint 008):
- **Typical speed** = median of `(course_distance_m / t_front)` across editions, where `t_front` is the median time of the first finishing group proxy.

Front-group proxy (because we don’t have mid-race telemetry):
- Use the first `K` finishers by place (default `K=10`) *who are not DNF/DQ/DNP and have non-null time*.
- Compute `t_front = median(race_time_seconds of those K)`.
- Compute `speed_mps = course_distance_m / t_front`; convert to mph/kph.
- Filter implausible speeds (configurable):
  - road race: 12–35 mph
  - criterium: 18–35 mph (but distance risk; see caveat below)

Distance caveat:
- If `course_distance_m < 5000` and race type is not `CRITERIUM`, treat distance as untrusted and suppress speed.
- If `course_distance_m < 2000`, suppress speed entirely (likely a single lap).

### Phase 4: Narrative generator (#18) (1–2 days)

**Goal:** deterministic, fast prose that combines the new stats with existing prediction output and course/climb context. Avoid LLM dependency for Sprint 008 (predictable, testable, no API keys).

Narrative algorithm (concrete)

Inputs:
- `course_type`, `distance_km`, `gain_m`
- climb list: biggest climb, number of climbs above threshold, last climb position (% distance)
- prediction: finish type + confidence (already)
- historical stats: drop rate, typical speed (new)

Generation steps:
1. **Course sentence**: terrain + distance + climbing (only include if present).
2. **Climb sentence**: if climbs exist, mention biggest climb and whether it’s late.
3. **Pace/attrition sentence**: typical speed + drop rate with qualitative bands.
4. **Tactics sentence**: map finish type to 1–2 tactical heuristics (“likely bunch sprint → protect position late; reduced sprint → survive climbs, then contest”).
5. **Caveats sentence**: if any input missing or sample small, append a short caveat.

Qualitative bands (shown to users; keep “no raw probabilities” convention):
- Drop rate:
  - `<10%`: “low attrition”
  - `10–25%`: “moderate attrition”
  - `>25%`: “high attrition”
- Speed (mph):
  - `<22`: “steady”
  - `22–26`: “fast”
  - `>26`: “very fast”

Code sketch:

```python
def generate_what_to_expect(context: dict) -> str:
    parts: list[str] = []
    # 1) course summary
    # 2) climbs + timing
    # 3) speeds + attrition
    # 4) finish-type tactics
    # 5) caveats
    return " ".join(p for p in parts if p)
```

### Phase 5: Map↔elevation sync in Streamlit (Leaflet component) (3–5 days; highest risk)

**Goal:** deliver story #2 credibly within the Streamlit stack.

#### The Folium/Streamlit interactivity challenge (explicit)
- Folium maps are rendered as HTML/JS; Streamlit’s Python runtime does not observe hover events without a component bridge.
- `st_folium()` can return click/viewport data, but each interaction triggers a rerun; it is unsuitable for high-frequency hover sync.

#### Sprint 008 solution (concrete)

Implement `render_course_profile_component(profile_points, climbs)` using `streamlit.components.v1.html` and a bundled HTML template that:
- Renders Leaflet map (polyline + gradient coloring + climb overlays).
- Renders elevation profile (Plotly.js area chart).
- Implements client-side sync:
  - Hover over profile → move map marker + highlight local polyline segment.
  - Click map (or drag marker along route) → move vertical cursor on profile.

Design constraints:
- All data passed into the component must be JSON-serialized (no string concatenation of untrusted content).
- Payload size must be bounded (downsample to ~1–2k points).
- Provide a fallback path:
  - If component fails (browser/Streamlit issues), render existing Folium map + a non-synced Plotly elevation chart.

Minimal JS sync approach:
- Use profile index as the shared key (`i` in `[0..n-1]`).
- Hover event returns `i`; map marker snaps to `points[i]`.
- For map click, compute nearest index via a fast linear scan on a downsampled subset (good enough at n~1k) or a simple grid bin.

---

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/db/models.py` | MODIFY | Add `Course.profile_json` and `Course.climbs_json` (Option A), plus any timestamps needed. |
| `raceanalyzer/rwgps.py` | MODIFY | Add `fetch_route_track_points(route_id)` (returns track_points) or extend existing fetch to return per-point data. |
| `raceanalyzer/elevation.py` | MODIFY | Add profile building helpers + `detect_climbs()`; keep existing `classify_terrain()` intact. |
| `raceanalyzer/predictions.py` | MODIFY | Add historical stats helpers (drop rate, typical speed) and narrative generator (deterministic templates). |
| `raceanalyzer/queries.py` | MODIFY | Extend `get_race_preview()` to include `profile_points`, `climbs`, `drop_rate`, `typical_speed`, `narrative`. |
| `raceanalyzer/ui/maps.py` | MODIFY | Keep `render_course_map()`; add `render_course_profile_component()` wrapper for the new embedded component. |
| `raceanalyzer/ui/pages/race_preview.py` | MODIFY | Replace “map-only” block with the synced component; add Historical Stats + What to Expect cards. |
| `raceanalyzer/ui/templates/course_profile_component.html` | CREATE | Leaflet + Plotly.js template with sync logic (no external build step). |
| `raceanalyzer/cli.py` | MODIFY | Add `course-profile-extract` command to populate profile/climb JSON for courses. |
| `tests/test_elevation.py` | MODIFY | Add tests for profile smoothing + climb detection on synthetic profiles. |
| `tests/test_predictions.py` | MODIFY | Add tests for drop rate, typical speed, and narrative output (golden strings / snapshot-ish). |
| `tests/test_queries.py` | MODIFY | Add integration-style tests for `get_race_preview()` new keys + graceful degradation. |

---

## Definition of Done

### Functional
- [ ] Race Preview page renders a **single interactive course component** (map + elevation) when `Course.profile_json` exists.
- [ ] Hovering the elevation profile moves a map marker instantly (no full-page rerun flicker).
- [ ] Detected climbs render as labeled segments with consistent coloring (and are stable across reruns).
- [ ] Race Preview shows:
  - [ ] Typical finishing speed (when distance + times are sufficient), with sample size.
  - [ ] Drop rate (when results are sufficient), with sample size.
  - [ ] “What to Expect” narrative (deterministic; includes caveats when inputs missing).
- [ ] All features degrade gracefully:
  - [ ] If no RWGPS route id / no track_points: show existing Folium map (if polyline exists) and suppress profile/climbs.
  - [ ] If insufficient history: suppress stats and show a clear “insufficient history” note.

### Data + performance
- [ ] Profile extraction persists downsampled points (bounded size) and climbs for at least 10 representative series without manual intervention.
- [ ] Race Preview does not fetch RWGPS over the network on page load for series with cached profiles.
- [ ] Component payload ≤ ~300KB typical (downsampling enforced).

### Testing
- [ ] Unit tests cover climb detection thresholds, merging behavior, and noise robustness.
- [ ] Unit tests cover drop-rate and speed calculations with:
  - missing `field_size`
  - missing `race_time_seconds`
  - untrusted distance heuristics (crit/lap-like distance)
- [ ] `pytest` passes and `ruff check .` passes.

---

## Risks

| Risk | Why it’s specific to Streamlit/Folium | Mitigation |
|------|---------------------------------------|------------|
| Map↔profile sync is janky or impossible via `st_folium` | Folium runs in JS; Streamlit reruns Python per interaction; hover sync becomes unusable | Use a single embedded Leaflet+Plotly component with client-side JS sync; keep Folium as fallback. |
| Large polylines make the component slow on mobile | Streamlit iframe payload + Leaflet polyline rendering can lag at >5k points | Resample/downsample profile + polyline; segment the polyline only at color boundaries; cap points. |
| CSS/layout issues (iframe height, responsiveness) | Streamlit component sizing can be finicky across devices | Fixed height + responsive width; test on narrow viewport; provide “expand” toggle. |
| Tile usage / rate limiting | OpenStreetMap tiles have usage expectations; Folium/Leaflet can generate many requests during pan/zoom | Use a single light tile layer; document fair use; consider Carto/MapTiler later. |
| RWGPS availability / schema variance | Track point fields may differ (`x/y/e` vs `lng/lat/elevation`) | Robust parsing with fallbacks; tests with captured fixture JSON. |
| “Typical speed” is misleading when distance is wrong | RWGPS route may not represent full race distance (e.g., crit lap route) | Suppress speed when distance is implausible; always show methodology + sample size. |

---

## Security

- **HTML component injection safety:** embed data as JSON only (e.g., `json.dumps(...)` into a `<script type="application/json">` tag) and parse with `JSON.parse`, never by string concatenation of user input.
- **CDN risk:** if the component uses CDN-hosted JS (Leaflet/Plotly), pin versions and prefer integrity hashes if feasible; consider vendoring later if stability becomes an issue.
- **Network calls:** RWGPS and Nominatim calls must have timeouts and descriptive User-Agent (already present). Do not introduce API keys in code or docs.

---

## Dependencies

### Existing (no new heavy Python deps targeted for Sprint 008)
- `streamlit`, `plotly`, `folium`, `streamlit-folium`, `pandas`, `sqlalchemy`, `requests`.

### External services
- RWGPS route detail JSON (`https://ridewithgps.com/routes/{id}.json`) for track points/elevation.
- OpenStreetMap (or CartoDB tiles) for map rendering.

---

## Open Questions

1. **Where should the profile data live long-term?** Sprint 008 recommends `Course.profile_json`/`Course.climbs_json` for speed of delivery. If we expect to query “all climbs across courses” later (Sprint 010 key moments), should we normalize into tables in Sprint 009?
2. **Crit distance ambiguity:** Do RWGPS routes for crits in this dataset represent a lap or the full race? If lap-only, should we suppress “typical speed” for crits entirely in Sprint 008 and only re-enable once we can infer total distance from results metadata (if available)?
3. **Category normalization:** Drop rate and speed are category-string keyed. If category naming is inconsistent across years, do we need a category alias map before we can trust these stats?
4. **Component ownership:** Should the synced component fully replace Folium on Race Preview, or should we keep Folium as the default map and only use the component for “Profile view”?
5. **Climb definition tuning:** Are the proposed thresholds (600m / 35m / 3%) aligned with PNW amateur perception, or should we tune via a small labeled set of known climbs?

