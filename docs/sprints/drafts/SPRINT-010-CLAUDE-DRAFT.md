# Sprint 010: Unified Race Feed & Forward-Looking UX

## Overview

Sprint 010 replaces the current multi-page navigation model with a single unified race feed as the primary entry point. Today, a racer must navigate between 5 separate Streamlit pages (Calendar, Series Detail, Race Detail, Race Preview, Dashboard) to go from "what races exist?" to "what should I expect?" This sprint collapses that journey into a single scrollable feed where upcoming races appear at the top with inline historical intelligence -- predicted finish type, terrain badge, narrative summary, drop rate, and course profile thumbnail -- all visible without clicking through to a detail page.

The architectural thesis: the feed IS the app. Race cards expand inline using `st.expander` and session state to reveal full preview content (narrative, course profile, contenders). The Race Preview page is retained as a deep-link target but is no longer the primary way to access preview data. A persistent global category filter (stored in `st.session_state` and `st.query_params`) ensures the racer sets their category once and sees relevant data everywhere. A "This Weekend" section at the top of the feed surfaces imminent races. Text search lets racers find races by name.

**What this sprint does NOT do:** It does not build new data pipelines, prediction algorithms, or external API integrations. All underlying data (predictions, narratives, stats, course profiles, contenders) already exists in the database and is served by `queries.py` and `predictions.py`. This sprint reorganizes how that data is presented. It also does not remove the existing Series Detail, Race Detail, or Dashboard pages -- they remain accessible for power users but are no longer required stops on the primary journey.

**Duration:** 2-3 weeks
**Prerequisite:** Sprint 009 complete (road-results GraphQL calendar, predictor.aspx startlists)

---

## Use Cases

### In Scope (18 "Good" use cases, grouped by phase)

**Phase 1 -- Unified Feed Foundation (UC-01, UC-03, UC-44, UC-48, UC-49)**
- UC-01: See upcoming races with historical context inline
- UC-03: Race cards sort by date with upcoming first
- UC-44: Single entry point, not five pages
- UC-48: "This Weekend" quick view
- UC-49: Search for a race by name

**Phase 2 -- Rich Race Cards (UC-02, UC-04, UC-05, UC-06, UC-07, UC-08, UC-29)**
- UC-02: Upcoming race cards link to preview, not results
- UC-04: Collapse historical editions under the upcoming race
- UC-05: Series-first view where upcoming edition is the hero
- UC-06: "No upcoming edition" badge on dormant series
- UC-07: One-tap from feed to registration
- UC-08: "What to Expect" summary visible without clicking into detail
- UC-29: Course profile thumbnail visible on the race card

**Phase 3 -- Inline Expansion & Global Filters (UC-45, UC-46, UC-47, UC-50)**
- UC-45: Category filter is persistent and global
- UC-46: Race card expands in place instead of navigating away
- UC-47: Deep link to a race preview from external sources
- UC-50: Remember where I left off

**Phase 4 -- Content Enrichment (UC-09, UC-16)**
- UC-09: Finish type explained in plain language, not jargon
- UC-16: Display typical race duration

### Deferred to Future Sprint

The following "Good" use cases are cut from this sprint to keep scope realistic:

| Use Case | Reason for Deferral |
|----------|-------------------|
| UC-10: "What kind of racer does well here?" | Requires new derivation logic mapping course profiles and finish types to rider archetypes. Better as a follow-up once the feed is stable. |
| UC-20: Finish type/racer type explainer | Educational content that can be added as a static reference section later without architectural changes. |
| UC-25: Field strength indicator | Needs an algorithm definition (aggregate points vs. historical averages). Deferred until we have a clear metric. |
| UC-26: Contender rider types | Requires rider-type inference from historical results -- a new analysis feature, not a UX reshuffling. |
| UC-28: Team representation | Useful but requires team-level aggregation queries that don't exist yet. |
| UC-31: "Where does the race get hard?" | The narrative already includes climb sentences. Surfacing the right sentence inline on the card is a Phase 4 polish item. |
| UC-32: Course-finish correlation explanation | Educational content, deferred alongside UC-20. |
| UC-33: Course compared to known race | Requires a course similarity algorithm (DTW or simpler). Significant new logic. |
| UC-37: Side-by-side comparison | Requires a comparison UI layout -- a feature sprint on its own. |
| UC-38: Season calendar view | A calendar-style visualization (timeline or grid by month) is a distinct component. Deferred. |

