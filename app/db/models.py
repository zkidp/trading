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
