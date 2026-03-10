# Sprint 008: P0 Race Intelligence — Interactive Maps, Predictions & Narrative

## Overview

This sprint initiates the delivery of the 12 P0 user stories identified for the core "Race Intelligence" product. Because the scope of 12 P0 stories is too large for a single sprint, we will phase them across three sprints to ensure each sprint delivers a self-contained, valuable increment.

Sprint 008 establishes the foundation: an interactive map synced with an elevation profile, and core historical statistics (drop rates, speeds) synthesized into a plain-language narrative. By the end of Sprint 008, racers will have a significantly upgraded Race Preview page that allows them to explore course topography interactively and understand the historical attrition and pacing of their specific category.

### Phasing the 12 P0 Stories
1. **Sprint 008 (Current): Map Foundation & Historical Stats**
   - #1 Interactive Course Map
   - #2 Elevation Profile Overlaid on Map
   - #3 Climb Segments on Map
   - #16 Typical Finishing Speeds
   - #17 Drop Rate
   - #18 "What to Expect" Summary
2. **Sprint 009: Advanced Predictions & Weather**
   - #10 Wind Exposure Zones
   - #12 Pack Odds
   - #20 Weather-Adjusted Predictions
3. **Sprint 010: Visualization & Replay**
   - #11 Predicted Finish Type (Enhanced UX over Sprint 007 baseline)
   - #19 Predicted Key Moments on Map
   - #28 Animated Race Replay

## Use Cases

1. **Interactive Mapping**: As a racer, I can view an interactive course map (pan/zoom) and an elevation profile. Hovering over the elevation profile highlights the corresponding geographic location on the map, helping me connect topography to the real world.
2. **Climb Segments**: As a racer, I can see significant climbs color-coded by gradient on both the map and the elevation profile, so I know where the decisive efforts will be required.
3. **Historical Context**: As a racer, I can see the historical Drop Rate and Typical Finishing Speeds for my category, giving me a baseline for how selective and fast the race typically is.
4. **Narrative Summary**: As a racer, I can read a concise "What to Expect" narrative that translates raw stats and predictions into a plain-language race script.

## Architecture

### 1. Synchronized Interactive Map (Addressing the Streamlit/Folium Challenge)
**The Challenge:** Streamlit's `st_folium` integration triggers a full Python script rerun on interaction and doesn't natively support listening to Plotly hover events to update a map marker without unacceptable latency.
**The Solution:** Build a custom Streamlit HTML component (`streamlit.components.v1.html`) that bundles Leaflet.js (for the map) and Chart.js or Plotly.js (for the elevation profile) inside a single iframe. 
- Python prepares the track points (lat, lon, elevation, distance) as a JSON payload.
- The custom HTML component renders both the map and the chart.
- JavaScript within the iframe handles the hover event on the chart and moves a Leaflet marker instantaneously, avoiding Streamlit's Python server roundtrip.

### 2. Climb Detection Algorithm
We will implement a sliding window algorithm over the RWGPS `track_points` to detect sustained climbs.
- **Smoothing:** Apply a moving average to the elevation data to filter out GPS noise.
- **Detection:** Calculate the gradient (Δelevation / Δdistance) over a rolling window (e.g., 500m).
- **Thresholding:** Segments with a sustained gradient > 4% for > 500m are flagged as climbs. They are categorized by severity (e.g., Cat 4 to HC, or simply color-coded: 4-6% yellow, 6-9% red, 9%+ dark red).

