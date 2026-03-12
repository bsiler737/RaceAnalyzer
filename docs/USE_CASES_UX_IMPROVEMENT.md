# RaceAnalyzer UX Improvement Use Cases

> **Persona:** A newer PNW road racer trying to decide which races to do, anxious about what to expect, and curious which races play to their strengths.
>
> **Core UX thesis:** Upcoming races and past race intelligence should be a single unified experience. The user's journey is: *discover an upcoming race → instantly see what that race is like based on historical data → decide if it's right for them.*
>
> **Rating instructions:** Mark each use case as **Good**, **OK**, or **Bad**.
>
> | Rating | Meaning |
> |--------|---------|
> | **Good** | Yes, build this — it directly improves the racer's journey |
> | **OK** | Reasonable but not urgent — would use it if it existed |
> | **Bad** | Wrong direction, not useful, or over-engineered for this persona |

---

## A. Unified Race Feed (Merging Upcoming + Historical)

### UC-01: See upcoming races with historical context inline
**The racer** opens the app and sees a single feed of upcoming races. Each race card already shows the predicted finish type, terrain badge, and drop rate — no clicking into a separate "past races" section required.

**Rating:** `[ good]`

---

### UC-02: Upcoming race cards link directly to the preview, not a results page
**The racer** taps an upcoming race and lands on a forward-looking preview ("What to Expect") rather than a backward-looking results table. Past results exist as supporting evidence within the preview, not as the primary view.

**Rating:** `[ good]`

---

### UC-03: Race cards sort by date with upcoming first
**The racer** sees upcoming races at the top of the feed sorted by date (soonest first), with past editions of those same races accessible by scrolling down or expanding the card — not on a separate page.

**Rating:** `[good ]`

---

### UC-04: Collapse historical editions under the upcoming race
**The racer** sees "Banana Belt Road Race — Mar 22, 2026" as a single card. A disclosure chevron reveals "5 previous editions" inline, showing finish types per year as a compact sparkline or icon row — no page navigation needed.

**Rating:** `[ good]`

---

### UC-05: Series-first view where the upcoming edition is the hero
**The racer** browses by series (e.g., "Banana Belt"). The series card prominently features the next upcoming edition date, registration link, and predicted finish type. Historical editions are secondary context within the same card.

**Rating:** `[ good]`

---

### UC-06: "No upcoming edition" badge on dormant series
**The racer** can distinguish between series with an upcoming edition and series that haven't been announced yet. Dormant series appear grayed out or at the bottom so the racer focuses on actionable races.

**Rating:** `[ good]`

---

### UC-07: One-tap from feed to registration
**The racer** sees a "Register" button directly on the race card in the main feed. They don't need to navigate to a detail page just to find the BikeReg link.

**Rating:** `[ good]`

---

## B. Reducing Race-Day Anxiety

### UC-08: "What to Expect" summary visible without clicking into detail
**The racer** sees a 1-2 sentence narrative preview directly on the race card in the feed (e.g., "Flat 60km course, usually ends in a bunch sprint. 12% drop rate — most finishers stay in the pack.").

**Rating:** `[good ]`

---

### UC-09: Finish type explained in plain language, not jargon
**The racer** sees "The group usually stays together and sprints for the finish" instead of "Bunch Sprint." Technical labels exist as tooltips for experienced racers, but the default is plain English.

**Rating:** `[good ]`

---

### UC-10: See "What kind of racer does well here?"
**The racer** sees a short description on the race preview like "Sprinters and pack riders thrive here" or "Strong climbers and breakaway artists have the edge" — derived from the course profile and finish type history.

**Rating:** `[good ]`

---

### UC-11: Visual severity indicator for how hard the race is
**The racer** sees a simple 1-5 difficulty scale (like a ski run rating) based on combined drop rate, elevation, and field strength — so they can eyeball whether this race is beginner-appropriate.

**Rating:** `[ bad]`

