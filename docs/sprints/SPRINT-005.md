# Sprint 005: Classification-Centric UI Overhaul

## Overview

Pivot the calendar from event-type presentation (criterium, road race) to **finish-type classification** (bunch sprint, breakaway, individual TT). Users care what *happened*, not what the event was called. Add a new `INDIVIDUAL_TT` finish type for time trials and hill climbs. Redesign tiles as a CSS Grid with finish-type icons, hide UNKNOWN-classified races by default, make tiles fully clickable with hover effects, and add back navigation from the detail page. Source maps via Nominatim geocoding with OpenStreetMap static tiles.

**Duration**: ~4-5 days
**Prerequisite**: Sprint 004 complete, 20 real PNW races scraped with classifications.
**Merged from**: Codex draft (primary — CSS Grid, spacing algorithm, Nominatim maps, query_params), Claude draft (icon designs, URL validation, fallback navigation), Gemini draft (security section), interview decisions (frequency-based overall classification, Codex TT algorithm, scope cuts).

---

## Use Cases

1. **As a racer**, I see finish-type icons on tiles (bunch sprint, breakaway, etc.) telling me what happened, not what the event was called.
2. **As a racer**, I see "Individual TT" for time trials and hill climbs instead of GC_SELECTIVE or UNKNOWN.
3. **As a racer**, I see only classified races by default. A toggle reveals the ~50% of races lacking time data.
4. **As a racer**, I click anywhere on a tile to see race details — the whole tile is a click target with a hover lift effect.
5. **As a racer**, each tile shows an overall classification badge (e.g., "Bunch Sprint") summarizing the race.
6. **As a racer**, I can navigate back from race detail to the calendar without losing my filter state.
7. **As a racer**, I see a map on each race showing the geographic area (geocoded from the race location).
8. **As a developer**, I can run `classify --all` and Individual TTs are detected automatically from metadata, keywords, or statistical spacing patterns.

---

## Architecture

```
raceanalyzer/
├── db/
│   └── models.py              # MODIFY: Add FinishType.INDIVIDUAL_TT
├── classification/
│   └── finish_type.py         # MODIFY: Add is_individual_tt(), update classify_finish_type()
├── queries.py                 # MODIFY: get_race_tiles() with overall_finish_type,
│                              #          FINISH_TYPE_TOOLTIPS, INDIVIDUAL_TT display name
├── ui/
│   ├── components.py          # REWRITE: FINISH_TYPE_ICONS (SVGs), CSS Grid tiles,
│   │                          #          clickable tiles with hover, tooltip support
│   ├── maps.py                # CREATE: Nominatim geocoding, OSM static map URLs
│   ├── pages/
│   │   ├── calendar.py        # MODIFY: UNKNOWN toggle, CSS Grid rendering, filter state
│   │   └── race_detail.py     # MODIFY: Back button with filter state, area map
├── cli.py                     # MODIFY: Pass race metadata to classifier

tests/
├── test_finish_type.py        # MODIFY: Add Individual TT test cases
├── test_queries.py            # MODIFY: Test overall_finish_type aggregation
```

### Key Design Decisions

1. **Individual TT detection: three-tier with statistical spacing** (Codex approach, user-approved). Metadata (race_type) → name keywords → statistical analysis (group_ratio > 0.7 AND gap CV < 0.8). The statistical tier catches TTs with non-obvious names (e.g., "Maryhill Loops", "Mutual of Enumclaw").

2. **Overall classification: most frequent non-UNKNOWN** (user-approved). For each race, count finish types across categories excluding UNKNOWN. Pick the most frequent. Ties broken by total finishers in that type, then lowest average CV. This approach works well as historical editions of the same race are added.

3. **CSS Grid tiles** (Codex approach, user-approved). Full `st.markdown` HTML injection with CSS Grid layout, hover pseudo-classes, and `<a>` tag click targets. More flexible than `st.columns` for interactivity.

4. **Nominatim geocoding as primary map source**. Every race has a location string. Geocode it, show an OSM static map. BikeReg/RideWithGPS course maps are a future enhancement, not a blocker.

5. **Tooltips via HTML `title` attribute**. Simple, zero-dependency. Can be upgraded to CSS tooltips later. Cuttable if scope-constrained.

6. **Back navigation with filter state preservation**. Store filters in `st.query_params` before navigating to detail. Back button reads them and restores.

---

## Implementation

### 1. `raceanalyzer/db/models.py` — Add INDIVIDUAL_TT

