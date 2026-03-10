# Sprint 005: Classification-Centric Tiles, Navigation, and Maps

*Codex Draft -- Independent perspective for synthesis review*

## Overview

Sprint 005 reorients the entire calendar experience around **finish type classification** instead of event type. Today a user sees "Road Race" or "Criterium" on each tile, but that tells them nothing about what actually happened. After this sprint, tiles will show "Bunch Sprint" or "Breakaway" with an icon that conveys the race's character, a casual tooltip for non-cyclists, and a clickable surface that navigates to the detail page.

The sprint also introduces a 9th `FinishType` -- `INDIVIDUAL_TT` -- for time trials and hill climbs where riders start at intervals rather than en masse. Rather than detecting this purely through name keywords (which is brittle and misses edge cases), this draft proposes a **statistical spacing algorithm**: in a TT, the ratio of `num_groups` to `total_finishers` approaches 1.0 because nearly every rider finishes alone, and the standard deviation of consecutive inter-rider gaps is low because riders leave at fixed intervals (typically 30s or 60s). This is a fundamentally different signal from a mass-start race where the gap distribution is bimodal (tight within groups, large between groups).

For maps, this draft is skeptical of bikereg scraping as a reliable source and proposes a concrete fallback-first strategy using Nominatim geocoding of the race location string to place a static OpenStreetMap tile. Course-specific maps from RideWithGPS/Strava become an enhancement layer, not a blocker.

For the "overall" race classification shown on tiles, this draft proposes using the **highest-confidence classification** across categories rather than the most frequent. A Cat 3 bunch sprint classified at 0.9 confidence is more informative than a Cat 4/5 MIXED at 0.5, even if MIXED appears in more categories.

The tile grid itself moves from `st.columns` to **CSS Grid via `st.markdown` HTML injection**, giving us real hover effects, click targets that span the full tile, and responsive layout without fighting Streamlit's column model.

## Use Cases

1. **UC-1: Individual TT Detection** -- When a race is a time trial or hill climb (whether by name or by the statistical signature of its results), every category is classified as `INDIVIDUAL_TT` instead of being misclassified as GC_SELECTIVE or MIXED.

2. **UC-2: Classification-Driven Tiles** -- A user scanning the calendar sees a finish-type icon (not event-type icon) and an overall classification label on each tile, immediately conveying the race's character.

3. **UC-3: Hidden UNKNOWN Races** -- The 12+ races lacking time data (101 UNKNOWN classifications) are hidden by default. A toggle reveals them for completeness.

4. **UC-4: Full-Tile Click Navigation** -- Clicking anywhere on a tile navigates to the race detail page. No more hunting for a small "View Details" button.

5. **UC-5: Casual Tooltips** -- A non-cyclist friend hovering over "GC Selective" sees "The race blew apart on a climb -- small groups everywhere, no pack left." Every finish type has a tooltip written in plain conversational language.

6. **UC-6: Back Navigation with State Preservation** -- The race detail page has a "Back to Calendar" action that returns the user to the tile grid with their filters (year, state, page position) intact via `st.query_params`.

7. **UC-7: Location-Based Maps** -- Each race tile and detail page shows a map centered on the race location. If the race has course coordinates, those are overlaid. If not, a location pin on an OpenStreetMap tile provides geographic context.

8. **UC-8: Overall Classification via Confidence** -- Each tile displays the single most confident classification across all categories for that race, providing the most reliable characterization.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Streamlit App                             │
│                                                                  │
│  ┌──────────────────────┐    ┌───────────────────────────────┐   │
│  │  calendar.py          │    │  race_detail.py               │   │
│  │  - CSS Grid tiles     │◄───│  - Back btn (query_params)    │   │
│  │  - UNKNOWN toggle     │    │  - Course map (OSM fallback)  │   │
│  │  - Finish-type icons  │    │  - Classifications + tooltips │   │
│  └──────────┬───────────┘    └───────────────┬───────────────┘   │
│             │                                │                   │
│  ┌──────────▼────────────────────────────────▼───────────────┐   │
│  │                    components.py                           │   │
│  │  - FINISH_TYPE_ICONS (SVG dict)                           │   │
│  │  - FINISH_TYPE_TOOLTIPS (casual text dict)                │   │
│  │  - FINISH_TYPE_COLORS (color dict)                        │   │
│  │  - render_tile_grid() -- CSS Grid HTML injection          │   │
│  │  - render_location_map() -- OSM static tile               │   │
│  └──────────┬────────────────────────────────────────────────┘   │
│             │                                                    │
│  ┌──────────▼────────────────────────────────────────────────┐   │
│  │                     queries.py                             │   │
│  │  - get_race_tiles() + overall_finish_type (max confidence) │   │
│  │  - get_race_detail() (unchanged)                          │   │
│  │  - FINISH_TYPE_DISPLAY_NAMES + INDIVIDUAL_TT              │   │
│  └──────────┬────────────────────────────────────────────────┘   │
│             │                                                    │
│  ┌──────────▼────────────────────────────────────────────────┐   │
│  │              classification/finish_type.py                 │   │
│  │  - is_individual_tt() -- spacing algorithm                │   │
│  │  - classify_finish_type() -- existing decision tree       │   │
│  └──────────┬────────────────────────────────────────────────┘   │
│             │                                                    │
│  ┌──────────▼────────────────────────────────────────────────┐   │
│  │                    db/models.py                            │   │
│  │  - FinishType.INDIVIDUAL_TT enum value                    │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │               maps.py (new utility)                       │   │
│  │  - geocode_location() -- Nominatim                        │   │
│  │  - build_osm_map_url() -- static tile URL                 │   │
│  │  - fetch_course_map_url() -- bikereg (best-effort)        │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

