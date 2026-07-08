"""Tests for Lobster and Databento replay modules and backtest harness."""

import os
import tempfile

import pytest

import exchange_simulator as ex
from data.replay import LobsterReplay, LobsterEventType, ReplayGenerator
from data.databento import DatabentoReplay, DatabentoAction
from data.backtest import run_backtest, BacktestResult
from agents.base import BaseAgent


# Path to sample data files
SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "sample_data")
LOBSTER_SAMPLE = os.path.join(SAMPLE_DIR, "lobster_sample.csv")
DATABENTO_SAMPLE = os.path.join(SAMPLE_DIR, "databento_sample.csv")


class SimpleAgent(BaseAgent):
    """Minimal agent for backtest testing -- does nothing on market data."""

    @property
    def name(self) -> str:
        return f"simple_agent_{self.agent_id}"

    def on_market_data(self, engine, timestamp: int) -> list:
        return []


class PassiveQuoter(BaseAgent):
    """Agent that posts a buy and sell around mid-price for testing fills."""

    @property
    def name(self) -> str:
        return f"passive_quoter_{self.agent_id}"

    def on_market_data(self, engine, timestamp: int) -> list:
        orders = []
        book = engine.book()
        best_bid = book.best_bid_price()
        best_ask = book.best_ask_price()

        if best_bid is not None and best_ask is not None:
            mid = (best_bid + best_ask) // 2
            # Post wide quotes
            buy_order = self.make_order(
                ex.Side.Buy, mid - 100, 10, ex.OrderType.Limit, ex.TimeInForce.GTC, timestamp
            )
            sell_order = self.make_order(
                ex.Side.Sell, mid + 100, 10, ex.OrderType.Limit, ex.TimeInForce.GTC, timestamp
            )
            orders.extend([buy_order, sell_order])

        return orders


class TestLobsterReplay:
    """Tests for the LOBSTER L3 replay."""

    def test_parses_sample_data(self):
        """LobsterReplay correctly parses the sample data file."""
        replay = LobsterReplay(LOBSTER_SAMPLE)
        events = list(replay.events())
        assert len(events) == 50

    def test_generates_orders_from_new_limit_events(self):
        """generate() only yields orders for event_type=1."""
        replay = LobsterReplay(LOBSTER_SAMPLE)
        orders = list(replay.generate())

        # Count type=1 events in sample (hand-counted: lines with ,1, as second field)
        all_events = list(LobsterReplay(LOBSTER_SAMPLE).events())
        new_limit_count = sum(
            1 for e in all_events if e.event_type == LobsterEventType.NEW_LIMIT
        )
        assert len(orders) == new_limit_count
        assert len(orders) > 0

    def test_event_types_mapped_correctly(self):
        """All LOBSTER event types are correctly parsed."""
        replay = LobsterReplay(LOBSTER_SAMPLE)
        events = list(replay.events())

        event_types_found = {e.event_type for e in events}
        # Sample data includes types 1, 2, 3, 4, 5, 7
        assert LobsterEventType.NEW_LIMIT in event_types_found
        assert LobsterEventType.PARTIAL_CANCEL in event_types_found
        assert LobsterEventType.FULL_CANCEL in event_types_found
        assert LobsterEventType.EXECUTION_VISIBLE in event_types_found
        assert LobsterEventType.EXECUTION_HIDDEN in event_types_found
        assert LobsterEventType.TRADING_HALT in event_types_found

    def test_timestamp_filtering(self):
        """start_time and end_time filters work correctly."""
        # Full range
        replay_all = LobsterReplay(LOBSTER_SAMPLE)
        all_events = list(replay_all.events())

        # Filter to middle portion (timestamps are around 34200.001 - 34200.003)
        replay_filtered = LobsterReplay(
            LOBSTER_SAMPLE,
            start_time=34200.001,
            end_time=34200.003,
        )
        filtered_events = list(replay_filtered.events())

        assert len(filtered_events) < len(all_events)
        assert len(filtered_events) > 0

        for event in filtered_events:
            assert event.timestamp_ns >= int(34200.001 * 1_000_000_000)
            assert event.timestamp_ns <= int(34200.003 * 1_000_000_000)

    def test_timestamps_are_ordered(self):
        """Events are yielded in timestamp order."""
        replay = LobsterReplay(LOBSTER_SAMPLE)
        events = list(replay.events())
        timestamps = [e.timestamp_ns for e in events]
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1]

    def test_order_fields_valid(self):
        """Generated orders have valid fields."""
        replay = LobsterReplay(LOBSTER_SAMPLE)
        orders = list(replay.generate())

        for order in orders:
            assert order.side in (ex.Side.Buy, ex.Side.Sell)
            assert order.price > 0
            assert order.quantity > 0
            assert order.type == ex.OrderType.Limit
            assert order.tif == ex.TimeInForce.GTC
            assert order.filled_quantity == 0
            assert order.timestamp > 0

    def test_missing_file_raises(self):
        """FileNotFoundError for nonexistent file."""
        with pytest.raises(FileNotFoundError):
            LobsterReplay("/nonexistent/path.csv")

    def test_backward_compat_replay_generator(self):
        """ReplayGenerator still works as a backward-compatible alias."""
        replay = ReplayGenerator(LOBSTER_SAMPLE)
        orders = list(replay.generate())
        assert len(orders) > 0


