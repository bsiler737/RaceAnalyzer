# Research Findings: PNW Bike Race Analysis Tool

*Research completed: March 9, 2026*

---

## 1. Data Acquisition: Scraping & Parsing Race Results

### Key Discovery: Hidden JSON API

**road-results.com, results.bikereg.com, and crossresults.com are all the same platform (athleteReg)** and expose a hidden JSON API endpoint:

```
https://www.road-results.com/downloadrace.php?raceID={ID}&json=1
```

This returns structured JSON with **29 fields per result** including: place, rider name, team, finish time, points, field size, category, DNF/DQ flags, license number, age. No HTML parsing needed for core results data.

### Existing Projects

| Project | URL | Notes |
|---------|-----|-------|
| **physinet/road-results** | https://github.com/physinet/road-results | Python, Flask, PostgreSQL. Iterates sequential race IDs, fetches JSON. Scraping code reusable, hosted app defunct. |
| **procyclingstats** (PyPI) | https://pypi.org/project/procyclingstats/ | Gold standard for pro racing data |
| **FirstCyclingAPI** | https://pypi.org/project/FirstCyclingAPI/ | Wraps firstcycling.com |
| **CrossResults dataset** | https://github.com/tristans/crossresults_dataset | Static TSV dataset of cross results |

### What the JSON API Gives You for Free
- Finish times, places, field size, categories
- Rider names/IDs, team names
- Points (current + carried), license numbers, ages
- DNF/DQ/DNP status

### What Still Requires HTML Parsing
- Race date, location
- Time gaps (must be computed from RaceTime values)
- Race Predictor / startlist data
- Upgrade point estimates

### What Doesn't Exist
- No scrapers for USA Cycling results (legacy or current)
- No scrapers for CrossResults (only static TSV dataset)
- No scrapers for the road-results Race Predictor feature

### Other APIs Available
- BikeReg has a REST API and a GraphQL endpoint at `outsideapi.com/fed-gw/graphql` for event/registration metadata

### Recommended Approach
1. Start with the JSON API (`downloadrace.php?raceID={ID}&json=1`) for bulk historical data
2. Iterate sequential race IDs (they appear to be sequential)
3. Supplement with HTML parsing for metadata (dates, locations, time gaps)
4. Build separate scraper for Race Predictor startlist data
5. Reference implementation: `physinet/road-results` repo

---

## 2. Finish Type Classification: Sprint vs. Breakaway vs. Individual

### Key Published Research

**"Technical classification of professional cycling stages using unsupervised learning"** (Frontiers in Sports and Active Living, October 2025)
- Analyzed 439 international race stages (2017-2023)
- Used KMeans clustering on 5 technical variables
- **Key metric: Coefficient of Variation (CV) of finish times** as a proxy for peloton fragmentation
- Flat stages: CV ~0.58-0.66; mountain stages: CV ~0.85-0.89
- Strongest predictors: relative elevation (β=0.42) and unpaved % (β=0.23)
- Tools: Python 3.10, scikit-learn 1.4.2

### UCI "Same Group" Rules (Critical Domain Knowledge)

The UCI defines groups using a **chain rule on consecutive gaps**:
- **Standard rule**: 1 second gap = new time group
- **3-second rule** (sprint stages): Gap threshold widened to 3 seconds for the main peloton
- At 60 km/h, 1 second ≈ 17 meters; 3 seconds ≈ 50 meters
- Chain rule means a stretched peloton can have 30+ seconds between first and last rider while still being "one group"

**For amateur racing at lower speeds (~35-45 km/h), the equivalent gap is 2-4 seconds.**

### Gap Clustering Algorithms (Best to Simplest)

| Algorithm | Description | Best For |
|-----------|-------------|----------|
| **Simple Consecutive Gap Threshold** | Sort by time, split where gap > 3s | Starting point, interpretable |
| **DBSCAN** (eps=3s, min_samples=2) | Density-based, auto-detects group count | Robust, directly encodes gap rule |
| **HDBSCAN** | Hierarchical DBSCAN, handles variable densities | Best for mixed scenarios (tight sprint + spread chase) |
| **Jenks Natural Breaks** | Optimal 1D clustering, minimizes within-class variance | When number of groups can be estimated |

### Finish Type Classification Rules

Once riders are grouped, classify by group structure:

