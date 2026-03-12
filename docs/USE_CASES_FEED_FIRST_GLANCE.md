# Use Cases: Feed First Glance & Decision Dive

> **Persona:** Beginner PNW road racer (Cat 4/5, 1-3 seasons). See [BEGINNER_RACER_PERSONA.md](BEGINNER_RACER_PERSONA.md).
>
> **Design principle:** The feed card's first glance must answer the racer's decision factors *in priority order* — without expanding, without clicking, without navigating. The card earns a click by answering "should I care?" in under 3 seconds.
>
> **Priority order** (from persona study):
> 1. Date & logistics — when and how far?
> 2. Social — are my people going?
> 3. Course character — flat, hilly, how long?
> 4. Finish pattern — sprint, breakaway, selection?
> 5. Field size & strength
> 6. Drop rate
> 7. Race type familiarity
> 8. Registration friction

---

## Current State (Sprint 010)

The feed card currently shows: predicted finish type (plain English + label), terrain badge, drop rate %, narrative snippet, racer type description, elevation sparkline, duration, climb highlight, registration link, and historical editions popover.

**What's missing from the first glance:**
- **Location/distance** — location is buried in caption metadata below the card content
- **Teammate/social info** — not surfaced at all (data exists in startlists)
- **Field size** — not on the card
- **Course distance** — not on the card (data exists)
- The card buries some high-priority info (location, date) below lower-priority info (narrative, racer type description)

---

## Part 1: First-Glance Use Cases (No Click Required)

These use cases define what the racer should absorb from the feed card *before expanding or tapping anything*. The card title + first visual row must cover decision factors 1-4.

### FG-01: Date and location visible in the card header

**The racer** sees the race date AND location directly in the expander title or immediately below it — not buried after the narrative. For upcoming races: "Banana Belt Road Race — Mar 22, 2026 — Drain, OR". For historical: "Last raced Mar 2025 — Drain, OR".

**Why:** Date and logistics are the #1 decision factor. If it's next Saturday and 30 minutes away, they're interested. If it's 4 hours away on a work day, they scroll past. This must be the first thing they read.

**Gap:** Currently the expander label has the date but location is in a `st.caption` below all card content.

---

### FG-02: Teammates registered badge

**The racer** who has set their team name (one-time setting, sidebar or config) sees a badge on cards where teammates are registered: "2 teammates registered" or the specific names. If no teammates are registered, no badge — no noise.

**Why:** Social proof is decision factor #2. "My buddy Jake is doing this one" is often the tipping point. We have startlist data with team names — this is a join away from being surfaced.

**Data available:** `startlists.team` contains team names for registered riders. The user sets their team once; the app filters startlists for matches.

---

### FG-03: Course character one-liner on the first visual row

**The racer** sees a compact course summary on the top row of the card: terrain badge + distance + total climbing in a single line. Example: "Rolling — 62 km — 800m gain" or "Flat — 40 km — 120m gain".

**Why:** Course character is decision factor #3. The terrain badge already exists, but distance and climbing are not on the card. A racer who hates hills needs to see "Hilly — 1200m gain" at a glance, not after expanding.

**Gap:** `distance_m` and `total_gain_m` are available in feed item data but not rendered on the card.

---

### FG-04: Finish pattern prediction on the first visual row

**The racer** sees the plain-English finish type prediction ("The group usually stays together and sprints for the finish") as the headline of the card content — before the narrative, before the sparkline, before everything else.

**Why:** How the race will play out is factor #4 and the thing most correlated with "can I survive this?" A beginner who reads "bunch sprint" thinks "I can hide in the pack." A beginner who reads "the field splits apart on the climbs" thinks "I might get dropped."

**Status:** Already implemented. Confirm it stays the lead content as other elements are added.

---

### FG-05: Field size on the card

**The racer** sees typical field size directly on the card: "Usually 35-40 starters" (from historical data) or "28 registered" (from current startlist, if available).

**Why:** Factor #5. A race with 60 starters in Cat 5 feels like a real race. A race with 8 starters feels like a time trial with witnesses. Field size shapes expectations and comfort level.

**Data available:** Historical results have rider counts per category. Startlists have current registration counts.

---

### FG-06: Drop rate stays prominent

