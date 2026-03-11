"""Parsers for road-results.com HTML pages and JSON API responses."""

from __future__ import annotations

import logging
import re
from datetime import datetime

from raceanalyzer.scraper.errors import NoResultsError, UnexpectedParsingError
from raceanalyzer.utils.time_parsing import parse_race_time

logger = logging.getLogger(__name__)

# Regex patterns for HTML metadata extraction
METADATA_REGEX = re.compile(r'resultstitle" ?>(.*?)[\n\r]')
DATE_REGEX = re.compile(r"([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})")

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


class RacePageParser:
    """Extracts metadata from a road-results.com race HTML page."""

    def __init__(self, race_id: int, html: str):
        self.race_id = race_id
        self._html = html
        self._metadata: dict | None = None

    def _extract_metadata(self) -> dict:
        if self._metadata is not None:
            return self._metadata

        match = METADATA_REGEX.search(self._html)
        if not match:
            raise UnexpectedParsingError(
                f"Could not find resultstitle in HTML for race {self.race_id}"
            )

        raw = match.group(1)
        parts = [p.strip() for p in raw.split("&bull;")]

        result = {"name": parts[0] if parts else "Unknown"}

        if len(parts) > 1:
            result["date"] = self._parse_date(parts[1])
            result["date_raw"] = parts[1]

        if len(parts) > 2:
            location_parts = [p.strip() for p in parts[2].split(",")]
            if len(location_parts) >= 2:
                result["state_province"] = location_parts[-1].strip().split()[0]
                # Location is everything except the last part (state)
                result["location"] = ", ".join(location_parts[:-1]).strip()
            else:
                result["location"] = parts[2].strip()

        self._metadata = result
        return result

    def _parse_date(self, date_str: str) -> datetime | None:
        match = DATE_REGEX.search(date_str)
        if not match:
            return None
        month_str, day_str, year_str = match.groups()
        month = MONTH_MAP.get(month_str)
        if month is None:
            return None
        try:
            return datetime(int(year_str), month, int(day_str))
        except ValueError:
            return None

    def name(self) -> str:
        return self._extract_metadata().get("name", "Unknown")

    def date(self) -> datetime | None:
        return self._extract_metadata().get("date")

    def location(self) -> str | None:
        return self._extract_metadata().get("location")

    def state_province(self) -> str | None:
        return self._extract_metadata().get("state_province")

    def parse(self) -> dict:
        """Return all extracted metadata as a dict."""
        meta = self._extract_metadata()
        return {
            "race_id": self.race_id,
            "name": meta.get("name", "Unknown"),
            "date": meta.get("date"),
            "location": meta.get("location"),
            "state_province": meta.get("state_province"),
        }


class PredictorCategoryParser:
    """Parses predictor.aspx category discovery response (Sprint 009)."""

    def __init__(self, html: str):
        self._html = html

    def categories(self) -> list[dict]:
        """Extract category entries from predictor HTML.

        Returns: [{"cat_id": str, "cat_name": str}]
        Conservative: returns [] on unexpected structure.
        """
        try:
            pattern = re.compile(
                r"<span\s+class=['\"]categoryname['\"]"
                r"\s+raceid=['\"]([^'\"]+)['\"]"
                r"\s*>(.*?)</span>",
                re.IGNORECASE,
            )
            matches = pattern.findall(self._html)
            return [{"cat_id": m[0], "cat_name": m[1].strip()} for m in matches]
        except Exception:
            logger.warning("Failed to parse predictor categories")
            return []

    def total_riders(self) -> int | None:
        """Extract total rider count from 'This race has N racers preregistered'."""
        try:
            match = re.search(r"This race has (\d+) racers? preregistered", self._html)
            return int(match.group(1)) if match else None
        except Exception:
            return None


