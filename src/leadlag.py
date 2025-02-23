from __future__ import annotations

from gt_trading_client import Prioritizer
from gt_trading_client import SharedState
from gt_trading_client import Strategy

import time
import asyncio


class LeadLagStrategy(Strategy):
    def __init__(self, quoter: Prioritizer, shared_state: SharedState):
        super().__init__(quoter, shared_state)
        self.prevWmid_b = -1
        self.BETickCyle = -1
        self.E_stats = [False, -1.0]

    async def on_orderbook_update(self) -> None:
        if self.BETickCyle == 300:
            # close out E position
            if self.E_stats[0]:
                asyncio.create_task(self._quoter.place_limit(ticker="E", volume=self.E_stats[1], price=self.wmid('E'), is_bid=True))
            else:
                asyncio.create_task(self._quoter.place_limit(ticker="E", volume=self.E_stats[1], price=self.wmid('E'), is_bid=False))
            self.BETickCyle = -1
        elif self.BETickCyle != -1:
            # add to tick cycle
            self.BETickCyle += 1
        if self.prevWmid_b > 0 and self.BETickCyle == -1:
            if self.prevWmid_b > 1.02 * self.wmid('B'):
                # buy E, sell later
                e_ask = self.best_ask(ticker='E')
                if e_ask is not None:
                    asyncio.create_task(self._quoter.place_limit(ticker="E", volume=e_ask[1], price=self.wmid('E'), is_bid=True))
                    self.BETickCyle = 0
                    self.E_stats[0] = False
                    self.E_stats[1] = e_ask[1]
            elif self.prevWmid_b < 0.98 * self.wmid('B'):
                # sell E, buy later
                e_bid = self.best_bid(ticker='E')
                if e_bid is not None:
                    asyncio.create_task(
                        self._quoter.place_limit(ticker="E", volume=e_bid[1], price=self.wmid('E'), is_bid=False))
                    self.BETickCyle = 0
                    self.E_stats[0] = True
                    self.E_stats[1] = e_bid[1]
    async def on_portfolio_update(self) -> None:
        #print("Portfolio update", self.get_pnl())
        pass