**The racer** sees the drop rate in the first visual row alongside terrain and finish type, not tucked into a corner. The label (low/moderate/high) matters more than the exact percentage for a quick scan.

**Why:** Factor #6. "12% drop rate (low)" = "I'll probably finish." "45% drop rate (high)" = "I might get shelled." The label does more work than the number for a first-glance read.

**Status:** Already implemented as percentage. Consider promoting the label (low/moderate/high) to be more prominent than the number.

---

### FG-07: Race type icon or label for familiarity

**The racer** sees whether this is a road race, criterium, time trial, or circuit race directly on the card. A racer who has done 3 crits but never a road race makes different decisions for each.

**Why:** Factor #7. Race type is a top-level categorization that shapes every expectation. "Oh, this is a crit — I know what that is" vs. "This is a road race — I've never done one of those."

**Gap:** Race type (crit vs road race vs TT) may not be explicitly stored or surfaced. May need to derive from series metadata or course characteristics.

---

## Part 2: Card Layout Reorder

### FG-08: Reorder card content to match decision priority

**The racer** sees card content in this order, matching their decision priority:

**Header row (in expander label or first line):**
- Race name, date, location

**Row 1 — Quick-scan badges (the "should I care?" row):**
- Teammates registered (if any)
- Course: terrain badge + distance + gain
- Field size
- Drop rate label

**Row 2 — How it plays out:**
- Finish type prediction (plain English)
- Elevation sparkline

**Row 3 — Deeper context (still no click):**
- Narrative snippet (1-2 sentences)
- Duration estimate
- Climb highlight

**Row 4 — Action:**
- Register button (if upcoming)
- View Preview / View Series buttons

**Row 5 — Historical context (popover):**
- Previous editions

**Why:** The current layout leads with finish type and terrain (factors 3-4) and puts location after everything (factor 1). Reordering to match the decision priority means the racer's eyes hit the highest-value info first.

---

## Part 3: Detail Dive Use Cases (One Click Deep)

These use cases define what the racer sees when they want to go deeper — clicking "Race Preview" from the card.

### DD-01: Interactive course profile with hill segment callouts

**The racer** clicks into the race preview and sees the full interactive course elevation graph — the one that shows the route with color-coded climb segments, gradient bands, and clickable climb markers. This is the "hero visualization" of the detail view.

**Why:** The sparkline on the card tells them "hilly or not." The full profile tells them *where* it gets hard, *how* hard, and *how long*. A beginner preparing for race day will study this to mentally rehearse the course. "OK, there's a big climb at km 18 and then it's flat to the finish — if I survive the climb I can recover."

**Status:** Already built (Sprint 008). Ensure it's the visual centerpiece of the preview page.

---

### DD-02: Climb-by-climb breakdown with race context

**The racer** sees each detected climb listed with: start km, length, average gradient, max gradient, and a one-liner about what typically happens there. Example: "Climb 1: km 18-20, 2.1 km at 6.2% avg — this is where the field usually splits."

**Why:** The persona study says beginners can't translate "800m elevation gain" into race dynamics. They need someone to say "here's where it hurts and here's what happens." We have the climb detection data; we just need to connect it to race outcomes in plain language.

**Data available:** Climb detection from elevation.py produces start/end km, gradient stats. Finish type history tells us whether the race typically splits (selective) or stays together (sprint).

---

### DD-03: Startlist with team groupings

**The racer** sees the registered riders grouped by team, with their team's riders highlighted. They can see: "Team Rapha has 5 riders — they'll likely control the pace. Your team has 2 riders registered."

**Why:** Persona factor #2 (social) and factor #5 (field strength). Team dynamics are the #1 thing beginners don't understand but that profoundly affect race outcomes. Showing team blocks makes the social landscape legible.

**Data available:** Startlist data includes team names. We already have contender predictions.

---

### DD-04: "What kind of racer does well here?" expanded

**The racer** sees the racer type description (already on the card as a one-liner) expanded into a full paragraph with course-specific reasoning: "This race favors sprinters and pack riders because the course is mostly flat with no significant climbs to break up the field. In 4 of the last 5 editions, the race ended in a bunch sprint. Riders who can stay in the draft and position well for the final kilometer tend to do best."

