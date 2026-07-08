"""Pre-built market scenarios using the Hawkes order flow generator.

Each scenario returns a list of Order objects configured to produce
characteristic market microstructure dynamics.
"""

from data.hawkes import HawkesGenerator


def calm_market(seed: int = 42) -> list:
    """Low intensity, tight spread, gentle random walk.

    Simulates a quiet market with steady, predictable order flow.
    Typical of large-cap stocks during midday trading.

    Parameters
    ----------
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    list of Order
        Orders exhibiting calm market behavior.
    """
    gen = HawkesGenerator(
        base_intensity=5.0,
        alpha=0.3,
        beta=1.0,
        duration=120.0,
        mid_price=100_000,
        tick_size=100,
        avg_quantity=10,
        cross_excitation=0.2,
        limit_ratio=0.85,
        spread_ticks=2,
        seed=seed,
    )
    return gen.generate()


def volatile_market(seed: int = 42) -> list:
    """High intensity, wider spread, momentum bursts.

    Simulates a turbulent market with clustered arrivals and
    wider spreads. Typical of news-driven volatility events.

    Parameters
    ----------
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    list of Order
        Orders exhibiting volatile market behavior.
    """
    gen = HawkesGenerator(
        base_intensity=30.0,
        alpha=0.95,
        beta=1.1,
        duration=60.0,
        mid_price=100_000,
        tick_size=100,
        avg_quantity=20,
        cross_excitation=0.8,
        limit_ratio=0.5,
        spread_ticks=5,
        seed=seed,
    )
    return gen.generate()


def flash_crash(seed: int = 42) -> list:
    """Calm period followed by sudden liquidity withdrawal and recovery.

    Generates three phases:
    1. Calm buildup (book fills with limit orders)
    2. Crash (aggressive selling, few limit buys, wide spreads)
    3. Recovery (intensity drops, spread normalizes)

    Parameters
    ----------
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    list of Order
        Orders simulating a flash crash event.
    """
    orders = []

    # Phase 1: Calm buildup (30 seconds)
    calm_gen = HawkesGenerator(
        base_intensity=8.0,
        alpha=0.2,
        beta=1.0,
        duration=30.0,
        mid_price=100_000,
        tick_size=100,
        avg_quantity=10,
        cross_excitation=0.2,
        limit_ratio=0.9,
        spread_ticks=2,
        seed=seed,
    )
    phase1 = calm_gen.generate()
    orders.extend(phase1)

    # Phase 2: Crash (10 seconds) - high intensity, aggressive selling
    crash_gen = HawkesGenerator(
        base_intensity=50.0,
        alpha=1.1,
        beta=1.2,
        duration=10.0,
        mid_price=98_000,  # price already falling
        tick_size=100,
        avg_quantity=50,
        cross_excitation=0.9,
        limit_ratio=0.2,  # mostly market orders
        spread_ticks=10,
        seed=seed + 1 if seed is not None else None,
    )
    phase2 = crash_gen.generate()

    # Offset timestamps for phase 2
    phase1_end_ns = phase1[-1].timestamp if phase1 else 30_000_000_000
    for order in phase2:
        order.timestamp += phase1_end_ns
        order.id += len(phase1)
    orders.extend(phase2)

    # Phase 3: Recovery (20 seconds) - calming down
    recovery_gen = HawkesGenerator(
        base_intensity=12.0,
        alpha=0.4,
        beta=1.5,
        duration=20.0,
        mid_price=95_000,  # lower after crash
        tick_size=100,
        avg_quantity=15,
        cross_excitation=0.3,
        limit_ratio=0.8,
        spread_ticks=4,
        seed=seed + 2 if seed is not None else None,
    )
    phase3 = recovery_gen.generate()

    # Offset timestamps for phase 3
    phase2_end_ns = orders[-1].timestamp if orders else 40_000_000_000
    for order in phase3:
        order.timestamp += phase2_end_ns
        order.id += len(orders)
    orders.extend(phase3)

    return orders