---

## Architecture

### Page Model Changes

The current 5-page `st.navigation()` structure in `app.py` remains, but the Calendar page is renamed "Race Feed" and becomes a substantially richer single-page experience. The navigation sidebar is simplified: "Race Feed" is the hero; other pages become secondary.

```
Current:                          Sprint 010:
Calendar (landing)                Race Feed (landing, default)
  -> Series Detail                  [inline expansion replaces navigation]
  -> Race Detail                  Series Detail (secondary, linked)
  -> Race Preview                 Race Detail (secondary, linked)
  -> Dashboard                    Race Preview (deep-link target)
                                  Dashboard (secondary)
```

### Session State Architecture

Streamlit reruns the entire script on every interaction. The feed's state must be managed carefully to avoid losing context on rerun.

```python
# New session state keys (all set in app.py init block):
st.session_state.setdefault("global_category", None)     # UC-45: persistent category
st.session_state.setdefault("search_query", "")           # UC-49: search text
st.session_state.setdefault("expanded_series_id", None)   # UC-46: which card is expanded
st.session_state.setdefault("feed_scroll_position", 0)    # UC-50: pagination offset
st.session_state.setdefault("show_this_weekend", True)     # UC-48: weekend filter state
```

Query params for deep linking (UC-47):
- `?series_id=42` -- opens feed with that series expanded
- `?category=Men+Cat+4/5` -- sets global category
- `?q=banana+belt` -- pre-fills search

On first load, `app.py` reads query params and seeds session state. Subsequent interactions update session state, which is the source of truth.

### Feed Data Pipeline

A new query function `get_feed_items()` replaces the current split between `get_series_tiles()` and the upcoming-races loop in `calendar.py`. It returns a unified list of feed items sorted by relevance:

```python
def get_feed_items(
    session: Session,
    *,
    category: Optional[str] = None,
    search_query: Optional[str] = None,
    this_weekend_only: bool = False,
) -> list[dict]:
    """Return feed items: one per series, enriched with preview data.

    Each item contains:
    - series metadata (name, location, state, edition count)
    - upcoming edition info (date, registration_url) or None
    - predicted finish type + confidence
    - narrative snippet (first 1-2 sentences)
    - drop rate summary
    - course type + thumbnail flag
    - is_upcoming: bool (for sort priority)
    - is_this_weekend: bool
    """
```

Sort order:
1. "This weekend" upcoming races (by date ascending)
2. Other upcoming races (by date ascending)
3. Series with no upcoming edition (by most recent edition date descending)

### Inline Expansion Pattern (UC-46)

Streamlit does not support true "expand in place" DOM manipulation. The two viable patterns are:

**Option A: `st.expander` (recommended)**
Each race card is rendered inside an `st.expander`. The collapsed state shows the rich card (name, date, badges, narrative snippet, terrain thumbnail). Expanding reveals the full Race Preview content (course profile, full narrative, contenders, stats, registration link). This is native Streamlit, requires no custom JS, and works with keyboard navigation.

**Option B: Session-state conditional rendering**
Track `st.session_state.expanded_series_id`. When a card is clicked, set this value and rerun. The feed re-renders with the selected card showing full detail content and other cards collapsed. Drawback: the page scrolls to the top on rerun unless we use `st.query_params` as an anchor.

**Decision: Use Option A (`st.expander`)** for the primary feed. It is the simplest Streamlit-native pattern, avoids scroll-position issues, and allows multiple cards to be open simultaneously (useful for comparison). The expander label is the race card header; the body contains full preview content rendered by extracting the core rendering logic from `race_preview.py` into reusable component functions.

