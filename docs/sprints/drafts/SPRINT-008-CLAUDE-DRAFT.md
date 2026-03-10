# Sprint 008: Interactive Course Intelligence & Historical Race Stats

## Overview

Sprint 008 delivers the foundational layer of P0 race intelligence: an interactive course map synced with an elevation profile, climb segment visualization, historical race statistics (drop rate, finishing speeds), and a template-driven "What to Expect" narrative. By the end of this sprint, the Race Preview page transforms from a static summary into an interactive course exploration tool backed by historical data — the single most valuable upgrade for a racer preparing for an unfamiliar event.

**Why these 6 stories first:** Stories #1, #2, #3 are the spatial foundation — every future map feature (#10 wind zones, #19 key moments, #28 replay) renders _on top of_ this interactive map. Stories #16, #17, #18 are the simplest prediction extensions — they query existing `Result` data with straightforward aggregation, require no external APIs, and produce the inputs for the narrative generator. Together, these 6 stories form a self-contained deliverable: a racer opens Race Preview and sees an interactive map with climbs highlighted, plus historical stats and a plain-English race summary.

**What's deferred and why:** Wind exposure (#10) requires external geodata (OpenStreetMap land-use queries). Pack odds (#12) requires a probability model we haven't designed. Weather (#20) requires an external API integration. Key moments (#19) and replay (#28) require correlating spatial data with historical gap data — the hardest algorithmic work. Enhanced finish type UX (#11) is incremental polish on Sprint 007's working baseline. All of these build on the foundation this sprint establishes.

### P0 Story Phasing Across 3 Sprints

| Sprint | Stories | Theme |
|--------|---------|-------|
| **008** (this sprint) | #1, #2, #3, #16, #17, #18 | Interactive map + elevation + climbs + historical stats + narrative |
| **009** | #10, #11, #12, #20 | Wind exposure, enhanced finish type UX, pack odds, weather integration |
| **010** | #19, #28 | Key moments on map, animated race replay |

**Duration**: ~2-3 weeks
**Prerequisite**: Sprint 007 complete (Course model, baseline predictions, Race Preview page, Folium course map).

---

## Use Cases

1. **As a racer**, I can pan, zoom, and explore the course on an interactive map with the route highlighted, so I can identify key turns and landmarks before race day. _(#1)_
2. **As a racer**, I can see an elevation profile chart below the map, and when I hover over a point on the profile, a marker moves to the corresponding location on the map — so I can connect "that big climb at mile 12" with an actual place on the route. _(#2)_
3. **As a racer**, I can see individual climbs color-coded by gradient severity (moderate/steep/brutal) on both the map and the elevation profile, so I immediately know where the hard efforts are. _(#3)_
4. **As a racer**, I can see the historical drop rate for my category (e.g., "32% of Cat 4 starters DNF'd or were dropped"), so I know how selective the race is. _(#17)_
5. **As a racer**, I can see typical finishing speeds from past editions (e.g., "Winning group averaged 24.1 mph"), so I know whether the pace is within my fitness. _(#16)_
6. **As a racer**, I can read a "What to Expect" narrative summarizing the race in plain English — terrain character, expected finish type, historical selectivity, and pacing context — so I can mentally prepare even though I've never done this event. _(#18)_
7. **As a developer**, I can call `extract_climb_segments()` with RWGPS track_points and get back a list of detected climbs with gradient, length, and start/end coordinates.
8. **As a developer**, I can call `calculate_drop_rate()` and `calculate_typical_speeds()` with a series_id and category, and get back structured data that degrades gracefully when history is sparse.

---

## Architecture

### Critical Data Gap: Track Points

The existing system stores only encoded polylines (`RaceSeries.rwgps_encoded_polyline`), which decode to `[(lat, lon), ...]` — **no elevation or distance-along-route data**. Stories #1-#3 all require per-point elevation. Two options:

**Option A: Fetch-on-demand from RWGPS API.** When Race Preview loads, if track_points aren't cached, fetch `/routes/{id}.json` and extract `track_points`. Cache in `st.session_state` for the session. Pro: no schema change. Con: adds latency on first load (~1-2s), RWGPS dependency at render time.

**Option B: Store track_points in a new DB column.** Add a `track_points_json` TEXT column to `Course` (or a separate `CourseTrackPoints` table). Populate during `elevation-extract` CLI. Pro: zero render-time latency, no RWGPS dependency. Con: significant storage (~50-200KB per route as compressed JSON).

**Recommendation: Option B (store in DB).** The track_points data is stable (routes don't change), the storage cost is modest for ~100-200 PNW series, and it eliminates a runtime dependency on an external API. We store a lightweight representation: `[{d: distance_m, e: elevation_m, y: lat, x: lon}, ...]` with abbreviated keys to reduce size. The `elevation-extract` CLI already fetches the RWGPS route JSON; we just need to persist the track_points alongside the aggregate stats.

### Map-Elevation Sync: The Streamlit/Folium Challenge

**The Problem:** Folium maps rendered via `st_folium` trigger a full Streamlit script rerun on interaction. There's no way to listen to a Plotly hover event and update a Folium marker without a server roundtrip, causing unacceptable lag (200-500ms per hover event).

**Evaluated Approaches:**

| Approach | Latency | Complexity | Drawbacks |
|----------|---------|------------|-----------|
| Plotly + st_folium side-by-side, click-to-scroll | ~300ms | Low | Not hover-synced; requires clicking, not hovering |
| `pydeck` (Deck.gl) replacing Folium | ~50ms | Medium | No built-in elevation chart; loses Folium markers/popups |
| Custom HTML component (Leaflet + Plotly.js) | ~5ms | High | Must build from scratch; iframe isolation limits |
| Streamlit Bidirectional Component | ~20ms | Very High | Requires npm build pipeline; overkill for this |

**Recommendation: Custom HTML component via `streamlit.components.v1.html`.** This bundles Leaflet.js (map) and Plotly.js (elevation chart) in a single HTML page rendered as an iframe. Python serializes the track_points + climb segments as JSON and injects them into the HTML template. JavaScript handles all hover/sync interactions client-side with zero server roundtrips. This is the same approach used by Strava's route viewer.

Key design choices:
- **Plotly.js over Chart.js** for the elevation chart — matches our existing Plotly usage, supports area fills for climb coloring, has built-in hover events.
- **Leaflet.js over Folium** inside the component — Leaflet is what Folium wraps anyway; using it directly gives us full JS control.
- **CartoDB Positron tiles** — matches the existing Folium map aesthetic, no API key needed.
- **SRI hashes on CDN scripts** — prevents supply chain attacks on Leaflet/Plotly CDN loads.
- **Responsive layout** — map takes 60% height, elevation profile takes 40%, with a CSS breakpoint for mobile (stacks vertically).

### Climb Detection Algorithm

A two-pass approach over smoothed track_points:

**Pass 1: Smoothing.** GPS elevation data has ±3-5m noise per point. Apply a Gaussian-weighted rolling average with a window of ~200m of distance (not a fixed number of points, since point spacing varies). This preserves real gradient changes while eliminating GPS jitter.

**Pass 2: Segment detection.** Iterate smoothed points, computing gradient = Δelevation / Δdistance for each consecutive pair. Use a state machine:

```
State: FLAT (default)
  → if gradient >= 3% for 200m+: transition to CLIMBING, record start
State: CLIMBING
  → if gradient < 1% for 100m+: transition to FLAT, record end (if total climb length >= 500m)
  → accumulate: total gain, max gradient, average gradient, length
```

The 3% entry threshold catches moderate climbs (Cat 4+). The 1% exit threshold with 100m hysteresis prevents false endings on brief flat spots within a longer climb. The 500m minimum length filters out short ramps.

**Climb categorization by average gradient:**

| Category | Avg Gradient | Color | Label |
|----------|-------------|-------|-------|
| Moderate | 3-5% | `#FFC107` (amber) | "Moderate climb" |
| Steep | 5-8% | `#FF5722` (deep orange) | "Steep climb" |
| Brutal | 8%+ | `#B71C1C` (dark red) | "Brutal climb" |

### Historical Stats Algorithms

**Drop Rate (#17):**

```python
def calculate_drop_rate(session, series_id, category=None) -> dict:
    """
    Returns: {
        "drop_rate": float (0.0-1.0),
        "total_starters": int,
        "total_dropped": int,  # DNF + DQ + DNP
        "edition_count": int,
        "label": "low" | "moderate" | "high" | "extreme",
        "confidence": "high" | "moderate" | "low",
    }
    """
```

Query all `Result` rows for races in this series (and optionally category). Count starters = total rows, dropped = rows where `dnf=True OR dq=True OR dnp=True`. Compute `drop_rate = dropped / starters`. Average across editions, weighted 2x for the most recent 2 editions (matching the recency weighting in `predict_series_finish_type`).

**Label mapping:** <10% → "low", 10-25% → "moderate", 25-40% → "high", >40% → "extreme".
**Confidence:** 3+ editions with 10+ starters each → "high", 2 editions or small fields → "moderate", 1 edition → "low".

**Typical Finishing Speeds (#16):**

```python
def calculate_typical_speeds(session, series_id, category=None) -> dict:
    """
    Returns: {
        "median_winner_speed_kph": float,
        "median_winner_speed_mph": float,
        "median_field_speed_kph": float,  # median of all finishers
        "edition_count": int,
        "confidence": "high" | "moderate" | "low",
    }
    """
```

For each historical edition: take `Result.race_time_seconds` for finishers (not DNF) in this category. Compute speed = `Course.distance_m / race_time_seconds * 3.6` (m/s → kph). Take the winner's speed (place=1) and the median field speed. Average across editions. Filter outliers: discard speeds < 15 kph or > 55 kph (likely timing errors or neutralized starts).

**Graceful degradation:** If `Course.distance_m` is NULL, speeds cannot be computed — return None and skip the speed card in the UI. If `race_time_seconds` is NULL for all results, return None. If only 1 edition has timing data, show it with "low" confidence and a "(single edition)" qualifier.

### Narrative Generator (#18)

Template-based, not LLM-based. Deterministic, fast, and testable.

**Architecture:** A `generate_narrative()` function takes structured inputs and composes a 2-4 sentence summary by selecting from template fragments based on input values.

```python
def generate_narrative(
    course_type: str,           # "flat" | "rolling" | "hilly" | "mountainous"
    predicted_finish_type: str, # from predict_series_finish_type()
    drop_rate: dict | None,     # from calculate_drop_rate()
    typical_speed: dict | None, # from calculate_typical_speeds()
    distance_km: float | None,
    total_gain_m: float | None,
    edition_count: int,
) -> str:
```

**Template structure (3 sentences):**

1. **Course sentence:** Describes the physical course.
   - "This {distance_km:.0f} km {course_type} course has {total_gain_m:.0f}m of climbing."
   - Flat variant: "This {distance_km:.0f} km flat course has minimal climbing — positioning and tactics matter more than pure power."
   - Mountainous variant: "This {distance_km:.0f} km mountain course packs {total_gain_m:.0f}m of climbing — expect the field to shatter on the climbs."

2. **History sentence:** Describes what typically happens.
   - "Based on {edition_count} previous editions, this race typically ends in a {finish_type_display}."
   - With drop rate: "Historically, {drop_rate_pct}% of starters are dropped or DNF — {selectivity_adjective} for the category."
   - Selectivity adjectives: "fairly typical" (<15%), "moderately selective" (15-30%), "quite selective" (30-45%), "brutally selective" (>45%).

3. **Pacing sentence (if speed data available):**
   - "The winning group usually averages around {speed_mph:.0f} mph ({speed_kph:.0f} kph)."

**Graceful degradation:** Each sentence is independently optional. If no course data: skip sentence 1. If no history: "This is a new event — no historical data is available yet." If no speed data: skip sentence 3. The function always returns at least one sentence.

---

## Implementation

### Phase 1: Track Points Storage & Climb Detection (~25% effort)

**Files:** `raceanalyzer/db/models.py`, `raceanalyzer/rwgps.py`, `raceanalyzer/elevation.py`, `raceanalyzer/cli.py`, `tests/test_elevation.py`

**Tasks:**

1.1. Add `track_points_json` column to `Course` model:

```python
# Compact track points: [{d: distance_m, e: elevation_m, y: lat, x: lon}, ...]
track_points_json = Column(Text, nullable=True)
```

1.2. Update `elevation-extract` CLI to persist track_points alongside aggregate stats. On each RWGPS route fetch, serialize the track_points array as compact JSON and store in `Course.track_points_json`. Use abbreviated keys (`d`, `e`, `y`, `x`) to reduce storage.

1.3. Add helper function to `rwgps.py`:

```python
def extract_track_points(route_json: dict) -> list[dict]:
    """Extract compact track points from RWGPS route JSON.

    Returns: [{d: cumulative_distance_m, e: elevation_m, y: lat, x: lon}, ...]
    Computes cumulative distance via haversine if not present in source data.
    """
```

1.4. Implement `extract_climb_segments()` in `elevation.py`:

```python
def smooth_elevations(
    track_points: list[dict],
    window_m: float = 200.0,
) -> list[dict]:
    """Apply distance-weighted Gaussian smoothing to elevation data.

    Returns track_points with smoothed 'e' values. Original 'e' preserved as 'e_raw'.
    """

def extract_climb_segments(
    track_points: list[dict],
    entry_gradient: float = 0.03,   # 3% to start a climb
    exit_gradient: float = 0.01,    # 1% to end a climb
    min_length_m: float = 500.0,    # minimum 500m to count
    hysteresis_m: float = 100.0,    # must stay below exit for 100m
) -> list[dict]:
    """Detect sustained climb segments from track points.

    Returns: [{
        "start_idx": int,
        "end_idx": int,
        "start_distance_m": float,
        "end_distance_m": float,
        "length_m": float,
        "total_gain_m": float,
        "avg_gradient": float,      # 0.0-1.0
        "max_gradient": float,
        "category": "moderate" | "steep" | "brutal",
        "color": str,               # hex color for rendering
        "start_coords": (lat, lon),
        "end_coords": (lat, lon),
    }, ...]
    """
```

1.5. Add `get_track_points()` helper to `queries.py`:

```python
def get_track_points(session, series_id) -> list[dict] | None:
    """Load and deserialize track points for a series. Returns None if unavailable."""
```

1.6. Tests (`tests/test_elevation.py`):
- Climb detection on synthetic track_points: single steady climb, climb with false flat, two climbs with descent between, flat course (no climbs), noisy data before/after smoothing.
- Smoothing function preserves total gain within 5% tolerance.
- Edge cases: fewer than 10 track points, all-flat elevation, single-point.

---

### Phase 2: Historical Stats Engine (~20% effort)

**Files:** `raceanalyzer/predictions.py`, `raceanalyzer/queries.py`, `tests/test_predictions.py`

**Tasks:**

2.1. Implement `calculate_drop_rate()` in `predictions.py`:

```python
def calculate_drop_rate(
    session: Session,
    series_id: int,
    category: Optional[str] = None,
) -> Optional[dict]:
    """Calculate historical drop/DNF rate for a series + category.

    Returns None if no historical data. Returns dict with:
    - drop_rate: float (0.0-1.0)
    - total_starters: int
    - total_dropped: int
    - edition_count: int
    - label: "low" | "moderate" | "high" | "extreme"
    - confidence: "high" | "moderate" | "low"
    """
```

Query logic: For each edition in the series, count total results (starters) and results where `dnf=True OR dq=True OR dnp=True` (dropped). Compute per-edition drop rates, then weighted average with 2x recency for the last 2 editions.

2.2. Implement `calculate_typical_speeds()` in `predictions.py`:

```python
def calculate_typical_speeds(
    session: Session,
    series_id: int,
    category: Optional[str] = None,
) -> Optional[dict]:
    """Calculate historical finishing speeds for a series + category.

    Requires Course.distance_m to compute speed from time.
    Returns None if distance or timing data unavailable.
    """
```

Query logic: Join `Result` → `Race` → `Course` (via series_id). For each edition, get `race_time_seconds` for finishers. Compute speed = `distance_m / race_time_seconds * 3.6`. Discard outliers (< 15 kph or > 55 kph). Return median winner speed and median field speed, averaged across editions.

2.3. Implement `generate_narrative()` in `predictions.py`:

```python
def generate_narrative(
    course_type: Optional[str],
    predicted_finish_type: Optional[str],
    drop_rate: Optional[dict],
    typical_speed: Optional[dict],
    distance_km: Optional[float],
    total_gain_m: Optional[float],
    edition_count: int = 0,
) -> str:
    """Generate a plain-English 'What to Expect' summary.

    Template-based. Each sentence is independently optional based on data availability.
    Always returns at least one sentence.
    """
```

2.4. Update `get_race_preview()` in `queries.py` to include drop_rate, speeds, narrative, track_points, and climb_segments in its return dict.

2.5. Tests (`tests/test_predictions.py`):
- Drop rate with known fixture data (e.g., 10 starters, 3 DNF → 30%).
- Drop rate with no history → returns None.
- Drop rate with multiple editions, verify recency weighting.
- Speed calculation with known distance and times.
- Speed calculation filters outliers.
- Speed returns None when Course.distance_m is NULL.
- Narrative generation with full data, partial data (no speed), no data.
- Narrative produces human-readable English (assert no raw numbers without units, no "None" strings).

---

### Phase 3: Custom Interactive Map Component (~35% effort)

**Files:** `raceanalyzer/ui/templates/course_profile.html`, `raceanalyzer/ui/maps.py`, `raceanalyzer/ui/pages/race_preview.py`

This is the highest-effort, highest-risk phase. The custom HTML component replaces the static Folium map with an interactive Leaflet + Plotly.js experience.

**Tasks:**

3.1. Create `raceanalyzer/ui/templates/course_profile.html`:

A self-contained HTML file that:
- Loads Leaflet.js (~40KB) and Plotly.js (basic bundle, ~1MB) from CDN with SRI hashes.
- Accepts a `window.__COURSE_DATA__` JSON object injected by Python, containing:
  ```json
  {
    "track_points": [{"d": 0, "e": 152.3, "y": 47.61, "x": -122.33}, ...],
    "climbs": [{"start_idx": 42, "end_idx": 87, "category": "steep", "color": "#FF5722", ...}, ...],
    "race_name": "Seward Park Road Race",
    "start_marker": [47.61, -122.33],
    "finish_marker": [47.62, -122.34]
  }
  ```
- Renders a Leaflet map (top 60%) with:
  - Route polyline (Strava orange `#FC4C02`)
  - Climb segments as colored overlays on the polyline
  - Start/finish markers (green play / red flag)
  - Auto-fit bounds to route
  - CartoDB Positron tiles
- Renders a Plotly.js elevation area chart (bottom 40%) with:
  - X-axis: distance (km), Y-axis: elevation (m)
  - Climb segments as colored fill regions
  - Hover crosshair showing elevation, distance, and gradient
- **Hover sync:** When the user hovers over the elevation chart, a red circle marker moves to the corresponding lat/lon on the Leaflet map. Implemented via Plotly's `plotly_hover` event → lookup track_point by index → `marker.setLatLng()`.
- **Click sync:** Clicking a climb segment on the elevation chart zooms the map to that climb's bounding box.
- **Responsive:** At viewport width < 768px, map and chart stack vertically (50/50). Above 768px, chart is below map (60/40).

3.2. Add `render_interactive_course_profile()` to `maps.py`:

```python
def render_interactive_course_profile(
    track_points: list[dict],
    climb_segments: list[dict],
    race_name: str = "",
    height: int = 700,
) -> None:
    """Render the interactive Leaflet + Plotly course profile component.

    Falls back to render_course_map() if track_points is empty/None.
    """
```

This function:
- Reads the HTML template from `templates/course_profile.html`.
- Serializes track_points and climb_segments as JSON.
- Injects the JSON into the HTML via string replacement (safe — data is JSON-serialized, not user input).
- Calls `streamlit.components.v1.html(html_content, height=height)`.

3.3. **Fallback strategy:** If `track_points_json` is NULL for a series (e.g., elevation-extract hasn't run or RWGPS didn't have track_points), fall back to the existing `render_course_map()` Folium renderer. The elevation chart and climb segments simply don't appear. This matches the project's "graceful degradation at every layer" principle.

3.4. Manual visual testing checklist (no automated test for visual rendering):
- [ ] Map loads and shows route polyline
- [ ] Climbs are colored correctly on map and elevation chart
- [ ] Hover on chart moves marker on map smoothly
- [ ] Start/finish markers visible
- [ ] Mobile viewport (375px) stacks vertically
- [ ] No JS console errors
- [ ] Component loads in < 2 seconds

---

### Phase 4: Race Preview UI Integration (~20% effort)

**Files:** `raceanalyzer/ui/pages/race_preview.py`, `raceanalyzer/ui/components.py`

**Tasks:**

4.1. Replace the existing Folium course map call with the new interactive component:

```python
# Before (Sprint 007):
if series.get("encoded_polyline"):
    render_course_map(series["encoded_polyline"], series["display_name"])

# After (Sprint 008):
track_points = preview.get("track_points")
climb_segments = preview.get("climb_segments")
if track_points:
    render_interactive_course_profile(
        track_points, climb_segments or [], series["display_name"]
    )
elif series.get("encoded_polyline"):
    render_course_map(series["encoded_polyline"], series["display_name"])
```

4.2. Add "Historical Stats" card between the Prediction card and Contenders card:

```python
with st.container(border=True):
    st.subheader("Historical Stats")
    col1, col2 = st.columns(2)

    # Drop Rate
    drop = preview.get("drop_rate")
    if drop:
        with col1:
            st.metric("Drop Rate", f"{drop['drop_rate']*100:.0f}%")
            render_selectivity_badge(drop["label"])
            st.caption(f"Based on {drop['edition_count']} editions")

    # Typical Speed
    speed = preview.get("typical_speed")
    if speed:
        with col2:
            st.metric("Winning Speed", f"{speed['median_winner_speed_mph']:.1f} mph")
            st.caption(f"Median across {speed['edition_count']} editions")
```

4.3. Add "What to Expect" narrative card at the top of the page (above Course Profile):

```python
with st.container(border=True):
    st.subheader("What to Expect")
    narrative = preview.get("narrative")
    if narrative:
        st.markdown(narrative)
    else:
        st.info("Not enough data to generate a race summary yet.")
```

4.4. Add `render_selectivity_badge()` and `render_climb_legend()` to `components.py`.

4.5. Update card ordering on Race Preview:
1. What to Expect (narrative) — new
2. Course Profile (interactive map + elevation) — upgraded
3. Predicted Finish Type — existing from Sprint 007
4. Historical Stats (drop rate + speed) — new
5. Top Contenders — existing from Sprint 007
6. Post-race Feedback — existing from Sprint 007

---

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/db/models.py` | MODIFY | Add `track_points_json` column to `Course` |
| `raceanalyzer/rwgps.py` | MODIFY | Add `extract_track_points()` helper |
| `raceanalyzer/elevation.py` | MODIFY | Add `smooth_elevations()`, `extract_climb_segments()` |
| `raceanalyzer/predictions.py` | MODIFY | Add `calculate_drop_rate()`, `calculate_typical_speeds()`, `generate_narrative()` |
| `raceanalyzer/queries.py` | MODIFY | Update `get_race_preview()` to include new data; add `get_track_points()` |
| `raceanalyzer/cli.py` | MODIFY | Update `elevation-extract` to persist track_points_json |
| `raceanalyzer/config.py` | MODIFY | Add climb detection thresholds, speed outlier bounds, drop rate label thresholds |
| `raceanalyzer/ui/templates/course_profile.html` | CREATE | Custom Leaflet + Plotly.js interactive component |
| `raceanalyzer/ui/maps.py` | MODIFY | Add `render_interactive_course_profile()` with fallback to Folium |
| `raceanalyzer/ui/pages/race_preview.py` | MODIFY | Integrate interactive map, narrative, stats cards; reorder layout |
| `raceanalyzer/ui/components.py` | MODIFY | Add `render_selectivity_badge()`, `render_climb_legend()` |
| `tests/test_elevation.py` | MODIFY | Add climb detection tests, smoothing tests |
| `tests/test_predictions.py` | MODIFY | Add drop rate, speed, narrative generation tests |
| `tests/conftest.py` | MODIFY | Add track_points fixtures, multi-edition result fixtures |

---

## Definition of Done

### Data Layer
- [ ] `Course.track_points_json` column exists and is populated by `elevation-extract` CLI
- [ ] `extract_track_points()` produces compact `[{d, e, y, x}, ...]` format from RWGPS route JSON
- [ ] Track points are persisted for all series with `rwgps_route_id`
- [ ] Re-running `elevation-extract` (without `--force`) skips series that already have track_points

### Climb Detection
- [ ] `smooth_elevations()` reduces GPS noise while preserving real climbs (total gain within 5% of raw)
- [ ] `extract_climb_segments()` detects climbs ≥500m with ≥3% average gradient
- [ ] Each climb has: start/end coords, length, gain, avg/max gradient, category, color
- [ ] Flat courses correctly return 0 climb segments
- [ ] Noisy elevation data doesn't produce spurious short climbs after smoothing

### Historical Stats
- [ ] `calculate_drop_rate()` returns weighted average drop rate with label and confidence
- [ ] `calculate_drop_rate()` returns None for series with no result data
- [ ] `calculate_typical_speeds()` returns median winner and field speeds in kph and mph
- [ ] `calculate_typical_speeds()` returns None when distance or timing data is missing
- [ ] Speed outliers (< 15 kph or > 55 kph) are filtered before computing median

### Narrative
- [ ] `generate_narrative()` produces 1-3 sentences of plain English
- [ ] Narrative degrades gracefully: works with any subset of inputs (course only, history only, full data)
- [ ] Narrative never contains "None", raw floats without units, or technical jargon
- [ ] Narrative includes terrain description, finish type prediction, selectivity context, and pacing (when data available)

### Interactive Map Component
- [ ] Custom HTML component renders Leaflet map with route polyline and climb overlays
- [ ] Elevation profile chart renders below map with climb segments as colored regions
- [ ] Hovering on elevation chart moves a marker on the map in real-time (no server roundtrip)
- [ ] Start/finish markers are visible
- [ ] Component loads CDN scripts with SRI integrity hashes
- [ ] Component is responsive: stacks vertically on mobile (< 768px)
- [ ] Falls back to existing Folium map when track_points_json is NULL

### UI Integration
- [ ] Race Preview page displays "What to Expect" narrative at top
- [ ] Race Preview page shows interactive map (or Folium fallback)
- [ ] Race Preview page shows Drop Rate and Typical Speed metrics
- [ ] All new cards degrade gracefully — missing data shows info message, not errors
- [ ] No raw probabilities or decimal scores shown to users — qualitative labels only

### Testing
- [ ] Unit tests for climb detection (5+ test cases including edge cases)
- [ ] Unit tests for drop rate calculation (3+ test cases)
- [ ] Unit tests for speed calculation (3+ test cases including outlier filtering)
- [ ] Unit tests for narrative generation (4+ test cases: full data, partial, empty, edge)
- [ ] All existing tests continue to pass
- [ ] Test coverage remains > 85%

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **`streamlit.components.v1.html` iframe sizing/scrolling issues** | Medium | High | Set explicit height in Python. Use `overflow: hidden` in the iframe. Test on Chrome, Firefox, Safari. If truly broken, fall back to Folium map + separate Plotly elevation chart (lose hover sync, keep everything else). |
| **Plotly.js bundle size (~1MB) causes slow first load** | Medium | Medium | Use `plotly-basic.min.js` (scatter/line only, ~400KB). Add `loading="lazy"` to the component. Cache via browser HTTP cache headers. |
| **GPS elevation noise causes false climb detections** | High | Medium | The 200m Gaussian smoothing window should handle typical ±3-5m GPS noise. Add a configurable `min_gain_m` parameter (default 20m) — segments with < 20m total gain are discarded even if gradient is met. |
| **RWGPS track_points missing elevation data** | Low | High | Some RWGPS routes may have lat/lon but no elevation per point. Check for `e`/`elevation` field; if missing, fall back to encoded polyline only (no elevation chart, no climb detection). Log a warning. |
| **`race_time_seconds` is NULL for most results** | Medium | Medium | Many road-results.com results lack timing data. If < 50% of results have timing, skip speed calculation entirely. Show "Timing data not available" in UI. |
| **Custom HTML component doesn't receive return data from Streamlit** | Low | Low | We don't need bidirectional communication — data flows one way (Python → JS). `st.components.v1.html` supports this natively. |
| **CDN unavailability for Leaflet/Plotly** | Low | Medium | Pin specific CDN versions. Consider bundling minified JS inline for critical path (Leaflet is only 40KB). Plotly is too large to inline. |
| **`track_points_json` column bloats SQLite database** | Low | Low | 200 routes × 200KB = ~40MB. Well within SQLite's comfort zone. Compress with zlib if needed in future. |

---

## Security

- **XSS prevention in HTML component:** All data injected into the HTML template is JSON-serialized via Python's `json.dumps()`. No user-supplied strings are interpolated into HTML or JS. Track point data is numeric (lat, lon, elevation, distance).
- **CDN integrity:** Leaflet.js and Plotly.js loaded via `<script src="..." integrity="sha384-..." crossorigin="anonymous">`. Pin to specific versions (Leaflet 1.9.4, Plotly 2.35.0).
- **No new external API calls at render time.** Track points are pre-fetched and stored. The HTML component makes no network requests beyond CDN script loads and tile fetches.
- **Rate limiting on elevation-extract CLI:** Maintained at 2s between RWGPS API calls (from Sprint 007).
- **No PII in track points or stats.** Drop rates and speeds are aggregate statistics. Track points are geographic coordinates from public RWGPS routes.

---

## Dependencies

**Existing (no changes):**
- `sqlalchemy`, `streamlit`, `pandas`, `plotly`, `folium`, `streamlit-folium`, `polyline`, `requests`, `click`

**New Python packages: None.**

**Frontend (CDN, not installed):**
- Leaflet.js 1.9.4 (BSD-2 license, loaded in iframe)
- Plotly.js 2.35.0 basic bundle (MIT license, loaded in iframe)
- CartoDB Positron map tiles (free, no API key)

---

## Open Questions

1. **Track points storage format:** Compact JSON (`[{d, e, y, x}, ...]`) vs. two parallel arrays (`{distances: [...], elevations: [...], lats: [...], lons: [...]}`)? Parallel arrays are ~15% smaller but less readable. Recommendation: compact JSON for simplicity; optimize only if storage becomes an issue.

2. **Smoothing window size:** 200m is a reasonable default for PNW road races (1-5km climbs). Should this be configurable in `Settings`? Probably yes, but not user-facing — developer config only.

3. **Climb minimum gain threshold:** Should we require a minimum total elevation gain (e.g., 20m) in addition to minimum length and gradient? This would filter out long gentle false-positives. Recommendation: yes, add `min_gain_m=20.0` parameter.

4. **Drop rate: include DQ as "dropped"?** DQ (disqualified) is not the same as DNF (did not finish). A DQ rider technically finished but was penalized. Recommendation: count DQ separately and don't include in drop rate. Count DNF + DNP only.

5. **Speed display: mph vs kph?** US amateur racing community primarily uses mph. International convention is kph. Recommendation: show both, lead with mph for PNW audience. Consider making this a user preference in Sprint 009+.

6. **Narrative tone:** How informal should the narrative be? "The field will get shattered on the climb" vs. "Significant attrition is expected on the climb." Recommendation: casual but informative — match the existing `COURSE_TYPE_DESCRIPTIONS` tone ("Strong all-rounders and punchy riders thrive"). The audience is amateur racers, not academics.

7. **RWGPS track_points density:** Some routes have 500 points, others have 5000. Should we downsample before storing? Recommendation: downsample to ~1 point per 50m of distance (~2000 points for a 100km course). This keeps storage reasonable and is more than sufficient for visualization and climb detection.

8. **Hover sync performance with many track points:** If a route has 5000+ points, Plotly hover events firing for each index could cause jank. Recommendation: downsample to ~500-1000 points for the visualization. The climb detection can run on the full-resolution data before downsampling.