```python
class FinishType(enum.Enum):
    BUNCH_SPRINT = "bunch_sprint"
    SMALL_GROUP_SPRINT = "small_group_sprint"
    BREAKAWAY = "breakaway"
    BREAKAWAY_SELECTIVE = "breakaway_selective"
    REDUCED_SPRINT = "reduced_sprint"
    GC_SELECTIVE = "gc_selective"
    MIXED = "mixed"
    INDIVIDUAL_TT = "individual_tt"  # NEW
    UNKNOWN = "unknown"
```

No migration needed — SQLAlchemy stores enum values as strings in SQLite.

### 2. `raceanalyzer/classification/finish_type.py` — TT Detection

New function `is_individual_tt()` called before the existing decision tree:

```python
def is_individual_tt(
    groups: list[RiderGroup],
    total_finishers: int,
    race_type: RaceType | None = None,
    race_name: str = "",
) -> tuple[bool, float]:
    """Detect individual TT/hill climb via three-tier analysis.

    Returns (is_tt, confidence):
    - Tier 1: race_type metadata (TIME_TRIAL, HILL_CLIMB) -> 0.95
    - Tier 2: name keywords -> 0.85
    - Tier 3: statistical spacing (group_ratio > 0.7, gap_cv < 0.8) -> 0.75
    """
    # Tier 1: Race type metadata
    if race_type in (RaceType.TIME_TRIAL, RaceType.HILL_CLIMB):
        return (True, 0.95)

    # Tier 2: Name keywords
    name_lower = race_name.lower()
    tt_keywords = ["time trial", "tt ", " tt", "hill climb", "hillclimb",
                   "chrono", "itt", "contre la montre"]
    if any(kw in name_lower for kw in tt_keywords):
        return (True, 0.85)

    # Tier 3: Statistical spacing
    if not groups or total_finishers < 5:
        return (False, 0.0)

    group_ratio = len(groups) / total_finishers
    if group_ratio <= 0.7:
        return (False, 0.0)

    # CV of consecutive inter-rider gaps (NOT absolute times)
    all_times = sorted(
        t for g in groups for r in g.riders
        if (t := getattr(r, "race_time_seconds", None)) is not None
    )
    if len(all_times) < 5:
        return (False, 0.0)

    gaps = [all_times[i] - all_times[i-1]
            for i in range(1, len(all_times)) if all_times[i] > all_times[i-1]]
    if not gaps:
        return (False, 0.0)

    gap_mean = statistics.mean(gaps)
    if gap_mean <= 0:
        return (False, 0.0)

    gap_cv = statistics.stdev(gaps) / gap_mean
    if gap_cv < 0.8:
        return (True, 0.75)

    return (False, 0.0)
```

Modify `classify_finish_type()` signature to accept `race_type` and `race_name` (with backward-compatible defaults):

```python
def classify_finish_type(
    groups: list[RiderGroup],
    total_finishers: int,
    gap_threshold_used: float = 3.0,
    race_type: RaceType | None = None,  # NEW
    race_name: str = "",                 # NEW
) -> ClassificationResult:
    # Check for Individual TT first
    is_tt, tt_confidence = is_individual_tt(
        groups, total_finishers, race_type, race_name
    )
    if is_tt:
        metrics = _compute_metrics(groups, total_finishers, gap_threshold_used)
        return ClassificationResult(
            finish_type=FinishType.INDIVIDUAL_TT,
            confidence=tt_confidence,
            metrics=metrics,
        )

    # ... existing decision tree unchanged ...
```

### 3. `raceanalyzer/queries.py` — Overall Classification on Tiles

Modify `get_race_tiles()` to include `overall_finish_type`:

```python
def get_race_tiles(session, *, year=None, states=None, limit=200):
    # Query races with all their classifications
    # ... existing query ...

    # Post-process: compute overall_finish_type per race
    # For each race, find most frequent non-UNKNOWN finish type
    # Tiebreak: total finishers, then lowest avg CV
    for row in data:
        race_id = row["id"]
        classifications = (
            session.query(RaceClassification.finish_type,
                          func.count().label("cnt"),
                          func.sum(RaceClassification.num_finishers).label("total_finishers"),
                          func.avg(RaceClassification.cv_of_times).label("avg_cv"))
            .filter(RaceClassification.race_id == race_id,
                    RaceClassification.finish_type != FinishType.UNKNOWN)
            .group_by(RaceClassification.finish_type)
            .order_by(func.count().desc(),
                       func.sum(RaceClassification.num_finishers).desc(),
                       func.avg(RaceClassification.cv_of_times).asc())
            .first()
        )
        row["overall_finish_type"] = (
            classifications[0].value if classifications else "unknown"
        )
```

