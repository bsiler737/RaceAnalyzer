"""Two-tier error hierarchy for scraping.

ExpectedParsingError: silently handled (race cancelled, no results, 404).
UnexpectedParsingError: propagates (structural change, needs developer attention).
"""


class ExpectedParsingError(Exception):
    """Data unavailable for known reasons."""


class UnexpectedParsingError(Exception):
    """Structural change in API/HTML response."""


class RaceNotFoundError(ExpectedParsingError):
    """Race ID does not exist on road-results.com."""


class NoResultsError(ExpectedParsingError):
    """Race exists but has no posted results."""
