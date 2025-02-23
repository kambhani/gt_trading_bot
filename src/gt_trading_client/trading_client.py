from __future__ import annotations

import json
import urllib.request
from typing import Any

import aiohttp

from .config.order import Order
from .config.order import OrderSide
from .filtered_orderbook import FilteredOrderBook
from .raw_orderbook import OrderBook
from .shared_state import SharedState
from .strategy import Strategy
from .user_portfolio import UserPortfolio
from .websocket_client import WebSocketClient


class TradingClient:
    """
    Trading Client Class.
    """
    def __init__(
        self, http_endpoint: str, ws_endpoint: str, username: str, api_key: str
    ):
        """
        Constructor. Creates a new TradingClient with specified HTTP endpoint, websocket endpoint, username, and API key.
        Args:
            http_endpoint: str - contains an HTTP link to API endpoint
            ws_endpoint: str - contains a WS link to websocket endpoint
            username: str - username of the user
            api_key: str - API key, used for authentication
        """
        self._http_endpoint = http_endpoint
        self._ws_endpoint = ws_endpoint
        self._username = username
        self._api_key = api_key
        self._strategy = None

        self._user_buildup()

    def set_strategy(self, strategy: Strategy) -> None:
        """
        Setter for strategy. Sets the client's strategy to be the specified strategy.
        Args:
            strategy: Strategy - a concrete implementation of the Strategy class; will be run by client.

        Returns: None

        """
        self._client.set_strategy(strategy)

    def _user_buildup_params(self) -> tuple[str, dict[str, Any]]:
        """
        Private method used to format user parameters for buildup.
        Returns: tuple[str, dict[str, Any]] - formatted JSON data to send to buildup endpoint

        """
        url = self._http_endpoint + "/buildup"
        form_data = {"username": self._username, "apiKey": self._api_key}
        return (url, form_data)

    def _user_buildup(self) -> None:
        """
        User Buildup Method. Authenticate the user and obtain a session token.
        Creates 4 objects:
            1. orderbook: FilteredOrderBook - orderbook object used by trading client to keep track of exchange global orderbook
            2. user_portfolio: UserPortfolio - portfolio used by trading client to keep track of user portfolio
            3. client: WebSocketClient - websocket client used by trading client to read socket stream
            4. shared_state: SharedState - shared state used by trading client to store key global information
        Returns: None
        """
        url, form_data = self._user_buildup_params()
        req = urllib.request.Request(
            url=url,
            data=json.dumps(form_data).encode("utf-8"),
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        response = json.loads(urllib.request.urlopen(req).read().decode("utf-8"))
        self._session_token = response.get("sessionToken")
        self._orderbook: OrderBook = FilteredOrderBook(
            raw_order_book=json.loads(response["orderBookData"])
        )
        self._user_portfolio = UserPortfolio()
        self._client = WebSocketClient(
            endpoint=self._ws_endpoint,
            orderbook=self._orderbook,
            session_token=self._session_token,
            portfolio=self._user_portfolio,
            username=self._username,
        )
        self._shared_state = SharedState(
            orderbook=self._orderbook,
            portfolio=self._user_portfolio,
        )

    @property
    def shared_state(self) -> SharedState:
        """
        Getter method for shared state
        Returns: SharedState - shared state object used by system to containerize user portfolio and orderbook

        """
        return self._shared_state

    def _error_check(self, message: dict[str, Any]) -> bool:
        """
        Helper method to parse JSON response from exchange and check for erro
        Args:
            message: dict[str, Any] - message from JSON response of exchange

        Returns: bool - whether or not there is an error

        """
        if message["errorCode"] != 0:
            return False
        return True

    def _limit_params(
        self, ticker: str, volume: float, price: float, is_bid: bool
    ) -> tuple[str, dict[str, Any]]:
        """
        Helper method to format limit order API request.
        Args:
            ticker: str - ticker for limit order
            volume: float - volume for limit order
            price: float - price for limit order
            is_bid: bool - if limit order is bid or ask

        Returns: tuple[str, dict[str, Any]] - tuple containing request URL and JSON parameters

        """
        url = f"{self._http_endpoint}/limit_order"
        form_data = {
            "username": self._username,
            "sessionToken": self._session_token,
            "ticker": ticker,
            "volume": volume,
            "price": price,
            "isBid": is_bid,
        }
        return (url, form_data)

    async def place_limit(
        self, ticker: str, volume: float, price: float, is_bid: bool
    ) -> None:
        """
        Sends a limit order asynchronously using aiohttp.
        Args
            ticker: str - ticker for limit order
            volume: float - volume for limit order
            price: float - price for limit order
            is_bid: bool - if limit order is bid or ask

        Returns: None
        """
        if not self._session_token:
            raise Exception("User not authenticated. Call user_buildup first.")

        url, form_data = self._limit_params(
            ticker=ticker, volume=volume, price=price, is_bid=is_bid
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=form_data) as response:
                content = await response.json()
                #print(content)
                message = content["message"]
                if not self._error_check(message=message):
                    return
                volume_filled = message["volumeFilled"]
                volume_remaining = volume - volume_filled
                # Order_id
                order_id = message["orderId"]
                if volume_filled > 0:
                    self._user_portfolio.add_position(
                        ticker=ticker,
                        position_delta=volume_filled if is_bid else -volume_filled,
                    )
                if volume_remaining > 0:
                    self._user_portfolio.add_order(
                        order=Order(
                            ticker=ticker,
                            volume=volume_remaining,
                            price=price,
                            side=OrderSide.BID if is_bid else OrderSide.ASK,
                            id=order_id,
                        )
                    )

    def _market_params(
        self, ticker: str, volume: float, is_bid: bool
    ) -> tuple[str, dict[str, Any]]:
        """
        Helper method to format market order API request.
        Args:
            ticker: str - ticker for market order
            volume: float - volume for market order
            is_bid: bool - if market order is bid or ask

        Returns: tuple[str, dict[str, Any]] - tuple containing request URL and JSON parameters

        """
        url = f"{self._http_endpoint}/market_order"
        form_data = {
            "username": self._username,
            "sessionToken": self._session_token,
            "ticker": ticker,
            "volume": volume,
            "isBid": is_bid,
        }
        return (url, form_data)

    async def place_market(self, ticker: str, volume: float, is_bid: bool) -> None:
        """
        Place a market order asynchronously using aiohttp.
        Args:
            ticker: str - ticker for market order
            volume: float - volume for market order
            is_bid: bool - if market order is bid or ask

        Returns: None
        """
        if not self._session_token:
            raise Exception("User not authenticated. Call user_buildup first.")

        url, form_data = self._market_params(
            ticker=ticker, volume=volume, is_bid=is_bid
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=form_data) as response:
                content = await response.json()
                message = content["message"]

                if not self._error_check(message=message):
                    return

                volume_filled = message["volumeFilled"]
                price = message["price"]
                if volume_filled > 0:
                    self._user_portfolio.add_position(
                        ticker=ticker,
                        position_delta=volume_filled if is_bid else -volume_filled,
                        price=price,
                    )

     ### Cancel Single Order ###

    def _remove_order_params(self, order_id: int) -> tuple[str, dict[str, Any]]:
        """
        Helper method to format remove a single order API request.

        Returns: tuple[str, dict[str, Any]] - tuple containing request URL and JSON parameters
        """

        url = f"{self._http_endpoint}/remove"
        form_data = {
            "orderId": order_id,
            "username": self._username,
            "sessionToken": self._session_token
        }
        return (url, form_data)


    async def remove_order(self, order: Order) -> None:
        """
        Remove order based on id asynchronously using aiohttp

        Returns: None
        """
        if not self._session_token:
            raise Exception("User not authenticated. Call user_buildup first.")
        
        url, form_data = self._remove_order_params(order.id)

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=form_data) as response:
                content = await response.json()  # Parse JSON response asynchronously
                #print(content)
                message = content["message"]

                if not message or not self._error_check(message=message):
                    return
                
            self._user_portfolio.remove_single_order(order)

    ### End of Cancel Single Order ###


    def _remove_all_params(self) -> tuple[str, dict[str, Any]]:
        """
        Helper method to format remove all API request.

        Returns: tuple[str, dict[str, Any]] - tuple containing request URL and JSON parameters

        """
        url = f"{self._http_endpoint}/remove_all"
        form_data = {
            "username": self._username,
            "sessionToken": self._session_token,
        }
        return (url, form_data)

    async def remove_all(self) -> None:
        """
        Remove all open orders asynchronously using aiohttp.

        Returns: None
        """
        if not self._session_token:
            raise Exception("User not authenticated. Call user_buildup first.")

        url, form_data = self._remove_all_params()

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=form_data) as response:
                content = await response.json()  # Parse JSON response asynchronously
                #print(content)
                message = content["message"]

                if not message or not self._error_check(message=message):
                    return

                self._user_portfolio.clear_orders()

    async def subscribe(self) -> None:
        """
        Subscribes to websocket asynchronously.
        Returns: None

        """
        await self._client.subscribe()

    async def unsubscribe(self) -> None:
        """
        Unsubscribes from websocket asynchronously.
        Returns: None

        """
        await self._client.unsubscribe()
