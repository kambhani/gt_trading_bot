from __future__ import annotations

import aiohttp
import asyncio
import contextlib
import copy
import json
import time
import traceback
import urllib.request
from abc import ABC
from abc import abstractmethod
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any

import nest_asyncio
import websockets
from sortedcontainers import SortedDict



class OrderSide(str, Enum):
    BID = "BID"
    ASK = "ASK"


# Used to represent orders returned from portfolio
@dataclass
class Order:
    """
    Order object to represent order data returned from portfolio.
    Attributes:
        ticker: str - represents ticker of the order
        price: float - represents price of order
        volume: float - represents volume of order
        side: OrderSide - represents side of order (bid/ask)
        id: int - represents order ID tracked by exchange
    """
    ticker: str
    price: float
    volume: float
    side: OrderSide
    id: int


class PlacableOrder(ABC):
    @abstractmethod
    def atomic_params(self) -> dict[str, Any]:
        pass


# Used to represent limit order to be placed
@dataclass
class LimitOrder(PlacableOrder):
    ticker: str
    price: float
    volume: float
    is_bid: bool

    def atomic_params(self) -> dict[str, Any]:
        form_data = {
            "type": "limit_order",
            "ticker": self.ticker,
            "price": self.price,
            "volume": self.volume,
            "bid": self.is_bid,
        }
        return form_data


# Used to represent market order to be placed
@dataclass
class MarketOrder(PlacableOrder):
    ticker: str
    volume: float
    is_bid: bool

    def atomic_params(self) -> dict[str, Any]:
        form_data = {
            "type": "market_order",
            "ticker": self.ticker,
            "volume": self.volume,
            "bid": self.is_bid,
        }
        return form_data


# Used to represent single order removal
@dataclass
class RemoveOrder(PlacableOrder):
    id: int

    def atomic_params(self) -> dict[str, Any]:
        form_data = {
            "type": "remove",
            "orderID": self.id,
        }
        return form_data


# Used to represent remove all
@dataclass
class RemoveAll(PlacableOrder):

    def atomic_params(self) -> dict[str, Any]:
        form_data = {
            "type": "remove_all",
        }
        return form_data
        
class UserPortfolio:
    """
    UserPortfolio Class to keep track of user's holdings, balance, pnl, and orders.
    """
    def __init__(self) -> None:
        """
        Constructor. Instantiates a clean slate portfolio.
        """
        self._balance: float = 0
        self._pnl: float = 0
        self._positions: dict[str, dict[str, float]] = {}
        self._username = None
        self._orders: dict[str, list[Order]] = {}

    def update_portfolio(self, message: dict[str, Any]) -> None:
        """
        Updates portfolio with information.
        Args:
            message: dict[str, Any] - contains balance, pnl, positions, username, orders as keys; updates state of the portfolio

        Returns: None

        """
        if not isinstance(message, dict):
            print("Invalid message format:", message)
            return

        self._balance = float(message.get("balance", 0))
        self._pnl = float(message.get("pnl", 0))
        self._positions = message.get("positions", {})
        self._username = message.get("username")
        self._orders = {}

        orders = message.get("Orders")
        if isinstance(orders, dict):
            for ticker, order_list_per_ticker in orders.items():
                self._orders[ticker] = []
                for order in order_list_per_ticker:
                    order_with_ticker = Order(
                        ticker=ticker,
                        volume=order["volume"],
                        price=order["price"],
                        side=order["side"],
                        id=order["orderId"],
                    )
                    self._orders[ticker].append(order_with_ticker)

    def add_order(self, order: Order) -> None:
        """
        Appends an order to the portfolio.
        Args:
            order:

        Returns: None

        """
        if order.ticker not in self._orders:
            self._orders[order.ticker] = []
        self._orders[order.ticker].append(order)

    def add_position(self, ticker: str, position_delta: float, price: float) -> None:
        """
        Adds a position to the user's portfolio.
        Args:
            ticker: str - desired ticker to add position for
            position_delta: float - difference in position
            price: float - price at which the position delta was acquired

        Returns: None

        """
        if ticker not in self._positions:
            self._positions[ticker] = {"quantity": 0, "averagePrice": 0}
        self._positions[ticker]["averagePrice"] *= self._positions[ticker]["quantity"]
        self._positions[ticker]["averagePrice"] += position_delta * price
        self._positions[ticker]["quantity"] += position_delta
        if self._positions[ticker]["quantity"] == 0:
            self._positions[ticker]["averagePrice"] = 0
        else:
            self._positions[ticker]["averagePrice"] /= self._positions[ticker]["quantity"]

    def clear_orders(self) -> None:
        """
        Clears all orders from portfolio
        Returns: None

        """
        self._orders = {}

    @property
    def positions(self) -> dict[str, float]:
        """
        Getter method for positions.
        Returns: dict[str, float] - positions

        """
        return self._positions

    @property
    def orders(self) -> dict[str, list[Order]]:
        """
        Getter method for orders.
        Returns: dict[str, list[Order]] - orders

        """
        return self._orders

    @property
    def balance(self) -> float:
        """
        Getter method for balance.
        Returns: float - balance

        """
        return self._balance

    @property
    def pnl(self) -> float:
        """
        Getter method for pnl.
        Returns: float - pnl

        """
        return self._pnl
        
        
