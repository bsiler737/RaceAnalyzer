"""Synthetic demo data generator for RaceAnalyzer.

Generates ~50 realistic PNW bike races with results and classifications
that exercise all UI features. Uses no external dependencies.
"""

from __future__ import annotations

import math
import random
from datetime import datetime

from sqlalchemy.orm import Session

from raceanalyzer.db.models import (
    FinishType,
    Race,
    RaceClassification,
    RaceType,
    Result,
    Rider,
    ScrapeLog,
)
from raceanalyzer.queries import infer_race_type

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

# PNW season: Feb–Oct
RACE_MONTHS = [2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10]

# Finish type weights per category
FINISH_TYPE_WEIGHTS: dict[str, dict[FinishType, float]] = {
    "Men Pro/1/2": {
        FinishType.BUNCH_SPRINT: 0.20, FinishType.SMALL_GROUP_SPRINT: 0.15,
        FinishType.BREAKAWAY: 0.20, FinishType.BREAKAWAY_SELECTIVE: 0.10,
        FinishType.REDUCED_SPRINT: 0.15, FinishType.GC_SELECTIVE: 0.05,
        FinishType.MIXED: 0.10, FinishType.UNKNOWN: 0.05,
    },
    "Men Cat 3": {
        FinishType.BUNCH_SPRINT: 0.35, FinishType.SMALL_GROUP_SPRINT: 0.20,
        FinishType.BREAKAWAY: 0.10, FinishType.BREAKAWAY_SELECTIVE: 0.05,
        FinishType.REDUCED_SPRINT: 0.15, FinishType.GC_SELECTIVE: 0.02,
        FinishType.MIXED: 0.08, FinishType.UNKNOWN: 0.05,
    },
    "Men Cat 4/5": {
        FinishType.BUNCH_SPRINT: 0.45, FinishType.SMALL_GROUP_SPRINT: 0.20,
        FinishType.BREAKAWAY: 0.05, FinishType.BREAKAWAY_SELECTIVE: 0.02,
        FinishType.REDUCED_SPRINT: 0.10, FinishType.GC_SELECTIVE: 0.01,
        FinishType.MIXED: 0.10, FinishType.UNKNOWN: 0.07,
    },
    "Women Pro/1/2/3": {
        FinishType.BUNCH_SPRINT: 0.25, FinishType.SMALL_GROUP_SPRINT: 0.20,
        FinishType.BREAKAWAY: 0.15, FinishType.BREAKAWAY_SELECTIVE: 0.08,
        FinishType.REDUCED_SPRINT: 0.15, FinishType.GC_SELECTIVE: 0.04,
        FinishType.MIXED: 0.08, FinishType.UNKNOWN: 0.05,
    },
    "Women Cat 4": {
        FinishType.BUNCH_SPRINT: 0.35, FinishType.SMALL_GROUP_SPRINT: 0.20,
        FinishType.BREAKAWAY: 0.08, FinishType.BREAKAWAY_SELECTIVE: 0.02,
        FinishType.REDUCED_SPRINT: 0.15, FinishType.GC_SELECTIVE: 0.02,
        FinishType.MIXED: 0.10, FinishType.UNKNOWN: 0.08,
    },
    "Masters Men 40+": {
        FinishType.BUNCH_SPRINT: 0.25, FinishType.SMALL_GROUP_SPRINT: 0.15,
        FinishType.BREAKAWAY: 0.15, FinishType.BREAKAWAY_SELECTIVE: 0.10,
        FinishType.REDUCED_SPRINT: 0.15, FinishType.GC_SELECTIVE: 0.05,
        FinishType.MIXED: 0.10, FinishType.UNKNOWN: 0.05,
    },
}


