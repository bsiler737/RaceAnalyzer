# Sprint 003: Synthetic Demo Data

*Codex Draft — Independent perspective for synthesis review*

## Overview

The RaceAnalyzer UI (Sprint 002) works but displays empty states because road-results.com is blocking our IP. This sprint generates synthetic demo data that exercises every UI feature — calendar filtering, race detail with confidence badges, distribution charts, and trend analysis — so we can continue iterating on the UI without waiting for scraping access to resume.

This is intentionally disposable work. The demo data module will be irrelevant once real scraping resumes. The key design decision is therefore **simplicity over extensibility**: a single `raceanalyzer/demo_data.py` module with two public functions (`seed_demo_data` and `clear_demo_data`), wired into the existing Click CLI as `seed-demo` and `clear-demo` commands. No new dependencies, no new tables, no schema changes. The module uses only stdlib `random` with a fixed seed for reproducibility.

The harder problem is making the data *realistic enough* to look credible in the UI. This means:
- Race names that a PNW cyclist would recognize (Banana Belt, Cherry Pie, Mason Lake, Mutual of Enumclaw)
- Time distributions that produce all 8 `FinishType` values when fed through the existing classifier logic
- CV values calibrated to exercise all 3 confidence badge colors (green < 0.005, yellow 0.005-0.02, red >= 0.02)
- A 5-year span (2020-2024) with enough variation to make the trend chart interesting
- ~100 riders with realistic first/last name combinations (not "Rider 1", "Rider 2")

The demo data marks itself for easy removal: all demo race IDs use a high range (90001-90100) that will never collide with real road-results.com IDs, and all demo rider `road_results_id` values use a parallel high range (80001-80200). The `clear-demo` command deletes by this ID range, so it cannot accidentally destroy real data.

## Use Cases

1. **UC-1: Seed Demo Data** — A developer runs `python -m raceanalyzer seed-demo` and the database is populated with ~50 races, ~100 riders, ~2500 results, and ~120 classifications. The command is idempotent: running it twice does not create duplicates (it clears and re-seeds).

2. **UC-2: Clear Demo Data** — A developer runs `python -m raceanalyzer clear-demo` and all demo races, riders, results, and classifications are removed. Real data (if any) is untouched.

3. **UC-3: UI Demonstration** — After seeding, the Streamlit UI shows meaningful data on all 3 pages: the calendar has races across 5 years and 4 states, the detail page shows confidence badges in all 3 colors, and the dashboard shows interesting distribution and trend charts.

4. **UC-4: Reproducible Data** — The random seed is fixed so that every run of `seed-demo` produces identical data. This makes screenshots and test assertions deterministic.

## Architecture

### Module Placement

```
raceanalyzer/
    demo_data.py          # seed_demo_data(), clear_demo_data(), all data tables
    cli.py                # Add seed-demo, clear-demo commands
```

A single module keeps the disposable code contained. When we no longer need demo data, we delete one file and two CLI command registrations.

### Data Design

The demo data is structured around **race templates** — named races that recur annually at the same location, each with a characteristic finish profile. This mirrors real PNW racing, where the same course tends to produce similar outcomes year after year, with some drift.

#### Race Templates (~12 templates, ~50 race instances across 5 years)

| Template | Location | State | Typical Finish Type | Notes |
|----------|----------|-------|-------------------|-------|
| Banana Belt RR | Maryhill | WA | BREAKAWAY / BREAKAWAY_SELECTIVE | Windy, exposed course |
| Cherry Pie Crit | Niles | OR | BUNCH_SPRINT | Classic flat crit |
| Mason Lake RR | Shelton | WA | GC_SELECTIVE | Hilly course |
| Mutual of Enumclaw TT | Enumclaw | WA | GC_SELECTIVE | Hilly TT-style |
| PIR Tuesday Night | Portland | OR | BUNCH_SPRINT / SMALL_GROUP_SPRINT | Flat track |
| Seward Park Crit | Seattle | WA | BUNCH_SPRINT | Flat park crit |
| Tour de Whidbey | Whidbey Island | WA | MIXED | Variable terrain |
| Piece of Cake RR | Ridgefield | WA | REDUCED_SPRINT | Rolling course |
| Gorge Roubaix | The Dalles | OR | BREAKAWAY | Wind + gravel sectors |
| Twilight Criterium | Boise | ID | SMALL_GROUP_SPRINT | Technical crit |
| Tour de Victoria | Victoria | BC | MIXED | Multi-stage |
| Gastown Grand Prix | Vancouver | BC | BUNCH_SPRINT | Downtown crit |

Not every template appears every year. Some are added mid-range (simulating new races), some skip a year (simulating cancellations). This produces ~50 total race instances.

#### Categories (6)

| Category | Typical Field Size |
|----------|-------------------|
| Men Pro/1/2 | 30-60 |
| Men Cat 3 | 25-50 |
| Men Cat 4/5 | 30-70 |
| Women Cat 1/2/3 | 15-35 |
| Masters Men 40+ | 20-40 |
| Masters Men 50+ | 10-25 |

#### Rider Pool (~100 riders)

