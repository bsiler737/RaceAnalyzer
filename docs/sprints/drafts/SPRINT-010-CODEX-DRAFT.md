# Sprint 010: Unified Race Feed & Forward-Looking UX Overhaul

## Overview

Sprint 010 restructures the RaceAnalyzer Streamlit UI around a single entry point: a unified race feed that merges upcoming and historical race data into one scrollable stream. Today, a racer must navigate across five separate pages (Calendar, Series Detail, Race Detail, Race Preview, Finish Type Dashboard) to answer the basic question "what should I race next?" This sprint collapses that journey into a feed-first architecture where every race card is forward-looking by default, inline-expandable, and enriched with the prediction and course intelligence data that already exists in the database.

The architectural bet here diverges from the obvious approach of "rebuild the Calendar page." Instead of incrementally improving the existing Calendar page, this sprint introduces a **new Feed page that becomes the default**, keeps the existing pages intact as deep-link targets, and uses Streamlit's `st.session_state` as a lightweight state bus to coordinate the global category filter, expanded card tracking, and search state. The existing pages become detail views that the feed links to only when the user wants the full firehose -- the feed itself provides enough inline context that most users never leave it.

This approach has a practical advantage: it is non-destructive. The existing Calendar, Series Detail, Race Preview, and Race Detail pages continue to function and serve as deep-link destinations. The new Feed page is additive. If it ships half-finished, the old pages still work.

**Duration**: 2-3 weeks
**Prerequisite**: Sprint 009 complete (road-results calendar, startlists, power rankings)

---

## Use Cases

### Included (the realistic 2-3 week scope)

These are grouped by the phase that implements them:

**Feed foundation (Phase 1):**
- UC-44: Single entry point -- the feed IS the app
- UC-03: Races sort by date with upcoming first
- UC-01: Upcoming race cards show historical context inline (finish type, terrain, drop rate)
- UC-06: "No upcoming edition" badge on dormant series
- UC-48: "This Weekend" section at top of feed

**Rich cards with inline data (Phase 2):**
- UC-08: 1-2 sentence narrative preview on the card itself
- UC-09: Finish type explained in plain language, not jargon
- UC-29: Elevation sparkline thumbnail on the card
- UC-07: Register button directly on the card
- UC-16: Typical race duration on the card

**Navigation, search, and state (Phase 3):**
- UC-45: Category filter is persistent and global
- UC-49: Search for a race by name
- UC-46: Race card expands in place (via `st.expander` + session state)
- UC-47: Deep link to a race preview from external sources
- UC-02: Upcoming cards link to preview, not results

**Contextual enrichment (Phase 4):**
- UC-05: Series-first view where upcoming edition is the hero
- UC-04: Historical editions collapsed under the upcoming race
- UC-31: "Where does the race get hard?" one-liner
- UC-10: "What kind of racer does well here?"
- UC-32: Course-finish correlation explanation
- UC-50: Remember category filter and last-viewed state across sessions

### Deferred (cut from this sprint)

- UC-37: Side-by-side race comparison -- requires a new multi-select UI paradigm; better as its own sprint
- UC-33: Course compared to a known race -- needs a course similarity algorithm (Euclidean distance on profile vectors, or DTW); too much new data work
- UC-38: Season calendar view -- color-coded month grid is a custom component; defer to a Sprint 011 "Season Planning" sprint
- UC-25: Field strength indicator -- algorithm is undefined (aggregate carried_points vs. historical average); needs design work before implementation
- UC-26: Contender rider types -- requires inferring rider archetypes from result history; no such classification exists yet
- UC-28: Team representation -- interesting but niche; the contender list already shows teams
- UC-20: Finish type explainer reference -- could be a static markdown page, but doesn't need sprint effort

The cuts are driven by a principle: this sprint is about **reorganizing and surfacing existing data**, not computing new derived data. UC-25, UC-26, UC-33, and UC-38 all require new algorithms or new UI components. UC-37 needs a new interaction pattern. These are better served by focused follow-up sprints.

