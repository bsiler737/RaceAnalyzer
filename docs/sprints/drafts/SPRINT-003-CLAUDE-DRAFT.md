# Sprint 003: Synthetic Demo Data

## Overview

Generate realistic synthetic race data so the RaceAnalyzer UI can be demonstrated and iterated on while road-results.com blocks our IP. This sprint adds a single new module (`raceanalyzer/demo.py`) and two CLI commands (`seed-demo`, `clear-demo`). The demo data covers ~50 races across 5 years (2020–2024), 4 PNW states/provinces, 6 categories, and all 8 finish types with realistic time distributions. This is disposable scaffolding — expected to be removed once real scraping resumes.

**Duration**: ~2–3 days
**Primary deliverable**: `python -m raceanalyzer seed-demo` populates the DB; `python -m raceanalyzer clear-demo` removes it.
**Prerequisite**: Sprint 002 complete (UI, query layer, charts).

---

## Use Cases

1. **As a developer**, I can run `python -m raceanalyzer seed-demo` to populate the DB with ~50 races so all three UI pages show meaningful data without a working scraper connection.
2. **As a developer**, I can run `python -m raceanalyzer clear-demo` to cleanly remove all demo data, leaving any real scraped data untouched.
3. **As a demo presenter**, I can launch the UI after seeding and see the Race Calendar populated with recognizable PNW race names across multiple years and states.
4. **As a demo presenter**, I can click into any race detail and see per-category finish type classifications with all three confidence badge colors (green, orange, red).
5. **As a demo presenter**, I can view the Finish Type Dashboard and see distribution charts with all 8 finish types represented, and a trend chart showing meaningful variation across 5 years.
6. **As a tester**, I can seed demo data and verify that every UI feature (filters, badges, charts, empty states) works correctly with realistic data shapes.

---

## Architecture

```
raceanalyzer/
├── demo.py             # NEW: Demo data generation + cleanup
├── cli.py              # MODIFY: Add seed-demo + clear-demo commands
├── db/
│   ├── models.py       # (existing, no changes)
│   └── engine.py       # (existing, no changes)
└── config.py           # (existing, no changes)

tests/
├── test_demo.py        # NEW: Tests for demo data generation
└── conftest.py         # (existing, no changes)
```

### Data Flow

```
demo.py: generate_demo_data(session)
    │
    ├── Creates Race rows (id range 900_001–900_999, avoids real IDs)
    ├── Creates Rider rows (pool of ~80 synthetic PNW riders)
    ├── Creates Result rows (realistic times per finish type)
    ├── Creates RaceClassification rows (metrics match time data)
    └── Creates ScrapeLog rows (status="demo", marks data for cleanup)
    │
    ▼
clear_demo_data(session)
    │
    └── Deletes all ScrapeLog where status="demo", cascades to related rows
```

### Key Design Decisions

1. **Reserved ID range (900_001+)** — Demo races use IDs in the 900_000+ range, well above `max_race_id=15000` from Settings. This prevents collisions with real scraped data and makes cleanup simple.
2. **ScrapeLog with status="demo"** — Each demo race gets a ScrapeLog entry with `status="demo"`. Cleanup queries this marker rather than relying on ID ranges, making it robust.
3. **No external dependencies** — Uses only `random` from stdlib. Race names, rider names, and team names are hardcoded lists of real PNW entities.
4. **Deterministic with optional seed** — `random.seed(42)` by default for reproducible output, but accepts a `--seed` CLI option for variation.
5. **Finish-type-aware time generation** — Each finish type has a distinct time distribution pattern (e.g., bunch sprints have tight clusters, breakaways have a gap then a cluster).

---

## Implementation

### File: `raceanalyzer/demo.py`

