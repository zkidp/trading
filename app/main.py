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

    # Step 4/5 (P0-5/6): AI analyze + write SentimentSignal + select Top1.
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        logger.warning("DEEPSEEK_API_KEY 未配置：跳过 AI 分析与交易（安全）")
        return 0

    try:
        from datetime import timedelta

        from app.db.crud import insert_signals, select_top1_today_no_risk
        from app.processors.ai_analyzer import AIAnalyzer

        titles = [x.raw_title for x in raw_items if x.raw_title]
        analyzer = AIAnalyzer(api_key=api_key, batch_size=15, timeout_s=25)
        analyzed = analyzer.analyze_titles(titles)

        now_utc = _utc_now()
        day_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

        engine = build_engine()
        session_maker = build_session_maker(engine)
        try:
            async with session_maker() as session:
                inserted_signals = await insert_signals(session, analyzed, created_at=now_utc)
                await session.commit()

                top1 = await select_top1_today_no_risk(session, day_start_utc=day_start)
        finally:
            await engine.dispose()

        logger.info("AI 分析完成 | titles={} | signals_inserted={}", len(titles), inserted_signals)
        if top1 is None:
            logger.warning("Top1 不存在（可能无 ticker 或都有风险标签）：今日不交易")
            return 0

        logger.info(
            "Top1 信号 | ticker={} | score={} | risk_tags={} | summary={}",
            top1.ticker,
            top1.score,
            top1.risk_tags,
            top1.ai_summary,
        )

    except Exception:
        logger.exception("AI/Signal 阶段异常：安全退出（不交易）")
        return 0

    # Step 6/7 (P0-7): IB executor
    try:
        from app.broker.executor import IBExecutor

        if top1.ticker is None:
            logger.warning("Top1 ticker 为空：不交易")
            return 0

        amount_usd = float(os.getenv("INVEST_AMOUNT_USD", "40"))
        dry_run_effective = _get_bool_env("DRY_RUN", True)

        async with IBExecutor(dry_run=dry_run_effective) as ex:
            result = await ex.buy_fractional_by_amount(top1.ticker, amount_usd=amount_usd)

        logger.info(
            "执行完成 | dry_run={} | ticker={} | amount_usd={} | price={} | qty={} | status={}",
            result.dry_run,
            result.ticker,
            result.amount_usd,
            result.price,
            result.qty,
            result.order_status,
        )

    except Exception:
        logger.exception("IB 执行阶段异常：安全退出（不交易）")
        return 0

    return 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        logger.exception("主程序异常：安全退出（不交易）")
        sys.exit(1)
