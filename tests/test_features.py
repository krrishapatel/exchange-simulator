"""Tests for the order book feature engineering pipeline."""

import numpy as np
import pytest

from features.engine import FeatureEngine, FeatureConfig


class TestBookImbalance:
    def test_balanced_book(self):
        engine = FeatureEngine(FeatureConfig(imbalance_levels=3, normalize=False))
        engine.on_book_update(
            bid_prices=[100, 99, 98],
            bid_quantities=[50, 50, 50],
            ask_prices=[101, 102, 103],
            ask_quantities=[50, 50, 50],
        )
        features = engine.compute()
        # All levels balanced -> imbalance = 0
        for i in range(3):
            assert features[i] == pytest.approx(0.0)

    def test_bid_heavy_imbalance(self):
        engine = FeatureEngine(FeatureConfig(imbalance_levels=3, normalize=False))
        engine.on_book_update(
            bid_prices=[100, 99, 98],
            bid_quantities=[100, 50, 50],
            ask_prices=[101, 102, 103],
            ask_quantities=[20, 50, 50],
        )
        features = engine.compute()
        # Level 1: (100-20)/(100+20) = 80/120 = 0.667
        assert features[0] == pytest.approx(80 / 120, rel=1e-3)

    def test_ask_heavy_imbalance(self):
        engine = FeatureEngine(FeatureConfig(imbalance_levels=2, normalize=False))
        engine.on_book_update(
            bid_prices=[100, 99],
            bid_quantities=[10, 10],
            ask_prices=[101, 102],
            ask_quantities=[90, 90],
        )
        features = engine.compute()
        # Level 1: (10-90)/(10+90) = -0.8
        assert features[0] == pytest.approx(-0.8)


class TestTradeImbalance:
    def test_all_buys(self):
        engine = FeatureEngine(FeatureConfig(trade_imbalance_window=10, normalize=False))
        engine.on_book_update([100], [50], [101], [50])
        for _ in range(10):
            engine.on_trade(price=100.5, quantity=10, side=1)
        features = engine.compute()
        # trade_imbalance is after imbalance_levels(5) + weighted_mid(1)
        trade_imb_idx = 5 + 1
        assert features[trade_imb_idx] == pytest.approx(1.0)

    def test_all_sells(self):
        engine = FeatureEngine(FeatureConfig(trade_imbalance_window=10, normalize=False))
        engine.on_book_update([100], [50], [101], [50])
        for _ in range(10):
            engine.on_trade(price=100.5, quantity=10, side=-1)
        features = engine.compute()
        trade_imb_idx = 5 + 1
        assert features[trade_imb_idx] == pytest.approx(-1.0)

    def test_balanced_trades(self):
        engine = FeatureEngine(FeatureConfig(trade_imbalance_window=10, normalize=False))
        engine.on_book_update([100], [50], [101], [50])
        for i in range(10):
            side = 1 if i % 2 == 0 else -1
            engine.on_trade(price=100.5, quantity=10, side=side)
        features = engine.compute()
        trade_imb_idx = 5 + 1
        assert features[trade_imb_idx] == pytest.approx(0.0)


class TestVolatility:
    def test_zero_volatility_flat_price(self):
        config = FeatureConfig(volatility_windows=[5], momentum_windows=[1], normalize=False)
        engine = FeatureEngine(config)
        for _ in range(20):
            engine.on_book_update([100], [50], [101], [50])
        features = engine.compute()
        # After: imbalance(5) + wmid(1) + trade_imb(1) + vwap(1) + spread_abs(1) + spread_rel(1) = idx 10
        vol_idx = 10
        assert features[vol_idx] == pytest.approx(0.0, abs=1e-10)

    def test_higher_variance_higher_vol(self):
        config = FeatureConfig(volatility_windows=[10], momentum_windows=[1], normalize=False)
        engine_low = FeatureEngine(config)
        engine_high = FeatureEngine(config)

        # Low vol: price barely moves
        for i in range(20):
            p = 100.0 + 0.001 * (i % 2)
            engine_low.on_book_update([p], [50], [p + 1], [50])

        # High vol: price swings
        for i in range(20):
            p = 100.0 + 2.0 * ((-1) ** i)
            engine_high.on_book_update([p], [50], [p + 1], [50])

        f_low = engine_low.compute()
        f_high = engine_high.compute()
        vol_idx = 10
        assert f_high[vol_idx] > f_low[vol_idx]


class TestFeatureVector:
    def test_correct_shape(self):
        config = FeatureConfig()
        engine = FeatureEngine(config)
        engine.on_book_update([100], [50], [101], [50])
        features = engine.compute()
        assert features.shape == (engine.num_features,)
        assert len(engine.feature_names) == engine.num_features

    def test_empty_book_graceful(self):
        engine = FeatureEngine(FeatureConfig(normalize=False))
        features = engine.compute()
        assert features.shape == (engine.num_features,)
        # Should not crash, imbalances should be 0
        for i in range(5):
            assert features[i] == 0.0 or np.isnan(features[i])

    def test_normalization_bounds(self):
        config = FeatureConfig(normalize=True)
        engine = FeatureEngine(config)
        # Feed enough data to populate all features
        for i in range(300):
            bid = 100.0 + np.sin(i * 0.1) * 2
            engine.on_book_update(
                [bid, bid - 1, bid - 2, bid - 3, bid - 4],
                [50, 40, 30, 20, 10],
                [bid + 1, bid + 2, bid + 3, bid + 4, bid + 5],
                [50, 40, 30, 20, 10],
                timestamp=i * 0.01,
            )
            side = 1 if i % 3 != 0 else -1
            engine.on_trade(price=bid + 0.5, quantity=10, side=side, timestamp=i * 0.01)

        features = engine.compute()
        # All finite features should be in [-1, 1]
        finite_mask = np.isfinite(features)
        assert np.all(features[finite_mask] >= -1.0)
        assert np.all(features[finite_mask] <= 1.0)


class TestKyleLambda:
    def test_positive_lambda_with_price_impact(self):
        config = FeatureConfig(kyle_lambda_window=20, normalize=False)
        engine = FeatureEngine(config)

        # Simulate: buys push price up, sells push price down
        price = 100.0
        for i in range(30):
            side = 1 if i % 2 == 0 else -1
            price += side * 0.5  # price moves with order flow
            engine.on_book_update([price], [50], [price + 1], [50])
            engine.on_trade(price=price + 0.5, quantity=10, side=side)

        features = engine.compute()
        kyle_idx = engine.num_features - 1  # last feature
        assert np.isfinite(features[kyle_idx])
        assert features[kyle_idx] > 0  # positive price impact


class TestVWAPDeviation:
    def test_above_vwap(self):
        config = FeatureConfig(vwap_window=10, normalize=False)
        engine = FeatureEngine(config)

        # Trade at low prices
        for i in range(15):
            engine.on_book_update([90], [50], [91], [50])
            engine.on_trade(price=90.5, quantity=10, side=1)

        # Now price is higher
        engine.on_book_update([100], [50], [101], [50])
        features = engine.compute()
        # vwap_deviation idx = 5 + 1 + 1 = 7
        vwap_idx = 7
        assert features[vwap_idx] > 0  # mid > vwap