**Why:** The card-level one-liner earns the click. The expanded version builds confidence by explaining *why* — connecting course features to race dynamics to racer types. This is the anxiety reducer.

**Status:** Racer type description exists as a one-liner. The narrative exists as 1-2 sentences. This use case is about combining and expanding them in the preview context.

---

### DD-05: Historical finish type pattern visualization

**The racer** sees a compact visual showing how this race has ended across all historical editions — not just a list of years, but a pattern that makes prediction legible. Example: a row of finish-type icons per year, making it obvious that "this race is almost always a bunch sprint" or "this race is unpredictable."

**Why:** Patterns build trust. If the racer can see that the prediction ("bunch sprint") matches 4 of 5 historical editions, they believe it. If it's been different every year, they know to expect anything. The current editions popover is text-only and requires a click — a visual pattern is faster to absorb.

---

### DD-06: Similar races cross-reference

**The racer** sees "Similar to: Seward Park Crit, Cherry Pie Road Race" — races with comparable course profiles and finish type patterns. If they've done one of those, they can anchor their expectations. If they haven't, it's another race to explore.

**Why:** Persona says "course comparisons to known references collapse uncertainty instantly." This is the single most powerful anxiety reducer for someone who has done 1-2 races and is evaluating race #3.

**Data available:** Course type + finish type + distance can be used for similarity matching. Doesn't need to be sophisticated — same course_type + same predicted finish type + similar distance is a good-enough heuristic.

---

### DD-07: Course map with race features

**The racer** sees the course plotted on a map with key race features marked: start/finish, feed zones (if known), the major climbs highlighted on the route, and sprint points. This gives them a geographic mental model of the race.

**Status:** Map visualization exists (Folium, Sprint 008). Ensure it's integrated into the preview page alongside the elevation profile.

---

## Part 4: "My Team" Configuration

### MT-01: Set my team name once

**The racer** enters their team name in the sidebar (or a settings area) once. The app stores it in session state (and optionally in a cookie/URL param for persistence). This is used to power FG-02 (teammate badges) and DD-03 (startlist highlighting).

**Why:** This is the minimal personalization needed to unlock the social features. No account, no login — just a text input. The value is immediate: every race card now tells them if their people are going.

---

### MT-02: Teammate names on the card

**The racer** who has set their team name sees specific teammate names on cards where teammates are registered: "Jake, Maria registered" (if 1-2 teammates) or "3 teammates registered" (if more). Clicking shows full list.

**Why:** "Jake is doing this one" is a more powerful motivator than "1 teammate registered." Names make it personal.

---

## Part 5: Feed Organization & Filtering

The current feed is a flat list with "Racing Soon" / "Upcoming" / historical tiers. This doesn't match how a beginner racer actually scans a calendar. They think in terms of: "What's coming up that I'd actually do?" — which means filtering out disciplines they don't race, locations too far away, and then scanning what's left month by month. The feed should let them narrow fast and then scan the remainder efficiently.

### FO-01: Discipline filter (road, gravel, cyclocross, MTB, track)

**The racer** can filter the entire feed by discipline. Disciplines are higher-level than race type — "Road" encompasses road races, criteriums, time trials, hill climbs, and stage races. "Gravel" is its own discipline. So is cyclocross, mountain bike, and track.

A road racer who has zero interest in gravel or MTB events shouldn't have to scroll past them. They set "Road" once and the feed only shows road-discipline events. A multi-discipline racer can select multiple or leave it on "All."

**Why:** This is the coarsest, most decisive filter a racer applies. Before they care about date, location, or course — they already know they don't race gravel. Showing them gravel events is pure noise.

**Data gap:** The current `RaceType` enum (criterium, road_race, hill_climb, stage_race, time_trial) captures race format within the road discipline but doesn't model discipline as a separate concept. We need a `Discipline` field on `RaceSeries` (or derived from race type) that groups: Road = {criterium, road_race, hill_climb, stage_race, time_trial}, Gravel, CX, MTB, Track. For the current dataset (PNW road racing), most events are Road discipline, but as the tool grows this becomes essential.

---

### FO-02: Race type filter within discipline

**The racer** who has filtered to "Road" can further filter by race type: criteriums only, road races only, time trials only, etc. A beginner who has only done crits and isn't ready for a road race can narrow to just crits. A racer who hates time trials can exclude them.

