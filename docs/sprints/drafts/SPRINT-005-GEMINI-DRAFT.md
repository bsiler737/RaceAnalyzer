# Sprint 005 Draft: UI Overhaul & Individual TT Classification

## Overview

This sprint focuses on a significant user interface overhaul to center the user experience around the more insightful `FinishType` classifications rather than the generic `RaceType`. Key initiatives include creating a new `INDIVIDUAL_TT` classification, redesigning the race calendar tiles to be more interactive and informative, implementing real course map scraping from BikeReg with a fallback, and improving UI navigation. The goal is to transform the calendar from a simple list into a rich, data-driven discovery tool.

## Use Cases

1.  **As a user, I want to see a specific classification for Individual Time Trials and Hill Climbs** so that these distinct race formats are correctly identified.
2.  **As a user, I want the icon on each race tile to represent the finish type (e.g., Bunch Sprint, Breakaway)** so I can quickly understand the character of the race at a glance.
3.  **As a user, I want races with unknown finish types to be hidden by default** so I can focus on races with complete and interesting data, with an option to view them if needed.
4.  **As a user, I want to click anywhere on a race tile to navigate to the detail page** for a smoother, more intuitive browsing experience.
5.  **As a user, I want to see the overall race classification directly on the tile** to get a summary of the race's most common finish type.
6.  **As a user, I want to hover over a classification name to see a simple explanation** so I can learn what terms like "GC Selective" or "Reduced Sprint" mean.
7.  **As a user, I want to see a map of the actual race course on the detail page** when available, sourced from services like RideWithGPS or Strava, to better understand the race's terrain.
8.  **As a user, I want a clear "Back" button on the race detail page** to easily return to the calendar grid.

## Architecture

This sprint introduces changes across the data, classification, and UI layers.

1.  **Data Layer**: The `FinishType` enum in `raceanalyzer/db/models.py` will be extended with an `INDIVIDUAL_TT` member. No other schema changes are required.
2.  **Classification Layer**: The classifier in `raceanalyzer/classification/finish_type.py` will be enhanced to detect Individual TTs. This will be a pre-classification step that runs before the gap-based analysis. It will use race metadata (name, `RaceType`) and statistical analysis of results (high number of groups, coefficient of variation).
3.  **Query Layer**: The `get_race_tiles` function in `raceanalyzer/queries.py` will be modified to join `races` with `race_classifications`. It will calculate an "overall" finish type for each race, defined as the most frequently occurring `FinishType` across all of its categories (excluding 'UNKNOWN').
4.  **UI Layer**:
    *   **Components**: `raceanalyzer/ui/components.py` will be heavily modified. The existing `RACE_TYPE_ICONS` will be replaced by a new `FINISH_TYPE_ICONS` dictionary. The `render_race_tile` function will be re-written to use these new icons, display the overall classification, and embed the entire tile in a clickable anchor tag with CSS for hover effects. Tooltips will be implemented using the `title` attribute in HTML.
    *   **Pages**: `raceanalyzer/ui/pages/calendar.py` will incorporate a `st.toggle` to control the visibility of races classified as `UNKNOWN`. `raceanalyzer/ui/pages/race_detail.py` will feature a simple `st.button` for back-navigation.
5.  **Scraping**: A new utility function will be developed to attempt scraping BikeReg race pages for RideWithGPS or Strava links. This will be a best-effort service with a fallback strategy to display a static map based on the race's location string if no course-specific URL is found.

## Implementation

### `raceanalyzer/db/models.py`

*   In `class FinishType(enum.Enum)`, add a new member: `INDIVIDUAL_TT = "individual_tt"`

### `raceanalyzer/classification/finish_type.py`

*   A new function `is_individual_time_trial(race: Race, results: list[Result]) -> bool` will be created and called at the beginning of the classification process.
*   **Proposed Algorithm**:
    1.  **Metadata Check**: Return `True` if `race.race_type` is `TIME_TRIAL` or `HILL_CLIMB`, or if "Time Trial" or "Hill Climb" (case-insensitive) is in `race.name`.
    2.  **Statistical Check**: If metadata check fails, analyze the results for a given category. A race is likely an ITT if:
        *   The number of groups is high (e.g., `> 0.7 * total_finishers`), indicating most riders finished alone.
        *   The coefficient of variation (CV) of finish times is high (e.g., `> 0.9`), indicating a wide, steady spread of times.
        *   The standard deviation of time gaps between consecutive finishers is low, indicating evenly spaced riders. This is a strong signal for staggered starts.

### `raceanalyzer/queries.py`

*   Modify `get_race_tiles` to include the overall `finish_type`:
    *   Perform a LEFT JOIN from `Race` to `RaceClassification`.
    *   Use a window function or a subquery with `MODE()` to find the most frequent non-'UNKNOWN' `finish_type` for each `race_id`.
    *   Return this new `overall_finish_type` field in the DataFrame.
*   Add `INDIVIDUAL_TT` to the `FINISH_TYPE_DISPLAY_NAMES` dictionary: `"individual_tt": "Individual TT"`.

### `raceanalyzer/ui/components.py`