class OrderBook:
    """
    OrderBook class for representing orders in orderbook.
    """
    def __init__(
        self, raw_order_book: dict[str, dict[str, dict[str, str]]] | None = None
    ):
        """
        Constructor. Initializes OrderBook state with raw order book.

        Creates orderbook representation:
            orderbook = {
                ticker1: {
                    "bids": SortedDict({price1: volume1, price2: volume2,...}, reverse=True),
                    "asks": SortedDict({{price1: volume1, price2: volume2,...}})
                },
                ticker2: {
                    "bids": SortedDict({price1: volume1, price2: volume2,...}, reverse=True),
                    "asks": SortedDict({{price1: volume1, price2: volume2,...}})
                },
                ...
            }

        Args:
            raw_order_book: dict[str, dict[str, dict[str, str]]] - representation of a raw orderbook;
                - layer1 (orderbook): maps tickers [str] to volumes [dict]
                - layer2 (volumes): maps bidVolumes or askVolumes to prices/volumes
        """
        if raw_order_book is None:
            raw_order_book = {}
        if not isinstance(raw_order_book, dict):
            raise TypeError("Input data must be a dictionary.")

        self._orderbooks: dict[str, dict[str, SortedDict[float, float]]] = {}
        for ticker, volumes in raw_order_book.items():
            self._orderbooks[ticker] = {
                "bids": self._create_sorted_dict(
                    volumes.get("bidVolumes", {}), reverse=True
                ),
                "asks": self._create_sorted_dict(
                    volumes.get("askVolumes", {}), reverse=False
                ),
            }

    @property
    def orderbooks(self) -> dict[str, dict[str, SortedDict[float, float]]]:
        """
        Gets internal orderbook representation

        Returns: dict[str, dict[str, SortedDict[float, float]]] - internal orderbook representation

        """
        return self._orderbooks

    @property
    def raw_orderbooks(self) -> dict[str, dict[str, SortedDict[float, float]]]:
        """
        Gets internal orderbook representation

        Returns: dict[str, dict[str, SortedDict[float, float]]] - internal orderbook representation

        """
        return self._orderbooks

    def best_bid(self, ticker: str) -> tuple[float, float] | None:
        """
        Returns the best bid for the specified ticker in the orderbook. Returns None if there is no bid.
        Args:
            ticker: str - ticker for which the best bid is desired

        Returns: tuple[float, float] | None - tuple of price and volume of best bid

        """
        if self._orderbooks[ticker]["bids"]:
            return self._orderbooks[ticker]["bids"].peekitem(index=0)
        return None

    def best_ask(self, ticker: str) -> tuple[float, float] | None:
        """
        Returns the best ask for the specified ticker in the orderbook. Returns None if there is no ask.
        Args:
            ticker: str - ticker for which the bets ask is desired

        Returns: tuple[float, float] | None - tuple of price and volume of best ask

        """
        if self._orderbooks[ticker]["asks"]:
            return self._orderbooks[ticker]["asks"].peekitem(index=0)
        return None

    def mid(self, ticker: str) -> float | None:
        """
        Returns average of best bid and best ask for specified ticker. None if there are 0 bids or 0 asks.
        Args:
            ticker: str - ticker for which mid-price is desired

        Returns: float | None - average of best bid and best ask for specified ticker

        """
        best_bid = self.best_bid(ticker=ticker)
        best_ask = self.best_ask(ticker=ticker)
        if best_bid is None or best_ask is None:
            return None
        return (best_bid[0] + best_ask[0]) / 2

    def wmid(self, ticker: str) -> float | None:
        """
        Returns weighted mid-price of specified ticker. None if there are 0 bids or 0 asks.
        Args:
            ticker: str - ticker for which weighted mid-price is desired.

        Returns: float | None - mid-price of specified ticker

        """
        best_bid = self.best_bid(ticker=ticker)
        best_ask = self.best_ask(ticker=ticker)
        if best_bid is None or best_ask is None:
            return None
        return (best_bid[0] * best_ask[1] + best_ask[0] * best_bid[1]) / (
            best_bid[1] + best_ask[1]
        )

    def spread(self, ticker: str) -> float | None:
        """
        Returns spread of specified ticker. None if there are 0 bids or 0 asks.
        Args:
            ticker: str - ticker for which spread is desired

        Returns: float | None - spread of desired ticker

        """
        best_bid = self.best_bid(ticker=ticker)
        best_ask = self.best_ask(ticker=ticker)
        if best_bid is None or best_ask is None:
            return None
        return best_ask[0] - best_bid[0]

    def _create_sorted_dict(
        self, volumes: dict[str, str], reverse: bool
    ) -> SortedDict[float, float]:
        """
        Helper method for creating a sorted dictionary, given dictionary.

        Args:
            volumes: dict - dictionary representing raw volumes
            reverse: bool - indicates if SortedDict should be in reverse order

        Returns: SortedDict - sorted dictionary representation of dict

        """
        if reverse:
            return SortedDict(
                lambda x: -x,
                [(float(price), float(qty)) for price, qty in volumes.items()],
            )
        else:
            return SortedDict(
                [(float(price), float(qty)) for price, qty in volumes.items()]
            )

    def update_volumes(
        self, updates: list[dict[str, str]], orders: dict[str, list[Order]]
    ) -> None:
        """
        Updates the orderbook with new data.
        Args:
            updates: list[dict[str, str]] - data structure representing updates made to orderbook
            orders: dict[str, list[Order]]

        Returns: None

        """
        if not isinstance(updates, list):
            raise TypeError("Updates must be provided as a list.")

        for update in updates:
            if (
                not isinstance(update, dict)
                or "ticker" not in update
                or "price" not in update
                or "side" not in update
                or "volume" not in update
            ):
                raise ValueError(
                    "Each update must be a dictionary with keys 'ticker', 'price', 'side', and 'volume'."
                )

            ticker = update["ticker"]
            price = float(update["price"])
            side = update["side"].upper()
            volume = float(update["volume"])

            if ticker not in self._orderbooks:
                self._orderbooks[ticker] = {
                    "bids": self._create_sorted_dict({}, reverse=True),
                    "asks": self._create_sorted_dict({}, reverse=False),
                }

            if side == "BID":
                if volume == 0.0:
                    self._orderbooks[ticker]["bids"].pop(price, None)
                else:
                    self._orderbooks[ticker]["bids"][price] = volume
            elif side == "ASK":
                if volume == 0.0:
                    self._orderbooks[ticker]["asks"].pop(price, None)
                else:
                    self._orderbooks[ticker]["asks"][price] = volume
            else:
                raise ValueError("Side must be 'BID' or 'ASK'.")

    def __repr__(self) -> str:
        """
        Overrides __repr__ magic method.

        Returns: str - object's string representation

        """
        return f"OrderBook({self._orderbooks})"

    def __str__(self) -> str:
        """
        Overrides __str__ magic method.

        Returns: str - object's string representation

        """
        output = []
        for ticker, data in self._orderbooks.items():
            output.append(f"Ticker: {ticker}")
            output.append("  Bid Volumes:")
            for price, volume in data["bids"].items():
                output.append(f"    {price:.2f}: {volume:.2f}")
            output.append("  Ask Volumes:")
            for price, volume in data["asks"].items():
                output.append(f"    {price:.2f}: {volume:.2f}")
        return "\n".join(output)


