from __future__ import annotations

from gt_trading_client import Prioritizer
from gt_trading_client import SharedState
from gt_trading_client import Strategy

import time
import asyncio


class MMStrategy(Strategy):
    def __init__(self, quoter: Prioritizer, shared_state: SharedState):
        super().__init__(quoter, shared_state)

    async def on_orderbook_update(self) -> None:
        print("Orderbook update", time.time())
        wmid = self.wmid('A')
        if wmid:
            await self._quoter.remove_all()
            asyncio.create_task(self._quoter.place_limit(ticker="A", volume=100, price=wmid - 0.5, is_bid=True))
            asyncio.create_task(self._quoter.place_limit(ticker="A", volume=100, price=wmid + 0.5, is_bid=False))
    async def on_portfolio_update(self) -> None:
        #print("Portfolio update", self.get_pnl())
        pass
