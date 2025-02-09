from __future__ import annotations

from src.raw_orderbook import OrderBook
from src.config.order import Order


class FilteredOrderBook(OrderBook):
    def __init__(self, raw_order_book: dict | None = None):
        self._orderbook = OrderBook(raw_order_book=raw_order_book)
        self._orderbooks = self._orderbook.orderbooks

    @property
    def orderbooks(self) -> dict:
        return self._orderbooks

    def update_volumes(self, updates: list, orders: dict[str, list[Order]]) -> None:
        self._orderbook.update_volumes(updates=updates)
        for order_list_per_ticker in orders.values():
            for order in order_list_per_ticker:
                if order.ticker in self._orderbooks:
                    if order.side == "BUY":
                        self._orderbooks[order.ticker]["bids"][order.price] += order.volume
                    else:
                        self._orderbooks[order.ticker]["asks"][order.price] += order

    def __repr__(self):
        return f"FilteredOrderBook({self.order_books})"

    def __str__(self):
        return super().__str__()
