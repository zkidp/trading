from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TradeExecution


async def count_executions_since(session: AsyncSession, start_utc: datetime) -> int:
    stmt = select(func.count()).select_from(TradeExecution).where(TradeExecution.created_at >= start_utc)
    res = await session.execute(stmt)
    return int(res.scalar_one())


async def insert_execution(
    session: AsyncSession,
    *,
    ticker: str,
    amount_usd: float,
    price: float | None,
    qty: float | None,
    dry_run: bool,
    order_status: str | None,
    error: str | None,
    created_at: datetime,
) -> None:
    session.add(
        TradeExecution(
            ticker=ticker,
            amount_usd=amount_usd,
            price=price,
            qty=qty,
            dry_run=dry_run,
            order_status=order_status,
            error=error,
            created_at=created_at,
        )
    )