**Why:** Within a discipline, race type is the next most decisive filter. Crits feel like a completely different sport than road races to a beginner — different skills, different anxiety, different preparation. Letting them filter means they see a manageable list of races they'd actually consider.

---

### FO-03: Geographic filter by state/region

**The racer** can filter by state or region: WA, OR, ID, BC, or "All PNW." A racer based in Seattle who won't drive to Boise for a Cat 5 race filters to WA (or WA + OR) and instantly removes races they'd never attend.

**Why:** Logistics is decision factor #1. A race 4 hours away is effectively invisible to most beginners — showing it wastes vertical space and attention. The state/province data already exists and is indexed.

**Data available:** `races.state_province` is populated and indexed. Filter can be a sidebar multi-select like the existing category filter.

---

### FO-04: Persistent filter preferences

**The racer** sets discipline, race type, geography, and category filters once. The app remembers them across sessions (via URL params and/or local storage). When they open the app Tuesday morning to check the weekend's races, their filters are already applied.

**Why:** Re-applying 3-4 filters on every visit is friction that punishes return users. The existing category filter already persists to URL params — extend this pattern to all filters.

---

### FO-05: Replace "Soon" / "Upcoming" labels with days-until countdown

**The racer** sees a concrete countdown on each upcoming race: "in 3 days", "in 6 days", "in 11 days", "in 2 weeks", "in 5 weeks". The rules:
- 0 days: "Today"
- 1 day: "Tomorrow"
- 2-14 days: "in N days"
- 15+ days: "in N weeks" (rounded down)

**Why:** "SOON" and "UPCOMING" are vague buckets that don't help a racer plan. "In 3 days" creates urgency. "In 6 weeks" says "I have time." The countdown is the single most useful temporal signal and it costs almost nothing to compute. Every calendar app does this — the racer's brain is already trained to read it.

**Current state:** The expander label shows "SOON" (≤7 days) or "UPCOMING" with a formatted date. The date is there but the racer has to do mental math. The countdown replaces the label AND makes the date redundant for quick scanning.

---

### FO-06: Month-based section headers (agenda view)

**The racer** sees the feed organized by month with clear visual headers: "March 2026", "April 2026", "May 2026". Within each month, races are sorted by date. This looks like a calendar agenda view — the format every racer already uses to think about their season.

**Why:** The current flat list with tier-based sorting (soon → upcoming → historical) doesn't help a racer think about their season structure. Month headers let them think: "What's in March? OK, two crits and a road race. April? Three road races including Banana Belt." They can plan a month at a time, which matches how beginners build a season — tentatively, one month ahead.

**Design:** Historical/dormant races can go in a collapsed "Past Races" section below the last upcoming month, or be omitted from the agenda view entirely (accessible via Browse All). The agenda view should be the default for upcoming races; the flat "all races" view remains available.

---

### FO-07: Don't over-emphasize the next race

**The racer** sees ALL upcoming races with equal visual weight, not a hero section for the next one. The "Racing Soon" section currently auto-expands and dominates the viewport. But the next race might be a gravel event the racer doesn't care about, or a 4-hour drive they'd never make. Giving it hero treatment before the racer has filtered is presumptuous.

**Why:** The beginner's primary mode is *browsing and learning*, not zeroing in on one race. They're trying to understand the full landscape of what's available — "what kinds of races exist? which ones sound interesting? what's the season look like?" A hero section assumes they've already decided, when they haven't. Equal-weight cards in a month-grouped agenda let them scan and self-select.

**Change:** Remove the auto-expanded "Racing Soon" section. Instead, the days-until countdown (FO-05) provides urgency naturally. Races "in 3 days" will stand out by their countdown without needing a separate section.

---

### FO-08: Scannable card density for multi-race evaluation

**The racer** can see at least 4-5 race cards on screen at once without scrolling — enough to compare and contrast. Cards in their collapsed/summary state should be compact: one line of essential info (name, date, location, countdown, discipline badge) plus a second line of quick-scan data (terrain, distance, finish type, drop rate).

