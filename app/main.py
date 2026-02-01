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

from app.db.session import build_engine, init_db


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

    logger.info("数据库初始化完成。当前版本尚未实现采集/AI/交易，安全退出（不交易）。")
    return 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        logger.exception("主程序异常：安全退出（不交易）")
        sys.exit(1)
