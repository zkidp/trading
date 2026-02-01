from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RawNewsIn:
    source: str
    raw_title: str
    url: str
    fetched_at: datetime


class RedditCollector:
    def __init__(self, subreddits: list[str], limit: int = 50) -> None:
        self._subreddits = subreddits
        self._limit = limit

    def fetch(self) -> list[RawNewsIn]:
        """Fetch Reddit posts.

        NOTE: Implementation to be added.
        """
        return []
