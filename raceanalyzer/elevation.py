"""Terrain classification, profile processing, and climb detection."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from raceanalyzer.config import Settings
from raceanalyzer.db.models import CourseType


def compute_m_per_km(
    total_gain_m: Optional[float], distance_m: Optional[float]
) -> Optional[float]:
    """Compute meters of climbing per kilometer. Returns None if inputs missing."""
    if total_gain_m is None or distance_m is None or distance_m <= 0:
        return None
    return total_gain_m / (distance_m / 1000.0)


def _uci_climb_category(length_km: float, avg_grade: float) -> int:
    """Estimate UCI-style climb category (4=easiest, 0=HC).

    Based on standard categorization rules:
    - HC: 15+km@8%+ or 20+km@4%+
    - Cat 1: 5-10km@8%+ or 10-15km@6%+
    - Cat 2: 5-10km@5-7% or 10+km@3-5%
    - Cat 3: 2-4km@6%+ or 4-6km@4%+
    - Cat 4: 2km@6%+ or 4km@4%+
    Returns 5 if not a categorizable climb.
    """
    score = length_km * avg_grade  # simple difficulty product
    if score >= 120 or (length_km >= 20 and avg_grade >= 4) or (length_km >= 15 and avg_grade >= 8):
        return 0  # HC
    if score >= 60 or (length_km >= 10 and avg_grade >= 6) or (length_km >= 5 and avg_grade >= 8):
        return 1
    if score >= 30 or (length_km >= 10 and avg_grade >= 3.5) or (length_km >= 5 and avg_grade >= 5):
        return 2
    if score >= 12 or (length_km >= 4 and avg_grade >= 4) or (length_km >= 2 and avg_grade >= 6):
        return 3
    if score >= 8 or (length_km >= 2 and avg_grade >= 4):
        return 4
    return 5  # not a real climb


def classify_terrain(
    m_per_km: Optional[float],
    settings: Optional[Settings] = None,
    climbs: Optional[list[dict]] = None,
) -> CourseType:
    """Classify terrain using m/km ratio adjusted by climb quality.

    When climb data is available, the hardest climb's UCI category
    can push the classification up or pull it down. Short, shallow
    climbs (all Cat 4+) on a moderate-m/km course = rolling, not hilly.
    Long sustained climbs (Cat 1-2) on a moderate course = hilly or mountainous.
    """
    if m_per_km is None:
        return CourseType.UNKNOWN

    if settings is None:
        settings = Settings()

    # Base classification from m/km
    if m_per_km < settings.terrain_flat_max:
        base = CourseType.FLAT
    elif m_per_km < settings.terrain_rolling_max:
        base = CourseType.ROLLING
    elif m_per_km < settings.terrain_hilly_max:
        base = CourseType.HILLY
    else:
        base = CourseType.MOUNTAINOUS

    # Adjust based on climb characteristics if available
    if not climbs:
        return base

    # Find the hardest climb (lowest UCI category number = hardest)
    best_cat = 5
    for cl in climbs:
        length_km = cl.get("length_m", 0) / 1000.0
        avg_grade = cl.get("avg_grade", 0)
        cat = _uci_climb_category(length_km, avg_grade)
        if cat < best_cat:
            best_cat = cat

    # Adjustment rules:
    # If all climbs are Cat 4+ (nothing harder), cap at ROLLING
    if best_cat >= 4 and base in (CourseType.HILLY, CourseType.MOUNTAINOUS):
        return CourseType.ROLLING

    # If hardest climb is Cat 3, floor at HILLY (real categorized climb)
    if best_cat <= 3 and base in (CourseType.FLAT, CourseType.ROLLING):
        return CourseType.HILLY

    # If hardest climb is Cat 1 or HC, floor at MOUNTAINOUS if m/km > 12
    if best_cat <= 1 and m_per_km >= 12:
        return CourseType.MOUNTAINOUS

    # If hardest climb is Cat 2 and total climbing is heavy, push to MOUNTAINOUS
    if best_cat <= 2 and m_per_km >= 12:
        return CourseType.MOUNTAINOUS

    return base


COURSE_TYPE_DISPLAY_NAMES = {
    "flat": "Flat",
    "rolling": "Rolling",
    "hilly": "Hilly",
    "mountainous": "Mountainous",
    "unknown": "Unknown Terrain",
}

COURSE_TYPE_DESCRIPTIONS = {
    "flat": "Minimal climbing. Expect bunch finishes unless wind or tactics break it up.",
    "rolling": "Moderate climbing. Strong all-rounders and punchy riders thrive.",
    "hilly": "Significant climbing. Climbers and breakaway artists have the advantage.",
    "mountainous": "Major climbing. Pure climbers dominate; the field will shatter.",
    "unknown": "No elevation data available for this course.",
}


def course_type_display(course_type_value: str) -> str:
    """Convert CourseType enum value to human-readable name."""
    return COURSE_TYPE_DISPLAY_NAMES.get(
        course_type_value, course_type_value.replace("_", " ").title()
    )


# --- GPX parsing ---


def parse_gpx_track_points(gpx_path: Path) -> list[dict]:
    """Parse a GPX file into track points with cumulative distance.

    Returns the same format as extract_track_points: [{d, e, y, x}, ...].
    Works with both Strava and RideWithGPS GPX exports.
    """
    tree = ET.parse(gpx_path)
    root = tree.getroot()

    # Handle GPX namespace
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    result: list[dict] = []
    cum_dist = 0.0

    for trkpt in root.iter(f"{ns}trkpt"):
        lat_s = trkpt.get("lat")
        lon_s = trkpt.get("lon")
        if lat_s is None or lon_s is None:
            continue

        lat = float(lat_s)
        lon = float(lon_s)

        ele_el = trkpt.find(f"{ns}ele")
        elev = float(ele_el.text) if ele_el is not None and ele_el.text else 0.0

        if result:
            prev = result[-1]
            cum_dist += _haversine(prev["y"], prev["x"], lat, lon)

        result.append({"d": cum_dist, "e": elev, "y": lat, "x": lon})

    return result


def gpx_to_encoded_polyline(track_points: list[dict]) -> Optional[str]:
    """Encode parsed GPX track points as a Google encoded polyline."""
    if not track_points:
        return None
    import polyline as pl

    coords = [(pt["y"], pt["x"]) for pt in track_points]
    return pl.encode(coords)


def compute_elevation_stats(track_points: list[dict]) -> Optional[dict]:
    """Compute elevation stats from parsed track points (GPX or RWGPS).

    Returns dict matching the shape of rwgps.fetch_route_elevation output.
    """
    if not track_points or len(track_points) < 2:
        return None

    total_gain = 0.0
    total_loss = 0.0
    elevations = [pt["e"] for pt in track_points]

    for i in range(1, len(track_points)):
        delta = track_points[i]["e"] - track_points[i - 1]["e"]
        if delta > 0:
            total_gain += delta
        else:
            total_loss += abs(delta)

    return {
        "distance_m": track_points[-1]["d"],
        "total_gain_m": total_gain,
        "total_loss_m": total_loss,
        "max_elevation_m": max(elevations),
        "min_elevation_m": min(elevations),
    }


# --- Profile processing ---


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in meters between two lat/lon points."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371000.0 * 2 * math.asin(math.sqrt(a))


def extract_track_points(route_json: dict) -> list[dict]:
    """Parse RWGPS route JSON into structured track points with cumulative distance.

    Each point: {d: cumulative_distance_m, e: elevation_m, y: lat, x: lon}.
    Returns empty list if no usable track points.
    """
    raw_points = route_json.get("track_points", [])
    if not raw_points:
        return []

    result = []
    cum_dist = 0.0

    for i, pt in enumerate(raw_points):
        lat = pt.get("y", pt.get("lat"))
        lon = pt.get("x", pt.get("lng"))
        elev = pt.get("e", pt.get("elevation"))

        if lat is None or lon is None or elev is None:
            continue

        lat, lon, elev = float(lat), float(lon), float(elev)

        if result:
            prev = result[-1]
            cum_dist += _haversine(prev["y"], prev["x"], lat, lon)

        result.append({"d": cum_dist, "e": elev, "y": lat, "x": lon})

    return result


def resample_profile(
    track_points: list[dict], step_m: float = 50.0
) -> list[dict]:
    """Resample track points to uniform spacing via linear interpolation.

    Input points must have keys: d (cumulative distance), e, y, x.
    Returns points at every step_m meters.
    """
    if len(track_points) < 2:
        return list(track_points)

    total_dist = track_points[-1]["d"]
    if total_dist <= 0:
        return list(track_points)

    result = []
    src_idx = 0
    n_steps = int(total_dist / step_m)

    for i in range(n_steps + 1):
        target_d = i * step_m
        if target_d > total_dist:
            target_d = total_dist

        # Advance source index
        while src_idx < len(track_points) - 2 and track_points[src_idx + 1]["d"] < target_d:
            src_idx += 1

        p0 = track_points[src_idx]
        p1 = track_points[min(src_idx + 1, len(track_points) - 1)]

        seg_len = p1["d"] - p0["d"]
        if seg_len > 0:
            t = (target_d - p0["d"]) / seg_len
        else:
            t = 0.0

        t = max(0.0, min(1.0, t))

        result.append({
            "d": round(target_d, 1),
            "e": round(p0["e"] + t * (p1["e"] - p0["e"]), 1),
            "y": round(p0["y"] + t * (p1["y"] - p0["y"]), 6),
            "x": round(p0["x"] + t * (p1["x"] - p0["x"]), 6),
        })

    return result


def smooth_elevations(
    profile: list[dict], window_m: float = 200.0, step_m: float = 50.0
) -> list[dict]:
    """Apply Gaussian-weighted rolling average to elevation values.

    Preserves real gradient changes while eliminating GPS jitter.
    The window_m parameter controls the width of the Gaussian kernel.
    """
    if len(profile) < 2:
        return list(profile)

    sigma = window_m / 4.0  # ~95% of weight within window
    half_window_pts = max(1, int(window_m / step_m))
    result = []

    for i, pt in enumerate(profile):
        weight_sum = 0.0
        elev_sum = 0.0

        lo = max(0, i - half_window_pts)
        hi = min(len(profile), i + half_window_pts + 1)

        for j in range(lo, hi):
            dist = abs(profile[j]["d"] - pt["d"])
            w = math.exp(-0.5 * (dist / sigma) ** 2)
            weight_sum += w
            elev_sum += w * profile[j]["e"]

        smoothed_e = elev_sum / weight_sum if weight_sum > 0 else pt["e"]
        result.append({**pt, "e": round(smoothed_e, 1)})

    return result


def compute_gradients(profile: list[dict]) -> list[dict]:
    """Compute gradient (percent) at each point using smoothed elevation.

    Gradient = (elevation_change / distance_change) * 100.
    First point gets gradient 0.
    """
    if len(profile) < 2:
        return [{**pt, "g": 0.0} for pt in profile]

    result = [{**profile[0], "g": 0.0}]

    for i in range(1, len(profile)):
        dd = profile[i]["d"] - profile[i - 1]["d"]
        de = profile[i]["e"] - profile[i - 1]["e"]
        gradient = (de / dd * 100.0) if dd > 0 else 0.0
        result.append({**profile[i], "g": round(gradient, 1)})

    return result


def build_profile(track_points: list[dict], step_m: float = 50.0) -> list[dict]:
    """Full pipeline: resample -> smooth -> compute gradients.

    Returns list of {d, e, y, x, g} dicts ready for JSON storage.
    """
    if len(track_points) < 2:
        return []

    resampled = resample_profile(track_points, step_m=step_m)
    smoothed = smooth_elevations(resampled, step_m=step_m)
    return compute_gradients(smoothed)


# --- Climb detection ---


@dataclass
class Climb:
    """A detected climb segment."""

    start_d: float  # Start distance along route (meters)
    end_d: float  # End distance along route (meters)
    length_m: float
    gain_m: float
    avg_grade: float
    max_grade: float
    category: str  # "moderate", "steep", "brutal"
    color: str  # Hex color for visualization
    start_coords: list  # [lat, lon]
    end_coords: list  # [lat, lon]


# Climb category thresholds and colors
_CLIMB_CATEGORIES = [
    (8.0, "brutal", "#B71C1C"),
    (5.0, "steep", "#FF5722"),
    (0.0, "moderate", "#FFC107"),
]


def _categorize_climb(avg_grade: float) -> tuple[str, str]:
    """Return (category, color) for a climb based on average gradient."""
    for threshold, category, color in _CLIMB_CATEGORIES:
        if avg_grade >= threshold:
            return category, color
    return "moderate", "#FFC107"


def detect_climbs(
    profile_points: list[dict],
    *,
    entry_grade: float = 2.5,
    entry_sustain_m: float = 150.0,
    exit_grade: float = 1.0,
    exit_sustain_m: float = 200.0,
    merge_gap_m: float = 150.0,
    min_length_m: float = 500.0,
    min_gain_m: float = 20.0,
    min_avg_grade: float = 3.0,
) -> list[dict]:
    """Detect climbs using a two-state machine with merge and filter.

    Parameters control the detection thresholds (configurable via Settings).
    Returns list of climb dicts ready for JSON storage.
    """
    if len(profile_points) < 2:
        return []

    # Pass 1: State machine detection
    raw_climbs = []
    state = "FLAT"
    climb_start_idx = 0
    sustain_start_d = 0.0

    for i, pt in enumerate(profile_points):
        g = pt.get("g", 0.0)

        if state == "FLAT":
            if g >= entry_grade:
                if sustain_start_d == 0.0:
                    sustain_start_d = pt["d"]
                    climb_start_idx = i
                if pt["d"] - sustain_start_d >= entry_sustain_m:
                    state = "CLIMBING"
            else:
                sustain_start_d = 0.0

        elif state == "CLIMBING":
            if g < exit_grade:
                if sustain_start_d == 0.0:
                    sustain_start_d = pt["d"]
                if pt["d"] - sustain_start_d >= exit_sustain_m:
                    # End of climb
                    raw_climbs.append((climb_start_idx, i))
                    state = "FLAT"
                    sustain_start_d = 0.0
            else:
                sustain_start_d = 0.0

    # If still climbing at the end, close the climb
    if state == "CLIMBING":
        raw_climbs.append((climb_start_idx, len(profile_points) - 1))

    if not raw_climbs:
        return []

    # Pass 2: Merge adjacent climbs separated by small gaps
    merged = [raw_climbs[0]]
    for start_idx, end_idx in raw_climbs[1:]:
        prev_end = merged[-1][1]
        gap = profile_points[start_idx]["d"] - profile_points[prev_end]["d"]
        if gap <= merge_gap_m:
            merged[-1] = (merged[-1][0], end_idx)
        else:
            merged.append((start_idx, end_idx))

    # Pass 3: Compute metrics and filter
    result = []
    for start_idx, end_idx in merged:
        start_pt = profile_points[start_idx]
        end_pt = profile_points[end_idx]
        length_m = end_pt["d"] - start_pt["d"]

        if length_m <= 0:
            continue

        # Compute gain and max gradient over the segment
        gain = 0.0
        max_g = 0.0
        for j in range(start_idx, end_idx + 1):
            g = profile_points[j].get("g", 0.0)
            if g > max_g:
                max_g = g
            if j > start_idx:
                de = profile_points[j]["e"] - profile_points[j - 1]["e"]
                if de > 0:
                    gain += de

        avg_grade = (gain / length_m * 100.0) if length_m > 0 else 0.0

        # Apply filters
        if length_m < min_length_m or gain < min_gain_m or avg_grade < min_avg_grade:
            continue

        category, color = _categorize_climb(avg_grade)

        result.append({
            "start_d": round(start_pt["d"], 0),
            "end_d": round(end_pt["d"], 0),
            "length_m": round(length_m, 0),
            "gain_m": round(gain, 0),
            "avg_grade": round(avg_grade, 1),
            "max_grade": round(max_g, 1),
            "category": category,
            "color": color,
            "start_coords": [start_pt["y"], start_pt["x"]],
            "end_coords": [end_pt["y"], end_pt["x"]],
        })

    return result
