# Sprint 010: Unified Race Feed & Forward-Looking UX

## Overview

Sprint 010 replaces the current multi-page navigation model with a single unified race feed as the primary entry point. Today, a racer must navigate between 5 separate Streamlit pages (Calendar, Series Detail, Race Detail, Race Preview, Dashboard) to go from "what races exist?" to "what should I expect?" This sprint collapses that journey into a single scrollable feed where upcoming races appear at the top with inline historical intelligence -- predicted finish type, terrain badge, narrative summary, drop rate, course profile sparkline, and a plain-English description of what kind of racer does well -- all visible without clicking through to a detail page.

The architectural approach is **additive, not destructive**: a new `feed.py` page becomes the default landing page, while the existing Calendar page is preserved as "Browse All" for power users. The existing Series Detail, Race Detail, Race Preview, and Dashboard pages remain functional as deep-link targets. If the feed ships incomplete at any point, the old pages still work. Cards expand inline using native `st.expander` widgets to reveal full preview content -- course profile, narrative, contenders, historical editions -- without leaving the page. A persistent global category filter, text search, and "Racing Soon" section (next 7 days) complete the unified experience.

**What this sprint does NOT do:** It does not build new data pipelines, prediction algorithms, or external API integrations. All underlying data (predictions, narratives, stats, course profiles, contenders) already exists in the database and is served by `queries.py` and `predictions.py`. This sprint reorganizes how that data is presented. It does not remove existing pages.

**Duration:** 2-3 weeks
**Prerequisite:** Sprint 009 complete (road-results GraphQL calendar, predictor.aspx startlists)

---

## Use Cases

### In Scope (20 "Good" use cases, grouped by phase)

**Phase 1 -- Feed Foundation (UC-01, UC-03, UC-06, UC-44, UC-48, UC-49)**
- UC-01: See upcoming races with historical context inline
- UC-03: Race cards sort by date with upcoming first
- UC-06: "No upcoming edition" badge on dormant series
- UC-44: Single entry point, not five pages
- UC-48: "Racing Soon" section showing next 7 days
- UC-49: Search for a race by name

**Phase 2 -- Rich Cards & Content (UC-02, UC-04, UC-05, UC-07, UC-08, UC-09, UC-10, UC-16, UC-29, UC-31)**
- UC-02: Upcoming race cards link to preview, not results
- UC-04: Collapse historical editions under the upcoming race
- UC-05: Series-first view where upcoming edition is the hero
- UC-07: One-tap from feed to registration
- UC-08: "What to Expect" summary visible without clicking into detail
- UC-09: Finish type explained in plain language, not jargon
- UC-10: "What kind of racer does well here?" (lookup table)
- UC-16: Display typical race duration
- UC-29: Course profile thumbnail visible on the race card
- UC-31: "Where does the race get hard?" one-liner (from existing climb data)

**Phase 3 -- Global Filters, Deep Linking & Persistence (UC-45, UC-46, UC-47, UC-50)**
- UC-45: Category filter is persistent and global
- UC-46: Race card expands in place instead of navigating away
- UC-47: Deep link to a race preview from external sources
- UC-50: Remember where I left off (URL-based state persistence)

### Deferred to Future Sprint

| Use Case | Reason for Deferral |
|----------|-------------------|
| UC-20: Finish type/racer type explainer | Educational content that can be added as a static reference section later. |
| UC-25: Field strength indicator | Needs an algorithm definition (aggregate points vs. historical averages). |
| UC-26: Contender rider types | Requires rider-type inference from historical results -- a new analysis feature. |
| UC-28: Team representation | Requires team-level aggregation queries that don't exist yet. |
| UC-32: Course-finish correlation explanation | Educational content, deferred alongside UC-20. |
| UC-33: Course compared to known race | Requires a course similarity algorithm. Significant new logic. |
| UC-37: Side-by-side comparison | Requires a comparison UI layout -- a feature sprint on its own. |
| UC-38: Season calendar view | A calendar-style visualization is a distinct custom component. |

---

## Architecture

### Page Model Changes

