from __future__ import annotations

import pandas as pd

from src.prioritizer import Prioritizer
from src.shared_state import SharedState
from src.strategy import Strategy

SYMBOLS = ["A", "B", "C", "D", "E"]
VOLUME = 1e7


class DataChallengeStrategy(Strategy):
    def __init__(self, quoter: Prioritizer, shared_state: SharedState):
        super().__init__(quoter, shared_state)
        self._tick_cnt = 0
        self._test_data = pd.read_csv("trial_test_data.csv")

    def on_orderbook_update(self) -> None:
        tick = self._test_data.iloc[self._tick_cnt]
        self._quoter.remove_all()
        for symbol in SYMBOLS:
            self._quoter.place_limit(
                ticker=symbol,
                volume=VOLUME,
                price=tick[f"Stock{symbol}_Bid"],
                is_bid=True,
            )
            self._quoter.place_limit(
                ticker=symbol,
                volume=VOLUME,
                price=tick[f"Stock{symbol}_Ask"],
                is_bid=False,
            )
        self._tick_cnt += 1

    def on_portfolio_update(self) -> None:
        pass
