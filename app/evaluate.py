from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pandas_market_calendars as mcal
import yfinance as yf
from loguru import logger
from sqlalchemy import select

from app.db.models import TradeExecution, TradeOutcome
from app.db.session import build_engine, build_session_maker, init_db

_ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class OutcomePrices:
    entry_close: float
    t3_close: float
    t7_close: float
    spy_entry_close: float
    spy_t3_close: float
    spy_t7_close: float


def _to_et_session_date(ts_utc: datetime) -> datetime.date:
    if ts_utc.tzinfo is None:
        ts_utc = ts_utc.replace(tzinfo=timezone.utc)
    return ts_utc.astimezone(_ET).date()


def _trading_sessions(start: datetime.date, end: datetime.date) -> list[datetime.date]:
    cal = mcal.get_calendar("NYSE")
    sched = cal.schedule(start_date=start, end_date=end)
    return [d.date() for d in sched.index.to_pydatetime()]


def _load_close_series(symbol: str, start: datetime.date, end: datetime.date) -> pd.Series:
    # yfinance returns timezone-aware index; we normalize to date.
    df = yf.download(symbol, start=str(start), end=str(end + timedelta(days=1)), progress=False, interval="1d", auto_adjust=False)
    if df is None or df.empty:
        raise RuntimeError(f"无法获取行情: {symbol}")
    close = df["Close"].copy()
    close.index = pd.to_datetime(close.index).date
    return close


def _pick_close(close: pd.Series, session: datetime.date) -> float:
    if session not in close.index:
        raise RuntimeError(f"缺少收盘价数据: session={session}")
    v = close.loc[session]
    return float(v)


def compute_outcome_prices(entry_session: datetime.date, symbol: str) -> OutcomePrices:
    # Need enough sessions for T+7 and some buffer.
    sessions = _trading_sessions(entry_session - timedelta(days=7), entry_session + timedelta(days=20))
    if entry_session not in sessions:
        # If entry day is not a trading day, use next trading day.
        next_sessions = [s for s in sessions if s > entry_session]
        if not next_sessions:
            raise RuntimeError("无法找到下一交易日")
        entry_session = next_sessions[0]

    idx = sessions.index(entry_session)
    t3 = sessions[idx + 3]
    t7 = sessions[idx + 7]

    # Pull prices for symbol and SPY
    start = sessions[max(0, idx - 5)]
    end = sessions[idx + 7] + timedelta(days=2)

    close_sym = _load_close_series(symbol, start, end)
    close_spy = _load_close_series("SPY", start, end)

    return OutcomePrices(
        entry_close=_pick_close(close_sym, entry_session),
        t3_close=_pick_close(close_sym, t3),
        t7_close=_pick_close(close_sym, t7),
        spy_entry_close=_pick_close(close_spy, entry_session),
        spy_t3_close=_pick_close(close_spy, t3),
        spy_t7_close=_pick_close(close_spy, t7),
    )


def _ret(a: float, b: float) -> float:
    return (b / a) - 1.0


async def _async_main() -> int:
    now_utc = datetime.now(timezone.utc)

    engine = build_engine()
    session_maker = build_session_maker(engine)
    try:
        await init_db(engine)

        async with session_maker() as session:
            # Find executions without outcome and older than ~2 trading days (data likely available).
            cutoff = now_utc - timedelta(days=2)
            stmt = (
                select(TradeExecution)
                .where(TradeExecution.created_at <= cutoff)
                .where(~TradeExecution.id.in_(select(TradeOutcome.trade_execution_id)))
                .order_by(TradeExecution.created_at.asc())
                .limit(50)
            )
            executions = list((await session.execute(stmt)).scalars().all())

        if not executions:
            logger.info("没有需要评估的执行记录")
            return 0

        inserted = 0
        for ex in executions:
            entry_session = _to_et_session_date(ex.created_at)
            try:
                prices = compute_outcome_prices(entry_session, ex.ticker)
                out = TradeOutcome(
                    trade_execution_id=ex.id,
                    ticker=ex.ticker,
                    entry_session=str(entry_session),
                    entry_close=prices.entry_close,
                    t3_close=prices.t3_close,
                    t7_close=prices.t7_close,
                    t3_return=_ret(prices.entry_close, prices.t3_close),
                    t7_return=_ret(prices.entry_close, prices.t7_close),
                    spy_t3_return=_ret(prices.spy_entry_close, prices.spy_t3_close),
                    spy_t7_return=_ret(prices.spy_entry_close, prices.spy_t7_close),
                    computed_at=now_utc,
                )

                async with session_maker() as session:
                    session.add(out)
                    await session.commit()
                inserted += 1
                logger.info("评估完成 | exec_id={} | {} | t3={:.3%} (spy={:.3%}) | t7={:.3%} (spy={:.3%})",
                            ex.id, ex.ticker, out.t3_return, out.spy_t3_return, out.t7_return, out.spy_t7_return)
            except Exception:
                logger.exception("评估失败 | exec_id={} | ticker={}", ex.id, ex.ticker)
                continue

        logger.info("评估写入完成 | outcomes_inserted={}", inserted)
        return 0

    finally:
        await engine.dispose()


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())
