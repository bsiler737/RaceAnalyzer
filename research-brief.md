# Research Brief: PNW Bike Race Analysis Tool

## Project Goal

Build an analysis tool that classifies road bike race finishes in the Pacific Northwest (WA, OR, ID, BC) by type (sprint, breakaway, individual/GC-style), predicts future race outcomes, and recommends races to riders based on their cycling phenotype. Primary data source: https://www.road-results.com/

---

## Research Areas

### 1. Data Acquisition: Scraping & Parsing Race Results

**What to find:**
- Public GitHub repos that scrape or parse cycling race results from road-results.com or similar sites (USACycling, BikeReg, CrossResults, FirstCyclingResults)
- Best practices for structured extraction of race result data: finish times, time gaps, field size, categories, rider names, race names, dates, locations
- How road-results.com structures its data (URL patterns, HTML structure, any APIs or feeds). Look for any existing scrapers or parsers for this specific site
- Approaches to handling the "race predictor" feature on road-results.com (pre-race registration/startlist data)

**Search terms:**
- `road-results.com scraper` / `road-results.com API`
- `cycling results scraper github`
- `usac race results parser`
- `crossresults scraper`
- `firstcycling scraper python`
- `bikereg results parser`
- `procyclingstats scraper github` (pro-level equivalent, likely has mature tooling)

**Why it matters:** Everything downstream depends on clean, structured results data. We need finish times and gap data specifically, not just placement order.

---

### 2. Finish Type Classification: Sprint vs. Breakaway vs. Individual

**What to find:**
- Academic papers or blog posts on classifying cycling race finishes by type using time gap analysis
- Statistical methods for detecting clusters in finish time data (to distinguish "the bunch finished together" from "a breakaway had a gap" from "riders were spread out")
- Existing implementations of gap-based clustering for race results (any sport with time-based finishes: running, cycling, triathlon, XC skiing)
- Thresholds or heuristics used by cycling analysts to define "same group" vs "gap" (e.g., ProCyclingStats bunch sprint detection)
- How sites like ProCyclingStats, FirstCycling, or CyclingAnalytics classify finish types at the pro level

**Search terms:**
- `cycling finish type classification algorithm`
- `bunch sprint detection cycling results`
- `time gap clustering race results`
- `DBSCAN time series clustering finish times`
- `cycling race analysis github`
- `procyclingstats finish type` / `how procyclingstats classifies sprints`
- `breakaway detection cycling data`
- `race result gap analysis`

**Key technical questions:**
- What time gap threshold separates "same group" from "breakaway"? Is it absolute (e.g., 3 seconds) or relative to field size and race distance?
- How do you handle missing time data (results that only show placement, not time gaps)?
- How do you account for different category sizes (a 15-person field vs. 80-person field)?

**Why it matters:** This is the core analytical engine. The classification must be credible to experienced racers who already have intuitions about these races.

---

### 3. Race Outcome Prediction

**What to find:**
- Models or approaches for predicting cycling race outcomes based on historical results
- GitHub repos implementing Elo ratings, Glicko ratings, or similar ranking systems for cycling
- How road-results.com's own "race predictor" works (methodology, if documented)
- Bayesian approaches to predicting race outcomes given historical finish-type distributions
- Sports prediction models that handle the specific challenge of cycling (team dynamics, course profiles, weather)

**Search terms:**
- `cycling race prediction model github`
- `elo rating cycling`
- `glicko rating bicycle racing`
- `bayesian sports prediction cycling`
- `road-results race predictor methodology`
- `cycling power ranking algorithm`
- `amateur cycling prediction model`

**Key technical questions:**
- How do you build a prediction model for amateur racing where rider fitness varies significantly season to season?
- What features matter most: past results at the same race, overall season form, category-specific performance?
- How do you combine finish-type prediction (what kind of race will this be?) with rider-outcome prediction (who will win given this kind of race)?

---

### 4. Rider Phenotype Matching

**What to find:**
- How cycling analytics platforms (Strava, TrainingPeaks, WKO, intervals.icu) classify rider types (sprinter, rouleur, climber, time trialist, puncheur, etc.)
- Methods for inferring rider type from race results alone (without power data), e.g., "this rider consistently does well in sprint finishes"
- Research on cycling phenotype classification
- Any tools that recommend races or routes based on rider profile

**Search terms:**
- `cycling rider type classification`
- `cyclist phenotype sprinter climber rouleur`
- `rider profiling from race results`
- `cycling race recommendation engine`
- `WKO rider type power profile`
- `cycling analytics rider classification github`

**Key technical questions:**
- Can you reliably classify a rider's type from results data alone (no power/HR data)?
- What's the minimum number of race results needed to classify a rider?
- How do you handle riders who are "developing" or change type over time?

---

### 5. Course Profile & Race Character

**What to find:**
- Public datasets or APIs for course elevation profiles in WA, OR, ID, BC
- Methods for classifying race courses by difficulty/type (flat, rolling, hilly, mountainous)
- How course profile correlates with finish type (strong signal expected)
- Existing PNW race calendars or databases with course metadata

**Search terms:**
- `cycling course profile classification`
- `race course elevation analysis`
- `strava segment elevation API`
- `pacific northwest cycling race calendar data`
- `OBRA race results` / `WSBA race results` / `MBRA race results`
- `cycling race course difficulty score`

---

### 6. UI/UX Patterns for Race Analysis Tools

**What to find:**
- Existing cycling analysis dashboards or tools (open source preferred) for UI inspiration
- Effective visualizations for finish-type trends over time (the "last 5 years" trend element mentioned in the seed doc)
- How to display probability/confidence information to non-technical users
- Race prediction leaderboard UI patterns

**Search terms:**
- `cycling analytics dashboard github`
- `race analysis visualization`
- `sports prediction UI open source`
- `probability display design patterns`

---

### 7. Tech Stack & Architecture Patterns

**What to find:**
- Similar sports analytics projects on GitHub to understand common tech stacks
- Best practices for building a data pipeline: scrape -> clean -> classify -> predict -> display
- Lightweight web app frameworks suitable for this kind of analytical tool
- Approaches to keeping results data updated (scheduling, incremental scraping)

**Search terms:**
- `sports analytics web app github`
- `cycling data pipeline`
- `race results database schema`
- `sports prediction app architecture`

---

## Priority Order

1. **Data acquisition** (nothing works without data)
2. **Finish type classification** (core value proposition)
3. **Course profile correlation** (strengthens classification accuracy)
4. **Race outcome prediction** (the "who to watch" feature)
5. **Rider phenotype matching** (the personalization layer)
6. **UI/UX patterns** (presentation)
7. **Tech stack decisions** (informed by findings above)

## Specific Repos to Investigate

If found, do deep dives on any repos that:
- Scrape road-results.com, CrossResults, or USAC results
- Implement time-gap clustering on race finish data
- Build Elo/Glicko systems for amateur cycling
- Classify cycling race finish types algorithmically
- Provide PNW-specific cycling race data or calendars

## Output Expected

For each area, return:
- **What exists**: specific repos, papers, blog posts, tools with URLs
- **What approach they use**: algorithms, data structures, tech stacks
- **What's reusable**: code we can adapt, APIs we can call, datasets we can use
- **What gaps remain**: things we'll need to build from scratch
- **Recommended approach**: given everything found, what's the best path for our tool
