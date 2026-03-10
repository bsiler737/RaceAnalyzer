# Sprint 005: Classification-Centric UI Overhaul + Individual TT Detection

## Overview

Transform the calendar page from event-type-oriented tiles (criterium, road race, hill climb) into classification-oriented tiles (bunch sprint, breakaway, GC selective, etc.) that communicate the *character* of each race at a glance. Add a new `INDIVIDUAL_TT` finish type to correctly classify time trials and hill climbs where riders finish individually on staggered starts. Hide the ~53% of classifications that are `UNKNOWN` (no time data) behind a toggle so the default view surfaces only actionable insights. Make tiles fully clickable with hover effects, add casual-language tooltips for each classification, source real course maps from BikeReg/RideWithGPS where possible, and add back-navigation from the detail page.

**Duration**: ~4-5 days
**Primary deliverables**: Individual TT classifier, finish-type SVG icons on tiles, UNKNOWN toggle, clickable tiles with hover, tooltips, overall race classification, back button, course map scraping with fallback.
**Prerequisite**: Sprint 004 complete (tile grid, race type icons, mini course maps, scary racers).

---

## Use Cases

1. **As a racer**, I see tiles with icons that tell me whether a race ended in a bunch sprint, breakaway, or solo TT effort -- the finish character matters more to me than whether the event was technically a "criterium" or "road race."
2. **As a racer**, I see an "overall" classification label on each tile (e.g., "Bunch Sprint") so I know the dominant pattern without clicking into details.
3. **As a racer**, I hover over "GC Selective" and a tooltip explains in plain English: "The field shattered into many small groups -- climbing or crosswinds blew it apart."
4. **As a racer**, I see that hill climbs and time trials show as "Individual TT" rather than being misclassified as "GC Selective" due to their many single-rider groups.
5. **As a racer**, I see a clean calendar page showing only classified races by default, and I can toggle "Show unclassified races" to see the 12 events that lack time data.
6. **As a racer**, I click anywhere on a tile (not just the small button) and land on the detail page; hovering over a tile gives me a visual lift effect.
7. **As a racer**, I can click "Back to Calendar" on the detail page to return to where I was browsing.
8. **As a racer**, I see an actual course map on the detail page when the race has a linked RideWithGPS or Strava route, or a location-based area map otherwise.
9. **As a developer**, I can run the test suite and see Individual TT detection tested against both name-based and statistical detection paths.

---

## Architecture

```
raceanalyzer/
+-- db/
|   +-- models.py              # MODIFY: Add INDIVIDUAL_TT to FinishType enum
+-- classification/
|   +-- finish_type.py         # MODIFY: Add ITT pre-classification check
|   +-- grouping.py            # (no changes)
+-- queries.py                 # MODIFY: Add overall_finish_type to tile query,
|                              #          add INDIVIDUAL_TT display name
+-- scraper/
|   +-- client.py              # (no changes)
|   +-- course_maps.py         # CREATE: BikeReg/RideWithGPS course map URL scraper
+-- ui/
|   +-- components.py          # MODIFY: Replace RACE_TYPE_ICONS with FINISH_TYPE_ICONS,
|   |                          #          add tooltips, clickable tiles, hover CSS
|   +-- pages/
|       +-- calendar.py        # MODIFY: Add UNKNOWN toggle, pass overall_finish_type
|       +-- race_detail.py     # MODIFY: Add back button, course map embed

tests/
+-- test_finish_type.py        # MODIFY: Add Individual TT test cases
+-- test_course_maps.py        # CREATE: Tests for BikeReg URL extraction
+-- test_queries.py            # MODIFY: Test overall_finish_type aggregation
```

### Data Flow

```
Tile rendering pipeline (calendar.py):

  get_race_tiles(session, year, states)
      |
      +-- JOIN races -> race_classifications
      +-- Aggregate: pick most-common non-UNKNOWN finish_type per race
      +-- If ALL categories are UNKNOWN -> overall_finish_type = "unknown"
      +-- Returns DataFrame with new "overall_finish_type" column
      |
      v
  [calendar.py]
      |
      +-- Toggle: show_unknown (default False)
      +-- Filter: df[df["overall_finish_type"] != "unknown"] unless toggled
      |
      v
  render_race_tile(tile_data)
      |
      +-- render_finish_type_icon(overall_finish_type)  -> inline SVG
      +-- Classification badge with tooltip title attr
      +-- Entire tile wrapped in clickable <a> with hover CSS
      +-- Click -> st.query_params + st.switch_page

Classification pipeline (for Individual TT):

  classify_race_category(race, results_for_category)
      |
      +-- Step 1: is_individual_tt(race_name, race_type, groups, total_finishers)
      |     |
      |     +-- Name match? ("time trial", "hill climb", "tt ", "itt", "chrono")
      |     +-- Race type match? (TIME_TRIAL or HILL_CLIMB)
      |     +-- Statistical match? (group_ratio > 0.7 AND low gap_stdev)
      |     |
      |     +-- If any True -> return INDIVIDUAL_TT
      |
      +-- Step 2: Existing decision tree (BUNCH_SPRINT, BREAKAWAY, etc.)

Course map resolution (race_detail.py):

  get_course_map_url(race_url_or_bikereg_url)
      |
      +-- Fetch BikeReg page HTML
      +-- Scan for ridewithgps.com/routes/ or strava.com/routes/ links
      +-- Return first match or None
      |
      v
  [race_detail.py]
      |
      +-- If course map URL found -> embed iframe
      +-- Elif race has location -> OpenStreetMap static tile centered on location
      +-- Else -> no map shown
```

### Key Design Decisions

1. **Overall race classification = plurality vote, excluding UNKNOWN.** When a race has multiple categories (e.g., Pro/1/2 classified as BREAKAWAY, Cat 4 as BUNCH_SPRINT, Cat 5 as BUNCH_SPRINT), take the most frequent non-UNKNOWN type. On ties, prefer the type from the category with the most finishers, as larger fields produce more reliable classifications. If every category is UNKNOWN, the overall is UNKNOWN.

2. **Individual TT detection is a pre-check, not a new decision tree branch.** The function `is_individual_tt()` runs before the standard classifier. If it returns True, classification short-circuits to `INDIVIDUAL_TT` with high confidence. This avoids contaminating the existing decision tree logic, which assumes mass-start racing.

3. **Three-signal ITT detection with OR logic.** Any one of these signals triggers INDIVIDUAL_TT: (a) race name keywords, (b) `race_type` enum value, (c) statistical fingerprint. The statistical check exists for edge cases where the race name is ambiguous (e.g., "Seward Park Omnium" that includes a TT stage).

