# Sprint 008: Interactive Course Intelligence & Historical Race Stats

## Overview

Sprint 008 delivers the foundational layer of P0 race intelligence: an interactive course map synced with an elevation profile, climb segment visualization, historical race statistics (drop rate, finishing speeds), and a template-driven "What to Expect" narrative. By the end of this sprint, the Race Preview page transforms from a static summary into an interactive course exploration tool backed by historical data — the single most valuable upgrade for a racer preparing for an unfamiliar event.

**Why these 6 stories first:** Stories #1, #2, #3 are the spatial foundation — every future map feature (#10 wind zones, #19 key moments, #28 replay) renders on top of this interactive map. Stories #16, #17, #18 are the simplest prediction extensions — they query existing `Result` data with straightforward aggregation, require no external APIs, and produce the inputs for the narrative generator. Together, these 6 stories form a self-contained deliverable: a racer opens Race Preview and sees an interactive map with climbs highlighted, historical stats, and a plain-English race summary.

**What's deferred and why:** Wind exposure (#10) requires external geodata. Pack odds (#12) requires a probability model. Weather (#20) requires an external API. Key moments (#19) and replay (#28) require correlating spatial data with historical gap data — the hardest algorithmic work. All build on the foundation this sprint establishes.

### P0 Story Phasing Across 3 Sprints

| Sprint | Stories | Theme |
|--------|---------|-------|
| **008** (this sprint) | #1, #2, #3, #16, #17, #18 | Interactive map + elevation + climbs + historical stats + narrative |
| **009** | #10, #11, #12, #20 | Wind exposure, enhanced finish type UX, pack odds, weather integration |
| **010** | #19, #28 | Key moments on map, animated race replay |

### Cut Ladder

If time runs short, deliver in this priority order:

1. **Must ship:** Interactive map + elevation profile + climb segments (#1, #2, #3)
2. **Should ship:** Drop rate + typical speeds (#17, #16)
3. **Nice to ship:** "What to Expect" narrative (#18)

The interactive map with climb visualization is the highest-value deliverable. Stats and narrative can ship in a fast follow-up if needed.

**Duration**: ~2-3 weeks
**Prerequisite**: Sprint 007 complete (Course model, baseline predictions, Race Preview page, Folium course map)

---

## Use Cases

1. **As a racer**, I can pan, zoom, and explore the course on an interactive map with the route highlighted, so I can identify key turns and landmarks before race day. _(#1)_
2. **As a racer**, I can see an elevation profile chart synced to the map — hovering over the profile moves a marker on the map — so I can connect "that big climb at mile 12" to an actual place on the route. _(#2)_
3. **As a racer**, I can see individual climbs color-coded by gradient severity (moderate / steep / brutal) on both the map and the elevation profile, so I immediately know where the hard efforts are. _(#3)_
4. **As a racer**, I can see the historical drop rate for my category (e.g., "32% of Cat 4 starters DNF'd or were dropped"), so I know how selective the race is. _(#17)_
5. **As a racer**, I can see typical finishing speeds from past editions (e.g., "Winning group averaged 24.1 mph"), so I know whether the pace is within my fitness. _(#16)_
6. **As a racer**, I can read a "What to Expect" narrative summarizing the race in plain English — terrain character, expected finish type, historical selectivity, and pacing context — so I can mentally prepare even though I've never done this event. _(#18)_
7. **As a developer**, I can call `detect_climbs()` with course profile points and get back structured climb segments with gradient, length, and coordinates.
8. **As a developer**, I can call `calculate_drop_rate()` and `calculate_typical_speeds()` with a series_id and category, and get back structured data that degrades gracefully when history is sparse.

---

## Architecture

### Phase 0 Definition: Drop Rate

**Drop rate = DNF + DNP only.** DQ (disqualified) is excluded — it indicates a rules infraction, not course attrition. This definition is locked into function signatures, UI copy, and tests.

### Critical Data Gap: Track Points

The existing system stores only encoded polylines (`RaceSeries.rwgps_encoded_polyline`), which decode to `[(lat, lon), ...]` — no elevation or distance-along-route data. Stories #1-#3 all require per-point elevation.

**Solution: Pre-compute and store profile + climbs in DB.** Add `profile_json` and `climbs_json` TEXT columns to the `Course` model. Populate during a CLI extraction step (following the `elevation-extract` pattern). This eliminates RWGPS network calls from the page-load path and ensures fast, reproducible rendering.

Storage format for `profile_json`:
```json
[{"d": 0, "e": 152.3, "y": 47.61, "x": -122.33, "g": 2.1}, ...]
```
- `d`: cumulative distance (meters)
- `e`: smoothed elevation (meters)
- `y`: latitude
- `x`: longitude
- `g`: smoothed gradient (percent)

Downsampled to ~1 point per 50m (~2000 points for a 100km course). Payload target: ≤ 300KB per course.

Storage format for `climbs_json`:
```json
[{"start_d": 12400, "end_d": 14200, "length_m": 1800, "gain_m": 108, "avg_grade": 6.0, "max_grade": 9.2, "category": "steep", "color": "#FF5722", "start_coords": [47.61, -122.33], "end_coords": [47.62, -122.34]}, ...]
```

### Map-Elevation Sync: The Streamlit/Folium Challenge

**The Problem:** Folium maps rendered via `st_folium` trigger a full Streamlit script rerun on interaction. There's no way to listen to a Plotly hover event and update a Folium marker without a server roundtrip, causing unacceptable lag.

**Primary approach: Custom HTML component via `streamlit.components.v1.html`.** Bundles Leaflet.js (map) and Plotly.js (elevation chart) in a single HTML page rendered as an iframe. Python serializes profile points + climb segments as JSON and injects them into the template. JavaScript handles all hover/sync interactions client-side with zero server roundtrips.

Key design choices:
- **Plotly.js** for the elevation chart (matches existing Plotly usage in the project)
- **Leaflet.js** inside the component (Folium wraps Leaflet; using it directly gives full JS control)
- **CartoDB Positron tiles** (matches existing map aesthetic, no API key needed)
- **SRI hashes** on CDN scripts (Leaflet 1.9.4, Plotly 2.35.0 basic bundle)
- **Responsive layout:** map 60% / chart 40% above 768px; stacks vertically on mobile

**Fallback approach (if custom component proves too complex):** Render existing Folium map + separate Plotly elevation chart side-by-side in Streamlit. No hover sync, but both views are present with climb overlays. Ship everything else (stats, narrative, climbs on map) and revisit sync in Sprint 009.

### Climb Detection Algorithm

A two-pass approach over uniformly resampled, smoothed profile points:

**Pass 1: Resampling and Smoothing.**
1. Parse RWGPS track_points: `(lat, lon, elevation)` per point
2. Compute cumulative distance via haversine
3. Resample to uniform 25-50m spacing (interpolate lat/lon/elevation)
4. Apply Gaussian-weighted rolling average with 200m window to elevation (preserves real gradient changes, eliminates ±3-5m GPS jitter)
5. Compute gradient at each point using smoothed elevation

**Pass 2: State machine detection with merge step.**

```
State: FLAT (default)
  → if gradient ≥ 2.5% sustained for 150m: transition to CLIMBING, record start
State: CLIMBING
  → if gradient < 1.0% sustained for 200m: transition to FLAT, record end
  → accumulate: total gain, max gradient, average gradient, length
```

Post-processing:
- **Merge** adjacent climbs separated by ≤ 150m gap (prevents fragmented climbs from brief false flats)
- **Filter** by minimum thresholds: length ≥ 500m, gain ≥ 20m, average gradient ≥ 3%

**Climb categorization by average gradient:**

| Category | Avg Gradient | Color | Label |
|----------|-------------|-------|-------|
| Moderate | 3-5% | `#FFC107` (amber) | "Moderate climb" |
| Steep | 5-8% | `#FF5722` (deep orange) | "Steep climb" |
| Brutal | 8%+ | `#B71C1C` (dark red) | "Brutal climb" |

### Historical Stats Algorithms

**Drop Rate (#17):**

```python
def calculate_drop_rate(session, series_id, category=None) -> dict | None:
    """Calculate historical attrition rate (DNF + DNP only; excludes DQ).

    Returns: {
        "drop_rate": float (0.0-1.0),
        "total_starters": int,
        "total_dropped": int,
        "edition_count": int,
        "label": "low" | "moderate" | "high" | "extreme",
        "confidence": "high" | "moderate" | "low",
    }
    Returns None if no historical data.
    """
```

Per-edition: count starters from `len(Result rows)` (fall back from `field_size` which may be missing). Count dropped = rows where `dnf=True OR dnp=True`. Compute per-edition drop rates, then take the **median** across editions (robust to outlier years with extreme weather).

**Label mapping:** <10% → "low", 10-25% → "moderate", 25-40% → "high", >40% → "extreme"
**Confidence:** 3+ editions with 10+ starters each → "high", 2 editions or small fields → "moderate", 1 edition → "low"

**Typical Finishing Speeds (#16):**

```python
def calculate_typical_speeds(session, series_id, category=None) -> dict | None:
    """Calculate historical finishing speeds. Requires Course.distance_m.

    Suppressed entirely for criteriums (race_type == CRITERIUM) because
    RWGPS routes typically represent a single lap, not total race distance.

    Returns: {
        "median_winner_speed_mph": float,
        "median_field_speed_mph": float,
        "median_winner_speed_kph": float,
        "median_field_speed_kph": float,
        "edition_count": int,
        "confidence": "high" | "moderate" | "low",
    }
    Returns None if distance, timing data, or race type makes speed unreliable.
    """
```

Per-edition "front group proxy": take the top K=10 finishers (by place, not DNF, with non-null `race_time_seconds`). Compute `speed = Course.distance_m / race_time_seconds * 3.6` (kph). Filter outliers: discard speeds < 15 kph or > 55 kph. Take median across editions.

**Distance plausibility checks:**
- If `race_type == CRITERIUM`: suppress speed entirely (single-lap distance)
- If `Course.distance_m < 5000` and race type is not CRITERIUM: suppress (likely a single lap)
- If `Course.distance_m` is NULL: return None
- If < 50% of results have `race_time_seconds`: return None

### Narrative Generator (#18)

Template-based, deterministic, fast, and testable. No LLM dependency.

```python
def generate_narrative(
    course_type: str | None,
    predicted_finish_type: str | None,
    drop_rate: dict | None,
    typical_speed: dict | None,
    distance_km: float | None,
    total_gain_m: float | None,
    climbs: list[dict] | None,
    edition_count: int = 0,
) -> str:
```

**Structure (3-5 sentences, each independently optional):**

1. **Course sentence:** Terrain + distance + climbing summary
   - Flat: "This {distance} km flat course has minimal climbing — positioning and pack tactics matter more than raw power."
   - Hilly: "This {distance} km course packs {gain}m of climbing across {n} significant climbs."
   - Mountainous: "This {distance} km mountain course packs {gain}m of climbing — expect the field to shatter on the climbs."

2. **Climb sentence (if climbs detected):** Highlights the biggest/last climb
   - "The hardest climb is a {length}m {category} effort averaging {grade}% — and it comes in the final quarter of the race."

3. **History sentence:** Finish type + selectivity
   - "Based on {n} previous editions, this race typically ends in a {finish_type}."
   - With drop rate: "Historically {rate}% of starters are dropped or DNF — {qualifier} for the category."
   - Qualitative bands: "fairly typical" (<15%), "moderately selective" (15-30%), "quite selective" (30-45%), "brutally selective" (>45%)

4. **Pacing sentence (if speed available):**
   - "The winning group usually averages around {speed} mph ({kph} kph)."

5. **Caveat (if data is limited):**
   - "Based on limited history (1 edition) — take these numbers with a grain of salt."

Each sentence is independently optional. If no data at all: "This is a new event — no historical data is available yet."

---

## Implementation

### Phase 1: Profile Extraction & Storage (~25% effort)

**Goal:** Persist pre-computed course profiles and climb data in the DB, eliminating RWGPS calls from the page-load path.

**Files:**
- `raceanalyzer/db/models.py` — Add `profile_json` and `climbs_json` TEXT columns to `Course`
- `raceanalyzer/rwgps.py` — Add `extract_track_points()` to parse RWGPS route JSON into structured points
- `raceanalyzer/elevation.py` — Add profile building: `resample_profile()`, `smooth_elevations()`, `compute_gradients()`
- `raceanalyzer/cli.py` — Add `course-profile-extract` CLI command
- `tests/test_elevation.py` — Profile building tests

**Tasks:**
- [ ] Add `profile_json` and `climbs_json` columns to `Course` model
- [ ] Implement `extract_track_points(route_json)` in `rwgps.py`: parse lat/lon/elevation, compute haversine cumulative distance
- [ ] Implement `resample_profile(track_points, step_m=50)`: uniform spacing via interpolation
- [ ] Implement `smooth_elevations(profile, window_m=200)`: Gaussian-weighted rolling average
- [ ] Implement `compute_gradients(profile)`: gradient at each point from smoothed elevation
- [ ] Implement `course-profile-extract` CLI: fetch RWGPS route JSON → build profile → detect climbs → persist to Course
- [ ] Re-run extraction for all series with `rwgps_route_id` to populate new columns
- [ ] Tests: profile from synthetic track_points, haversine accuracy, smoothing preserves total gain within 5%

### Phase 2: Climb Detection (~15% effort)

**Goal:** Detect meaningful climbs from course profiles using a state machine with merge step.

**Files:**
- `raceanalyzer/elevation.py` — Add `detect_climbs()` with state machine + merge logic
- `raceanalyzer/config.py` — Add climb detection thresholds to Settings
- `tests/test_elevation.py` — Climb detection tests

**Tasks:**
- [ ] Implement `detect_climbs(profile_points)` state machine: enter at 2.5% sustained 150m, exit at 1.0% sustained 200m
- [ ] Implement merge step: adjacent climbs with gap ≤ 150m are merged
- [ ] Implement post-filter: length ≥ 500m, gain ≥ 20m, avg gradient ≥ 3%
- [ ] Add `Climb` dataclass with start/end distance, gain, gradients, category, color, coordinates
- [ ] Add configurable thresholds to `Settings` dataclass
- [ ] Tests: single steady climb, climb with false flat (merge), two separate climbs, flat course (0 climbs), noisy data, short course, very short ramp (filtered out)

### Phase 3: Historical Stats Engine (~20% effort)

**Goal:** Compute drop rate and typical finishing speeds from existing Result data.

**Files:**
- `raceanalyzer/predictions.py` — Add `calculate_drop_rate()`, `calculate_typical_speeds()`
- `raceanalyzer/queries.py` — Update `get_race_preview()` to include new stats
- `tests/test_predictions.py` — Stats tests

**Tasks:**
- [ ] Implement `calculate_drop_rate(session, series_id, category)`: DNF + DNP only, median across editions, label + confidence
- [ ] Implement `calculate_typical_speeds(session, series_id, category)`: front-group proxy (top K=10 finishers), median speed across editions, outlier filtering (15-55 kph), crit suppression
- [ ] Add distance plausibility checks: suppress speed for CRITERIUM, distance < 5km, NULL distance
- [ ] Handle missing `field_size` (fall back to result row count)
- [ ] Handle missing `race_time_seconds` (skip if < 50% have timing)
- [ ] Update `get_race_preview()` to include `drop_rate` and `typical_speed`
- [ ] Tests: known fixture (10 starters, 3 DNF → 30%), no history → None, multiple editions with recency, speed with outliers filtered, crit suppression, missing distance → None

### Phase 4: Narrative Generator (~10% effort)

**Goal:** Template-based "What to Expect" narrative combining course data, predictions, and stats.

**Files:**
- `raceanalyzer/predictions.py` — Add `generate_narrative()`
- `raceanalyzer/queries.py` — Update `get_race_preview()` to include narrative
- `tests/test_predictions.py` — Narrative tests

**Tasks:**
- [ ] Implement `generate_narrative()` with 5 sentence slots (course, climb, history, pacing, caveat)
- [ ] Each sentence independently optional based on data availability
- [ ] Qualitative bands for selectivity and speed (no raw numbers without context)
- [ ] Never output "None", raw floats without units, or technical jargon
- [ ] Update `get_race_preview()` to include `narrative`
- [ ] Tests: full data, partial data (no speed), no climbs, no history, completely new event, flat course

### Phase 5: Custom Interactive Map Component (~30% effort, highest risk)

**Goal:** Deliver the interactive map + elevation profile with hover sync.

**Files:**
- `raceanalyzer/ui/templates/course_profile.html` — Self-contained HTML/JS component
- `raceanalyzer/ui/maps.py` — Add `render_interactive_course_profile()` with fallback
- `raceanalyzer/ui/pages/race_preview.py` — Integrate new component + stats + narrative cards
- `raceanalyzer/ui/components.py` — Add `render_selectivity_badge()`, `render_climb_legend()`

**Tasks:**
- [ ] Create `course_profile.html` template:
  - Leaflet.js map with route polyline, climb segment overlays (colored), start/finish markers
  - Plotly.js elevation area chart with climb regions as colored fills
  - Hover sync: `plotly_hover` event → move `L.circleMarker` on map
  - Click climb on chart → zoom map to climb bounding box
  - Responsive: 60/40 split above 768px, stacked on mobile
  - Load CDN scripts with SRI integrity hashes
  - Data via `window.__COURSE_DATA__` JSON injection (safe — JSON-serialized, no user input)
- [ ] Implement `render_interactive_course_profile(profile_points, climbs, race_name, height=700)` in `maps.py`
  - Read HTML template, inject JSON data, render via `st.components.v1.html`
  - **Fallback:** if template fails or track_points unavailable, fall back to `render_course_map()` (existing Folium) + separate Plotly elevation chart
- [ ] Add `render_selectivity_badge(label)` and `render_climb_legend()` to `components.py`
- [ ] Update Race Preview page layout:
  1. "What to Expect" narrative card (top)
  2. Interactive course profile component (or Folium + Plotly fallback)
  3. Predicted Finish Type (existing)
  4. Historical Stats card (drop rate + speed metrics)
  5. Top Contenders (existing)
  6. Post-race Feedback (existing)
- [ ] All new cards degrade gracefully: missing data → info message, not errors

**Manual visual testing checklist:**
- [ ] Map loads with route polyline visible
- [ ] Climbs colored correctly on both map and elevation chart
- [ ] Hover on chart moves marker on map (or fallback: both views present)
- [ ] Start/finish markers visible
- [ ] Mobile viewport (375px) stacks vertically
- [ ] No JS console errors
- [ ] Component loads in < 3 seconds
- [ ] Falls back gracefully when track_points unavailable

---

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/db/models.py` | MODIFY | Add `profile_json`, `climbs_json` columns to `Course` |
| `raceanalyzer/rwgps.py` | MODIFY | Add `extract_track_points()` to parse RWGPS route JSON |
| `raceanalyzer/elevation.py` | MODIFY | Add `resample_profile()`, `smooth_elevations()`, `compute_gradients()`, `detect_climbs()` |
| `raceanalyzer/predictions.py` | MODIFY | Add `calculate_drop_rate()`, `calculate_typical_speeds()`, `generate_narrative()` |
| `raceanalyzer/queries.py` | MODIFY | Update `get_race_preview()` with profile, climbs, stats, narrative |
| `raceanalyzer/cli.py` | MODIFY | Add `course-profile-extract` CLI command |
| `raceanalyzer/config.py` | MODIFY | Add climb thresholds, speed outlier bounds, drop rate label thresholds |
| `raceanalyzer/ui/templates/course_profile.html` | CREATE | Custom Leaflet + Plotly.js interactive component |
| `raceanalyzer/ui/maps.py` | MODIFY | Add `render_interactive_course_profile()` with Folium fallback |
| `raceanalyzer/ui/pages/race_preview.py` | MODIFY | Integrate interactive map, narrative card, stats cards; reorder layout |
| `raceanalyzer/ui/components.py` | MODIFY | Add `render_selectivity_badge()`, `render_climb_legend()` |
| `tests/test_elevation.py` | MODIFY | Profile resampling, smoothing, climb detection tests |
| `tests/test_predictions.py` | MODIFY | Drop rate, speed, narrative generation tests |
| `tests/test_queries.py` | MODIFY | `get_race_preview()` integration tests with new data |
| `tests/conftest.py` | MODIFY | Add track_points fixtures, multi-edition result fixtures |

---

## Definition of Done

### Data Layer
- [ ] `Course.profile_json` and `Course.climbs_json` columns exist
- [ ] `course-profile-extract` CLI populates both columns from RWGPS route data
- [ ] Profile is downsampled to ≤ 2000 points (~50m spacing); payload ≤ 300KB
- [ ] Re-running CLI (without `--force`) skips courses that already have profile data
- [ ] All series with `rwgps_route_id` have profiles populated (batch extraction works)

### Climb Detection
- [ ] Climbs ≥ 500m with ≥ 3% avg gradient and ≥ 20m gain are detected
- [ ] Adjacent climbs separated by ≤ 150m are merged
- [ ] Each climb has: start/end coords, length, gain, avg/max gradient, category, color
- [ ] Flat courses correctly return 0 climb segments
- [ ] GPS noise doesn't produce spurious climbs after smoothing

### Historical Stats
- [ ] `calculate_drop_rate()` returns median drop rate (DNF + DNP only) with label and confidence
- [ ] `calculate_drop_rate()` returns None for series with no result data
- [ ] `calculate_typical_speeds()` returns median winner and field speeds in kph and mph
- [ ] `calculate_typical_speeds()` returns None for criteriums, missing distance, or insufficient timing data
- [ ] Speed outliers (< 15 kph or > 55 kph) are filtered

### Narrative
- [ ] `generate_narrative()` produces 1-5 sentences of plain English
- [ ] Each sentence is independently optional based on data availability
- [ ] Narrative never contains "None", raw floats without units, or technical jargon
- [ ] Narrative degrades to "This is a new event — no historical data is available yet." when no data exists
- [ ] Selectivity uses qualitative bands ("fairly typical", "moderately selective", etc.)

### Interactive Map Component
- [ ] Custom HTML component renders Leaflet map with route polyline and climb overlays
- [ ] Elevation profile chart renders with climb segments as colored regions
- [ ] Hovering on elevation chart moves a marker on the map (no server roundtrip)
- [ ] CDN scripts loaded with SRI integrity hashes (Leaflet 1.9.4, Plotly 2.35.0)
- [ ] Responsive: stacks vertically on mobile (< 768px)
- [ ] Falls back to Folium map + Plotly chart side-by-side if component fails or track_points unavailable

### UI Integration
- [ ] Race Preview shows "What to Expect" narrative at top
- [ ] Race Preview shows interactive map (or fallback)
- [ ] Race Preview shows Drop Rate and Typical Speed metrics in Historical Stats card
- [ ] All new cards degrade gracefully (missing data → info message, not errors)
- [ ] No raw probabilities or decimal scores shown — qualitative labels only

### Testing
- [ ] Climb detection: 7+ test cases (steady climb, false flat merge, two climbs, flat course, noisy data, short course, filtered ramp)
- [ ] Drop rate: 4+ test cases (known fixture, no history, multiple editions, DNP handling)
- [ ] Speed: 4+ test cases (known fixture, outlier filtering, crit suppression, missing distance)
- [ ] Narrative: 5+ test cases (full data, partial, no climbs, flat course, new event)
- [ ] `get_race_preview()` returns new fields; degrades when data missing
- [ ] All existing tests pass
- [ ] `ruff check .` passes
- [ ] Test coverage remains > 85%

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Custom HTML component sizing/scrolling issues in Streamlit iframe** | Medium | High | Set explicit height in Python. Use responsive CSS inside iframe. Test Chrome/Firefox/Safari. **If truly broken:** fall back to side-by-side Folium + Plotly (lose hover sync, keep everything else). |
| **Plotly.js basic bundle size (~400KB) causes slow first load** | Medium | Medium | Use `plotly-basic.min.js` (scatter/line only). Browser HTTP cache prevents re-download. Consider vendoring inline if CDN proves unreliable. |
| **GPS elevation noise causes false climb detections** | High | Medium | 200m Gaussian smoothing window handles typical ±3-5m GPS noise. Post-filter requires ≥ 20m gain and ≥ 500m length. Merge step prevents fragmentation. |
| **RWGPS track_points missing elevation per point** | Low | High | Check for elevation field; if missing, fall back to encoded polyline only (no elevation chart, no climbs). Log warning. |
| **`race_time_seconds` is NULL for many results** | Medium | Medium | If < 50% of results have timing, skip speed calculation entirely. Show "Timing data not available." |
| **Crit single-lap distance produces wrong speeds** | High | High | **Suppress speed entirely for criteriums.** Re-enable in future sprint when total race distance can be inferred. |
| **Route varies across editions of the same series** | Medium | Medium | Profile extraction uses the series-level `rwgps_route_id`. UI notes "based on most recent route." If per-race routes differ, prefer the most recent. |
| **CDN unavailability for Leaflet/Plotly** | Low | Medium | Pin CDN versions. Leaflet is 40KB (could inline). Plotly is too large to inline but cached aggressively. |
| **SQLite migration: adding TEXT columns to Course** | Low | Low | Manual `ALTER TABLE` (existing pattern). NULL default means existing rows unaffected. `course-profile-extract` backfills. |
| **Climb detection thresholds don't match PNW amateur perception** | Medium | Low | Thresholds are configurable in Settings. Adjust after manual review of 5-10 representative PNW courses. |

---

## Security

- **XSS prevention in HTML component:** All data injected via `json.dumps()` into a `<script type="application/json">` tag, parsed with `JSON.parse`. No user-supplied strings interpolated into HTML or JS. Track point data is numeric (lat, lon, elevation, distance).
- **CDN integrity:** Leaflet.js and Plotly.js loaded via `<script src="..." integrity="sha384-..." crossorigin="anonymous">`. Pinned to specific versions.
- **No new external API calls at render time.** Profile data is pre-fetched and stored. HTML component makes no network requests beyond CDN script loads and map tile fetches.
- **Rate limiting on profile extraction CLI:** Maintained at 2s between RWGPS API calls (consistent with Sprint 007).
- **No PII in profile data or stats.** Drop rates and speeds are aggregate statistics. Profile points are geographic coordinates from public RWGPS routes.

---

## Dependencies

**Existing Python packages (no changes):**
- `sqlalchemy`, `streamlit`, `pandas`, `plotly`, `folium`, `streamlit-folium`, `polyline`, `requests`, `click`

**New Python packages: None.**

**Frontend (CDN, loaded in iframe only):**
- Leaflet.js 1.9.4 (BSD-2 license)
- Plotly.js 2.35.0 basic bundle (MIT license)
- CartoDB Positron map tiles (free, no API key)

---

## Open Questions

1. **Profile data normalization:** Sprint 008 stores `profile_json`/`climbs_json` as JSON blobs on `Course` for speed of delivery. If Sprint 010's "key moments" feature needs to query climbs across courses, normalize into tables then. Acknowledged tradeoff.

2. **Category normalization:** Category strings may differ across years ("Cat 4/5" vs "4/5", "Women 1/2/3" vs "W1/2/3"). For Sprint 008, match on exact category string from results. Add a category alias map in Sprint 009 if this proves to be a problem for stat accuracy.

3. **Smoothing window tuning:** 200m Gaussian window is reasonable for PNW road races (1-5km climbs). Should be configurable in `Settings` but not user-facing. Adjust after reviewing profile output for 5-10 representative courses.

4. **Downsampling strategy:** Sprint 008 uses every-Nth-point downsampling from the uniformly resampled profile. If this flattens peaks visually, upgrade to shape-preserving downsampling (e.g., Ramer-Douglas-Peucker) in a future sprint.

5. **HTML component lifecycle:** The raw `components.v1.html` approach has no linting, type checking, or hot reload. If the component proves valuable and needs iteration, promote it to a proper Streamlit custom component package in a future sprint.

6. **Out-and-back and multi-lap courses:** The profile and map will show overlapping segments for out-and-back courses. Add a UI note "Route shown as-is from RideWithGPS" for Sprint 008. Handle deduplication later if needed.
