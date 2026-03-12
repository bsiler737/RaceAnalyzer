# RaceAnalyzer User Stories

> **Instructions for Reviewer:** Mark each story as `[GOOD]` or `[BAD]` to indicate whether you want **more** capabilities like this or **fewer**. This feedback will guide future development priorities.
>
> | Rating   | Meaning |
> |----------|---------|
> | `[GOOD]` | We want more capabilities like this — invest here |
> | `[BAD]`  | We want fewer capabilities like this — deprioritize or remove |

---

## Data Acquisition & Scraping

### 1. Scrape a Single Race from Road-Results
**As a** data analyst, **I want to** scrape a single race by ID from road-results.com **so that** I can quickly pull in results for a specific event I'm interested in.

**Review:** `[ Bad]`

---

### 2. Bulk Scrape a Range of Races
**As a** database administrator, **I want to** scrape a range of race IDs in one command **so that** I can efficiently backfill historical data without running individual commands.

**Review:** `[ Good]`

---

### 3. Resume an Interrupted Scrape
**As a** data analyst, **I want to** resume a scrape that was interrupted partway through **so that** I don't re-download races I've already captured and waste time or hit rate limits.

**Review:** `[Good ]`

---

### 4. Bypass Cloudflare Protection
**As a** data engineer, **I want** the scraper to automatically handle Cloudflare challenges **so that** scraping doesn't fail on protected pages.

**Review:** `[GOod ]`

---

### 5. Respect Rate Limits During Scraping
**As a** responsible data consumer, **I want** the scraper to enforce configurable delays and exponential backoff **so that** I don't overload source websites or get banned.

**Review:** `[ Good]`

---

### 6. Archive Raw HTML and JSON
**As a** data analyst, **I want** raw scraped HTML and JSON saved to disk **so that** I can reparse data later if my parsing logic changes without re-scraping.

**Review:** `[ GOod]`

---

## Calendar & Upcoming Events

### 7. Discover Upcoming Races from BikeReg
**As a** racer, **I want to** see upcoming cycling events pulled from BikeReg **so that** I can plan my race calendar without checking multiple websites.

**Review:** `[ Good]`

---

### 8. Match Upcoming Events to Known Series
**As a** racer, **I want** upcoming events automatically fuzzy-matched to historical race series **so that** I get context about what a race is typically like before I register.

**Review:** `[ Good]`

---

### 9. View Registration Links for Upcoming Races
**As a** racer, **I want to** click through to the registration page for an upcoming event **so that** I can sign up directly from the race calendar view.

**Review:** `[ Good]`

---

## Startlist Intelligence

### 10. Fetch Confirmed Startlists from BikeReg
**As a** racer, **I want to** see who is registered for an upcoming race **so that** I can gauge the competition before race day.

**Review:** `[Good ]`

---

### 11. Filter Startlists by Category
**As a** Cat 3 racer, **I want to** filter the startlist to my specific category **so that** I only see the riders I'll actually be racing against.

**Review:** `[ Good]`

---

## Race Classification & Analysis

### 12. Classify How a Race Finished
**As a** racer, **I want** each race automatically classified by finish type (bunch sprint, breakaway, etc.) **so that** I understand the dynamics of races I missed or want to study.

**Review:** `[ Good]`

---

### 13. See Confidence Levels on Classifications
**As a** coach, **I want to** see a confidence score on each finish type classification **so that** I know how reliable the analysis is before basing training decisions on it.

**Review:** `[ Bad]`

---

### 14. Detect Time Trials Automatically
**As a** data analyst, **I want** time trials identified through multiple detection methods (metadata, keywords, statistical spacing) **so that** they're correctly separated from mass-start races.

**Review:** `[ Good]`

---

### 15. View Gap Group Structure
**As a** racer, **I want to** see how the field split into gap groups **so that** I can understand where the race broke apart and how decisive the selection was.

**Review:** `[ Good]`

---

### 16. Understand Group Size and Gaps
**As a** coach, **I want to** see the number of riders in each group and the time gaps between groups **so that** I can identify whether my athlete was in the front selection or the chase.

**Review:** `[ GOod]`

---