Key architectural decisions that differ from the Gemini draft:

- **CSS Grid over `st.columns`**: Streamlit columns do not support click handlers or hover pseudo-classes. CSS Grid via HTML injection gives full control over tile interactivity.
- **Highest-confidence over most-frequent**: A race with 3 categories classified as MIXED (0.5 confidence each) and 1 classified as BREAKAWAY (0.8 confidence) should show BREAKAWAY on the tile -- that is the classification we are most certain about.
- **Nominatim-first maps over bikereg-first**: Bikereg scraping is speculative and fragile. Every race has a location string, so geocoding always works. Course maps from RideWithGPS/Strava are a bonus.
- **Spacing algorithm over keyword matching for TT detection**: Keywords miss races named "Maryhill Loops" (a well-known hill climb) or "Mutual of Enumclaw" (a TT). The statistical signature is race-format-agnostic.

## Implementation

### 1. `raceanalyzer/db/models.py` -- Add INDIVIDUAL_TT

Add the new enum value after MIXED, before UNKNOWN:

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

No schema migration needed -- SQLAlchemy stores enum values as strings in SQLite, so adding a new value is backwards-compatible.

### 2. `raceanalyzer/classification/finish_type.py` -- Spacing-Based TT Detection

The core insight: in a TT, riders leave at fixed intervals (30s, 60s, 90s). The inter-rider gaps in the results approximate a uniform distribution. In a mass-start race, gaps cluster near zero (within groups) and are large (between groups) -- a bimodal distribution.

Two complementary signals:
1. **Group fragmentation ratio**: `num_groups / total_finishers`. In a TT this approaches 1.0 (every rider is their own "group"). In a bunch sprint this approaches 0.0 (one big group). Threshold: > 0.7.
2. **Gap uniformity**: The coefficient of variation (stdev/mean) of consecutive inter-rider time gaps. In a TT, gaps are relatively uniform (CV < 0.8). In a mass-start race, the CV is high because gaps vary wildly between "0 seconds within a group" and "30+ seconds between groups". Threshold: CV < 0.8.

Additionally, a metadata pre-check uses `race.race_type` as a strong prior when available.

```python
import statistics
from raceanalyzer.db.models import FinishType, RaceType


def is_individual_tt(
    groups: list[RiderGroup],
    total_finishers: int,
    race_type: RaceType | None = None,
    race_name: str = "",
) -> tuple[bool, float]:
    """Detect individual time trial / hill climb via spacing analysis.

    Returns (is_tt, confidence) tuple.

    Algorithm:
    1. If race_type is TIME_TRIAL or HILL_CLIMB -> (True, 0.95)
    2. If race name contains TT/time trial/hill climb keywords -> (True, 0.85)
    3. Statistical test: group_ratio > 0.7 AND gap_cv < 0.8 -> (True, 0.75)
    4. Otherwise -> (False, 0.0)
    """
    # Signal 1: Race type metadata (strongest signal)
    if race_type in (RaceType.TIME_TRIAL, RaceType.HILL_CLIMB):
        return (True, 0.95)

    # Signal 2: Name keywords (moderate signal, catches cases without race_type)
    name_lower = race_name.lower()
    tt_keywords = ["time trial", "tt ", " tt", "hill climb", "hillclimb", "chrono"]
    if any(kw in name_lower for kw in tt_keywords):
        return (True, 0.85)

    # Signal 3: Statistical spacing analysis (weakest but most general)
    if not groups or total_finishers < 5:
        return (False, 0.0)

    num_groups = len(groups)
    group_ratio = num_groups / total_finishers

    # Calculate CV of consecutive inter-rider gaps
    all_times = []
    for g in groups:
        for r in g.riders:
            t = getattr(r, "race_time_seconds", None)
            if t is not None:
                all_times.append(t)

    if len(all_times) < 5:
        return (False, 0.0)

    all_times.sort()
    consecutive_gaps = [
        all_times[i] - all_times[i - 1] for i in range(1, len(all_times))
    ]
    consecutive_gaps = [g for g in consecutive_gaps if g > 0]  # filter zero gaps

    if not consecutive_gaps:
        return (False, 0.0)

    gap_mean = statistics.mean(consecutive_gaps)
    gap_cv = statistics.stdev(consecutive_gaps) / gap_mean if gap_mean > 0 else float("inf")

    if group_ratio > 0.7 and gap_cv < 0.8:
        return (True, 0.75)

    return (False, 0.0)
```

Modify `classify_finish_type` to call the TT check first:

```python
def classify_finish_type(
    groups: list[RiderGroup],
    total_finishers: int,
    gap_threshold_used: float = 3.0,
    race_type: RaceType | None = None,
    race_name: str = "",
) -> ClassificationResult:
    """Apply rule-based decision tree to grouped results."""
    if not groups or total_finishers == 0:
        return ClassificationResult(
            finish_type=FinishType.UNKNOWN,
            confidence=1.0,
            metrics={"reason": "no_time_data"},
        )

    # Pre-check: Individual TT detection
    is_tt, tt_confidence = is_individual_tt(
        groups, total_finishers, race_type, race_name,
    )
    if is_tt:
        # Still compute metrics for debugging
        metrics = _compute_metrics(groups, total_finishers, gap_threshold_used)
        metrics["tt_detection_method"] = (
            "race_type" if tt_confidence >= 0.95
            else "name_keyword" if tt_confidence >= 0.85
            else "spacing_analysis"
        )
        return ClassificationResult(
            finish_type=FinishType.INDIVIDUAL_TT,
            confidence=tt_confidence,
            metrics=metrics,
        )

    # ... existing decision tree unchanged ...
```

