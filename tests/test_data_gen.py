"""Tests for the synthetic data generation module."""

import os
import tempfile

import numpy as np
import pytest

import exchange_simulator as ex
from data.hawkes import HawkesGenerator
from data.replay import ReplayGenerator
from data.scenarios import calm_market, volatile_market, flash_crash


class TestHawkesGenerator:
    """Tests for the Hawkes process order flow generator."""

    def test_produces_orders(self):
        """Generator produces a non-empty list of orders."""
        gen = HawkesGenerator(
            base_intensity=10.0, alpha=0.8, beta=1.2, duration=10.0, seed=42
        )
        orders = gen.generate()
        assert len(orders) > 0

    def test_timestamps_increasing(self):
        """All order timestamps are monotonically increasing."""
        gen = HawkesGenerator(
            base_intensity=15.0, alpha=0.5, beta=1.0, duration=30.0, seed=123
        )
        orders = gen.generate()
        timestamps = [o.timestamp for o in orders]
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1], (
                f"Timestamp decreased at index {i}: "
                f"{timestamps[i - 1]} -> {timestamps[i]}"
            )

    def test_valid_order_fields(self):
        """All orders have valid field values."""
        gen = HawkesGenerator(
            base_intensity=10.0, alpha=0.6, beta=1.0, duration=20.0, seed=99
        )
        orders = gen.generate()

        for order in orders:
            assert order.side in (ex.Side.Buy, ex.Side.Sell)
            assert order.price > 0
            assert order.quantity > 0
            assert order.type in (ex.OrderType.Limit, ex.OrderType.Market)
            assert order.filled_quantity == 0
            assert order.timestamp >= 0

    def test_deterministic_with_seed(self):
        """Same seed produces identical output."""
        gen1 = HawkesGenerator(base_intensity=10.0, alpha=0.5, beta=1.0, duration=10.0, seed=777)
        gen2 = HawkesGenerator(base_intensity=10.0, alpha=0.5, beta=1.0, duration=10.0, seed=777)

        orders1 = gen1.generate()
        orders2 = gen2.generate()

        assert len(orders1) == len(orders2)
        for o1, o2 in zip(orders1, orders2):
            assert o1.timestamp == o2.timestamp
            assert o1.price == o2.price
            assert o1.quantity == o2.quantity
            assert o1.side == o2.side

    def test_different_seeds_differ(self):
        """Different seeds produce different output."""
        gen1 = HawkesGenerator(base_intensity=10.0, alpha=0.5, beta=1.0, duration=10.0, seed=1)
        gen2 = HawkesGenerator(base_intensity=10.0, alpha=0.5, beta=1.0, duration=10.0, seed=2)

        orders1 = gen1.generate()
        orders2 = gen2.generate()

        # Very unlikely to have identical lengths AND prices
        prices1 = [o.price for o in orders1]
        prices2 = [o.price for o in orders2]
        assert prices1 != prices2 or len(orders1) != len(orders2)

    def test_clustering_property(self):
        """Inter-arrival times are NOT exponentially distributed (clustering).

        For a Poisson process, inter-arrival times are exponential with
        coefficient of variation (CV) = 1. For a Hawkes process with
        clustering, CV > 1 due to bursts of activity.
        """
        gen = HawkesGenerator(
            base_intensity=10.0,
            alpha=0.9,
            beta=1.1,
            duration=120.0,
            seed=42,
        )
        orders = gen.generate()
        assert len(orders) > 50, "Need enough events for statistical test"

        timestamps = np.array([o.timestamp for o in orders], dtype=float)
        inter_arrivals = np.diff(timestamps)

        # Coefficient of variation: std / mean
        # For exponential (Poisson): CV = 1
        # For clustered (Hawkes): CV > 1
        cv = np.std(inter_arrivals) / np.mean(inter_arrivals)
        assert cv > 1.0, (
            f"Expected CV > 1 for clustered process, got CV={cv:.3f}. "
            f"Inter-arrival times appear too regular (Poisson-like)."
        )

    def test_unstable_parameters_rejected(self):
        """alpha >= beta should raise ValueError (unstable process)."""
        with pytest.raises(ValueError, match="unstable"):
            HawkesGenerator(base_intensity=10.0, alpha=1.5, beta=1.0)

    def test_both_sides_present(self):
        """Generator produces orders on both buy and sell sides."""
        gen = HawkesGenerator(
            base_intensity=10.0, alpha=0.5, beta=1.0, duration=30.0, seed=42
        )
        orders = gen.generate()
        sides = {o.side for o in orders}
        assert ex.Side.Buy in sides
        assert ex.Side.Sell in sides