### Elevation Sparkline Component (UC-29)

The course profile thumbnail is a small inline SVG sparkline rendered from `course.profile_json`. This is a pure Python function that generates an SVG path from the elevation points -- no Plotly or iframe needed. Target size: 200x40px. The function lives in `components.py` and is called during card rendering.

```python
def render_elevation_sparkline(profile_points: list[dict], width: int = 200, height: int = 40):
    """Render a tiny elevation sparkline as inline SVG."""
    # Sample every Nth point to keep SVG small
    # Generate SVG <path> with viewBox scaling
    # Render via st.markdown(svg, unsafe_allow_html=True)
```

### Plain-English Finish Types (UC-09)

The existing `FINISH_TYPE_TOOLTIPS` dict in `queries.py` already contains full English sentences. Sprint 010 promotes these to the default display, with the short label as a subtitle. The rendering change is in `components.py` -- the badge shows the tooltip text as the primary label and the short name in smaller text below.

For the feed card, a truncated version is shown (first clause only, ~40 chars). The full sentence appears in the expanded view.

### Duration Estimate (UC-16)

A new function in `predictions.py` calculates typical race duration from `Result.race_time_seconds` across historical editions:

```python
def calculate_typical_duration(
    session: Session,
    series_id: int,
    category: Optional[str] = None,
) -> Optional[dict]:
    """Calculate typical race duration from historical results.

    Returns: {
        "winner_duration_minutes": float,
        "field_duration_minutes": float,
        "edition_count": int,
    }
    """
```

This uses the same edition-iteration pattern as `calculate_typical_speeds()` but returns time directly rather than deriving speed from distance.

---

## Implementation

### Phase 1: Unified Feed Foundation (35% of effort)

**Goal:** Replace the Calendar page with a unified feed. Upcoming races at top, series-based cards, "This Weekend" section, search bar.

**Files:**
- `raceanalyzer/queries.py` -- Add `get_feed_items()` and `search_series()` functions
- `raceanalyzer/ui/pages/calendar.py` -- Rewrite as the unified feed page (rename conceptually; keep filename for URL stability)
- `raceanalyzer/ui/app.py` -- Update page title to "Race Feed", seed new session state keys
- `raceanalyzer/ui/components.py` -- Add `render_feed_card()` function for the collapsed card view
- `tests/test_queries.py` -- Tests for `get_feed_items()` and `search_series()`

**Implementation details:**

`get_feed_items()` in `queries.py`:
```python
def get_feed_items(session, *, category=None, search_query=None, this_weekend_only=False):
    # 1. Query all series with LEFT JOIN to upcoming races
    # 2. For each series: get prediction, drop rate snippet, course type
    # 3. Generate narrative snippet (first 2 sentences of generate_narrative())
    # 4. Sort: upcoming-this-weekend first, then upcoming-by-date, then historical
    # 5. Apply search filter (LIKE on display_name)
    # 6. Apply category filter (passed through to prediction/stats)
```

`search_series()`:
```python
def search_series(session, query: str, limit: int = 20) -> list[dict]:
    """Search series by name using SQL LIKE. Case-insensitive."""
    return session.query(RaceSeries).filter(
        RaceSeries.display_name.ilike(f"%{query}%")
    ).limit(limit).all()
```

Feed page layout in `calendar.py`:
```python
def render():
    session = st.session_state.db_session

    # Global category filter (top of sidebar, persistent)
    global_cat = render_global_category_filter(session)

    # Search bar (top of main area)
    search = st.text_input("Search races", value=st.session_state.get("search_query", ""),
                           placeholder="e.g. Banana Belt, Mason Lake...")
    if search != st.session_state.get("search_query", ""):
        st.session_state.search_query = search
        st.rerun()

    # Fetch feed items
    items = get_feed_items(session, category=global_cat, search_query=search)

    # "This Weekend" section
    weekend_items = [i for i in items if i["is_this_weekend"]]
    if weekend_items:
        st.subheader("This Weekend")
        for item in weekend_items:
            render_feed_card(item, expanded=False)
        st.divider()

    # Main feed
    st.subheader("All Races")
    upcoming = [i for i in items if i["is_upcoming"] and not i["is_this_weekend"]]
    historical = [i for i in items if not i["is_upcoming"]]

    if upcoming:
        st.caption("UPCOMING")
        for item in upcoming:
            render_feed_card(item, expanded=False)

    if historical:
        st.caption("PAST SERIES")
        for item in historical:
            render_feed_card(item, expanded=False)
```