A new `feed.py` page becomes the default. The existing Calendar page is kept as "Browse All."

```
Current:                          Sprint 010:
Calendar (landing, default)       Race Feed (feed.py, default)
  -> Series Detail                Browse All (calendar.py, secondary)
  -> Race Detail                  Series Detail (secondary)
  -> Race Preview                 Race Detail (secondary)
  -> Dashboard                    Race Preview (deep-link target)
                                  Dashboard (secondary)
```

In `app.py`:
```python
feed_page = st.Page("pages/feed.py", title="Race Feed", icon="\U0001f3c1", default=True)
calendar_page = st.Page("pages/calendar.py", title="Browse All", icon="\U0001f4c5")
```

### Session State Architecture

```python
# Initialized in app.py, seeded from query params on first load:
st.session_state.setdefault("global_category", st.query_params.get("category"))
st.session_state.setdefault("search_query", st.query_params.get("q", ""))
st.session_state.setdefault("feed_page_size", 20)  # pagination
```

Query params for deep linking (UC-47):
- `?series_id=42` -- opens feed with that series card at the top (isolation pattern)
- `?category=Men+Cat+4/5` -- sets global category
- `?q=banana+belt` -- pre-fills search

On first load, `app.py` reads query params and seeds session state. Subsequent interactions update session state, which is synced back to query params for URL-based persistence (UC-50).

### Feed Data Pipeline

A new query function `get_feed_items()` returns a unified list of feed items sorted by relevance:

```python
def get_feed_items(
    session: Session,
    *,
    category: Optional[str] = None,
    search_query: Optional[str] = None,
    racing_soon_only: bool = False,
) -> list[dict]:
    """Return feed items: one per series, enriched with preview data.

    Each item contains:
    - series metadata (id, display_name, location, state, edition_count)
    - upcoming edition info (date, registration_url) or None
    - predicted finish type + confidence
    - narrative snippet (first 2 sentences)
    - drop rate summary (label + percentage)
    - course type + distance + total gain
    - racer_type_description (UC-10, from lookup table)
    - climb_highlight (UC-31, from climbs_json)
    - duration_minutes (UC-16, from race_time_seconds)
    - elevation_sparkline_points (downsampled to ~50 points)
    - is_upcoming: bool
    - is_racing_soon: bool (date within next 7 days)
    - editions_summary: list[dict] (year, finish_type per edition)
    """
```

**Performance strategy:** Per-series data (prediction, stats, narrative) is cached at the `(series_id, category)` level using `@st.cache_data(ttl=300)`. The outer `get_feed_items()` iterates over series and calls cached helpers, so repeated filter/search changes only re-query the series list, not the per-series computations.

Sort order:
1. "Racing Soon" upcoming races (by date ascending)
2. Other upcoming races (by date ascending)
3. Series with no upcoming edition (by most recent edition date descending)

### Inline Expansion Pattern (UC-46)

Native `st.expander` with multi-open allowed:

```python
for item in feed_items:
    with st.expander(card_label(item)):
        render_feed_card_summary(item)   # badges, narrative snippet, sparkline
        render_feed_card_detail(item)     # full narrative, course profile, contenders
```

Multi-open allows ad-hoc comparison between cards. No session state tracking of open/close -- Streamlit manages expander state natively.

**Lazy loading of heavy components:** The interactive course profile (Leaflet + Plotly iframe from Sprint 008) renders eagerly inside expanders, which could be slow with 20+ cards. Mitigation: only render the interactive map for the first 3 expanded cards; show the SVG sparkline + "View Full Preview" link for the rest. This bounds DOM weight while keeping the experience fast.

### Deep Link Isolation Pattern

When `?series_id=N` is in the URL, instead of scrolling to that card in the full feed, the feed shows only that series card (pre-expanded) with a "Show all races" button. This avoids Streamlit's scroll-position limitations and gives a clean shareable experience.

### Elevation Sparkline (UC-29)

Pure Python SVG generation. ~200 bytes per card, no JS overhead:

```python
def render_elevation_sparkline(profile_points: list[dict], width: int = 200, height: int = 40):
    """Render a tiny elevation sparkline as inline SVG via st.markdown(unsafe_allow_html=True)."""
    # Sample to ~50 points
    # Generate SVG <path> with viewBox scaling
    # Fill + stroke in green
```

### Plain-English Finish Types (UC-09)

Reuse the existing `FINISH_TYPE_TOOLTIPS` dict in `queries.py` which already contains full English sentences. The feed card shows the tooltip text as the primary description with the short label ("Bunch Sprint") as a caption. No duplicate dict needed.

### "What Kind of Racer Does Well Here?" (UC-10)

A static lookup table mapping `(course_type, finish_type)` to a sentence:

```python
RACER_TYPE_DESCRIPTIONS = {
    ("flat", "bunch_sprint"): "Sprinters and pack riders thrive here.",
    ("flat", "breakaway"): "Strong riders who can sustain a solo effort have an edge.",
    ("rolling", "reduced_sprint"): "Punchy riders who can handle repeated surges do well.",
    ("hilly", "gc_selective"): "Pure climbers dominate this race.",
    # ~12 combinations covering realistic pairings
}
```

If the combination isn't in the table, the sentence is omitted. No new algorithm needed.

### "Where Does the Race Get Hard?" (UC-31)

Extracted from the existing `climbs_json` data on `Course`:

```python
def climb_highlight(climbs: list[dict]) -> Optional[str]:
    """Return a one-liner about the hardest or final climb."""
    if not climbs:
        return None
    # Find the hardest climb (highest avg_grade) or the last climb
    # Format: "The race gets hard at km 18 -- a 1.8km steep climb averaging 6.0%"
```

This reuses climb data already computed in Sprint 008. No new detection or external calls.

### Typical Race Duration (UC-16)

A new function using raw `race_time_seconds` from historical results:

```python
def calculate_typical_duration(session, series_id, category=None) -> Optional[dict]:
    """Calculate typical race duration from historical Results.

    Returns: {
        "winner_duration_minutes": float,
        "field_duration_minutes": float,
        "edition_count": int,
    }
    """
    # Same edition-iteration pattern as calculate_typical_speeds()
    # Uses race_time_seconds directly (no speed/distance derivation)
    # Suppress for TTs
```

### Persistent Category Filter (UC-45)

```python
def render_global_category_filter(session) -> Optional[str]:
    """Render a persistent category filter in the sidebar.
    Reads/writes st.session_state.global_category.
    Syncs to st.query_params['category'] for URL persistence.
    """
    categories = _cached_categories(session)
    current = st.session_state.get("global_category")
    chosen = st.sidebar.selectbox(
        "Your Category",
        options=[None] + categories,
        index=...,
        format_func=lambda x: "All Categories" if x is None else x,
        key="global_category_selector",
    )
    if chosen != current:
        st.session_state.global_category = chosen
        # Sync to query params for UC-50
        if chosen:
            st.query_params["category"] = chosen
        elif "category" in st.query_params:
            del st.query_params["category"]
    return chosen
```

All pages (Race Preview, Series Detail, Race Detail) read from `st.session_state.get("global_category")` as their default category.

---

## Implementation

### Phase 1: Feed Foundation & Query Layer (30% of effort)

**Goal:** New feed page with feed query, "Racing Soon" section, search, pagination, and dormant series handling.

**Files:**
- `raceanalyzer/ui/pages/feed.py` -- CREATE: New unified feed page
- `raceanalyzer/queries.py` -- MODIFY: Add `get_feed_items()`, `search_series()`, per-series caching helpers
- `raceanalyzer/ui/app.py` -- MODIFY: Add feed page as default, keep calendar as "Browse All"
- `tests/test_queries.py` -- MODIFY: Tests for `get_feed_items()` and `search_series()`