```python
"""Synthetic demo data generator for RaceAnalyzer.

Generates ~50 realistic PNW bike races with results and classifications
that exercise all UI features. Uses no external dependencies.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from raceanalyzer.db.models import (
    FinishType,
    Race,
    RaceClassification,
    Result,
    Rider,
    ScrapeLog,
)

# --- Constants ---

DEMO_ID_BASE = 900_001
DEMO_SCRAPE_STATUS = "demo"

# Real PNW race names and locations
PNW_RACES = [
    ("Banana Belt Road Race", "Maryhill", "WA"),
    ("Cherry Pie Criterium", "Niles", "OR"),
    ("Mason Lake Road Race", "Shelton", "WA"),
    ("Mutual of Enumclaw Stage Race", "Enumclaw", "WA"),
    ("Seward Park Criterium", "Seattle", "WA"),
    ("Piece of Cake Road Race", "Ridgefield", "WA"),
    ("Tour de Bloom Stage Race", "Wenatchee", "WA"),
    ("Twilight Criterium", "Boise", "ID"),
    ("Gorge Roubaix", "The Dalles", "OR"),
    ("Obras Criterium Series", "Portland", "OR"),
    ("PIR Short Track Criterium", "Portland", "OR"),
    ("Volunteer Park Criterium", "Seattle", "WA"),
    ("Apple Cider Criterium", "Hood River", "OR"),
    ("Marymoor Grand Prix", "Redmond", "WA"),
    ("Bear Creek Road Race", "Medford", "OR"),
    ("Tour de Whidbey", "Whidbey Island", "WA"),
    ("Snake River Road Race", "Twin Falls", "ID"),
    ("BC Superweek Criterium", "Vancouver", "BC"),
    ("Tour de Delta", "Delta", "BC"),
    ("Gastown Grand Prix", "Vancouver", "BC"),
    ("White Rock Criterium", "White Rock", "BC"),
    ("Elkhorn Classic Stage Race", "Baker City", "OR"),
    ("Oregon Trail Classic", "Bend", "OR"),
    ("Stottlemeyer Road Race", "Bainbridge Island", "WA"),
    ("Mount Tabor Hill Climb", "Portland", "OR"),
]

CATEGORIES = [
    "Men Pro/1/2",
    "Men Cat 3",
    "Men Cat 4/5",
    "Women Pro/1/2/3",
    "Women Cat 4",
    "Masters Men 40+",
]

PNW_TEAMS = [
    "Audi Cycling Team", "Hagens Berman", "Team Montano Velo",
    "Broadmark Capital", "Rad Racing NW", "River City Bicycles",
    "Team Hammer", "Lux Cycling", "North Division Bicycle Club",
    "Boise Cycling Club", "Gruppo Sportivo", "Trek Red Truck Racing",
    "Symmetrics Cycling", "H&R Block Pro Cycling", "Escape Velocity",
    None, None, None,  # Some riders unattached
]

PNW_CITIES = [
    ("Seattle", "WA"), ("Portland", "OR"), ("Boise", "ID"),
    ("Vancouver", "BC"), ("Tacoma", "WA"), ("Eugene", "OR"),
    ("Bellingham", "WA"), ("Bend", "OR"), ("Spokane", "WA"),
    ("Victoria", "BC"), ("Corvallis", "OR"), ("Olympia", "WA"),
    ("Redmond", "WA"), ("Issaquah", "WA"), ("Hood River", "OR"),
]

# First/last name pools for rider generation
FIRST_NAMES = [
    "Alex", "Ben", "Chris", "David", "Erik", "Finn", "Greg", "Hank",
    "Ian", "Jake", "Kyle", "Liam", "Matt", "Nate", "Owen", "Paul",
    "Quinn", "Ryan", "Sam", "Tyler", "Uma", "Val", "Will", "Xander",
    "Yuki", "Zach", "Anna", "Beth", "Cara", "Diana", "Elena", "Faye",
    "Gina", "Hope", "Iris", "Jade", "Kate", "Luna", "Maya", "Nina",
    "Olivia", "Petra", "Rosa", "Sara", "Tara", "Violet", "Wendy", "Zoe",
]

LAST_NAMES = [
    "Anderson", "Baker", "Chen", "Davis", "Evans", "Fischer", "Garcia",
    "Hansen", "Ito", "Jensen", "Kim", "Larson", "Miller", "Nelson",
    "Olson", "Park", "Quinn", "Rivera", "Schmidt", "Thompson",
    "Ueda", "Vance", "Walsh", "Xu", "Yamada", "Zhou",
]

# Race months (PNW season: Feb–Oct)
RACE_MONTHS = [2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10]

# Finish type weights per category (simulates real-world patterns)
# Pro fields: more breakaways and selective finishes
# Lower cats: more bunch sprints
FINISH_TYPE_WEIGHTS: dict[str, dict[FinishType, float]] = {
    "Men Pro/1/2": {
        FinishType.BUNCH_SPRINT: 0.20,
        FinishType.SMALL_GROUP_SPRINT: 0.15,
        FinishType.BREAKAWAY: 0.20,
        FinishType.BREAKAWAY_SELECTIVE: 0.10,
        FinishType.REDUCED_SPRINT: 0.15,
        FinishType.GC_SELECTIVE: 0.05,
        FinishType.MIXED: 0.10,
        FinishType.UNKNOWN: 0.05,
    },
    "Men Cat 3": {
        FinishType.BUNCH_SPRINT: 0.35,
        FinishType.SMALL_GROUP_SPRINT: 0.20,
        FinishType.BREAKAWAY: 0.10,
        FinishType.BREAKAWAY_SELECTIVE: 0.05,
        FinishType.REDUCED_SPRINT: 0.15,
        FinishType.GC_SELECTIVE: 0.02,
        FinishType.MIXED: 0.08,
        FinishType.UNKNOWN: 0.05,
    },
    "Men Cat 4/5": {
        FinishType.BUNCH_SPRINT: 0.45,
        FinishType.SMALL_GROUP_SPRINT: 0.20,
        FinishType.BREAKAWAY: 0.05,
        FinishType.BREAKAWAY_SELECTIVE: 0.02,
        FinishType.REDUCED_SPRINT: 0.10,
        FinishType.GC_SELECTIVE: 0.01,
        FinishType.MIXED: 0.10,
        FinishType.UNKNOWN: 0.07,
    },
    "Women Pro/1/2/3": {
        FinishType.BUNCH_SPRINT: 0.25,
        FinishType.SMALL_GROUP_SPRINT: 0.20,
        FinishType.BREAKAWAY: 0.15,
        FinishType.BREAKAWAY_SELECTIVE: 0.08,
        FinishType.REDUCED_SPRINT: 0.15,
        FinishType.GC_SELECTIVE: 0.04,
        FinishType.MIXED: 0.08,
        FinishType.UNKNOWN: 0.05,
    },
    "Women Cat 4": {
        FinishType.BUNCH_SPRINT: 0.35,
        FinishType.SMALL_GROUP_SPRINT: 0.20,
        FinishType.BREAKAWAY: 0.08,
        FinishType.BREAKAWAY_SELECTIVE: 0.02,
        FinishType.REDUCED_SPRINT: 0.15,
        FinishType.GC_SELECTIVE: 0.02,
        FinishType.MIXED: 0.10,
        FinishType.UNKNOWN: 0.08,
    },
    "Masters Men 40+": {
        FinishType.BUNCH_SPRINT: 0.25,
        FinishType.SMALL_GROUP_SPRINT: 0.15,
        FinishType.BREAKAWAY: 0.15,
        FinishType.BREAKAWAY_SELECTIVE: 0.10,
        FinishType.REDUCED_SPRINT: 0.15,
        FinishType.GC_SELECTIVE: 0.05,
        FinishType.MIXED: 0.10,
        FinishType.UNKNOWN: 0.05,
    },
}


def _pick_finish_type(category: str) -> FinishType:
    """Weighted random selection of finish type for a category."""
    weights = FINISH_TYPE_WEIGHTS.get(category, FINISH_TYPE_WEIGHTS["Men Cat 3"])
    types = list(weights.keys())
    probs = list(weights.values())
    return random.choices(types, weights=probs, k=1)[0]


def _generate_times(
    finish_type: FinishType,
    field_size: int,
    base_time: float,
) -> list[dict]:
    """Generate realistic race_time_seconds for a field based on finish type.

    Returns list of dicts with keys: place, race_time_seconds, gap_to_leader,
    gap_group_id, dnf.

    Time distribution patterns by finish type:
    - BUNCH_SPRINT: Everyone within ~5s, one tight group
    - SMALL_GROUP_SPRINT: Lead group of 5-10, then 30s+ gap, then stragglers
    - BREAKAWAY: 1-3 riders 30-90s ahead, then a main bunch
    - BREAKAWAY_SELECTIVE: 2-5 riders ahead with gaps between them, then bunch
    - REDUCED_SPRINT: Main field shattered, top 15-20 in small group, rest scattered
    - GC_SELECTIVE: Very spread out, individual gaps throughout
    - MIXED: Some grouping but messy, moderate spread
    - UNKNOWN: Random scatter, limited data
    """
    results = []
    num_dnf = max(0, int(field_size * random.uniform(0.0, 0.08)))
    num_finishers = field_size - num_dnf

    times: list[float] = []

    if finish_type == FinishType.BUNCH_SPRINT:
        # Tight group, everyone within ~5s
        for i in range(num_finishers):
            gap = random.uniform(0, 0.3) * (i + 1)  # max ~5s spread for 15 riders
            times.append(base_time + gap)

    elif finish_type == FinishType.SMALL_GROUP_SPRINT:
        # Lead group of 5-10, gap, then rest
        lead_size = random.randint(5, min(10, num_finishers))
        for i in range(lead_size):
            times.append(base_time + random.uniform(0, 0.3) * (i + 1))
        gap = random.uniform(20.0, 45.0)
        for i in range(num_finishers - lead_size):
            times.append(base_time + gap + random.uniform(0, 15.0) + i * 0.5)

    elif finish_type == FinishType.BREAKAWAY:
        # 1-3 solo/duo ahead, then main bunch
        break_size = random.randint(1, 3)
        for i in range(break_size):
            times.append(base_time + i * random.uniform(1.0, 5.0))
        gap = random.uniform(30.0, 90.0)
        for i in range(num_finishers - break_size):
            times.append(base_time + gap + random.uniform(0, 0.3) * (i + 1))

    elif finish_type == FinishType.BREAKAWAY_SELECTIVE:
        # 2-5 ahead with gaps, then bunch
        break_size = random.randint(2, 5)
        for i in range(break_size):
            times.append(base_time + i * random.uniform(5.0, 15.0))
        gap = random.uniform(40.0, 80.0)
        for i in range(num_finishers - break_size):
            times.append(base_time + gap + random.uniform(0, 10.0) + i * 0.8)

    elif finish_type == FinishType.REDUCED_SPRINT:
        # Top 8-12 together, then scattered
        lead_size = random.randint(8, min(12, num_finishers))
        for i in range(lead_size):
            times.append(base_time + random.uniform(0, 0.4) * (i + 1))
        for i in range(num_finishers - lead_size):
            times.append(base_time + 15.0 + i * random.uniform(3.0, 8.0))

    elif finish_type == FinishType.GC_SELECTIVE:
        # Very spread out, increasing gaps
        for i in range(num_finishers):
            times.append(base_time + i * random.uniform(5.0, 20.0))

    elif finish_type == FinishType.MIXED:
        # Some clustering but messy
        for i in range(num_finishers):
            cluster_gap = 15.0 if i > num_finishers // 3 else 0.0
            times.append(base_time + cluster_gap + random.uniform(0, 3.0) * (i + 1))

    else:  # UNKNOWN
        for i in range(num_finishers):
            times.append(base_time + random.uniform(0, 2.0) * (i + 1))

    times.sort()

    # Assign gap groups using 3s threshold
    gap_threshold = 3.0
    group_id = 0
    leader_time = times[0] if times else base_time

    for i, t in enumerate(times):
        if i > 0 and (t - times[i - 1]) > gap_threshold:
            group_id += 1
        results.append({
            "place": i + 1,
            "race_time_seconds": round(t, 2),
            "gap_to_leader": round(t - leader_time, 2),
            "gap_group_id": group_id,
            "dnf": False,
        })

    # Add DNF riders
    for i in range(num_dnf):
        results.append({
            "place": None,
            "race_time_seconds": None,
            "gap_to_leader": None,
            "gap_group_id": None,
            "dnf": True,
        })

    return results


def _compute_classification_metrics(
    time_results: list[dict],
    finish_type: FinishType,
    gap_threshold: float = 3.0,
) -> dict:
    """Compute RaceClassification metric columns from generated time data."""
    finishers = [r for r in time_results if not r["dnf"]]
    if not finishers:
        return {
            "num_finishers": 0, "num_groups": 0, "largest_group_size": 0,
            "largest_group_ratio": 0.0, "leader_group_size": 0,
            "gap_to_second_group": 0.0, "cv_of_times": None,
            "gap_threshold_used": gap_threshold,
        }

    # Count groups and sizes
    groups: dict[int, int] = {}
    for r in finishers:
        gid = r["gap_group_id"]
        groups[gid] = groups.get(gid, 0) + 1

    sorted_groups = sorted(groups.items())
    num_groups = len(sorted_groups)
    largest_group_size = max(groups.values())
    leader_group_size = sorted_groups[0][1] if sorted_groups else 0

    # Gap to second group
    gap_to_second = 0.0
    if num_groups >= 2:
        group_0_max_time = max(
            r["race_time_seconds"] for r in finishers if r["gap_group_id"] == 0
        )
        group_1_min_time = min(
            r["race_time_seconds"] for r in finishers if r["gap_group_id"] == 1
        )
        gap_to_second = round(group_1_min_time - group_0_max_time, 2)

    # CV of times
    times = [r["race_time_seconds"] for r in finishers]
    mean_t = sum(times) / len(times)
    variance = sum((t - mean_t) ** 2 for t in times) / len(times)
    std_t = variance ** 0.5
    cv = round(std_t / mean_t, 6) if mean_t > 0 else 0.0

    return {
        "num_finishers": len(finishers),
        "num_groups": num_groups,
        "largest_group_size": largest_group_size,
        "largest_group_ratio": round(largest_group_size / len(finishers), 3),
        "leader_group_size": leader_group_size,
        "gap_to_second_group": gap_to_second,
        "cv_of_times": cv,
        "gap_threshold_used": gap_threshold,
    }


def _format_race_time(seconds: float) -> str:
    """Convert seconds to H:MM:SS.ff string."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _generate_riders(count: int) -> list[dict]:
    """Generate a pool of synthetic rider identities."""
    riders = []
    used_names = set()
    for i in range(count):
        while True:
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            if name not in used_names:
                used_names.add(name)
                break
        city, state = random.choice(PNW_CITIES)
        riders.append({
            "name": name,
            "team": random.choice(PNW_TEAMS),
            "city": city,
            "state": state,
            "age": random.randint(18, 65),
        })
    return riders


def generate_demo_data(
    session: Session,
    *,
    num_races: int = 50,
    seed: int = 42,
) -> dict:
    """Generate and insert synthetic demo data.

    Returns summary dict with counts of created entities.
    """
    random.seed(seed)

    # Generate rider pool
    rider_pool = _generate_riders(80)
    db_riders: list[Rider] = []
    for i, r in enumerate(rider_pool):
        rider = Rider(
            name=r["name"],
            road_results_id=DEMO_ID_BASE + i,
        )
        session.add(rider)
        db_riders.append(rider)
    session.flush()  # Assign IDs

    race_count = 0
    result_count = 0
    classification_count = 0
    years = [2020, 2021, 2022, 2023, 2024]

    for year in years:
        # Pick ~10 races per year (vary slightly)
        races_this_year = random.sample(
            PNW_RACES, k=min(len(PNW_RACES), num_races // len(years) + random.randint(-2, 2))
        )

        for race_name, location, state in races_this_year:
            race_id = DEMO_ID_BASE + race_count
            month = random.choice(RACE_MONTHS)
            day = random.randint(1, 28)
            race_date = datetime(year, month, day)

            race = Race(
                id=race_id,
                name=race_name,
                date=race_date,
                location=location,
                state_province=state,
                url=f"https://www.road-results.com/Race/{race_id}",
            )
            session.add(race)

            # ScrapeLog entry for cleanup tracking
            session.add(ScrapeLog(
                race_id=race_id,
                status=DEMO_SCRAPE_STATUS,
                scraped_at=datetime.utcnow(),
                result_count=0,  # Updated below
            ))

            # Pick which categories ran (not all categories at every race)
            num_cats = random.randint(3, len(CATEGORIES))
            race_categories = random.sample(CATEGORIES, k=num_cats)

            # Base time: crits ~45min, road races ~2-3hr
            is_crit = "crit" in race_name.lower() or "short track" in race_name.lower()
            base_time = random.uniform(2400, 3200) if is_crit else random.uniform(7200, 10800)

            race_result_count = 0
            for category in race_categories:
                finish_type = _pick_finish_type(category)
                field_size = random.randint(12, 45) if "Pro" in category else random.randint(8, 30)

                # Assign riders from pool to this field
                field_riders = random.sample(
                    db_riders, k=min(field_size, len(db_riders))
                )
                time_results = _generate_times(finish_type, field_size, base_time)

                for j, tr in enumerate(time_results):
                    rider = field_riders[j] if j < len(field_riders) else None
                    rider_info = rider_pool[db_riders.index(rider)] if rider else {
                        "name": f"Unknown Rider {j}", "team": None,
                        "city": None, "state": None, "age": None,
                    }
                    session.add(Result(
                        race_id=race_id,
                        rider_id=rider.id if rider else None,
                        place=tr["place"],
                        name=rider_info["name"],
                        team=rider_info["team"],
                        age=rider_info["age"],
                        city=rider_info["city"],
                        state_province=rider_info["state"],
                        race_category_name=category,
                        race_time=_format_race_time(tr["race_time_seconds"]) if tr["race_time_seconds"] else None,
                        race_time_seconds=tr["race_time_seconds"],
                        field_size=field_size,
                        dnf=tr["dnf"],
                        gap_to_leader=tr["gap_to_leader"],
                        gap_group_id=tr["gap_group_id"],
                    ))
                    result_count += 1
                    race_result_count += 1

                # Classification
                metrics = _compute_classification_metrics(time_results, finish_type)
                session.add(RaceClassification(
                    race_id=race_id,
                    category=category,
                    finish_type=finish_type,
                    **metrics,
                ))
                classification_count += 1

            # Update scrape log result count
            log = session.query(ScrapeLog).filter(ScrapeLog.race_id == race_id).first()
            if log:
                log.result_count = race_result_count

            race_count += 1

    session.commit()

    return {
        "races": race_count,
        "riders": len(db_riders),
        "results": result_count,
        "classifications": classification_count,
    }


def clear_demo_data(session: Session) -> dict:
    """Remove all demo data identified by ScrapeLog status='demo'.

    Uses cascade deletes on Race to clean up Results and Classifications.
    Returns summary dict with counts of deleted entities.
    """
    demo_logs = (
        session.query(ScrapeLog)
        .filter(ScrapeLog.status == DEMO_SCRAPE_STATUS)
        .all()
    )
    demo_race_ids = [log.race_id for log in demo_logs]

    if not demo_race_ids:
        return {"races": 0, "riders": 0, "results": 0, "classifications": 0}

    # Count before deleting (for summary)
    from raceanalyzer.db.models import Race as RaceModel

    races = session.query(RaceModel).filter(RaceModel.id.in_(demo_race_ids)).all()
    race_count = len(races)

    # Delete races (cascades to results and classifications)
    for race in races:
        session.delete(race)

    # Delete scrape logs
    for log in demo_logs:
        session.delete(log)

    # Delete demo riders (road_results_id in demo range)
    demo_riders = (
        session.query(Rider)
        .filter(Rider.road_results_id >= DEMO_ID_BASE)
        .filter(Rider.road_results_id < DEMO_ID_BASE + 1000)
        .all()
    )
    rider_count = len(demo_riders)
    for rider in demo_riders:
        session.delete(rider)

    session.commit()

    return {
        "races": race_count,
        "riders": rider_count,
    }
```

