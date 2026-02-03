from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.broker.observer import AccountValues, PositionValues
from app.db.models import AccountSnapshot, PositionSnapshot


async def insert_account_snapshot(session: AsyncSession, v: AccountValues, created_at: datetime) -> None:
    session.add(
        AccountSnapshot(
            net_liquidation=v.net_liquidation,
            total_cash=v.total_cash,
            buying_power=v.buying_power,
            init_margin_req=v.init_margin_req,
            maint_margin_req=v.maint_margin_req,
            created_at=created_at,
        )
    )


async def insert_position_snapshots(session: AsyncSession, items: Sequence[PositionValues], created_at: datetime) -> int:
    if not items:
        return 0
    session.add_all(
        [
            PositionSnapshot(
                ticker=i.ticker,
                position=i.position,
                avg_cost=i.avg_cost,
                market_price=i.market_price,
                market_value=i.market_value,
                unrealized_pnl=i.unrealized_pnl,
                created_at=created_at,
            )
            for i in items
        ]
    )
    return len(items)
