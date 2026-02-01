"""Main entrypoint for the daily AI-Quant job.

The system MUST be safe by default:
- DRY_RUN defaults to true
- Any failure in external dependencies should result in NO trading.

This module will be expanded step-by-step.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

from loguru import logger


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _get_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def main() -> int:
    dry_run = _get_bool_env("DRY_RUN", True)
    trading_mode = os.getenv("TRADING_MODE", "paper")

    logger.info("AI-Quant 启动 | now_utc={} | dry_run={} | trading_mode={}", _utc_now().isoformat(), dry_run, trading_mode)

    # Placeholder: real pipeline will be implemented in subsequent commits.
    logger.warning("当前为骨架版本：尚未实现采集/AI/落库/交易。系统将安全退出（不交易）。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        logger.exception("主程序异常：安全退出（不交易）")
        sys.exit(1)