**Why:** A beginner evaluating their first season needs to compare 10-20 races to find 3-5 they'll actually do. If each collapsed card takes up half the screen, they can only see 2 at a time and lose context as they scroll. Density enables comparison. The card earns vertical space when the racer *expands* it — not before.

**Current state:** Streamlit expanders have significant padding overhead. Each collapsed expander with its label takes ~60-80px. This is reasonable but the expanded cards are tall. Consider whether the collapsed label itself can carry more info (date, location, countdown, terrain) so the racer rarely needs to expand just to decide if they're interested.

---

## Part 6: Performance

The feed is too slow. A beginner racer who opens the app and waits 5+ seconds for the feed to render will close it and check BikeReg instead. Speed is not a feature — it's a prerequisite. Every second of load time costs users.

### PF-01: Eliminate N+1 queries in get_feed_items

**The problem:** `get_feed_items()` loops over every series and issues 8-10+ individual database queries per series: upcoming race, most recent race, edition count, prediction (which itself queries classifications), course data, duration (queries results), drop rate (queries results), narrative generation, editions list, and per-edition finish type computation. For 50 series, that's 400-500 queries.

**The fix:** Batch-load all data upfront:
- One query for all upcoming races (JOIN series, filter date >= today, partition by series, take first per series)
- One query for all most-recent races (partition by series)
- One query for all edition counts (GROUP BY series_id)
- One query for all courses
- Bulk-compute predictions, durations, drop rates from pre-loaded data rather than per-series session queries

**Target:** Feed load should complete in <500ms for the full dataset. Currently it's likely multiple seconds.

---

### PF-02: Cache feed results at the query layer

**The problem:** Every Streamlit rerun (filter change, button click, expander toggle) re-executes `get_feed_items()` from scratch. Streamlit's `@st.cache_data` is used for category/year/state lists but NOT for the main feed query.

**The fix:** Cache `get_feed_items()` results with `@st.cache_data(ttl=300)` keyed on (category, search_query, discipline, race_type, state). Feed data changes infrequently — a 5-minute cache is fine. Invalidate on explicit refresh.

---

### PF-03: Lazy-load expanded card content

**The problem:** The feed computes narrative snippets, sparkline downsampling, climb highlights, racer type descriptions, and editions summaries for ALL series upfront — even though only a few cards will be expanded at any time.

**The fix:** Split feed items into two tiers:
- **Tier 1 (always computed):** series metadata, date, location, upcoming status, countdown, course type, distance, gain, predicted finish type, drop rate, field size. This is the collapsed-card data — cheap to compute.
- **Tier 2 (computed on expand):** narrative snippet, elevation sparkline, climb highlight, racer type description, duration, editions summary. Loaded when the user expands a card, cached after first load.

**Why:** If 50 series are in the feed and the user expands 3, we're doing 47 sets of unnecessary computation. Tier 2 data involves JSON parsing, narrative generation, and multiple sub-queries — all skippable until needed.

---

### PF-04: Pre-compute and store prediction results

**The problem:** `predict_series_finish_type()`, `calculate_drop_rate()`, and `calculate_typical_duration()` run statistical aggregations over historical results on every feed load. These results don't change until new race results are scraped.

**The fix:** Compute predictions at scrape time and store them in a `series_predictions` table (or similar). The feed query then reads pre-computed values with a simple JOIN instead of running aggregation logic per-series at render time.

**When to recompute:** After any scrape that adds new results. A `last_computed` timestamp on the predictions table lets the app know if predictions are stale.

---

### PF-05: Paginate at the query layer, not in Python

**The problem:** `get_feed_items()` fetches and enriches ALL series, then Python slices `items[:visible_count]` for pagination. If there are 100 series, all 100 are fully computed even when only 20 are displayed.

**The fix:** Push pagination into the query. After applying filters and sorting, LIMIT/OFFSET the series list before the enrichment loop. Only enrich the 20 series that will actually be displayed.

**Depends on:** PF-01 (batch loading) makes this feasible — once data is batch-loaded, slicing the series list early is straightforward.

---

### PF-06: Profile and set a performance budget

**The problem:** We don't know what's actually slow. Is it the 400 queries? The narrative generation? JSON parsing? Streamlit rendering? Without measurement, optimization is guesswork.