---

## Architecture

### Feed-First, Pages-Second

The core architectural change is introducing a new `feed.py` page that becomes the `default=True` page in `app.py`. The existing Calendar page becomes a secondary page (renamed "Browse All" or similar). This is a single line change in `app.py`:

```python
feed_page = st.Page("pages/feed.py", title="Race Feed", icon="\U0001f3c1", default=True)
calendar_page = st.Page("pages/calendar.py", title="Browse All", icon="\U0001f4c5")
```

The feed page is a new file, not a modification of `calendar.py`. This avoids the risk of breaking the existing calendar during development and allows the two views to coexist.

### State Management: Session State as a Bus

Streamlit reruns the full page script on every interaction. The unified feed needs to coordinate:

1. **Global category filter** -- set once, respected by all cards and detail views
2. **Expanded card tracking** -- which feed card is currently expanded
3. **Search query** -- the current search string
4. **"This Weekend" filter toggle** -- boolean

All of these live in `st.session_state`:

```python
# Initialized once in feed.py render()
if "feed_category" not in st.session_state:
    st.session_state.feed_category = None  # None = all categories
if "feed_expanded_series" not in st.session_state:
    st.session_state.feed_expanded_series = None  # series_id or None
if "feed_search" not in st.session_state:
    st.session_state.feed_search = ""
if "feed_this_weekend" not in st.session_state:
    st.session_state.feed_this_weekend = False
```

### Inline Card Expansion: Why `st.expander` Wins

The intent doc asks about three approaches for inline expansion: (a) `st.expander`, (b) session state conditional rendering, (c) page navigation.

This draft chooses **`st.expander` with session-state-driven `expanded` flag**, not raw conditional rendering. Rationale:

- `st.expander` is a native Streamlit component with built-in open/close affordance and accessibility. It renders collapse/expand without JavaScript.
- Session-state conditional rendering (option b) requires building custom open/close buttons, tracking state manually, and handling the "only one card open at a time" constraint ourselves. It works but is more code for the same result.
- Page navigation (option c) violates the "single feed" thesis.

The pattern:

```python
for series in feed_items:
    with st.expander(series.display_name, expanded=(st.session_state.feed_expanded_series == series.id)):
        render_feed_card_summary(series)  # always shown
        if st.session_state.feed_expanded_series == series.id:
            render_feed_card_detail(series)  # full preview content
```

One limitation: `st.expander` doesn't fire a callback when toggled in Streamlit's current API. To track which card is open, we use a button inside the summary that sets `st.session_state.feed_expanded_series` and triggers `st.rerun()`. The expander serves as the visual container; the button controls the state.

**Alternative considered:** Using `st.container(border=True)` with conditional rendering and a toggle button. This gives more layout control but loses the native expand/collapse animation. If the expander approach feels too constrained during implementation, this is a viable fallback.

### Feed Query: A New Aggregation Function

The feed needs a single query that returns series ordered by relevance:

1. Series with upcoming races (sorted by upcoming date ascending)
2. Series without upcoming races (sorted by most recent edition descending)

This is a new function `get_feed_items()` in `queries.py` that returns a list of dicts, each pre-loaded with the data needed for a rich card:

```python
def get_feed_items(
    session: Session,
    *,
    category: Optional[str] = None,
    search: Optional[str] = None,
    this_weekend: bool = False,
) -> list[dict]:
    """Return series data for the unified feed, upcoming-first.

    Each dict contains:
      - series metadata (id, display_name, location, state)
      - upcoming race info (date, registration_url) or None
      - prediction (predicted_finish_type, confidence)
      - course summary (course_type, distance_km, total_gain_m)
      - narrative snippet (first 2 sentences of generate_narrative)
      - drop_rate dict
      - typical_speed dict
      - has_upcoming: bool
      - edition_count: int
      - elevation_sparkline: list[float] or None (downsampled to ~30 points)
    """
```