Extract a `_compute_metrics` helper from the existing body to keep things clean:

```python
def _compute_metrics(
    groups: list[RiderGroup],
    total_finishers: int,
    gap_threshold_used: float,
) -> dict:
    """Extract group-structure metrics for storage and debugging."""
    group_sizes = [len(g.riders) for g in groups]
    largest_group_size = max(group_sizes)
    largest_group_ratio = largest_group_size / total_finishers
    leader_group_size = len(groups[0].riders)
    gap_to_second = groups[0].gap_to_next if groups[0].gap_to_next is not None else 0.0

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

    return {
        "num_finishers": total_finishers,
        "num_groups": len(groups),
        "largest_group_size": largest_group_size,
        "largest_group_ratio": round(largest_group_ratio, 4),
        "leader_group_size": leader_group_size,
        "gap_to_second_group": round(gap_to_second, 2),
        "cv_of_times": round(cv_of_times, 6),
        "gap_threshold_used": gap_threshold_used,
    }
```

### 3. `raceanalyzer/queries.py` -- Overall Classification via Max Confidence

Add `INDIVIDUAL_TT` to the display names:

```python
FINISH_TYPE_DISPLAY_NAMES = {
    "bunch_sprint": "Bunch Sprint",
    "small_group_sprint": "Small Group Sprint",
    "breakaway": "Breakaway",
    "breakaway_selective": "Breakaway Selective",
    "reduced_sprint": "Reduced Sprint",
    "gc_selective": "GC Selective",
    "mixed": "Mixed",
    "individual_tt": "Individual TT",  # NEW
    "unknown": "Unknown",
}
```

Modify `get_race_tiles` to compute the overall finish type. Rather than SQL aggregation (which cannot easily express "highest confidence"), we post-process in Python:

```python
def get_race_tiles(
    session: Session,
    *,
    year: Optional[int] = None,
    states: Optional[list[str]] = None,
    limit: int = 200,
) -> pd.DataFrame:
    """Return race tile data with overall finish type (highest confidence)."""
    query = session.query(
        Race.id,
        Race.name,
        Race.date,
        Race.location,
        Race.state_province,
        Race.race_type,
        Race.course_lat,
        Race.course_lon,
    )

    if year is not None:
        query = query.filter(func.strftime("%Y", Race.date) == str(year))
    if states:
        query = query.filter(Race.state_province.in_(states))

    query = query.order_by(Race.date.desc()).limit(limit)
    races = query.all()

    if not races:
        return pd.DataFrame(columns=[
            "id", "name", "date", "location", "state_province",
            "race_type", "course_lat", "course_lon",
            "overall_finish_type", "overall_confidence", "num_categories",
        ])

    race_ids = [r.id for r in races]

    # Fetch all classifications for these races in one query
    settings = Settings()
    classifications = (
        session.query(RaceClassification)
        .filter(RaceClassification.race_id.in_(race_ids))
        .all()
    )

    # Group by race_id, pick highest-confidence non-UNKNOWN classification
    from collections import defaultdict
    race_class_map: dict[int, tuple[str, float]] = {}
    race_cat_counts: dict[int, int] = defaultdict(int)

    for c in classifications:
        race_cat_counts[c.race_id] += 1
        ft_value = c.finish_type.value if c.finish_type else "unknown"
        if ft_value == "unknown":
            continue

        # Reconstruct confidence from the classification metrics
        # We use cv_of_times to derive confidence via the same logic
        # the classifier used. For stored classifications, we can
        # approximate confidence from the finish type rules.
        confidence = _estimate_confidence_from_metrics(c)

        current = race_class_map.get(c.race_id)
        if current is None or confidence > current[1]:
            race_class_map[c.race_id] = (ft_value, confidence)

    data = []
    for r in races:
        ft_info = race_class_map.get(r.id, ("unknown", 0.0))
        data.append({
            "id": r.id,
            "name": r.name,
            "date": r.date,
            "location": r.location,
            "state_province": r.state_province,
            "race_type": r.race_type.value if r.race_type else None,
            "course_lat": r.course_lat,
            "course_lon": r.course_lon,
            "overall_finish_type": ft_info[0],
            "overall_confidence": ft_info[1],
            "num_categories": race_cat_counts.get(r.id, 0),
        })

    return pd.DataFrame(data)


def _estimate_confidence_from_metrics(c: RaceClassification) -> float:
    """Estimate the classifier's confidence from stored metrics.

    This reconstructs the approximate confidence that classify_finish_type()
    would have returned. It uses the same heuristics as the decision tree.
    """
    ft = c.finish_type.value if c.finish_type else "unknown"
    lgr = c.largest_group_ratio or 0.0
    num_groups = c.num_groups or 0

    confidence_map = {
        "bunch_sprint": 0.9 if lgr > 0.8 else 0.75,
        "breakaway": 0.8,
        "breakaway_selective": 0.8,
        "small_group_sprint": 0.75,
        "gc_selective": 0.7,
        "reduced_sprint": 0.65,
        "individual_tt": 0.85,
        "mixed": 0.5,
        "unknown": 0.0,
    }
    conf = confidence_map.get(ft, 0.5)
    if num_groups == 1:
        conf = min(conf + 0.1, 1.0)
    return conf
```