*   Remove `RACE_TYPE_ICONS` and `RACE_TYPE_COLORS`.
*   Add `FINISH_TYPE_ICONS` with unique SVG designs for each type:
    *   **`BUNCH_SPRINT`**: Icon showing a tight cluster of dots.
    *   **`BREAKAWAY`**: Icon showing one or two dots ahead of a larger cluster.
    *   **`INDIVIDUAL_TT`**: Icon of a stopwatch.
    *   **`GC_SELECTIVE`**: Icon of a fragmented line of dots.
    *   ...and so on for all types.
*   Add `FINISH_TYPE_TOOLTIPS` dictionary mapping `FinishType` enums to plain-language descriptions (e.g., `BUNCH_SPRINT`: "A finish where the main pack of riders sprinted for the line together.").
*   Rewrite `render_race_tile`:
    *   It will accept the new `overall_finish_type` data.
    *   The entire component will be wrapped in `st.markdown(f'<a href="..." style="text-decoration: none; color: inherit;" target="_self">{tile_html}</a>', unsafe_allow_html=True)`.
    *   A `<style>` block will be injected via `st.markdown` to add hover effects (e.g., `a:hover > div { box-shadow: ...; }`).
    *   The classification text will be rendered in a `span` with a `title` attribute containing the tooltip text.

### `raceanalyzer/ui/pages/calendar.py`

*   Add a toggle: `show_unknown = st.toggle("Show races with unknown classification", value=False)`.
*   Filter the DataFrame before rendering: `if not show_unknown: df = df[df["overall_finish_type"] != "UNKNOWN"]`.

### `raceanalyzer/ui/pages/race_detail.py`

*   At the top of the page, add: `if st.button("⬅️ Back to Calendar"): st.switch_page("pages/calendar.py")`.

### `raceanalyzer/scraper/bikereg_scraper.py` (New File)

*   **Feasibility**: Scraping is feasible but potentially brittle due to site changes or anti-bot measures.
*   **Proposed Function**: `def get_course_map_url(bikereg_race_url: str) -> Optional[str]:`
    *   Use `requests` to fetch the HTML.
    *   Use `BeautifulSoup` to parse it.
    *   Search for all `<a>` tags where the `href` attribute contains "ridewithgps.com/routes/" or "strava.com/routes/".
    *   Return the first match.
*   **Fallback Strategy**: If `get_course_map_url` returns `None`, the `race_detail` page will use the `race.location` string to generate a URL for a static map image centered on that location (e.g., using an OpenStreetMap embed). If location is also unavailable, no map will be shown.

## Files Summary

*   **Modified**:
    *   `raceanalyzer/db/models.py`
    *   `raceanalyzer/classification/finish_type.py`
    *   `raceanalyzer/queries.py`
    *   `raceanalyzer/ui/components.py`
    *   `raceanalyzer/ui/pages/calendar.py`
    *   `raceanalyzer/ui/pages/race_detail.py`
*   **Created**:
    *   `raceanalyzer/scraper/bikereg_scraper.py` (or similar utility file)

## Definition of Done

*   [ ] `FinishType` enum contains `INDIVIDUAL_TT`.
*   [ ] The classifier correctly identifies known time trials and hill climbs as `INDIVIDUAL_TT`.
*   [ ] Race calendar tiles display an icon corresponding to the race's overall `FinishType`.
*   [ ] A toggle on the calendar page hides/shows races with an `UNKNOWN` classification.
*   [ ] The entire area of a race tile is a single clickable link to its detail page.
*   [ ] The overall `FinishType` (e.g., "Bunch Sprint") is displayed as text on the tile.
*   [ ] Hovering the mouse over the classification text reveals a tooltip with a simple definition.
*   [ ] The race detail page includes a button that navigates back to the calendar page.
*   [ ] The race detail page attempts to display an embedded course map from BikeReg, falling back to a location-based map.
*   [ ] All existing tests pass and new unit tests for the ITT classification logic are added.

## Risks

*   **BikeReg Scraping (High)**: The structure of BikeReg's website may change, breaking the scraper. The site may also employ anti-scraping technologies. The fallback to a location-based map is a critical mitigation.
*   **ITT Detection Accuracy (Medium)**: The heuristic-based algorithm for detecting TTs may produce false positives or negatives. It will require testing and tuning against real data.
*   **Streamlit CSS Customization (Low)**: Implementing hover effects and fully clickable tiles using `st.markdown` can be complex and may have cross-browser quirks.

## Security

*   Any URLs scraped from BikeReg must be validated to ensure they point to expected domains (ridewithgps.com, strava.com) before being used, to prevent potential open redirect vulnerabilities.
*   When scraping, use a responsible crawl rate and a descriptive User-Agent to avoid disrupting the service.

## Dependencies

*   `requests` (likely already present for existing scraper)
*   `beautifulsoup4`

## Open Questions

1.  What is the preferred logic for determining the "overall" classification if a race has multiple categories with different finish types (e.g., Pro/1/2 is a breakaway, Cat 4 is a bunch sprint)? The proposed approach is to use the most frequent non-unknown type. Is this acceptable?
2.  For the map fallback, is an embedded static map image centered on the race's location string sufficient, or should we consider a more interactive map component?
