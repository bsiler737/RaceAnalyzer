# Sprint 007: Schema Foundation, Baseline Predictions & Race Preview

## Overview

Based on the strategic direction from `mid-plan-improvements.md` (specifically Sprint 2a: "Ship Something Racers Can Use"), this sprint begins the transition of RaceAnalyzer from a retrospective data viewer into a prospective race prediction tool. The primary objective is to allow a racer to view upcoming events, see the expected terrain, read a predicted finish type, and review the top contenders.

This sprint will introduce structural database additions (courses, startlists, user labels, and rider rating columns). We will extract elevation profiles from RideWithGPS data to calculate a 4-bin terrain classification. To provide immediate value before implementing complex machine learning, we will deploy a **Baseline Heuristic Predictor** using existing `carried_points` data. Finally, we will build a mobile-first **Race Preview** page and integrate upcoming events into the existing calendar.

---

## Use Cases

1. **As a racer**, I can look at the calendar and see upcoming races with a predicted finish type, helping me plan my race season.
2. **As a racer**, I can view a mobile-friendly Race Preview page for an upcoming event, showing course terrain, predicted finish type, and top contenders.
3. **As a racer**, I can see if a course is Flat, Rolling, Hilly, or Mountainous based on elevation data extracted from RWGPS routes.
4. **As a developer**, I can run `raceanalyzer elevation-extract` to populate the new `courses` table using data extracted from matched RWGPS routes.
5. **As a developer**, I can run a baseline prediction on a race and see it rank riders using a simple heuristic (e.g., field-adjusted average finish percentile derived from `carried_points`).
6. **As a developer**, I can run `raceanalyzer scrape-startlists` to pull upcoming confirmed riders via the BikeReg API or CSV endpoint.

---

## Architecture

*   **Schema Enhancements**: 
    *   Add `Course` table linked to `RaceSeries`. 
    *   Add `Startlist` and `UserLabel` tables.
    *   Add rating columns (`mu`, `sigma`, `num_races`) to the `Rider` model, and snapshot columns (`prior_mu`, `prior_sigma`, `mu`, `sigma`, `predicted_place`) to the `Result` model. 
    *   Add `CourseType` enum (FLAT, ROLLING, HILLY, MOUNTAINOUS).
*   **Elevation Extraction Pipeline**: 
    *   Use RWGPS summary stats (`distance` and `elevation_gain`). Calculate the `m_per_km` ratio.
    *   Map `m_per_km` to `CourseType` bins to assign a terrain classification.
*   **Startlist Scraper**: 
    *   A new `BikeRegScraper` class will target BikeReg API/CSV endpoints to download confirmed registered riders. Implements graceful degradation (tier 1: startlist -> tier 2: historical performers).
*   **Prediction Layer**: 
    *   A `BaselinePredictor` module. It calculates expected finish percentiles using `carried_points`. It combines historical series classification with the new terrain classification to predict the race outcome.
*   **UI Architecture**: 
    *   Introduce a new Streamlit page `race_preview.py` designed mobile-first using responsive columns. 
    *   Extend `calendar.py` to query future races and show registration links alongside historical data.

---

## Implementation

### Phase 1: Schema Extensions
**Files:**
*   `raceanalyzer/db/models.py`

**Tasks:**
1.  Add `CourseType` enum with values: `FLAT`, `ROLLING`, `HILLY`, `MOUNTAINOUS`.
2.  Create `Course` model: `id`, `series_id` (ForeignKey), `distance`, `elevation_gain`, `m_per_km`, `course_type`, `version_hash`.
3.  Create `Startlist` model: `id`, `race_id`, `category`, `rider_name`, `team_name`, `source`, `scraped_at`.
4.  Create `UserLabel` model: `id`, `race_id`, `category`, `finish_type`, `user_id` (or session UUID), `created_at`.
5.  Update `Rider` model: Add `mu` (Float), `sigma` (Float), `num_races` (Integer).
6.  Update `Result` model: Add `prior_mu`, `prior_sigma`, `mu`, `sigma`, `predicted_place`.

### Phase 2: Elevation Extraction & Terrain Classification
**Files:**
*   `raceanalyzer/rwgps.py`
*   `raceanalyzer/classification/terrain.py` (New)
*   `raceanalyzer/cli.py`

**Tasks:**
1.  Update `rwgps.py` fetch/search logic to ensure `distance` and `elevation_gain` are retained from the JSON payloads.
2.  Create `terrain.py`: Implement logic to calculate `m_per_km` = `elevation_gain / (distance / 1000)`.
3.  Implement threshold logic in `terrain.py`: Flat (<5 m/km), Rolling (5-10 m/km), Hilly (10-15 m/km), Mountainous (>15 m/km).
4.  Add `raceanalyzer elevation-extract` CLI command to iterate through series with a known `rwgps_route_id`, fetch route stats, classify terrain, and insert/update rows in the `Course` table.

### Phase 3: Startlist Scraping & Upcoming Calendar
**Files:**
*   `raceanalyzer/scraper/bikereg.py` (New)
*   `raceanalyzer/cli.py`
*   `raceanalyzer/queries.py`