| Finish Type | Pattern | CV Signature |
|-------------|---------|-------------|
| **Bunch Sprint** | One large group (>60% of field), all within seconds | Very low (<0.5%) |
| **Small Group Sprint** | Small lead group (2-10), gap, then main group | Low-moderate |
| **Breakaway** | 1-3 riders with 30s+ gap to main group | Low-moderate |
| **Selective/GC-style** | Many small groups, no dominant large group | High (>1%) |
| **Reduced Sprint** | Medium lead group (10-30) after attrition | Moderate |

### Decision Logic

```python
if largest_group_ratio > 0.5 and gap_to_second_group < 30:
    finish_type = "BUNCH_SPRINT"
elif leader_group_size <= 5 and gap_to_second_group > 30:
    if largest_group_ratio > 0.4:
        finish_type = "BREAKAWAY"
    else:
        finish_type = "BREAKAWAY_SELECTIVE"
elif num_groups > 5 and largest_group_ratio < 0.3:
    finish_type = "GC_SELECTIVE"
elif leader_group_size > 5 and leader_group_size < total * 0.5:
    finish_type = "REDUCED_SPRINT"
else:
    finish_type = "MIXED"
```

### Key Gaps
- **No labeled training data**: No public dataset of race results with labeled finish types. Need to manually label ~100-200 races.
- **Amateur racing specifics**: All research focuses on pro cycling. Amateur field dynamics differ (smaller fields, wider ability range, no leadout trains).
- **Missing time handling**: No validated approach for results with placement-only data.

### Recommended Implementation Path
1. Start with consecutive-gap grouping (3-second threshold)
2. Extract group-structure features (largest group ratio, leader group size, gap to second group, number of groups, CV)
3. Apply rule-based classifier
4. Validate against hand-labeled sample of ~50 races
5. Upgrade to HDBSCAN if simple threshold produces too many false splits

---

## 3. Race Outcome Prediction

### Key Published Work

| Source | Approach | Key Finding |
|--------|----------|-------------|
| **PerfoRank** (Springer 2024) | Clusters races by elevation/surface, applies TrueSkill per cluster | Most rigorous; directly applicable to amateur racing with race-type specialization |
| **Mortirolo blog** | Practical Elo/TrueSkill for cycling | Solves large-field problem by decomposing 200-rider races into 100 sub-races of 30 randomly sampled riders |
| **Learn-to-Rank** (Frontiers 2021) | XGBoost/LambdaMART with features for quality, course matching, 6-week form | Best-performing ML approach for predicting top-10 finishers |
| **VeloRost** (Springer 2025) | Bayesian dual-skill TrueSkill | Models leader vs. helper skills separately, capturing team dynamics |

### How Existing Systems Work

- **road-results.com / CrossResults.com**: Simple points averaging (best 5 of last 10 races in 12 months). They are **leaderboards, not predictors**.
- **CrossResults** ranking: Weighted average of normalized finish positions. Documented at crossresults.com/faq.

### Key Gaps
- **No model predicts finish type** (sprint, breakaway, solo) from course + field composition
- **Almost no work targets amateur racing** specifically (fitness variance 2-5x higher, data sparser)
- **No system combines race-type classification with conditional rider ranking**

### Recommended Approach
1. **Glicko-2 or TrueSkill** ratings per race type (crit/road/TT/hillclimb) using `skelo` or `trueskill` Python libraries
2. **Pairwise decomposition** with random subsampling for large fields (Mortirolo method)
3. **LambdaMART Learn-to-Rank** for final predictions with features: overall rating, type-specific rating, 6-week form, same-race history, field strength
4. **Two-stage prediction**: First predict finish type from course + field, then rank riders conditionally
5. **Glicko-2's volatility parameter** naturally handles amateur fitness variance — erratic riders get wide confidence intervals

### Python Libraries
- `skelo` — Elo/Glicko implementations for sports
- `trueskill` — Microsoft's TrueSkill algorithm
- `xgboost` with LambdaMART objective for Learn-to-Rank

---

## 4. Rider Phenotype Matching

### Key Finding: Results-Based Classification Is Feasible

**ProCyclingStats is the strongest proof point**: They classify pro riders into six specialties (Sprint, Climber, Hills, GC, Time Trial, One Day) **purely from results** by:
1. Classifying each race's terrain profile
2. Awarding specialty points based on finish position in each race type

The transferable principle: **ratios/shape matter, not absolutes** — a rider who finishes 15th in sprints and 50th in mountains is still a "sprinter profile."

