from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.rss_collector import RawNewsIn
from app.db.models import RawNews, SentimentSignal
from app.processors.ai_analyzer import AnalyzedItem


@dataclass(frozen=True)
class InsertedRawNews:
    id: int
    source: str
    raw_title: str
    url: str
    fetched_at: datetime


async def insert_raw_news(session: AsyncSession, items: Sequence[RawNewsIn]) -> list[InsertedRawNews]:
    """Insert RawNews rows with ON CONFLICT DO NOTHING.

    Returns rows that were actually inserted (for downstream AI analysis dedup).
    """
    if not items:
        return []

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
        return []

    stmt = insert(RawNews).values(values)
    stmt = stmt.on_conflict_do_nothing(index_elements=[RawNews.url])
    stmt = stmt.returning(RawNews.id, RawNews.source, RawNews.raw_title, RawNews.url, RawNews.fetched_at)

    result = await session.execute(stmt)
    rows = result.fetchall()

    inserted: list[InsertedRawNews] = [
        InsertedRawNews(
            id=int(r.id),
            source=str(r.source),
            raw_title=str(r.raw_title),
            url=str(r.url),
            fetched_at=r.fetched_at,
        )
        for r in rows
    ]
    return inserted


async def insert_signals(session: AsyncSession, items: Sequence[AnalyzedItem], created_at: datetime) -> int:
    if not items:
        return 0

    rows = [
        SentimentSignal(
            ticker=i.ticker,
            score=i.sentiment,
            risk_tags=i.risk_tags,
            ai_summary=i.summary,
            created_at=created_at,
        )
        for i in items
    ]
    session.add_all(rows)
    return len(rows)


async def select_top1_today_no_risk(session: AsyncSession, day_start_utc: datetime) -> SentimentSignal | None:
    empty_risk = func.coalesce(func.jsonb_array_length(SentimentSignal.risk_tags), 0) == 0

    stmt = (
        select(SentimentSignal)
        .where(SentimentSignal.created_at >= day_start_utc)
        .where(SentimentSignal.ticker.is_not(None))
        .where(empty_risk)
        .order_by(SentimentSignal.score.desc())
        .limit(1)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()
