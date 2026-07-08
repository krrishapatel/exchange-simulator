"""Random agent that places limit orders near the midprice."""

import random

from .base import BaseAgent


class RandomAgent(BaseAgent):
    """Agent that randomly submits buy/sell limit orders near the midprice.

    Places orders within a configurable number of ticks from the
    current midprice, with random quantities between 1 and 10.
    """

    def __init__(self, agent_id: int, tick_range: int = 5, seed: int | None = None):
        """Initialize RandomAgent.

        Args:
            agent_id: Unique agent identifier.
            tick_range: Max distance in ticks from mid for order placement.
            seed: Optional random seed for reproducibility.
        """
        super().__init__(agent_id)
        self._tick_range = tick_range
        self._rng = random.Random(seed)

    @property
    def name(self) -> str:
        return f"Random-{self.agent_id}"

    def on_market_data(self, engine, timestamp: int) -> list:
        """Generate random orders near the midprice.

        Only places orders when the book has both a bid and an ask.
        Randomly chooses to buy or sell, picks a price within tick_range
        of the midprice, and a quantity between 1 and 10.
        """
        import exchange_simulator as ex

        book = engine.book()

        best_bid = book.best_bid_price()
        best_ask = book.best_ask_price()

        # Only trade when both sides of the book exist
        if best_bid is None or best_ask is None:
            # If book is empty, seed it with a wide spread
            orders = []
            base_price = 100_0000  # 100.0000 in fixed-point
            if best_bid is None:
                bid_price = base_price - self._rng.randint(1, self._tick_range) * 100
                qty = self._rng.randint(1, 10)
                orders.append(
                    self.make_order(
                        ex.Side.Buy, bid_price, qty,
                        ex.OrderType.Limit, ex.TimeInForce.GTC, timestamp
                    )
                )
            if best_ask is None:
                ask_price = base_price + self._rng.randint(1, self._tick_range) * 100
                qty = self._rng.randint(1, 10)
                orders.append(
                    self.make_order(
                        ex.Side.Sell, ask_price, qty,
                        ex.OrderType.Limit, ex.TimeInForce.GTC, timestamp
                    )
                )
            return orders

        mid = (best_bid + best_ask) // 2

        # Randomly choose side
        side = ex.Side.Buy if self._rng.random() < 0.5 else ex.Side.Sell

        # Price offset from mid (in ticks, where 1 tick = 100 in fixed-point)
        offset = self._rng.randint(0, self._tick_range) * 100

        if side == ex.Side.Buy:
            price = mid - offset
        else:
            price = mid + offset

        # Ensure price is positive
        price = max(price, 100)

        quantity = self._rng.randint(1, 10)

        order = self.make_order(
            side, price, quantity,
            ex.OrderType.Limit, ex.TimeInForce.GTC, timestamp
        )
        return [order]