Names generated from two lists of ~30 first names and ~40 last names, combined randomly. Each rider gets a stable `road_results_id` in the 80001-80200 range. Riders are assigned to 1-3 categories based on a simple age/ability model, so the same rider can appear across races in the same category.

#### Time Distribution Strategy

Each finish type requires a specific time gap pattern. The generator creates results by:

1. Setting a base time for the race (e.g., 3600s for a 1-hour race)
2. Generating finish times according to the target finish type's signature:
   - **BUNCH_SPRINT**: Most riders within 0-3s of winner, tiny gaps between consecutive finishers
   - **SMALL_GROUP_SPRINT**: A lead group of 5-10 within 2s, then a gap, then the rest bunched
   - **BREAKAWAY**: 1-3 riders solo, then 30s+ gap to a large main group
   - **BREAKAWAY_SELECTIVE**: 1-3 riders solo, 30s+ gap, but the remaining field is shattered (no large group)
   - **REDUCED_SPRINT**: A group of 10-20 (but not the full field) together, rest scattered
   - **GC_SELECTIVE**: Many small groups, no dominant bunch, high time spread
   - **MIXED**: Some bunching, some gaps, no clear pattern
   - **UNKNOWN**: Sparse or missing time data

3. Computing `cv_of_times` from the generated times and storing it on the classification
4. Varying the tightness of distributions across years so that CV values span all three confidence tiers:
   - Green (cv < 0.005): Tight bunch sprints, clean breakaways with obvious pattern
   - Yellow (0.005 <= cv < 0.02): Moderate variation, less clear-cut finishes
   - Red (cv >= 0.02): High variation, ambiguous classification

#### Demo ID Ranges

| Entity | ID Range | Rationale |
|--------|----------|-----------|
| Races | 90001-90100 | Well above road-results.com's current max (~15000) |
| Riders | road_results_id 80001-80200 | Same principle, avoids collision |

### Data Flow

```
seed-demo command
       |
       v
  demo_data.seed_demo_data(session)
       |
       +-- 1. clear_demo_data(session)     # idempotent: remove stale demo data
       +-- 2. generate riders              # ~100 riders with realistic names
       +-- 3. for each race template:
       |      for each year:
       |        create Race
       |        for each category:
       |          generate Results with time distribution matching target finish type
       |          create RaceClassification with computed metrics
       +-- 4. session.commit()
       |
       v
  Database populated, UI ready
```

## Implementation

### Phase 1: Demo Data Module (80% of effort)

**File:** `raceanalyzer/demo_data.py` — New file

**Tasks:**

| Task | Description |
|------|-------------|
| 1.1 | Define race templates (name, location, state, target finish types per year) |
| 1.2 | Define rider name pools (first names, last names) and category assignments |
| 1.3 | Implement time distribution generators for each of the 8 finish types |
| 1.4 | Implement metric computation (cv_of_times, num_groups, largest_group_size, etc.) |
| 1.5 | Implement `seed_demo_data(session)` orchestrating all generation |
| 1.6 | Implement `clear_demo_data(session)` deleting by ID range |

**Complete module:**