**Note**: Ideally the classifier would store its confidence score in the `race_classifications` table. A future sprint should add a `confidence` column. For now, we reconstruct it from the metrics.

### 4. `raceanalyzer/ui/components.py` -- Finish-Type Icons, Tooltips, CSS Grid Tiles

#### New Constants

Replace `RACE_TYPE_ICONS` and `RACE_TYPE_COLORS` with finish-type equivalents:

```python
FINISH_TYPE_ICONS: dict[str, str] = {
    "bunch_sprint": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="8" cy="12" r="2.5" fill="#E53935"/>'
        '<circle cx="12" cy="10" r="2.5" fill="#E53935"/>'
        '<circle cx="12" cy="14" r="2.5" fill="#E53935"/>'
        '<circle cx="16" cy="12" r="2.5" fill="#E53935"/>'
        '<circle cx="12" cy="12" r="2.5" fill="#E53935"/>'
        '</svg>'
    ),
    "small_group_sprint": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="7" cy="12" r="2" fill="#FB8C00"/>'
        '<circle cx="11" cy="11" r="2" fill="#FB8C00"/>'
        '<circle cx="11" cy="13" r="2" fill="#FB8C00"/>'
        '<line x1="14" y1="12" x2="18" y2="12" stroke="#FB8C00" stroke-width="1" stroke-dasharray="2,2"/>'
        '<circle cx="20" cy="12" r="1.5" fill="#FB8C00" opacity="0.4"/>'
        '</svg>'
    ),
    "breakaway": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="5" cy="12" r="2.5" fill="#1E88E5"/>'
        '<line x1="9" y1="12" x2="15" y2="12" stroke="#1E88E5" stroke-width="1" stroke-dasharray="3,2"/>'
        '<circle cx="18" cy="11" r="1.5" fill="#1E88E5" opacity="0.4"/>'
        '<circle cx="18" cy="13" r="1.5" fill="#1E88E5" opacity="0.4"/>'
        '<circle cx="20" cy="12" r="1.5" fill="#1E88E5" opacity="0.4"/>'
        '</svg>'
    ),
    "breakaway_selective": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="4" cy="12" r="2" fill="#7B1FA2"/>'
        '<circle cx="8" cy="12" r="2" fill="#7B1FA2"/>'
        '<line x1="11" y1="12" x2="16" y2="12" stroke="#7B1FA2" stroke-width="1" stroke-dasharray="3,2"/>'
        '<circle cx="19" cy="11" r="1.5" fill="#7B1FA2" opacity="0.5"/>'
        '<circle cx="21" cy="13" r="1.5" fill="#7B1FA2" opacity="0.3"/>'
        '</svg>'
    ),
    "reduced_sprint": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="6" cy="12" r="2" fill="#43A047"/>'
        '<circle cx="10" cy="11" r="2" fill="#43A047"/>'
        '<circle cx="10" cy="13" r="2" fill="#43A047"/>'
        '<circle cx="14" cy="12" r="2" fill="#43A047"/>'
        '<line x1="17" y1="12" x2="22" y2="12" stroke="#43A047" stroke-width="1" stroke-dasharray="2,2"/>'
        '</svg>'
    ),
    "gc_selective": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="3" cy="12" r="1.5" fill="#FF7043"/>'
        '<circle cx="7" cy="10" r="1.5" fill="#FF7043"/>'
        '<circle cx="11" cy="13" r="1.5" fill="#FF7043"/>'
        '<circle cx="15" cy="11" r="1.5" fill="#FF7043"/>'
        '<circle cx="19" cy="14" r="1.5" fill="#FF7043"/>'
        '<circle cx="22" cy="10" r="1.5" fill="#FF7043"/>'
        '</svg>'
    ),
    "individual_tt": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="12" cy="12" r="9" fill="none" stroke="#8E24AA" stroke-width="2"/>'
        '<line x1="12" y1="12" x2="12" y2="5" stroke="#8E24AA" stroke-width="2" '
        'stroke-linecap="round"/>'
        '<line x1="12" y1="12" x2="17" y2="12" stroke="#8E24AA" stroke-width="1.5" '
        'stroke-linecap="round"/>'
        '<circle cx="12" cy="12" r="1.5" fill="#8E24AA"/>'
        '</svg>'
    ),
    "mixed": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="5" cy="8" r="1.5" fill="#78909C"/>'
        '<circle cx="9" cy="14" r="2" fill="#78909C"/>'
        '<circle cx="13" cy="10" r="1.5" fill="#78909C"/>'
        '<circle cx="17" cy="16" r="2.5" fill="#78909C"/>'
        '<circle cx="20" cy="8" r="1.5" fill="#78909C"/>'
        '</svg>'
    ),
    "unknown": (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="12" cy="12" r="8" fill="none" stroke="#9E9E9E" stroke-width="2"/>'
        '<text x="12" y="16" text-anchor="middle" font-size="12" fill="#9E9E9E">?</text>'
        '</svg>'
    ),
}

FINISH_TYPE_COLORS: dict[str, str] = {
    "bunch_sprint": "#E53935",
    "small_group_sprint": "#FB8C00",
    "breakaway": "#1E88E5",
    "breakaway_selective": "#7B1FA2",
    "reduced_sprint": "#43A047",
    "gc_selective": "#FF7043",
    "individual_tt": "#8E24AA",
    "mixed": "#78909C",
    "unknown": "#9E9E9E",
}

FINISH_TYPE_TOOLTIPS: dict[str, str] = {
    "bunch_sprint": (
        "The whole pack stayed together and sprinted for the finish line "
        "in a giant mass of riders. Think NASCAR but on bikes."
    ),
    "small_group_sprint": (
        "A small group broke away from the main pack and then sprinted "
        "against each other at the end. Like a breakaway in basketball "
        "but with more lycra."
    ),
    "breakaway": (
        "One or two gutsy riders escaped from the pack early and held on "
        "to win. The pack was chasing but never caught them."
    ),
    "breakaway_selective": (
        "A few riders got away AND the pack behind fell apart too. "
        "It was a hard day for everyone -- the course chewed people up."
    ),
    "reduced_sprint": (
        "The race was hard enough that a lot of riders got dropped, but "
        "a decent-sized group still sprinted at the finish. Survival of "
        "the fittest, then a sprint."
    ),
    "gc_selective": (
        "The race blew apart on a climb -- small groups everywhere, no "
        "big pack left. Like a mountain stage in the Tour de France."
    ),
    "individual_tt": (
        "Riders started one at a time and raced against the clock, not "
        "each other. No drafting, no group tactics -- just you vs. the "
        "stopwatch."
    ),
    "mixed": (
        "The finish pattern did not clearly match any single type. Might "
        "have been a weird race, or the data is a bit fuzzy."
    ),
    "unknown": (
        "We do not have enough timing data to figure out what happened "
        "in this race. It might have been exciting -- we just cannot tell."
    ),
}
```

