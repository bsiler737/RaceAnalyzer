# Sprint 006 Cross-Critique: UX and Practical Feasibility

**Reviewer**: Claude Opus 4.6
**Date**: 2026-03-09
**Drafts reviewed**: Claude, Codex, Gemini

---

## 1. User Flow: Calendar -> Series -> Edition Detail

**The three-level navigation (Calendar -> Series Detail -> Race Detail) is the right call, but only for multi-edition series.** All three drafts propose this hierarchy. The question is whether the intermediate series page adds value or just adds a click.

**For multi-edition series (2+ editions):** The series detail page is justified. A racer considering Banana Belt wants to see the trend across years -- that is the whole point of deduplication. Putting 4 years of classification history inline on a calendar tile would be information overload. The click-through is earned.

**For single-edition "series" (1 edition):** All three drafts handle this correctly by routing single-edition tiles straight to the existing race detail page. Gemini is explicit about this: "Single-edition tiles render identically to current tiles." Good.

**What is missing from all three drafts:** Back-navigation state preservation. Only Gemini specifies a `back_to_series` session state mechanism for returning from race detail to the series page. Claude and Codex leave this unspecified. This matters because Streamlit's lack of a browser-native back button means a broken "back" flow will frustrate users immediately. **Adopt Gemini's approach here.**

**Codex's sidebar edition navigator** is an interesting alternative: instead of a separate series page, it puts other editions in the sidebar of race_detail. This is actually clever for quick comparison -- a racer can hop between the 2024 and 2023 editions of the same race without leaving the detail view. However, it should be a complement to the series page, not a replacement. The series page provides the aggregated trend view that sidebar navigation cannot.

**Recommendation:** Calendar -> Series Detail (multi-edition) or Calendar -> Race Detail (single edition). Keep Codex's sidebar edition links as a bonus on the race detail page.

---

## 2. Series Tile Information Density

The three drafts represent a clear spectrum:

| Draft | Tile contents |
|-------|---------------|
| **Codex** | Name + edition count badge + date + location + classification badge |
| **Claude** | Name + edition count + date range + location + classification badge |
| **Gemini** | Name + edition count badge + date range + location + classification badge + mini distribution bar |

**Codex gets this right.** A tile's job is to help the racer quickly decide "is this race worth clicking on?" The answer comes from: what race is it (name), what type of race is it (badge), and when/where is it (date/location). Edition count is a useful signal ("this is a well-established race"). That is sufficient.

**Gemini's mini distribution bar is too much for a tile.** An 8px stacked bar on a tile card is:
- Too small to be readable at a glance. A racer scanning 20+ tiles will not pause to interpret color segments.
- Redundant with the badge, which already communicates the dominant finish type.
- Visually noisy when multiplied across a grid of tiles.

The distribution bar is excellent content -- but it belongs on the series detail page, not the tile. The racer who cares about "60% bunch sprint, 20% breakaway, 20% reduced" is already committed to learning about that race and will click through.

**Date range (Claude/Gemini) vs latest date (Codex):** Date range ("Mar 2022 -- Mar 2025") is more useful than just the latest date. It immediately communicates how long-running the series is, which matters for predicting whether it will happen again.

**Recommendation:** Adopt Codex's simplicity, add date range from Claude/Gemini, drop the mini distribution bar. Tile content: name + edition badge + date range + location + classification badge.

---

## 3. Classification Aggregation Visualization

All three drafts converge on a **stacked bar chart by year**. Is this the right chart type?

**Alternative analysis:**

