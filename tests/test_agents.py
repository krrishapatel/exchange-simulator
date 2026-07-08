"""Tests for the Python agent framework and simulation loop."""

import sys
import os

# Add the project root to the path so agents/ and simulation/ can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import exchange_simulator as ex
from agents import BaseAgent, RandomAgent
from simulation import SimulationLoop


class TestBaseAgent:
    """Tests for the BaseAgent abstract class."""

    def test_cannot_instantiate_directly(self):
        """BaseAgent is abstract and cannot be instantiated."""
        try:
            BaseAgent(1)
            assert False, "Should have raised TypeError"
        except TypeError:
            pass

    def test_make_order_creates_valid_order(self):
        """make_order produces properly configured Order objects."""
        agent = RandomAgent(agent_id=1, seed=42)
        order = agent.make_order(
            ex.Side.Buy, 100_0000, 5,
            ex.OrderType.Limit, ex.TimeInForce.GTC, timestamp=1000
        )
        assert order.side == ex.Side.Buy
        assert order.price == 100_0000
        assert order.quantity == 5
        assert order.type == ex.OrderType.Limit
        assert order.tif == ex.TimeInForce.GTC
        assert order.timestamp == 1000
        assert order.id > 0

    def test_order_ids_are_unique(self):
        """Each call to make_order produces a unique order ID."""
        agent = RandomAgent(agent_id=1, seed=42)
        ids = set()
        for _ in range(100):
            order = agent.make_order(
                ex.Side.Buy, 100_0000, 1,
                ex.OrderType.Limit, ex.TimeInForce.GTC
            )
            ids.add(order.id)
        assert len(ids) == 100


class TestRandomAgent:
    """Tests for the RandomAgent implementation."""

    def test_name(self):
        """RandomAgent reports its name correctly."""
        agent = RandomAgent(agent_id=7, seed=0)
        assert agent.name == "Random-7"

    def test_seeds_book_when_empty(self):
        """RandomAgent places orders even when the book is empty."""
        agent = RandomAgent(agent_id=1, seed=42)
        engine = ex.MatchingEngine()
        orders = agent.on_market_data(engine, timestamp=0)
        assert len(orders) > 0

    def test_places_orders_near_mid(self):
        """When book has both sides, orders are near midprice."""
        engine = ex.MatchingEngine()

        # Seed the book manually
        bid = ex.Order()
        bid.id = 99001
        bid.side = ex.Side.Buy
        bid.price = 100_0000
        bid.quantity = 10
        bid.type = ex.OrderType.Limit
        bid.tif = ex.TimeInForce.GTC
        bid.timestamp = 0
        bid.filled_quantity = 0
        bid.stop_price = 0
        bid.peg_offset = 0
        bid.visible_quantity = 0
        bid.hidden_quantity = 0
        engine.submit(bid)

        ask = ex.Order()
        ask.id = 99002
        ask.side = ex.Side.Sell
        ask.price = 101_0000
        ask.quantity = 10
        ask.type = ex.OrderType.Limit
        ask.tif = ex.TimeInForce.GTC
        ask.timestamp = 0
        ask.filled_quantity = 0
        ask.stop_price = 0
        ask.peg_offset = 0
        ask.visible_quantity = 0
        ask.hidden_quantity = 0
        engine.submit(ask)

        agent = RandomAgent(agent_id=2, seed=123)
        orders = agent.on_market_data(engine, timestamp=1000)
        assert len(orders) == 1

        order = orders[0]
        mid = (100_0000 + 101_0000) // 2
        # Order should be within tick_range (5) * 100 of mid
        assert abs(order.price - mid) <= 5 * 100


class TestSimulationLoop:
    """Tests for the SimulationLoop."""

    def test_runs_without_crashing(self):
        """1000 steps with 2 random agents completes without error."""
        agents = [
            RandomAgent(agent_id=1, seed=42),
            RandomAgent(agent_id=2, seed=123),
        ]
        sim = SimulationLoop(agents, num_steps=1000)
        results = sim.run()

        assert results["steps"] == 1000
        assert "pnl" in results
        assert "inventory" in results
        assert "fills" in results

    def test_produces_fills(self):
        """Random agents should produce at least some fills in 1000 steps."""
        agents = [
            RandomAgent(agent_id=1, seed=42),
            RandomAgent(agent_id=2, seed=123),
        ]
        sim = SimulationLoop(agents, num_steps=1000)
        results = sim.run()

        assert results["fills"] > 0, "Expected some fills but got zero"

    def test_pnl_tracking(self):
        """PnL values are tracked for each agent."""
        agents = [
            RandomAgent(agent_id=1, seed=42),
            RandomAgent(agent_id=2, seed=99),
        ]
        sim = SimulationLoop(agents, num_steps=500)
        results = sim.run()

        # Both agents should have PnL entries
        assert "Random-1" in results["pnl"]
        assert "Random-2" in results["pnl"]

    def test_multiple_agents(self):
        """Simulation works with 5 agents."""
        agents = [RandomAgent(agent_id=i, seed=i * 7) for i in range(5)]
        sim = SimulationLoop(agents, num_steps=200)
        results = sim.run()

        assert len(results["pnl"]) == 5
        assert results["fills"] > 0

    def test_inventory_changes(self):
        """Agents that trade should have non-zero inventory changes."""
        agents = [
            RandomAgent(agent_id=1, seed=42),
            RandomAgent(agent_id=2, seed=123),
        ]
        sim = SimulationLoop(agents, num_steps=1000)
        results = sim.run()

        # At least one agent should have non-zero inventory
        inventories = list(results["inventory"].values())
        assert any(inv != 0 for inv in inventories), (
            "Expected at least one agent to have non-zero inventory"
        )