```python
# raceanalyzer/demo_data.py
"""Synthetic demo data generator for RaceAnalyzer.

Generates ~50 realistic PNW bike races across 5 years (2020-2024) with
~100 riders, all 8 finish types, and varying confidence levels.

This module is disposable — it exists only to hydrate the UI while
road-results.com is blocking our IP.
"""
from __future__ import annotations

import random
import statistics
from datetime import datetime, timedelta
from typing import List, Tuple

from sqlalchemy.orm import Session

from raceanalyzer.db.models import (
    FinishType,
    Race,
    RaceClassification,
    Result,
    Rider,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEMO_RACE_ID_START = 90001
DEMO_RIDER_RR_ID_START = 80001
RANDOM_SEED = 42

FIRST_NAMES: List[str] = [
    "Alex", "Ben", "Carlos", "David", "Erik", "Finn", "Greg", "Henry",
    "Ian", "Jake", "Kyle", "Leo", "Marco", "Nathan", "Oscar", "Paul",
    "Quinn", "Ryan", "Sam", "Tyler", "Victor", "Will", "Yuki", "Zach",
    "Anna", "Beth", "Clara", "Diana", "Elena", "Fiona", "Grace", "Hannah",
]

LAST_NAMES: List[str] = [
    "Anderson", "Baker", "Chen", "Davis", "Evans", "Fischer", "Garcia",
    "Hansen", "Ito", "Jensen", "Kim", "Larsen", "Martinez", "Nelson",
    "Olsen", "Park", "Quinn", "Roberts", "Schmidt", "Tanaka", "Ueda",
    "Vance", "Wang", "Xu", "Yamamoto", "Zhang", "Berg", "Strom",
    "Pedersen", "Nakamura", "Sato", "Lee", "Nguyen", "Patel", "Murphy",
    "Campbell", "Mitchell", "Brooks", "Reed", "Wood",
]

CATEGORIES: List[Tuple[str, int, int]] = [
    # (name, min_field_size, max_field_size)
    ("Men Pro/1/2", 30, 60),
    ("Men Cat 3", 25, 50),
    ("Men Cat 4/5", 30, 70),
    ("Women Cat 1/2/3", 15, 35),
    ("Masters Men 40+", 20, 40),
    ("Masters Men 50+", 10, 25),
]

PNW_TEAMS: List[str] = [
    "Audi Cycling", "Team Breadwinner", "Canyon Velo", "Deschutes Brewery",
    "EP Cycling", "Flat Tire Racing", "Gruppo Sportivo", "Hagens Berman",
    "Team Inertia", "Jet City Velo", "KEXP Racing", "Larch Mountain CC",
    "Metier Racing", "Ninkasi Cycling", "Oly Town Racing", "Project 529",
    "Rad Racing", "SpeedVagen", "Team S&M", "Veloforma",
    "",  # unattached
    "",
    "",
]

# Race templates: (name, location, state, base_month, base_day,
#                   target_finish_types_by_year)
# Each template maps year -> intended FinishType for the primary category.
# Other categories get slight variations.
RACE_TEMPLATES = [
    {
        "name": "Banana Belt RR",
        "location": "Maryhill",
        "state": "WA",
        "month": 3,
        "day": 5,
        "years": {
            2020: FinishType.BREAKAWAY,
            2021: FinishType.BREAKAWAY,
            2022: FinishType.BREAKAWAY_SELECTIVE,
            2023: FinishType.BREAKAWAY,
            2024: FinishType.BREAKAWAY_SELECTIVE,
        },
    },
    {
        "name": "Cherry Pie Crit",
        "location": "Niles",
        "state": "OR",
        "month": 2,
        "day": 19,
        "years": {
            2020: FinishType.BUNCH_SPRINT,
            2021: FinishType.BUNCH_SPRINT,
            2022: FinishType.BUNCH_SPRINT,
            2023: FinishType.SMALL_GROUP_SPRINT,
            2024: FinishType.BUNCH_SPRINT,
        },
    },
    {
        "name": "Mason Lake RR",
        "location": "Shelton",
        "state": "WA",
        "month": 4,
        "day": 12,
        "years": {
            2020: FinishType.GC_SELECTIVE,
            2021: FinishType.GC_SELECTIVE,
            2023: FinishType.GC_SELECTIVE,
            2024: FinishType.REDUCED_SPRINT,
        },
    },
    {
        "name": "Mutual of Enumclaw RR",
        "location": "Enumclaw",
        "state": "WA",
        "month": 5,
        "day": 18,
        "years": {
            2020: FinishType.GC_SELECTIVE,
            2021: FinishType.BREAKAWAY_SELECTIVE,
            2022: FinishType.GC_SELECTIVE,
            2023: FinishType.BREAKAWAY_SELECTIVE,
            2024: FinishType.GC_SELECTIVE,
        },
    },
    {
        "name": "PIR Tuesday Night",
        "location": "Portland",
        "state": "OR",
        "month": 6,
        "day": 10,
        "years": {
            2020: FinishType.BUNCH_SPRINT,
            2021: FinishType.BUNCH_SPRINT,
            2022: FinishType.SMALL_GROUP_SPRINT,
            2023: FinishType.BUNCH_SPRINT,
            2024: FinishType.BUNCH_SPRINT,
        },
    },
    {
        "name": "Seward Park Crit",
        "location": "Seattle",
        "state": "WA",
        "month": 7,
        "day": 20,
        "years": {
            2021: FinishType.BUNCH_SPRINT,
            2022: FinishType.BUNCH_SPRINT,
            2023: FinishType.BUNCH_SPRINT,
            2024: FinishType.SMALL_GROUP_SPRINT,
        },
    },
    {
        "name": "Tour de Whidbey",
        "location": "Whidbey Island",
        "state": "WA",
        "month": 4,
        "day": 26,
        "years": {
            2020: FinishType.MIXED,
            2022: FinishType.REDUCED_SPRINT,
            2023: FinishType.MIXED,
            2024: FinishType.BREAKAWAY,
        },
    },
    {
        "name": "Piece of Cake RR",
        "location": "Ridgefield",
        "state": "WA",
        "month": 8,
        "day": 3,
        "years": {
            2020: FinishType.REDUCED_SPRINT,
            2021: FinishType.REDUCED_SPRINT,
            2022: FinishType.BUNCH_SPRINT,
            2023: FinishType.REDUCED_SPRINT,
            2024: FinishType.SMALL_GROUP_SPRINT,
        },
    },
    {
        "name": "Gorge Roubaix",
        "location": "The Dalles",
        "state": "OR",
        "month": 3,
        "day": 22,
        "years": {
            2020: FinishType.BREAKAWAY,
            2021: FinishType.BREAKAWAY,
            2022: FinishType.BREAKAWAY_SELECTIVE,
            2024: FinishType.BREAKAWAY,
        },
    },
    {
        "name": "Twilight Criterium",
        "location": "Boise",
        "state": "ID",
        "month": 7,
        "day": 4,
        "years": {
            2020: FinishType.SMALL_GROUP_SPRINT,
            2021: FinishType.BUNCH_SPRINT,
            2022: FinishType.SMALL_GROUP_SPRINT,
            2023: FinishType.SMALL_GROUP_SPRINT,
            2024: FinishType.BUNCH_SPRINT,
        },
    },
    {
        "name": "Tour de Victoria",
        "location": "Victoria",
        "state": "BC",
        "month": 6,
        "day": 15,
        "years": {
            2020: FinishType.MIXED,
            2021: FinishType.GC_SELECTIVE,
            2022: FinishType.MIXED,
            2023: FinishType.REDUCED_SPRINT,
            2024: FinishType.MIXED,
        },
    },
    {
        "name": "Gastown Grand Prix",
        "location": "Vancouver",
        "state": "BC",
        "month": 7,
        "day": 10,
        "years": {
            2020: FinishType.BUNCH_SPRINT,
            2021: FinishType.BUNCH_SPRINT,
            2022: FinishType.BUNCH_SPRINT,
            2023: FinishType.BUNCH_SPRINT,
            2024: FinishType.SMALL_GROUP_SPRINT,
        },
    },
]


# ---------------------------------------------------------------------------
# Time distribution generators
# ---------------------------------------------------------------------------

def _generate_times_bunch_sprint(
    rng: random.Random, field_size: int, base_time: float
) -> List[float]:
    """Bunch sprint: most riders within 0-3s, tiny consecutive gaps."""
    times = []
    for i in range(field_size):
        if i < int(field_size * 0.8):
            # Main bunch: within 2 seconds of each other
            times.append(base_time + rng.uniform(0, 2.0))
        else:
            # Stragglers: 5-30s back
            times.append(base_time + rng.uniform(5.0, 30.0))
    times.sort()
    return times


def _generate_times_small_group_sprint(
    rng: random.Random, field_size: int, base_time: float
) -> List[float]:
    """Small group sprint: lead group of 5-10, gap, then main bunch."""
    times = []
    lead_size = rng.randint(5, min(10, field_size // 2))
    for i in range(field_size):
        if i < lead_size:
            times.append(base_time + rng.uniform(0, 1.5))
        elif i < lead_size + int(field_size * 0.5):
            times.append(base_time + rng.uniform(10.0, 15.0))
        else:
            times.append(base_time + rng.uniform(20.0, 45.0))
    times.sort()
    return times


def _generate_times_breakaway(
    rng: random.Random, field_size: int, base_time: float
) -> List[float]:
    """Breakaway: 1-3 solo, big gap, then a large main group."""
    times = []
    break_size = rng.randint(1, 3)
    for i in range(field_size):
        if i < break_size:
            times.append(base_time + rng.uniform(0, 3.0))
        elif i < break_size + int(field_size * 0.7):
            # Main bunch: 35-45s back, tight together
            times.append(base_time + rng.uniform(35.0, 40.0))
        else:
            times.append(base_time + rng.uniform(50.0, 90.0))
    times.sort()
    return times


def _generate_times_breakaway_selective(
    rng: random.Random, field_size: int, base_time: float
) -> List[float]:
    """Breakaway selective: 1-3 solo, big gap, field shattered (no big group)."""
    times = []
    break_size = rng.randint(1, 3)
    for i in range(field_size):
        if i < break_size:
            times.append(base_time + rng.uniform(0, 2.0))
        else:
            # Scattered field: each rider increasingly further back
            offset = 35.0 + (i - break_size) * rng.uniform(3.0, 8.0)
            times.append(base_time + offset)
    times.sort()
    return times


def _generate_times_reduced_sprint(
    rng: random.Random, field_size: int, base_time: float
) -> List[float]:
    """Reduced sprint: front group of 10-20, rest dropped."""
    times = []
    front_size = rng.randint(10, min(20, field_size // 2 + 5))
    for i in range(field_size):
        if i < front_size:
            times.append(base_time + rng.uniform(0, 3.0))
        else:
            times.append(base_time + rng.uniform(15.0, 60.0))
    times.sort()
    return times


def _generate_times_gc_selective(
    rng: random.Random, field_size: int, base_time: float
) -> List[float]:
    """GC selective: many small groups, high time spread, no big bunch."""
    times = []
    for i in range(field_size):
        # Spread across wide range in small clusters
        cluster = i // 3
        within_cluster = rng.uniform(0, 1.5)
        times.append(base_time + cluster * rng.uniform(8.0, 15.0) + within_cluster)
    times.sort()
    return times


def _generate_times_mixed(
    rng: random.Random, field_size: int, base_time: float
) -> List[float]:
    """Mixed: some bunching, some gaps, no clear single pattern."""
    times = []
    for i in range(field_size):
        if i < field_size // 4:
            times.append(base_time + rng.uniform(0, 4.0))
        elif i < field_size // 2:
            times.append(base_time + rng.uniform(8.0, 18.0))
        else:
            times.append(base_time + rng.uniform(20.0, 60.0))
    times.sort()
    return times


def _generate_times_unknown(
    rng: random.Random, field_size: int, base_time: float
) -> List[float]:
    """Unknown: sparse time data — only a few riders have times."""
    times = []
    for i in range(field_size):
        if rng.random() < 0.3:
            times.append(base_time + rng.uniform(0, 60.0))
        else:
            times.append(0.0)  # will be treated as missing
    times.sort()
    return times


TIME_GENERATORS = {
    FinishType.BUNCH_SPRINT: _generate_times_bunch_sprint,
    FinishType.SMALL_GROUP_SPRINT: _generate_times_small_group_sprint,
    FinishType.BREAKAWAY: _generate_times_breakaway,
    FinishType.BREAKAWAY_SELECTIVE: _generate_times_breakaway_selective,
    FinishType.REDUCED_SPRINT: _generate_times_reduced_sprint,
    FinishType.GC_SELECTIVE: _generate_times_gc_selective,
    FinishType.MIXED: _generate_times_mixed,
    FinishType.UNKNOWN: _generate_times_unknown,
}


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def _compute_metrics(
    times: List[float], finish_type: FinishType, gap_threshold: float = 3.0
) -> dict:
    """Compute classification metrics from a list of finish times.

    Returns a dict with keys matching RaceClassification columns.
    """
    valid_times = [t for t in times if t > 0]
    num_finishers = len(valid_times)

    if num_finishers < 2:
        return {
            "num_finishers": num_finishers,
            "num_groups": 1 if num_finishers else 0,
            "largest_group_size": num_finishers,
            "largest_group_ratio": 1.0 if num_finishers else 0.0,
            "leader_group_size": num_finishers,
            "gap_to_second_group": 0.0,
            "cv_of_times": 0.0,
            "gap_threshold_used": gap_threshold,
        }

    # Group by consecutive gaps
    sorted_times = sorted(valid_times)
    groups: List[List[float]] = [[sorted_times[0]]]
    for i in range(1, len(sorted_times)):
        if sorted_times[i] - sorted_times[i - 1] > gap_threshold:
            groups.append([])
        groups[-1].append(sorted_times[i])

    group_sizes = [len(g) for g in groups]
    largest_group_size = max(group_sizes)
    leader_group_size = group_sizes[0]

    gap_to_second = 0.0
    if len(groups) > 1:
        gap_to_second = groups[1][0] - groups[0][-1]

    mean_time = statistics.mean(sorted_times)
    stdev_time = statistics.stdev(sorted_times) if len(sorted_times) > 1 else 0.0
    cv = stdev_time / mean_time if mean_time > 0 else 0.0

    return {
        "num_finishers": num_finishers,
        "num_groups": len(groups),
        "largest_group_size": largest_group_size,
        "largest_group_ratio": largest_group_size / num_finishers,
        "leader_group_size": leader_group_size,
        "gap_to_second_group": round(gap_to_second, 2),
        "cv_of_times": round(cv, 6),
        "gap_threshold_used": gap_threshold,
    }


def _format_time(seconds: float) -> str:
    """Format seconds as H:MM:SS.ss race time string."""
    if seconds <= 0:
        return ""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


# ---------------------------------------------------------------------------
# Category variation: slightly alter finish type for non-primary categories
# ---------------------------------------------------------------------------

_FINISH_TYPE_VARIATIONS = {
    FinishType.BUNCH_SPRINT: [
        FinishType.BUNCH_SPRINT,
        FinishType.BUNCH_SPRINT,
        FinishType.SMALL_GROUP_SPRINT,
    ],
    FinishType.SMALL_GROUP_SPRINT: [
        FinishType.SMALL_GROUP_SPRINT,
        FinishType.BUNCH_SPRINT,
        FinishType.REDUCED_SPRINT,
    ],
    FinishType.BREAKAWAY: [
        FinishType.BREAKAWAY,
        FinishType.BREAKAWAY,
        FinishType.BREAKAWAY_SELECTIVE,
    ],
    FinishType.BREAKAWAY_SELECTIVE: [
        FinishType.BREAKAWAY_SELECTIVE,
        FinishType.BREAKAWAY,
        FinishType.GC_SELECTIVE,
    ],
    FinishType.REDUCED_SPRINT: [
        FinishType.REDUCED_SPRINT,
        FinishType.BUNCH_SPRINT,
        FinishType.SMALL_GROUP_SPRINT,
    ],
    FinishType.GC_SELECTIVE: [
        FinishType.GC_SELECTIVE,
        FinishType.BREAKAWAY_SELECTIVE,
        FinishType.MIXED,
    ],
    FinishType.MIXED: [
        FinishType.MIXED,
        FinishType.REDUCED_SPRINT,
        FinishType.UNKNOWN,
    ],
    FinishType.UNKNOWN: [
        FinishType.UNKNOWN,
        FinishType.MIXED,
        FinishType.UNKNOWN,
    ],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def seed_demo_data(session: Session) -> dict:
    """Populate the database with synthetic demo data.

    Idempotent: clears existing demo data before seeding.

    Returns a summary dict: {"races": int, "riders": int, "results": int,
                              "classifications": int}
    """
    rng = random.Random(RANDOM_SEED)

    # Clear any existing demo data first
    clear_demo_data(session)

    # --- Generate riders ---
    riders: List[Rider] = []
    used_names: set = set()
    rider_id = DEMO_RIDER_RR_ID_START
    while len(riders) < 100:
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        full_name = f"{first} {last}"
        if full_name in used_names:
            continue
        used_names.add(full_name)
        rider = Rider(
            name=full_name,
            road_results_id=rider_id,
        )
        session.add(rider)
        riders.append(rider)
        rider_id += 1

    session.flush()  # assign IDs

    # Pre-assign riders to categories (each rider races 1-3 categories)
    rider_categories: dict = {}  # rider index -> list of category indices
    for i, rider in enumerate(riders):
        num_cats = rng.choices([1, 2, 3], weights=[0.4, 0.4, 0.2])[0]
        cats = rng.sample(range(len(CATEGORIES)), min(num_cats, len(CATEGORIES)))
        rider_categories[i] = cats

    # --- Generate races ---
    race_id = DEMO_RACE_ID_START
    total_results = 0
    total_classifications = 0

    for template in RACE_TEMPLATES:
        for year, primary_finish_type in template["years"].items():
            # Compute race date with slight annual variation
            day_offset = rng.randint(-3, 3)
            try:
                race_date = datetime(
                    year, template["month"],
                    min(max(template["day"] + day_offset, 1), 28),
                )
            except ValueError:
                race_date = datetime(year, template["month"], 15)

            race = Race(
                id=race_id,
                name=template["name"],
                date=race_date,
                location=template["location"],
                state_province=template["state"],
                url=f"https://www.road-results.com/race/{race_id}",
            )
            session.add(race)

            # Generate results and classifications per category
            for cat_idx, (cat_name, min_field, max_field) in enumerate(CATEGORIES):
                # Vary finish type by category
                if cat_idx == 0:
                    cat_finish_type = primary_finish_type
                else:
                    cat_finish_type = rng.choice(
                        _FINISH_TYPE_VARIATIONS[primary_finish_type]
                    )

                field_size = rng.randint(min_field, max_field)
                base_time = rng.uniform(3200.0, 4800.0)

                # Get riders eligible for this category
                eligible = [
                    i for i, cats in rider_categories.items()
                    if cat_idx in cats
                ]
                if len(eligible) < field_size:
                    eligible = list(range(len(riders)))
                field_riders = rng.sample(eligible, min(field_size, len(eligible)))

                # Generate times
                gen = TIME_GENERATORS[cat_finish_type]
                times = gen(rng, len(field_riders), base_time)

                # Create results
                dnf_count = 0
                for place_idx, (rider_idx, time_val) in enumerate(
                    zip(field_riders, times)
                ):
                    rider = riders[rider_idx]
                    is_dnf = False
                    # Small chance of DNF for last few riders
                    if place_idx >= len(field_riders) - 3 and rng.random() < 0.15:
                        is_dnf = True
                        dnf_count += 1

                    race_time_seconds = time_val if (time_val > 0 and not is_dnf) else None
                    race_time_str = _format_time(time_val) if (time_val > 0 and not is_dnf) else None

                    result = Result(
                        race_id=race_id,
                        rider_id=rider.id,
                        place=None if is_dnf else place_idx + 1,
                        name=rider.name,
                        team=rng.choice(PNW_TEAMS),
                        city=template["location"],
                        state_province=template["state"],
                        race_category_name=cat_name,
                        race_time=race_time_str,
                        race_time_seconds=race_time_seconds,
                        field_size=len(field_riders),
                        dnf=is_dnf,
                        dq=False,
                        dnp=False,
                    )
                    session.add(result)
                    total_results += 1

                # Compute metrics and create classification
                metrics = _compute_metrics(times, cat_finish_type)

                classification = RaceClassification(
                    race_id=race_id,
                    category=cat_name,
                    finish_type=cat_finish_type,
                    num_finishers=metrics["num_finishers"],
                    num_groups=metrics["num_groups"],
                    largest_group_size=metrics["largest_group_size"],
                    largest_group_ratio=metrics["largest_group_ratio"],
                    leader_group_size=metrics["leader_group_size"],
                    gap_to_second_group=metrics["gap_to_second_group"],
                    cv_of_times=metrics["cv_of_times"],
                    gap_threshold_used=metrics["gap_threshold_used"],
                )
                session.add(classification)
                total_classifications += 1

            race_id += 1

    session.commit()

    return {
        "races": race_id - DEMO_RACE_ID_START,
        "riders": len(riders),
        "results": total_results,
        "classifications": total_classifications,
    }


def clear_demo_data(session: Session) -> int:
    """Remove all demo data from the database.

    Deletes races in the demo ID range (which cascades to results and
    classifications), and riders in the demo road_results_id range.

    Returns the number of races deleted.
    """
    # Delete results for demo races (cascade should handle this, but be explicit)
    demo_race_ids = [
        r[0]
        for r in session.query(Race.id)
        .filter(Race.id >= DEMO_RACE_ID_START)
        .all()
    ]

    if not demo_race_ids:
        # Also clean up riders in case of partial state
        session.query(Rider).filter(
            Rider.road_results_id >= DEMO_RIDER_RR_ID_START,
            Rider.road_results_id < DEMO_RIDER_RR_ID_START + 200,
        ).delete(synchronize_session="fetch")
        session.commit()
        return 0

    # Delete classifications
    session.query(RaceClassification).filter(
        RaceClassification.race_id.in_(demo_race_ids)
    ).delete(synchronize_session="fetch")

    # Delete results
    session.query(Result).filter(
        Result.race_id.in_(demo_race_ids)
    ).delete(synchronize_session="fetch")

    # Delete races
    count = session.query(Race).filter(
        Race.id >= DEMO_RACE_ID_START
    ).delete(synchronize_session="fetch")

    # Delete demo riders
    session.query(Rider).filter(
        Rider.road_results_id >= DEMO_RIDER_RR_ID_START,
        Rider.road_results_id < DEMO_RIDER_RR_ID_START + 200,
    ).delete(synchronize_session="fetch")

    session.commit()
    return count
```