### Phase 2: Rich Race Cards (30% of effort)

**Goal:** Each feed card shows inline: predicted finish type badge, terrain badge, narrative snippet, drop rate, course sparkline, registration link, edition count with disclosure. Cards are `st.expander` widgets.

**Files:**
- `raceanalyzer/ui/components.py` -- Add `render_feed_card()`, `render_elevation_sparkline()`, `render_dormant_badge()`
- `raceanalyzer/queries.py` -- Extend `get_feed_items()` to include narrative snippet, course data flag, registration URL
- `raceanalyzer/ui/pages/calendar.py` -- Wire up rich cards

**`render_feed_card()` structure:**
```python
def render_feed_card(item: dict, expanded: bool = False):
    series_id = item["series_id"]
    label_parts = [item["display_name"]]
    if item.get("upcoming_date"):
        label_parts.append(f" -- {item['upcoming_date']:%b %d, %Y}")
    elif item.get("latest_date"):
        label_parts.append(f" -- last raced {item['latest_date']:%b %Y}")

    with st.expander("".join(label_parts), expanded=expanded):
        # Row 1: Badges (finish type, terrain, drop rate)
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        with col1:
            if item.get("predicted_finish_type"):
                render_prediction_badge(item["predicted_finish_type"], item["confidence"])
        with col2:
            if item.get("course_type"):
                render_terrain_badge(item["course_type"])
        with col3:
            if item.get("drop_rate_pct") is not None:
                st.caption(f"{item['drop_rate_pct']}% drop rate")
        with col4:
            if item.get("edition_count", 0) > 1:
                st.caption(f"{item['edition_count']} editions")

        # Row 2: Narrative snippet + sparkline
        text_col, spark_col = st.columns([3, 1])
        with text_col:
            if item.get("narrative_snippet"):
                st.write(item["narrative_snippet"])
        with spark_col:
            if item.get("has_profile"):
                render_elevation_sparkline(item["profile_points_sampled"])

        # Row 3: Registration + navigation
        if item.get("is_upcoming"):
            btn_col1, btn_col2 = st.columns(2)
            if item.get("registration_url"):
                btn_col1.markdown(f"[Register]({item['registration_url']})")
            with btn_col2:
                if st.button("Full Preview", key=f"preview_{series_id}"):
                    st.query_params["series_id"] = str(series_id)
                    st.switch_page("pages/race_preview.py")

        # Row 4: Dormant badge (UC-06)
        if not item.get("is_upcoming"):
            st.caption("No upcoming edition announced")

        # Row 5: Historical editions disclosure (UC-04)
        if item.get("edition_count", 0) > 1:
            with st.expander(f"Previous editions ({item['edition_count']})"):
                for ed in item.get("editions_summary", []):
                    st.write(f"- {ed['date']:%Y}: {ed['finish_type_display']}")
```

