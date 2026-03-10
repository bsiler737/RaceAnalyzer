# Mid-Plan Improvements: RaceAnalyzer vs. Best Practices

*Generated: March 10, 2026*
*Revised with feedback from Claude Sonnet 4, Gemini 2.5 Flash, and OpenAI o3*

This document identifies where the current RaceAnalyzer implementation falls short of the best practices documented in `research-findings.md` and the exemplary patterns in `exemplary-code.md`. Priorities are informed by a three-model review consensus that emphasized: ship simple predictions with good UI before building the research platform.

---

## 1. Startlist & Registration Data

### 1a. No Startlist Data from Any Source
**Best practice** (research-findings, §1 "What Still Requires HTML Parsing"): Startlist data is needed for pre-race predictions and "who should we watch for" (seed.md goal).

**Current state**: No scraper for startlists. `queries.get_scary_racers()` uses historical carried_points as a proxy but cannot answer "who is registered for an upcoming race."

**Gap**: Cannot fulfill seed.md goals: "who should we watch for as the top 10 candidates to finish on the podium?"

**Fix — multi-source strategy with graceful degradation**:
1. **Primary: BikeReg API/CSV** — BikeReg has a REST API and "Confirmed Riders" CSV for most WA/OR races. Legitimate, stable, and avoids legal risk. Try this first.
2. **Secondary: OBRA startlists** — OBRA posts startlists for Oregon races. Zone4 covers BC.
3. **Tertiary: Road-Results Race Predictor** — HTML scraping as last resort with conservative rate limiting (2s base delay, exponential backoff on 429). Archive raw HTML for offline re-parse. Use the procyclingstats two-tier error pattern.
4. **Manual fallback**: Let users paste a startlist URL or enter rider names for races where automated scraping fails.

**Scraping considerations** (from reviewer feedback):
- Race Predictor is per-category; implement category-aware scraping by iterating `?cat=###` query params
- Startlists change daily in race week; implement incremental refresh (weekly until race week, then daily)
- Some riders opt out of public startlists; never assume a complete list
- Emit checksum hash per racer list per scrape; skip DB writes when unchanged
- Road-Results Race Predictor may be a premium feature — a takedown request could kill this overnight. BikeReg-first strategy mitigates this risk.

**Graceful degradation tiers** (always show something useful):
1. **With current startlist**: Full predictions with registered riders
2. **Without startlist**: "Top 5 riders who've raced this event before" — requires zero startlist scraping, delivers ~70% of the value
3. **No race history**: Top-rated riders in this category who live in the region

---

### 1b. No Upcoming Race Calendar
**Best practice** (seed.md): "What kind of a finish do you expect for upcoming races?"

**Current state**: Calendar page shows past race series tiles only. No integration with upcoming race schedules.

**Gap**: Cannot show future races or predictions for upcoming events. The tool is retrospective when users need it to be prospective.

**Fix**: Scrape BikeReg event data and OBRA/WSBA calendars for upcoming race dates. Display on calendar page with predicted finish type based on historical data for that race series. Include registration links.

---

## 2. Course Profile & Elevation Data

### 2a. No Elevation Profile Analysis
**Best practice** (PerfoRank exemplary code, Practice A): Extract climb features from elevation data. Research identifies this as "the most labor-intensive part of the project but has the highest signal value."

**Current state**: RWGPS integration fetches route polylines for map display but does not extract or analyze elevation data.

**Gap**: Cannot build course-to-finish-type correlation model. Cannot implement the two-stage prediction architecture (classify course first, then predict outcome).

**Fix — phased approach** (consensus: start simple, sophisticate later):

**Phase 0 (this sprint)**: Use RWGPS summary stats (total elevation gain, max grade, distance) to compute m/km ratio. Classify courses into 4 human-verified terrain bins:
- Flat: <5 m/km
- Rolling: 5-10 m/km
- Hilly: 10-15 m/km
- Mountainous: >15 m/km