This is a fat query by design. The feed card renders all of this data without any secondary fetches. The tradeoff is a heavier initial load, but the feed is the only page the user sees on launch, so front-loading the data is acceptable.

The `this_weekend` filter is implemented as a date range filter: `today <= race.date <= today + 7 days`.

The `search` filter is a case-insensitive `LIKE '%query%'` on `RaceSeries.display_name`. Simple, no full-text search index needed.

### Elevation Sparkline: Downsampled Profile Data

UC-29 wants a tiny elevation profile on the card. The full `profile_json` in the Course table can be thousands of points. The feed query downsamples this to ~30 points using simple min-max decimation (take every Nth point, preserving the global min and max). This produces a list of elevation values that `st.line_chart` or a tiny `st.area_chart` can render in a small column.

No custom JavaScript required -- Streamlit's built-in charting is sufficient for a sparkline at this size.

### Plain-Language Finish Types (UC-09)

The existing `FINISH_TYPE_TOOLTIPS` dict in `queries.py` already contains plain-English descriptions:
- "The whole pack stayed together and sprinted for the line."
- "A solo rider or tiny group escaped and held on to the finish."

The feed card uses these tooltip strings as the **primary text** and moves the technical label ("Bunch Sprint") into a smaller caption. This is a presentation change, not a data change. A new helper:

```python
def finish_type_plain_english(ft_value: str) -> str:
    """Return the plain-English explanation, or fall back to display name."""
    return FINISH_TYPE_TOOLTIPS.get(ft_value, finish_type_display_name(ft_value))
```

### "What Kind of Racer Does Well Here?" (UC-10)

This is a template-based string derived from course type and predicted finish type. No new algorithm -- just a lookup table:

```python
RACER_TYPE_DESCRIPTIONS = {
    ("flat", "bunch_sprint"): "Sprinters and pack riders thrive here.",
    ("flat", "breakaway"): "Strong riders who can sustain a solo effort have an edge.",
    ("rolling", "reduced_sprint"): "Punchy riders who can handle repeated surges do well.",
    ("hilly", "gc_selective"): "Pure climbers dominate this race.",
    # ... ~12 combinations covering the realistic pairings
}
```

Fallback: if the combination isn't in the table, omit the sentence. This is cheap to implement and directly answers the use case without requiring rider-type inference.

### Typical Race Duration (UC-16)

The existing `typical_speed` data includes `median_winner_speed_kph` and the course has `distance_m`. Duration = distance / speed. This is a simple derivation added to the narrative or displayed as a metric:

```python
if typical_speed and course_dict and course_dict.get("distance_m"):
    distance_km = course_dict["distance_m"] / 1000
    winner_hours = distance_km / typical_speed["median_winner_speed_kph"]
    # Format as "~1h 45m"
```

### Persistent Category Filter Across Pages (UC-45)

`st.session_state.feed_category` is set on the feed page and read by Race Preview, Series Detail, and Race Detail pages. Each page checks:

```python
category = st.session_state.get("feed_category") or st.query_params.get("category")
```

The feed page sets this in the sidebar (or top bar). When the user navigates to a detail page and back, the filter persists because `st.session_state` survives page transitions within a Streamlit session.

### Deep Links (UC-47)

Already partially implemented via `st.query_params`. The feed page checks for `?series_id=X` on load and auto-expands that card. Race Preview already accepts `?series_id=X&category=Y`. No new work needed beyond ensuring the feed page handles the query param.

### "Remember Where I Left Off" (UC-50)

Streamlit session state persists within a browser session but not across page reloads. For cross-session persistence, we use `st.query_params` to encode the category filter and last-viewed series into the URL. When the user bookmarks or refreshes, the URL restores state:

```
?category=Men+Cat+4%2F5&series_id=42
```

This is lightweight and requires no server-side storage.

---

## Implementation