class PredictorRiderParser:
    """Parses predictor.aspx per-category rider response (Sprint 009)."""

    def __init__(self, html: str):
        self._html = html

    def riders(self) -> list[dict]:
        """Extract ranked riders from predictor HTML table.

        Returns: [{"rank": int, "name": str, "racer_id": int, "team": str, "points": float}]
        Conservative: returns [] on unexpected structure.
        """
        try:
            # Find the data table
            table_match = re.search(
                r"<table[^>]*class=['\"]datatable1['\"][^>]*>(.*?)</table>",
                self._html,
                re.DOTALL | re.IGNORECASE,
            )
            if not table_match:
                return []

            table_html = table_match.group(1)
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL | re.IGNORECASE)

            riders = []
            for row_html in rows:
                cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL | re.IGNORECASE)
                if len(cells) < 3:
                    continue

                # Cell 0: "N. <a href='?n=racers&sn=r&rID=1162'>Name</a>"
                cell0 = cells[0].strip()

                # Extract rank
                rank_match = re.match(r"(\d+)\.", cell0)
                rank = int(rank_match.group(1)) if rank_match else None

                # Extract name and racer_id from link
                link_match = re.search(
                    r"rID=(\d+)['\"]?\s*>(.*?)</a>", cell0, re.IGNORECASE
                )
                if not link_match:
                    continue
                racer_id = int(link_match.group(1))
                name = link_match.group(2).strip()

                # Strip asterisks (road-results uses them for riders with < 4 scoring races)
                name = name.replace("*", "").strip()

                # Cell 1: team
                team = re.sub(r"<[^>]+>", "", cells[1]).strip()

                # Cell 2: points
                points_str = re.sub(r"<[^>]+>", "", cells[2]).strip()
                try:
                    points = float(points_str)
                except (ValueError, TypeError):
                    points = None

                riders.append({
                    "rank": rank,
                    "name": name,
                    "racer_id": racer_id,
                    "team": team,
                    "points": points,
                })

            return riders

        except Exception:
            logger.warning("Failed to parse predictor riders")
            return []


class RaceResultParser:
    """Parses the JSON API response into normalized result dicts."""

    def __init__(self, race_id: int, raw_json: list[dict]):
        self.race_id = race_id
        self._data = raw_json

    @staticmethod
    def _safe_int(val) -> int | None:
        if val is None or val == "":
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_float(val) -> float | None:
        if val is None or val == "":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def results(self) -> list[dict]:
        """Parse all results into normalized dicts."""
        if not self._data:
            raise NoResultsError(f"No results for race {self.race_id}")

        parsed = []
        for row in self._data:
            # Name: try FirstName+LastName first, fall back to Name
            first = (row.get("FirstName") or "").strip()
            last = (row.get("LastName") or "").strip()
            if first or last:
                name = f"{first} {last}".strip()
            else:
                name = (row.get("Name") or "").strip()
            if not name:
                continue

            place = self._safe_int(row.get("Place"))

            time_str = row.get("RaceTime") or ""
            time_seconds = parse_race_time(time_str)

            # FieldSize or RacerCount
            field_size = self._safe_int(
                row.get("FieldSize") or row.get("RacerCount") or row.get("Starters")
            )

            # Age: CalculatedAge or ReportedAge or Age
            age = self._safe_int(
                row.get("CalculatedAge") or row.get("ReportedAge") or row.get("Age")
            )

            points = self._safe_float(row.get("Points"))

            # CarriedPoints or PriorPoints
            carried_points = self._safe_float(
                row.get("CarriedPoints") or row.get("PriorPoints")
            )

            racer_id = self._safe_int(row.get("RacerID"))

            # Status flags: check IsDnf/IsDQ/IsDNP fields first, then RaceTime string
            status = (time_str or "").upper().strip()
            dnf = bool(row.get("IsDnf")) or "DNF" in status
            dq = bool(row.get("IsDQ")) or "DQ" in status
            dnp = bool(row.get("IsDNP")) or "DNP" in status or "DNS" in status

            # Team: TeamName or Team
            team = (row.get("TeamName") or row.get("Team") or "").strip() or None

            # License
            license_val = (str(row.get("License") or "")).strip() or None

            parsed.append({
                "race_id": self.race_id,
                "place": place,
                "name": name,
                "team": team,
                "age": age,
                "city": (row.get("City") or "").strip() or None,
                "state_province": (row.get("State") or "").strip() or None,
                "license": license_val,
                "race_category_name": (row.get("RaceCategoryName") or "").strip() or None,
                "race_time": time_str.strip() if time_str else None,
                "race_time_seconds": time_seconds,
                "field_size": field_size,
                "dnf": dnf,
                "dq": dq,
                "dnp": dnp,
                "points": points,
                "carried_points": carried_points,
                "racer_id": racer_id,
            })

        return parsed

    def categories(self) -> list[str]:
        """Extract unique category names."""
        cats = set()
        for row in self._data:
            cat = row.get("RaceCategoryName", "").strip()
            if cat:
                cats.add(cat)
        return sorted(cats)