**RatingReason:** A hard race course can favor climbers or breakaway artists, so it could still be advantageous to some kinds of beginner.

---

### UC-12: See how many people typically finish vs. start
**The racer** sees "Typically 45 starters, 38 finishers" on the race card so they can gauge how brutal the selection is before reading deeper.

**Rating:** `[ bad ]`

**RatingReason:** We already have the number or racers dropped. Duplicative

---

### UC-13: "Races for your first season" curated filter
**The racer** can toggle a filter that shows only races with low drop rates, moderate field sizes, and simpler courses — a curated "beginner-friendly" subset of the calendar.

**Rating:** `[ bad]`

---

### UC-14: Show what getting dropped looks like
**The racer** can see from past results where in the race people typically get dropped (e.g., "Most riders who DNF'd were dropped by mile 15 on the climb"). This sets expectations so being dropped feels normal, not catastrophic.

**Rating:** `[ bad]`

---

### UC-15: See "What happens if I get dropped?"
**The racer** sees a note like "Riders who get dropped typically finish 5-10 minutes behind the pack. The course is well-marked and you can ride in safely." This addresses the #1 anxiety of new racers.

**Rating:** `[ bad]`

---

### UC-16: Display typical race duration
**The racer** sees "This race typically takes 1h 45m for the winning group and ~2h for the full field" so they can plan nutrition, warmup, and their day around the event.

**Rating:** `[good]`

---

## C. Matching Races to Racer Strengths

### UC-17: Self-identify racing style via simple quiz
**The racer** answers 3-4 questions ("Do you prefer flat roads or hills? Are you fast in a sprint or better at sustained efforts?") and gets tagged with a rider archetype (sprinter, climber, all-rounder, etc.) — no power data required.

**Rating:** `[ bad]`

**RatingReason:** Not necessarily a bad feature idea, but beginners tend to overly pigeonhole themselves in an archetype and we don't want to encourage that

---

### UC-18: See a "fit score" for each race based on rider type
**The racer** who self-identified as a sprinter sees a green "Great fit" badge on flat crits and a red "Tough fit" badge on hilly road races. The badge is visible directly on race cards in the feed.

**Rating:** `[ bad]`

---

### UC-19: Filter the race feed by "good for me"
**The racer** can toggle a filter that surfaces only races where their rider type historically performs well, based on course profile and finish type correlations.

**Rating:** `[ bad]`

---

### UC-20: See which finish types favor which racer types
**The racer** can read a brief explainer: "Bunch Sprint = sprinters dominate. Breakaway = attackers and climbers. Selective = pure climbers." This is always accessible as reference, not buried in a help page.

**Rating:** `[ good]`

---

### UC-21: Infer rider type from past results (if available)
**The racer** who has some race history in the database gets an auto-detected rider profile: "Your results suggest you're strongest in sprint finishes (3 of your 5 best results were bunch sprints)." This replaces or supplements the self-ID quiz.

**Rating:** `[bad ]`

---

### UC-22: Compare "my type" vs. "this race type" visually
**The racer** sees a simple overlap graphic — their strength profile (e.g., heavy on sprint, light on climbing) overlaid with the race's historical finish type distribution — so the match/mismatch is immediately visual.

**Rating:** `[ bad]`

---

### UC-23: Suggest tactical approach based on fit
**The racer** who is a sprinter looking at a hilly race sees: "This race doesn't favor your strengths, but if you survive the climbs, you'll have an advantage in the reduced group sprint at the finish." Conversely, a climber at a flat race sees: "Try to attack on the one short hill at km 35 — it's where breakaways have succeeded in 2 of the last 5 editions."

**Rating:** `[ bad]`

---

## D. Understanding the Competition

### UC-24: See contenders inline on the race card
**The racer** sees the top 3 registered riders (with points) directly on the race card without navigating to a separate page. "Top registered: J. Smith (82 pts), A. Lee (71 pts), M. Davis (65 pts)."

