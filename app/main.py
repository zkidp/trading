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


def _get_str_env(name: str, default: str) -> str:
    raw = os.getenv(name)
    return default if raw is None else raw.strip()


def _split_keywords(raw: str) -> list[str]:
    kws = [x.strip().lower() for x in raw.split(",")]
    return [x for x in kws if x]


async def _async_main() -> int:
    dry_run = _get_bool_env("DRY_RUN", True)
    trading_mode = os.getenv("TRADING_MODE", "paper")
    run_phase = _get_str_env("RUN_PHASE", "preopen")

    logger.info(
        "AI-Quant 启动 | now_utc={} | phase={} | dry_run={} | trading_mode={}",
        _utc_now().isoformat(),
        run_phase,
        dry_run,
        trading_mode,
    )

    # Step 1 (P0-3): DB init.
    engine = build_engine()
    try:
        await init_db(engine)
    finally:
        await engine.dispose()

    # Step 1.5: Daily account/position snapshot for preopen/postclose (best effort).
    if run_phase.lower() in {"preopen", "postclose"}:
        try:
            from app.broker.executor import IBExecutor
            from app.broker.observer import fetch_account_values, fetch_positions
            from app.db.snapshots import insert_account_snapshot, insert_position_snapshots

            now_utc = _utc_now()
            async with IBExecutor(dry_run=True) as ex:
                account_v = await fetch_account_values(ex.ib)
                positions_v = await fetch_positions(ex.ib)

            engine = build_engine()
            session_maker = build_session_maker(engine)
            try:
                async with session_maker() as session:
                    await insert_account_snapshot(session, account_v, created_at=now_utc)
                    await insert_position_snapshots(session, positions_v, created_at=now_utc)
                    await session.commit()
            finally:
                await engine.dispose()

            logger.info("已记录账户/持仓快照 | positions={}", len(positions_v))
        except Exception:
            logger.exception("账户/持仓快照失败（不影响后续流程）")

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

        # Monitor-only mode: keyword alerts (no AI / no trading).
        if run_phase.lower() == "monitor":
            raw_kw = _get_str_env(
                "NEWS_KEYWORDS",
                "trump,tariff,china,fed,powell,cpi,inflation,jobs,recession,shutdown,ai,nvidia,nvda,datacenter,gpu,compute,cloud,power,grid,utilities,semiconductor",
            )
            keywords = _split_keywords(raw_kw)
            hits: dict[str, list[tuple[str, str, str]]] = {}
            for item in raw_items:
                title_l = item.raw_title.lower()
                for kw in keywords:
                    if kw and kw in title_l:
                        hits.setdefault(kw, []).append((item.source, item.raw_title, item.url))

            if hits:
                engine = build_engine()
                session_maker = build_session_maker(engine)
                now_utc = _utc_now()
                try:
                    from app.db.alerts import insert_news_alerts
                    from app.news_writer import NewsHit, append_news_markdown

                    flat_hits: list[NewsHit] = []
                    async with session_maker() as session:
                        for kw, rows in hits.items():
                            await insert_news_alerts(session, keyword=kw, items=rows, created_at=now_utc)
                            for (src, title, url) in rows:
                                flat_hits.append(NewsHit(keyword=kw, source=src, title=title, url=url))
                        await session.commit()

                    md_path = append_news_markdown(now_utc=now_utc, hits=flat_hits)
                finally:
                    await engine.dispose()

                logger.warning(
                    "新闻监控命中 | keywords={} | hits={} | md_path={}",
                    list(hits.keys()),
                    sum(len(v) for v in hits.values()),
                    str(md_path) if md_path else None,
                )
            else:
                logger.info("新闻监控：未命中关键词")

            return 0
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
                inserted_rows = await insert_raw_news(session, raw_items)
                await session.commit()
        finally:
            await engine.dispose()

        logger.info(
            "RawNews 入库完成 | total={} | inserted={} (url unique 去重)",
            len(raw_items),
            len(inserted_rows),
        )

        # For preopen/postclose, it's useful to still track the account even if no trade happens.
        # We'll snapshot later after we have Top1 (and possibly trade).
    except Exception:
        logger.exception("RawNews 入库阶段异常：安全退出（不交易）")
        return 0

    # Step 4/5 (P0-5/6): AI analyze + write SentimentSignal + select Top1.
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        logger.warning("DEEPSEEK_API_KEY 未配置：跳过 AI 分析与交易（安全）")
        return 0

    try:
        from app.db.crud import insert_signals, select_top1_today_no_risk
        from app.processors.ai_analyzer import AIAnalyzer

        if not inserted_rows:
            logger.warning("本次没有新增 RawNews：跳过 AI 分析与交易（安全）")
            return 0

        titles = [x.raw_title for x in inserted_rows if x.raw_title]
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

        from app.broker.risk import get_float_env, get_int_env
        from app.db.execution import count_executions_since, insert_execution

        amount_usd = float(os.getenv("INVEST_AMOUNT_USD", "40"))
        dry_run_effective = _get_bool_env("DRY_RUN", True)

        min_sent = get_float_env("MIN_SENTIMENT_TO_TRADE", 0.3)
        max_daily_trades = get_int_env("MAX_DAILY_TRADES", 1)

        if float(top1.score) < float(min_sent):
            logger.warning("Top1 分数低于阈值：不交易 | score={} < min_sentiment={}", top1.score, min_sent)
            return 0

        now_utc = _utc_now()
        day_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

        engine = build_engine()
        session_maker = build_session_maker(engine)
        try:
            async with session_maker() as session:
                trades_today = await count_executions_since(session, day_start)
        finally:
            await engine.dispose()

        if trades_today >= max_daily_trades:
            logger.warning(
                "触发 MAX_DAILY_TRADES：不交易 | trades_today={} | max_daily_trades={}",
                trades_today,
                max_daily_trades,
            )
            return 0

        error: str | None = None
        result = None
        snapshot_err: str | None = None

        try:
            async with IBExecutor(dry_run=dry_run_effective) as ex:
                # Daily monitoring: record account + positions snapshot (best effort).
                try:
                    from app.broker.observer import fetch_account_values, fetch_positions
                    from app.db.snapshots import insert_account_snapshot, insert_position_snapshots

                    account_v = await fetch_account_values(ex.ib)
                    positions_v = await fetch_positions(ex.ib)

                    engine = build_engine()
                    session_maker = build_session_maker(engine)
                    try:
                        async with session_maker() as session:
                            await insert_account_snapshot(session, account_v, created_at=now_utc)
                            await insert_position_snapshots(session, positions_v, created_at=now_utc)
                            await session.commit()
                    finally:
                        await engine.dispose()
                except Exception as e:
                    snapshot_err = str(e)
                    logger.exception("持仓/账户快照失败（不影响交易决策）")

                result = await ex.buy_fractional_by_amount(top1.ticker, amount_usd=amount_usd)

        except Exception as e:
            error = str(e)
            raise
        finally:
            # Always record an execution row for audit/kill-switch purposes.
            engine = build_engine()
            session_maker = build_session_maker(engine)
            try:
                async with session_maker() as session:
                    await insert_execution(
                        session,
                        ticker=top1.ticker,
                        amount_usd=amount_usd,
                        price=None if result is None else result.price,
                        qty=None if result is None else result.qty,
                        dry_run=dry_run_effective,
                        order_status=None if result is None else result.order_status,
                        error=error or snapshot_err,
                        created_at=now_utc,
                    )
                    await session.commit()
            finally:
                await engine.dispose()

        if result is None:
            logger.warning("未产生执行结果：不交易")
            return 0

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