### File: `raceanalyzer/cli.py` — Add `seed-demo` and `clear-demo` commands

```python
@main.command("seed-demo")
@click.option("--num-races", type=int, default=50, help="Number of races to generate.")
@click.option("--seed", type=int, default=42, help="Random seed for reproducibility.")
@click.pass_context
def seed_demo(ctx, num_races, seed):
    """Populate the database with synthetic demo data."""
    settings = ctx.obj["settings"]

    from raceanalyzer.db.engine import get_session, init_db
    from raceanalyzer.demo import generate_demo_data

    init_db(settings.db_path)
    session = get_session(settings.db_path)

    click.echo(f"Seeding {num_races} demo races (seed={seed})...")
    summary = generate_demo_data(session, num_races=num_races, seed=seed)

    click.echo(
        f"Created {summary['races']} races, {summary['riders']} riders, "
        f"{summary['results']} results, {summary['classifications']} classifications."
    )
    session.close()


@main.command("clear-demo")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def clear_demo(ctx, yes):
    """Remove all synthetic demo data from the database."""
    settings = ctx.obj["settings"]

    from raceanalyzer.db.engine import get_session
    from raceanalyzer.demo import clear_demo_data

    if not yes:
        click.confirm("This will delete all demo data. Continue?", abort=True)

    session = get_session(settings.db_path)
    summary = clear_demo_data(session)

    click.echo(f"Removed {summary['races']} demo races and {summary['riders']} demo riders.")
    session.close()
```