**Elevation sparkline:**
```python
def render_elevation_sparkline(points: list[dict], width=200, height=40):
    if not points or len(points) < 2:
        return
    # Sample to ~50 points
    step = max(1, len(points) // 50)
    sampled = points[::step]
    elevations = [p["e"] for p in sampled]
    min_e, max_e = min(elevations), max(elevations)
    e_range = max_e - min_e or 1
    # Build SVG path
    x_step = width / (len(sampled) - 1)
    path_parts = []
    for i, e in enumerate(elevations):
        x = i * x_step
        y = height - (e - min_e) / e_range * height
        cmd = "M" if i == 0 else "L"
        path_parts.append(f"{cmd}{x:.1f},{y:.1f}")
    # Close path for fill
    path_parts.append(f"L{width},{height}")
    path_parts.append(f"L0,{height}")
    path_parts.append("Z")
    path_d = " ".join(path_parts)
    svg = (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}"'
        f' xmlns="http://www.w3.org/2000/svg">'
        f'<path d="{path_d}" fill="#4CAF50" opacity="0.3" stroke="#4CAF50" stroke-width="1.5"/>'
        f'</svg>'
    )
    st.markdown(svg, unsafe_allow_html=True)
```

### Phase 3: Global Category Filter & Deep Linking (25% of effort)

**Goal:** Category filter persists across all views. Deep links work. Scroll position / last-viewed state is remembered.

**Files:**
- `raceanalyzer/ui/app.py` -- Initialize global session state from query params
- `raceanalyzer/ui/components.py` -- Replace `render_sidebar_filters()` with `render_global_category_filter()` that writes to session state
- `raceanalyzer/ui/pages/calendar.py` -- Read global category from session state
- `raceanalyzer/ui/pages/race_preview.py` -- Read global category from session state instead of per-page selector
- `raceanalyzer/ui/pages/series_detail.py` -- Read global category from session state
- `raceanalyzer/ui/pages/race_detail.py` -- Read global category from session state

**Global category filter implementation:**

In `app.py`, after session/settings init:
```python
# Sync query params -> session state on first load
if "global_category" not in st.session_state:
    st.session_state.global_category = st.query_params.get("category", None)
if "expanded_series_id" not in st.session_state:
    qs = st.query_params.get("series_id")
    st.session_state.expanded_series_id = int(qs) if qs else None
if "search_query" not in st.session_state:
    st.session_state.search_query = st.query_params.get("q", "")
```

In `components.py`:
```python
def render_global_category_filter(session) -> Optional[str]:
    """Render a persistent category filter in the sidebar.

    Reads/writes st.session_state.global_category.
    Updates st.query_params for deep linking.
    """
    categories = _cached_categories(session)
    current = st.session_state.get("global_category")

    cat_options = [None] + categories
    default_idx = 0
    if current and current in categories:
        default_idx = categories.index(current) + 1

    chosen = st.sidebar.selectbox(
        "Your Category",
        options=cat_options,
        index=default_idx,
        format_func=lambda x: "All Categories" if x is None else x,
        key="global_category_selector",
    )

    if chosen != current:
        st.session_state.global_category = chosen
        if chosen:
            st.query_params["category"] = chosen
        elif "category" in st.query_params:
            del st.query_params["category"]

    return chosen
```

**Deep linking (UC-47):**
The URL `http://localhost:8501/?series_id=42&category=Men+Cat+4/5` opens the feed with series 42 expanded and the category pre-set. This works because `app.py` seeds session state from query params on first load, and the feed page checks `st.session_state.expanded_series_id` to pre-expand the matching card's `st.expander(expanded=True)`.

**Remember state (UC-50):**
Streamlit session state already persists across reruns within a browser session. The pagination offset (`feed_scroll_position`) is stored as the number of items rendered. When the user clicks "Show More", we increment this counter. On return visits (within the same session), items up to this offset are rendered. True cross-session persistence (surviving tab close) would require cookies or URL encoding, which is out of scope -- session state is sufficient for the "return to where I was within a browsing session" use case.

### Phase 4: Content Enrichment (10% of effort)

**Goal:** Plain-English finish type labels as default. Race duration estimates.

**Files:**
- `raceanalyzer/queries.py` -- Add `FINISH_TYPE_PLAIN_ENGLISH` dict with short plain-English labels
- `raceanalyzer/predictions.py` -- Add `calculate_typical_duration()`
- `raceanalyzer/ui/components.py` -- Update badge rendering to use plain-English by default
- `raceanalyzer/ui/pages/race_preview.py` -- Show duration estimate
- `tests/test_predictions.py` -- Tests for `calculate_typical_duration()`