#### CSS Grid Tile Renderer

Replace `render_race_tile` with a CSS Grid approach. The key advantage: the entire tile is a single `<a>` tag, making it fully clickable without JavaScript.

```python
_TILE_GRID_CSS = """
<style>
.ra-tile-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
    padding: 0.5rem 0;
}
@media (max-width: 768px) {
    .ra-tile-grid {
        grid-template-columns: repeat(2, 1fr);
    }
}
@media (max-width: 480px) {
    .ra-tile-grid {
        grid-template-columns: 1fr;
    }
}
.ra-tile {
    display: block;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 1rem;
    text-decoration: none;
    color: inherit;
    transition: box-shadow 0.2s ease, transform 0.15s ease;
    background: white;
    cursor: pointer;
}
.ra-tile:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    transform: translateY(-2px);
}
.ra-tile-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
}
.ra-tile-name {
    font-weight: 600;
    font-size: 0.95em;
    line-height: 1.2;
    flex: 1;
}
.ra-tile-meta {
    font-size: 0.8em;
    color: #666;
    margin-bottom: 0.5rem;
}
.ra-tile-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.75em;
    color: white;
}
</style>
"""


def render_tile_grid(tiles: list[dict]) -> None:
    """Render all tiles as a CSS Grid with clickable cards.

    Each tile dict should have: id, name, date, location, state_province,
    overall_finish_type, overall_confidence.
    """
    html_parts = [_TILE_GRID_CSS, '<div class="ra-tile-grid">']

    for tile in tiles:
        ft = tile.get("overall_finish_type", "unknown")
        color = FINISH_TYPE_COLORS.get(ft, "#9E9E9E")
        icon_svg = FINISH_TYPE_ICONS.get(ft, FINISH_TYPE_ICONS["unknown"])
        tooltip = FINISH_TYPE_TOOLTIPS.get(ft, "")
        display_name = FINISH_TYPE_DISPLAY_NAMES.get(
            ft, ft.replace("_", " ").title()
        )

        date_str = ""
        if tile.get("date"):
            try:
                date_str = f"{tile['date']:%b %d, %Y}"
            except (TypeError, ValueError):
                date_str = str(tile["date"])

        location = tile.get("location", "")
        state = tile.get("state_province", "")
        loc_str = f"{location}, {state}" if state else location

        # Build the tile's query param URL
        race_url = f"?race_id={tile['id']}&page=race_detail"

        # Escape HTML in name
        safe_name = (tile.get("name") or "Race").replace("&", "&amp;").replace("<", "&lt;")

        html_parts.append(f'''
        <a class="ra-tile" href="{race_url}" target="_self"
           onclick="window.parent.postMessage({{type:'streamlit:setQueryParam',key:'race_id',value:'{tile["id"]}'}}, '*'); return true;">
          <div class="ra-tile-header">
            {icon_svg}
            <span class="ra-tile-name">{safe_name}</span>
          </div>
          <div class="ra-tile-meta">{date_str} &middot; {loc_str}</div>
          <span class="ra-tile-badge" style="background-color:{color};"
                title="{tooltip}">{display_name}</span>
        </a>
        ''')

    html_parts.append('</div>')
    st.markdown("\n".join(html_parts), unsafe_allow_html=True)
```

**Important caveat**: Streamlit's `st.markdown` with `unsafe_allow_html=True` renders inside an iframe. The `<a>` tags with query params will not trigger Streamlit navigation directly. We need a companion mechanism:

```python
def _handle_tile_click() -> bool:
    """Check if a tile was clicked via query params and navigate."""
    race_id = st.query_params.get("race_id")
    page = st.query_params.get("page")
    if race_id and page == "race_detail":
        st.session_state["selected_race_id"] = int(race_id)
        st.switch_page("pages/race_detail.py")
        return True
    return False
```

This function is called at the top of `calendar.py`'s `render()`. When a user clicks a tile, the URL changes, Streamlit reruns, and the click handler catches the query param.

**Fallback**: If the CSS Grid + anchor approach proves unreliable in Streamlit's iframe model, we fall back to `st.columns` with `st.button` but style the container with hover CSS. The CSS injection still improves the visual experience even without full-tile clickability.

#### Finish Type Display Names (imported from queries)