4. **Finish-type icons replace race-type icons entirely on tiles.** The `RACE_TYPE_ICONS` dict remains in components.py for potential use elsewhere but is no longer referenced by tile rendering. A new `FINISH_TYPE_ICONS` dict maps each `FinishType` value to a 24x24 SVG.

5. **Clickable tiles via HTML anchor wrapping.** Streamlit's `st.container(border=True)` doesn't natively support click handlers on the whole surface. We inject raw HTML with `unsafe_allow_html=True`: the tile is rendered as an `<a>` tag wrapping styled `<div>` content. A `<style>` block injected once per page adds `:hover` effects. Navigation uses `st.query_params` + `st.switch_page`.

6. **BikeReg scraping is best-effort, not a hard dependency.** The feature degrades gracefully: real course map -> location area map -> no map. We do not block tile rendering on scraping results.

---

## Implementation

### File: `raceanalyzer/db/models.py` -- Add INDIVIDUAL_TT enum value

Add one line to the `FinishType` enum:

```python
class FinishType(enum.Enum):
    BUNCH_SPRINT = "bunch_sprint"
    SMALL_GROUP_SPRINT = "small_group_sprint"
    BREAKAWAY = "breakaway"
    BREAKAWAY_SELECTIVE = "breakaway_selective"
    REDUCED_SPRINT = "reduced_sprint"
    GC_SELECTIVE = "gc_selective"
    INDIVIDUAL_TT = "individual_tt"          # <-- NEW
    MIXED = "mixed"
    UNKNOWN = "unknown"
```

Because SQLite stores enum values as strings, adding a new value requires no migration -- existing rows are unaffected. The `INDIVIDUAL_TT` value is placed before `MIXED`/`UNKNOWN` to keep the "real" classifications grouped together.

---

### File: `raceanalyzer/classification/finish_type.py` -- Individual TT detection

Add a pre-classification function and integrate it into `classify_finish_type`:

```python
import re
import statistics
from dataclasses import dataclass

from raceanalyzer.classification.grouping import RiderGroup
from raceanalyzer.db.models import FinishType, RaceType


# Keywords that signal an individual time trial or hill climb format
_ITT_NAME_PATTERNS = re.compile(
    r"(?i)\b(time\s*trial|hill\s*climb|hillclimb|chrono|"
    r"individual\s+tt|itt\b|contre.la.montre)",
)

# RaceType enum values that always indicate individual TT format
_ITT_RACE_TYPES = {RaceType.TIME_TRIAL, RaceType.HILL_CLIMB}


def is_individual_tt(
    race_name: str,
    race_type: RaceType | None,
    groups: list[RiderGroup],
    total_finishers: int,
) -> bool:
    """Detect whether a category should be classified as Individual TT.

    Three independent signals (OR logic):

    1. Name-based: race name contains TT/time trial/hill climb keywords.
    2. Type-based: race_type is TIME_TRIAL or HILL_CLIMB.
    3. Statistical: group structure shows evenly-spaced individual finishers.
       Triggered when ALL of:
         - num_groups / total_finishers > 0.7 (most riders finish alone)
         - total_finishers >= 5 (need enough data)
         - stdev of consecutive gaps is low relative to mean gap
           (gap_cv < 0.6, meaning gaps are regular rather than random)

    The statistical check catches TTs/hill climbs that have unusual names
    or missing race_type metadata.
    """
    # Signal 1: Name keywords
    if _ITT_NAME_PATTERNS.search(race_name):
        return True

    # Signal 2: RaceType enum
    if race_type in _ITT_RACE_TYPES:
        return True

    # Signal 3: Statistical fingerprint
    if not groups or total_finishers < 5:
        return False

    num_groups = len(groups)
    group_ratio = num_groups / total_finishers

    if group_ratio <= 0.7:
        return False

    # Compute stdev of consecutive inter-group gaps
    consecutive_gaps = []
    for g in groups:
        if g.gap_to_next is not None:
            consecutive_gaps.append(g.gap_to_next)

    if len(consecutive_gaps) < 3:
        return False

    mean_gap = statistics.mean(consecutive_gaps)
    if mean_gap <= 0:
        return False

    gap_stdev = statistics.stdev(consecutive_gaps)
    gap_cv = gap_stdev / mean_gap

    # Low CV means evenly spaced (staggered start), high CV means random
    # bunch-racing fragmentation. Threshold 0.6 is conservative.
    return gap_cv < 0.6


def classify_finish_type(
    groups: list[RiderGroup],
    total_finishers: int,
    gap_threshold_used: float = 3.0,
    race_name: str = "",
    race_type: RaceType | None = None,
) -> ClassificationResult:
    """Apply rule-based decision tree to grouped results.

    Now includes Individual TT pre-check before the standard decision tree.
    """
    if not groups or total_finishers == 0:
        return ClassificationResult(
            finish_type=FinishType.UNKNOWN,
            confidence=1.0,
            metrics={"reason": "no_time_data"},
        )

    # --- Individual TT pre-check ---
    if is_individual_tt(race_name, race_type, groups, total_finishers):
        # Compute standard metrics for storage even though we short-circuit
        group_sizes = [len(g.riders) for g in groups]
        all_times = []
        for g in groups:
            for r in g.riders:
                t = getattr(r, "race_time_seconds", None)
                if t is not None:
                    all_times.append(t)
        cv_of_times = 0.0
        if len(all_times) > 1:
            mean = statistics.mean(all_times)
            if mean > 0:
                cv_of_times = statistics.stdev(all_times) / mean

        return ClassificationResult(
            finish_type=FinishType.INDIVIDUAL_TT,
            confidence=0.95,
            metrics={
                "num_finishers": total_finishers,
                "num_groups": len(groups),
                "largest_group_size": max(group_sizes),
                "largest_group_ratio": round(max(group_sizes) / total_finishers, 4),
                "leader_group_size": len(groups[0].riders),
                "gap_to_second_group": round(
                    groups[0].gap_to_next if groups[0].gap_to_next else 0.0, 2
                ),
                "cv_of_times": round(cv_of_times, 6),
                "gap_threshold_used": gap_threshold_used,
                "reason": "individual_tt_detected",
            },
        )

    # --- Standard decision tree (existing logic, unchanged) ---
    # ... (rest of function remains the same)
```

**Why these thresholds?**