class FilteredOrderBook(OrderBook):
    """
    FilteredOrderBook class for representing a filtered orderbook without any of the user's open orders.
    """
    def __init__(
        self, raw_order_book: dict[str, dict[str, dict[str, str]]] | None = None
    ) -> None:
        self._orderbook = OrderBook(raw_order_book=raw_order_book)
        self._orderbooks = self._orderbook.orderbooks

    @property
    def orderbooks(self) -> dict[str, dict[str, SortedDict[float, float]]]:
        return self._orderbooks

    @property
    def raw_orderbooks(self) -> dict[str, dict[str, SortedDict[float, float]]]:
        return self._orderbook.orderbooks

    def update_volumes(
        self, updates: list[dict[str, str]], orders: dict[str, list[Order]]
    ) -> None:
        """
        Updates the orderbook with new data, filtering out all current open orders.
        Args:
            updates: list[dict[str, str]] - data structure representing updates made to orderbook
            orders: dict[str, list[Order]] - open orders of client to filter out of orderbook

        Returns: None

        """
        self._orderbook.update_volumes(updates=updates, orders=orders)
        self._orderbooks = copy.deepcopy(self._orderbook.orderbooks)
        for order_list_per_ticker in orders.values():
            for order in order_list_per_ticker:
                if order.ticker in self._orderbooks:
                    if order.side == OrderSide.BID:
                        if order.price not in self._orderbooks[order.ticker]["bids"]:
                            continue
                        self._orderbooks[order.ticker]["bids"][
                            order.price
                        ] -= order.volume
                        if self._orderbooks[order.ticker]["bids"][order.price] == 0:
                            self._orderbooks[order.ticker]["bids"].pop(
                                order.price, None
                            )
                    else:
                        if order.price not in self._orderbooks[order.ticker]["asks"]:
                            continue
                        self._orderbooks[order.ticker]["asks"][
                            order.price
                        ] -= order.volume
                        if self._orderbooks[order.ticker]["asks"][order.price] == 0:
                            self._orderbooks[order.ticker]["asks"].pop(
                                order.price, None
                            )

    def __repr__(self) -> str:
        return f"FilteredOrderBook({self._orderbooks})"

    def __str__(self) -> str:
        return super().__str__()