### Phase 1: Feed Page Foundation & Feed Query (30% effort)

**Goal:** A new feed page that shows all series sorted upcoming-first, with basic card rendering and the "This Weekend" section.

**Files:**
- `raceanalyzer/ui/pages/feed.py` -- CREATE: New unified feed page
- `raceanalyzer/queries.py` -- MODIFY: Add `get_feed_items()` query function
- `raceanalyzer/ui/app.py` -- MODIFY: Add feed page as default, demote calendar
- `tests/test_queries.py` -- MODIFY: Add tests for `get_feed_items()`

**Tasks:**
- [ ] Create `get_feed_items()` in `queries.py` that returns series-level dicts with upcoming race info, prediction, course summary, drop rate, and narrative snippet
- [ ] Implement "This Weekend" date filtering (today to today+7)
- [ ] Implement search filtering (case-insensitive LIKE on display_name)
- [ ] Create `feed.py` page with: search bar at top, "This Weekend" toggle, series cards rendered in a single-column list (not the 3-column grid -- feed cards are wider and richer)
- [ ] Each card shows: series name, upcoming date (or "No upcoming edition"), finish type badge, terrain badge, location
- [ ] "No upcoming edition" series appear grayed out (lower opacity via inline CSS) and sorted after upcoming series (UC-06)
- [ ] Add feed page to `app.py` navigation as default
- [ ] Tests: `get_feed_items` returns upcoming-first ordering; search filters correctly; this_weekend filters correctly; empty database returns empty list

### Phase 2: Rich Card Content (25% effort)

**Goal:** Feed cards show narrative snippets, plain-language finish types, elevation sparklines, register buttons, and race duration.

**Files:**
- `raceanalyzer/ui/pages/feed.py` -- MODIFY: Enrich card rendering
- `raceanalyzer/ui/components.py` -- MODIFY: Add `render_feed_card()`, `render_elevation_sparkline()` helper
- `raceanalyzer/queries.py` -- MODIFY: Add `finish_type_plain_english()`, add sparkline downsampling to `get_feed_items()`, add duration calculation
- `raceanalyzer/predictions.py` -- MODIFY: Add `racer_type_description()` lookup function
- `tests/test_queries.py` -- MODIFY: Test sparkline downsampling, plain-English finish types

**Tasks:**
- [ ] Add `finish_type_plain_english()` helper to `queries.py`
- [ ] Add elevation sparkline downsampling in `get_feed_items()` -- take every Nth point from `profile_json` to produce ~30 points
- [ ] Render sparkline using `st.area_chart()` in a narrow column (height ~60px via `st.area_chart(data, height=60)`) -- note: Streamlit's `height` param on charts may require workaround via custom CSS
- [ ] Render 1-2 sentence narrative on the card (truncate `generate_narrative()` output to first 2 sentences)
- [ ] Render plain-English finish type as primary text, technical label as caption
- [ ] Add "Register" button/link directly on card when `registration_url` is available (UC-07)
- [ ] Add race duration estimate when speed and distance data are available (UC-16)
- [ ] Add `racer_type_description()` in `predictions.py` -- lookup table mapping (course_type, finish_type) to a sentence about what kind of racer does well
- [ ] Render racer type description on card when available (UC-10)
- [ ] Tests: sparkline downsampling produces correct number of points; `finish_type_plain_english` returns tooltip text; `racer_type_description` returns expected strings for known combinations and None for unknown

### Phase 3: Navigation, Search, and Persistent State (25% effort)

**Goal:** Category filter persists globally, cards expand inline, search works, deep links work.

**Files:**
- `raceanalyzer/ui/pages/feed.py` -- MODIFY: Add inline expansion, category filter, deep link handling
- `raceanalyzer/ui/pages/race_preview.py` -- MODIFY: Read `feed_category` from session state
- `raceanalyzer/ui/pages/series_detail.py` -- MODIFY: Read `feed_category` from session state
- `raceanalyzer/ui/pages/race_detail.py` -- MODIFY: Read `feed_category` from session state
- `raceanalyzer/ui/components.py` -- MODIFY: Add `render_global_category_filter()`

