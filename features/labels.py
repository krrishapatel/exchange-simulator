"""Target label generation for supervised learning.

Provides functions to compute forward-looking labels from price series,
aligned with feature vectors for training ML models.
"""

from __future__ import annotations

import numpy as np


def mid_price_return(prices: np.ndarray, horizon: int) -> np.ndarray:
    """Compute future mid-price return at a given horizon.

    Parameters
    ----------
    prices : np.ndarray
        Array of mid-prices (shape: (N,)).
    horizon : int
        Number of ticks to look ahead.

    Returns
    -------
    np.ndarray
        Array of returns (shape: (N,)). Last `horizon` entries are NaN
        since we cannot compute future returns for them.
    """
    n = len(prices)
    labels = np.full(n, np.nan, dtype=np.float64)

    if n <= horizon:
        return labels

    future_prices = prices[horizon:]
    current_prices = prices[:n - horizon]

    # Avoid division by zero
    valid = current_prices > 0
    labels[:n - horizon][valid] = (
        (future_prices[valid] - current_prices[valid]) / current_prices[valid]
    )

    return labels


def spread_crossing(prices: np.ndarray, horizon: int) -> np.ndarray:
    """Binary label: does price move more than one spread within horizon?

    Simplified version: labels as 1 if the price moves up by more than
    a threshold (half the average spread), -1 if down, 0 if flat.

    Parameters
    ----------
    prices : np.ndarray
        Array of mid-prices (shape: (N,)).
    horizon : int
        Number of ticks to look ahead for the crossing.

    Returns
    -------
    np.ndarray
        Array of labels: 1 (up crossing), -1 (down crossing), 0 (no crossing).
        Last `horizon` entries are NaN.
    """
    n = len(prices)
    labels = np.full(n, np.nan, dtype=np.float64)

    if n <= horizon:
        return labels

    # Compute threshold as fraction of typical price movement
    returns = np.diff(prices)
    valid_returns = returns[np.isfinite(returns) & (returns != 0)]
    if len(valid_returns) < 10:
        threshold = 0.0
    else:
        threshold = np.std(valid_returns) * 0.5

    for i in range(n - horizon):
        current = prices[i]
        if current <= 0 or not np.isfinite(current):
            continue

        # Look at maximum excursion within horizon
        future_window = prices[i + 1: i + 1 + horizon]
        max_price = np.max(future_window)
        min_price = np.min(future_window)

        up_move = max_price - current
        down_move = current - min_price

        if up_move > threshold and up_move >= down_move:
            labels[i] = 1.0
        elif down_move > threshold and down_move > up_move:
            labels[i] = -1.0
        else:
            labels[i] = 0.0

    return labels


def directional_label(prices: np.ndarray, horizon: int, threshold: float = 0.0) -> np.ndarray:
    """Classify future returns as up/down/flat.

    Parameters
    ----------
    prices : np.ndarray
        Array of mid-prices.
    horizon : int
        Look-ahead window in ticks.
    threshold : float
        Return magnitude below which the label is 'flat' (0).
        If 0, uses adaptive threshold (median absolute return).

    Returns
    -------
    np.ndarray
        Labels: 1 (up), -1 (down), 0 (flat). Shape (N,).
    """
    returns = mid_price_return(prices, horizon)

    if threshold == 0.0:
        valid_ret = returns[np.isfinite(returns)]
        if len(valid_ret) > 0:
            threshold = np.median(np.abs(valid_ret)) * 0.5
        else:
            threshold = 1e-10

    labels = np.zeros_like(returns)
    labels[returns > threshold] = 1.0
    labels[returns < -threshold] = -1.0
    labels[~np.isfinite(returns)] = np.nan

    return labels


def volatility_regime(prices: np.ndarray, window: int = 50) -> np.ndarray:
    """Categorical label for volatility regime: low (0), medium (1), high (2).

    Computes rolling volatility and classifies into terciles.

    Parameters
    ----------
    prices : np.ndarray
        Array of mid-prices.
    window : int
        Rolling window for volatility computation.

    Returns
    -------
    np.ndarray
        Labels: 0 (low vol), 1 (medium vol), 2 (high vol). Shape (N,).
        First `window` entries are NaN.
    """
    n = len(prices)
    labels = np.full(n, np.nan, dtype=np.float64)

    if n < window + 1:
        return labels

    # Compute returns
    returns = np.zeros(n, dtype=np.float64)
    returns[1:] = np.diff(prices) / np.maximum(prices[:-1], 1e-10)

    # Rolling std
    vol = np.full(n, np.nan, dtype=np.float64)
    for i in range(window, n):
        vol[i] = np.std(returns[i - window + 1: i + 1])

    # Classify into terciles based on the overall distribution
    valid_vol = vol[np.isfinite(vol)]
    if len(valid_vol) < 3:
        return labels

    low_threshold = np.percentile(valid_vol, 33.3)
    high_threshold = np.percentile(valid_vol, 66.7)

    for i in range(window, n):
        v = vol[i]
        if not np.isfinite(v):
            continue
        if v <= low_threshold:
            labels[i] = 0.0
        elif v <= high_threshold:
            labels[i] = 1.0
        else:
            labels[i] = 2.0

    return labels