# PNW city center coordinates for route generation
PNW_CITY_COORDS: dict[str, tuple[float, float]] = {
    "Maryhill": (45.68, -120.85),
    "Niles": (45.52, -122.68),
    "Shelton": (47.21, -123.10),
    "Enumclaw": (47.20, -121.99),
    "Seattle": (47.61, -122.33),
    "Ridgefield": (45.81, -122.74),
    "Wenatchee": (47.42, -120.31),
    "Boise": (43.62, -116.21),
    "The Dalles": (45.60, -121.18),
    "Portland": (45.52, -122.68),
    "Redmond": (47.67, -122.12),
    "Hood River": (45.71, -121.52),
    "Medford": (42.33, -122.87),
    "Whidbey Island": (48.22, -122.68),
    "Twin Falls": (42.56, -114.46),
    "Vancouver": (49.28, -123.12),
    "Delta": (49.09, -123.06),
    "White Rock": (49.02, -122.80),
    "Baker City": (44.77, -117.83),
    "Bend": (44.06, -121.31),
    "Bainbridge Island": (47.63, -122.52),
}


def _generate_course_coords(
    location: str,
    race_type: RaceType,
    rng: random.Random,
) -> tuple[list[float], list[float]]:
    """Generate a plausible course polyline near a PNW city.

    Returns (latitudes, longitudes) as lists of ~10-20 floats.
    """
    center = PNW_CITY_COORDS.get(location, (47.0, -122.0))
    center_lat, center_lon = center
    lats: list[float] = []
    lons: list[float] = []

    if race_type == RaceType.CRITERIUM:
        scale = 0.008 + rng.uniform(0, 0.004)
        corners = [
            (0, 0), (scale, 0.2 * scale), (scale, scale),
            (0.2 * scale, scale * 1.1), (0, 0),
        ]
        for dlat, dlon in corners:
            lats.append(center_lat + dlat)
            lons.append(center_lon + dlon)
        smooth_lats, smooth_lons = [], []
        for i in range(len(lats) - 1):
            smooth_lats.append(lats[i])
            smooth_lons.append(lons[i])
            smooth_lats.append((lats[i] + lats[i + 1]) / 2 + rng.uniform(-0.001, 0.001))
            smooth_lons.append((lons[i] + lons[i + 1]) / 2 + rng.uniform(-0.001, 0.001))
        smooth_lats.append(lats[-1])
        smooth_lons.append(lons[-1])
        lats, lons = smooth_lats, smooth_lons

    elif race_type == RaceType.HILL_CLIMB:
        num_points = 15
        for i in range(num_points):
            t = i / (num_points - 1)
            lats.append(center_lat + t * 0.04 + rng.uniform(-0.002, 0.002))
            lons.append(center_lon + t * 0.01 + rng.uniform(-0.003, 0.003))

    elif race_type == RaceType.TIME_TRIAL:
        num_points = 10
        for i in range(num_points):
            t = i / (num_points - 1)
            lats.append(center_lat + t * 0.03 + rng.uniform(-0.001, 0.001))
            lons.append(center_lon + t * 0.02 + rng.uniform(-0.001, 0.001))

    elif race_type == RaceType.STAGE_RACE:
        num_points = 16
        for i in range(num_points):
            angle = 2 * math.pi * i / (num_points - 1)
            radius_lat = 0.06 + rng.uniform(-0.02, 0.02)
            radius_lon = 0.08 + rng.uniform(-0.02, 0.02)
            lats.append(center_lat + radius_lat * math.sin(angle))
            lons.append(center_lon + radius_lon * math.cos(angle))
        lats.append(lats[0])
        lons.append(lons[0])

    elif race_type == RaceType.GRAVEL:
        num_points = 14
        for i in range(num_points):
            angle = 2 * math.pi * i / (num_points - 1)
            radius = 0.03 + rng.uniform(-0.01, 0.015)
            lats.append(center_lat + radius * math.sin(angle) + rng.uniform(-0.005, 0.005))
            lons.append(center_lon + radius * 1.3 * math.cos(angle) + rng.uniform(-0.005, 0.005))
        lats.append(lats[0])
        lons.append(lons[0])

    else:  # ROAD_RACE or UNKNOWN
        num_points = 14
        for i in range(num_points):
            angle = 2 * math.pi * i / (num_points - 1)
            radius_lat = 0.03 + rng.uniform(-0.005, 0.005)
            radius_lon = 0.05 + rng.uniform(-0.01, 0.01)
            lats.append(center_lat + radius_lat * math.sin(angle))
            lons.append(center_lon + radius_lon * math.cos(angle))
        lats.append(lats[0])
        lons.append(lons[0])

    return lats, lons


