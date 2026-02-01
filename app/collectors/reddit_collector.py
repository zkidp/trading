from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

from loguru import logger


@dataclass(frozen=True)
class RawNewsIn:
    source: str
    raw_title: str
    url: str
    fetched_at: datetime


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RedditCollector:
    def __init__(self, subreddits: list[str], limit: int = 50) -> None:
        self._subreddits = subreddits
        self._limit = limit

    def fetch(self) -> list[RawNewsIn]:
        """Fetch Reddit hot posts titles.

        Env vars required:
        - REDDIT_CLIENT_ID
        - REDDIT_CLIENT_SECRET
        - REDDIT_USER_AGENT

        Failure should degrade gracefully: return empty list.
        """
        client_id = os.getenv("REDDIT_CLIENT_ID")
        client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        user_agent = os.getenv("REDDIT_USER_AGENT")
        if not client_id or not client_secret or not user_agent:
            logger.warning("Reddit key 未配置：跳过 Reddit 抓取")
            return []

        try:
            import praw  # local import to avoid hard failure if dependency missing
        except Exception:
            logger.exception("praw 导入失败：跳过 Reddit 抓取")
            return []

        fetched_at = _utc_now()
        seen: set[str] = set()
        out: list[RawNewsIn] = []

        try:
            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
            )
            for sub in self._subreddits:
                try:
                    sr = reddit.subreddit(sub)
                    posts = list(sr.hot(limit=self._limit))
                    logger.info("Reddit 抓取 | subreddit=r/{} | posts={}", sub, len(posts))

                    for p in posts:
                        title = (getattr(p, "title", None) or "").strip()
                        permalink = (getattr(p, "permalink", None) or "").strip()
                        url = f"https://www.reddit.com{permalink}" if permalink else (getattr(p, "url", None) or "")
                        url = url.strip()
                        # Ensure url is not empty; DB dedup relies on url unique.
                        if not title and not url:
                            continue

                        key = url or title
                        if key in seen:
                            continue
                        seen.add(key)

                        out.append(
                            RawNewsIn(
                                source=f"reddit:r/{sub}",
                                raw_title=title or url,
                                url=url,
                                fetched_at=fetched_at,
                            )
                        )
                except Exception:
                    logger.exception("Reddit 抓取失败 | subreddit=r/{}", sub)
                    continue
        except Exception:
            logger.exception("Reddit 初始化失败：跳过 Reddit 抓取")
            return []

        return out
