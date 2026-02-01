from __future__ import annotations

import os

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base


def build_engine() -> AsyncEngine:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL 未设置")
    return create_async_engine(database_url, echo=False, pool_pre_ping=True)


def build_session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    logger.info("初始化数据库表结构（create_all）")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
