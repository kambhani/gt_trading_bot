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
        
        # If no price exsits return
        if not self.wmid(ticker):
            return

        # Need to only remove order if price changes
        position: int = self.get_positions()[ticker]['quantity']
        
        
        
        # Gets our order list
        order_list = self._shared_state.portfolio.orders.get(ticker, [])

        # Calculate the new bid and ask prices
        bid_price, ask_price = await self.calc_bid_ask(ticker)

        # Ensure position does not exceed bounds
        if position < 100:  # Can still buy
            volume_bid = (100 - position)
            #bid_price = wmid - (volume_bid / 200) * abs(position) / 100  # Dynamic spread
            present = False
            for order in order_list:
                if order.side == "BID" and round(order.price, 0) != round(bid_price, 0):
                    await self._quoter.remove_single(order)
                elif order.side == "BID" and round(order.price, 0) == round(bid_price, 0) and not present:
                    present = True
                elif order.side == "BID" and round(order.price, 0) == round(bid_price, 0) and present:
                    await self._quoter.remove_single(order)
            if volume_bid > 0 and not present:
                asyncio.create_task(
                    self._quoter.place_limit(ticker=ticker, volume=volume_bid, price=bid_price, is_bid=True)
                )
        if position > -100:  # Can still sell
            volume_ask = (100 + position)
            present = False
            for order in order_list:
                if order.side == "ASK" and round(order.price, 0) != round(ask_price, 0):
                    await self._quoter.remove_single(order)
                elif order.side == "ASK" and round(order.price, 0) == round(ask_price, 0) and not present:
                    present = True
                elif order.side == "ASK" and round(order.price, 0) == round(ask_price, 0) and present:
                    await self._quoter.remove_single(order)
            if volume_ask > 0 and not present:
                asyncio.create_task(
                    self._quoter.place_limit(ticker=ticker, volume=volume_ask, price=ask_price, is_bid=False)
                )


    async def calc_bid_ask(self, ticker: str):
        wmid = self.wmid(ticker=ticker)
        spread = self.spread(ticker=ticker)

        bid_volume = np.sum(self.get_orderbooks()[ticker]['bids'].values())
        ask_volume = np.sum(self.get_orderbooks()[ticker]['asks'].values())

        volatility = 0.2 # Placeholder for now

        bid_price = wmid - ((spread / 2) * (ask_volume / bid_volume)) - volatility
        ask_price = wmid + ((spread / 2) * (bid_volume / ask_volume)) + volatility


        return int(np.round(bid_price)), int(np.round(ask_price))

    async def on_portfolio_update(self) -> None:
        #print("Portfolio update", self.get_pnl())
        pass
