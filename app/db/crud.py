from __future__ import annotations

from collections.abc import Sequence

from loguru import logger
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.rss_collector import RawNewsIn
from app.db.models import RawNews


async def insert_raw_news(session: AsyncSession, items: Sequence[RawNewsIn]) -> int:
    """Insert RawNews rows with ON CONFLICT DO NOTHING.

    Returns number of inserted rows (best effort; relies on rowcount).
    """
    if not items:
        return 0

    values = [
        {
            "source": i.source,
            "raw_title": i.raw_title,
            "url": i.url,
            "fetched_at": i.fetched_at,
        }
        for i in items
        if i.url  # url required for DB unique dedup
    ]

    if not values:
        logger.warning("RawNews 入库跳过：所有数据缺少 url")
        return 0

    stmt = insert(RawNews).values(values)
    stmt = stmt.on_conflict_do_nothing(index_elements=[RawNews.url])

    result = await session.execute(stmt)
    # rowcount is supported for INSERT ... ON CONFLICT DO NOTHING in many cases.
    inserted = int(result.rowcount or 0)
    return inserted