- `group_ratio > 0.7`: In a 20-rider TT, the 3-second gap grouping typically produces 14+ groups (ratio ~0.7+). In a bunch sprint, even a fragmented one, the ratio rarely exceeds 0.5. The 0.7 threshold gives clear separation.
- `gap_cv < 0.6`: TT riders start at regular intervals (typically 30s-2min), so their finish-time gaps reflect this regularity plus some noise. The CV of consecutive gaps in a TT is typically 0.2-0.5. In a GC-selective road race that fragments into many groups, the gaps are random (CV 0.8-1.5+).
- `total_finishers >= 5`: Below 5 riders, the statistical signals are too noisy to trust.

**Important signature change**: `classify_finish_type` gains two optional parameters (`race_name`, `race_type`) that are empty/None by default for backward compatibility. Callers that want ITT detection must pass these. The pipeline code that calls the classifier will need updating to pass race metadata.

---

### File: `raceanalyzer/queries.py` -- Overall finish type + display names

#### Add INDIVIDUAL_TT to display names

```python
FINISH_TYPE_DISPLAY_NAMES = {
    "bunch_sprint": "Bunch Sprint",
    "small_group_sprint": "Small Group Sprint",
    "breakaway": "Breakaway",
    "breakaway_selective": "Breakaway Selective",
    "reduced_sprint": "Reduced Sprint",
    "gc_selective": "GC Selective",
    "individual_tt": "Individual TT",          # <-- NEW
    "mixed": "Mixed",
    "unknown": "Unknown",
}
```

#### Modify `get_race_tiles` to compute overall finish type

Replace the current `get_race_tiles` with a version that joins to `race_classifications` and aggregates:

```python
from collections import Counter

def get_race_tiles(
    session: Session,
    *,
    year: Optional[int] = None,
    states: Optional[list[str]] = None,
    limit: int = 200,
) -> pd.DataFrame:
    """Return race tile data with overall finish type classification.

    The overall_finish_type is the most common non-UNKNOWN finish type
    across all categories for a race. Ties are broken by the category
    with the most finishers. If all categories are UNKNOWN, the overall
    is "unknown".

    Columns: id, name, date, location, state_province, race_type,
    course_lat, course_lon, num_categories, overall_finish_type.
    """
    # Base query: all races with optional filters
    query = session.query(Race).options()

    if year is not None:
        query = query.filter(func.strftime("%Y", Race.date) == str(year))
    if states:
        query = query.filter(Race.state_province.in_(states))

    query = query.order_by(Race.date.desc()).limit(limit)
    races = query.all()

    columns = [
        "id", "name", "date", "location", "state_province",
        "race_type", "course_lat", "course_lon", "num_categories",
        "overall_finish_type",
    ]
    if not races:
        return pd.DataFrame(columns=columns)

    # Batch-load classifications for all race IDs
    race_ids = [r.id for r in races]
    classifications = (
        session.query(
            RaceClassification.race_id,
            RaceClassification.finish_type,
            RaceClassification.num_finishers,
        )
        .filter(RaceClassification.race_id.in_(race_ids))
        .all()
    )

    # Build per-race classification map
    race_classifications: dict[int, list[tuple]] = {}
    for race_id, ft, num_finishers in classifications:
        race_classifications.setdefault(race_id, []).append(
            (ft.value if ft else "unknown", num_finishers or 0)
        )

    data = []
    for race in races:
        cats = race_classifications.get(race.id, [])
        overall_ft = _compute_overall_finish_type(cats)

        data.append({
            "id": race.id,
            "name": race.name,
            "date": race.date,
            "location": race.location,
            "state_province": race.state_province,
            "race_type": race.race_type.value if race.race_type else None,
            "course_lat": race.course_lat,
            "course_lon": race.course_lon,
            "num_categories": len(cats),
            "overall_finish_type": overall_ft,
        })

    return pd.DataFrame(data, columns=columns)


def _compute_overall_finish_type(
    category_types: list[tuple[str, int]],
) -> str:
    """Pick the overall finish type from a list of (finish_type, num_finishers) tuples.

    Strategy: most common non-UNKNOWN type. Ties broken by sum of finishers
    for that type (larger fields are more reliable).
    """
    if not category_types:
        return "unknown"

    non_unknown = [(ft, nf) for ft, nf in category_types if ft != "unknown"]
    if not non_unknown:
        return "unknown"

    # Count occurrences and sum finishers per type
    type_counts: dict[str, int] = Counter()
    type_finishers: dict[str, int] = {}
    for ft, nf in non_unknown:
        type_counts[ft] += 1
        type_finishers[ft] = type_finishers.get(ft, 0) + nf

    # Sort by count descending, then by total finishers descending
    ranked = sorted(
        type_counts.keys(),
        key=lambda ft: (type_counts[ft], type_finishers.get(ft, 0)),
        reverse=True,
    )
    return ranked[0]
```

---

### File: `raceanalyzer/ui/components.py` -- Finish type icons, tooltips, clickable tiles

#### New `FINISH_TYPE_ICONS` dictionary (24x24 SVGs)

Each icon is designed to visually communicate the finish pattern at a glance:

```python
FINISH_TYPE_ICONS: dict[str, str] = {
    # BUNCH_SPRINT: Tightly packed cluster of 5 dots representing a mass sprint.
    # Three dots in front row, two behind -- conveying density and speed.
    "bunch_sprint": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="7" cy="14" r="2.5" fill="#E53935"/>'
        '<circle cx="12" cy="13" r="2.5" fill="#E53935"/>'
        '<circle cx="17" cy="14" r="2.5" fill="#E53935"/>'
        '<circle cx="9" cy="9" r="2.5" fill="#E53935" opacity="0.7"/>'
        '<circle cx="15" cy="9" r="2.5" fill="#E53935" opacity="0.7"/>'
        '<path d="M19 14 L22 12 M19 14 L22 16" stroke="#E53935" '
        'stroke-width="1" opacity="0.4"/>'  # speed lines
        '</svg>'
    ),

    # SMALL_GROUP_SPRINT: A small leading cluster (3 dots) with a gap,
    # then a larger trailing group (3 dots faded). The gap is the key visual.
    "small_group_sprint": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="4" cy="12" r="2" fill="#FB8C00"/>'
        '<circle cx="8" cy="11" r="2" fill="#FB8C00"/>'
        '<circle cx="6" cy="15" r="2" fill="#FB8C00"/>'
        '<line x1="11" y1="8" x2="11" y2="16" stroke="#FB8C00" '
        'stroke-width="1" stroke-dasharray="2,2" opacity="0.5"/>'  # gap line
        '<circle cx="16" cy="12" r="2" fill="#FB8C00" opacity="0.4"/>'
        '<circle cx="20" cy="11" r="2" fill="#FB8C00" opacity="0.4"/>'
        '<circle cx="18" cy="15" r="2" fill="#FB8C00" opacity="0.4"/>'
        '</svg>'
    ),

    # BREAKAWAY: A single bold dot far ahead, dashed line gap, then a pack behind.
    # Conveys the lone rider (or 2-3) off the front with daylight.
    "breakaway": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="4" cy="12" r="3" fill="#1E88E5"/>'
        '<line x1="9" y1="12" x2="14" y2="12" stroke="#1E88E5" '
        'stroke-width="1.5" stroke-dasharray="2,2" opacity="0.5"/>'
        '<circle cx="17" cy="11" r="2" fill="#1E88E5" opacity="0.4"/>'
        '<circle cx="20" cy="12" r="2" fill="#1E88E5" opacity="0.4"/>'
        '<circle cx="17" cy="14" r="2" fill="#1E88E5" opacity="0.4"/>'
        '<circle cx="20" cy="15" r="2" fill="#1E88E5" opacity="0.3"/>'
        '</svg>'
    ),

    # BREAKAWAY_SELECTIVE: Like breakaway but the pack behind is also fragmented.
    # Small lead group, gap, then scattered dots (no coherent bunch).
    "breakaway_selective": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="4" cy="12" r="2.5" fill="#7B1FA2"/>'
        '<circle cx="8" cy="11" r="2" fill="#7B1FA2"/>'
        '<line x1="11" y1="12" x2="13" y2="12" stroke="#7B1FA2" '
        'stroke-width="1" stroke-dasharray="2,2" opacity="0.5"/>'
        '<circle cx="16" cy="10" r="1.5" fill="#7B1FA2" opacity="0.4"/>'
        '<circle cx="19" cy="13" r="1.5" fill="#7B1FA2" opacity="0.3"/>'
        '<circle cx="21" cy="10" r="1.5" fill="#7B1FA2" opacity="0.25"/>'
        '<circle cx="17" cy="16" r="1.5" fill="#7B1FA2" opacity="0.2"/>'
        '</svg>'
    ),

    # REDUCED_SPRINT: A medium-sized front group (4 dots) with a faded tail.
    # Bigger than breakaway but smaller than bunch sprint.
    "reduced_sprint": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="5" cy="12" r="2.5" fill="#00897B"/>'
        '<circle cx="10" cy="11" r="2.5" fill="#00897B"/>'
        '<circle cx="7" cy="8" r="2.5" fill="#00897B" opacity="0.8"/>'
        '<circle cx="12" cy="15" r="2.5" fill="#00897B" opacity="0.8"/>'
        '<circle cx="18" cy="12" r="1.5" fill="#00897B" opacity="0.3"/>'
        '<circle cx="21" cy="11" r="1.5" fill="#00897B" opacity="0.2"/>'
        '</svg>'
    ),

    # GC_SELECTIVE: Many small scattered dots representing a shattered field.
    # No clustering, all spread out -- conveys fragmentation.
    "gc_selective": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="3" cy="12" r="2" fill="#43A047"/>'
        '<circle cx="7" cy="8" r="2" fill="#43A047" opacity="0.8"/>'
        '<circle cx="10" cy="14" r="2" fill="#43A047" opacity="0.65"/>'
        '<circle cx="14" cy="10" r="2" fill="#43A047" opacity="0.5"/>'
        '<circle cx="17" cy="15" r="2" fill="#43A047" opacity="0.4"/>'
        '<circle cx="21" cy="11" r="2" fill="#43A047" opacity="0.3"/>'
        '</svg>'
    ),

    # INDIVIDUAL_TT: A stopwatch/clock face -- universal symbol for time trials.
    # Circle with minute hand and a small "TT" label.
    "individual_tt": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="12" cy="13" r="9" fill="none" stroke="#8E24AA" stroke-width="2"/>'
        '<line x1="12" y1="13" x2="12" y2="7" stroke="#8E24AA" stroke-width="2" '
        'stroke-linecap="round"/>'
        '<line x1="12" y1="13" x2="16" y2="13" stroke="#8E24AA" stroke-width="1.5" '
        'stroke-linecap="round"/>'
        '<rect x="10" y="2" width="4" height="3" rx="1" fill="#8E24AA"/>'
        '</svg>'
    ),

    # MIXED: A question-mark-ish arrangement -- some dots clustered, some not.
    # Conveys ambiguity / no clear pattern.
    "mixed": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="5" cy="10" r="2" fill="#78909C"/>'
        '<circle cx="8" cy="10" r="2" fill="#78909C"/>'
        '<circle cx="13" cy="8" r="2" fill="#78909C" opacity="0.6"/>'
        '<circle cx="11" cy="14" r="2" fill="#78909C" opacity="0.6"/>'
        '<circle cx="18" cy="12" r="2" fill="#78909C" opacity="0.4"/>'
        '<circle cx="20" cy="16" r="2" fill="#78909C" opacity="0.3"/>'
        '</svg>'
    ),

    # UNKNOWN: A gray circle with "?" -- no data available.
    "unknown": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="12" cy="12" r="9" fill="none" stroke="#BDBDBD" stroke-width="2"/>'
        '<text x="12" y="16" text-anchor="middle" font-size="12" '
        'font-weight="bold" fill="#BDBDBD">?</text>'
        '</svg>'
    ),
}

FINISH_TYPE_COLORS = {
    "bunch_sprint": "#E53935",
    "small_group_sprint": "#FB8C00",
    "breakaway": "#1E88E5",
    "breakaway_selective": "#7B1FA2",
    "reduced_sprint": "#00897B",
    "gc_selective": "#43A047",
    "individual_tt": "#8E24AA",
    "mixed": "#78909C",
    "unknown": "#BDBDBD",
}
```

**Icon design rationale**: Every icon uses dots/circles to represent riders. The spatial arrangement of the dots tells the story: bunch sprint = tight cluster, breakaway = one dot ahead of the pack, GC selective = scattered dots, Individual TT = stopwatch (unique since it is not a mass-start format). Opacity gradations show riders fading behind. Each type has a distinct color from Material Design for accessibility.

#### New `FINISH_TYPE_TOOLTIPS` dictionary

