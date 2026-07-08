"""Backtesting harness for replaying historical data through trading agents.

Feeds historical events from a replay source into the matching engine in
timestamp order, routes fills to agents, and records performance metrics
over time.
"""

from dataclasses import dataclass, field
from typing import Any, Generator, Optional

import exchange_simulator as ex


@dataclass
class BacktestResult:
    """Results from a backtest run.

    Attributes
    ----------
    agent_pnl : dict[str, list[float]]
        Time series of PnL for each agent (keyed by agent name).
    agent_inventory : dict[str, list[int]]
        Time series of inventory for each agent.
    agent_fills : dict[str, int]
        Total fill count per agent.
    timestamps : list[int]
        Timestamps at which snapshots were taken (nanoseconds).
    total_events : int
        Total number of events processed from the replay source.
    total_fills : int
        Total number of fills across all agents.
    final_pnl : dict[str, float]
        Final PnL for each agent.
    final_inventory : dict[str, int]
        Final inventory for each agent.
    """
    agent_pnl: dict = field(default_factory=dict)
    agent_inventory: dict = field(default_factory=dict)
    agent_fills: dict = field(default_factory=dict)
    timestamps: list = field(default_factory=list)
    total_events: int = 0
    total_fills: int = 0
    final_pnl: dict = field(default_factory=dict)
    final_inventory: dict = field(default_factory=dict)


def run_backtest(
    replay_source: Generator,
    agents: list,
    max_events: Optional[int] = None,
    snapshot_interval: int = 100,
) -> BacktestResult:
    """Run a backtest using a replay source and a list of trading agents.

    Feeds historical events into the matching engine in timestamp order.
    After each historical event is submitted, each agent gets a chance to
    react via on_market_data(). Fills are routed to the relevant agents.

    Parameters
    ----------
    replay_source : Generator
        A generator that yields events. Each event must have at minimum:
        - timestamp_ns (int): event timestamp in nanoseconds
        - to_order() method or be an Order object directly
        For LobsterReplay.events() or DatabentoReplay.events(), use the
        events generator. For simple replay, use .generate() which yields
        Order objects directly.
    agents : list
        List of BaseAgent instances to participate in the backtest.
    max_events : int, optional
        Maximum number of events to process. None means process all.
    snapshot_interval : int
        Take a PnL/inventory snapshot every N events. Default 100.

    Returns
    -------
    BacktestResult
        Comprehensive results including time series and summary statistics.
    """
    engine = ex.MatchingEngine()
    result = BacktestResult()

    # Initialize tracking
    for agent in agents:
        result.agent_pnl[agent.name] = []
        result.agent_inventory[agent.name] = []
        result.agent_fills[agent.name] = 0

    # Map order_id -> agent for fill routing
    order_to_agent: dict[int, Any] = {}
    event_count = 0

    for event in replay_source:
        if max_events is not None and event_count >= max_events:
            break

        # Convert event to Order if it has to_order method
        if hasattr(event, "to_order"):
            order = event.to_order()
            if order is None:
                event_count += 1
                continue
            timestamp = event.timestamp_ns
        else:
            # Assume it is already an Order object
            order = event
            timestamp = order.timestamp

        # Submit historical order to engine
        fills = engine.submit(order)
        event_count += 1

        # Process fills from historical order
        _route_fills(fills, order_to_agent, agents, result)

        # Let each agent react to the new market state
        for agent in agents:
            agent_orders = agent.on_market_data(engine, timestamp)
            if agent_orders:
                for agent_order in agent_orders:
                    order_to_agent[agent_order.id] = agent
                    agent_fills = engine.submit(agent_order)
                    _route_fills(agent_fills, order_to_agent, agents, result)

        # Take periodic snapshots
        if event_count % snapshot_interval == 0:
            result.timestamps.append(timestamp)
            for agent in agents:
                result.agent_pnl[agent.name].append(agent.pnl)
                result.agent_inventory[agent.name].append(agent.inventory)

    # Record final state
    result.total_events = event_count
    for agent in agents:
        result.final_pnl[agent.name] = agent.pnl
        result.final_inventory[agent.name] = agent.inventory

    # Take final snapshot if not already captured
    if event_count % snapshot_interval != 0:
        last_ts = result.timestamps[-1] if result.timestamps else 0
        result.timestamps.append(last_ts)
        for agent in agents:
            result.agent_pnl[agent.name].append(agent.pnl)
            result.agent_inventory[agent.name].append(agent.inventory)

    return result


def _route_fills(
    fills: list,
    order_to_agent: dict,
    agents: list,
    result: BacktestResult,
) -> None:
    """Route fills to the relevant agents and update statistics."""
    for fill in fills:
        result.total_fills += 1

        # Route to taker agent
        taker_agent = order_to_agent.get(fill.taker_order_id)
        if taker_agent is not None:
            taker_agent.on_fill(fill)
            result.agent_fills[taker_agent.name] += 1

        # Route to maker agent
        maker_agent = order_to_agent.get(fill.maker_order_id)
        if maker_agent is not None:
            maker_agent.on_fill(fill)
            result.agent_fills[maker_agent.name] += 1