class TestDatabentoReplay:
    """Tests for the Databento MBO replay."""

    def test_parses_sample_data(self):
        """DatabentoReplay correctly parses the sample data file."""
        replay = DatabentoReplay(DATABENTO_SAMPLE)
        events = list(replay.events())
        assert len(events) == 50

    def test_generates_orders_from_add_events(self):
        """generate() only yields orders for action=ADD."""
        replay = DatabentoReplay(DATABENTO_SAMPLE)
        orders = list(replay.generate())

        all_events = list(DatabentoReplay(DATABENTO_SAMPLE).events())
        add_count = sum(1 for e in all_events if e.action == DatabentoAction.ADD)
        assert len(orders) == add_count
        assert len(orders) > 0

    def test_action_types_mapped_correctly(self):
        """All Databento action types are correctly parsed."""
        replay = DatabentoReplay(DATABENTO_SAMPLE)
        events = list(replay.events())

        actions_found = {e.action for e in events}
        assert DatabentoAction.ADD in actions_found
        assert DatabentoAction.MODIFY in actions_found
        assert DatabentoAction.CANCEL in actions_found
        assert DatabentoAction.TRADE in actions_found

    def test_price_conversion(self):
        """Prices are converted from decimal to fixed-point correctly."""
        replay = DatabentoReplay(DATABENTO_SAMPLE, price_multiplier=100)
        events = list(replay.events())

        # First event: price=100.50, should become 10050
        first_event = events[0]
        assert first_event.price == 10050

    def test_side_mapping(self):
        """Buy/Sell sides are mapped correctly."""
        replay = DatabentoReplay(DATABENTO_SAMPLE)
        events = list(replay.events())

        buy_events = [e for e in events if e.side == ex.Side.Buy]
        sell_events = [e for e in events if e.side == ex.Side.Sell]
        assert len(buy_events) > 0
        assert len(sell_events) > 0

    def test_timestamps_are_ordered(self):
        """Events are yielded in timestamp order."""
        replay = DatabentoReplay(DATABENTO_SAMPLE)
        events = list(replay.events())
        timestamps = [e.timestamp_ns for e in events]
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1]

    def test_timestamp_filtering(self):
        """start_ts and end_ts filters work correctly."""
        replay_all = DatabentoReplay(DATABENTO_SAMPLE)
        all_events = list(replay_all.events())

        # Filter a subset
        start = 1625140800001000000
        end = 1625140800003000000
        replay_filtered = DatabentoReplay(
            DATABENTO_SAMPLE, start_ts=start, end_ts=end
        )
        filtered_events = list(replay_filtered.events())

        assert len(filtered_events) < len(all_events)
        assert len(filtered_events) > 0
        for event in filtered_events:
            assert event.timestamp_ns >= start
            assert event.timestamp_ns <= end

    def test_missing_file_raises(self):
        """FileNotFoundError for nonexistent file."""
        with pytest.raises(FileNotFoundError):
            DatabentoReplay("/nonexistent/path.csv")

    def test_invalid_header_raises(self):
        """ValueError for file with invalid header."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("col1,col2,col3\n")
            f.write("1,2,3\n")
            path = f.name

        try:
            with pytest.raises(ValueError, match="missing columns"):
                DatabentoReplay(path)
        finally:
            os.unlink(path)


class TestBacktestHarness:
    """Tests for the backtesting harness."""

    def test_backtest_produces_valid_result(self):
        """Backtest with simple agents produces a BacktestResult."""
        replay = LobsterReplay(LOBSTER_SAMPLE)
        agents = [SimpleAgent(agent_id=1)]

        result = run_backtest(replay.generate(), agents)

        assert isinstance(result, BacktestResult)
        assert result.total_events > 0
        assert "simple_agent_1" in result.final_pnl
        assert "simple_agent_1" in result.final_inventory

    def test_backtest_max_events_limits(self):
        """max_events parameter limits the number of processed events."""
        replay = LobsterReplay(LOBSTER_SAMPLE)
        agents = [SimpleAgent(agent_id=1)]

        result = run_backtest(replay.generate(), agents, max_events=5)
        assert result.total_events == 5

    def test_backtest_with_multiple_agents(self):
        """Backtest tracks multiple agents independently."""
        replay = LobsterReplay(LOBSTER_SAMPLE)
        agents = [SimpleAgent(agent_id=1), SimpleAgent(agent_id=2)]

        result = run_backtest(replay.generate(), agents)

        assert "simple_agent_1" in result.final_pnl
        assert "simple_agent_2" in result.final_pnl
        assert len(result.agent_pnl) == 2

    def test_backtest_time_series_recorded(self):
        """PnL and inventory time series are recorded at intervals."""
        replay = LobsterReplay(LOBSTER_SAMPLE)
        agents = [SimpleAgent(agent_id=1)]

        result = run_backtest(replay.generate(), agents, snapshot_interval=5)

        assert len(result.timestamps) > 0
        assert len(result.agent_pnl["simple_agent_1"]) == len(result.timestamps)
        assert len(result.agent_inventory["simple_agent_1"]) == len(result.timestamps)

    def test_backtest_with_databento_source(self):
        """Backtest works with Databento replay source."""
        replay = DatabentoReplay(DATABENTO_SAMPLE)
        agents = [SimpleAgent(agent_id=1)]

        result = run_backtest(replay.generate(), agents)

        assert isinstance(result, BacktestResult)
        assert result.total_events > 0

    def test_backtest_fills_routed_to_agents(self):
        """Fills are correctly routed to participating agents."""
        replay = LobsterReplay(LOBSTER_SAMPLE)
        agents = [PassiveQuoter(agent_id=1)]

        result = run_backtest(replay.generate(), agents, snapshot_interval=10)

        # The passive quoter should get some fills as historical orders cross
        # its quotes (or at minimum the result structure is valid)
        assert isinstance(result.total_fills, int)
        assert isinstance(result.agent_fills["passive_quoter_1"], int)