class SharedState:
    """
    Shared state object to share orderbook, portfolio data across modules.
    """
    def __init__(self, orderbook: OrderBook, portfolio: UserPortfolio):
        """
        Constructor.
        Args:
            orderbook: OrderBook - reference to OrderBook object
            portfolio: UserPortfolio - reference to UserPortfolio object
        """
        self._orderbook = orderbook
        self._portfolio = portfolio

    @property
    def orderbook(self) -> OrderBook:
        """
        Getter method for orderbook
        Returns: OrderBook

        """
        return self._orderbook

    @property
    def portfolio(self) -> UserPortfolio:
        """
        Getter method for portfolio
        Returns: UserPortfolio

        """
        return self._portfolio


class Strategy(ABC):
    """
    Strategy Abstract Base Class. This class defines what constitutes a strategy.
    Has 2 abstract methods, implementations for which need to be provided:
        on_orderbook_update()
        on_portfolio_update()
    """

    def __init__(self, quoter: Prioritizer, shared_state: SharedState):
        """
        Constructor. Each strategy contains a quoter and a shared state.
        Args:
            quoter: Prioritizer - prioritizer object used for enforcing rate limits
            shared_state: SharedState - object used to represent global orderbook and user portfolio
        """
        self._quoter = quoter
        self._shared_state = shared_state

    # -------- USER PORTFOLIO METHODS --------
    def get_positions(self) -> dict[str, float]:
        """
        Getter method for positions.
        Returns: dict[str, float] - positions; dictionary with tickers as keys and volume held (position) as values

        """
        return self._shared_state.portfolio.positions

    def get_orders(self) -> dict[str, list[Order]]:
        """
        Getter method for open orders.
        Returns: dict[str, list[Order]] - orders represented as a dict with tickers as keys and Order objects as values

        """
        return self._shared_state.portfolio.orders

    def get_balance(self) -> float:
        """
        Getter method for balance.
        Returns: float - current user balance

        """
        return self._shared_state.portfolio.balance

    def get_pnl(self) -> float:
        """
        Getter method for PnL.
        Returns: float - current user PnL

        """
        return self._shared_state.portfolio.pnl

    # -------- ORDERBOOK METHODS --------
    def get_orderbooks(self) -> dict[str, dict[str, SortedDict[float, float]]]:
        """
        Gets internal orderbook representation.
        ```
        orderbook = {
            ticker1: {
                "bids": sortedcontainers.SortedDict({price1: volume1, price2: volume2,...}, reverse=True),
                "asks": sortedcontainers.SortedDict({{price1: volume1, price2: volume2,...}})
            },
            ticker2: {
                "bids": sortedcontainers.SortedDict({price1: volume1, price2: volume2,...}, reverse=True),
                "asks": sortedcontainers.SortedDict({{price1: volume1, price2: volume2,...}})
            },
            ...
        }
        ```

        Returns: dict[str, dict[str, SortedDict[float, float]]] - internal orderbook representation

        """
        return self._shared_state.orderbook.raw_orderbooks

    def get_orderbook_str(self) -> str:
        """
        Returns a string representation for orderbook (for printing purposes).

        Returns: str - string representation of orderbook

        """
        return str(self._shared_state.orderbook)

    def best_bid(self, ticker: str) -> tuple[float, float] | None:
        """
        Returns the best bid for the specified ticker in the orderbook. Returns None if there is no bid.
        Args:
            ticker: str - ticker for which the best bid is desired

        Returns: tuple[float, float] | None - tuple of price and volume of best bid

        """
        return self._shared_state.orderbook.best_bid(ticker=ticker)

    def best_ask(self, ticker: str) -> tuple[float, float] | None:
        """
        Returns the best ask for the specified ticker in the orderbook. Returns None if there is no ask.
        Args:
            ticker: str - ticker for which the bets ask is desired

        Returns: tuple[float, float] | None - tuple of price and volume of best ask

        """
        return self._shared_state.orderbook.best_ask(ticker=ticker)

    def mid(self, ticker: str) -> float | None:
        """
        Returns average of best bid and best ask for specified ticker. None if there are 0 bids or 0 asks.
        Args:
            ticker: str - ticker for which mid-price is desired

        Returns: float | None - average of best bid and best ask for specified ticker

        """
        return self._shared_state.orderbook.mid(ticker=ticker)

    def wmid(self, ticker: str) -> float | None:
        """
        Returns weighted mid-price of specified ticker. None if there are 0 bids or 0 asks.
        Args:
            ticker: str - ticker for which weighted mid-price is desired.

        Returns: float | None - mid-price of specified ticker

        """
        return self._shared_state.orderbook.wmid(ticker=ticker)

    def spread(self, ticker: str) -> float | None:
        """
        Returns spread of specified ticker. None if there are 0 bids or 0 asks.
        Args:
            ticker: str - ticker for which spread is desired

        Returns: float | None - spread of desired ticker

        """
        return self._shared_state.orderbook.spread(ticker=ticker)

    async def start(self) -> None:
        await self._quoter.subscribe()

    # -------- ABSTRACT METHODS --------
    @abstractmethod
    async def on_orderbook_update(self) -> None:
        pass

    @abstractmethod
    async def on_portfolio_update(self) -> None:
        pass