| Chart type | Pros | Cons |
|-----------|------|------|
| **Stacked bar (proposed)** | Shows change over time; each year is a distinct data point; natural for "how many categories finished as X" | Hard to compare absolute values across years when baseline shifts; color segments can be hard to distinguish |
| **Pie chart** | Good for "overall proportion" at a glance | Terrible for comparison across years; cannot show trends; limited to one time period |
| **Sankey diagram** | Beautiful for showing flow between categories and outcomes | Massively over-engineered for this data; hard to read; unfamiliar to most users |
| **Simple frequency table** | Most precise; no ambiguity | Boring; takes more vertical space; harder to spot patterns |
| **Grouped bar (side by side)** | Easy to compare individual finish types across years | Takes more horizontal space; loses the "whole" view |
| **Heatmap table** | Compact; colored cells by finish type per category per year | Actually, this IS Gemini's per-category pivot table |

**The stacked bar chart is the right default for the headline "how does this race usually finish?"** It answers the trend question directly. However, it should be paired with Gemini's per-category pivot table, which answers the more specific question "does Cat 1/2 finish differently from Cat 4/5?"

**One concern with the stacked bar:** With only 2-4 years of data (the current dataset spans 2022-2025), a bar chart with 3 bars looks sparse. Consider: if a series has only 2 editions, the chart may not be worth rendering at all. A threshold of 3+ editions before showing the chart (falling back to a simple table for 2 editions) would avoid awkward-looking visualizations.

**Recommendation:** Stacked bar chart (all three drafts agree). Add Gemini's per-category pivot table below it. Skip the chart for series with fewer than 3 editions.

---

## 4. Course Map Prominence

**Gemini proposes a hero-sized map (75% column width in a `[3, 1]` split). Claude puts it as a secondary element within per-edition expanders. Codex uses a full-width Folium map on race detail.**

For a racer, the answer depends on **what they are looking at**:

- **Series detail page:** The classification data is more important. The racer came here to answer "what kind of race is this?" not "where does the road go?" A hero map pushes the classification content below the fold. Most racers already know the general area of PNW races; the map is supplementary.

- **Race detail page (individual edition):** The map is more important. The racer clicked through to a specific edition, possibly because race day is coming and they want to study the course. Here, a prominent map is justified.

**Gemini's hero layout has another problem:** It assumes one route per series, but different editions may use different courses (the Mason Lake problem that Codex and Gemini both acknowledge). Showing a single map for a series is potentially misleading. The map should be per-edition, shown on the race detail page.

**What should go in the series detail page map slot instead?** Either: (a) the most recent edition's route with a note "showing 2025 course", or (b) no map at all, with the map appearing per-edition in the accordion. Option (b) is safer and avoids the false-equivalence problem.

**Recommendation:** Map should be secondary on the series detail page (inside edition accordions or omitted from the top). Map should be prominent on the individual race detail page.

---

## 5. Empty State Handling

**Gemini is the clear winner here** with an explicit error/empty state table covering 8 scenarios. Claude and Codex handle the basics but leave several cases implicit.

**Critical comparison:**

| Scenario | Claude | Codex | Gemini |
|----------|--------|-------|--------|
| No RWGPS route found | Falls back to area map | Falls back to area map | Falls back to area map + caption "Course route not available" |
| Series with 1 edition | Implicit (works via existing code) | Implicit | Explicit: no edition badge, no distribution bar, no chart |
| No classifications at all | Not discussed | Not discussed | "Unknown" badge, no bar, "No classification data available" |
| Race not yet assigned to series | Not discussed | Uses COALESCE fallback | Explicit: renders as individual tile, shows message to run CLI |
| Network failure on RWGPS | Implicit (empty return) | Implicit | Explicit: log warning, serve from cache, never block page load |
| Geocoding fails | Not discussed | Not discussed | Map section absent, no error shown |
| Polyline decode fails | Not discussed | Not discussed | Log error, fall back to area map |
| Calendar empty after filters | render_empty_state() | render_empty_state() | render_empty_state() with contextual message |

**The ~50% of races without timing data** is the biggest UX concern. All three drafts include the "show unclassified" toggle, which is good. But consider: after deduplication, a series where ALL editions are "unknown" is essentially useless for the racer's primary use case (predicting race character). These should be deprioritized in the default view, which all three drafts do by filtering "unknown" by default. Good.