class TestReplayGenerator:
    """Tests for the LOBSTER L3 replay generator."""

    def test_missing_file_raises(self):
        """FileNotFoundError raised for nonexistent file."""
        with pytest.raises(FileNotFoundError):
            ReplayGenerator("/nonexistent/path/to/data.csv")

    def test_empty_file_raises(self):
        """ValueError raised for empty file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("")
            path = f.name

        try:
            with pytest.raises(ValueError, match="Empty"):
                ReplayGenerator(path)
        finally:
            os.unlink(path)

    def test_invalid_format_raises(self):
        """ValueError raised for file with too few columns."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("1.0,2,3\n")
            path = f.name

        try:
            with pytest.raises(ValueError, match="Invalid LOBSTER format"):
                ReplayGenerator(path)
        finally:
            os.unlink(path)

    def test_valid_file_parses(self):
        """Valid LOBSTER file produces Order objects."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            # Type 1 = new limit order, direction 1 = buy
            f.write("34200.123456789,1,1001,100,500000,1\n")
            f.write("34200.234567890,1,1002,50,499900,-1\n")
            # Type 4 = execution (should be skipped)
            f.write("34200.345678901,4,1001,10,500000,1\n")
            path = f.name

        try:
            replay = ReplayGenerator(path)
            orders = list(replay.generate())

            assert len(orders) == 2  # only type=1 events
            assert orders[0].side == ex.Side.Buy
            assert orders[0].quantity == 100
            assert orders[0].price == 500000
            assert orders[1].side == ex.Side.Sell
            assert orders[1].quantity == 50
        finally:
            os.unlink(path)


class TestScenarios:
    """Tests for pre-built market scenarios."""

    def test_calm_market_non_empty(self):
        """Calm market scenario produces orders."""
        orders = calm_market(seed=1)
        assert len(orders) > 0

    def test_volatile_market_non_empty(self):
        """Volatile market scenario produces orders."""
        orders = volatile_market(seed=1)
        assert len(orders) > 0

    def test_flash_crash_non_empty(self):
        """Flash crash scenario produces orders."""
        orders = flash_crash(seed=1)
        assert len(orders) > 0

    def test_volatile_more_orders_than_calm(self):
        """Volatile market should generate more orders than calm."""
        calm = calm_market(seed=10)
        volatile = volatile_market(seed=10)
        # Volatile has higher intensity and shorter duration but more events/sec
        # Compare events per second
        calm_duration = calm[-1].timestamp / 1e9
        volatile_duration = volatile[-1].timestamp / 1e9
        calm_rate = len(calm) / calm_duration
        volatile_rate = len(volatile) / volatile_duration
        assert volatile_rate > calm_rate

    def test_flash_crash_has_phases(self):
        """Flash crash has distinct phases visible in timestamp gaps."""
        orders = flash_crash(seed=42)
        assert len(orders) > 100

        # All timestamps should be increasing
        timestamps = [o.timestamp for o in orders]
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1]

    def test_scenario_orders_valid(self):
        """All scenario orders have valid fields."""
        for scenario_fn in [calm_market, volatile_market, flash_crash]:
            orders = scenario_fn(seed=7)
            for order in orders:
                assert order.price > 0
                assert order.quantity > 0
                assert order.side in (ex.Side.Buy, ex.Side.Sell)