### Phase 2: CLI Commands (10% of effort)

**File:** `raceanalyzer/cli.py` — Modify (add two commands)

**Tasks:**

| Task | Description |
|------|-------------|
| 2.1 | Add `seed-demo` Click command that initializes DB and calls `seed_demo_data()` |
| 2.2 | Add `clear-demo` Click command that calls `clear_demo_data()` |

**Code additions to `cli.py`:**

```python
@main.command("seed-demo")
@click.pass_context
def seed_demo(ctx):
    """Populate database with synthetic demo data (~50 races, ~100 riders)."""
    settings = ctx.obj["settings"]

    from raceanalyzer.db.engine import get_session, init_db
    from raceanalyzer.demo_data import seed_demo_data

    init_db(settings.db_path)
    session = get_session(settings.db_path)

    click.echo("Seeding demo data...")
    summary = seed_demo_data(session)
    click.echo(
        f"Done: {summary['races']} races, {summary['riders']} riders, "
        f"{summary['results']} results, {summary['classifications']} classifications."
    )
    session.close()


@main.command("clear-demo")
@click.pass_context
def clear_demo(ctx):
    """Remove all synthetic demo data from the database."""
    settings = ctx.obj["settings"]

    from raceanalyzer.db.engine import get_session
    from raceanalyzer.demo_data import clear_demo_data

    session = get_session(settings.db_path)
    count = clear_demo_data(session)
    click.echo(f"Removed {count} demo races and associated data.")
    session.close()
```

