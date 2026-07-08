"""Hawkes process order flow generator.

Generates realistic order arrival times with self-exciting clustering.
Buy and sell arrivals are separate but cross-exciting: a burst on one
side triggers more activity on both sides, mimicking real market
microstructure dynamics.
"""

import numpy as np

import exchange_simulator as ex


class HawkesGenerator:
    """Generates synthetic order flow using a bivariate Hawkes process.

    Parameters
    ----------
    base_intensity : float
        Baseline arrival rate (lambda_0) for each side, in events per second.
    alpha : float
        Kernel strength (self-excitation magnitude). Must be < beta for stability.
    beta : float
        Exponential decay rate of the excitation kernel.
    duration : float
        Total simulation duration in seconds.
    mid_price : int
        Starting mid-price (fixed-point integer matching engine convention).
    tick_size : int
        Minimum price increment.
    avg_quantity : int
        Mean order quantity (drawn from geometric distribution).
    cross_excitation : float
        Fraction of excitation transmitted to the opposite side (0 to 1).
    limit_ratio : float
        Probability an order is a limit order (vs market order).
    spread_ticks : int
        Average half-spread in ticks for limit order placement.
    seed : int or None
        Random seed for reproducibility.
    """

    def __init__(
        self,
        base_intensity: float = 10.0,
        alpha: float = 0.8,
        beta: float = 1.2,
        duration: float = 60.0,
        mid_price: int = 100_000,
        tick_size: int = 100,
        avg_quantity: int = 10,
        cross_excitation: float = 0.5,
        limit_ratio: float = 0.7,
        spread_ticks: int = 3,
        seed: int | None = None,
    ):
        if alpha >= beta:
            raise ValueError("Hawkes process unstable: alpha must be < beta")
        self.base_intensity = base_intensity
        self.alpha = alpha
        self.beta = beta
        self.duration = duration
        self.mid_price = mid_price
        self.tick_size = tick_size
        self.avg_quantity = avg_quantity
        self.cross_excitation = cross_excitation
        self.limit_ratio = limit_ratio
        self.spread_ticks = spread_ticks
        self.seed = seed

    def generate(self) -> list:
        """Generate order flow using thinning algorithm for bivariate Hawkes.

        Returns
        -------
        list of exchange_simulator.Order
            Orders with realistic timestamps, prices, and quantities.
        """
        rng = np.random.default_rng(self.seed)
        orders = []
        order_id = 1

        # State: intensity for buy and sell sides
        # Each side's intensity: lambda_i(t) = base + sum of kernel contributions
        buy_history = []  # list of event times for buy side
        sell_history = []  # list of event times for sell side

        t = 0.0
        current_mid = float(self.mid_price)

        # Volatility: modulated by recent event intensity
        base_vol = self.tick_size * 0.5  # baseline per-event mid-price jitter

        while t < self.duration:
            # Compute current intensities
            lambda_buy = self._intensity(t, buy_history, sell_history, rng)
            lambda_sell = self._intensity(t, sell_history, buy_history, rng)
            lambda_total = lambda_buy + lambda_sell

            if lambda_total <= 0:
                lambda_total = self.base_intensity * 2

            # Thinning: propose next event time
            dt = rng.exponential(1.0 / lambda_total)
            t += dt

            if t >= self.duration:
                break

            # Accept/reject (Ogata thinning)
            lambda_buy_new = self._intensity(t, buy_history, sell_history, rng)
            lambda_sell_new = self._intensity(t, sell_history, buy_history, rng)
            lambda_total_new = lambda_buy_new + lambda_sell_new

            u = rng.uniform()
            if u > lambda_total_new / lambda_total:
                continue  # reject

            # Determine which side fires
            if rng.uniform() < lambda_buy_new / (lambda_buy_new + lambda_sell_new):
                side = ex.Side.Buy
                buy_history.append(t)
            else:
                side = ex.Side.Sell
                sell_history.append(t)

            # Update mid-price: random walk with Hawkes-modulated volatility
            recent_events = len(
                [e for e in buy_history[-20:] + sell_history[-20:] if t - e < 1.0]
            )
            vol_multiplier = 1.0 + 0.1 * recent_events
            mid_step = rng.normal(0, base_vol * vol_multiplier)
            current_mid += mid_step
            current_mid = max(current_mid, self.tick_size * 10)  # floor

            # Decide order type
            is_limit = rng.uniform() < self.limit_ratio
            order_type = ex.OrderType.Limit if is_limit else ex.OrderType.Market

            # Price determination
            if is_limit:
                offset_ticks = rng.geometric(1.0 / self.spread_ticks)
                offset = offset_ticks * self.tick_size
                if side == ex.Side.Buy:
                    price = int(round(current_mid / self.tick_size) * self.tick_size - offset)
                else:
                    price = int(round(current_mid / self.tick_size) * self.tick_size + offset)
            else:
                # Market orders: price at 0 (engine handles as marketable)
                price = 0

            price = max(price, self.tick_size)

            # Quantity from geometric distribution
            quantity = int(rng.geometric(1.0 / self.avg_quantity))
            quantity = max(1, quantity)

            # Build Order object
            order = ex.Order()
            order.id = order_id
            order.side = side
            order.price = price
            order.quantity = quantity
            order.filled_quantity = 0
            order.type = order_type
            order.tif = ex.TimeInForce.GTC if is_limit else ex.TimeInForce.IOC
            order.timestamp = int(t * 1_000_000_000)  # seconds -> nanoseconds
            order.stop_price = 0
            order.peg_offset = 0
            order.visible_quantity = 0
            order.hidden_quantity = 0

            orders.append(order)
            order_id += 1

        return orders

    def _intensity(
        self, t: float, own_history: list, other_history: list, rng
    ) -> float:
        """Compute intensity at time t for one side.

        Uses exponential kernel with self-excitation and cross-excitation.
        """
        intensity = self.base_intensity

        # Self-excitation from own history (recent events only for performance)
        for event_t in own_history[-100:]:
            dt = t - event_t
            if dt <= 0:
                continue
            intensity += self.alpha * np.exp(-self.beta * dt)

        # Cross-excitation from other side
        for event_t in other_history[-100:]:
            dt = t - event_t
            if dt <= 0:
                continue
            intensity += self.cross_excitation * self.alpha * np.exp(-self.beta * dt)

        return max(intensity, 0.0)