**Plain-English labels (UC-09):**
```python
FINISH_TYPE_PLAIN_ENGLISH = {
    "bunch_sprint": "The group stays together and sprints",
    "small_group_sprint": "A select group sprints among themselves",
    "breakaway": "An attacker escapes and holds on",
    "breakaway_selective": "Attackers ride away, the field shatters",
    "reduced_sprint": "The hard pace drops many, survivors sprint",
    "gc_selective": "The race blows apart into small groups",
    "individual_tt": "Riders race the clock individually",
    "mixed": "No single pattern dominates",
    "unknown": "Not enough data to classify",
}
```

These are used as the primary text on feed cards. The existing short labels ("Bunch Sprint", "Breakaway") become the badge text alongside, giving both at-a-glance recognition and plain-English context.

**Duration calculation (UC-16):**
```python
def calculate_typical_duration(session, series_id, category=None):
    # Same pattern as calculate_typical_speeds()
    # For each edition: get winner's race_time_seconds, field median race_time_seconds
    # Return median across editions in minutes
    # Suppress for TTs (individual pacing, not meaningful "field" time)
```

---

## Files Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `raceanalyzer/ui/app.py` | Modify | Rename Calendar to "Race Feed", seed global session state from query params |
| `raceanalyzer/ui/pages/calendar.py` | **Rewrite** | Unified feed with search, "This Weekend", inline cards, pagination |
| `raceanalyzer/ui/components.py` | Modify | Add `render_feed_card()`, `render_elevation_sparkline()`, `render_global_category_filter()`, `render_dormant_badge()`; update badge rendering for plain-English |
| `raceanalyzer/queries.py` | Modify | Add `get_feed_items()`, `search_series()`, `FINISH_TYPE_PLAIN_ENGLISH` |
| `raceanalyzer/predictions.py` | Modify | Add `calculate_typical_duration()` |
| `raceanalyzer/ui/pages/race_preview.py` | Modify | Read global category from session state; add duration display; extract reusable rendering functions |
| `raceanalyzer/ui/pages/series_detail.py` | Modify | Read global category from session state |
| `raceanalyzer/ui/pages/race_detail.py` | Modify | Read global category from session state |
| `tests/test_queries.py` | Modify | Tests for `get_feed_items()`, `search_series()` |
| `tests/test_predictions.py` | Modify | Tests for `calculate_typical_duration()` |

No new files are created. No database schema changes. No new dependencies.

---

## Definition of Done

### Functional

1. The app opens to a single feed page showing all series, with upcoming races sorted first by date
2. Each feed card displays inline: predicted finish type (in plain English), terrain badge, drop rate percentage, narrative snippet (1-2 sentences), and registration link (if upcoming)
3. "This Weekend" section appears at the top when races occur within the next 7 days
4. Text search filters the feed by series name in real time
5. Clicking a feed card's expander reveals full preview content (course profile, full narrative, contenders, stats) without leaving the page
6. A course elevation sparkline thumbnail appears on cards that have profile data
7. Series with no upcoming edition show a "No upcoming edition" indicator and sort below upcoming races
8. Historical editions are accessible via a nested expander within each card showing year and finish type per edition
9. Setting the category filter in the sidebar persists across page navigation and applies to all views (feed, preview, detail)
10. Deep links with `?series_id=N` and `?category=X` query params open the feed with the correct card expanded and category set
11. Race duration estimate appears on the Race Preview page when sufficient historical timing data exists

### Non-Functional