### 17. Classify Races Across All Categories at Once
**As a** data analyst, **I want to** classify all unclassified races in the database with a single command **so that** I can batch-process new data efficiently.

**Review:** `[good]`

---

### 18. Adjust Gap Threshold for Classification
**As a** analyst, **I want to** configure the gap threshold used for grouping riders **so that** I can tune the classification for different race types (e.g., looser thresholds for gravel).

**Review:** `[ Bad]`

---

## Series Management

### 19. Automatically Group Races into Series
**As a** racer, **I want** recurring races (e.g., annual editions of the same event) grouped into series **so that** I can see the history of a race across years.

**Review:** `[ Good]`

---

### 20. Normalize Messy Race Names
**As a** data analyst, **I want** race names cleaned of year numbers, ordinals, sponsor tags, and abbreviations **so that** "2023 21st Annual Banana Belt RR presented by Acme" and "Banana Belt Road Race 2024" end up in the same series.

**Review:** `[good]`

---

### 21. Browse All Editions of a Series
**As a** racer, **I want to** see all historical editions of a race series with dates and classifications **so that** I can track how a race has evolved over time.

**Review:** `[ Bad]`

---

### 22. View Classification Trends Across Editions
**As a** coach, **I want to** see a trend chart showing how finish types changed across editions of a series **so that** I can identify if a race is becoming more selective or more sprint-friendly.

**Review:** `[ Good]`

---

## Course & Terrain Intelligence

### 23. Find Matching Routes on RideWithGPS
**As a** racer, **I want** the system to automatically find the most likely RWGPS route for a race **so that** I can preview the course without manual searching.

**Review:** `[ Good]`

---

### 24. View Elevation Profile Data
**As a** racer, **I want to** see total elevation gain, distance, and min/max elevation for a race course **so that** I know what kind of terrain to expect.

**Review:** `[ Good]`

---

### 25. See Terrain Classification
**As a** racer, **I want** courses classified as flat, rolling, hilly, or mountainous **so that** I can quickly assess whether a race suits my strengths.

**Review:** `[ Good]`

---

### 26. View Course Maps
**As a** racer, **I want to** see the race course plotted on a map **so that** I can study the route, identify key sections, and plan my pre-ride.

**Review:** `[ ]`

---

### 27. Read Terrain-Based Tactical Descriptions
**As a** newer racer, **I want** plain-language descriptions of what to expect on each terrain type **so that** I can understand race dynamics even without years of experience (e.g., "climbers and breakaway artists have the advantage").

**Review:** `[ Good]`

---

## Predictions & Forecasting

### 28. Predict Finish Type for Upcoming Races
**As a** racer, **I want** a predicted finish type for an upcoming race based on historical editions **so that** I can tailor my race strategy (e.g., train for a sprint vs. a breakaway).

**Review:** `[ Good]`

---

### 29. See Prediction Confidence
**As a** coach, **I want to** see whether a finish type prediction is high, moderate, or low confidence **so that** I weight it appropriately in race planning.

**Review:** `[ Good]`

---

### 30. View Predicted Contenders
**As a** racer, **I want to** see a ranked list of likely top finishers for an upcoming race **so that** I know who to watch and mark in the field.

**Review:** `[ Good]`

---

### 31. Contenders from Startlist When Available
**As a** racer, **I want** contender predictions based on the actual startlist when it's available **so that** predictions reflect who's actually showing up, not just historical participants.

**Review:** `[ Good]`

---

### 32. Fallback Contenders from Historical Data
**As a** racer, **I want** contender predictions even when no startlist exists, based on historical series performers or top regional riders **so that** I still get useful intel for races without published startlists.

**Review:** `[ Bad]`

---

### 33. See Top Competitors ("Scary Racers") by Category
**As a** racer, **I want to** see who the strongest riders are in my category across the region **so that** I know the key names to watch all season.

**Review:** `[ Good]`

---

## Visual Exploration & Dashboard

### 34. Browse Races in a Tile Calendar View
**As a** racer, **I want to** browse races as visual tiles grouped by series **so that** I can quickly scan the race calendar and find events of interest.

**Review:** `[ Good]`

---