**Rating:** `[bad ]`

**RatingReason:** Only relevant to p12 field -- confusing for new racers who are going to be in the 4 or 5s

---

### UC-25: "How strong is the field?" summary metric
**The racer** sees a simple field strength indicator (e.g., "Strong field" / "Average field" / "Weak field") based on the aggregate points of registered riders vs. historical averages for this category.

**Rating:** `[ good]`

---

### UC-26: See which contenders are sprinters vs. climbers
**The racer** can see rider-type tags next to contender names in the startlist (e.g., "J. Smith — Sprinter, 82 pts"). This helps them understand not just who's fast, but who's dangerous in which scenario.

**Rating:** `[ good]`

---

### UC-27: "Riders I've raced against before" highlight
**The racer** who has some history sees which startlist riders they've previously raced against, with a note like "You finished 12 places behind J. Smith at Banana Belt 2025." This gives personal context.

**Rating:** `[ bad]`

---

### UC-28: See team representation in the field
**The racer** can see which teams have multiple riders registered: "Team X has 4 riders — they may control the race." This is critical tactical info that new racers often miss.

**Rating:** `[ good]`

---

## E. Course Intelligence (Inline, Not Separate)

### UC-29: Course profile thumbnail visible on the race card
**The racer** sees a tiny elevation sparkline directly on the race card in the feed — a visual shorthand for flat/rolling/hilly without needing to click through.

**Rating:** `[ good]`

---

### UC-30: Key climb callout on the race card
**The racer** sees "Key climb: 2.1 km at 6% avg" on the race card itself, not buried three clicks deep. This single data point often determines whether a race is appropriate.

**Rating:** `[ bad]`

---

### UC-31: "Where does the race get hard?" one-liner
**The racer** sees a summary like "The race gets hard at km 18 (a steep 1.5km climb) and again at km 42 (2km at 5%)" — derived from climb detection data, surfaced as a plain-English sentence.

**Rating:** `[good ]`

---

### UC-32: Course-finish correlation explanation
**The racer** can understand why a flat race usually ends in a sprint and why a hilly race usually ends selectively. A brief educational blurb connects course features to expected race dynamics.

**Rating:** `[ good]`

---

### UC-33: See course compared to a race they know
**The racer** sees "Similar course profile to Seward Park Crit" or "Comparable climbing to Banana Belt" — using a race they may have already done as a reference point.

**Rating:** `[good ]`

---

## F. Decision-Making & Planning

### UC-34: "Should I do this race?" decision summary
**The racer** sees a consolidated box at the top of the preview with: fit score, difficulty rating, predicted finish type, field strength, and drop rate — everything needed to decide in one glance.

**Rating:** `[ bad]`

---

### UC-35: Save races to a personal shortlist
**The racer** can bookmark races they're considering. Their shortlist is accessible from a "My Races" tab, showing dates and key stats so they can compare and decide.

**Rating:** `[ bad]`

---

### UC-36: See travel distance to each race
**The racer** inputs their home location once and sees driving time/distance on every race card. A 3-hour drive vs. a 30-minute drive materially changes the decision.

**Rating:** `[ bad]`

---

### UC-37: Compare two races side by side
**The racer** can select two upcoming races and see them compared: course profile, finish type, difficulty, field strength, and fit score side by side. This helps when choosing between races on the same weekend.

**Rating:** `[ good]`

---

### UC-38: See a season overview with race types highlighted
**The racer** sees a calendar-style view of the season with each race color-coded by predicted finish type. They can see at a glance that March is all crits, April has two hilly road races, and May has the big stage race.

**Rating:** `[ good]`

---

### UC-39: Get a "season plan" recommendation
**The racer** who has set their rider type gets a suggested progression: "Start with Seward Park Crit (easy, flat), then try Banana Belt (moderate, rolling), then Cherry Blossom (hard, hilly)." A curated pathway for the season.