### 3. Historical Stats Engine
- **Drop Rate (#17):** Calculated by querying `Result` for a given `series_id` and `category`. Formula: `(DNF + DQ + DNP) / Total Starters`. Gracefully degrade if `Total Starters < 10`.
- **Typical Finishing Speeds (#16):** Query `Result.race_time_seconds` for the top 10 finishers in the category. Calculate speed using `Course.distance_m`. Return the median winning group speed (to exclude neutralized rollouts or anomalous timing errors).

### 4. Narrative Generator (#18)
Instead of relying on an LLM (which introduces latency, cost, and unpredictability), we will use a **Template-Based Engine**. It ensures deterministic, fast, and highly reliable prose.
- Inputs: Terrain type, predicted finish type, drop rate, typical speed.
- Output: A dynamic, plain-English summary. Example: "This rolling course typically results in a small group sprint. It is highly selective, with a historical drop rate of 25%, and the winning group usually averages around 24.5 mph."

## Implementation Phases

### Phase 1: Data Processing & Algorithms (`raceanalyzer/predictions.py`, `raceanalyzer/elevation.py`)
- Implement `extract_climb_segments(track_points)` in `elevation.py`.
- Implement `calculate_drop_rate(session, series_id, category)` in `predictions.py`.
- Implement `calculate_typical_speeds(session, series_id, category)` in `predictions.py`.
- Implement `generate_race_narrative(course_type, finish_type, drop_rate, speed)` in `predictions.py`.

### Phase 2: Custom Interactive Component (`raceanalyzer/ui/components/map_profile.html`)
- Create a self-contained HTML file loading Leaflet and Chart.js from CDNs.
- Implement the JavaScript logic to draw the polyline, render the elevation area chart, and sync the chart's `onHover` event to update a Leaflet `L.circleMarker` position.
- Wrap this in a Python function `render_interactive_course_profile(track_points_json)`.

### Phase 3: UI Integration (`raceanalyzer/ui/pages/race_preview.py`)
- Replace the existing `render_course_map` static Folium call with the new interactive component.
- Add UI cards for "Historical Stats" displaying Drop Rate and Speed with clear explanations.
- Prominently display the "What to Expect" narrative at the top of the Race Preview page.

## Code Sketches

### Climb Detection Algorithm
```python
def extract_climb_segments(track_points: list[dict], min_gradient=0.04, min_length_m=500.0) -> list[dict]:
    """
    track_points: list of dicts with 'distance', 'elevation', 'lat', 'lon'
    """
    climbs = []
    # 1. Smooth elevation data (e.g., 100m rolling average)
    smoothed_pts = _apply_moving_average(track_points)
    
    # 2. Sliding window to find sustained gradients
    current_climb = None
    for i in range(1, len(smoothed_pts)):
        dx = smoothed_pts[i]['distance'] - smoothed_pts[i-1]['distance']
        dy = smoothed_pts[i]['elevation'] - smoothed_pts[i-1]['elevation']
        grad = dy / dx if dx > 0 else 0
        
        if grad >= min_gradient:
            if not current_climb:
                current_climb = {'start_idx': i-1, 'start_dist': smoothed_pts[i-1]['distance']}
        else:
            if current_climb:
                length = smoothed_pts[i-1]['distance'] - current_climb['start_dist']
                if length >= min_length_m:
                    current_climb['end_idx'] = i-1
                    climbs.append(current_climb)
                current_climb = None
    return climbs
```

### Map-Profile Sync (JS snippet for HTML component)
```javascript
// Assume 'map' is a Leaflet instance and 'chart' is a Chart.js instance
let marker = L.circleMarker([0, 0], { radius: 5, color: 'red' }).addTo(map);

chart.options.onHover = (e, elements) => {
    if (elements.length > 0) {
        const index = elements[0].index;
        const pt = trackPoints[index]; // array injected from Python
        marker.setLatLng([pt.lat, pt.lon]);
    }
};
```

## Files Summary

| File | Action | Description |
|------|--------|-------------|
| `raceanalyzer/elevation.py` | MODIFY | Add `extract_climb_segments()` algorithm. |
| `raceanalyzer/predictions.py` | MODIFY | Add drop rate, speed calculations, and narrative template logic. |
| `raceanalyzer/ui/maps.py` | MODIFY | Expose a function to render the custom Streamlit HTML component. |
| `raceanalyzer/ui/templates/map_profile.html` | CREATE | Custom HTML/JS for Leaflet + Chart.js bidirectional sync. |
| `raceanalyzer/ui/pages/race_preview.py` | MODIFY | Integrate the new interactive map, narrative, and historical stats cards. |
| `tests/test_predictions.py` | MODIFY | Add unit tests for drop rate, speeds, and narrative generation. |
| `tests/test_elevation.py` | MODIFY | Add tests verifying climb detection on sample RWGPS data. |

## Definition of Done

- [ ] `calculate_drop_rate` accurately calculates the DNF/DQ percentage for a category, handling edge cases (no data).
- [ ] `calculate_typical_speeds` returns the median speed of top finishers.
- [ ] `extract_climb_segments` successfully identifies sustained climbs from raw track point data.
- [ ] A custom HTML component displays a Leaflet map and elevation chart simultaneously.
- [ ] Hovering over the elevation chart smoothly moves a marker on the map without Streamlit reloading.
- [ ] The Race Preview UI displays the Narrative Summary, Drop Rate, and Speed metrics cleanly.
- [ ] Features degrade gracefully (e.g., if a race has no track points, show stats without map; if no history, show map without stats).
- [ ] Unit tests cover all new algorithms with >85% coverage.

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **Streamlit Custom Component Rendering** | High | Medium | If `components.v1.html` feels clunky or has layout issues, ensure we use responsive CSS (`width: 100%`) inside the iframe and set a fixed height in Python. |
| **Noisy GPS Elevation Data** | Medium | High | Raw RWGPS elevation can be noisy, causing false positive climb detections. We must apply a moving average / smoothing function before calculating gradients. |
| **Speed Calculation Outliers** | Low | Medium | Some races have neutralized rollouts or timing errors resulting in 5mph or 40mph averages. We mitigate this by using the median of the top 10 finishers and filtering absurd values. |

## Security

- **XSS Prevention:** Data passed to the custom HTML component must be strictly JSON serialized. No user input will be directly injected into the HTML template unescaped.
- **Dependencies:** Leaflet and Chart.js will be loaded from reputable CDNs (e.g., cdnjs, unpkg) using Subresource Integrity (SRI) hashes to prevent supply chain attacks.

## Dependencies

- No new Python packages are required.
- Frontend libraries (Leaflet.js, Chart.js) will be loaded via CDN. OpenStreetMap tiles will be used for the map background to avoid API key requirements.

## Open Questions

1. **Wind exposure data source:** Addressed for Sprint 009. We will likely use Overpass API to query land-use tags along the route to determine tree cover.
2. **"Key moments" algorithm:** Addressed for Sprint 010. We will correlate historical gap-grouping (from `Result.gap_group_id`) with climb locations.
3. **Pack odds calculation:** Addressed for Sprint 009. Will be a function of historical drop rate and the user's relative category ranking.
4. **RWGPS track_points extraction:** Do we already persist full `track_points` in the DB or just the encoded polyline? If only the polyline, we must update `raceanalyzer/rwgps.py` to store or fetch track points (distance/elevation arrays) since polyline decoding only yields lat/lon, not elevation or distance along route. *(Needs verification before phase 1).*