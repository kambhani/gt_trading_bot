from __future__ import annotations
import numpy as np

from gt_trading_client import Prioritizer
from gt_trading_client import SharedState
from gt_trading_client import Strategy

import time
import asyncio

from collections import deque

class MMStrategy(Strategy):
    def __init__(self, quoter: Prioritizer, shared_state: SharedState):
        super().__init__(quoter, shared_state)

    async def on_orderbook_update(self) -> None:
        #print("Orderbook update", time.time())
        await self._quoter.remove_all()
        await self.market_make_stock("A")
        await self.market_make_stock("B")
        await self.market_make_stock("C")
        await self.market_make_stock("D")
        await self.market_make_stock("E")

    async def market_make_stock(self, ticker: str):
        pass

    async def calc_bid_ask(self, ticker: str):
        wmid = self.wmid(ticker=ticker)
        spread = self.spread(ticker=ticker)

        bid_volume = np.sum(self.get_orderbooks[ticker]['bids'][1])
        ask_volume = np.sum(self.get_orderbooks[ticker]['asks'][1])

        volatility = 0.2 # Placeholder for now

        bid_price = wmid - ((spread / 2) * (ask_volume / bid_volume)) - volatility
        ask_price = wmid + ((spread / 2) * (bid_volume / ask_volume)) + volatility


        return (int(np.round(bid_price)), int(np.round(ask_price)))

    async def on_portfolio_update(self) -> None:
        #print("Portfolio update", self.get_pnl())
        pass
