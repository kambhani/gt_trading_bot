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
        # need to only remove order if price changes
        positions = self.get_positions()
        wmid = self.wmid(ticker)
        #print(positions[ticker])
        if wmid:
            position = positions[ticker]['quantity']

            # Ensure position does not exceed bounds
            if position < 100:  # Can still buy
                volume_bid = 100 - position
                bid_price = wmid - (volume_bid / 200) * max(0.04, min(1.0, abs(position) / 100))  # Dynamic spread
                asyncio.create_task(
                    self._quoter.place_limit(ticker=ticker, volume=volume_bid, price=bid_price, is_bid=True))

            if position > -100:  # Can still sell
                volume_ask = 100 + position
                ask_price = wmid + (volume_ask / 200) * max(0.04, min(1.0, abs(position) / 100))  # Dynamic spread
                asyncio.create_task(
                    self._quoter.place_limit(ticker=ticker, volume=volume_ask, price=ask_price, is_bid=False))

    async def on_portfolio_update(self) -> None:
        #print("Portfolio update", self.get_pnl())
        pass