```python
FINISH_TYPE_TOOLTIPS: dict[str, str] = {
    "bunch_sprint": (
        "Bunch Sprint -- The whole pack stayed together and sprinted for the "
        "line at the end. Elbows out, hold your line."
    ),
    "small_group_sprint": (
        "Small Group Sprint -- A select group of 6-15 riders got clear and "
        "sprinted amongst themselves. You had to be in the move to contest."
    ),
    "breakaway": (
        "Breakaway -- A handful of riders broke away and the main pack never "
        "caught them. Fortune favors the bold."
    ),
    "breakaway_selective": (
        "Breakaway Selective -- An early move stuck AND the field behind "
        "shattered too. A hard day for everyone."
    ),
    "reduced_sprint": (
        "Reduced Sprint -- The pack got whittled down by attrition. Not "
        "quite a sprint, not quite a breakaway -- a war of attrition."
    ),
    "gc_selective": (
        "GC Selective -- The field was blown to pieces. Many small groups "
        "spread across the road. Hills or crosswinds did the damage."
    ),
    "individual_tt": (
        "Individual TT -- Riders started one at a time and raced against "
        "the clock. Just you, the road, and the pain cave."
    ),
    "mixed": (
        "Mixed -- Different categories had different outcomes, so there is no "
        "single pattern. Check the detail page for a per-category breakdown."
    ),
    "unknown": (
        "Unknown -- No finish time data is available for this race, so we "
        "cannot determine the finish type. Results may only have placements."
    ),
}
```

#### New `render_finish_type_icon` function

```python
def render_finish_type_icon(finish_type: Optional[str]) -> str:
    """Return inline SVG string for the given finish type.

    Does NOT call st.markdown -- returns the raw SVG for embedding in HTML.
    """
    if finish_type and finish_type in FINISH_TYPE_ICONS:
        return FINISH_TYPE_ICONS[finish_type]
    return FINISH_TYPE_ICONS["unknown"]
```

#### Rewritten `render_race_tile` with clickable surface and tooltip

```python
# Inject once per page render (called in calendar.py before the tile loop)
_TILE_HOVER_CSS = """
<style>
.race-tile {
    display: block;
    text-decoration: none;
    color: inherit;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 8px;
    transition: box-shadow 0.2s ease, transform 0.15s ease;
    cursor: pointer;
    background: white;
}
.race-tile:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    transform: translateY(-2px);
    border-color: #bdbdbd;
}
.race-tile:active {
    transform: translateY(0);
    box-shadow: 0 2px 6px rgba(0,0,0,0.1);
}
.tile-classification {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.8em;
    color: white;
    cursor: help;
}
</style>
"""


def inject_tile_hover_css():
    """Inject the tile hover CSS once per page. Call before rendering tiles."""
    st.markdown(_TILE_HOVER_CSS, unsafe_allow_html=True)


def render_race_tile(tile_row: dict, key_prefix: str = "tile"):
    """Render a single race tile as a fully clickable card with hover effects."""
    finish_type = tile_row.get("overall_finish_type", "unknown")
    color = FINISH_TYPE_COLORS.get(finish_type, "#BDBDBD")
    icon_svg = render_finish_type_icon(finish_type)
    tooltip = FINISH_TYPE_TOOLTIPS.get(finish_type, "")
    display_name = queries.finish_type_display_name(finish_type)

    # Date formatting
    date_str = ""
    if tile_row.get("date"):
        try:
            date_str = f"{tile_row['date']:%b %d, %Y}"
        except (TypeError, ValueError):
            date_str = str(tile_row["date"])

    # Location
    location = tile_row.get("location", "")
    state = tile_row.get("state_province", "")
    loc_str = f"{location}, {state}" if state else location

    # Classification badge with tooltip
    badge_html = (
        f'<span class="tile-classification" '
        f'style="background-color:{color};" '
        f'title="{tooltip}">{display_name}</span>'
    )

    race_id = tile_row["id"]

    # Build tile HTML -- the entire tile is a single clickable unit
    tile_html = f"""
    <div class="race-tile" onclick="
        const params = new URLSearchParams(window.location.search);
        params.set('race_id', '{race_id}');
        const base = window.location.pathname.replace(/\\/[^\\/]*$/, '');
        window.location.href = base + '/race_detail?race_id={race_id}';
    ">
        <div style="display:flex;align-items:center;gap:8px;">
            {icon_svg}
            <strong style="font-size:0.95em;">{tile_row['name']}</strong>
        </div>
        <div style="font-size:0.83em;color:#666;margin-top:6px;">
            {date_str} &middot; {loc_str}
        </div>
        <div style="margin-top:6px;">
            {badge_html}
        </div>
    </div>
    """

    st.markdown(tile_html, unsafe_allow_html=True)

    # Hidden Streamlit button for actual navigation (JS onclick above is
    # enhancement; this hidden button is the reliable fallback via
    # Streamlit's native routing)
    if st.button(
        "Details",
        key=f"{key_prefix}_btn_{race_id}",
        type="secondary",
        # Visually hidden via CSS but still functional
    ):
        st.session_state["selected_race_id"] = int(race_id)
        st.query_params["race_id"] = str(race_id)
        st.switch_page("pages/race_detail.py")
```

**Note on Streamlit routing**: Pure JavaScript `onclick` navigation is fragile in Streamlit's iframe-based architecture. The approach above uses JS for the visual clickable tile but retains a hidden Streamlit `st.button` as the reliable routing mechanism. A cleaner alternative is to use `st.link_button` if available in the installed Streamlit version, or to rely solely on the hidden button and style the entire `st.container` with injected CSS.

---

### File: `raceanalyzer/ui/pages/calendar.py` -- UNKNOWN toggle + updated tile rendering

```python
"""Race Calendar page -- visual tile grid of all PNW races."""

from __future__ import annotations

import streamlit as st

from raceanalyzer import queries
from raceanalyzer.ui.components import (
    inject_tile_hover_css,
    render_empty_state,
    render_race_tile,
    render_sidebar_filters,
)

TILES_PER_PAGE = 12


def render():
    session = st.session_state.db_session
    filters = render_sidebar_filters(session)

    st.title("PNW Race Calendar")

    df = queries.get_race_tiles(session, year=filters["year"], states=filters["states"])

    if df.empty:
        render_empty_state(
            "No races found. Try adjusting your filters or run "
            "`raceanalyzer scrape` to import data."
        )
        return

    # --- UNKNOWN toggle ---
    total_count = len(df)
    unknown_count = len(df[df["overall_finish_type"] == "unknown"])
    classified_count = total_count - unknown_count

    show_unknown = st.toggle(
        f"Show unclassified races ({unknown_count} hidden)",
        value=False,
    )

    if not show_unknown:
        df = df[df["overall_finish_type"] != "unknown"]

    if df.empty:
        render_empty_state(
            "All races are unclassified. Toggle 'Show unclassified races' "
            "to see them, or run `raceanalyzer classify` to classify."
        )
        return

    # Metrics row
    col1, col2, col3 = st.columns(3)
    col1.metric("Classified Races", classified_count)
    col2.metric("Total Races", total_count)
    dated = df[df["date"].notna()]
    if not dated.empty:
        col3.metric(
            "Date Range",
            f"{dated['date'].min():%b %Y} -- {dated['date'].max():%b %Y}",
        )

    # Inject hover CSS once
    inject_tile_hover_css()

    # Pagination state
    if "tile_page_size" not in st.session_state:
        st.session_state.tile_page_size = TILES_PER_PAGE
    visible_count = st.session_state.tile_page_size

    # Tile grid (3 columns)
    visible_df = df.head(visible_count)
    for row_start in range(0, len(visible_df), 3):
        cols = st.columns(3)
        for col_idx in range(3):
            idx = row_start + col_idx
            if idx < len(visible_df):
                with cols[col_idx]:
                    tile_data = visible_df.iloc[idx].to_dict()
                    render_race_tile(tile_data, key_prefix=f"cal_{idx}")

    # Show more button
    if visible_count < len(df):
        remaining = len(df) - visible_count
        if st.button(f"Show more ({remaining} remaining)"):
            st.session_state.tile_page_size = visible_count + TILES_PER_PAGE
            st.rerun()


render()
```