**What none of the drafts address:** What happens when a series has MIXED data -- some editions classified, some not? Example: Banana Belt 2022 has no timing data, 2023-2025 do. The series badge should be computed from the editions that have data, which is what the "ignore unknown" logic does. But the series detail page should explicitly show "No timing data" for the 2022 edition rather than silently omitting it from the chart. Gemini's chart code uses `if ft != "unknown": continue` which means 2022 would be absent from the bar chart entirely, with no indication to the user that data was missing. This should be addressed.

**Recommendation:** Adopt Gemini's comprehensive empty state table. Add one more case: "Edition with no classification data" should show an explicit "No timing data available" message in the edition accordion, and the chart should indicate missing years (e.g., a gap or a gray "no data" bar segment).

---

## 6. Scope Realism

All three drafts claim 5-6 days. Let me count the actual work:

**Feature 1 -- Course Maps:**
- RWGPS search client + scoring algorithm: 0.5 day
- Track point fetching + caching: 0.5 day
- Map rendering (Folium or iframe): 0.5 day
- CLI commands (match-routes, override): 0.5 day
- Tests: 0.5 day
- **Subtotal: ~2.5 days**

**Feature 2 -- Deduplication/Series:**
- Name normalization + tests: 0.5 day
- DB schema changes + migration: 0.5 day
- Series queries (tiles, detail, aggregation): 1 day
- Series tile rendering: 0.5 day
- Series detail page (full layout, chart, pivot, accordions): 1.5 days
- Calendar integration: 0.5 day
- CLI commands: 0.25 day
- Tests: 0.5 day
- **Subtotal: ~5.25 days**

**Combined: ~7.75 days, not 5-6.** The series detail page alone (chart + pivot table + accordion + map integration + back-navigation + empty states) is underestimated in all three drafts.

**Codex's phased approach is the most realistic.** It explicitly says Phase A (maps) and Phase B (dedup) are independent and can ship separately. It further identifies Phase C (series detail page polish) as stretch/next sprint. This is honest scoping.

**Gemini's draft is the most ambitious:** hero map, mini distribution bar on tiles, per-category pivot table, mobile responsiveness table, elevation profile stretch goal. This is great design work but probably 8-9 days to implement well.

**Claude's draft** falls in the middle -- full-featured but without the polish details Gemini adds.

**The key question:** Does the series detail page need to ship in this sprint, or can Calendar -> Race Detail (with edition sidebar links) suffice as an MVP? If the user's primary need is "stop showing me 4 copies of Banana Belt," then the calendar grouping alone delivers 80% of the value. The series detail page (with its chart, pivot, and accordion) is where the remaining 20% lives but also where most of the complexity is.

**Recommendation:** Ship in two phases within the sprint:
1. **Days 1-3:** Course maps (full) + series grouping with calendar tiles (no separate series detail page yet; clicking a series tile goes to the most recent edition's race detail, with Codex's sidebar edition links).
2. **Days 4-6:** Series detail page with chart and editions accordion. Cut the per-category pivot table and the mini distribution bar if running behind.

If days 4-6 prove insufficient, the series detail page slips to Sprint 007 with no loss of core value.

---

## Summary of Design Disagreements