Add to display names and tooltips:

```python
FINISH_TYPE_DISPLAY_NAMES["individual_tt"] = "Individual TT"

FINISH_TYPE_TOOLTIPS = {
    "bunch_sprint": "The whole pack stayed together and sprinted for the line.",
    "small_group_sprint": "A select group broke clear and sprinted among themselves.",
    "breakaway": "A solo rider or tiny group escaped and held on to the finish.",
    "breakaway_selective": "Attackers rode away and the chase groups shattered behind them.",
    "reduced_sprint": "The hard pace dropped many riders, but survivors sprinted it out.",
    "gc_selective": "The race blew apart — small groups everywhere, no pack left.",
    "individual_tt": "Riders started one at a time and raced the clock, not each other.",
    "mixed": "A bit of everything — no single pattern dominated.",
    "unknown": "Not enough timing data to classify this race.",
}
```

### 4. `raceanalyzer/ui/components.py` — Finish Type Icons & CSS Grid Tiles

Replace `RACE_TYPE_ICONS` with `FINISH_TYPE_ICONS` — nine 24x24 inline SVGs:

| Finish Type | Visual | Color |
|-------------|--------|-------|
| `bunch_sprint` | Tight cluster of 5 dots in arrow/V formation | #E53935 (red) |
| `small_group_sprint` | 3 dots ahead, gap line, 5 dots behind | #FF9800 (orange) |
| `breakaway` | 1 dot far ahead, dashed gap, cluster behind | #4CAF50 (green) |
| `breakaway_selective` | 2 dots ahead, scattered dots behind | #2E7D32 (dark green) |
| `reduced_sprint` | ~4 dots in front cluster, gap, scattered | #1E88E5 (blue) |
| `gc_selective` | Multiple scattered small clusters | #7B1FA2 (purple) |
| `individual_tt` | Single dot with clock/stopwatch lines | #00ACC1 (teal) |
| `mixed` | 3 dots at different heights (irregular) | #78909C (blue-gray) |
| `unknown` | Question mark in circle | #9E9E9E (gray) |

**CSS Grid tile rendering** — new `render_tile_grid()` function:

```python
import html

def render_tile_grid(tiles_df, key_prefix="cal"):
    """Render tiles as a CSS Grid with clickable cards and hover effects."""
    # Inject global CSS once
    st.markdown('''
    <style>
    .race-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
    .race-tile {
        border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px;
        background: white; cursor: pointer; transition: all 0.2s;
    }
    .race-tile:hover {
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        transform: translateY(-2px);
    }
    .race-tile a { text-decoration: none; color: inherit; display: block; }
    @media (max-width: 768px) {
        .race-grid { grid-template-columns: repeat(2, 1fr); }
    }
    </style>
    ''', unsafe_allow_html=True)

    # Build HTML for all visible tiles
    cards_html = []
    for idx, row in tiles_df.iterrows():
        name = html.escape(str(row.get("name", "")))
        finish_type = row.get("overall_finish_type", "unknown")
        icon = FINISH_TYPE_ICONS.get(finish_type, FINISH_TYPE_ICONS["unknown"])
        color = FINISH_TYPE_COLORS.get(finish_type, "#9E9E9E")
        display = FINISH_TYPE_DISPLAY_NAMES.get(finish_type, "Unknown")
        tooltip = html.escape(FINISH_TYPE_TOOLTIPS.get(finish_type, ""))
        race_id = row["id"]

        # Date formatting
        date_str = ""
        if row.get("date"):
            try:
                date_str = f"{row['date']:%b %d, %Y}"
            except (TypeError, ValueError):
                date_str = str(row["date"])

        loc = html.escape(str(row.get("location", "") or ""))
        state = html.escape(str(row.get("state_province", "") or ""))
        loc_str = f"{loc}, {state}" if state else loc

        card = f'''
        <div class="race-tile" onclick="window.location.search='?page=race_detail&race_id={race_id}'">
          <div style="display:flex;align-items:center;gap:8px;">
            {icon}
            <strong>{name}</strong>
          </div>
          <div style="margin-top:8px;font-size:0.85em;color:#666;">
            {date_str} &middot; {loc_str}
          </div>
          <div style="margin-top:6px;" title="{tooltip}">
            <span style="background:{color};color:white;padding:2px 8px;
              border-radius:4px;font-size:0.8em;">{display}</span>
          </div>
        </div>
        '''
        cards_html.append(card)

    grid_html = f'<div class="race-grid">{"".join(cards_html)}</div>'
    st.markdown(grid_html, unsafe_allow_html=True)

    # Hidden st.button fallback for reliable Streamlit navigation
    # (CSS Grid onclick may not work in all Streamlit iframe configs)
    for idx, row in tiles_df.iterrows():
        if st.button(f"View {row['name']}", key=f"{key_prefix}_btn_{row['id']}",
                     type="secondary"):
            st.session_state["selected_race_id"] = int(row["id"])
            st.query_params["race_id"] = str(row["id"])
            st.switch_page("pages/race_detail.py")
```