12. All existing `pytest` tests pass unchanged
13. New tests cover `get_feed_items()`, `search_series()`, and `calculate_typical_duration()`
14. `ruff check .` passes with no new warnings
15. Feed page loads in under 3 seconds with 50+ series (acceptable since `get_feed_items()` calls prediction/stats functions per series, but these are cached)
16. The Race Preview, Series Detail, Race Detail, and Dashboard pages remain functional and accessible

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Feed load time**: `get_feed_items()` calls `predict_series_finish_type()`, `calculate_drop_rate()`, and `generate_narrative()` per series. With 50+ series, this could be slow. | Medium | High | Use `@st.cache_data(ttl=300)` on `get_feed_items()`. The function returns serializable dicts, so Streamlit's cache works. Alternatively, pre-compute and cache per-series summaries in a dict keyed by `(series_id, category)`. |
| **Expander scroll behavior**: Opening an `st.expander` does not cause a full page rerun, but closing and reopening may. Streamlit's expander state is managed internally and may conflict with session state tracking. | Low | Medium | Do not try to track expander open/close state in session state. Let Streamlit manage it natively. Only use session state for the deep-link case (`expanded_series_id` on initial load). |
| **Search performance**: SQL `LIKE '%query%'` on `display_name` is fine for ~100 series but could be slow if the dataset grows. | Low | Low | Acceptable for current scale. If needed later, add a full-text search index or precompute a search cache. |
| **Narrative snippet extraction**: Splitting `generate_narrative()` output into a "snippet" (first 1-2 sentences) is fragile if the narrative format changes. | Low | Low | Use `sentence_split()` helper that splits on `. ` and takes the first 2 elements. Alternatively, have `generate_narrative()` return a structured dict with `summary` and `detail` keys. |
| **Global category filter rerun loop**: Changing the category selectbox triggers a rerun, which re-renders the selectbox, which could trigger another rerun if the default index calculation is wrong. | Medium | Medium | Use a `key` parameter on the selectbox to prevent Streamlit from re-creating the widget. Compare old and new values before calling `st.rerun()` -- only rerun if the value actually changed. |

---

## Security

- No new external API calls or network requests
- No user authentication or personal data storage
- Search input is passed through SQLAlchemy's parameterized queries (no SQL injection risk)
- Query params are read-only from the URL; no user-supplied data is written to the database
- Inline HTML rendering (sparklines, badges) uses hardcoded SVG with no user-controlled content interpolated into markup

---

## Dependencies

- **No new Python packages.** All functionality uses existing Streamlit, SQLAlchemy, and pandas APIs.
- **No new external services.** All data comes from the existing SQLite database.
- **Sprint 009 must be complete.** The feed relies on `Race.is_upcoming`, `Race.registration_url`, and `Startlist` data populated by Sprint 009's road-results integration.

---

## Open Questions

1. **Should `get_feed_items()` pre-compute all preview data on page load, or lazy-load on expander open?** Pre-computing is simpler and cache-friendly but may be slow for large datasets. Lazy-loading reduces initial load time but requires more complex session state management. Recommendation: pre-compute with `@st.cache_data` for the first version; optimize later if performance is a problem.

2. **How many sentences should the narrative snippet show?** The intent document says "1-2 sentences." The current `generate_narrative()` returns 1-5 sentences. Recommendation: show the first 2 sentences (course + history) on the card; show the full narrative in the expanded view.

3. **Should the existing `render_sidebar_filters()` (year, state, category) be preserved alongside the new global category filter?** Year and state filters are useful for power users. Recommendation: keep year and state filters in the sidebar below the category filter. The category filter moves to the top of the sidebar with a more prominent label ("Your Category") to signal persistence.

4. **Should we rename `calendar.py` to `feed.py`?** Renaming would be cleaner conceptually but could break any external links or bookmarks to `pages/calendar.py`. Recommendation: keep the filename but update the page title in `app.py` to "Race Feed."

5. **What is the "This Weekend" date range?** Recommendation: today through the end of Sunday. Use `datetime.now()` to determine the current day and compute the date range. Races on Saturday and Sunday of the current week qualify.

6. **Should dormant series (UC-06) be hidden by default or shown grayed out?** Recommendation: show them below upcoming series with reduced opacity (CSS `opacity: 0.6`) and a "No upcoming edition" caption. A toggle to hide them entirely is a nice-to-have.