### Phase 3: Tests (10% of effort)

**File:** `tests/test_demo_data.py` — New file

**Tasks:**

| Task | Description |
|------|-------------|
| 3.1 | Test `seed_demo_data` produces expected counts (~50 races, ~100 riders, all 8 finish types) |
| 3.2 | Test `clear_demo_data` removes all demo data and leaves real data intact |
| 3.3 | Test idempotency: seeding twice produces the same result as seeding once |
| 3.4 | Test CV distribution: verify all 3 confidence tiers are represented |
| 3.5 | Test all 4 states are represented |
| 3.6 | Test date range spans 2020-2024 |

**Key test code:**

```python
# tests/test_demo_data.py
"""Tests for synthetic demo data generation."""
from __future__ import annotations

from datetime import datetime

import pytest

from raceanalyzer.db.models import (
    FinishType,
    Race,
    RaceClassification,
    Result,
    Rider,
)
from raceanalyzer.demo_data import (
    DEMO_RACE_ID_START,
    DEMO_RIDER_RR_ID_START,
    clear_demo_data,
    seed_demo_data,
)


class TestSeedDemoData:
    def test_produces_expected_race_count(self, session):
        summary = seed_demo_data(session)
        assert 40 <= summary["races"] <= 60

    def test_produces_expected_rider_count(self, session):
        summary = seed_demo_data(session)
        assert summary["riders"] == 100

    def test_all_finish_types_represented(self, session):
        seed_demo_data(session)
        classifications = session.query(RaceClassification).all()
        finish_types_found = {c.finish_type for c in classifications}
        for ft in FinishType:
            assert ft in finish_types_found, f"Missing finish type: {ft}"

    def test_all_states_represented(self, session):
        seed_demo_data(session)
        states = {
            r[0] for r in session.query(Race.state_province).distinct().all()
        }
        assert states >= {"WA", "OR", "ID", "BC"}

    def test_date_range_spans_five_years(self, session):
        seed_demo_data(session)
        years = {
            r[0].year
            for r in session.query(Race.date).filter(
                Race.id >= DEMO_RACE_ID_START
            ).all()
        }
        assert years >= {2020, 2021, 2022, 2023, 2024}

    def test_confidence_tiers_all_represented(self, session):
        seed_demo_data(session)
        classifications = session.query(RaceClassification).all()
        cv_values = [c.cv_of_times for c in classifications if c.cv_of_times is not None]

        green = [cv for cv in cv_values if cv < 0.005]
        yellow = [cv for cv in cv_values if 0.005 <= cv < 0.02]
        red = [cv for cv in cv_values if cv >= 0.02]

        assert len(green) > 0, "No green (high confidence) classifications"
        assert len(yellow) > 0, "No yellow (medium confidence) classifications"
        assert len(red) > 0, "No red (low confidence) classifications"

    def test_race_ids_in_demo_range(self, session):
        seed_demo_data(session)
        races = session.query(Race).filter(Race.id >= DEMO_RACE_ID_START).all()
        assert len(races) > 0
        for race in races:
            assert race.id >= DEMO_RACE_ID_START

    def test_idempotent(self, session):
        summary1 = seed_demo_data(session)
        summary2 = seed_demo_data(session)
        assert summary1 == summary2
        # No duplicate races
        race_count = session.query(Race).filter(
            Race.id >= DEMO_RACE_ID_START
        ).count()
        assert race_count == summary2["races"]

    def test_six_plus_categories(self, session):
        seed_demo_data(session)
        categories = {
            r[0]
            for r in session.query(RaceClassification.category).distinct().all()
        }
        assert len(categories) >= 6


class TestClearDemoData:
    def test_removes_demo_data(self, session):
        seed_demo_data(session)
        count = clear_demo_data(session)
        assert count > 0
        assert session.query(Race).filter(
            Race.id >= DEMO_RACE_ID_START
        ).count() == 0
        assert session.query(Rider).filter(
            Rider.road_results_id >= DEMO_RIDER_RR_ID_START
        ).count() == 0

    def test_preserves_real_data(self, session):
        # Add a "real" race
        real_race = Race(id=1, name="Real Race", date=datetime(2023, 1, 1))
        session.add(real_race)
        session.commit()

        seed_demo_data(session)
        clear_demo_data(session)

        assert session.query(Race).filter(Race.id == 1).count() == 1

    def test_clear_empty_db(self, session):
        count = clear_demo_data(session)
        assert count == 0
```

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `raceanalyzer/demo_data.py` | New | Demo data generator: race templates, rider pool, time distributions, seed/clear functions |
| `raceanalyzer/cli.py` | Modify | Add `seed-demo` and `clear-demo` Click commands |
| `tests/test_demo_data.py` | New | Tests for demo data generation and cleanup |