This achieves 80% of flat-vs-hilly discrimination with minimal effort.

**Phase 1 (data-gated)**: Implement `scipy.signal.find_peaks` with UCI prominence thresholds (Cat 4: 80m, Cat 3: 160m, Cat 2: 320m, Cat 1: 640m, HC: 800m). Compute last-climb position as fraction of race distance. Note: PNW "stairstep rollers" may need adapted thresholds — prominence alone can misclassify them.

**Phase 2 (if needed)**: COP-KMeans constrained clustering with domain knowledge. Likely unnecessary if threshold-based classification works well.

**Route data acquisition challenges** (from reviewer feedback):
- Not all promoters use RWGPS; some use Strava, Garmin, or static image maps
- Routes change year-to-year; need a `course_version` table keyed by distance (+/-1 km) and gain (+/-50 m)
- RWGPS API is paid and throttled; budget ~$0.003/route, put an async cache in front
- 200-point polylines from public endpoints lose gradient detail; fetch full-resolution when available
- **Fallback strategy**: When no route data exists, use historical finish-type data as a proxy for course difficulty. Add Strava Segment API or USGS DEM as secondary elevation sources.
- Add a manual GPX upload mechanism for users or race organizers

---

### 2b. Course Type Classification
**Best practice** (research-findings, §5): m/km thresholds, PCS ProfileScore formula, KMeans clustering.

**Current state**: `race_type` field (criterium, road_race, etc.) exists but no terrain-based classification.

**Gap**: Cannot correlate course terrain with finish type.

**Fix**: Add `course_type` enum (flat, rolling, hilly, mountainous) using m/km thresholds from 2a Phase 0. Additional considerations:
- **Circuit/lap awareness**: Multiply single-lap elevation by lap count for cumulative fatigue metrics. Flag criteriums separately since their elevation profiles have different strategic meaning.
- **Surface type**: Extract road vs. gravel from race descriptions — significant for PNW races
- **Category-adaptive interpretation**: A "Cat 4" climb may split a Cat 5 field but not a Cat 2 field. Allow thresholds to be parameterized by category when sufficient data exists.

---

### 2c. No Weather Signal
**Best practice** (reviewer feedback — flagged by 2 of 3 models): "Weather is often more decisive than elevation in the PNW." Wind on flat courses can mimic hill selectivity. Chuckanut in February has completely different dynamics than in July.

**Current state**: No weather data of any kind.

**Gap**: Elevation alone underpredicts selective finishes in bad weather. Races with historically variable finish types likely correlate with weather variability.

**Fix** (P2 — future sprint): Integrate historical weather data (temperature, precipitation, wind speed) from a weather API for race dates and locations. For now, flag in the UI when a race has historically variable finish types — that variability is a useful signal even without knowing the cause.

---

## 3. Rating System & Prediction

### 3a. Baseline Heuristic Model (NEW)
**Best practice** (consensus — all 3 reviewers flagged this as missing): Before any ML, implement a simple benchmark that future models must beat.

**Current state**: No predictions of any kind. `carried_points` from road-results.com is stored but unused analytically.

**Gap**: Cannot validate whether complex models are worth their complexity without a baseline.

**Fix**: Implement "field-adjusted average finish percentile in last 12 months" using existing carried_points data. This requires zero new infrastructure, can be built today, and provides immediate value while validating the prediction UI and user workflow. Every subsequent model must demonstrably beat this baseline.

---

### 3b. No Rating System (Glicko-2)
**Best practice** (road-results exemplary code, Practice E; skelo exemplary code, Practices A-D; research-findings §3): Chronological Glicko-2 processing with temporal validity intervals.

**Current state**: No rating system. No `mu`/`sigma` columns on riders or results.

**Gap**: Cannot rank riders or predict race outcomes.

**Fix — phased approach**:

**Phase 0 (this sprint)**: Implement Glicko-2 via `skelo` library. Process races chronologically, per-category. Store prior/posterior ratings per result. Expose mu (expected placing) and sigma (confidence) directly in the UI. This alone is immediately useful — "instant value in two weeks" per reviewer consensus.

**Phase 1 (data-gated, >500 races per terrain type)**: Add course-type conditional ratings. A rider gets a separate rating for flat races vs. hilly races. If insufficient data, fall back to global rating + terrain type as a categorical feature.

**Key considerations** (from reviewer feedback):
- **Rating-dependent K factors**: New/upgrading riders should converge faster (high K), established riders should be stable (low K). Use `skelo`'s sigmoid K function.
- **Temporal validity intervals**: Use `strict_past_data=True` from skelo to prevent data leakage in predictions.
- **Category upgrade handling**: When a rider appears in a new category, initialize their rating from the previous category with inflated sigma (higher uncertainty). Track category transitions in the rider model.
- **Cross-category learning**: A Cat 4 rider's results tell you something about their Cat 3 performance. Don't treat categories as fully siloed.
- **Inactivity modeling**: Glicko-2's sigma naturally increases during inactivity, modeling fitness uncertainty. This is ideal for amateur racers with inconsistent schedules.

---

### 3c. Win/Podium Probability Model
**Best practice** (PerfoRank exemplary code, Practice C; research-findings §3).

**Current state**: No prediction model of any kind.

**Gap**: Cannot generate win probabilities, podium predictions, or ranked startlists.

**Fix — phased approach** (consensus: simple models first, gate complexity on data volume):