**Tasks:**
- [ ] Add global category selector in the feed sidebar that writes to `st.session_state.feed_category` and `st.query_params["category"]`
- [ ] Modify Race Preview, Series Detail, and Race Detail pages to check `st.session_state.get("feed_category")` as default category
- [ ] Implement inline card expansion: each card has a "More" button that sets `st.session_state.feed_expanded_series = series_id` and triggers `st.rerun()`
- [ ] Expanded card shows: full narrative, course profile (reuse `render_interactive_course_profile` from `maps.py` if profile data exists), prediction details, contender list top-5, "Where does the race get hard?" climb one-liner (UC-31), course-finish correlation blurb (UC-32)
- [ ] Expanded card has "View Full Preview" button linking to Race Preview page, and "Collapse" button
- [ ] Historical editions appear as a sub-list inside the expanded card: "5 previous editions" with year and finish type per edition (UC-04, UC-05)
- [ ] Handle `?series_id=X` query param on feed load: auto-expand that card
- [ ] Handle `?category=Y` query param on feed load: set global category filter
- [ ] UC-02: "More" button on upcoming race cards leads to expansion with preview content, not to Race Detail (the historical results page)
- [ ] "Where does the race get hard?" one-liner (UC-31): extract from `climbs` data, format as "The race gets hard at km X (a Ym climb at Z%)" -- reuse the climb sentence logic from `generate_narrative()`
- [ ] Course-finish correlation blurb (UC-32): static lookup mapping course_type to a 1-sentence explanation ("Flat courses tend to end in bunch sprints because..." etc.)
- [ ] Tests: session state persists category across pages; deep link auto-expands correct card; search + category filter combination works

### Phase 4: Polish, Edge Cases, and Persistence (20% effort)

**Goal:** Handle edge cases, polish the feed layout, ensure existing pages still work, add URL-based state persistence.

**Files:**
- `raceanalyzer/ui/pages/feed.py` -- MODIFY: Edge cases, empty states, URL state sync
- `raceanalyzer/ui/pages/calendar.py` -- MODIFY: Minor rename/reorganization (keep functional)
- `raceanalyzer/ui/components.py` -- MODIFY: Feed card empty states
- `tests/test_feed_integration.py` -- CREATE: Integration tests for feed query + rendering edge cases

**Tasks:**
- [ ] Empty state: no races in database -- show friendly message with CLI hint
- [ ] Empty state: no upcoming races -- show "No upcoming races found. Showing all series by most recent edition."
- [ ] Empty state: search returns nothing -- show "No races matching 'X'" with clear-search button
- [ ] Empty state: series with no course data -- card still renders without sparkline, terrain badge, or duration
- [ ] Empty state: series with no historical data -- card shows "New event -- no historical data yet" instead of prediction
- [ ] Sync `feed_category` and `feed_expanded_series` to `st.query_params` so bookmarks and refreshes restore state (UC-50)
- [ ] Verify Race Preview page still works standalone (accessed via direct URL or from feed expansion)
- [ ] Verify Series Detail page still works standalone
- [ ] Verify Race Detail page still works standalone
- [ ] Verify Dashboard page still works standalone
- [ ] Verify existing calendar page still works (now as "Browse All")
- [ ] Add pagination to feed: show first 20 series, "Show more" button loads next 20 (reuse pattern from calendar.py)
- [ ] Performance: cache `get_feed_items()` with `@st.cache_data(ttl=300)` to avoid re-querying on every interaction
- [ ] Run `ruff check .` on all new/modified files
- [ ] Run `pytest tests/ -v` and verify all existing tests pass
- [ ] Tests: feed renders correctly with zero upcoming races; feed renders with series missing course/prediction data; pagination works; cache invalidation works

