from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuyResult:
    ticker: str
    amount_usd: float
    price: float | None
    qty: float | None
    dry_run: bool


class IBExecutor:
    def __init__(self, dry_run: bool = True) -> None:
        self._dry_run = dry_run

    async def connect(self) -> None:
        """Connect to IB Gateway.

        NOTE: Implementation to be added (AsyncIO).
        """
        return None

    async def buy_fractional_by_amount(self, ticker: str, amount_usd: float) -> BuyResult:
        """Buy a fractional amount by USD.

        NOTE: Implementation to be added.
        """
        return BuyResult(ticker=ticker, amount_usd=amount_usd, price=None, qty=None, dry_run=self._dry_run)
