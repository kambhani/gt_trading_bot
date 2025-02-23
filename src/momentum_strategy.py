from __future__ import annotations

from gt_trading_client import Prioritizer
from gt_trading_client import SharedState
from gt_trading_client import Strategy

import time
import asyncio
import asyncio
import time
import pandas as pd
from collections import deque


class MomentumStrategy(Strategy):
    def __init__(self, quoter: Prioritizer, shared_state: SharedState, lookback: int = 10):
        super().__init__(quoter, shared_state)
        self.lookback = lookback
        self.prices = deque(maxlen=lookback)  # Rolling price storage

    async def on_orderbook_update(self) -> None:
        for ticker in ['D']:
            order_list = self._shared_state.portfolio.orders.get(ticker, [])
            if len(order_list) == 0:
                await self.single_stock(ticker)

    async def single_stock(self, ticker: str):
        latest_price = self.wmid(ticker)  # Fetch latest price
        self.prices.append(latest_price)  # Store price in rolling window
        position: int = self.get_positions()[ticker]['quantity']
        qty = 25

        if len(self.prices) == self.lookback:
            rolling_mean = sum(self.prices) / self.lookback  # Compute rolling mean

            # Determine buy/sell signal
            if latest_price > rolling_mean and position == 0:
                asyncio.create_task(
                    self._quoter.place_limit(ticker=ticker, volume=min(self.best_ask(ticker)[1], qty),
                                             price=self.best_ask(ticker)[0], is_bid=True)
                )
                asyncio.create_task(
                    self._quoter.place_limit(ticker=ticker, volume=min(self.best_ask(ticker)[1], qty),
                                             price=self.best_ask(ticker)[0] + 1, is_bid=False)
                )
            elif latest_price < rolling_mean and position == 0:
                asyncio.create_task(
                    self._quoter.place_limit(ticker=ticker, volume=min(self.best_bid(ticker)[1], qty),
                                             price=self.best_bid(ticker)[0], is_bid=False)
                )
                asyncio.create_task(
                    self._quoter.place_limit(ticker=ticker, volume=min(self.best_bid(ticker)[1], qty),
                                             price=self.best_bid(ticker)[0] - 1, is_bid=True)
                )

    async def on_portfolio_update(self) -> None:
        pass