Note: The hidden buttons need CSS to actually hide them (`.stButton { display: none; }`), or remove them entirely if JS navigation works reliably in testing.

### 5. `raceanalyzer/ui/maps.py` — Nominatim Geocoding (NEW FILE)

```python
"""Location geocoding and static map URL generation."""

import logging
import requests

logger = logging.getLogger(__name__)

_GEOCODE_CACHE: dict[str, tuple[float, float] | None] = {}


def geocode_location(location: str, state: str = "") -> tuple[float, float] | None:
    """Geocode a location string via Nominatim. Returns (lat, lon) or None.

    Results are cached in-memory for the session.
    """
    query = f"{location}, {state}" if state else location
    if query in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[query]

    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": "RaceAnalyzer/0.1 (PNW bike race analysis)"},
            timeout=5,
        )
        if resp.ok and resp.json():
            data = resp.json()[0]
            result = (float(data["lat"]), float(data["lon"]))
            _GEOCODE_CACHE[query] = result
            return result
    except Exception:
        logger.debug("Geocoding failed for %s", query)

    _GEOCODE_CACHE[query] = None
    return None


def build_static_map_url(lat: float, lon: float, zoom: int = 12) -> str:
    """Return an OpenStreetMap static map URL centered on lat/lon."""
    return (
        f"https://staticmap.openstreetmap.de/staticmap.php"
        f"?center={lat},{lon}&zoom={zoom}&size=400x200&maptype=mapnik"
        f"&markers={lat},{lon},red-pushpin"
    )
```

### 6. `raceanalyzer/ui/pages/calendar.py` — UNKNOWN Toggle & Filter State

```python
# After sidebar filters
show_unknown = st.toggle("Show races without timing data", value=False)

# Filter
if not show_unknown:
    df = df[df["overall_finish_type"] != "unknown"]

if df.empty:
    render_empty_state("No classified races found. Toggle 'Show races without timing data' to see all.")
    return

# Store filter state in query params for back navigation
st.query_params["year"] = str(filters["year"]) if filters["year"] else ""
st.query_params["states"] = ",".join(filters["states"]) if filters["states"] else ""

# Render CSS Grid tiles (replaces st.columns loop)
visible_df = df.head(visible_count)
render_tile_grid(visible_df, key_prefix="cal")
```

### 7. `raceanalyzer/ui/pages/race_detail.py` — Back Button & Map

```python
# At top of page
col_back, col_spacer = st.columns([1, 5])
with col_back:
    if st.button("Back to Calendar"):
        st.switch_page("pages/calendar.py")

# ... existing detail page ...

# Area map (after header, before classifications)
from raceanalyzer.ui.maps import geocode_location, build_static_map_url

if race.get("location"):
    coords = geocode_location(race["location"], race.get("state_province", ""))
    if coords:
        map_url = build_static_map_url(*coords)
        st.image(map_url, caption=f"{race['location']}, {race.get('state_province', '')}")
```

### 8. `raceanalyzer/cli.py` — Pass Metadata to Classifier

In the `classify` command, load the Race object and pass its name/type to `classify_finish_type()`:

```python
race_obj = session.get(Race, rid)
classification = classify_finish_type(
    groups, total_finishers, gap_threshold,
    race_type=race_obj.race_type if race_obj else None,
    race_name=race_obj.name if race_obj else "",
)
```

---

## Files Summary