```python
from raceanalyzer.queries import FINISH_TYPE_DISPLAY_NAMES
```

### 5. `raceanalyzer/ui/pages/calendar.py` -- UNKNOWN Toggle + CSS Grid

```python
"""Race Calendar page -- visual tile grid of all PNW races."""

from __future__ import annotations

import streamlit as st

from raceanalyzer import queries
from raceanalyzer.ui.components import (
    _handle_tile_click,
    render_empty_state,
    render_sidebar_filters,
    render_tile_grid,
)

TILES_PER_PAGE = 12


def render():
    session = st.session_state.db_session

    # Handle tile click navigation via query params
    if _handle_tile_click():
        return

    filters = render_sidebar_filters(session)

    st.title("PNW Race Calendar")

    df = queries.get_race_tiles(session, year=filters["year"], states=filters["states"])

    if df.empty:
        render_empty_state(
            "No races found. Try adjusting your filters or run "
            "`raceanalyzer scrape` to import data."
        )
        return

    # UNKNOWN toggle
    show_unknown = st.toggle("Show races without classification data", value=False)
    if not show_unknown:
        df = df[df["overall_finish_type"] != "unknown"]

    if df.empty:
        render_empty_state(
            "All races have unknown classifications. "
            "Toggle 'Show races without classification data' to see them."
        )
        return

    # Metrics row
    col1, col2, col3 = st.columns(3)
    col1.metric("Classified Races", len(df))
    col2.metric("States/Provinces", df["state_province"].nunique())
    dated = df[df["date"].notna()]
    if not dated.empty:
        col3.metric(
            "Date Range",
            f"{dated['date'].min():%b %Y} -- {dated['date'].max():%b %Y}",
        )

    # Pagination
    if "tile_page_size" not in st.session_state:
        st.session_state.tile_page_size = TILES_PER_PAGE
    visible_count = st.session_state.tile_page_size

    visible_df = df.head(visible_count)
    tile_dicts = [row.to_dict() for _, row in visible_df.iterrows()]

    # Render CSS Grid tiles
    render_tile_grid(tile_dicts)

    # Show more button
    if visible_count < len(df):
        remaining = len(df) - visible_count
        if st.button(f"Show more ({remaining} remaining)"):
            st.session_state.tile_page_size = visible_count + TILES_PER_PAGE
            st.rerun()


render()
```

### 6. `raceanalyzer/ui/pages/race_detail.py` -- Back Navigation with State Preservation

Add back navigation at the top of the page. Use `st.query_params` to preserve the user's filter state:

```python
def render():
    session = st.session_state.db_session

    # Back navigation -- preserves filter state via query params
    if st.button("Back to Calendar"):
        # Clear the race_id param but keep filter params
        params = dict(st.query_params)
        params.pop("race_id", None)
        params.pop("page", None)
        st.query_params.update(params)
        st.switch_page("pages/calendar.py")

    # ... rest of existing render() unchanged ...
```

To preserve filter state, `calendar.py`'s `render_sidebar_filters` should store filter selections in query params:

```python
# In render_sidebar_filters or calendar.py render():
# When filters change, update query params
if year is not None:
    st.query_params["year"] = str(year)
elif "year" in st.query_params:
    del st.query_params["year"]
```

And when the calendar loads, it reads from query params to restore filter state:

```python
# In calendar.py, restore filter state from query params
saved_year = st.query_params.get("year")
if saved_year:
    filters["year"] = int(saved_year)
```

### 7. `raceanalyzer/ui/maps.py` (New File) -- Nominatim Geocoding + OSM Static Map

```python
"""Map utilities: geocoding via Nominatim + static OpenStreetMap tiles.

This module provides location-based maps as a reliable fallback when
course-specific map data (RideWithGPS, Strava) is unavailable.
"""

from __future__ import annotations

import urllib.parse
from typing import Optional

import requests
import streamlit as st

# Nominatim requires a descriptive User-Agent per their usage policy
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = "RaceAnalyzer/0.1 (PNW cycling analysis tool)"

# Cache geocoding results to avoid repeat API calls
_geocode_cache: dict[str, Optional[tuple[float, float]]] = {}


def geocode_location(location: str, state: str = "") -> Optional[tuple[float, float]]:
    """Geocode a location string to (lat, lon) using Nominatim.

    Caches results in-memory to minimize API calls.
    Returns None if geocoding fails.
    """
    query = f"{location}, {state}" if state else location
    if query in _geocode_cache:
        return _geocode_cache[query]

    try:
        resp = requests.get(
            _NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": _USER_AGENT},
            timeout=5,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            lat = float(results[0]["lat"])
            lon = float(results[0]["lon"])
            _geocode_cache[query] = (lat, lon)
            return (lat, lon)
    except (requests.RequestException, ValueError, KeyError, IndexError):
        pass

    _geocode_cache[query] = None
    return None


def build_osm_map_html(
    lat: float,
    lon: float,
    zoom: int = 12,
    width: int = 300,
    height: int = 200,
    marker: bool = True,
) -> str:
    """Build an OpenStreetMap iframe embed for a location.

    Uses the OpenStreetMap embed API which requires no API key.
    """
    bbox_delta = 0.05 * (18 - zoom)  # Rough bounding box from zoom
    bbox = f"{lon - bbox_delta},{lat - bbox_delta},{lon + bbox_delta},{lat + bbox_delta}"

    if marker:
        marker_param = f"&marker={lat},{lon}"
    else:
        marker_param = ""

    return (
        f'<iframe width="{width}" height="{height}" frameborder="0" '
        f'scrolling="no" marginheight="0" marginwidth="0" '
        f'src="https://www.openstreetmap.org/export/embed.html?'
        f'bbox={bbox}&layer=mapnik{marker_param}" '
        f'style="border: 1px solid #ccc; border-radius: 4px;">'
        f'</iframe>'
    )


def render_location_map(
    location: Optional[str],
    state: Optional[str] = None,
    course_lat: Optional[str] = None,
    course_lon: Optional[str] = None,
) -> None:
    """Render a map for a race location. Uses course coords if available,
    falls back to geocoded location, or shows nothing.
    """
    # If we have course coordinates, use those (existing Plotly path)
    if course_lat and course_lon:
        from raceanalyzer.ui.components import _build_mini_course_map
        fig = _build_mini_course_map(course_lat, course_lon)
        st.plotly_chart(fig, use_container_width=True)
        return

    # Fallback: geocode the location and show an OSM embed
    if location:
        coords = geocode_location(location, state or "")
        if coords:
            html = build_osm_map_html(coords[0], coords[1])
            st.markdown(html, unsafe_allow_html=True)
```

