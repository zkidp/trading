from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser
from loguru import logger


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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RSSCollector:
    def __init__(self, sources: list[RSSSource]) -> None:
        self._sources = sources

    def fetch(self) -> list[RawNewsIn]:
        """Fetch RSS items and normalize into RawNewsIn.

        - Dedup based on url or title (in-memory)
        - fetched_at is always UTC now
        """
        fetched_at = _utc_now()
        seen: set[str] = set()
        out: list[RawNewsIn] = []

        for src in self._sources:
            try:
                feed = feedparser.parse(src.url)
            except Exception:
                logger.exception("RSS 抓取失败 | source={} | url={}", src.name, src.url)
                continue

            entries = getattr(feed, "entries", []) or []
            logger.info("RSS 抓取 | source={} | entries={}", src.name, len(entries))

            for e in entries:
                title = (getattr(e, "title", None) or "").strip()
                url = (getattr(e, "link", None) or "").strip()
                if not title and not url:
                    continue

                key = url or title
                if key in seen:
                    continue
                seen.add(key)

                if not url:
                    # Without url, DB-level unique dedup cannot work reliably; still keep it in memory,
                    # but main pipeline will skip url-less records when inserting.
                    logger.debug("RSS 条目缺少 url | source={} | title={}", src.name, title)

                out.append(
                    RawNewsIn(
                        source=src.name,
                        raw_title=title or url,
                        url=url or "",
                        fetched_at=fetched_at,
                    )
                )

        return out
