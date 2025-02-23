from __future__ import annotations

import time
from collections import deque
from .config.order import Order

from .trading_client import TradingClient


class Prioritizer:
    """
    Prioritizer class to execute actions, while being mindful of exchange rate limits.
    """
    def __init__(self, rate_limit: int, trading_client: TradingClient) -> None:
        """
        Constructor.
        Args:
            rate_limit: int - rate limit enforced by exchange
            trading_client: TradingClient - trading client of the user
        """
        self._rate_limit = rate_limit
        self._trading_client = trading_client
        self._rate_limit_window: deque[float] = deque()

    async def subscribe(self) -> None:
        """
        Subscribes to the socket
        Returns: None

        """
        await self._trading_client.subscribe()

    def _update_rate_limit_window(self) -> None:
        """
        Updates the rate limit window when previous timestamps expire.
        Returns: None

        """
        current_time = time.time()
        while self._rate_limit_window and self._rate_limit_window[0] < current_time - 1:
            self._rate_limit_window.popleft()

    async def place_limit(
        self, ticker: str, volume: float, price: float, is_bid: bool
    ) -> None:
        """
        Places a limit order and tracks timestamp.
        Args:
            ticker: str - ticker symbol for the limit order being placed
            volume: float - volume for the limit order being placed
            price: float - price for the limit order being placed
            is_bid: bool - if limit order being placed is a bid or ask

        Returns: None

        """
        self._update_rate_limit_window()
        if len(self._rate_limit_window) >= self._rate_limit:
            '''print(
                f"Limit order with params {ticker}, {volume}, {price} rejected due to rate limit"
            )'''
            return
        self._rate_limit_window.append(time.time())
        await self._trading_client.place_limit(ticker, volume, price, is_bid)

    async def place_market(self, ticker: str, volume: float, is_bid: bool) -> None:
        """
        Places a market order and tracks timestamp.
        Args:
            ticker: str - ticker symbol for the market order being placed
            volume: float - volume for the market order being placed
            is_bid: bool - if market order being placed is a bid or ask

        Returns: None

        """
        self._update_rate_limit_window()
        if len(self._rate_limit_window) >= self._rate_limit:
            '''print(
                f"Market order with params {ticker}, {volume} rejected due to rate limit"
            )'''
            return
        self._rate_limit_window.append(time.time())
        await self._trading_client.place_market(ticker, volume, is_bid)

    async def remove_all(self) -> None:
        """
        Performs a remove all operation, removing all open orders from the exchange.

        Returns: None

        """
        self._update_rate_limit_window()
        if len(self._rate_limit_window) >= self._rate_limit:
            '''print("Remove all orders rejected due to rate limit")'''
            return
        self._rate_limit_window.append(time.time())
        await self._trading_client.remove_all()

    async def remove_single(self, order: Order) -> None:
        self._update_rate_limit_window()
        if len(self._rate_limit_window) >= self._rate_limit:
            '''print(f"Remove order:{order.id} reject due to rate limit")'''
            return
        self._rate_limit_window.append(time.time())
        await self._trading_client.remove_order(order)