### Existing Classification Systems

| System | Categories | Data Source |
|--------|-----------|-------------|
| **ProCyclingStats** | Sprint, Climber, Hills, GC, TT, One Day | Race results + course profiles |
| **TrainerRoad** | Sprinter, Puncheur, Rouleur, TT, Climber, All-Rounder | Power data |
| **Xert** | Continuous "Focus Duration" spectrum | Power data |
| **WKO** | Power Duration Curve phenotype | Power data |

### Key Questions Answered

1. **Can you classify from results alone?** Yes. PCS proves it at pro level. Key challenge is classifying the *races themselves* by type first.

2. **Minimum results needed?** ~25 results for robust classification. Use tiered confidence:
   - Low confidence: 5-10 results
   - Moderate: 15-25
   - High: 25+

3. **Handling type evolution?** Use a **rolling window** (12-24 months) with recency weighting rather than career totals.

### Recommended Architecture

**Content-based recommendation system** where:
- Race terrain profiles are "items"
- Rider specialty vectors are "user preferences"
- Similarity scoring ranks race-rider fit

Steps:
1. Classify each race by course type (flat, rolling, hilly, mountainous)
2. For each rider, build a performance vector across race types
3. Normalize by field quality (Cat 5 vs Pro/1/2)
4. Compute rider specialty scores using the PCS-style points system
5. Recommend races where the rider's strengths match the expected finish type

### Key Gaps
- No existing open-source results-based rider classifier
- Amateur race course profile data is sparse
- Field quality normalization is unsolved (Cat 5 vs Pro/1/2 finishes)
- Criterium-specific classification is under-researched
- **No tool currently recommends races based on rider profile** — explicitly called out as unexplored in academic literature

---

## 5. Course Profile & Race Character

### Elevation Data Sources

| Source | Coverage | Access | Notes |
|--------|----------|--------|-------|
| **RideWithGPS** | Excellent PNW coverage | Web scraping | Many PNW race routes available; Portland-based company |
| **Strava Segments API** | Good | API (rate limited) | Explore endpoint + segment detail; 200 req/15min |
| **Open-Elevation** | Global | Free API | Uses SRTM data, 30m resolution |
| **OpenRouteService** | Global | Free API | Elevation along arbitrary routes |
| **Google Elevation API** | Global | Paid | $5/1000 requests |

### Course Classification Methods

| Method | Description |
|--------|-------------|
| **m/km thresholds** | Flat <5 m/km, Rolling 5-10, Hilly 10-15, Mountainous >15 |
| **Strava formula** | `elevation_gain / distance * 100` for gradient classification |
| **PJAMM index** | Weighted climb difficulty accounting for gradient variability |
| **KMeans clustering** | Cluster on (distance, vert_gain, avg_gradient, max_gradient) |
| **PCS ProfileScore** | `([Steepness]/2)^2 * [Length_km] * distance_factor` |

### Course-Finish Type Correlation (Strong Signal)

| Course Type | Expected Finish | Confidence |
|-------------|----------------|------------|
| Flat/crit circuit | Bunch sprint | High |
| Rolling with flat finish | Sprint or small group | Medium |
| Hilly with summit finish | Selective/individual | High |
| Rolling with uphill finish | Reduced group or breakaway | Medium |

### PNW-Specific Data Sources

| Source | Coverage | Data Available |
|--------|----------|---------------|
| **OBRA** (Oregon) | Oregon races | Results back to 2001; schedule at obra.org |
| **WSBA** (Washington) | WA races | Calendar; results via road-results.com |
| **road-results.com** | PNW + national | 3.9M+ results, 420K+ racers |
| **Zone4** | British Columbia | BC cycling results |
| **BikeReg** | National | Event registration + metadata |
| **RaceCenter** | National | Race calendar aggregator |

### Critical Gap

**No existing dataset links PNW race results to course elevation profiles.** This is a manual data curation task — you'll need to:
1. Map each race name to a specific course/route
2. Obtain elevation data for that route (via RideWithGPS, Strava, or GPS data)
3. Classify the course type
4. Build the course → finish type correlation model

This is the most labor-intensive part of the project but has the highest signal value.

---

## 6. UI/UX & Tech Stack

### Existing Cycling Analytics Projects