| File | Action | Description |
|------|--------|-------------|
| `raceanalyzer/db/models.py` | **Modify** | Add `INDIVIDUAL_TT` to FinishType enum |
| `raceanalyzer/classification/finish_type.py` | **Modify** | Add `is_individual_tt()`, update `classify_finish_type()` signature |
| `raceanalyzer/queries.py` | **Modify** | Overall finish type in tile query, tooltips dict, TT display name |
| `raceanalyzer/ui/components.py` | **Rewrite** | Replace race-type icons with finish-type icons, CSS Grid tiles |
| `raceanalyzer/ui/maps.py` | **Create** | Nominatim geocoding, OSM static map URLs |
| `raceanalyzer/ui/pages/calendar.py` | **Modify** | UNKNOWN toggle, CSS Grid rendering, filter state in query params |
| `raceanalyzer/ui/pages/race_detail.py` | **Modify** | Back button, area map display |
| `raceanalyzer/cli.py` | **Modify** | Pass race_type/race_name to classifier |
| `tests/test_finish_type.py` | **Modify** | Individual TT tests (metadata, keyword, statistical, edge cases) |
| `tests/test_queries.py` | **Modify** | Test overall_finish_type aggregation |

**Total new files**: 1 (`maps.py`)
**Total modified files**: 9
**Estimated new tests**: ~8-10

---

## Definition of Done

1. `FinishType.INDIVIDUAL_TT` exists in enum
2. `is_individual_tt()` detects TTs via metadata (0.95), keywords (0.85), and statistical spacing (0.75)
3. Statistical detection uses group_ratio > 0.7 AND consecutive-gap CV < 0.8
4. `classify_finish_type()` calls TT check before decision tree, with backward-compatible signature
5. Tiles display finish-type SVG icons (9 types), not event-type icons
6. Each tile shows overall classification badge (most frequent non-UNKNOWN across categories)
7. UNKNOWN races hidden by default; `st.toggle` reveals them
8. Clicking anywhere on a tile navigates to the race detail page
9. Tiles have visual hover effect (box-shadow + translateY)
10. Race detail page has "Back to Calendar" button that preserves filter state via query params
11. Nominatim geocoding produces area maps for races with location data
12. All race names/locations in HTML are escaped via `html.escape()`
13. CLI `classify` command passes `race_type` and `race_name` to classifier
14. All existing tests pass (zero regressions)
15. New tests: Individual TT metadata detection, keyword detection, statistical detection, edge cases (small field, no times)

---

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Nominatim rate limiting (1 req/sec policy) | No maps on fresh load | Medium | In-memory cache, `@st.cache_data`, sequential requests |
| CSS Grid onclick unreliable in Streamlit iframe | Broken tile navigation | Medium | Hidden st.button fallback for native Streamlit routing |
| TT statistical detection false positives (GC races) | Wrong classification | Low | Conservative group_ratio > 0.7 threshold; metadata/keywords checked first |
| HTML injection breaks on special characters | XSS or broken tiles | Low | `html.escape()` on all dynamic strings |
| SQLite enum value addition | Potential query issues | Very Low | SQLAlchemy stores as strings; new value is additive |
| Existing tests break from `classify_finish_type()` signature change | Test failures | Low | New params have defaults (`race_type=None`, `race_name=""`) |

---

## Security

- All dynamic strings in HTML tiles escaped via `html.escape()`
- Nominatim requests use descriptive User-Agent per usage policy
- No user-controlled data flows into SVG icon strings (all constants)
- If BikeReg scraping added later: validate URLs against domain allowlist (ridewithgps.com, strava.com)

---

## Dependencies

- No new Python packages required
- `requests` already in dependencies (for Nominatim)
- External APIs: Nominatim (free, no key), OpenStreetMap static maps (free)

---

## Scope Cut Guidance (from user)

If constrained, cut in this order (last = cut first):
1. **Keep**: Classification icons on tiles, Individual TT detection, UNKNOWN toggle, clickable tiles + hover, back navigation
2. **Cut if needed**: Tooltips (HTML `title` attributes), real course maps from BikeReg/RideWithGPS

---

## Open Questions — Resolved

1. **Overall classification**: Most frequent non-UNKNOWN, tiebreak by total finishers then CV. (User decision)
2. **TT detection algorithm**: Codex three-tier with gap_cv < 0.8. (User decision)
3. **Map strategy**: Nominatim geocoding primary, BikeReg deferred. (User decision)
4. **Tile implementation**: CSS Grid via st.markdown. (User decision)
5. **Hill climb vs TT icon**: Grouped under INDIVIDUAL_TT (same icon/classification).
6. **SQLite MODE()**: Python-side aggregation, not SQL aggregate.
7. **CV metric for TT detection**: Consecutive inter-rider gaps (NOT absolute finish times).