### 8. Tests -- `tests/test_individual_tt.py`

```python
"""Tests for Individual TT detection in the finish type classifier."""

from __future__ import annotations

import pytest

from raceanalyzer.classification.finish_type import (
    ClassificationResult,
    classify_finish_type,
    is_individual_tt,
)
from raceanalyzer.classification.grouping import RiderGroup
from raceanalyzer.db.models import FinishType, RaceType


class FakeRider:
    def __init__(self, race_time_seconds: float):
        self.race_time_seconds = race_time_seconds


def _make_tt_groups(n_riders: int = 20, interval: float = 60.0) -> list[RiderGroup]:
    """Create groups typical of a TT: each rider in their own group."""
    groups = []
    for i in range(n_riders):
        t = 3600.0 + i * interval + (i % 3) * 5  # slight variation
        rider = FakeRider(race_time_seconds=t)
        gap = interval - (i % 3) * 5 + ((i + 1) % 3) * 5 if i < n_riders - 1 else None
        groups.append(RiderGroup(riders=[rider], min_time=t, max_time=t, gap_to_next=gap))
    return groups


def _make_bunch_sprint_groups(n_riders: int = 40) -> list[RiderGroup]:
    """Create groups typical of a bunch sprint: one big group."""
    riders = [FakeRider(race_time_seconds=3600.0 + i * 0.5) for i in range(n_riders)]
    return [RiderGroup(riders=riders, min_time=3600.0, max_time=3600.0 + n_riders * 0.5, gap_to_next=None)]


class TestIsIndividualTT:
    def test_race_type_time_trial(self):
        groups = _make_tt_groups()
        is_tt, confidence = is_individual_tt(groups, 20, race_type=RaceType.TIME_TRIAL)
        assert is_tt is True
        assert confidence == 0.95

    def test_race_type_hill_climb(self):
        groups = _make_tt_groups()
        is_tt, confidence = is_individual_tt(groups, 20, race_type=RaceType.HILL_CLIMB)
        assert is_tt is True
        assert confidence == 0.95

    def test_name_keyword_time_trial(self):
        groups = _make_tt_groups()
        is_tt, confidence = is_individual_tt(
            groups, 20, race_name="Mutual of Enumclaw Time Trial"
        )
        assert is_tt is True
        assert confidence == 0.85

    def test_statistical_detection_tt_spacing(self):
        groups = _make_tt_groups(n_riders=20, interval=60.0)
        is_tt, confidence = is_individual_tt(groups, 20)
        assert is_tt is True
        assert confidence == 0.75

    def test_bunch_sprint_not_detected_as_tt(self):
        groups = _make_bunch_sprint_groups()
        is_tt, _ = is_individual_tt(groups, 40)
        assert is_tt is False

    def test_too_few_finishers_returns_false(self):
        groups = _make_tt_groups(n_riders=3, interval=60.0)
        is_tt, _ = is_individual_tt(groups, 3)
        assert is_tt is False


class TestClassifyFinishTypeWithTT:
    def test_tt_takes_priority_over_decision_tree(self):
        groups = _make_tt_groups()
        result = classify_finish_type(
            groups, 20, race_type=RaceType.TIME_TRIAL,
        )
        assert result.finish_type == FinishType.INDIVIDUAL_TT
        assert result.confidence == 0.95

    def test_bunch_sprint_unchanged(self):
        groups = _make_bunch_sprint_groups()
        result = classify_finish_type(groups, 40)
        assert result.finish_type == FinishType.BUNCH_SPRINT
```

## Files Summary

| File | Action | Description |
|------|--------|-------------|
| `raceanalyzer/db/models.py` | Modify | Add `INDIVIDUAL_TT = "individual_tt"` to `FinishType` enum |
| `raceanalyzer/classification/finish_type.py` | Modify | Add `is_individual_tt()` function with spacing algorithm; modify `classify_finish_type()` to call it first; extract `_compute_metrics()` helper |
| `raceanalyzer/queries.py` | Modify | Add `INDIVIDUAL_TT` to display names; rewrite `get_race_tiles()` to return `overall_finish_type` via highest-confidence logic; add `_estimate_confidence_from_metrics()` |
| `raceanalyzer/ui/components.py` | Modify | Replace `RACE_TYPE_ICONS`/`RACE_TYPE_COLORS` with `FINISH_TYPE_ICONS`/`FINISH_TYPE_COLORS`/`FINISH_TYPE_TOOLTIPS`; add `render_tile_grid()` with CSS Grid; add `_handle_tile_click()`; keep old functions for backward compat |
| `raceanalyzer/ui/pages/calendar.py` | Modify | Add UNKNOWN toggle; replace `st.columns` tile loop with `render_tile_grid()`; add `_handle_tile_click()` call; restore filters from query params |
| `raceanalyzer/ui/pages/race_detail.py` | Modify | Add "Back to Calendar" button that preserves filter state via query params |
| `raceanalyzer/ui/maps.py` | Create | `geocode_location()` via Nominatim; `build_osm_map_html()` for OSM embed; `render_location_map()` with course-coords-or-geocode fallback |
| `tests/test_individual_tt.py` | Create | Unit tests for TT detection (metadata, keyword, statistical) and integration with `classify_finish_type()` |

