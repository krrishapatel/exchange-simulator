"""Dataset builder for supervised learning from simulated market data.

Runs a data source (Hawkes generator, Lobster replay, or live simulation)
through the FeatureEngine, computes features at each step, aligns labels,
and returns train-ready numpy arrays.
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np

from features.engine import FeatureConfig, FeatureEngine


def build_dataset(
    data_source,
    feature_config: Optional[FeatureConfig] = None,
    label_fn: Optional[Callable[[np.ndarray, int], np.ndarray]] = None,
    label_horizon: int = 10,
    max_samples: int = 50000,
    warmup: int = 200,
) -> tuple[np.ndarray, np.ndarray]:
    """Build feature matrix and label vector from a data source.

    Parameters
    ----------
    data_source : HawkesGenerator or similar
        Must have a `generate()` method returning a list of Order objects
        with .side, .price, .quantity, .timestamp, .type attributes.
    feature_config : FeatureConfig, optional
        Configuration for the feature engine. Uses defaults if None.
    label_fn : callable, optional
        Function(prices, horizon) -> labels. Defaults to directional_label.
    label_horizon : int
        Look-ahead horizon for label generation.
    max_samples : int
        Maximum number of samples to generate.
    warmup : int
        Number of initial ticks to skip (features may be NaN).

    Returns
    -------
    tuple of (X, y)
        X : np.ndarray of shape (n_samples, n_features)
        y : np.ndarray of shape (n_samples,)
    """
    import exchange_simulator as ex

    if feature_config is None:
        feature_config = FeatureConfig()
    if label_fn is None:
        from features.labels import directional_label

        def label_fn(prices, horizon):
            return directional_label(prices, horizon)

    engine_fe = FeatureEngine(feature_config)
    engine_me = ex.MatchingEngine()

    # Generate orders from data source
    orders = data_source.generate()

    # Process orders through matching engine, collecting features
    all_features = []
    mid_prices = []

    # Track book state from orders and fills
    # Since the OrderBook API only gives us best bid/ask and level counts,
    # we maintain our own L2 book from the order flow.
    bid_book: dict[int, int] = {}  # price -> total_qty
    ask_book: dict[int, int] = {}  # price -> total_qty

    for order in orders:
        if len(all_features) >= max_samples + warmup + label_horizon:
            break

        # Submit order to matching engine
        fills = engine_me.submit(order)

        # Update our shadow book
        if order.type == ex.OrderType.Limit:
            if order.side == ex.Side.Buy:
                bid_book[order.price] = bid_book.get(order.price, 0) + order.quantity
            else:
                ask_book[order.price] = ask_book.get(order.price, 0) + order.quantity

        # Process fills - reduce quantities from the book
        for fill in fills:
            price = fill.price
            qty = fill.quantity

            # Fills reduce both sides
            if price in bid_book:
                bid_book[price] = max(0, bid_book[price] - qty)
                if bid_book[price] == 0:
                    del bid_book[price]
            if price in ask_book:
                ask_book[price] = max(0, ask_book[price] - qty)
                if ask_book[price] == 0:
                    del ask_book[price]

            # Record trade in feature engine
            side_val = 1 if fill.aggressor_side == ex.Side.Buy else -1
            engine_fe.on_trade(
                float(fill.price),
                float(fill.quantity),
                side_val,
                float(order.timestamp) / 1e9,
            )

        # Build L2 snapshot for feature engine
        n_levels = feature_config.imbalance_levels

        # Top N bid levels (sorted descending by price)
        sorted_bids = sorted(
            ((p, q) for p, q in bid_book.items() if q > 0),
            key=lambda x: -x[0],
        )[:n_levels]

        # Top N ask levels (sorted ascending by price)
        sorted_asks = sorted(
            ((p, q) for p, q in ask_book.items() if q > 0),
            key=lambda x: x[0],
        )[:n_levels]

        bid_prices = [p for p, q in sorted_bids]
        bid_quantities = [q for p, q in sorted_bids]
        ask_prices = [p for p, q in sorted_asks]
        ask_quantities = [q for p, q in sorted_asks]

        # Update feature engine with book snapshot
        engine_fe.on_book_update(
            bid_prices,
            bid_quantities,
            ask_prices,
            ask_quantities,
            float(order.timestamp) / 1e9,
        )

        # Compute features
        feat_vec = engine_fe.compute()
        all_features.append(feat_vec)

        # Record mid price for label generation
        book = engine_me.book()
        best_bid = book.best_bid_price()
        best_ask = book.best_ask_price()
        if best_bid is not None and best_ask is not None:
            mid_prices.append((best_bid + best_ask) / 2.0)
        elif len(mid_prices) > 0:
            mid_prices.append(mid_prices[-1])
        else:
            mid_prices.append(np.nan)

    if len(all_features) == 0:
        n_feat = engine_fe.num_features
        return np.empty((0, n_feat), dtype=np.float64), np.empty(0, dtype=np.float64)

    # Stack features into matrix
    X_all = np.array(all_features, dtype=np.float64)
    prices_arr = np.array(mid_prices, dtype=np.float64)

    # Generate labels
    y_all = label_fn(prices_arr, label_horizon)

    # Remove warmup period and samples without valid labels
    valid_start = warmup
    valid_end = len(y_all) - label_horizon  # Labels need look-ahead

    if valid_end <= valid_start:
        n_feat = engine_fe.num_features
        return np.empty((0, n_feat), dtype=np.float64), np.empty(0, dtype=np.float64)

    X = X_all[valid_start:valid_end]
    y = y_all[valid_start:valid_end]

    # Remove rows where features or labels are NaN
    valid_mask = np.isfinite(y)
    # Also check that features don't have too many NaNs (allow some)
    feat_nan_count = np.sum(~np.isfinite(X), axis=1)
    valid_mask &= feat_nan_count < X.shape[1] // 2

    X = X[valid_mask]
    y = y[valid_mask]

    # Replace remaining NaN features with 0
    X = np.nan_to_num(X, nan=0.0)

    # Limit to max_samples
    if len(X) > max_samples:
        X = X[:max_samples]
        y = y[:max_samples]

    return X, y