| Decision | Claude | Codex | Gemini | Recommendation |
|----------|--------|-------|--------|----------------|
| **DB schema** | `RaceSeries` table + FK | `series_key` column (no new table) | `RaceSeries` + `RaceRoute` tables | Start with Codex's `series_key` column. Add `RaceSeries` table only if series-level metadata is needed. |
| **Map rendering** | RWGPS iframe | Folium polyline | Folium polyline | Folium polyline (Codex/Gemini). Iframe is too inflexible. |
| **Tile info density** | Medium | Minimal | High (distribution bar) | Minimal-to-medium. No distribution bar on tiles. |
| **Series detail map** | Per-edition in expander | N/A (no series page in MVP) | Hero-sized at top | Per-edition, not hero. |
| **Calendar toggle** | Series/Individual radio | No toggle (series only) | No toggle (series only) | No toggle for now. Series-only view is cleaner. |
| **Name normalization** | Strips suffixes but keeps canonical form ("banana belt road race") | Strips suffixes entirely ("banana belt") + handles Roman numerals | Strips suffixes, simple approach | Codex's approach is better -- stripping Roman numerals matters (Mason Lake I vs II). Stripping the suffix entirely ("banana belt" not "banana belt road race") is more aggressive but catches more variants. |
| **New dependencies** | None | `streamlit-folium`, `folium` | `streamlit-folium`, `folium`, `polyline` | `streamlit-folium` + `folium`. The `polyline` package is only needed if RWGPS returns encoded polylines (validate first). |
| **RWGPS route scoring** | Simple (0.7 name + 0.3 geo) | Complex (0.4 name + 0.25 geo + 0.2 length fit + 0.15 popularity) | Simple (first result from RWGPS) | Codex's 4-factor scoring is the most robust. Length fit is genuinely valuable for distinguishing crit routes from road race routes. |

---

## Recommended Merge Decisions

1. **Adopt Codex's `series_key` column approach** over Claude/Gemini's `RaceSeries` table. Simpler schema, fewer migrations, adequate for <2000 races. Upgrade to a dedicated table in a future sprint if series-level metadata becomes needed.

2. **Adopt Codex's 4-factor RWGPS scoring algorithm.** The race-type-aware distance expectations (crits are 0.8-3km, road races are 40-200km) will significantly reduce false matches compared to Claude's simpler 2-factor approach. Gemini's "take the first result" approach is too naive.

3. **Adopt Codex's Folium rendering** (not Claude's iframe). The styling control and offline capability justify the `streamlit-folium` dependency.

4. **Adopt Gemini's series detail page layout** (header + map + summary + chart + pivot + editions accordion) but demote the map from hero to per-edition, and cut the mini distribution bar from tiles.

5. **Adopt Gemini's empty state handling** as the comprehensive reference. Add the mixed-data case.

6. **Adopt Codex's phased rollout model.** Phase A (maps) and Phase B (dedup) ship independently. Series detail page is Phase C, shipped in the same sprint if time allows.

7. **Adopt Codex's name normalization** (handles Roman numerals, edition numbers, keeps `@lru_cache`). Merge in Claude's sponsor-stripping regex ("presented by", "sponsored by") which Codex lacks.

8. **Adopt Claude's `pick_display_name()` approach** (longest name with year stripped) for the series display name. Codex uses the most recent edition's name, which may be abbreviated.

---

## Interview Questions for the User

1. **When you look at the calendar today and see 4 copies of "Banana Belt RR," what do you actually want to do?** Are you comparing this year to last year (needing all editions visible), or just trying to find the upcoming one? This determines whether the calendar should group aggressively or offer a toggle.

2. **How often do you study the actual course map before a race?** Is the course map a "nice to have" or something you would actually use to make race-day decisions (kit choice, warm-up plan, feeding strategy)? This determines how prominent the map should be and whether the Folium polyline investment is worth it versus a simpler iframe.

3. **On a series detail page, what is the single most important thing to see?** If you clicked on "Banana Belt" and could only see one thing -- the course map, the classification trend chart, a list of past editions, or the overall badge -- which one? This determines page layout priority.

4. **Do you care about per-category breakdowns (e.g., "Cat 1/2 bunches, Cat 4/5 breaks away")?** Or is the overall series badge ("Bunch Sprint") sufficient for your needs? This determines whether the per-category pivot table is worth building or if it can be deferred.

5. **Are there races in the PNW calendar where the name stays the same but the course changes significantly between years?** (Mason Lake, Pacific Raceways, etc.) If yes, showing one course map for the whole series would be misleading, and we should show per-edition maps instead.
