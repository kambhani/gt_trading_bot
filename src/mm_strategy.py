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
        #await self._quoter.remove_all()
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
            #print(self._shared_state.portfolio.orders)
            order_list = self._shared_state.portfolio.orders.get(ticker, [])

            # Ensure position does not exceed bounds
            if position < 100:  # Can still buy
                volume_bid = (100 - position)
                bid_price = wmid - (volume_bid / 200) * abs(position) / 100  # Dynamic spread
                prev_order = next((obj for obj in order_list if obj.side == "BID"), None)

                if prev_order is not None and round(prev_order.price, 0) != round(bid_price, 0):
                    # Price changed, we need to remove previous order
                    await self._quoter.remove_single(prev_order)
                    prev_order = None
                if prev_order is None and volume_bid > 0:
                    asyncio.create_task(
                        self._quoter.place_limit(ticker=ticker, volume=volume_bid, price=bid_price, is_bid=True)
                    )
            if position > -100:  # Can still sell
                volume_ask = (100 + position)
                ask_price = wmid + (volume_ask / 200) * abs(position) / 100  # Dynamic spread
                prev_order = next((obj for obj in order_list if obj.side == "ASK"),
                                  None)

                if prev_order is not None and round(prev_order.price, 0) != round(ask_price, 0):
                    # Price changed, we need to remove previous order
                    await self._quoter.remove_single(prev_order)
                    prev_order = None
                if prev_order is None and volume_ask > 0:
                    asyncio.create_task(
                        self._quoter.place_limit(ticker=ticker, volume=volume_ask, price=ask_price, is_bid=False)
                    )
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