### Finish Type Time Distribution Rationale

Each finish type generates a distinct time signature that the existing classifier would produce the correct classification for:

| Finish Type | Time Pattern | CV Range | Groups (3s threshold) |
|---|---|---|---|
| `BUNCH_SPRINT` | All within ~5s, tight pack | < 0.002 | 1 large group |
| `SMALL_GROUP_SPRINT` | Lead 5-10 tight, 20-45s gap, rest scattered | 0.003–0.008 | 2-3 groups |
| `BREAKAWAY` | 1-3 riders ahead 30-90s, then tight bunch | 0.005–0.015 | 2 groups, small leader |
| `BREAKAWAY_SELECTIVE` | 2-5 ahead with inter-rider gaps, then bunch | 0.008–0.020 | 3-5 groups |
| `REDUCED_SPRINT` | Top 8-12 tight, rest scattered at intervals | 0.005–0.012 | 2-4 groups |
| `GC_SELECTIVE` | Very spread, escalating gaps | 0.015–0.040 | Many small groups |
| `MIXED` | Loose clustering, moderate spread | 0.005–0.015 | 2-3 messy groups |
| `UNKNOWN` | Minimal data or unclear pattern | varies | varies |

This ensures:
- **Green badges** (CV < 0.005): Bunch sprints with very tight finishes
- **Orange badges** (CV 0.005–0.015): Most breakaway/reduced sprint finishes
- **Red badges** (CV >= 0.015): GC selective and spread-out finishes

