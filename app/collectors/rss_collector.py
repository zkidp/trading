from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RSSSource:
    name: str
    url: str


@dataclass(frozen=True)
class RawNewsIn:
    source: str
    raw_title: str
    url: str
    fetched_at: datetime


class RSSCollector:
    def __init__(self, sources: list[RSSSource]) -> None:
        self._sources = sources

    def fetch(self) -> list[RawNewsIn]:
        """Fetch RSS items.

        NOTE: Implementation to be added.
        """
        return []
