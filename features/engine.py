"""Real-time feature computation engine for order book and trade data.

All features are computed in O(1) per tick using rolling windows and
incremental updates. The engine subscribes to market events (book updates
and trades) and maintains a feature vector that can be queried at any time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class FeatureConfig:
    """Configuration for which features to compute and their parameters.

    Attributes
    ----------
    imbalance_levels : int
        Number of book levels for imbalance computation (1-5).
    trade_imbalance_window : int
        Number of recent trades for trade imbalance.
    vwap_window : int
        Number of ticks for rolling VWAP.
    volatility_windows : list of int
        Tick windows for volatility computation.
    momentum_windows : list of int
        Tick windows for price momentum (returns).
    arrival_rate_alpha : float
        Exponential decay for arrival rate estimation.
    kyle_lambda_window : int
        Window for Kyle's lambda rolling regression.
    vpin_bucket_size : int
        Volume per VPIN bucket.
    vpin_num_buckets : int
        Number of buckets for VPIN computation.
    normalize : bool
        Whether to normalize features to approximately [-1, 1].
    """

    imbalance_levels: int = 5
    trade_imbalance_window: int = 50
    vwap_window: int = 100
    volatility_windows: list[int] = field(default_factory=lambda: [10, 50, 200])
    momentum_windows: list[int] = field(default_factory=lambda: [1, 5, 20, 50])
    arrival_rate_alpha: float = 0.05
    kyle_lambda_window: int = 50
    vpin_bucket_size: int = 50
    vpin_num_buckets: int = 20
    normalize: bool = True


class FeatureEngine:
    """Real-time feature computation from order book and trade events.

    The engine maintains internal state (rolling windows, price history)
    and computes a feature vector on each update. All computations are O(1)
    per tick using circular buffers and incremental statistics.

    Usage
    -----
    >>> config = FeatureConfig()
    >>> engine = FeatureEngine(config)
    >>> engine.on_book_update(bid_prices, bid_quantities, ask_prices, ask_quantities)
    >>> engine.on_trade(price, quantity, side)
    >>> features = engine.compute()  # numpy array
    """

    def __init__(self, config: Optional[FeatureConfig] = None):
        if config is None:
            config = FeatureConfig()
        self.config = config

        # Book state: prices and quantities at each level
        self._bid_prices = np.zeros(config.imbalance_levels, dtype=np.float64)
        self._bid_quantities = np.zeros(config.imbalance_levels, dtype=np.float64)
        self._ask_prices = np.zeros(config.imbalance_levels, dtype=np.float64)
        self._ask_quantities = np.zeros(config.imbalance_levels, dtype=np.float64)

        # Mid-price history for volatility and momentum
        max_window = max(
            max(config.volatility_windows),
            max(config.momentum_windows),
            config.vwap_window,
        )
        self._mid_history_size = max_window + 1
        self._mid_history = np.full(self._mid_history_size, np.nan, dtype=np.float64)
        self._mid_idx = 0
        self._tick_count = 0

        # Trade history for trade imbalance and VWAP
        self._trade_prices = np.zeros(config.trade_imbalance_window, dtype=np.float64)
        self._trade_quantities = np.zeros(config.trade_imbalance_window, dtype=np.float64)
        self._trade_sides = np.zeros(config.trade_imbalance_window, dtype=np.float64)  # +1 buy, -1 sell
        self._trade_idx = 0
        self._total_trades = 0

        # VWAP state (rolling)
        self._vwap_price_vol = np.zeros(config.vwap_window, dtype=np.float64)  # price * quantity
        self._vwap_vol = np.zeros(config.vwap_window, dtype=np.float64)  # quantity
        self._vwap_idx = 0
        self._total_vwap_updates = 0

        # Arrival rate (exponential moving average)
        self._arrival_rate = 0.0
        self._last_timestamp = 0.0

        # Kyle's lambda state (rolling regression)
        self._kyle_price_changes = np.zeros(config.kyle_lambda_window, dtype=np.float64)
        self._kyle_order_flows = np.zeros(config.kyle_lambda_window, dtype=np.float64)
        self._kyle_idx = 0
        self._total_kyle = 0
        self._prev_mid_for_kyle: Optional[float] = None

        # VPIN state
        self._vpin_buckets_buy = np.zeros(config.vpin_num_buckets, dtype=np.float64)
        self._vpin_buckets_total = np.zeros(config.vpin_num_buckets, dtype=np.float64)
        self._vpin_bucket_idx = 0
        self._vpin_current_bucket_vol = 0.0
        self._vpin_current_bucket_buy = 0.0
        self._total_vpin_buckets = 0

        # Compute feature vector size
        self._feature_names = self._build_feature_names()
        self._num_features = len(self._feature_names)

    def _build_feature_names(self) -> list[str]:
        """Build ordered list of feature names."""
        names = []
        # Book imbalance at each level
        for i in range(1, self.config.imbalance_levels + 1):
            names.append(f"book_imbalance_L{i}")
        # Weighted mid price deviation
        names.append("weighted_mid_deviation")
        # Trade imbalance
        names.append("trade_imbalance")
        # VWAP deviation
        names.append("vwap_deviation")
        # Spread (absolute and relative)
        names.append("spread_abs")
        names.append("spread_rel")
        # Volatility at different windows
        for w in self.config.volatility_windows:
            names.append(f"volatility_{w}")
        # VPIN
        names.append("vpin")
        # Price momentum at different windows
        for w in self.config.momentum_windows:
            names.append(f"momentum_{w}")
        # Arrival rate
        names.append("arrival_rate")
        # Kyle's lambda
        names.append("kyle_lambda")
        return names

    @property
    def feature_names(self) -> list[str]:
        """Return ordered list of feature names."""
        return self._feature_names

    @property
    def num_features(self) -> int:
        """Return the number of features in the output vector."""
        return self._num_features

    def on_book_update(
        self,
        bid_prices: np.ndarray | list,
        bid_quantities: np.ndarray | list,
        ask_prices: np.ndarray | list,
        ask_quantities: np.ndarray | list,
        timestamp: float = 0.0,
    ) -> None:
        """Update internal state with new book snapshot.

        Parameters
        ----------
        bid_prices : array-like
            Bid prices from best (index 0) to worst. Length <= imbalance_levels.
        bid_quantities : array-like
            Bid quantities corresponding to bid_prices.
        ask_prices : array-like
            Ask prices from best (index 0) to worst. Length <= imbalance_levels.
        ask_quantities : array-like
            Ask quantities corresponding to ask_prices.
        timestamp : float
            Event timestamp in seconds.
        """
        n_levels = self.config.imbalance_levels

        # Reset and fill
        self._bid_prices[:] = 0.0
        self._bid_quantities[:] = 0.0
        self._ask_prices[:] = 0.0
        self._ask_quantities[:] = 0.0

        bp = np.asarray(bid_prices, dtype=np.float64)
        bq = np.asarray(bid_quantities, dtype=np.float64)
        ap = np.asarray(ask_prices, dtype=np.float64)
        aq = np.asarray(ask_quantities, dtype=np.float64)

        n_bid = min(len(bp), n_levels)
        n_ask = min(len(ap), n_levels)

        self._bid_prices[:n_bid] = bp[:n_bid]
        self._bid_quantities[:n_bid] = bq[:n_bid]
        self._ask_prices[:n_ask] = ap[:n_ask]
        self._ask_quantities[:n_ask] = aq[:n_ask]

        # Update mid-price history
        mid = self._compute_mid()
        if mid is not None and np.isfinite(mid):
            idx = self._mid_idx % self._mid_history_size
            self._mid_history[idx] = mid
            self._mid_idx += 1
            self._tick_count += 1

        # Update arrival rate
        if timestamp > 0 and self._last_timestamp > 0:
            dt = timestamp - self._last_timestamp
            if dt > 0:
                instant_rate = 1.0 / dt
                alpha = self.config.arrival_rate_alpha
                self._arrival_rate = alpha * instant_rate + (1 - alpha) * self._arrival_rate
        self._last_timestamp = timestamp

    def on_trade(
        self,
        price: float,
        quantity: float,
        side: int,
        timestamp: float = 0.0,
    ) -> None:
        """Record a trade event.

        Parameters
        ----------
        price : float
            Trade price.
        quantity : float
            Trade quantity.
        side : int
            +1 for buy (aggressor), -1 for sell (aggressor).
        timestamp : float
            Event timestamp in seconds.
        """
        idx = self._trade_idx % self.config.trade_imbalance_window
        self._trade_prices[idx] = price
        self._trade_quantities[idx] = quantity
        self._trade_sides[idx] = side
        self._trade_idx += 1
        self._total_trades += 1

        # Update VWAP
        vwap_idx = self._vwap_idx % self.config.vwap_window
        self._vwap_price_vol[vwap_idx] = price * quantity
        self._vwap_vol[vwap_idx] = quantity
        self._vwap_idx += 1
        self._total_vwap_updates += 1

        # Update Kyle's lambda
        mid = self._compute_mid()
        if mid is not None and self._prev_mid_for_kyle is not None:
            price_change = mid - self._prev_mid_for_kyle
            order_flow = side * quantity
            k_idx = self._kyle_idx % self.config.kyle_lambda_window
            self._kyle_price_changes[k_idx] = price_change
            self._kyle_order_flows[k_idx] = order_flow
            self._kyle_idx += 1
            self._total_kyle += 1
        if mid is not None:
            self._prev_mid_for_kyle = mid

        # Update VPIN buckets
        self._vpin_current_bucket_vol += quantity
        if side > 0:
            self._vpin_current_bucket_buy += quantity

        if self._vpin_current_bucket_vol >= self.config.vpin_bucket_size:
            b_idx = self._vpin_bucket_idx % self.config.vpin_num_buckets
            self._vpin_buckets_buy[b_idx] = self._vpin_current_bucket_buy
            self._vpin_buckets_total[b_idx] = self._vpin_current_bucket_vol
            self._vpin_bucket_idx += 1
            self._total_vpin_buckets += 1
            self._vpin_current_bucket_vol = 0.0
            self._vpin_current_bucket_buy = 0.0

        # Update arrival rate from trade timestamp
        if timestamp > 0 and self._last_timestamp > 0:
            dt = timestamp - self._last_timestamp
            if dt > 0:
                instant_rate = 1.0 / dt
                alpha = self.config.arrival_rate_alpha
                self._arrival_rate = alpha * instant_rate + (1 - alpha) * self._arrival_rate
        if timestamp > 0:
            self._last_timestamp = timestamp

    def compute(self) -> np.ndarray:
        """Compute the full feature vector from current state.

        Returns
        -------
        np.ndarray
            Feature vector of shape (num_features,). Contains NaN for
            features that cannot yet be computed (insufficient history).
        """
        features = np.full(self._num_features, np.nan, dtype=np.float64)
        idx = 0

        # Book imbalance at each level: (bid_qty - ask_qty) / (bid_qty + ask_qty)
        for i in range(self.config.imbalance_levels):
            bq = self._bid_quantities[i]
            aq = self._ask_quantities[i]
            total = bq + aq
            if total > 0:
                features[idx] = (bq - aq) / total
            else:
                features[idx] = 0.0
            idx += 1

        # Weighted mid price deviation
        mid = self._compute_mid()
        wmid = self._compute_weighted_mid()
        if mid is not None and wmid is not None and mid > 0:
            # Normalize by spread
            spread = self._compute_spread()
            if spread > 0:
                features[idx] = (wmid - mid) / spread
            else:
                features[idx] = 0.0
        else:
            features[idx] = 0.0
        idx += 1

        # Trade imbalance: (buy_vol - sell_vol) / total_vol
        features[idx] = self._compute_trade_imbalance()
        idx += 1

        # VWAP deviation: (mid - vwap) / mid, normalized
        features[idx] = self._compute_vwap_deviation()
        idx += 1

        # Spread absolute and relative
        spread = self._compute_spread()
        if mid is not None and mid > 0:
            features[idx] = spread  # Will be normalized later
            idx += 1
            features[idx] = spread / mid
        else:
            features[idx] = 0.0
            idx += 1
            features[idx] = 0.0
        idx += 1

        # Volatility at different windows
        for w in self.config.volatility_windows:
            features[idx] = self._compute_volatility(w)
            idx += 1

        # VPIN
        features[idx] = self._compute_vpin()
        idx += 1

        # Price momentum at different windows
        for w in self.config.momentum_windows:
            features[idx] = self._compute_momentum(w)
            idx += 1

        # Arrival rate
        features[idx] = self._arrival_rate
        idx += 1

        # Kyle's lambda
        features[idx] = self._compute_kyle_lambda()
        idx += 1

        # Normalize if configured
        if self.config.normalize:
            features = self._normalize(features)

        return features

    def _compute_mid(self) -> Optional[float]:
        """Compute mid price from best bid and ask."""
        bp = self._bid_prices[0]
        ap = self._ask_prices[0]
        if bp > 0 and ap > 0:
            return (bp + ap) / 2.0
        return None

    def _compute_weighted_mid(self) -> Optional[float]:
        """Compute volume-weighted mid price.

        weighted_mid = (ask_qty * bid_px + bid_qty * ask_px) / (bid_qty + ask_qty)
        """
        bp = self._bid_prices[0]
        ap = self._ask_prices[0]
        bq = self._bid_quantities[0]
        aq = self._ask_quantities[0]

        total_qty = bq + aq
        if total_qty > 0 and bp > 0 and ap > 0:
            return (aq * bp + bq * ap) / total_qty
        return None

    def _compute_spread(self) -> float:
        """Compute current spread."""
        bp = self._bid_prices[0]
        ap = self._ask_prices[0]
        if bp > 0 and ap > 0:
            return ap - bp
        return 0.0

    def _compute_trade_imbalance(self) -> float:
        """Compute trade imbalance over recent trades.

        Returns (buy_volume - sell_volume) / total_volume.
        """
        n = min(self._total_trades, self.config.trade_imbalance_window)
        if n == 0:
            return 0.0

        # Use the filled portion of the circular buffer
        if self._total_trades <= self.config.trade_imbalance_window:
            sides = self._trade_sides[:n]
            quantities = self._trade_quantities[:n]
        else:
            sides = self._trade_sides
            quantities = self._trade_quantities

        buy_vol = np.sum(quantities[sides > 0])
        sell_vol = np.sum(quantities[sides < 0])
        total = buy_vol + sell_vol

        if total > 0:
            return (buy_vol - sell_vol) / total
        return 0.0

    def _compute_vwap_deviation(self) -> float:
        """Compute deviation of current mid from rolling VWAP."""
        mid = self._compute_mid()
        if mid is None:
            return 0.0

        n = min(self._total_vwap_updates, self.config.vwap_window)
        if n == 0:
            return 0.0

        if self._total_vwap_updates <= self.config.vwap_window:
            total_pv = np.sum(self._vwap_price_vol[:n])
            total_v = np.sum(self._vwap_vol[:n])
        else:
            total_pv = np.sum(self._vwap_price_vol)
            total_v = np.sum(self._vwap_vol)

        if total_v > 0:
            vwap = total_pv / total_v
            if vwap > 0:
                return (mid - vwap) / vwap
        return 0.0

    def _compute_volatility(self, window: int) -> float:
        """Compute rolling standard deviation of mid-price returns."""
        n_available = min(self._tick_count, self._mid_history_size)
        if n_available < window + 1:
            return np.nan

        # Get the last (window+1) mid prices for computing window returns
        prices = np.empty(window + 1, dtype=np.float64)
        for i in range(window + 1):
            buf_idx = (self._mid_idx - (window + 1) + i) % self._mid_history_size
            prices[i] = self._mid_history[buf_idx]

        # Compute returns
        valid_mask = (prices[:-1] > 0) & np.isfinite(prices[:-1]) & np.isfinite(prices[1:])
        if np.sum(valid_mask) < 2:
            return np.nan

        returns = np.diff(prices) / prices[:-1]
        valid_returns = returns[valid_mask]

        if len(valid_returns) < 2:
            return np.nan

        return float(np.std(valid_returns))

    def _compute_momentum(self, window: int) -> float:
        """Compute price return over the last `window` ticks."""
        n_available = min(self._tick_count, self._mid_history_size)
        if n_available <= window:
            return np.nan

        current_idx = (self._mid_idx - 1) % self._mid_history_size
        past_idx = (self._mid_idx - 1 - window) % self._mid_history_size

        current = self._mid_history[current_idx]
        past = self._mid_history[past_idx]

        if past > 0 and np.isfinite(past) and np.isfinite(current):
            return (current - past) / past
        return np.nan

    def _compute_vpin(self) -> float:
        """Compute Volume-Synchronized Probability of Informed Trading.

        VPIN = abs(sum(buy_vol - sell_vol per bucket)) / sum(total_vol per bucket)
        """
        n = min(self._total_vpin_buckets, self.config.vpin_num_buckets)
        if n < 2:
            return np.nan

        if self._total_vpin_buckets <= self.config.vpin_num_buckets:
            buy_vols = self._vpin_buckets_buy[:n]
            total_vols = self._vpin_buckets_total[:n]
        else:
            buy_vols = self._vpin_buckets_buy
            total_vols = self._vpin_buckets_total

        sell_vols = total_vols - buy_vols
        imbalances = np.abs(buy_vols - sell_vols)
        total = np.sum(total_vols)

        if total > 0:
            return float(np.sum(imbalances) / total)
        return np.nan

    def _compute_kyle_lambda(self) -> float:
        """Compute Kyle's lambda: price impact per unit of signed order flow.

        Uses OLS regression: delta_price = lambda * signed_flow + epsilon
        lambda = cov(delta_p, flow) / var(flow)
        """
        n = min(self._total_kyle, self.config.kyle_lambda_window)
        if n < 5:
            return np.nan

        if self._total_kyle <= self.config.kyle_lambda_window:
            dp = self._kyle_price_changes[:n]
            of = self._kyle_order_flows[:n]
        else:
            dp = self._kyle_price_changes
            of = self._kyle_order_flows

        var_of = np.var(of)
        if var_of < 1e-12:
            return np.nan

        cov = np.mean(dp * of) - np.mean(dp) * np.mean(of)
        return float(cov / var_of)

    def _normalize(self, features: np.ndarray) -> np.ndarray:
        """Normalize features to approximately [-1, 1] range.

        Uses feature-specific scaling factors based on typical market values.
        Features that are already ratios in [-1, 1] are left as-is.
        """
        result = features.copy()
        idx = 0

        # Book imbalance: already in [-1, 1]
        idx += self.config.imbalance_levels

        # Weighted mid deviation: already normalized by spread, clip
        result[idx] = np.clip(result[idx], -1.0, 1.0)
        idx += 1

        # Trade imbalance: already in [-1, 1]
        idx += 1

        # VWAP deviation: scale by 100 (typical deviation is < 1%)
        result[idx] = np.clip(result[idx] * 100.0, -1.0, 1.0)
        idx += 1

        # Spread absolute: normalize by typical spread (use current mid)
        mid = self._compute_mid()
        if mid is not None and mid > 0:
            result[idx] = np.clip(result[idx] / (mid * 0.01), -1.0, 1.0)  # 1% of mid as scale
        else:
            result[idx] = 0.0
        idx += 1

        # Spread relative: scale by 0.01 (typical is 0.01-0.1%)
        result[idx] = np.clip(result[idx] / 0.01, -1.0, 1.0)
        idx += 1

        # Volatility: scale each by typical vol level (0.01)
        for _ in self.config.volatility_windows:
            if np.isfinite(result[idx]):
                result[idx] = np.clip(result[idx] / 0.01, -1.0, 1.0)
            idx += 1

        # VPIN: already in [0, 1], shift to [-1, 1]
        if np.isfinite(result[idx]):
            result[idx] = np.clip(result[idx] * 2.0 - 1.0, -1.0, 1.0)
        idx += 1

        # Momentum: scale by 0.01 (1% move is large)
        for _ in self.config.momentum_windows:
            if np.isfinite(result[idx]):
                result[idx] = np.clip(result[idx] / 0.01, -1.0, 1.0)
            idx += 1

        # Arrival rate: normalize by 100 orders/sec as typical max
        if np.isfinite(result[idx]):
            result[idx] = np.clip(result[idx] / 100.0, -1.0, 1.0)
        idx += 1

        # Kyle's lambda: normalize by typical value
        if np.isfinite(result[idx]):
            result[idx] = np.clip(result[idx] / 0.001, -1.0, 1.0)
        idx += 1

        return result

    def reset(self) -> None:
        """Reset all internal state."""
        self.__init__(self.config)
