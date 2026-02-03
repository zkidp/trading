from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NewsAlert


async def insert_news_alerts(
    session: AsyncSession,
    *,
    keyword: str,
    items: Sequence[tuple[str, str, str]],
    created_at: datetime,
) -> int:
    """Insert alerts.

    items: (source, title, url)
    """
    if not items:
        return 0

    session.add_all(
        [
            NewsAlert(
                keyword=keyword,
                source=src,
                title=title,
                url=url,
                created_at=created_at,
            )
            for (src, title, url) in items
        ]
    )
    return len(items)