**Tasks:**
1.  Implement `BikeRegScraper` using the `requests` library to fetch confirmed riders from BikeReg. Must include 2-second base delay and exponential backoff on HTTP 429.
2.  Add `raceanalyzer scrape-startlists` CLI command to orchestrate fetching and writing to the `Startlist` table.
3.  Update `queries.py` to include `get_upcoming_races()` and `get_startlist(race_id, category)`.

### Phase 4: Baseline Prediction Model
**Files:**
*   `raceanalyzer/classification/prediction.py` (New)
*   `raceanalyzer/queries.py`

**Tasks:**
1.  Create a `BaselinePredictor` class.
2.  Implement logic to rank riders by their historical `carried_points` across the last 12 months.
3.  For a given race series and category:
    *   If a startlist is available: Rank registered riders using the baseline heuristic.
    *   If a startlist is unavailable: Fall back to pulling the top 5 historical performers at this series.
4.  Predict the expected `FinishType` by looking at the series' historical `overall_finish_type` and mapping it against the newly established `CourseType`.

### Phase 5: Race Preview UI & Calendar Integration
**Files:**
*   `raceanalyzer/ui/pages/race_preview.py` (New)
*   `raceanalyzer/ui/pages/calendar.py`
*   `raceanalyzer/ui/components.py`

**Tasks:**
1.  Build `race_preview.py` heavily utilizing Streamlit's container and column layouts for mobile responsiveness.
    *   Top section: Predicted finish type badge, terrain type badge, and natural language confidence indicators.
    *   Middle section: Course map (Folium polyline) and elevation summary.
    *   Bottom section: Top contenders list (displaying startlist data or historical fallback data).
2.  Modify `calendar.py`: Include future dates queried from the database. Differentiate visually between past series data and upcoming scheduled races. Include BikeReg/Registration links.

---

## Files Summary

*   `raceanalyzer/db/models.py`: Add `Course`, `Startlist`, `UserLabel` models; update `Rider`/`Result` models.
*   `raceanalyzer/rwgps.py`: Expose elevation/distance data.
*   `raceanalyzer/classification/terrain.py`: New terrain classification logic.
*   `raceanalyzer/scraper/bikereg.py`: New scraper tailored to BikeReg API/CSV.
*   `raceanalyzer/classification/prediction.py`: New baseline prediction heuristic.
*   `raceanalyzer/cli.py`: Add `elevation-extract` and `scrape-startlists` commands.
*   `raceanalyzer/queries.py`: Add queries for predictions, upcoming races, and startlists.
*   `raceanalyzer/ui/pages/race_preview.py`: New mobile-first Race Preview page.
*   `raceanalyzer/ui/pages/calendar.py`: Integrate upcoming races into calendar view.
*   `tests/`: Add tests for elevation extraction, baseline prediction, and BikeReg scraping (mocking HTTP via `responses`).

---

## Definition of Done

1.  `courses`, `startlists`, and `user_labels` tables are present in the database schema.
2.  `raceanalyzer elevation-extract` correctly calculates `m_per_km`, categorizes routes into 4 bins, and saves to the `Course` table.
3.  `BikeRegScraper` fetches upcoming riders, writes to the `Startlist` table, and gracefully handles rate limits/errors.
4.  Baseline predictor successfully ranks riders based on `carried_points` and outputs a predicted finish type.
5.  `Race Preview` page loads without horizontal scrolling on mobile viewports, successfully displaying the terrain, prediction, course map, and top contenders.
6.  Unit tests added for all new classification and scraping logic, achieving >85% coverage for new files.

---

## Risks & Mitigations

*   **Risk**: BikeReg API is undocumented, relies on CSV exports, or changes structure.
    *   **Mitigation**: Implement robust exception handling and fallback to "historical performers" if startlist fetch fails entirely.
*   **Risk**: RWGPS data lacks `elevation_gain` for some routes or requires higher-resolution point processing.
    *   **Mitigation**: Fallback to historical finish type as a proxy for course difficulty if terrain cannot be explicitly calculated. Limit phase 0 to basic summary stats before dealing with peak detection.
*   **Risk**: Overcomplicating the Baseline Predictor and missing the sprint timeline.
    *   **Mitigation**: Strictly use `carried_points` to generate a percentile. Do not attempt to calculate Glicko-2 ratings in this sprint (deferred to Sprint 2b).

---

## Security Considerations

*   Ensure the `BikeRegScraper` strictly enforces a 2-second rate limit to prevent IP bans or service disruption.
*   No PII (Personally Identifiable Information) outside of public racing data is logged or surfaced.
*   Maintain the existing paradigm of guarding against SQL injection by exclusively using SQLAlchemy ORM and parametrized queries.

---

## Dependencies

*   `requests` (already present)
*   `responses` (for mocking HTTP calls in tests)
*   *Note: No new ML libraries (e.g., `skelo`, `scipy`) are introduced in this sprint to keep the baseline simple and ship fast.*

---

## Open Questions

1.  Does the BikeReg API require authentication for the "Confirmed Riders" list, or is the CSV export publicly accessible without session cookies?
2.  Should we maintain granular versioning for courses in this sprint (e.g. tracking minor route deviations year-to-year), or can we defer `course_version` to the next sprint and map directly via `series_id`?
3.  Where should the user access the Race Preview page? As a dedicated tab within the existing Series Detail page, or as a distinct top-level page linked from the Upcoming Calendar?