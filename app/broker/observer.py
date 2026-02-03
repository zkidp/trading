from __future__ import annotations

from dataclasses import dataclass

from ib_insync import IB, Stock


@dataclass(frozen=True)
class AccountValues:
    net_liquidation: float | None
    total_cash: float | None
    buying_power: float | None
    init_margin_req: float | None
    maint_margin_req: float | None


@dataclass(frozen=True)
class PositionValues:
    ticker: str
    position: float
    avg_cost: float | None
    market_price: float | None
    market_value: float | None
    unrealized_pnl: float | None


def _get_tag(values: list[object], tag: str) -> float | None:
    for v in values:
        # AccountValue has fields: tag, value, currency, account
        if getattr(v, "tag", None) == tag:
            raw = getattr(v, "value", None)
            try:
                return float(raw)
            except Exception:
                return None
    return None


async def fetch_account_values(ib: IB) -> AccountValues:
    values = await ib.accountSummaryAsync()
    return AccountValues(
        net_liquidation=_get_tag(values, "NetLiquidation"),
        total_cash=_get_tag(values, "TotalCashValue"),
        buying_power=_get_tag(values, "BuyingPower"),
        init_margin_req=_get_tag(values, "InitMarginReq"),
        maint_margin_req=_get_tag(values, "MaintMarginReq"),
    )


async def fetch_positions(ib: IB) -> list[PositionValues]:
    positions = ib.positions()  # local cache after connection; OK for snapshots
    out: list[PositionValues] = []
    contracts = []

    for p in positions:
        c = p.contract
        sym = getattr(c, "symbol", None)
        if not sym:
            continue
        out.append(
            PositionValues(
                ticker=str(sym),
                position=float(p.position),
                avg_cost=float(p.avgCost) if getattr(p, "avgCost", None) is not None else None,
                market_price=None,
                market_value=None,
                unrealized_pnl=None,
            )
        )
        contracts.append(Stock(str(sym), "SMART", "USD"))

    if not contracts:
        return out

    # Best-effort snapshot prices
    tickers = await ib.reqTickersAsync(*contracts)
    price_map: dict[str, float] = {}
    for t in tickers:
        sym = getattr(t.contract, "symbol", None)
        if not sym:
            continue
        mp = t.marketPrice()
        if mp is None:
            continue
        try:
            price_map[str(sym)] = float(mp)
        except Exception:
            continue

    out2: list[PositionValues] = []
    for p in out:
        mp = price_map.get(p.ticker)
        mv = None if mp is None else mp * p.position
        out2.append(
            PositionValues(
                ticker=p.ticker,
                position=p.position,
                avg_cost=p.avg_cost,
                market_price=mp,
                market_value=mv,
                unrealized_pnl=None,
            )
        )
    return out2