**Phase 0**: Use Glicko-2 mu/sigma directly. Monte-Carlo simulation (sample from each rider's rating distribution, simulate race N times, count podium finishes) is trivial, interpretable, and works with small data.

**Phase 1**: Bradley-Terry or Plackett-Luce logistic regression — designed for ranking from partial orders, handles small fields well, and gives real probabilities (unlike LambdaMART scores which require calibration).

**Phase 2 (>1000 labeled race-categories)**: XGBoost LambdaMART with `rank:pairwise` objective. Features: overall rating, type-specific rating, recent form, race-specific history, field strength. Use race-level train/test split to prevent data leakage.

**Calibration requirement** (from reviewer feedback): Publish a calibration notebook. If predicted win probability vs. actual win frequency diverges >5 percentage points in any decile, downgrade to qualitative tags ("Likely winner" / "Strong contender" / "Dark horse") instead of showing numbers. Uncalibrated probabilities erode user trust.

**Limitations to communicate to users**: Weather, crashes, mechanicals, and day-of-race tactics are inherently unpredictable. Always show model confidence alongside predictions. "High confidence (15+ riders with 10+ results)" vs. "Speculative (sparse data)."

---

### 3d. Multi-Timescale Feature Engineering
**Best practice** (Cycling-predictions exemplary code, Practice A): Form (weeks) vs. status (years) vs. race-specific history.

**Current state**: No feature engineering. `get_scary_racers()` uses all-time carried_points.

**Gap**: Cannot distinguish current form from long-term ability or race-specific expertise.

**Fix**: Build feature extraction with two initial windows (consensus: limit to avoid feature explosion):
- **Recent form**: Average finish percentile in last 8 weeks (`last_8w_avg_place`)
- **Rating trend**: Rating delta over last year (`1y_rating_delta`)
- **Race-specific history**: Results at this specific race/series

Expand to full multi-timescale grid (2w/4w/6w/8w form, 1y/3y/5y status) only when the prediction model demonstrates it needs more features.

---

### 3e. Cluster-Specific Ratings
**Best practice** (PerfoRank exemplary code, Practice D): TrueSkill ratings per race cluster.

**Current state**: No ratings or clustering.

**Gap**: A single global rating can't capture that a rider is strong in sprints but weak in climbing races.

**Fix**: Implement only when >500 races exist per terrain type. With ~300 PNW races/year and Cat 3 riders racing 10-15x/year, splitting across 4 clusters yields 2-4 results per cluster per rider — not enough for stable ratings. Until then, use global Glicko-2 + terrain type as a dummy feature.

---

### 3f. Team Strength Features
**Best practice** (Cycling-predictions exemplary code, Practice B): Team-level aggregation identifies the protected rider.

**Current state**: Team name stored but unused analytically.

**Gap**: In Cat 1/2 racing, team tactics significantly influence outcomes.

**Fix**: Lower priority. Implement team-level aggregation (sum of teammate ratings, within-team z-score) for Cat 1/2 fields only. Negligible impact for Cat 3-5 where team tactics are minimal.

---

## 4. UI & Visualization

### 4a. Race Preview Page (NEW — highest-value UI element)
**Best practice** (consensus — all 3 reviewers independently identified this as the single most important missing feature): A one-stop "everything you need to know about this race" page.

**Current state**: Race Detail page shows historical classification and results. No forward-looking predictions, no contender analysis, no fit scoring.

**Gap**: The tool is retrospective when users need it to be prospective. No single page answers "should I race this event?"

**Fix**: Build a "Race Preview" page as the UI centerpiece, combining:
- **Finish type prediction**: Based on historical data for this race series + course terrain
- **Course profile**: Terrain type, elevation summary, course map
- **Top contenders**: From startlist (if available) or historical performers (fallback)
- **Fit score**: How well does this race suit the user's phenotype/strengths
- **Confidence indicators**: How much data backs each prediction

This page must ship in the same sprint as the first backend prediction feature. Backend improvements that users can't see don't drive adoption.

---

### 4b. Mobile-First Design (NEW)
**Best practice** (consensus — all 3 reviewers flagged this): "Race-day phone checks are the primary consumption mode."

**Current state**: No mobile considerations in any UI component.

**Gap**: PNW racers check race info on phones Saturday morning before deciding which race to drive to. Desktop-only design misses the primary use case.

**Fix**: Design all new UI components mobile-first using Streamlit responsive layouts with card-based components. Replace wide tables with scrollable or card-based views on narrow screens. Test all pages on mobile viewports.

---

### 4c. Prediction Confidence Display
**Best practice** (research-findings, §6): "Color-coded badges with natural language qualifiers. Progressive disclosure of probabilities on hover/click. Never show raw decimals to non-technical users."

**Current state**: Confidence badges exist for finish-type classification but no prediction confidence display.

**Fix**: Extend existing badge pattern to predictions. Show qualitative labels:
- "Likely winner" / "Strong podium contender" / "Dark horse"
- "High confidence" / "Moderate confidence" / "Speculative"
- Reveal actual numbers on click for users who want them

---

### 4d. Fit-Score Matrix (replaces historical heatmap)
**Best practice** (o3 review): Replace backward-looking course-vs-season heatmap with forward-looking Fit-Score Matrix.

**Original plan**: Heatmap with races on one axis, years on the other, colored by finish type.

**Reviewer critique**: "Racers care about 'this year + me', not 2008 patterns."

**Revised fix**: Build a Fit-Score Matrix: rows = upcoming races, columns = rider strength dimensions (sprint, hills, breakaway). Color shows suitability. Far more actionable than a historical heatmap. Keep the historical trend chart on the series detail page for context, but make the forward-looking matrix the primary dashboard view.

---

### 4e. User Feedback Loop (NEW — solves labeling problem for free)
**Best practice** (Gemini review): "After each race, prompt users to confirm/deny the predicted finish type. This generates labeled training data while engaging users."

**Current state**: No mechanism for user feedback. Hand-labeled training dataset identified as P1 gap (original item 2b) with no implementation path.

**Gap**: Cannot measure classifier accuracy without ground truth. Building a labeling workflow is work that users could do for us.

**Fix**: After each race weekend, show users a prompt: "We predicted [finish type] for [race]. Was that right?" Options: Confirm / Wrong (select correct type) / Skip. Store responses in a `user_labels` table. This generates the labeled training dataset (solving the original item 2b) while engaging users and improving trust.

---

### 4f. User Personalization
**Best practice** (Gemini review): "A Cat 3 sprinter, a Masters 50+ climber, and a team director have completely different information needs."

**Current state**: No concept of a user profile or personalized views.

**Fix**: Add lightweight user preferences (even cookie-based, no login required):
- Category (Cat 3, Masters 40+, Women 1/2, etc.)
- Home location (for distance filtering)
- Self-identified phenotype (sprinter, climber, rouleur, all-rounder)

All views filter through these preferences. Enable "show races within N hours drive of me in the next 8 weeks."

---

### 4g. Shareable Race Analysis
**Best practice** (o3 review): "Teams plan in group chats."

**Current state**: No way to share a race analysis with teammates.

**Fix**: Generate shareable links for Race Preview pages. Low effort (URL parameters), high social value for team planning.

---

## 5. Finish Type Classification

### 5a. No HDBSCAN / DBSCAN Grouping Option
**Best practice** (research-findings, §2): HDBSCAN as robust fallback for variable-density finish spreads.

**Current state**: Only consecutive-gap threshold grouping.

**Fix**: Add HDBSCAN as an alternative. Use consecutive-gap as default, HDBSCAN for validation or ambiguous cases. Lower priority since current grouping works for most clean data.

---

### 5b. CV-of-Times Used Only for Confidence, Not Classification
**Best practice** (research-findings, §2): CV is one of the best single predictors of race selectivity.

**Current state**: CV computed and stored but only used for confidence badging, not classification.

**Fix**: Incorporate CV thresholds into the classification decision tree to disambiguate borderline cases (REDUCED_SPRINT vs. GC_SELECTIVE).

---

## 6. Scraping & Data Acquisition

### 6a. No Async Parallel Fetching
**Best practice** (road-results exemplary code, Practice C): `FuturesSession(max_workers=8)` for concurrent HTTP requests.

**Current state**: Sequential processing with 3-second delay. `requests-futures` in dependencies but unused.

**Fix**: Implement two-phase async fetching. Guard SQLite writes with a lock or batch-insert queue. Use the road-results reference project pattern.

---

### 6b. No OBRA/WSBA Supplementary Scraping
**Best practice** (research-findings, §5 & §6): OBRA has 25 years of data; Zone4 covers BC.

**Current state**: Only road-results.com scraped.

**Fix**: Add parsers for OBRA HTML and Zone4 using the procyclingstats class-per-entity pattern.

---

### 6c. No Fuzzy Rider Identity Resolution
**Best practice** (research-findings, §6): Use `rapidfuzz` for fuzzy name matching.

**Current state**: Exact match on `road_results_id` only.

**Fix**: Add `rapidfuzz` dependency. Implement fuzzy matching as fallback. Use license number as additional join key.

---

### 6d. Missing Class-Per-Entity Scraper Architecture
**Best practice** (procyclingstats exemplary code, Practice A): Entity classes with auto-discovery parsing.

**Current state**: Standalone functions with manual dispatch.

**Fix**: Refactor into entity classes with `parse()` introspection and field selection via `*args`. Lower priority — current architecture works, refactor when adding new data sources.

---

## 7. Rider Phenotype & Recommendations

### 7a. No Results-Based Phenotype Classifier
**Best practice** (research-findings, §4): PCS-style classification from results. "Ratios/shape matter, not absolutes."

**Current state**: No phenotype classification.

**Gap**: Cannot answer "If I'm a sprinter, which PNW races are good for me?"

**Fix**: Build performance vectors across race/finish types. Compute PCS-style specialty scores. Confidence tiers: 5-10 results = low, 15-25 = moderate, 25+ = high. Depends on course type classification (2b) being in place.

---

### 7b. No Race Recommendation Engine
**Best practice** (research-findings, §4): Content-based recommendation. "Explicitly called out as unexplored in academic literature."

**Current state**: No recommendations or rider-race matching.

**Fix**: Similarity scoring between rider specialty vectors and course profiles. Rank upcoming races by expected fit. Depends on phenotype classifier (7a) and course profiles (2a).

---

## 8. Database & Schema

### 8a. Missing Tables
**Best practice** (research-findings, §6): 9-table schema including courses, teams, categories.

**Current state**: 6 tables. No dedicated courses, teams, or structured categories table.

**Fix**:
- `courses` table: elevation features (total gain, m/km, climb counts, last climb position, course_type), distance, version tracking (keyed by distance +/-1km & gain +/-50m)
- `teams` table: team identity resolution across races
- `categories` table: mapping raw strings to normalized categories (P12 = "Pro/1/2")
- `startlists` table: registered riders per upcoming race/category with source and scrape timestamp
- `user_labels` table: user-submitted finish type labels for training data

---

### 8b. No Rating Columns on Results/Riders
**Best practice** (road-results exemplary code, Practice D): Rating snapshots per result.

**Current state**: No rating columns.

**Fix**: Add to Rider model: `mu`, `sigma`, `num_races`. Add to Result model: `prior_mu`, `prior_sigma`, `mu`, `sigma`, `predicted_place`. Enables both current ratings and historical snapshots.

---

## 9. Infrastructure & Quality

### 9a. No PostgreSQL Path for Scale
**Current state**: SQLite-only with hardcoded path.

**Fix**: Low priority. Avoid SQLite-specific patterns. When parallel scraping is needed, this becomes the blocker.

---

### 9b. No Data Quality Monitoring
**Current state**: Error hierarchy exists but no quality monitoring.

**Fix**: Add `data-quality` CLI command reporting: scrape success rate, classification distribution, unclassified race count, and comparison against previous runs.

---

## Priority Summary

| Priority | Improvement | Impact | Effort |
|----------|------------|--------|--------|
| **P0** | 8a-b. Schema changes (courses, ratings, startlists, user_labels) | Foundation for everything below | Small |
| **P0** | 3a. Baseline heuristic model (carried_points) | Immediate predictions, validates UI | Small |
| **P0** | 2a. Basic elevation stats (m/km, Phase 0) | Unlocks course classification | Medium |
| **P0** | 2b. Course type classification (4-bin thresholds) | Feeds predictions and recommendations | Small |
| **P0** | 1a. Startlist data (BikeReg API first) | Required for forward-looking features | Medium |
| **P0** | 4a. Race Preview page (mobile-first) | Users must see predictions to care | Medium |
| **P1** | 3b. Glicko-2 rating system (Phase 0) | Real ratings, instant value | Large |
| **P1** | 3c. Win/podium probabilities (Monte-Carlo) | Core seed.md deliverable | Medium |
| **P1** | 4b. Mobile-first design | Primary consumption mode | Medium |
| **P1** | 4c. Prediction confidence display | Trust and transparency | Small |
| **P1** | 4e. User feedback loop | Free labeled data + engagement | Small |
| **P1** | 4f. User personalization (category, location, phenotype) | Enables filtering and fit scores | Medium |
| **P1** | 3d. Multi-timescale features (2 windows initially) | Prediction accuracy gain | Medium |
| **P1** | 1b. Upcoming race calendar | Connects analysis to action | Medium |
| **P1** | 5a. CV as classification input | Better classification accuracy | Small |
| **P2** | 3c. Win/podium probabilities (Bradley-Terry/Plackett-Luce) | Better probabilities than Monte-Carlo | Medium |
| **P2** | 3e. Cluster-specific ratings (data-gated, >500/terrain) | Type-specific prediction accuracy | Medium |
| **P2** | 2a. Elevation analysis Phase 1 (scipy peak detection) | Climb features, last-climb position | Medium |
| **P2** | 4d. Fit-Score Matrix visualization | Actionable race selection view | Medium |
| **P2** | 7a. Rider phenotype classifier | Core seed.md goal | Medium |
| **P2** | 7b. Race recommendation engine | Novel seed.md goal | Medium |
| **P2** | 6a. Async parallel fetching | 10x scrape speed | Medium |
| **P2** | 5a. HDBSCAN grouping option | Robustness for edge cases | Small |
| **P2** | 6c. Fuzzy rider matching | Cross-source identity | Small |
| **P2** | 2c. Historical weather signal | Explain finish-type variability | Medium |
| **P3** | 3c. Win/podium probabilities (LambdaMART, >1000 races) | State-of-art ranking | Large |
| **P3** | 3f. Team strength features | Marginal gain, upper categories only | Small |
| **P3** | 6b. OBRA/WSBA/Zone4 scraping | Historical depth | Large |
| **P3** | 6d. Class-per-entity refactor | Extensibility | Medium |
| **P3** | 4g. Shareable race analysis links | Team planning | Small |
| **P3** | 9a. PostgreSQL readiness | Scale preparation | Medium |
| **P3** | 9b. Data quality monitoring | Operational reliability | Small |

---

## Recommended Sprint Sequence

### Sprint 2a: "Ship Something Racers Can Use" (2-3 weeks)
**Goal**: A Cat 3 racer in Seattle can open the app on their phone, see upcoming races with predicted finish types and top contenders, and decide which race to target this weekend.

1. Schema changes: courses table, rating columns, startlists table, user_labels table
2. Basic elevation stats from RWGPS (m/km, total gain) → 4-bin terrain classification
3. Baseline heuristic predictions using carried_points (benchmark for all future models)
4. BikeReg startlist integration (API/CSV) with graceful degradation tiers
5. **Race Preview page** (mobile-first): predicted finish type + terrain + top contenders
6. Upcoming race calendar with BikeReg/OBRA schedule data

### Sprint 2b: "Real Predictions" (3-4 weeks)
**Goal**: Rider ratings power actual win/podium probability estimates. Users provide feedback that builds our training dataset.

1. Glicko-2 ratings (chronological, per-category, with upgrade handling)
2. Rider ratings displayed on Race Preview page with confidence badges
3. Monte-Carlo win/podium probabilities from Glicko-2 distributions
4. Multi-timescale features: 8-week form + 1-year trend + race-specific history
5. User feedback mechanism ("Was this prediction right?")
6. User personalization: category, location, phenotype preferences

### Sprint 3: "Sophistication" (4+ weeks, data-gated)
**Goal**: When data volume permits, upgrade to more powerful models. Build phenotype classification and race recommendations.

1. Bradley-Terry or Plackett-Luce probability model (replaces Monte-Carlo)
2. scipy peak detection for climb features (Phase 1 elevation)
3. Course-type conditional ratings (when >500 races per terrain exist)
4. Rider phenotype classifier (PCS-style specialty vectors)
5. Race recommendation engine (phenotype × course fit scoring)
6. Fit-Score Matrix visualization
7. LambdaMART (only when >1000 labeled race-categories exist)

---

## Design Principles (from three-model consensus)

1. **Ship value incrementally**: Every sprint must deliver something a racer can use this weekend. Don't build backend infrastructure without a corresponding UI surface.
2. **Gate complexity on data volume**: Don't deploy cluster-specific ratings with 3 data points per cluster. Set explicit thresholds (>500 races/terrain for cluster ratings, >1000 for LambdaMART).
3. **Graceful degradation everywhere**: Every feature must work with missing data. Startlist unavailable? Show historical performers. No elevation data? Use finish-type history. Sparse ratings? Show confidence intervals.
4. **Mobile-first, always**: The primary user is checking their phone Saturday morning. Design for that.
5. **Calibrate before displaying**: Never show raw model scores as probabilities. If predictions aren't calibrated, show qualitative labels instead.
6. **Users generate training data**: The feedback loop replaces manual labeling. Every "was this right?" response is a free labeled example.