**Rating:** `[ bad]`

---

## G. Post-Race Learning (Feeding Back Into the Journey)

### UC-40: After a race, see "How did it actually go?" vs. prediction
**The racer** returns to a race they did and sees whether the predicted finish type matched the actual classification. "We predicted Bunch Sprint, and it was indeed a Bunch Sprint." This builds trust in the tool.

**Rating:** `[ bad]`

---

### UC-41: See my result in the context of gap groups
**The racer** finds their name in the results and sees "You finished in Group 2, 35 seconds behind the lead group (Group 1 had 12 riders)." This tells a richer story than "23rd place."

**Rating:** `[ baed]`

---

### UC-42: "What should I work on?" based on my results
**The racer** who keeps getting dropped on climbs sees "You've been dropped on hilly courses in 3 of 4 races — consider focusing climbing in training or choosing flatter races." Actionable insight from their data.

**Rating:** `[ bad]`

---

### UC-43: Track improvement across the season
**The racer** sees a simple trend: "Your gap to the leader has decreased from 4:30 to 2:15 over the season" or "You've moved from Group 3 to Group 2." Progress visualization even when they're not winning.

**Rating:** `[ bad]`

---

## H. Information Architecture & Navigation

### UC-44: Single entry point, not five pages
**The racer** opens the app and lands on one unified feed — not a choice between "Calendar," "Series Detail," "Race Detail," "Preview," and "Dashboard." Those are implementation details, not user tasks. The feed IS the app.

**Rating:** `[ good]`

---

### UC-45: Category filter is persistent and global
**The racer** sets their category once (e.g., "Cat 4/5 Men") and every view — feed, preview, contenders, stats — automatically filters to that category. They never have to re-select it.

**Rating:** `[ good]`

---

### UC-46: Race card expands in place instead of navigating away
**The racer** clicks a race card and it expands inline to show the full preview (course, prediction, contenders) without leaving the feed. A "collapse" button returns them to browsing. No back-button navigation needed.

**Rating:** `[ good]`

---

### UC-47: Deep link to a race preview from external sources
**The racer's** friend texts them a link to a specific race preview. The link opens directly to that race's preview with all context — no login wall, no landing page, no "select a race first."

**Rating:** `[ good]`

---

### UC-48: "What's racing this weekend?" quick view
**The racer** sees a prominent "This Weekend" section at the very top of the feed showing only races in the next 7 days. This is the most common check-in behavior.

**Rating:** `[ good]`

---

### UC-49: Search for a race by name
**The racer** types "Banana Belt" into a search bar and immediately sees that series with its upcoming edition, past classifications, and course profile. No browsing through tiles required.

**Rating:** `[ good]`

---

### UC-50: Remember where I left off
**The racer** returns to the app and it remembers their category filter, last-viewed race, and scroll position. The experience picks up where they left off rather than resetting to the default view.

**Rating:** `[ good]`

---

## Summary

| Section | Use Cases | Range |
|---------|-----------|-------|
| A. Unified Race Feed | 7 | UC-01 – UC-07 |
| B. Reducing Race-Day Anxiety | 9 | UC-08 – UC-16 |
| C. Matching Races to Racer Strengths | 7 | UC-17 – UC-23 |
| D. Understanding the Competition | 5 | UC-24 – UC-28 |
| E. Course Intelligence (Inline) | 5 | UC-29 – UC-33 |
| F. Decision-Making & Planning | 6 | UC-34 – UC-39 |
| G. Post-Race Learning | 4 | UC-40 – UC-43 |
| H. Information Architecture & Nav | 7 | UC-44 – UC-50 |
| **Total** | **50** | |

### How These Differ from Existing User Stories

The previous user story sets (`USER_STORIES.md`, `best_user_stories.md`) were organized by **technical capability** (scraping, classification, prediction, etc.) and by **feature** (course maps, startlists, dashboards). These use cases are organized by **user journey moments**:

1. **Discovery** (A, H) — finding the right race
2. **Understanding** (B, E) — knowing what to expect
3. **Self-assessment** (C) — knowing if it's right for them
4. **Competition intel** (D) — knowing who they're racing against
5. **Decision** (F) — choosing and committing
6. **Growth** (G) — learning from the experience

The central architectural change proposed here is **collapsing the upcoming/historical split into a single feed where every race card is forward-looking by default**, with historical data serving as evidence rather than as a separate browsing experience.

---

## Why the Good Use Cases Are Good

The use cases rated **Good** share a few common qualities:

1. **They serve the core loop: discover → understand → decide → register.** The strongest use cases (UC-01 through UC-07, UC-44 through UC-50) collapse the journey from "what races exist?" to "I'm signing up" into as few steps as possible. Every good use case either shortens that path or adds context directly on the path without creating detours.

2. **They surface insight inline, not on separate pages.** Race cards that already show finish type predictions (UC-01), plain-language summaries (UC-08, UC-09), course thumbnails (UC-29), and field strength (UC-25) all respect the same principle: the racer should learn what they need without clicking away from the feed. Information architecture use cases (UC-44, UC-46, UC-48) reinforce this by eliminating page navigation entirely.

3. **They give context without prescribing decisions.** Good use cases like UC-10 ("What kind of racer does well here?"), UC-20 (finish type explanations), UC-31 ("Where does the race get hard?"), and UC-32 (course-finish correlations) educate the racer and let them draw their own conclusions. They describe the race, not the racer.

4. **They are objective and race-centric.** Team representation (UC-28), field strength (UC-25), contender rider types (UC-26), race duration (UC-16), course comparisons (UC-33), and season calendars (UC-38) all present factual, observable data about the race itself — data that's useful regardless of who the racer is or how experienced they are.

## Why the Bad Use Cases Are Bad

The use cases rated **Bad** fall into a few recurring traps:

1. **They pigeonhole beginners into archetypes.** The entire "Matching Races to Racer Strengths" section (UC-17 through UC-19, UC-21 through UC-23) asks new racers to self-identify as a "type" and then filters or scores races accordingly. New racers don't yet know what kind of racer they are, and labeling them too early encourages them to avoid races that might actually develop their weaknesses. The tool should describe races, not tell racers who they are.

2. **They duplicate data that already exists in a simpler form.** UC-12 (starters vs. finishers) restates the drop rate that's already shown. UC-30 (key climb callout) overlaps with the course profile thumbnail (UC-29) and the "where does it get hard?" summary (UC-31). Redundant data adds clutter without adding insight.

3. **They oversimplify things that aren't one-dimensional.** UC-11's difficulty scale (1–5, like a ski run) flattens a nuanced picture — a "hard" hilly race might actually be an advantage for a climber, even a beginner climber. A single scalar misrepresents the race and could scare off racers who'd do well.

4. **They drift from the tool's core value proposition.** The post-race learning features (UC-40 through UC-43) — prediction accuracy, gap group context, training recommendations, season tracking — are a different product. The tool's strength is helping racers choose upcoming races, not coaching them after the fact. Building these features dilutes focus without serving the primary "what should I race next?" question.

5. **They add personalization complexity for marginal value.** Saving races to a shortlist (UC-35), travel distance calculation (UC-36), season plan recommendations (UC-39), "riders I've raced against" (UC-27), and the "should I do this race?" decision box (UC-34) all require user accounts, stored preferences, or location data — significant engineering cost for features that serve a narrow moment in the journey. The feed itself, done well, makes these features unnecessary.

6. **They target the wrong audience for this persona.** UC-24 (inline contenders with points) is only meaningful to P/1/2 racers, not the newer Cat 4/5 racer this tool is designed for. Features aimed at advanced racers confuse beginners and clutter the interface.
