"""Main entrypoint for the daily AI-Quant job.

Safety rules:
- DRY_RUN defaults to true
- Any failure in external dependencies should result in NO trading

This file is implemented incrementally (small commits).
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone

from loguru import logger

from app.db.session import build_engine, build_session_maker, init_db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _get_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


async def _async_main() -> int:
    dry_run = _get_bool_env("DRY_RUN", True)
    trading_mode = os.getenv("TRADING_MODE", "paper")

    logger.info(
        "AI-Quant 启动 | now_utc={} | dry_run={} | trading_mode={}",
        _utc_now().isoformat(),
        dry_run,
        trading_mode,
    )

    # Step 1 (P0-3): DB init.
    engine = build_engine()
    try:
        await init_db(engine)
    finally:
        await engine.dispose()

    # Step 2 (P0-4): Collect titles.
    try:
        from app.collectors.rss_collector import RSSCollector, RSSSource
        from app.collectors.reddit_collector import RedditCollector

        rss_sources = [
            RSSSource(name="yahoo_finance", url="https://finance.yahoo.com/news/rssindex"),
            RSSSource(name="cnbc_topnews", url="https://www.cnbc.com/id/100003114/device/rss/rss.html"),
        ]
        rss_items = RSSCollector(rss_sources).fetch()
        reddit_items = RedditCollector(subreddits=["stocks", "investing"], limit=50).fetch()
        raw_items = rss_items + reddit_items
        logger.info(
            "采集完成 | rss={} | reddit={} | total={}",
            len(rss_items),
            len(reddit_items),
            len(raw_items),
        )
    except Exception:
        logger.exception("采集阶段异常：安全退出（不交易）")
        return 0

    # Step 3 (P0-6): Write RawNews (dedup by url unique).
    try:
        from app.db.crud import insert_raw_news

        engine = build_engine()
        session_maker = build_session_maker(engine)
        try:
            async with session_maker() as session:
                inserted = await insert_raw_news(session, raw_items)
                await session.commit()
        finally:
            await engine.dispose()

        logger.info("RawNews 入库完成 | total={} | inserted={} (url unique 去重)", len(raw_items), inserted)
    except Exception:
        logger.exception("RawNews 入库阶段异常：安全退出（不交易）")
        return 0

    logger.info("当前版本尚未实现 AI/交易，安全退出（不交易）。")
    return 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        logger.exception("主程序异常：安全退出（不交易）")
        sys.exit(1)
