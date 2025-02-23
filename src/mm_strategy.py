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

        if position > 0:
            # We have a buy positon so we need to sell
            self.remove_risk(ticker, position=position)
            return
        if position < 0:
            # We have a sell postion so we need to buy
            self.remove_risk(ticker, position=position)
            return


        # Gets our order list
        order_list = self._shared_state.portfolio.orders.get(ticker, [])

        # Calculate the new bid and ask prices based of WMID
        bid_price, ask_price = await self.calc_bid_ask2(ticker)

        # Double check postion
        # if not (-100 <= position <= 100):
        #     return


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

    # We are long positoins and need to remove them
    async def remove_risk(self, ticker: str, position: int):
        # Remove all orders on ticker
        # for order in self._shared_state.portfolio.orders.get(ticker, []):
        #     await self._quoter.remove_single(order)


        while position != 0:
            position = self.get_positions()[ticker]['quantity']




    # WMID calc
    async def calc_bid_ask(self, ticker: str):
        wmid = self.wmid(ticker=ticker)
        spread = self.spread(ticker=ticker)

        bid_volume = np.sum(self.get_orderbooks()[ticker]['bids'].values())
        ask_volume = np.sum(self.get_orderbooks()[ticker]['asks'].values())

        volatility = 0.2 # Placeholder for now

        bid_price = wmid - ((spread / 2) * (ask_volume / bid_volume)) - volatility
        ask_price = wmid + ((spread / 2) * (bid_volume / ask_volume)) + volatility


        return int(np.round(bid_price)), int(np.round(ask_price))
    
    # Spread Calc
    async def calc_bid_ask2(self, ticker: str):
        best_bid = await self.best_bid(ticker)
        best_ask = await self.best_ask(ticker)
        if best_bid is None or best_ask is None:
            raise KeyError("No bid or ask")
        
        if best_ask[0] - best_bid[0] > 2:
            # return WMID calc
            return (1, 1000)
        
        return (best_ask[0] - 1, best_bid[0] + 1)

    async def on_portfolio_update(self) -> None:
        #print("Portfolio update", self.get_pnl())
        pass