Several open-source projects exist (procyclingstats PyPI, CyclingStatsDataBase, Bike-Analytics, Cycling_API) but **none target PNW amateur racing**. No tool classifies finish types or predicts outcomes for regional amateur cycling — this is a completely unserved niche.

### PNW-Specific Data Sources for Scraping

- **OBRA** (`obra.org/results`) — structured HTML with rider name, team, category, placement, points. Organized by year and discipline (Criterium, Cyclocross, Gravel, MTB, Road, TT, Track) with 11+ category divisions per event.
- **WSBA** (`wsbaracing.org`) — Washington state results

### Recommended Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Language** | Python 3.11+ | Sole language; all ML/scraping libs are Python-native |
| **Scraping** | BeautifulSoup + requests | For OBRA/WSBA static HTML; road-results JSON API needs only `requests` |
| **Database** | SQLite via SQLAlchemy | Zero config for MVP, swappable to PostgreSQL later |
| **Data Processing** | Pandas | Standard for tabular data manipulation |
| **ML/Classification** | scikit-learn, XGBoost | RandomForest/XGBoost for finish-type classification and outcome prediction |
| **Rating System** | `skelo` or `trueskill` | Glicko-2/TrueSkill for rider ratings |
| **Dashboard** | Streamlit | Days to working product, pure Python, no JS needed |
| **Charts** | Plotly | Interactive charts within Streamlit |
| **Scheduling** | APScheduler | In-process scraping schedules |
| **Fuzzy Matching** | rapidfuzz | Rider identity resolution across data sources |

### UI/UX Patterns

**Confidence/Probability Display**: Use color-coded badges (green/yellow/red) with natural language qualifiers ("Likely sprint finish") at the surface. Progressive disclosure of actual probabilities and historical basis on hover/click. Never show raw decimals to non-technical users.

**Finish Type Trends**: Stacked area charts showing finish-type distribution over time (the "last 5 years" view).

**Prediction Leaderboards**: Sortable/filterable tables with expandable detail cards showing probability breakdowns.

**Course Patterns**: Heatmaps for course-vs-season patterns (e.g., which races trend toward sprints vs. breakaways by year).

### Database Schema (9 Core Tables)

Following patterns from the W3C Open Athletics Data Model:

1. `races` — race events with date, location, series
2. `series` — multi-race series (e.g., "Banana Belt" series)
3. `courses` — course profiles with elevation data
4. `riders` — deduplicated rider identities
5. `teams` — team affiliations
6. `categories` — race categories (P12, Masters 40+, etc.)
7. `results` — individual race results with times
8. `race_classifications` — finish type labels per race/category
9. `scrape_log` — tracking what's been scraped and when

### Key Technical Considerations

- **Rider identity resolution**: Riders appear with slightly different names across sources. Use `rapidfuzz` for fuzzy matching.
- **OBRA HTML fragility**: HTML structure may change; use defensive parsing and archive raw HTML.
- **No labeled training data**: Need manual labeling of 50-100 races for finish type classification, or derive from time-gap analysis.

---

## Summary: What to Build vs. What Exists

### Can Reuse / Adapt
- road-results.com JSON API (discovered endpoint)
- `physinet/road-results` scraper code
- UCI 3-second gap rule for group detection
- PCS ProfileScore formula for course classification
- PCS six-category rider taxonomy
- Glicko-2 / TrueSkill rating algorithms (`skelo`, `trueskill` libraries)
- LambdaMART learn-to-rank approach
- CV-of-finish-times metric for finish type discrimination

### Must Build From Scratch
- **Finish type classifier** (rule-based initially, no existing implementation)
- **Course profile database** for PNW races (manual curation + elevation APIs)
- **Results-based rider phenotype classifier** (novel, no open source exists)
- **Race recommendation engine** (explicitly called out as unexplored in literature)
- **Two-stage prediction model** (finish type → conditional rider ranking)
- **Race Predictor scraper** for road-results.com startlist data
- **Hand-labeled training dataset** (~100-200 races with finish type labels)

### Priority Implementation Order
1. **Data acquisition** — JSON API scraper for road-results.com
2. **Finish type classification** — Gap-based grouping + rule classifier
3. **Course profile database** — Manual curation + elevation APIs
4. **Race outcome prediction** — Glicko-2 ratings + LambdaMART
5. **Rider phenotype matching** — Results-based specialty vectors
6. **UI/visualization layer** — Dashboard with trends, predictions, recommendations