## Definition of Done

- [ ] `python -m raceanalyzer seed-demo` completes without error, reporting ~50 races, ~100 riders, ~2500+ results, ~120+ classifications
- [ ] `python -m raceanalyzer clear-demo` removes all demo data, reports count
- [ ] Running `seed-demo` twice produces identical data (idempotent, no duplicates)
- [ ] All 8 `FinishType` enum values appear in the generated classifications
- [ ] All 4 states (WA, OR, ID, BC) are represented
- [ ] All 6+ categories are represented
- [ ] Race dates span 2020-2024
- [ ] CV values exercise all 3 confidence badge colors: green (cv < 0.005), yellow (0.005-0.02), red (>= 0.02)
- [ ] Trend chart shows interesting year-over-year variation (not identical distributions each year)
- [ ] UI calendar, detail, and dashboard pages display meaningful data after seeding
- [ ] `clear-demo` does not affect any non-demo data (races with IDs below 90001, riders without demo road_results_id)
- [ ] All existing tests continue to pass
- [ ] All new tests pass
- [ ] `ruff check .` passes with zero errors
- [ ] Python 3.9 compatible: all new files use `from __future__ import annotations`
- [ ] No external dependencies added (stdlib `random` and `statistics` only)

## Risks & Mitigations

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Generated CV values do not actually land in all 3 confidence tiers | Medium | Medium | The time distribution generators are designed to produce different spread characteristics. Bunch sprints with 0-2s spread produce very low CV (~0.0003); GC selective with wide spread produces high CV (>0.02). Test explicitly asserts all 3 tiers are populated. If any tier is missing, tune the generator parameters. |
| Demo race IDs collide with real road-results.com IDs in the future | Low | Very Low | road-results.com currently has ~15,000 races. The demo range starts at 90,001. Even at 1,000 new races per year, collision would not occur for 75+ years. |
| Generated time distributions do not match what the existing classifier would produce for those finish types | Low | Medium | The demo data bypasses the classifier — it stores the target finish type directly on `RaceClassification`. This is intentional: the demo data's purpose is to exercise the UI, not to validate the classifier. The metrics are computed from the generated times so they are internally consistent. |
| `clear-demo` accidentally deletes real data | High | Very Low | Deletion is scoped to races with `id >= 90001` and riders with `road_results_id >= 80001`. These ranges are well above any real data. Tests explicitly verify that a "real" race (id=1) survives a clear operation. |
| `session.flush()` behavior differs between SQLite and other backends | Low | Low | This project only targets SQLite. The `flush()` call is needed to assign auto-increment IDs to riders before referencing them in results. Tested against in-memory SQLite. |