---

### File: `raceanalyzer/ui/pages/race_detail.py` -- Back button + course map

Add a back button at the top and a course map section:

```python
def render():
    session = st.session_state.db_session

    # --- Back navigation ---
    if st.button("Back to Calendar"):
        st.switch_page("pages/calendar.py")

    # ... (rest of existing render function) ...

    # --- Course Map Section (new, after header) ---
    st.divider()
    st.subheader("Course Map")

    course_map_url = None
    if race.get("url"):
        from raceanalyzer.scraper.course_maps import get_course_map_url
        course_map_url = get_course_map_url(race["url"])

    if course_map_url:
        # Embed RideWithGPS or Strava map
        if "ridewithgps.com" in course_map_url:
            # RideWithGPS provides an embed URL
            route_id = course_map_url.rstrip("/").split("/")[-1]
            embed_url = f"https://ridewithgps.com/embeds?type=route&id={route_id}"
            st.markdown(
                f'<iframe src="{embed_url}" width="100%" height="400" '
                f'frameborder="0" allowfullscreen></iframe>',
                unsafe_allow_html=True,
            )
        elif "strava.com" in course_map_url:
            route_id = course_map_url.rstrip("/").split("/")[-1]
            embed_url = f"https://www.strava.com/routes/{route_id}/embed"
            st.markdown(
                f'<iframe src="{embed_url}" width="100%" height="400" '
                f'frameborder="0" allowfullscreen></iframe>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f"[View course map]({course_map_url})")
    else:
        # Fallback: area map centered on race location
        location = race.get("location", "")
        state = race.get("state_province", "")
        if location:
            search_query = f"{location}, {state}" if state else location
            osm_url = (
                f"https://www.openstreetmap.org/export/embed.html"
                f"?bbox=-125,42,-116,49&layer=mapnik"
                f"&marker=47.6,-122.3"  # default to Seattle area
            )
            st.markdown(
                f'<iframe src="{osm_url}" width="100%" height="300" '
                f'frameborder="0"></iframe>',
                unsafe_allow_html=True,
            )
            st.caption(f"Area map for {search_query}. No course route available.")
        else:
            st.info("No course map or location data available for this race.")
```

**Note**: The fallback map uses a hardcoded PNW bounding box. A more precise version would geocode the `location` string, but that requires an external geocoding API. The hardcoded PNW region is adequate for an MVP since all data is PNW races.

---

### File: `raceanalyzer/scraper/course_maps.py` -- NEW: BikeReg course map scraper

```python
"""Best-effort course map URL extraction from BikeReg race pages.

Attempts to find RideWithGPS or Strava route links embedded in BikeReg
event pages. Returns None if no map link is found or if scraping fails.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Patterns for course map URLs we care about
_MAP_URL_PATTERNS = [
    re.compile(r"https?://ridewithgps\.com/routes/\d+", re.IGNORECASE),
    re.compile(r"https?://(?:www\.)?strava\.com/routes/\d+", re.IGNORECASE),
    re.compile(r"https?://ridewithgps\.com/ambassador_routes/\d+", re.IGNORECASE),
]

# road-results race URL -> BikeReg registration URL pattern
# road-results.com/race/{id} pages sometimes link to bikereg registration
_BIKEREG_LINK_PATTERN = re.compile(
    r"https?://(?:www\.)?bikereg\.com/[\w-]+", re.IGNORECASE
)

_REQUEST_HEADERS = {
    "User-Agent": (
        "RaceAnalyzer/1.0 (PNW cycling analysis tool; "
        "contact: github.com/raceanalyzer)"
    ),
}

_REQUEST_TIMEOUT = 10  # seconds


def get_course_map_url(race_page_url: str) -> Optional[str]:
    """Attempt to find a course map URL by scraping the race page and BikeReg.

    Strategy:
    1. Fetch the road-results race page.
    2. Scan for direct RideWithGPS/Strava links on the page.
    3. If none found, look for a BikeReg link on the page.
    4. If a BikeReg link is found, fetch that page and scan for map links.
    5. Return the first map URL found, or None.

    This is best-effort -- any network error, timeout, or missing data
    returns None silently (logged at DEBUG level).
    """
    try:
        # Step 1-2: Check the race page itself
        map_url = _scan_page_for_map_urls(race_page_url)
        if map_url:
            return map_url

        # Step 3-4: Look for BikeReg link, then scan BikeReg page
        bikereg_url = _find_bikereg_link(race_page_url)
        if bikereg_url:
            map_url = _scan_page_for_map_urls(bikereg_url)
            if map_url:
                return map_url

    except Exception:
        logger.debug("Course map scraping failed for %s", race_page_url, exc_info=True)

    return None


def _scan_page_for_map_urls(url: str) -> Optional[str]:
    """Fetch a page and scan all links/text for map URLs."""
    try:
        resp = requests.get(url, headers=_REQUEST_HEADERS, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Check all <a> href attributes
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        for pattern in _MAP_URL_PATTERNS:
            match = pattern.search(href)
            if match:
                return _validate_map_url(match.group(0))

    # Also check raw page text for URLs (some pages embed them outside <a> tags)
    page_text = soup.get_text()
    for pattern in _MAP_URL_PATTERNS:
        match = pattern.search(page_text)
        if match:
            return _validate_map_url(match.group(0))

    return None


def _find_bikereg_link(race_page_url: str) -> Optional[str]:
    """Fetch a page and find a BikeReg registration link."""
    try:
        resp = requests.get(
            race_page_url, headers=_REQUEST_HEADERS, timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    for a_tag in soup.find_all("a", href=True):
        if _BIKEREG_LINK_PATTERN.match(a_tag["href"]):
            return a_tag["href"]

    return None


def _validate_map_url(url: str) -> Optional[str]:
    """Ensure the URL points to a known, safe domain."""
    safe_domains = {"ridewithgps.com", "www.strava.com", "strava.com"}
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.hostname and parsed.hostname.lower() in safe_domains:
            return url
    except Exception:
        pass
    return None
```