**Tasks:**
- [ ] Create `get_feed_items()` in `queries.py` with per-series `@st.cache_data(ttl=300)` caching
- [ ] Implement "Racing Soon" date filter: `today <= race.date <= today + 7 days`
- [ ] Implement search: case-insensitive `ilike` on `display_name`, escaping `%` and `_` wildcards
- [ ] Create `feed.py` with: search bar, "Racing Soon" section, main feed list, pagination ("Show more" button, 20 items per page)
- [ ] Sort: racing-soon upcoming first, then other upcoming by date, then historical by recency
- [ ] "No upcoming edition" series appear with reduced opacity (`st.markdown` with inline CSS `opacity: 0.6`)
- [ ] Add feed page to `app.py` as `default=True`; rename calendar to "Browse All"
- [ ] Deep-link isolation: if `?series_id=N` in URL, show only that series card (expanded) with "Show all races" button
- [ ] Tests: upcoming-first ordering, search filtering, racing-soon filtering, empty database returns empty list, search wildcard escaping

### Phase 2: Rich Card Content (30% of effort)

**Goal:** Feed cards show narrative snippets, plain-English finish types, racer type descriptions, climb highlights, elevation sparklines, duration estimates, registration links, and historical editions.

**Files:**
- `raceanalyzer/ui/components.py` -- MODIFY: Add `render_feed_card()`, `render_elevation_sparkline()`, `render_dormant_badge()`
- `raceanalyzer/queries.py` -- MODIFY: Add sparkline downsampling to `get_feed_items()`, add `climb_highlight()`, add `finish_type_plain_english()`
- `raceanalyzer/predictions.py` -- MODIFY: Add `racer_type_description()`, `calculate_typical_duration()`
- `raceanalyzer/ui/pages/feed.py` -- MODIFY: Wire up rich cards
- `tests/test_predictions.py` -- MODIFY: Tests for `racer_type_description()`, `calculate_typical_duration()`
- `tests/test_queries.py` -- MODIFY: Tests for sparkline downsampling, `climb_highlight()`, `finish_type_plain_english()`

**`render_feed_card()` structure:**
```python
def render_feed_card(item: dict):
    # Row 1: Badges (plain-English finish type, terrain, drop rate)
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        if item.get("predicted_finish_type"):
            plain = finish_type_plain_english(item["predicted_finish_type"])
            st.write(plain)
            st.caption(finish_type_display_name(item["predicted_finish_type"]))
    with col2:
        if item.get("course_type"):
            render_terrain_badge(item["course_type"])
    with col3:
        if item.get("drop_rate_pct") is not None:
            st.caption(f"{item['drop_rate_pct']}% drop rate")

    # Row 2: Narrative snippet + sparkline
    text_col, spark_col = st.columns([3, 1])
    with text_col:
        if item.get("narrative_snippet"):
            st.write(item["narrative_snippet"])
        if item.get("racer_type_description"):
            st.caption(item["racer_type_description"])
    with spark_col:
        if item.get("elevation_sparkline_points"):
            render_elevation_sparkline(item["elevation_sparkline_points"])

    # Row 3: Duration + climb highlight
    if item.get("duration_minutes") or item.get("climb_highlight"):
        if item.get("duration_minutes"):
            winner_m = item["duration_minutes"]["winner_duration_minutes"]
            hours, mins = divmod(int(winner_m), 60)
            st.caption(f"Typical duration: ~{hours}h {mins:02d}m")
        if item.get("climb_highlight"):
            st.caption(item["climb_highlight"])

    # Row 4: Registration + full preview link
    if item.get("is_upcoming") and item.get("registration_url"):
        st.markdown(f"[Register]({item['registration_url']})")

    # Row 5: Historical editions (bulleted list, not nested expander)
    if item.get("editions_summary") and len(item["editions_summary"]) > 1:
        with st.popover(f"{len(item['editions_summary'])} previous editions"):
            for ed in item["editions_summary"]:
                st.write(f"- {ed['year']}: {ed['finish_type_display']}")
```