## Open Questions

1. **Should demo data include ScrapeLog entries?** The `ScrapeLog` table tracks scraping progress, and the UI may query it for status display. If the UI shows "last scraped" dates, we should seed `ScrapeLog` entries for demo races. **Recommendation**: Defer unless the UI actually reads `ScrapeLog`. The current Sprint 002 UI does not surface scrape status.

2. **Should the random seed be configurable via CLI flag?** A `--seed` option on `seed-demo` would allow generating different datasets for visual testing. **Recommendation**: Not needed for this disposable sprint. The fixed seed ensures reproducibility for screenshots and test assertions. If needed later, it is a one-line change.

3. **Should demo data include `gap_group_id` and `gap_to_leader` on Result rows?** These computed fields are populated during classification but not used by the current UI. **Recommendation**: Skip them. The UI reads from `RaceClassification`, not from per-result gap fields. Populating them would add complexity for no visible benefit.

4. **Race name uniqueness across years**: The same race name (e.g., "Banana Belt RR") appears multiple years. The UI's calendar page should display these as separate rows. If the UI groups by race name for trend analysis, will duplicate names cause confusion? **Recommendation**: This is the desired behavior — it mirrors real data where "Banana Belt RR" appears as a separate race each year with its own ID and classification. The trend chart groups by year, not by race name.
