"""Race series name normalization and grouping."""

from __future__ import annotations

import re
from functools import lru_cache

from sqlalchemy.orm import Session

from raceanalyzer.db.models import Race, RaceSeries

# Suffix normalization: abbreviation -> canonical form
_SUFFIX_MAP = {
    "rr": "road race",
    "r.r.": "road race",
    "cr": "circuit race",
    "c.r.": "circuit race",
    "tt": "time trial",
    "t.t.": "time trial",
    "itt": "individual time trial",
    "i.t.t.": "individual time trial",
    "crit": "criterium",
    "hc": "hill climb",
    "h.c.": "hill climb",
    "gp": "grand prix",
    "g.p.": "grand prix",
}

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_ORDINAL_RE = re.compile(r"\b\d{1,2}(?:st|nd|rd|th)\b", re.IGNORECASE)
_ANNUAL_RE = re.compile(r"\bannual\b", re.IGNORECASE)
_NOISE_RE = re.compile(r"\b(presented by|sponsored by|powered by)\b.*", re.IGNORECASE)

# Roman numerals I-XXX (longest first to match greedily)
_ROMAN_RE = re.compile(
    r"\b(XXX|XXIX|XXVIII|XXVII|XXVI|XXV|XXIV|XXIII|XXII|XXI|"
    r"XX|XIX|XVIII|XVII|XVI|XV|XIV|XIII|XII|XI|"
    r"X|IX|VIII|VII|VI|V|IV|III|II|I)\b"
)

# Edition digit stripping: "Mason Lake 1" → "Mason Lake", "Mason Lake 1 and 2" → "Mason Lake"
_COMPOUND_EDITION_RE = re.compile(r"\s+\d{1,2}\s*(?:and|&)\s*\d{1,2}\s*$", re.IGNORECASE)
_EDITION_DIGIT_RE = re.compile(r"\s+\d{1,2}\s*$")

# Hash-number edition: "Mason Lake Road Race #1" → "Mason Lake Road Race"
_HASH_EDITION_RE = re.compile(r"\s*#\d{1,2}\s*$")

# Trailing "Series" noise: "Mason Lake Road Race Series" → "Mason Lake Road Race"
_SERIES_SUFFIX_RE = re.compile(r"\s+series\s*$", re.IGNORECASE)

# Post-normalization alias map: merges known venue name variants.
# Key = normalized form that should be collapsed, value = canonical form.
_ALIAS_MAP = {
    "mason lake road race": "mason lake",
}


@lru_cache(maxsize=2048)
def normalize_race_name(name: str) -> str:
    """Normalize a race name to a series key.

    Examples:
        "2024 Banana Belt RR"          -> "banana belt road race"
        "Banana Belt Road Race 2023"   -> "banana belt road race"
        "Pacific Raceways XXI"         -> "pacific raceways"
        "Mason Lake I"                 -> "mason lake"
        "21st Annual Mutual of Enumclaw" -> "mutual of enumclaw"
    """
    s = name.strip()

    # Strip year patterns
    s = _YEAR_RE.sub("", s)

    # Strip ordinals and "annual"
    s = _ORDINAL_RE.sub("", s)
    s = _ANNUAL_RE.sub("", s)

    # Strip Roman numerals
    s = _ROMAN_RE.sub("", s)

    # Strip sponsor noise
    s = _NOISE_RE.sub("", s)

    # Strip hash-number editions (#1, #2)
    s = _HASH_EDITION_RE.sub("", s)

    # Strip trailing "Series"
    s = _SERIES_SUFFIX_RE.sub("", s)

    # Strip compound edition markers first ("Mason Lake 1 and 2"), then trailing digits
    # Guardrail: only apply if result still has ≥2 whitespace-separated tokens
    compound_candidate = _COMPOUND_EDITION_RE.sub("", s).strip()
    if compound_candidate != s.strip() and len(compound_candidate.split()) >= 2:
        s = compound_candidate
    else:
        digit_candidate = _EDITION_DIGIT_RE.sub("", s).strip()
        if digit_candidate != s.strip() and len(digit_candidate.split()) >= 2:
            s = digit_candidate

    # Lowercase for suffix matching
    s = s.lower().strip()

    # Normalize suffixes
    for abbrev, canonical in _SUFFIX_MAP.items():
        pattern = re.compile(r"\b" + re.escape(abbrev) + r"\b")
        s = pattern.sub(canonical, s)

    # Collapse whitespace, strip punctuation edges
    s = re.sub(r"\s+", " ", s).strip().strip("-\u2013\u2014,.")

    # Apply alias map for known venue name variants
    s = _ALIAS_MAP.get(s, s)

    return s


def pick_display_name(race_names: list[str]) -> str:
    """Choose the best display name from edition names.

    Picks the longest (most descriptive) name with year stripped.
    """
    if not race_names:
        return "Unknown Series"
    best = max(race_names, key=len)
    best = _YEAR_RE.sub("", best).strip()
    best = re.sub(r"\s+", " ", best).strip().strip("-\u2013\u2014,.")
    return best


def build_series(session: Session) -> dict:
    """Group all races into series by normalized name. Idempotent.

    Creates RaceSeries rows and sets series_id on each Race.
    Returns: {series_created: int, races_linked: int}.
    """
    races = session.query(Race).all()
    groups: dict[str, list[Race]] = {}
    for race in races:
        key = normalize_race_name(race.name)
        groups.setdefault(key, []).append(race)

    series_created = 0
    races_linked = 0

    for norm_name, edition_races in groups.items():
        # Find or create series
        series = (
            session.query(RaceSeries)
            .filter(RaceSeries.normalized_name == norm_name)
            .first()
        )
        if series is None:
            display = pick_display_name([r.name for r in edition_races])
            series = RaceSeries(normalized_name=norm_name, display_name=display)
            session.add(series)
            session.flush()
            series_created += 1

        for race in edition_races:
            if race.series_id != series.id:
                race.series_id = series.id
                races_linked += 1

    session.commit()
    return {"series_created": series_created, "races_linked": races_linked}