### Trend Data Design

To create interesting trend patterns across 5 years, the finish type weights shift subtly per year. This is achieved naturally by the per-race random selection — with 10 races/year across 6 categories, statistical variance creates organic-looking year-over-year shifts in the dashboard trend chart. If more pronounced trends are desired, a year-based weight modifier could be added, but the natural variance from ~60 classifications/year should suffice.

### Tests: `tests/test_demo.py`

```python
"""Tests for synthetic demo data generation."""

from __future__ import annotations

from raceanalyzer.db.models import (
    Base,
    FinishType,
    Race,
    RaceClassification,
    Result,
    Rider,
    ScrapeLog,
)
from raceanalyzer.demo import (
    DEMO_ID_BASE,
    DEMO_SCRAPE_STATUS,
    _compute_classification_metrics,
    _generate_times,
    clear_demo_data,
    generate_demo_data,
)


class TestGenerateTimes:
    """Verify time distributions match expected patterns per finish type."""

    def test_bunch_sprint_tight_spread(self):
        results = _generate_times(FinishType.BUNCH_SPRINT, 20, 3600.0)
        finishers = [r for r in results if not r["dnf"]]
        spread = finishers[-1]["gap_to_leader"]
        assert spread < 10.0  # All within 10s

    def test_breakaway_has_gap(self):
        results = _generate_times(FinishType.BREAKAWAY, 20, 3600.0)
        finishers = [r for r in results if not r["dnf"]]
        # Should have at least 2 gap groups
        groups = {r["gap_group_id"] for r in finishers}
        assert len(groups) >= 2

    def test_gc_selective_spread_out(self):
        results = _generate_times(FinishType.GC_SELECTIVE, 15, 3600.0)
        finishers = [r for r in results if not r["dnf"]]
        spread = finishers[-1]["gap_to_leader"]
        assert spread > 30.0  # Very spread out

    def test_dnf_count_reasonable(self):
        results = _generate_times(FinishType.BUNCH_SPRINT, 30, 3600.0)
        dnf_count = sum(1 for r in results if r["dnf"])
        assert dnf_count <= 3  # Max 8% of 30

    def test_all_finish_types_produce_results(self):
        for ft in FinishType:
            results = _generate_times(ft, 15, 3600.0)
            assert len(results) == 15


class TestComputeMetrics:
    def test_single_group_metrics(self):
        results = _generate_times(FinishType.BUNCH_SPRINT, 10, 3600.0)
        metrics = _compute_classification_metrics(results, FinishType.BUNCH_SPRINT)
        assert metrics["num_groups"] >= 1
        assert metrics["cv_of_times"] is not None
        assert metrics["cv_of_times"] < 0.005  # Tight group

    def test_multi_group_has_gap(self):
        results = _generate_times(FinishType.BREAKAWAY, 15, 3600.0)
        metrics = _compute_classification_metrics(results, FinishType.BREAKAWAY)
        assert metrics["num_groups"] >= 2
        assert metrics["gap_to_second_group"] > 5.0


class TestGenerateDemoData:
    def test_creates_expected_counts(self, session):
        summary = generate_demo_data(session, num_races=10, seed=42)
        assert summary["races"] == 10
        assert summary["riders"] == 80
        assert summary["results"] > 0
        assert summary["classifications"] > 0

    def test_races_use_demo_id_range(self, session):
        generate_demo_data(session, num_races=5, seed=42)
        races = session.query(Race).all()
        for race in races:
            assert race.id >= DEMO_ID_BASE

    def test_scrape_logs_marked_demo(self, session):
        generate_demo_data(session, num_races=5, seed=42)
        logs = session.query(ScrapeLog).all()
        for log in logs:
            assert log.status == DEMO_SCRAPE_STATUS

    def test_all_finish_types_represented(self, session):
        generate_demo_data(session, num_races=50, seed=42)
        classifications = session.query(RaceClassification).all()
        found_types = {c.finish_type for c in classifications}
        # With 50 races × ~4 categories, we should hit most types
        assert len(found_types) >= 6

    def test_all_states_represented(self, session):
        generate_demo_data(session, num_races=50, seed=42)
        races = session.query(Race).all()
        states = {r.state_province for r in races}
        assert states == {"WA", "OR", "ID", "BC"}

    def test_spans_five_years(self, session):
        generate_demo_data(session, num_races=50, seed=42)
        races = session.query(Race).all()
        years = {r.date.year for r in races}
        assert years == {2020, 2021, 2022, 2023, 2024}

    def test_deterministic_with_same_seed(self, session, engine):
        """Same seed produces identical data."""
        summary1 = generate_demo_data(session, num_races=10, seed=99)
        # Create a fresh session for comparison
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        summary2 = generate_demo_data(session, num_races=10, seed=99)
        assert summary1 == summary2

    def test_cv_spans_confidence_levels(self, session):
        """CV values should span green/orange/red thresholds."""
        generate_demo_data(session, num_races=50, seed=42)
        classifications = session.query(RaceClassification).all()
        cvs = [c.cv_of_times for c in classifications if c.cv_of_times is not None]
        has_green = any(cv < 0.005 for cv in cvs)
        has_orange = any(0.005 <= cv < 0.015 for cv in cvs)
        has_red = any(cv >= 0.015 for cv in cvs)
        assert has_green, "No high-confidence (green) classifications"
        assert has_orange, "No moderate-confidence (orange) classifications"
        assert has_red, "No low-confidence (red) classifications"


class TestClearDemoData:
    def test_removes_all_demo_data(self, session):
        generate_demo_data(session, num_races=10, seed=42)
        assert session.query(Race).count() > 0
        clear_demo_data(session)
        assert session.query(Race).count() == 0
        assert session.query(ScrapeLog).count() == 0

    def test_preserves_non_demo_data(self, session):
        """Real data should not be deleted."""
        # Add a "real" race
        session.add(Race(id=1, name="Real Race", state_province="WA"))
        session.add(ScrapeLog(race_id=1, status="success"))
        session.commit()

        generate_demo_data(session, num_races=5, seed=42)
        clear_demo_data(session)

        assert session.query(Race).count() == 1
        assert session.query(Race).first().name == "Real Race"

    def test_clear_empty_db_is_noop(self, session):
        summary = clear_demo_data(session)
        assert summary["races"] == 0
```

