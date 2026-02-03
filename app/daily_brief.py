from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from loguru import logger
from sqlalchemy import desc, select

from app.db.models import AccountSnapshot, NewsAlert, PositionSnapshot, TradeExecution
from app.db.session import build_engine, build_session_maker, init_db


@dataclass(frozen=True)
class BriefData:
    alerts: list[NewsAlert]
    latest_account: AccountSnapshot | None
    positions: list[PositionSnapshot]
    executions: list[TradeExecution]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _get_str_env(name: str, default: str) -> str:
    raw = os.getenv(name)
    return default if raw is None else raw.strip()


def _default_brief_dir() -> Path:
    home = Path.home()
    return home / ".openclaw" / "discord-qmd" / "1467563842417590416" / "1467610706932269056" / "news" / "brief"


def _day_start_utc(now_utc: datetime) -> datetime:
    return now_utc.replace(hour=0, minute=0, second=0, microsecond=0)


async def _load_data(*, now_utc: datetime) -> BriefData:
    engine = build_engine()
    session_maker = build_session_maker(engine)
    try:
        # Ensure tables exist (safe create_all)
        await init_db(engine)

        async with session_maker() as session:
            start = _day_start_utc(now_utc)

            alerts_stmt = select(NewsAlert).where(NewsAlert.created_at >= start).order_by(NewsAlert.created_at.desc()).limit(200)
            alerts = list((await session.execute(alerts_stmt)).scalars().all())

            acct_stmt = select(AccountSnapshot).order_by(desc(AccountSnapshot.created_at)).limit(1)
            latest_account = (await session.execute(acct_stmt)).scalar_one_or_none()

            # Latest position snapshot batch: take last 1 hour window as "latest set"
            pos_cutoff = now_utc - timedelta(hours=1)
            pos_stmt = (
                select(PositionSnapshot)
                .where(PositionSnapshot.created_at >= pos_cutoff)
                .order_by(desc(PositionSnapshot.created_at))
                .limit(500)
            )
            positions = list((await session.execute(pos_stmt)).scalars().all())

            exec_stmt = select(TradeExecution).where(TradeExecution.created_at >= start).order_by(desc(TradeExecution.created_at)).limit(50)
            executions = list((await session.execute(exec_stmt)).scalars().all())

            return BriefData(alerts=alerts, latest_account=latest_account, positions=positions, executions=executions)
    finally:
        await engine.dispose()


def _render_markdown(*, now_utc: datetime, data: BriefData) -> str:
    lines: list[str] = []
    lines.append(f"# Daily Brief — {now_utc.date().isoformat()} (UTC)\n")
    lines.append(f"Generated at: {now_utc.isoformat()}Z\n")

    # Account
    lines.append("\n## Account Snapshot (latest)\n")
    a = data.latest_account
    if a is None:
        lines.append("- (no account snapshot)\n")
    else:
        lines.append(f"- NetLiquidation: {a.net_liquidation}\n")
        lines.append(f"- TotalCash: {a.total_cash}\n")
        lines.append(f"- BuyingPower: {a.buying_power}\n")
        lines.append(f"- InitMarginReq: {a.init_margin_req}\n")
        lines.append(f"- MaintMarginReq: {a.maint_margin_req}\n")
        lines.append(f"- at: {a.created_at.isoformat()}\n")

    # Positions
    lines.append("\n## Positions (latest ~1h window, may include duplicates)\n")
    if not data.positions:
        lines.append("- (no position snapshot)\n")
    else:
        # De-dup by ticker keeping first occurrence
        seen: set[str] = set()
        for p in data.positions:
            if p.ticker in seen:
                continue
            seen.add(p.ticker)
            lines.append(
                f"- {p.ticker}: pos={p.position} avg_cost={p.avg_cost} mkt_price={p.market_price} mkt_value={p.market_value} at={p.created_at.isoformat()}\n"
            )

    # Executions
    lines.append("\n## Executions (today)\n")
    if not data.executions:
        lines.append("- (no executions)\n")
    else:
        for e in data.executions:
            lines.append(
                f"- {e.created_at.isoformat()} | {e.ticker} | amount={e.amount_usd} | dry_run={e.dry_run} | price={e.price} | qty={e.qty} | status={e.order_status} | error={e.error}\n"
            )

    # Alerts
    lines.append("\n## News Alerts (today, keyword hits)\n")
    if not data.alerts:
        lines.append("- (no alerts)\n")
    else:
        # group by keyword
        by_kw: dict[str, list[NewsAlert]] = {}
        for al in data.alerts:
            by_kw.setdefault(al.keyword, []).append(al)

        for kw in sorted(by_kw.keys()):
            lines.append(f"\n### {kw}\n")
            for al in by_kw[kw][:30]:
                title = al.title.replace("\n", " ").strip()
                if al.url:
                    lines.append(f"- [{title}]({al.url}) — {al.source} ({al.created_at.isoformat()})\n")
                else:
                    lines.append(f"- {title} — {al.source} ({al.created_at.isoformat()})\n")

    return "".join(lines)


async def _async_main() -> int:
    now_utc = _utc_now()
    data = await _load_data(now_utc=now_utc)

    md = _render_markdown(now_utc=now_utc, data=data)

    out_dir = Path(_get_str_env("BRIEF_MD_DIR", str(_default_brief_dir())))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{now_utc.date().isoformat()}-brief.md"
    out_path.write_text(md, encoding="utf-8")

    logger.info("已生成每日简报 | path={}", str(out_path))
    return 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())