### 35. Filter Races by Year
**As a** racer, **I want to** filter the race calendar by year **so that** I can focus on a specific season's events.

**Review:** `[Bad ]`

---

### 36. Filter Races by State or Province
**As a** PNW racer, **I want to** filter races by state (WA, OR, ID) or province (BC) **so that** I only see events within my travel range.

**Review:** `[ Good]`

---

### 37. Filter Races by Category
**As a** Cat 3 racer, **I want to** filter everything by my race category **so that** all analysis, predictions, and results are relevant to my field.

**Review:** `[ Good]`

---

### 38. View Finish Type Distribution Charts
**As a** analyst, **I want to** see pie and bar charts of finish type distribution across all classified races **so that** I understand the overall character of racing in my region.

**Review:** `[good]`

---

### 39. Track Finish Type Trends Over Time
**As a** analyst, **I want to** see a stacked area chart of how finish type proportions change year over year **so that** I can identify macro trends in how races are being decided.

**Review:** `[bad]`

---

### 40. View Race Detail with Full Results
**As a** racer, **I want to** drill into a specific race and see full per-category results with classifications **so that** I can study exactly what happened.

**Review:** `[good]`

---

### 41. Navigate Between Editions from Race Detail
**As a** racer, **I want** the race detail page to show other editions of the same series in a sidebar **so that** I can quickly compare this year's race to previous years.

**Review:** `[ good]`

---

### 42. View Location Maps for Races
**As a** racer, **I want to** see a map centered on the race location **so that** I can orient myself geographically even when a course map isn't available.

**Review:** `[ good]`

---

## Race Preview (Pre-Race Analysis)

### 43. Get a Complete Pre-Race Preview
**As a** racer, **I want** a single "race preview" page combining course profile, predicted finish type, and top contenders **so that** I have everything I need to prepare in one place.

**Review:** `[ good]`

---

### 44. See Course Profile Card in Preview
**As a** racer, **I want** the race preview to show terrain type, elevation gain, and distance at a glance **so that** I can assess course difficulty instantly.

**Review:** `[ good]`

---

## Data Quality & Feedback

### 45. Provide Finish Type Labels for Training
**As a** experienced racer, **I want to** submit my own label for how a race actually finished **so that** the system can learn from human knowledge and improve its classifier.

**Review:** `[ bad]`

---

### 46. See Predicted vs. Actual Finish Types
**As a** analyst, **I want to** compare the system's classification against user-submitted labels **so that** I can measure and improve classifier accuracy.

**Review:** `[ bad]`

---

### 47. Handle Missing or Incomplete Data Gracefully
**As a** user, **I want** the app to degrade gracefully when data is missing (no startlist, no elevation, no course map) **so that** I still get useful information rather than error screens.

**Review:** `[ ]`

---

## Infrastructure & Setup

### 48. Initialize the Database with One Command
**As a** developer, **I want to** run `raceanalyzer init` to create the full database schema **so that** I can get started quickly without manual SQL.

**Review:** `[ good]`

---

### 49. Generate Demo Data for Testing
**As a** developer, **I want to** generate ~50 realistic synthetic PNW races with results **so that** I can test the UI and analysis features without scraping real data first.

**Review:** `[ bad]`

---

### 50. Infer Race Type from Name
**As a** data analyst, **I want** the system to automatically classify races as criteriums, road races, time trials, hill climbs, gravel, or stage races based on name keywords **so that** race types are populated without manual tagging.

**Review:** `[ good]`

---

## Summary

| Category | Stories | Range |
|---|---|---|
| Data Acquisition & Scraping | 6 | #1–6 |
| Calendar & Upcoming Events | 3 | #7–9 |
| Startlist Intelligence | 2 | #10–11 |
| Race Classification & Analysis | 7 | #12–18 |
| Series Management | 4 | #19–22 |
| Course & Terrain Intelligence | 5 | #23–27 |
| Predictions & Forecasting | 6 | #28–33 |
| Visual Exploration & Dashboard | 9 | #34–42 |
| Race Preview | 2 | #43–44 |
| Data Quality & Feedback | 3 | #45–47 |
| Infrastructure & Setup | 3 | #48–50 |
| **Total** | **50** | |