## Definition of Done

- [ ] `FinishType.INDIVIDUAL_TT` exists in the enum and is stored/retrieved correctly
- [ ] `is_individual_tt()` detects TTs via race_type metadata (confidence 0.95)
- [ ] `is_individual_tt()` detects TTs via name keywords (confidence 0.85)
- [ ] `is_individual_tt()` detects TTs via spacing analysis when group_ratio > 0.7 and gap_cv < 0.8 (confidence 0.75)
- [ ] `classify_finish_type()` checks for TT before the main decision tree
- [ ] `get_race_tiles()` returns `overall_finish_type` using highest-confidence logic
- [ ] Calendar tiles display finish-type SVG icons instead of race-type icons
- [ ] Each tile shows a classification badge with the finish-type display name
- [ ] Hovering over the badge shows a casual tooltip explaining the finish type
- [ ] UNKNOWN races are hidden by default with a toggle to show them
- [ ] Clicking a tile navigates to the race detail page
- [ ] Race detail page has a "Back to Calendar" button
- [ ] Back navigation preserves filter state (year, state) via query params
- [ ] `render_location_map()` shows an OSM embed when course coords are unavailable
- [ ] Nominatim geocoding uses a proper User-Agent and caches results
- [ ] All 9 finish types have tooltip text
- [ ] All existing tests pass
- [ ] New tests for TT detection cover metadata, keyword, statistical, and negative cases

## Risks

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| CSS Grid tiles do not render clickably inside Streamlit's iframe sandbox | High | Medium | Fallback to `st.columns` + `st.button` with hover CSS only. The CSS Grid code degrades to visual-only styling. |
| Nominatim rate limiting or downtime blocks geocoding | Medium | Low | In-memory cache prevents repeat calls. Show no map rather than error. Nominatim's usage policy allows light use with a User-Agent. |
| `is_individual_tt()` statistical thresholds (0.7 group ratio, 0.8 gap CV) produce false positives on fragmented mass-start races | Medium | Medium | The metadata and keyword checks run first and handle most TTs. Statistical detection is the tertiary fallback. Thresholds should be validated against the 20 real races in the DB. |
| Reconstructing confidence from stored metrics (`_estimate_confidence_from_metrics`) is approximate | Low | High | This is a known approximation. The proper fix is adding a `confidence` column to `race_classifications` in a future sprint. |
| Removing `RACE_TYPE_ICONS` breaks any code that still references them | Medium | Low | Keep the old constants but mark them as deprecated. Search for usages before removing. |
| Bikereg scraping is not implemented in this sprint | Low | N/A | Intentionally deferred. The Nominatim + OSM fallback provides maps for all races with location data. Bikereg scraping can be added later as an enhancement. |

## Security Considerations

- **Nominatim API**: Only sends the race location string (already public data). Uses HTTPS. The User-Agent header is descriptive per Nominatim's usage policy. No API key needed.
- **HTML injection via `st.markdown`**: All user-facing strings (race names, locations) must be HTML-escaped before injection into the CSS Grid template. The implementation uses `.replace("&", "&amp;").replace("<", "&lt;")` on race names.
- **No new external dependencies with elevated privileges**: `requests` is already a project dependency. No new packages are introduced beyond what is already used.
- **Bikereg scraping intentionally omitted**: Avoids introducing scraping of a third-party site with unknown ToS implications in this sprint.

## Dependencies

- `requests` -- already present for the existing road-results scraper
- No new package dependencies

## Open Questions

1. **Confidence column**: Should we add a `confidence: Float` column to `race_classifications` in this sprint to avoid the `_estimate_confidence_from_metrics` approximation? It would be a small schema change but eliminates the reconstruction problem permanently.

2. **CSS Grid feasibility in Streamlit**: Has anyone confirmed that `<a>` tags with `target="_self"` work for navigation within Streamlit's `st.markdown`? If not, we should prototype this early and have the `st.columns` fallback ready.

3. **TT threshold tuning**: The 0.7 group_ratio and 0.8 gap_cv thresholds are theoretically motivated but untested on real data. Should we run the detection against the existing 20 races before committing to these values?

4. **Nominatim caching persistence**: The current in-memory cache is lost on app restart. Should we persist geocoding results in the database (e.g., `geo_lat`/`geo_lon` columns on the `races` table) to avoid repeated API calls?

5. **Tooltip mechanism**: The `title` attribute provides native browser tooltips but they are slow to appear and unstyled. Should we use a CSS-only tooltip (`::after` pseudo-element on hover) for faster, styled tooltips, or is the native `title` good enough for v1?

6. **Filter state in URL**: Storing filters in `st.query_params` means the URL becomes shareable -- a user can send a link to "2024 WA races." Is this desirable behavior or an unintended side effect?
