from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Note: keep ORM models simple; migrations can be added later if needed.


class Base(DeclarativeBase):
    pass


class RawNews(Base):
    __tablename__ = "raw_news"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SentimentSignal(Base):
    __tablename__ = "sentiment_signal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    ai_summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class TradeExecution(Base):
    __tablename__ = "trade_execution"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False)
    order_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class AccountSnapshot(Base):
    __tablename__ = "account_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    net_liquidation: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_cash: Mapped[float | None] = mapped_column(Float, nullable=True)
    buying_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    init_margin_req: Mapped[float | None] = mapped_column(Float, nullable=True)
    maint_margin_req: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class PositionSnapshot(Base):
    __tablename__ = "position_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    position: Mapped[float] = mapped_column(Float, nullable=False)
    avg_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unrealized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class NewsAlert(Base):
    __tablename__ = "news_alert"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyword: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class TradeOutcome(Base):
    __tablename__ = "trade_outcome"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_execution_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    # Evaluation aligned to NYSE sessions; stored as ISO date string for simplicity.
    entry_session: Mapped[str] = mapped_column(String(16), nullable=False)

    entry_close: Mapped[float] = mapped_column(Float, nullable=False)
    t3_close: Mapped[float] = mapped_column(Float, nullable=False)
    t7_close: Mapped[float] = mapped_column(Float, nullable=False)

    t3_return: Mapped[float] = mapped_column(Float, nullable=False)
    t7_return: Mapped[float] = mapped_column(Float, nullable=False)

    spy_t3_return: Mapped[float] = mapped_column(Float, nullable=False)
    spy_t7_return: Mapped[float] = mapped_column(Float, nullable=False)

    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
