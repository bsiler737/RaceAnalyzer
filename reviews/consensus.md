# Three-Model Consensus: Mid-Plan Improvements Review

*Synthesized from reviews by Claude Sonnet, Gemini 2.5 Flash, and OpenAI o3*
*Date: March 10, 2026*

---

## Unanimous Agreements (All 3 Models Agree)

### 1. UI is catastrophically under-prioritized

**Verdict: Promote UI from P3 to P1.**

All three reviewers independently flagged this as the single biggest mistake in the document. The reasoning is consistent:

- **Claude**: "All UI improvements are marked P3, but UI is how users access ALL other features. Bad UX kills adoption regardless of algorithmic sophistication."
- **Gemini**: "Without good UI, none of the P0 backend improvements matter to users."
- **o3**: "If users can't see the new elevation or prediction insights quickly, they won't know the backend got smarter."

**Consensus action**: Build a "Race Preview" page as the centerpiece UI element in the same sprint as the first backend prediction feature. This page combines finish-type history, course profile, top contenders, and a fit score. Design mobile-first.

---

### 2. LambdaMART is premature — ship Glicko-2 alone first

**Verdict: Demote Learn-to-Rank (4c) from P1 to P2. Ship Glicko-2 ratings as v1 prediction.**

All three models identified the same core issue: XGBoost LambdaMART requires data volumes the PNW scene can't provide, and simpler models deliver 80% of the value.

- **Claude**: "XGBoost LambdaMART is PhD-level complexity for what might be solved with simpler approaches."
- **Gemini**: "With ~300 PNW road races per year, the training data for learn-to-rank is thin. Overfitting is a serious risk."
- **o3**: "Learn-to-Rank requires thousands of training races; PNW season yields <300 road/crit races per year. Data sparsity will kill pairwise ranking models."

**Consensus action**: Phase 0 = Glicko-2 only (mu + sigma). Phase 1 = Bradley-Terry or Plackett-Luce for win/podium probabilities. Phase 2 = LambdaMART only after 1000+ labeled race-categories exist. Gate complexity on data volume.

---

### 3. Cluster-specific ratings (4b) will suffer from data sparsity

**Verdict: Keep as concept but gate on data volume. Fall back to global rating + terrain dummy.**

- **Claude**: Not explicitly called out but implied by recommending incremental approach.
- **Gemini**: "If you split ratings by 4 course types, each rider has 1/4 the data per cluster. Many Cat 3 riders race only 10-15 times per year."
- **o3**: "Sprinter-rating for a rider with two crits on file is noise."

**Consensus action**: Implement cluster-specific ratings only when >500 races exist per terrain type. Until then, use global Glicko-2 rating + terrain type as a categorical feature.

---

### 4. Course elevation: start with summary stats, not peak detection

**Verdict: Use RWGPS summary stats (total gain, m/km) before building scipy peak detector.**

All three agree the plan over-engineers the first version of elevation analysis.

- **Claude**: "Implement basic flat/rolling/hilly/mountainous classification first using m/km thresholds. Skip clustering initially."
- **Gemini**: "Starting with m/km thresholds is a pragmatic first step."
- **o3**: "Use RWGPS summary stats (total gain, max grade, vert-per-lap) before rolling your own peak detector. 80% of flat vs. hilly discrimination can be done today."

**Consensus action**: Phase 0 = m/km thresholds with 4 human-verified terrain bins. Phase 1 = scipy peak detection for climb features. Phase 2 = COP-KMeans clustering (if ever needed).

---

### 5. Race Predictor scraper needs alternative data sources

**Verdict: Try BikeReg API and OBRA startlists before scraping Road-Results Race Predictor.**

All three identified legal/ethical risk and fragility as concerns, and all independently recommended BikeReg as a primary alternative.

- **Claude**: "Contact OBRA, BikeReg, major race organizers about API access or data partnerships before scraping premium features."
- **Gemini**: "BikeReg has a REST API and shows 'Confirmed Riders' for many PNW races. This should be the primary startlist source."
- **o3**: "Add BikeReg CSV fallback; 80% of WA/OR races post startlists there and it's a stable URL pattern."

**Consensus action**: Primary = BikeReg API/CSV. Secondary = OBRA startlists for Oregon. Tertiary = Road-Results Race Predictor scraping (with conservative rate limits, raw HTML archival, and two-tier error handling). Always build graceful degradation for when no startlist is available.

---

### 6. Missing: graceful degradation for startlist data

**Verdict: Build "who to watch" using historical data first, regardless of startlist availability.**

- **Claude**: "Design the prediction UI to gracefully handle missing/stale startlist data. Show historical analysis even when current registrations aren't available."
- **Gemini**: "'Historical top performers at this race' is a perfectly good fallback."
- **o3**: Not explicitly stated but implied by phased approach.

**Consensus action**: The "top contenders" feature should work in three tiers: (1) with current startlist = best predictions, (2) without startlist = historical top performers at this race/series, (3) no history = top-rated riders in this category who live nearby.

---

### 7. Missing: mobile-first design

**Verdict: All UI should be designed mobile-first.**

- **Claude**: "PNW racers check race info on phones while driving to events."
- **Gemini**: "PNW racers check this on phones during Saturday morning coffee before deciding which race to drive to."
- **o3**: "Race-day phone checks are the primary consumption mode."

**Consensus action**: Use Streamlit responsive layouts with card-based components. Test on mobile viewports. Tables should be scrollable or replaced with card views on narrow screens.

---

## Strong Majority Agreements (2 of 3 Models Agree)

### 8. Weather/wind is a missing signal

**Claude** and **o3** both flagged weather as a significant missing factor. Gemini mentioned wind exposure under "beyond elevation" but didn't prioritize it.