---

### File: `raceanalyzer/classification/pipeline.py` (or wherever `classify_finish_type` is called)

The caller must be updated to pass `race_name` and `race_type` to the classifier:

```python
# Before (current call pattern):
result = classify_finish_type(groups, total_finishers, gap_threshold)

# After:
result = classify_finish_type(
    groups,
    total_finishers,
    gap_threshold_used=gap_threshold,
    race_name=race.name,
    race_type=race.race_type,
)
```

---

### File: `tests/test_finish_type.py` -- New Individual TT test cases

```python
class TestIndividualTT:
    """Tests for Individual TT detection."""

    def test_name_detection_time_trial(self):
        """Race name containing 'Time Trial' -> INDIVIDUAL_TT."""
        group = _make_group(1, 3600.0, spread=0)
        group.gap_to_next = 45.0
        groups = [group]
        for i in range(9):
            g = _make_group(1, 3645.0 + i * 45, spread=0)
            g.gap_to_next = 45.0 if i < 8 else None
            groups.append(g)

        result = classify_finish_type(
            groups, total_finishers=10,
            race_name="Mercer Island Time Trial",
            race_type=None,
        )
        assert result.finish_type == FinishType.INDIVIDUAL_TT

    def test_name_detection_hill_climb(self):
        """Race name containing 'Hill Climb' -> INDIVIDUAL_TT."""
        groups = [_make_group(1, 3600.0 + i * 30, spread=0) for i in range(15)]
        for i, g in enumerate(groups):
            g.gap_to_next = 30.0 if i < 14 else None

        result = classify_finish_type(
            groups, total_finishers=15,
            race_name="Mt. Tabor Hill Climb",
            race_type=None,
        )
        assert result.finish_type == FinishType.INDIVIDUAL_TT

    def test_race_type_detection(self):
        """race_type=TIME_TRIAL -> INDIVIDUAL_TT even without name keywords."""
        groups = [_make_group(1, 3600.0 + i * 60, spread=0) for i in range(8)]
        for i, g in enumerate(groups):
            g.gap_to_next = 60.0 if i < 7 else None

        result = classify_finish_type(
            groups, total_finishers=8,
            race_name="Seward Park Classic",  # no TT keywords
            race_type=RaceType.TIME_TRIAL,
        )
        assert result.finish_type == FinishType.INDIVIDUAL_TT

    def test_statistical_detection(self):
        """Evenly spaced solo finishers -> INDIVIDUAL_TT via statistics."""
        # 20 riders, each finishing ~30s apart with low variance
        import random
        random.seed(42)
        groups = []
        for i in range(20):
            g = _make_group(1, 3600.0 + i * 30 + random.uniform(-3, 3), spread=0)
            groups.append(g)
        for i in range(19):
            groups[i].gap_to_next = (
                groups[i + 1].min_time - groups[i].max_time
            )
        groups[-1].gap_to_next = None

        result = classify_finish_type(
            groups, total_finishers=20,
            race_name="Portland Omnium Stage 3",  # no TT keywords
            race_type=RaceType.ROAD_RACE,  # wrong type
        )
        assert result.finish_type == FinishType.INDIVIDUAL_TT

    def test_no_false_positive_gc_selective(self):
        """A GC-selective road race should NOT be classified as Individual TT."""
        # Many groups but with irregular gaps (CV > 0.6)
        groups = []
        gaps = [5, 45, 8, 90, 12, 120, 4]  # highly variable
        base = 3600.0
        for i in range(8):
            g = _make_group(3, base, spread=2.0)
            if i < 7:
                g.gap_to_next = float(gaps[i])
                base += 2.0 + gaps[i]
            else:
                g.gap_to_next = None
            groups.append(g)

        result = classify_finish_type(
            groups, total_finishers=24,
            race_name="Mt. Hood Classic Road Race",
            race_type=RaceType.ROAD_RACE,
        )
        # 8 groups / 24 finishers = 0.33, below 0.7 threshold
        assert result.finish_type != FinishType.INDIVIDUAL_TT

    def test_backward_compatible_no_race_name(self):
        """Calling without race_name/race_type still works (no ITT detection)."""
        group = _make_group(30, 3600.0, spread=2.0)
        group.gap_to_next = None
        result = classify_finish_type([group], total_finishers=30)
        assert result.finish_type == FinishType.BUNCH_SPRINT
```

---

## Files Summary

| File | Action | Changes |
|------|--------|---------|
| `raceanalyzer/db/models.py` | MODIFY | Add `INDIVIDUAL_TT = "individual_tt"` to `FinishType` enum |
| `raceanalyzer/classification/finish_type.py` | MODIFY | Add `is_individual_tt()` function with 3-signal detection; add `race_name`/`race_type` params to `classify_finish_type()`; short-circuit to INDIVIDUAL_TT when detected |
| `raceanalyzer/queries.py` | MODIFY | Add `"individual_tt"` to `FINISH_TYPE_DISPLAY_NAMES`; rewrite `get_race_tiles()` to compute `overall_finish_type` via plurality vote; add `_compute_overall_finish_type()` helper |
| `raceanalyzer/ui/components.py` | MODIFY | Add `FINISH_TYPE_ICONS` (9 SVG icons), `FINISH_TYPE_COLORS`, `FINISH_TYPE_TOOLTIPS`; add `render_finish_type_icon()`, `inject_tile_hover_css()`; rewrite `render_race_tile()` for clickable tiles with tooltips |
| `raceanalyzer/ui/pages/calendar.py` | MODIFY | Add `st.toggle` for UNKNOWN races; call `inject_tile_hover_css()`; update metrics row to show classified vs total counts |
| `raceanalyzer/ui/pages/race_detail.py` | MODIFY | Add "Back to Calendar" button at top; add course map section with iframe embed or OSM fallback |
| `raceanalyzer/scraper/course_maps.py` | CREATE | `get_course_map_url()` with multi-step scraping: race page -> BikeReg page -> RideWithGPS/Strava URL extraction; `_validate_map_url()` for domain allowlisting |
| `tests/test_finish_type.py` | MODIFY | Add `TestIndividualTT` class with 6 test cases covering name, type, statistical, false-positive, and backward-compat scenarios |
| `tests/test_course_maps.py` | CREATE | Tests for URL extraction logic using mocked HTTP responses |
| `tests/test_queries.py` | MODIFY | Test `_compute_overall_finish_type()` with various tie-breaking scenarios |
| Classification pipeline caller | MODIFY | Pass `race_name` and `race_type` to `classify_finish_type()` |