---

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/ui/pages/feed.py` | CREATE | New unified race feed page -- the primary entry point |
| `raceanalyzer/ui/app.py` | MODIFY | Add feed page as default, demote calendar to secondary |
| `raceanalyzer/queries.py` | MODIFY | Add `get_feed_items()`, `finish_type_plain_english()`, sparkline downsampling |
| `raceanalyzer/predictions.py` | MODIFY | Add `racer_type_description()` lookup |
| `raceanalyzer/ui/components.py` | MODIFY | Add `render_feed_card()`, `render_elevation_sparkline()`, `render_global_category_filter()` |
| `raceanalyzer/ui/pages/race_preview.py` | MODIFY | Read global category from session state |
| `raceanalyzer/ui/pages/series_detail.py` | MODIFY | Read global category from session state |
| `raceanalyzer/ui/pages/race_detail.py` | MODIFY | Read global category from session state |
| `raceanalyzer/ui/pages/calendar.py` | MODIFY | Minor: still functional, no longer default page |
| `tests/test_queries.py` | MODIFY | Tests for `get_feed_items`, sparkline, plain-English helpers |
| `tests/test_feed_integration.py` | CREATE | Integration tests for feed edge cases |
| `tests/test_predictions.py` | MODIFY | Tests for `racer_type_description()` |

---

## Definition of Done

### Feed Experience
- [ ] Opening the app lands on the unified feed, not the old Calendar page
- [ ] Upcoming races appear at the top of the feed, sorted by date ascending (soonest first)
- [ ] Series without upcoming editions appear below, sorted by most recent edition descending
- [ ] Each feed card shows: series name, date, finish type (plain English), terrain badge, narrative snippet, drop rate
- [ ] Each feed card shows an elevation sparkline when course profile data exists
- [ ] Each feed card shows a "Register" link when `registration_url` is available
- [ ] Dormant series (no upcoming edition) appear visually dimmed
- [ ] "This Weekend" toggle filters to races within the next 7 days

### Inline Expansion
- [ ] Clicking "More" on a feed card expands it inline to show full preview content
- [ ] Expanded cards show: full narrative, course profile, prediction with distribution, top 5 contenders, climb one-liner, course-finish correlation, historical editions
- [ ] Historical editions are collapsed under the upcoming edition with year and finish type
- [ ] Only one card is expanded at a time
- [ ] Expanded card has "View Full Preview" and "Collapse" buttons

### Search and Filtering
- [ ] Text search filters feed by series name (case-insensitive)
- [ ] Global category filter persists across all pages
- [ ] Category filter and expanded card are encoded in URL query params
- [ ] Deep link with `?series_id=X` auto-expands the correct card

### Backward Compatibility
- [ ] Calendar page ("Browse All") still functions
- [ ] Race Preview page still functions and accepts `?series_id=X&category=Y`
- [ ] Series Detail page still functions
- [ ] Race Detail page still functions
- [ ] Dashboard page still functions
- [ ] All existing pytest tests pass
- [ ] `ruff check .` passes

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Feed query is slow with many series** | Medium | Medium | Cache with `@st.cache_data(ttl=300)`. The query preloads predictions and narratives per series, which involves multiple DB queries per series. If >50 series, this could take 2-3 seconds. Pagination (20 items per page) bounds the visible set. If still slow, defer narrative/prediction loading to expansion time. |
| **`st.expander` doesn't support programmatic open/close** | Low | Medium | Streamlit 1.28+ supports the `expanded` parameter on `st.expander`. If the deployed version is older, fall back to `st.container(border=True)` with session-state-driven conditional rendering. |
| **Elevation sparkline looks bad at small sizes** | Medium | Low | If `st.area_chart(height=60)` doesn't look good, fall back to a tiny inline SVG polyline (similar to the existing finish-type SVG icons in `components.py`). The data is just a list of ~30 floats. |
| **Global category filter breaks existing pages** | Low | Medium | Existing pages already have their own category selectors. The global filter only provides a *default* -- each page's local selector takes precedence. No existing behavior is overridden. |
| **Narrative truncation cuts mid-sentence** | Low | Low | Split on `. ` (period + space) and take first 2 sentences. If the narrative has no period, show the whole thing. |
| **Feed cards are too tall, causing excessive scrolling** | Medium | Medium | Design the collapsed card to be compact: single row for name+date+badges, second row for narrative snippet. Target ~120px per collapsed card. The 3-column grid from Calendar is intentionally abandoned for a 1-column feed because the cards carry more information. |
| **Scope creep from expanded card content** | Medium | High | The expanded card reuses existing components (`render_interactive_course_profile`, contender list from `predict_contenders`). No new data visualization is built. If a component doesn't render cleanly inside an expander, omit it rather than building a custom alternative. |

---

## Security

- **No new external API calls.** This sprint reorganizes existing data; all race/course/prediction data is already in the SQLite database.
- **No PII concerns.** Rider names and points are already public data from road-results.com.
- **No new user input surfaces.** The search bar accepts text that is used in a SQLAlchemy `LIKE` clause via parameterized query (`.filter(RaceSeries.display_name.ilike(f"%{search}%"))`). No raw SQL interpolation.
- **Query params are sanitized.** `series_id` and `category` from `st.query_params` are validated (integer parse, membership check) before use, following the existing pattern in `race_preview.py`.

---

## Dependencies

**Existing Python packages (no changes):**
- `streamlit` -- UI framework (already the core dependency)
- `sqlalchemy` -- ORM (already used throughout)
- `pandas` -- DataFrames for queries (already used)
- `plotly` -- Charts (already used for course profiles)

**New Python packages: None.**

**External services: None.** This sprint is entirely UI reorganization over existing data.

---

## Open Questions

1. **Single-column feed vs. two-column layout?** The draft proposes a single-column feed (each card spans the full width). An alternative is a two-column layout where the left column is the feed list and the right column shows the expanded card's detail. This is more like a master-detail pattern and may feel more natural for desktop users. The tradeoff: Streamlit's `st.columns` can do this, but the detail panel would need to rerun on every card click, and managing scroll position in the list column is not straightforward. Recommendation: start with single-column, evaluate two-column if card expansion feels clunky.

2. **Should the feed replace the Calendar page entirely, or coexist?** The draft keeps both. An alternative is to remove the Calendar page and put a "grid view" toggle on the feed. This is cleaner but risks losing users who prefer the tile grid. Recommendation: ship with both, gather feedback, remove Calendar in a future sprint if the feed is clearly better.

3. **How many sentences of narrative on the collapsed card?** The draft says 2. One sentence might be enough and would keep cards more compact. Need to test with real data to see which length feels right.

4. **Should the elevation sparkline be interactive (clickable to expand)?** Probably not -- it's a visual hint, not a tool. The full interactive course profile is available in the expanded card. Keep the sparkline static.

5. **How should the "This Weekend" toggle interact with search?** If the user has "This Weekend" toggled on and searches for "Banana Belt" (which is next month), should the search override the date filter? Recommendation: yes, search should clear the weekend filter. Show a note: "Showing all dates because you searched for 'Banana Belt'."

6. **Performance: should `get_feed_items()` preload all data or lazy-load on expansion?** The draft preloads everything for the visible page (20 items). An alternative is to preload only card-summary data (name, date, finish type, terrain) and fetch narrative/prediction/contenders on expansion. This is faster for initial load but adds latency to expansion. Recommendation: preload everything with caching. If it's too slow, move to lazy-load in Phase 4.

7. **What should the "Where does the race get hard?" sentence look like when there are no climbs?** For flat courses, omit the sentence entirely. For rolling courses with minor climbs that don't meet the climb detection threshold, say "No major climbs detected -- expect the pace to be sustained throughout." This keeps the field populated without overpromising.
