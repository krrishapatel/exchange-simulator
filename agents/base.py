"""Base agent interface for exchange simulator agents."""

from abc import ABC, abstractmethod


class BaseAgent(ABC):
    """Abstract base class for all trading agents.

    Each agent has an ID, tracks its PnL and inventory, and responds
    to market data by generating orders.
    """

    def __init__(self, agent_id: int):
        self.agent_id = agent_id
        self.pnl = 0.0
        self.inventory = 0
        self.fills: list = []
        self._order_id_counter = agent_id * 1_000_000  # namespace per agent
        self._my_order_ids: set = set()

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this agent."""
        ...

    @abstractmethod
    def on_market_data(self, engine, timestamp: int) -> list:
        """Called each simulation step with the current engine state.

        Args:
            engine: The MatchingEngine instance (read book state from here).
            timestamp: Current simulation timestamp (nanoseconds).

        Returns:
            List of Order objects to submit to the engine.
        """
        ...

    def on_fill(self, fill) -> None:
        """Called when a fill involves one of this agent's orders.

        Updates inventory and PnL tracking.

        Args:
            fill: A Fill object from the matching engine.
        """
        self.fills.append(fill)

        # Determine if we are the maker or taker
        is_taker = fill.taker_order_id in self._my_order_ids
        is_maker = fill.maker_order_id in self._my_order_ids

        if is_taker:
            # We are the aggressor
            if fill.aggressor_side.name == "Buy":
                self.inventory += fill.quantity
                self.pnl -= fill.price * fill.quantity
            else:
                self.inventory -= fill.quantity
                self.pnl += fill.price * fill.quantity

        if is_maker:
            # We are the passive side (opposite of aggressor)
            if fill.aggressor_side.name == "Buy":
                # Aggressor bought from us, so we sold
                self.inventory -= fill.quantity
                self.pnl += fill.price * fill.quantity
            else:
                # Aggressor sold to us, so we bought
                self.inventory += fill.quantity
                self.pnl -= fill.price * fill.quantity

    def make_order(self, side, price, quantity, order_type, tif, timestamp=0):
        """Helper to create an Order with auto-incrementing ID.

        Args:
            side: Side.Buy or Side.Sell
            price: Order price (fixed-point integer)
            quantity: Order quantity
            order_type: OrderType enum value
            tif: TimeInForce enum value
            timestamp: Order timestamp (default 0)

        Returns:
            A configured Order object.
        """
        import exchange_simulator as ex

        self._order_id_counter += 1
        order = ex.Order()
        order.id = self._order_id_counter
        order.side = side
        order.price = price
        order.quantity = quantity
        order.type = order_type
        order.tif = tif
        order.timestamp = timestamp
        order.filled_quantity = 0
        order.stop_price = 0
        order.peg_offset = 0
        order.visible_quantity = 0
        order.hidden_quantity = 0

        self._my_order_ids.add(order.id)
        return order