---

## Files Summary

| File | Action | Description |
|------|--------|-------------|
| `raceanalyzer/demo.py` | **Create** | Demo data generator: ~300 lines, race/rider/result generation with finish-type-aware time distributions, cleanup function |
| `raceanalyzer/cli.py` | **Modify** | Add `seed-demo` and `clear-demo` Click commands (~30 lines) |
| `tests/test_demo.py` | **Create** | Tests for time generation, metrics computation, seed/clear lifecycle (~18 tests) |

**Total new files**: 2
**Total modified files**: 1
**Estimated new test count**: ~18

---

## Definition of Done

1. `python -m raceanalyzer seed-demo` populates the DB with ~50 races across 5 years (2020–2024), 4 states (WA, OR, ID, BC), 6 categories, and all 8 finish types
2. `python -m raceanalyzer clear-demo` removes all demo data; real scraped data is untouched
3. Demo race IDs are in the 900_001+ range — no collisions with real data
4. Time distributions are realistic per finish type: bunch sprints are tight, breakaways have clear gaps, GC selective is spread out
5. CV values span all three confidence badge colors (green < 0.005, orange 0.005–0.015, red >= 0.015)
6. UI Race Calendar shows ~50 races across all years and states after seeding
7. UI Race Detail shows per-category classifications with all three badge colors represented across the dataset
8. UI Finish Type Dashboard shows distribution charts with all 8 finish types; trend chart shows 5 years of data with visible variation
9. `seed-demo` is idempotent — running twice doesn't duplicate (IDs are deterministic)
10. All existing tests still pass (zero regressions)
11. New tests pass: time distribution properties, metrics computation, seed/clear lifecycle, data integrity
12. Python 3.9 compatible: `from __future__ import annotations` in all new files
13. No new external dependencies (stdlib `random` only)