---

## Definition of Done

- [ ] `FinishType` enum contains `INDIVIDUAL_TT` value
- [ ] `is_individual_tt()` correctly detects TTs via name keywords (case-insensitive)
- [ ] `is_individual_tt()` correctly detects TTs via `race_type` enum (TIME_TRIAL, HILL_CLIMB)
- [ ] `is_individual_tt()` correctly detects TTs via statistical fingerprint (group_ratio > 0.7, gap_cv < 0.6)
- [ ] GC-selective races with many groups are NOT falsely classified as Individual TT
- [ ] `classify_finish_type()` remains backward-compatible (no `race_name`/`race_type` = no ITT check)
- [ ] `get_race_tiles()` returns `overall_finish_type` column computed via plurality vote
- [ ] Tiles display finish-type SVG icons (9 distinct designs) instead of race-type icons
- [ ] Each tile shows a colored classification badge (e.g., "Bunch Sprint" in red)
- [ ] Hovering over a classification badge shows a casual tooltip explaining the type
- [ ] UNKNOWN-classified races are hidden by default; toggle reveals them with count label
- [ ] Clicking anywhere on a tile navigates to that race's detail page
- [ ] Tiles have a subtle lift/shadow hover effect
- [ ] Race detail page has a "Back to Calendar" button that navigates correctly
- [ ] Race detail page shows a course map (iframe) when a RideWithGPS/Strava URL is found
- [ ] Race detail page falls back to an area map when no course URL is found
- [ ] Course map scraping fails silently (no error shown to user)
- [ ] All existing tests pass; 6+ new test cases for Individual TT detection
- [ ] No new dependencies beyond `beautifulsoup4` (already likely present)

---

## Risks

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| BikeReg has Cloudflare protection or blocks scrapers | High | Medium | The scraper is best-effort. Use a descriptive User-Agent, respect robots.txt, and rate limit. If blocked, the fallback OSM area map is shown. Do NOT use cloudscraper for BikeReg -- if basic requests fails, accept the fallback. |
| Individual TT statistical detection false positives | Medium | Low | The 0.7 group_ratio threshold is conservative (most road races peak at 0.3-0.5). The gap_cv < 0.6 requirement filters out random fragmentation. Combined with `total_finishers >= 5`, false positives are unlikely. Monitor and tune post-launch. |
| Streamlit JS onclick navigation is unreliable | Medium | Medium | The clickable tile uses injected JavaScript, which Streamlit may sandbox or strip. The hidden `st.button` serves as a fallback. Test across Streamlit versions. Consider `st.link_button` if available. |
| Overall finish type plurality vote hides nuance | Low | High | This is by design -- the tile is a summary. The detail page still shows per-category classifications. Document that the overall type is a simplification. |
| OpenStreetMap embed tiles may be slow or rate-limited | Low | Low | OSM embeds are lightweight. If needed, switch to a static image via the OSM tile server. |
| Course map iframes may not render in all Streamlit deployments | Medium | Low | Streamlit Cloud and local both support `unsafe_allow_html` iframes. Test in target deployment. If blocked, degrade to a clickable link. |

---

## Security Considerations

1. **URL allowlisting for scraped map links.** The `_validate_map_url()` function checks that any scraped URL points to `ridewithgps.com` or `strava.com` before embedding it in an iframe. This prevents open-redirect or XSS attacks via malicious URLs injected into BikeReg pages.

2. **Iframe sandboxing.** All embedded iframes should include the `sandbox` attribute with only necessary permissions (`sandbox="allow-scripts allow-same-origin"`) to prevent the embedded page from navigating the parent frame or accessing cookies.

3. **HTML injection in tile content.** Race names, locations, and other database-sourced strings must be HTML-escaped before embedding in `st.markdown(unsafe_allow_html=True)` blocks. Use `html.escape()` on all dynamic content.

4. **Responsible scraping.** The course map scraper uses a descriptive `User-Agent` identifying the tool, a 10-second timeout, and does not retry aggressively. It should respect `robots.txt` (add a check if feasible).

5. **No credentials stored.** The course map scraping uses only public, unauthenticated HTTP requests. No API keys or tokens are involved.

---

## Dependencies

| Package | Version | Purpose | Status |
|---------|---------|---------|--------|
| `beautifulsoup4` | >=4.12 | HTML parsing for BikeReg page scraping | Likely already installed (used by parsers.py); verify |
| `requests` | >=2.28 | HTTP client for course map fetching | Already in requirements |
| `streamlit` | >=1.28 | `st.toggle` requires 1.28+; verify current version | Already in requirements |

No heavy new dependencies. The `beautifulsoup4` package is the only potential addition and is lightweight.

---

## Open Questions

1. **Plurality vote vs. weighted vote for overall finish type.** The draft proposes plurality (most common type wins). An alternative is to weight by confidence score or number of finishers. Should we implement the simpler plurality first and iterate, or go straight to a weighted approach?

2. **Should the "Back to Calendar" button preserve the user's pagination state and filter selections?** The current proposal uses `st.switch_page` which resets the page. Preserving state would require encoding filters in query params and restoring them on return.

3. **How should we handle races where the name says "Time Trial" but the results show a bunch finish?** (e.g., a team time trial or a misnamed event.) The current proposal would classify it as INDIVIDUAL_TT based on the name match alone. Should the statistical check be used to *override* the name check in such cases?

4. **Is `beautifulsoup4` already in the project's dependencies?** The existing `parsers.py` likely uses it for road-results HTML parsing. Need to verify before adding.

5. **Should we geocode the `location` string for a more accurate fallback map?** A geocoding API call (e.g., Nominatim) would give precise lat/lon for the area map. The current proposal uses a hardcoded PNW bounding box. Geocoding adds an external API dependency but is much more useful.

6. **Should the UNKNOWN toggle count be based on races or classifications?** The draft counts races, but a race can have a mix of UNKNOWN and non-UNKNOWN categories. The `overall_finish_type` already handles this (it shows the most common non-UNKNOWN type), so the toggle effectively hides races where ALL categories are UNKNOWN. Is this the right behavior?
