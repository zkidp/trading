from __future__ import annotations

import os
from dataclasses import dataclass

from ib_insync import IB, MarketOrder, Stock
from loguru import logger


@dataclass(frozen=True)
class BuyResult:
    ticker: str
    amount_usd: float
    price: float | None
    qty: float | None
    dry_run: bool
    order_status: str | None


class IBExecutor:
    """IBKR executor.

    Safety:
    - dry_run defaults to True: never place a real order
    - TRADING_MODE must be "paper" (env enforced)
    """

    def __init__(
        self,
        dry_run: bool = True,
        host: str = "ib-gateway",
        port: int = 4001,
        client_id: int = 7,
    ) -> None:
        self._dry_run = dry_run
        self._host = host
        self._port = port
        self._client_id = client_id
        self._ib: IB | None = None

    async def __aenter__(self) -> "IBExecutor":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        await self.disconnect()

    async def connect(self) -> None:
        trading_mode = os.getenv("TRADING_MODE", "paper")
        if trading_mode.strip().lower() != "paper":
            raise RuntimeError(f"TRADING_MODE 必须为 paper（当前={trading_mode}）")

        ib = IB()
        logger.info("连接 IB Gateway | host={} | port={} | client_id={}", self._host, self._port, self._client_id)
        await ib.connectAsync(host=self._host, port=self._port, clientId=self._client_id, timeout=10)
        self._ib = ib
        logger.info("IB 连接成功")

    async def disconnect(self) -> None:
        if self._ib is None:
            return
        try:
            self._ib.disconnect()
        finally:
            self._ib = None

    async def buy_fractional_by_amount(self, ticker: str, amount_usd: float) -> BuyResult:
        """Buy fractional shares by USD amount.

        - Fetch snapshot price
        - qty = amount / price
        - dry_run: only log
        """
        if self._ib is None:
            raise RuntimeError("IB 未连接")

        if amount_usd <= 0:
            raise ValueError("amount_usd 必须 > 0")

        contract = Stock(ticker, "SMART", "USD")

        tickers = await self._ib.reqTickersAsync(contract)
        if not tickers:
            raise RuntimeError("未获取到行情")

        t = tickers[0]
        price = float(t.marketPrice()) if t.marketPrice() is not None else 0.0
        if price <= 0:
            raise RuntimeError(f"价格异常: price={price}")

        qty = amount_usd / price
        if qty <= 0 or qty <= 1e-6:
            raise RuntimeError(f"数量异常: qty={qty}")

        if self._dry_run:
            logger.info(
                "模拟买入 | amount_usd=${} | ticker={} | price={} | qty={}",
                amount_usd,
                ticker,
                price,
                qty,
            )
            return BuyResult(ticker=ticker, amount_usd=amount_usd, price=price, qty=qty, dry_run=True, order_status=None)

        order = MarketOrder("BUY", qty)
        trade = self._ib.placeOrder(contract, order)
        # Give TWS/IBG a moment to update status.
        await self._ib.sleep(1)
        status = getattr(trade.orderStatus, "status", None)

        logger.info(
            "真实下单 | amount_usd=${} | ticker={} | price={} | qty={} | status={}",
            amount_usd,
            ticker,
            price,
            qty,
            status,
        )
        return BuyResult(ticker=ticker, amount_usd=amount_usd, price=price, qty=qty, dry_run=False, order_status=status)