---

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Generated time distributions don't match what the real classifier would produce | Misleading demo data | Medium | Time generation mirrors the classifier's grouping logic (3s gap threshold); metrics are computed from actual generated times, not hardcoded |
| Race ID collisions if user has scraped 900K+ races | Data corruption | Very Low | `max_race_id` in Settings is 15,000; ID base of 900,001 has >885K buffer |
| Rider pool of 80 is too small for 50 races × ~4 categories | Same riders appear everywhere | Low | Acceptable for demo purposes; riders are sampled per-field so they appear in realistic subsets |
| `clear-demo` accidentally deletes real data | Data loss | Low | Cleanup keys on `ScrapeLog.status == "demo"`, not ID range; real scrapes have status "success"/"error"/"not_found" |
| Random seed variance means some finish types appear 0 times in small datasets | Missing finish types in UI | Medium | With 50 races × ~4 categories (~200 classifications), probability of missing any type is very low; test asserts ≥6 of 8 types present |

---

## Open Questions

1. **Should `seed-demo` check for existing demo data first?** Running it twice with the same seed would hit unique constraint errors on race IDs. Options: (a) auto-clear first, (b) skip if demo data exists, (c) error with message. **Recommendation**: Auto-clear first with a log message — simplest UX.

2. **Should we add a `--years` flag to control the year range?** The default 2020–2024 covers 5 years for good trend data, but a presenter might want 2019–2024 for 6 years. **Recommendation**: Defer — hardcoded range is fine for disposable demo data.

3. **Category name consistency**: The demo uses clean names like "Men Pro/1/2" while real data has variations ("Men P12", "Cat 1/2 Men"). Should demo data include messy variants to be more realistic? **Recommendation**: No — clean names make the demo look better. Category normalization is a separate concern.

4. **Should demo riders have `license_number` values?** The model supports it but real road-results data may not always have it. **Recommendation**: Leave as None — matches realistic partial data.

5. **Year-over-year trend shaping**: Should we introduce deliberate year-to-year shifts in finish type weights (e.g., more breakaways in recent years) to make the trend chart more interesting? **Recommendation**: Try the natural random variance first. If the trend chart looks too flat, add a small year modifier in a follow-up.
