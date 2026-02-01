from __future__ import annotations

import os

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from tenacity import retry, stop_after_attempt, wait_exponential

from app.db.models import Base


def build_engine() -> AsyncEngine:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL 未设置")
    return create_async_engine(database_url, echo=False, pool_pre_ping=True)


def build_session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@retry(wait=wait_exponential(multiplier=1, min=1, max=8), stop=stop_after_attempt(8), reraise=True)
async def wait_for_db(engine: AsyncEngine) -> None:
    """Wait until database is reachable.

    This avoids app crash during docker-compose startup ordering.
    """
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def init_db(engine: AsyncEngine) -> None:
    logger.info("等待数据库就绪...")
    await wait_for_db(engine)

    logger.info("初始化数据库表结构（create_all）")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
