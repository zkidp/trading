from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalyzedItem:
    ticker: str | None
    sentiment: float
    summary: str
    risk_tags: list[str]


class AIAnalyzer:
    def __init__(self, api_key: str, batch_size: int = 15, timeout_s: int = 25) -> None:
        self._api_key = api_key
        self._batch_size = batch_size
        self._timeout_s = timeout_s

    def analyze_titles(self, titles: list[str]) -> list[AnalyzedItem]:
        """Analyze titles via DeepSeek.

        NOTE: Implementation to be added.
        """
        return []