**Tasks:**
- [ ] Implement `finish_type_plain_english()` reusing `FINISH_TYPE_TOOLTIPS`
- [ ] Implement `racer_type_description(course_type, finish_type)` lookup table (~12 entries)
- [ ] Implement `climb_highlight(climbs)` -- one-liner about hardest or final climb
- [ ] Implement `calculate_typical_duration()` from `race_time_seconds`
- [ ] Implement `render_elevation_sparkline()` as inline SVG
- [ ] Validate SVG rendering early: test `st.markdown(svg, unsafe_allow_html=True)` works in current Streamlit version
- [ ] Add elevation sparkline downsampling in `get_feed_items()` (~50 points from `profile_json`)
- [ ] Narrative snippet: split `generate_narrative()` output on `. ` and take first 2 sentences
- [ ] Historical editions: render as bulleted list in `st.popover` (avoids nested expander bugs)
- [ ] Registration link directly on card when `registration_url` available (UC-07)
- [ ] Tests: `racer_type_description` returns expected strings for known combinations and None for unknown; `calculate_typical_duration` with fixture data; `climb_highlight` with and without climbs; sparkline downsampling produces correct point count; `finish_type_plain_english` returns tooltip text

### Phase 3: Global Category Filter, Deep Linking & State Persistence (25% of effort)

**Goal:** Category filter persists across all views. Deep links work. URL encodes state for bookmark/refresh persistence.

**Files:**
- `raceanalyzer/ui/components.py` -- MODIFY: Add `render_global_category_filter()`
- `raceanalyzer/ui/app.py` -- MODIFY: Initialize global session state from query params
- `raceanalyzer/ui/pages/feed.py` -- MODIFY: Read global category, sync state to URL
- `raceanalyzer/ui/pages/race_preview.py` -- MODIFY: Read global category from session state
- `raceanalyzer/ui/pages/series_detail.py` -- MODIFY: Read global category from session state
- `raceanalyzer/ui/pages/race_detail.py` -- MODIFY: Read global category from session state

**Tasks:**
- [ ] Add global category selector in sidebar via `render_global_category_filter()`
- [ ] Sync `global_category` to `st.query_params["category"]` on change
- [ ] Modify Race Preview, Series Detail, and Race Detail to read `st.session_state.get("global_category")` as default category (page-local selector takes precedence)
- [ ] Deep-link handling in `feed.py`: `?series_id=N` isolates that card; `?category=Y` sets filter; `?q=X` pre-fills search
- [ ] State persistence (UC-50): sync search query and category to query params so bookmarks and refreshes restore state
- [ ] Handle empty category: "No races found for [Category]. Try 'All Categories'." message
- [ ] Tests: global category persists across simulated page transitions; deep-link isolation shows correct series; URL params restore state

### Phase 4: Edge Cases, Regression & Polish (15% of effort)

**Goal:** Handle all edge cases, verify backward compatibility, performance validation.

**Files:**
- `raceanalyzer/ui/pages/feed.py` -- MODIFY: Empty states, performance tuning
- `raceanalyzer/ui/pages/calendar.py` -- MODIFY: Minor (no longer default, still functional)
- `tests/test_queries.py` -- MODIFY: Edge case tests

**Tasks:**
- [ ] Empty state: no races in database -- friendly message with CLI hint
- [ ] Empty state: no upcoming races -- "No upcoming races. Showing all series by most recent edition."
- [ ] Empty state: search returns nothing -- "No races matching 'X'" with clear-search button
- [ ] Empty state: series with no course data -- card renders without sparkline/terrain/duration
- [ ] Empty state: series with no historical data -- "New event -- no historical data yet"
- [ ] Empty state: category filter yields nothing -- message suggesting broadening filter
- [ ] Handle stale "upcoming" races: feed query filters on `race.date >= today`, not just `is_upcoming` flag
- [ ] Performance: validate feed loads in under 3 seconds with 50+ series (manual test)
- [ ] Verify Calendar ("Browse All") page still functions
- [ ] Verify Race Preview page still functions standalone
- [ ] Verify Series Detail, Race Detail, Dashboard pages still function
- [ ] Run `ruff check .` on all new/modified files
- [ ] Run `pytest tests/ -v` and verify all existing tests pass
- [ ] Tests: feed renders with zero upcoming races; feed renders with series missing course/prediction data; pagination works