class WebSocketClient:
    """
    WebSocketClient to connect to websocket and receive live stream of market data.
    """

    def __init__(
        self,
        endpoint: str,
        orderbook: OrderBook,
        session_token: str,
        portfolio: UserPortfolio,
        username: str,
    ):
        """
        Constructor.
        Args:
            endpoint: str - link to endpoint
            orderbook: OrderBook - orderbook object
            session_token: str - session token of authenticated user
            portfolio: UserPortfolio - portfolio of user
            username: str - username of authenticated user
        """
        self._endpoint = f"{endpoint}?Session-ID={session_token}&Username={username}"
        self._subscribed: asyncio.Event | None = None
        self._ws = None
        self._orderbook = orderbook
        self._session_token = session_token
        self._portfolio = portfolio
        self._username = username
        self._strategy: Strategy | None = None

    def set_strategy(self, strategy: Strategy) -> None:
        """
        Setter method for strategy.
        Args:
            strategy: Strategy - user implemented trading strategy

        Returns: None

        """
        self._strategy = strategy

    async def _on_open(self, ws: websockets.ClientConnection) -> None:
        print("WebSocket connection established")
        # Send STOMP CONNECT frame
        connect_frame = (
            "CONNECT\n" "accept-version:1.1,1.0\n" "host:localhost\n" "\n\x00"
        )
        await ws.send(connect_frame)

        # Subscribe to orderbook topic
        subscribe_frame = (
            "SUBSCRIBE\n" "id:sub-0\n" "destination:/topic/orderbook\n" "\n\x00"
        )
        await ws.send(subscribe_frame)

        # Subscribe to private user queue
        user_subscribe_frame = (
            "SUBSCRIBE\n" "id:sub-1\n" "destination:/user/queue/private\n" "\n\x00"
        )
        await ws.send(user_subscribe_frame)
        assert self._subscribed is not None
        self._subscribed.set()
        print("STOMP connection and subscription established")

    async def _on_message(
        self, ws: websockets.ClientConnection, message: websockets.Data
    ) -> None:
        """
        Async method to process message from socket.
        Calls on_orderbook_update and on_portfolio_update methods of user strategy.
        Args:
            ws: ws.websockets.ClientConnection
            message: websockets.Data - data received from websocket

        Returns: None

        """
        try:
            if isinstance(message, bytes):
                message = message.decode("utf-8")

            if "\n\n" in message:
                headers, body = message.split("\n\n", 1)
                body = body.replace("\x00", "").strip()
                json_body = json.loads(body)

                destination = None
                for line in headers.split("\n"):
                    if line.startswith("destination:"):
                        destination = line.split(":", 1)[1].strip()
                        break

                if destination == "/topic/orderbook" and "content" in json_body:
                    content = json.loads(json_body["content"])
                    if isinstance(content, list):
                        self._orderbook.update_volumes(
                            updates=content, orders=self._portfolio.orders
                        )
                        if self._strategy:
                            await self._strategy.on_orderbook_update()

                elif destination == "/user/queue/private" and (
                    json_body and "balance" in json_body or "Orders" in json_body
                ):
                    self._portfolio.update_portfolio(json_body)
                    if self._strategy:
                        await self._strategy.on_portfolio_update()

        except Exception as e:
            print(f"Error processing message: {e}")
            traceback.print_exc()

    async def _on_error(
        self, ws: websockets.ClientConnection, error: Exception
    ) -> None:
        """
        Async method to handle error.
        Args:
            ws:
            error: Exception - exception thrown by the program.

        Returns: None

        """
        print(f"Error: {error}")

    async def _on_close(
        self, ws: websockets.ClientConnection, close_status_code: int, close_msg: str
    ) -> None:
        """
        Called to teardown the websocket connection.
        Args:
            ws:
            close_status_code:
            close_msg:

        Returns: None

        """
        print(f"Disconnected: {close_msg if close_msg else 'No message'}")
        self._connected = False

    async def _subscribe_ws(self) -> None:
        """
        Async method to subscribe to websocket.
        Returns: None

        """
        while True:
            try:
                async with websockets.connect(self._endpoint, max_queue=None) as ws:
                    await self._on_open(ws)
                    self._ws = ws
                    while True:
                        try:
                            message = await ws.recv()
                            await self._on_message(ws, message)
                        except websockets.ConnectionClosed as e:
                            await self._on_close(ws, e.code, e.reason)
                            break
            except Exception as e:
                await self._on_error(None, e)
                await asyncio.sleep(5)

    async def subscribe(self) -> None:
        """
        Subscribe method which subscribes to websocket and sets task.
        Returns: None

        """
        if self._subscribed:
            await self._subscribed.wait()
        self._subscribed = asyncio.Event()
        self._task = asyncio.create_task(self._subscribe_ws())
        await self._subscribed.wait()

    async def unsubscribe(self) -> None:
        """
        Unsubscribe method to cancel task and teardown socket connection.
        Returns: None

        """
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self._ws:
            await self._ws.close()
            self._ws = None
        self._subscribed = None
        
        
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
                print(content)
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
            print(
                f"Limit order with params {ticker}, {volume}, {price} rejected due to rate limit"
            )
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
            print(
                f"Market order with params {ticker}, {volume} rejected due to rate limit"
            )
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
            print("Remove all orders rejected due to rate limit")
            return
        self._rate_limit_window.append(time.time())
        await self._trading_client.remove_all()