- **Claude**: "Weather is often more decisive than elevation in the PNW."
- **o3**: "Wind on flat courses can mimic hill selectivity."

**Consensus action**: Add historical weather data as a future feature (P2). For now, note in the UI when a race has historically variable finish types — that variability likely correlates with weather.

---

### 9. Circuit/lap-aware elevation analysis

**Gemini** and **o3** independently flagged that multi-lap courses need special handling.

- **Gemini**: "For multi-lap courses, analyzing one lap's elevation misses cumulative fatigue."
- **o3**: "Need lap-aware elevation aggregation (crit course elevation is noise)."

**Consensus action**: When computing course features, multiply single-lap metrics by lap count for cumulative values. Flag criteriums separately since their elevation profiles have different strategic meaning.

---

### 10. Category upgrade/downgrade handling is missing

**Gemini** and **o3** flagged this; Claude mentioned it indirectly via "participation patterns."

- **Gemini**: "When a rider upgrades from Cat 4 to Cat 3, their rating needs recalibration."
- **o3**: "Missing a back-fill strategy for riders who upgrade or change licence numbers."

**Consensus action**: When a rider appears in a new category, initialize their category-specific rating from their previous category rating with inflated sigma (higher uncertainty). Track category transitions in the rider model.

---

### 11. Need a baseline heuristic before ML

**Claude** and **o3** explicitly called for a baseline; Gemini implied it with "carried_points as proxy."

- **Claude**: "Start with carried_points-based predictions (already available data)."
- **o3**: "Field-adjusted average finish position in last 12 months would let you A/B test against Glicko."

**Consensus action**: Before implementing Glicko-2, build a simple "historical average finish percentile" model using existing carried_points. Use this as the benchmark all future models must beat.

---

## Notable Unique Insights (1 Model Only, But Valuable)

| Insight | Source | Value |
|---------|--------|-------|
| **Fit-Score Matrix** replacing heatmap (rows = upcoming races, columns = rider strengths) | o3 | High — far more actionable than historical heatmap |
| **User feedback loop** as source of labeled training data (solving 2b for free) | Gemini | High — elegant dual-purpose feature |
| **"What-if" slider** for roster changes | o3 | Medium — cool but complex |
| **Shareable links** for team planning in group chats | o3 | Medium — low effort, high social value |
| **Monte-Carlo simulation** as interpretable alternative to LTR | o3 | High — simple, transparent, works with small data |
| **Participation prediction** (who shows up, not just who wins) | Claude | Medium — novel but hard to validate |
| **RWGPS API cost budgeting** (~$0.003/route) | o3 | Low — practical but small concern |
| **Course version table** keyed by distance +/-1km & gain +/-50m | o3 | Medium — solves route versioning cleanly |
| **Checksum-based delta scraping** for startlists | o3 | Medium — efficiency gain |

---

## Consensus Re-Prioritization

The original plan's priority ordering vs. the three-model consensus:

| Original | Item | Consensus | Rationale |
|----------|------|-----------|-----------|
| P0 | 4a. Rating system (Glicko-2) | **P0** | Unanimous: correct priority, but ship simpler v1 |
| P0 | 3a. Elevation profile analysis | **P0** | Unanimous: but start with m/km, not peak detection |
| P0 | 1b. Race Predictor scraper | **P0** | Unanimous: but BikeReg first, not Race Predictor |
| P3 | 7a-c. UI improvements | **P1** | **Unanimous upgrade**: UI is how users access everything |
| P1 | 4c. Learn-to-Rank (LambdaMART) | **P2** | Unanimous: data sparsity, premature complexity |
| P1 | 4d. Multi-timescale features | **P1** | Keep, but limit to 2 windows initially |
| P1 | 6a-b. Schema changes | **P0** | Keep: required foundation for P0 items |
| P2 | 4b. Cluster-specific ratings | **P2** | Keep, but gate on data volume |
| P2 | 3b. Course type classification | **P1** | Upgrade: simple m/km thresholds unlock predictions |
| — | Baseline heuristic model | **P0** | **New item**: benchmark before any ML |
| — | Graceful degradation for missing data | **P1** | **New item**: every feature needs a fallback |
| — | Mobile-first UI design | **P1** | **New item**: primary consumption mode |
| — | User feedback loop for labeling | **P1** | **New item**: solves 2b while engaging users |

---

## Recommended Sprint Sequence

### Sprint 2a: "Ship Something Racers Can Use" (2-3 weeks)
1. Schema changes (courses table, rating columns)
2. Basic elevation stats from RWGPS (m/km, total gain) → 4-bin terrain classification
3. Baseline heuristic predictions using carried_points
4. **Race Preview page** (mobile-first): finish-type history + terrain + top historical performers
5. BikeReg startlist integration (API/CSV)

### Sprint 2b: "Real Predictions" (3-4 weeks)
1. Glicko-2 ratings (chronological, per-category)
2. Rider ratings displayed on Race Preview page
3. Simple win/podium probabilities (Bradley-Terry or Monte-Carlo)
4. Graceful degradation tiers (startlist available → historical fallback → category fallback)
5. User feedback mechanism ("Was this prediction right?")

### Sprint 3: "Sophistication" (4+ weeks, data-gated)
1. scipy peak detection for climb features
2. Course-type conditional ratings (when data volume permits)
3. Multi-timescale features (form + status windows)
4. Plackett-Luce or LambdaMART (when 1000+ labeled races exist)
5. Fit-Score Matrix visualization
6. Rider phenotype classification

---

## The One-Sentence Summary

All three models agree: **the improvements doc correctly identifies what to build but over-engineers the first version and dramatically under-prioritizes the user-facing layer — ship simple predictions with good UI before building the research platform.**