---

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/ui/pages/feed.py` | CREATE | New unified race feed page -- the primary entry point |
| `raceanalyzer/ui/app.py` | MODIFY | Add feed page as default, keep calendar as "Browse All", seed global session state |
| `raceanalyzer/queries.py` | MODIFY | Add `get_feed_items()`, `search_series()`, `finish_type_plain_english()`, `climb_highlight()`, sparkline downsampling |
| `raceanalyzer/predictions.py` | MODIFY | Add `racer_type_description()`, `calculate_typical_duration()` |
| `raceanalyzer/ui/components.py` | MODIFY | Add `render_feed_card()`, `render_elevation_sparkline()`, `render_global_category_filter()`, `render_dormant_badge()` |
| `raceanalyzer/ui/pages/race_preview.py` | MODIFY | Read global category from session state |
| `raceanalyzer/ui/pages/series_detail.py` | MODIFY | Read global category from session state |
| `raceanalyzer/ui/pages/race_detail.py` | MODIFY | Read global category from session state |
| `raceanalyzer/ui/pages/calendar.py` | MODIFY | No longer default; still functional |
| `tests/test_queries.py` | MODIFY | Tests for `get_feed_items()`, `search_series()`, sparkline, `climb_highlight()`, `finish_type_plain_english()` |
| `tests/test_predictions.py` | MODIFY | Tests for `racer_type_description()`, `calculate_typical_duration()` |

No database schema changes. No new Python dependencies.

---

## Definition of Done

### Feed Experience
- [ ] Opening the app lands on the unified feed page (`feed.py`), not the old Calendar
- [ ] Upcoming races appear at the top, sorted by date ascending (soonest first)
- [ ] Series without upcoming editions appear below, sorted by most recent edition descending
- [ ] "Racing Soon" section shows races within the next 7 days when any exist
- [ ] Text search filters the feed by series name (case-insensitive, wildcards escaped)
- [ ] Pagination: first 20 items shown, "Show more" loads next 20

### Rich Cards
- [ ] Each card displays inline: plain-English finish type, terrain badge, drop rate, narrative snippet (1-2 sentences), registration link (if upcoming)
- [ ] Each card shows a "What kind of racer does well here?" sentence when course type and finish type data exist
- [ ] Each card shows a "Where does it get hard?" climb one-liner when climb data exists
- [ ] Each card shows an elevation sparkline (SVG) when course profile data exists
- [ ] Each card shows estimated race duration when sufficient timing data exists
- [ ] Historical editions accessible via popover (year + finish type per edition)
- [ ] Dormant series (no upcoming edition) appear visually dimmed with "No upcoming edition" indicator

### Inline Expansion
- [ ] Clicking an `st.expander` header reveals full preview content (narrative, course profile, contenders) without leaving the feed
- [ ] Multiple cards can be open simultaneously
- [ ] Expanded card has "View Full Preview" button linking to Race Preview page

### Search, Filtering & Deep Linking
- [ ] Global category filter in sidebar persists across page navigation
- [ ] Category and search state are encoded in URL query params (bookmarkable)
- [ ] Deep link with `?series_id=N` shows only that series card (expanded) with "Show all" button
- [ ] Deep link with `?category=X` sets the global category filter

### Backward Compatibility
- [ ] Calendar ("Browse All") page still functions
- [ ] Race Preview page still functions and accepts `?series_id=X&category=Y`
- [ ] Series Detail, Race Detail, and Dashboard pages still function
- [ ] All existing `pytest` tests pass
- [ ] `ruff check .` passes
- [ ] No existing tests are deleted or skipped

### Performance
- [ ] Feed loads in under 3 seconds with 50+ series (manual validation)
- [ ] Per-series data is cached with `@st.cache_data(ttl=300)`

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Feed query performance (N+1)**: `get_feed_items()` calls prediction/stats/narrative per series. 50+ series = 100-200+ DB queries. | Medium | High | Cache per-series summaries at `(series_id, category)` granularity with `@st.cache_data(ttl=300)`. Pagination bounds visible items to 20. |
| **`st.expander` eager rendering**: Expander contents render in DOM even when collapsed. 20+ cards with heavy components = slow page. | Medium | High | Only render the interactive course map for the first 3 expanded cards. Others get sparkline + "View Full Preview" link. Validate early in Phase 1. |
| **SVG sparkline rendering**: `st.markdown(svg, unsafe_allow_html=True)` may sanitize or strip SVG. | Low | Medium | Validate in Phase 2 as an early task. Fallback: `st.image()` with a PIL-generated PNG. |
| **Global category filter rerun loop**: Changing selectbox triggers rerun, which re-renders selectbox, which could trigger another rerun. | Medium | Medium | Use `key` parameter on selectbox. Compare old and new values before any state update. Only sync to query params when value actually changes. |
| **Narrative snippet cuts mid-sentence**: Splitting on `. ` could fail on abbreviations ("e.g.") or sentences without spaces after periods. | Low | Low | Use a sentence-split helper. If narrative has no `. `, show the whole thing. Cap at 200 characters with `...` as ultimate fallback. |
| **Nested expander bugs**: Historical editions were planned as nested `st.expander`. | Medium | Medium | Use `st.popover` instead of nested expander. Tested in Streamlit 1.28+. |
| **`st.cache_data` serialization failure**: Return values with `datetime` or non-serializable types will break caching. | Low | Medium | Ensure all cached return values are plain dicts with JSON-serializable types (strings, ints, floats, lists, None). |
| **Scope creep from expanded card content**: Full preview content inside expanders may not render cleanly. | Medium | Medium | If a component doesn't work inside an expander, omit it and link to Race Preview page instead. |
| **Search wildcard injection**: `%` and `_` in search input treated as SQL LIKE wildcards. | Low | Low | Escape `%` and `_` before passing to `ilike()`. |
| **Stale "upcoming" races**: Races marked `is_upcoming=True` but with past dates. | Medium | Low | Feed query filters on `race.date >= today` in addition to `is_upcoming` flag. |

---

## Security

- **No new external API calls or network requests.**
- **No user authentication or personal data storage.**
- **Search input**: Passed through SQLAlchemy's parameterized `ilike()` query with `%` and `_` escaped. No raw SQL interpolation.
- **Query params**: `series_id` validated as integer, `category` checked against known categories before use.
- **Inline SVG**: Generated from hardcoded numeric data (elevation points). No user-controlled content interpolated into markup.
- **No PII concerns.** Rider names and points are already public data from road-results.com.

---

## Dependencies

**Existing Python packages (no changes):**
- `streamlit`, `sqlalchemy`, `pandas`, `plotly`, `folium`, `click`

**New Python packages: None.**

**External services: None.** This sprint is entirely UI reorganization over existing data.

**Sprint 009 must be complete.** The feed relies on `Race.is_upcoming`, `Race.registration_url`, and `Startlist` data.

---

## Open Questions

1. **How many sentences should the narrative snippet show on the collapsed card?** Recommendation: 2 sentences (course + history). If real data shows this is too long, trim to 1. Cap at 200 characters with `...`.

2. **Should the feed eventually replace the Calendar page entirely?** Recommendation: ship with both for Sprint 010, gather feedback, remove Calendar in a future sprint if the feed is clearly better.

3. **Should "Racing Soon" disappear when there are no races in the next 7 days, or show an empty state?** Recommendation: hide the section entirely. Show a subtle note at the top: "No races in the next 7 days."

4. **How should "Racing Soon" interact with search?** Recommendation: search should override the date filter. If searching for "Banana Belt" (which is next month), show it regardless of the Racing Soon section. Show a note: "Showing all dates for 'Banana Belt'."

5. **What does `racer_type_description()` show for "mixed" or "unknown" finish types?** Recommendation: omit the sentence entirely. Only show it for the ~12 well-defined (course_type, finish_type) combinations.

6. **What about series with multiple upcoming races (e.g., March and April editions)?** Recommendation: show the soonest upcoming date as the hero. Mention the next date in the historical editions popover.

7. **What is the secondary sort when two series have upcoming races on the same date?** Recommendation: alphabetical by display_name.