**The fix:** Add lightweight timing instrumentation to `get_feed_items()`:
- Total wall time
- Time in DB queries (total)
- Time in prediction computation
- Time in narrative generation
- Number of queries executed

Log this on every feed load. Set a performance budget: feed must render in <1 second with a cold cache and <200ms with a warm cache. Alert (in dev/debug mode) when the budget is exceeded.

---

## Summary: What Changes

(Updated with Parts 5 and 6)

| Area | Current State | Proposed Change |
|------|--------------|-----------------|
| Card header | Name + date | Name + date + **location** + **countdown** |
| Card row 1 | Finish type, terrain, drop rate % | **Teammates** + terrain + distance + gain + field size + drop rate **label** |
| Card row 2 | Narrative + sparkline | Finish type prediction + sparkline |
| Card row 3 | Duration + climb highlight | Narrative + duration + climb highlight |
| Feed structure | Flat list, "Soon"/"Upcoming" tiers | **Month-grouped agenda** with countdown labels |
| Filtering | Category only | Category + **discipline** + **race type** + **state/region** (all persistent) |
| Detail preview | Exists but navigation-heavy | **Hero course graph** + climb breakdown + startlist with teams + similar races |
| Personalization | Category filter only | Category filter + **team name** + **discipline pref** + **geography pref** |
| Performance | N+1 queries, no caching, full compute on every load | Batch queries, cached feed, lazy expand, pre-computed predictions |

### Use Case Index

| ID | Name | Priority | Status |
|----|------|----------|--------|
| **First Glance** | | | |
| FG-01 | Date and location in header | P0 | Gap — location buried |
| FG-02 | Teammates registered badge | P0 | Gap — not built |
| FG-03 | Course character one-liner | P1 | Gap — distance/gain not on card |
| FG-04 | Finish pattern prediction lead | P1 | Built — confirm position |
| FG-05 | Field size on card | P1 | Gap — data exists, not rendered |
| FG-06 | Drop rate label prominent | P2 | Partially built — needs label emphasis |
| FG-07 | Race type label | P2 | Gap — may need data work |
| FG-08 | Card layout reorder | P0 | Redesign needed |
| **Detail Dive** | | | |
| DD-01 | Interactive course profile | P0 | Built (Sprint 008) |
| DD-02 | Climb breakdown with race context | P1 | Partially built — needs narrative |
| DD-03 | Startlist with team groupings | P1 | Gap — data exists, not grouped |
| DD-04 | Racer type description expanded | P2 | Partially built — needs expansion |
| DD-05 | Historical finish type visualization | P2 | Gap — text-only popover exists |
| DD-06 | Similar races cross-reference | P1 | Gap — needs similarity logic |
| DD-07 | Course map with race features | P2 | Built (Sprint 008) |
| **My Team** | | | |
| MT-01 | Set my team name | P0 | Gap — not built |
| MT-02 | Teammate names on card | P1 | Gap — depends on MT-01 |
| **Feed Organization** | | | |
| FO-01 | Discipline filter (road/gravel/CX/MTB/track) | P0 | Gap — discipline not modeled |
| FO-02 | Race type filter within discipline | P1 | Gap — race_type exists, not filterable |
| FO-03 | Geographic filter by state/region | P0 | Gap — data exists, not filterable |
| FO-04 | Persistent filter preferences | P1 | Partially built — category persists, others don't |
| FO-05 | Days-until countdown labels | P0 | Gap — uses "SOON"/"UPCOMING" |
| FO-06 | Month-based section headers | P0 | Gap — flat list |
| FO-07 | Don't over-emphasize next race | P1 | Gap — "Racing Soon" auto-expands |
| FO-08 | Scannable card density | P1 | Gap — cards too tall collapsed |
| **Performance** | | | |
| PF-01 | Eliminate N+1 queries | P0 | Gap — 8-10 queries per series |
| PF-02 | Cache feed results | P0 | Gap — no caching on main feed |
| PF-03 | Lazy-load expanded card content | P1 | Gap — all content computed upfront |
| PF-04 | Pre-compute predictions at scrape time | P1 | Gap — computed at render time |
| PF-05 | Paginate at query layer | P1 | Gap — Python-side slicing |
| PF-06 | Profile and set performance budget | P0 | Gap — no instrumentation |
