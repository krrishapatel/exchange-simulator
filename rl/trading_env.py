"""Gymnasium environment wrapping the exchange simulator matching engine."""

from __future__ import annotations

import random

import gymnasium as gym
import numpy as np
from gymnasium import spaces

import exchange_simulator as ex
from agents.random_agent import RandomAgent


class TradingEnv(gym.Env):
    """A Gymnasium environment for training RL trading agents.

    The agent interacts with a C++ matching engine populated by background
    noise traders (RandomAgents) that provide liquidity.

    Observation space (Box, float32, shape=(11,)):
        [0] mid_price (normalized)
        [1] spread (normalized)
        [2-4] bid_depth at levels 0,1,2 (normalized)
        [5-7] ask_depth at levels 0,1,2 (normalized)
        [8] agent_inventory (normalized)
        [9] agent_pnl (normalized)
        [10] imbalance (bid_qty - ask_qty) / (bid_qty + ask_qty)

    Action space (Discrete(5)):
        0: hold
        1: buy_limit_at_bid
        2: buy_market
        3: sell_limit_at_ask
        4: sell_market

    Reward:
        Realized PnL delta + inventory penalty (penalizes large positions).
    """

    metadata = {"render_modes": []}

    # Fixed-point price constants (1 unit = 0.0001 in real terms)
    _BASE_PRICE = 100_0000  # 100.0000

    def __init__(
        self,
        num_noise_traders: int = 5,
        episode_length: int = 1000,
        inventory_penalty: float = 0.001,
        order_quantity: int = 1,
        seed: int | None = None,
    ):
        """Initialize the trading environment.

        Args:
            num_noise_traders: Number of background RandomAgent noise traders.
            episode_length: Number of steps per episode.
            inventory_penalty: Per-step penalty multiplier on abs(inventory).
            order_quantity: Quantity for RL agent orders.
            seed: Optional random seed for reproducibility.
        """
        super().__init__()

        self.num_noise_traders = num_noise_traders
        self.episode_length = episode_length
        self.inventory_penalty = inventory_penalty
        self.order_quantity = order_quantity
        self._seed = seed

        # Observation: 11 floats
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(11,), dtype=np.float32
        )

        # Actions: hold, buy_limit_at_bid, buy_market, sell_limit_at_ask, sell_market
        self.action_space = spaces.Discrete(5)

        # Internal state (set during reset)
        self._engine: ex.MatchingEngine | None = None
        self._noise_traders: list[RandomAgent] = []
        self._step_count = 0
        self._agent_inventory = 0
        self._agent_pnl = 0.0
        self._prev_pnl = 0.0
        self._order_id_counter = 0
        self._my_order_ids: set[int] = set()
        self._order_to_agent: dict[int, RandomAgent] = {}
        self._rng = random.Random(seed)

    def _next_order_id(self) -> int:
        """Generate the next unique order ID for the RL agent."""
        self._order_id_counter += 1
        return self._order_id_counter

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict | None = None,
    ) -> tuple[np.ndarray, dict]:
        """Reset the environment to a fresh state.

        Creates a new matching engine, initializes noise traders, and seeds
        the order book with initial orders.

        Returns:
            Tuple of (observation, info).
        """
        super().reset(seed=seed)

        if seed is not None:
            self._rng = random.Random(seed)

        self._engine = ex.MatchingEngine()
        self._step_count = 0
        self._agent_inventory = 0
        self._agent_pnl = 0.0
        self._prev_pnl = 0.0
        self._order_id_counter = 900_000_000  # High range to avoid collisions
        self._my_order_ids = set()
        self._order_to_agent = {}

        # Create noise traders with unique seeds
        self._noise_traders = []
        for i in range(self.num_noise_traders):
            trader_seed = self._rng.randint(0, 2**31)
            trader = RandomAgent(agent_id=i + 1, tick_range=5, seed=trader_seed)
            self._noise_traders.append(trader)

        # Seed the book: run noise traders for a warmup period
        for warmup_step in range(50):
            timestamp = warmup_step * 1_000_000
            self._run_noise_traders(timestamp)

        obs = self._get_observation()
        info = self._get_info()
        return obs, info

    def step(
        self, action: int
    ) -> tuple[np.ndarray, float, bool, bool, dict]:
        """Execute one step in the environment.

        Args:
            action: Integer action from the action space.

        Returns:
            Tuple of (observation, reward, terminated, truncated, info).
        """
        assert self._engine is not None, "Must call reset() before step()"

        self._step_count += 1
        timestamp = (50 + self._step_count) * 1_000_000  # Continue after warmup

        # Execute the RL agent's action
        self._execute_action(action, timestamp)

        # Run noise traders for this step
        self._run_noise_traders(timestamp)

        # Calculate reward
        pnl_delta = self._agent_pnl - self._prev_pnl
        inv_penalty = self.inventory_penalty * abs(self._agent_inventory)
        reward = float(pnl_delta - inv_penalty)
        self._prev_pnl = self._agent_pnl

        # Check termination
        terminated = False
        truncated = self._step_count >= self.episode_length

        obs = self._get_observation()
        info = self._get_info()

        return obs, reward, terminated, truncated, info

    def _execute_action(self, action: int, timestamp: int) -> None:
        """Translate the discrete action into an order and submit it.

        Actions:
            0: hold (do nothing)
            1: buy limit at best bid
            2: buy market (cross the spread)
            3: sell limit at best ask
            4: sell market (cross the spread)
        """
        if action == 0:
            return

        book = self._engine.book()
        best_bid = book.best_bid_price()
        best_ask = book.best_ask_price()

        # Need a valid book to place orders
        if best_bid is None or best_ask is None:
            return

        order = ex.Order()
        order.id = self._next_order_id()
        order.quantity = self.order_quantity
        order.timestamp = timestamp
        order.filled_quantity = 0
        order.stop_price = 0
        order.peg_offset = 0
        order.visible_quantity = 0
        order.hidden_quantity = 0

        if action == 1:
            # Buy limit at bid
            order.side = ex.Side.Buy
            order.price = best_bid
            order.type = ex.OrderType.Limit
            order.tif = ex.TimeInForce.GTC
        elif action == 2:
            # Buy market (use IOC at ask price to cross)
            order.side = ex.Side.Buy
            order.price = best_ask
            order.type = ex.OrderType.Limit
            order.tif = ex.TimeInForce.IOC
        elif action == 3:
            # Sell limit at ask
            order.side = ex.Side.Sell
            order.price = best_ask
            order.type = ex.OrderType.Limit
            order.tif = ex.TimeInForce.GTC
        elif action == 4:
            # Sell market (use IOC at bid price to cross)
            order.side = ex.Side.Sell
            order.price = best_bid
            order.type = ex.OrderType.Limit
            order.tif = ex.TimeInForce.IOC
        else:
            return

        self._my_order_ids.add(order.id)
        fills = self._engine.submit(order)
        self._process_rl_agent_fills(fills)

    def _process_rl_agent_fills(self, fills: list) -> None:
        """Update RL agent inventory and PnL based on fills."""
        for fill in fills:
            is_taker = fill.taker_order_id in self._my_order_ids
            is_maker = fill.maker_order_id in self._my_order_ids

            if is_taker:
                if fill.aggressor_side.name == "Buy":
                    self._agent_inventory += fill.quantity
                    self._agent_pnl -= fill.price * fill.quantity
                else:
                    self._agent_inventory -= fill.quantity
                    self._agent_pnl += fill.price * fill.quantity

            if is_maker:
                if fill.aggressor_side.name == "Buy":
                    # Aggressor bought from us, we sold
                    self._agent_inventory -= fill.quantity
                    self._agent_pnl += fill.price * fill.quantity
                else:
                    # Aggressor sold to us, we bought
                    self._agent_inventory += fill.quantity
                    self._agent_pnl -= fill.price * fill.quantity

    def _run_noise_traders(self, timestamp: int) -> None:
        """Run all noise traders for one step and process their fills."""
        for trader in self._noise_traders:
            orders = trader.on_market_data(self._engine, timestamp)
            for order in orders:
                self._order_to_agent[order.id] = trader
                fills = self._engine.submit(order)
                for fill in fills:
                    # Route fills to noise traders
                    taker_agent = self._order_to_agent.get(fill.taker_order_id)
                    if taker_agent is not None:
                        taker_agent.on_fill(fill)
                    maker_agent = self._order_to_agent.get(fill.maker_order_id)
                    if maker_agent is not None:
                        maker_agent.on_fill(fill)
                    # Also check if RL agent is involved
                    self._process_rl_agent_fills([fill])

    def _get_observation(self) -> np.ndarray:
        """Construct the observation vector from current market state.

        Returns:
            numpy array of shape (11,) with float32 values.
        """
        book = self._engine.book()
        best_bid = book.best_bid_price()
        best_ask = book.best_ask_price()

        if best_bid is not None and best_ask is not None:
            mid_price = (best_bid + best_ask) / 2.0
            spread = best_ask - best_bid
        elif best_bid is not None:
            mid_price = float(best_bid)
            spread = 0.0
        elif best_ask is not None:
            mid_price = float(best_ask)
            spread = 0.0
        else:
            mid_price = float(self._BASE_PRICE)
            spread = 0.0

        # Normalize mid_price relative to base (centered around 0)
        norm_mid = (mid_price - self._BASE_PRICE) / self._BASE_PRICE
        # Normalize spread (typical spread is 100-500 in fixed point)
        norm_spread = spread / 1000.0

        # Depth: total quantity on each side (we don't have per-level access,
        # so we use total depth count as proxy, split into 3 "levels")
        total_bid_depth = book.bid_depth()
        total_ask_depth = book.ask_depth()

        # Simulate 3 levels by distributing total depth
        # Level 0 gets more, subsequent levels get progressively less
        bid_levels = self._distribute_depth(total_bid_depth, 3)
        ask_levels = self._distribute_depth(total_ask_depth, 3)

        # Normalize depths (typical depth is 0-50 orders)
        norm_bid_levels = [d / 50.0 for d in bid_levels]
        norm_ask_levels = [d / 50.0 for d in ask_levels]

        # Agent state
        norm_inventory = self._agent_inventory / 100.0  # Normalize by max expected
        norm_pnl = self._agent_pnl / 1_000_000.0  # Normalize PnL

        # Order imbalance
        total_depth = total_bid_depth + total_ask_depth
        if total_depth > 0:
            imbalance = (total_bid_depth - total_ask_depth) / total_depth
        else:
            imbalance = 0.0

        obs = np.array(
            [
                norm_mid,
                norm_spread,
                norm_bid_levels[0],
                norm_bid_levels[1],
                norm_bid_levels[2],
                norm_ask_levels[0],
                norm_ask_levels[1],
                norm_ask_levels[2],
                norm_inventory,
                norm_pnl,
                imbalance,
            ],
            dtype=np.float32,
        )
        return obs

    @staticmethod
    def _distribute_depth(total: int, levels: int) -> list[float]:
        """Distribute total depth count across simulated price levels.

        Uses a decreasing distribution: level 0 gets the most.
        """
        if total == 0:
            return [0.0] * levels
        # Weights: 3, 2, 1 for 3 levels
        weights = list(range(levels, 0, -1))
        weight_sum = sum(weights)
        return [total * w / weight_sum for w in weights]

    def _get_info(self) -> dict:
        """Return auxiliary info dictionary."""
        return {
            "inventory": self._agent_inventory,
            "pnl": self._agent_pnl,
            "step": self._step_count,
        }