def _coords_to_text(coords: list[float]) -> str:
    """Convert list of floats to comma-separated string for DB storage."""
    return ",".join(f"{c:.5f}" for c in coords)


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
    """
    results = []
    num_dnf = max(0, int(field_size * random.uniform(0.0, 0.08)))
    num_finishers = field_size - num_dnf

    times: list[float] = []

    if finish_type == FinishType.BUNCH_SPRINT:
        for i in range(num_finishers):
            gap = random.uniform(0, 0.3) * (i + 1)
            times.append(base_time + gap)

    elif finish_type == FinishType.SMALL_GROUP_SPRINT:
        lead_size = random.randint(5, min(10, num_finishers))
        for i in range(lead_size):
            times.append(base_time + random.uniform(0, 0.3) * (i + 1))
        gap = random.uniform(20.0, 45.0)
        for i in range(num_finishers - lead_size):
            times.append(base_time + gap + random.uniform(0, 15.0) + i * 0.5)

    elif finish_type == FinishType.BREAKAWAY:
        break_size = random.randint(1, 3)
        for i in range(break_size):
            times.append(base_time + i * random.uniform(1.0, 5.0))
        gap = random.uniform(30.0, 90.0)
        for i in range(num_finishers - break_size):
            times.append(base_time + gap + random.uniform(0, 0.3) * (i + 1))

    elif finish_type == FinishType.BREAKAWAY_SELECTIVE:
        break_size = random.randint(2, 5)
        for i in range(break_size):
            times.append(base_time + i * random.uniform(5.0, 15.0))
        gap = random.uniform(40.0, 80.0)
        for i in range(num_finishers - break_size):
            times.append(base_time + gap + random.uniform(0, 10.0) + i * 0.8)

    elif finish_type == FinishType.REDUCED_SPRINT:
        lead_size = random.randint(8, min(12, num_finishers))
        for i in range(lead_size):
            times.append(base_time + random.uniform(0, 0.4) * (i + 1))
        for i in range(num_finishers - lead_size):
            times.append(base_time + 15.0 + i * random.uniform(3.0, 8.0))

    elif finish_type == FinishType.GC_SELECTIVE:
        for i in range(num_finishers):
            times.append(base_time + i * random.uniform(5.0, 20.0))

    elif finish_type == FinishType.MIXED:
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

    groups: dict[int, int] = {}
    for r in finishers:
        gid = r["gap_group_id"]
        groups[gid] = groups.get(gid, 0) + 1

    sorted_groups = sorted(groups.items())
    num_groups = len(sorted_groups)
    largest_group_size = max(groups.values())
    leader_group_size = sorted_groups[0][1] if sorted_groups else 0

    gap_to_second = 0.0
    if num_groups >= 2:
        group_0_max_time = max(
            r["race_time_seconds"] for r in finishers if r["gap_group_id"] == 0
        )
        group_1_min_time = min(
            r["race_time_seconds"] for r in finishers if r["gap_group_id"] == 1
        )
        gap_to_second = round(group_1_min_time - group_0_max_time, 2)

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

    Auto-clears existing demo data first for idempotency.
    Returns summary dict with counts of created entities.
    """
    random.seed(seed)

    # Auto-clear existing demo data
    existing = (
        session.query(ScrapeLog)
        .filter(ScrapeLog.status == DEMO_SCRAPE_STATUS)
        .count()
    )
    if existing > 0:
        clear_demo_data(session)

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
    session.flush()

    race_count = 0
    result_count = 0
    classification_count = 0
    years = [2020, 2021, 2022, 2023, 2024]

    for year in years:
        races_this_year = random.sample(
            PNW_RACES,
            k=min(len(PNW_RACES), num_races // len(years) + random.randint(-2, 2)),
        )

        for race_name, location, state in races_this_year:
            race_id = DEMO_ID_BASE + race_count
            month = random.choice(RACE_MONTHS)
            day = random.randint(1, 28)
            race_date = datetime(year, month, day)

            race_type = infer_race_type(race_name)
            course_lats, course_lons = _generate_course_coords(
                location, race_type, random.Random(race_id),
            )

            race = Race(
                id=race_id,
                name=race_name,
                date=race_date,
                location=location,
                state_province=state,
                url=f"https://www.road-results.com/Race/{race_id}",
                race_type=race_type,
                course_lat=_coords_to_text(course_lats),
                course_lon=_coords_to_text(course_lons),
            )
            session.add(race)

            session.add(ScrapeLog(
                race_id=race_id,
                status=DEMO_SCRAPE_STATUS,
                scraped_at=datetime.utcnow(),
                result_count=0,
            ))

            num_cats = random.randint(3, len(CATEGORIES))
            race_categories = random.sample(CATEGORIES, k=num_cats)

            is_crit = "crit" in race_name.lower() or "short track" in race_name.lower()
            base_time = (
                random.uniform(2400, 3200) if is_crit
                else random.uniform(7200, 10800)
            )

            race_result_count = 0
            for category in race_categories:
                finish_type = _pick_finish_type(category)
                field_size = (
                    random.randint(12, 45) if "Pro" in category
                    else random.randint(8, 30)
                )

                field_riders = random.sample(
                    db_riders, k=min(field_size, len(db_riders))
                )
                time_results = _generate_times(finish_type, field_size, base_time)

                for j, tr in enumerate(time_results):
                    rider = field_riders[j] if j < len(field_riders) else None
                    rider_info = (
                        rider_pool[db_riders.index(rider)] if rider
                        else {
                            "name": f"Unknown Rider {j}",
                            "team": None, "city": None,
                            "state": None, "age": None,
                        }
                    )
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
                        race_time=(
                            _format_race_time(tr["race_time_seconds"])
                            if tr["race_time_seconds"] else None
                        ),
                        race_time_seconds=tr["race_time_seconds"],
                        field_size=field_size,
                        dnf=tr["dnf"],
                        gap_to_leader=tr["gap_to_leader"],
                        gap_group_id=tr["gap_group_id"],
                    ))
                    result_count += 1
                    race_result_count += 1

                metrics = _compute_classification_metrics(time_results, finish_type)
                session.add(RaceClassification(
                    race_id=race_id,
                    category=category,
                    finish_type=finish_type,
                    **metrics,
                ))
                classification_count += 1

            log = (
                session.query(ScrapeLog)
                .filter(ScrapeLog.race_id == race_id)
                .first()
            )
            if log:
                log.result_count = race_result_count

            race_count += 1

    # Assign carried_points based on result history
    # Riders who place well accumulate more points (simulates road-results Elo)
    for rider in db_riders:
        results = (
            session.query(Result)
            .filter(Result.rider_id == rider.id, Result.dnf.is_(False), Result.place.isnot(None))
            .all()
        )
        points = 0.0
        for r in results:
            if r.place == 1:
                points += random.uniform(8.0, 15.0)
            elif r.place <= 3:
                points += random.uniform(3.0, 8.0)
            elif r.place <= 5:
                points += random.uniform(1.0, 4.0)
            elif r.place <= 10:
                points += random.uniform(0.5, 2.0)
        # Write carried_points to all of this rider's results
        if points > 0:
            rider_results = (
                session.query(Result).filter(Result.rider_id == rider.id).all()
            )
            for r in rider_results:
                r.carried_points = round(points, 1)

    session.commit()

    return {
        "races": race_count,
        "riders": len(db_riders),
        "results": result_count,
        "classifications": classification_count,
    }


def clear_demo_data(session: Session) -> dict:
    """Remove all demo data identified by ScrapeLog status='demo'.

    Returns summary dict with counts of deleted entities.
    """
    demo_logs = (
        session.query(ScrapeLog)
        .filter(ScrapeLog.status == DEMO_SCRAPE_STATUS)
        .all()
    )
    demo_race_ids = [log.race_id for log in demo_logs]

    if not demo_race_ids:
        return {"races": 0, "riders": 0}

    races = session.query(Race).filter(Race.id.in_(demo_race_ids)).all()
    race_count = len(races)

    for race in races:
        session.delete(race)

    for log in demo_logs:
        session.delete(log)

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
