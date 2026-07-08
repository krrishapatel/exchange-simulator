"""Tests for MultiAssetEngine Python bindings."""

import exchange_simulator as ex


def make_order(order_id, side, price, qty, timestamp=1000):
    """Helper to create a limit order."""
    o = ex.Order()
    o.id = order_id
    o.side = side
    o.price = price
    o.quantity = qty
    o.filled_quantity = 0
    o.visible_quantity = 0
    o.hidden_quantity = 0
    o.type = ex.OrderType.Limit
    o.tif = ex.TimeInForce.GTC
    o.timestamp = timestamp
    return o


def test_separate_books_per_symbol():
    """MultiAssetEngine creates separate books per symbol."""
    engine = ex.MultiAssetEngine()

    # Submit buy to symbol 1
    buy = make_order(1, ex.Side.Buy, 100, 10)
    fills = engine.submit(symbol_id=1, order=buy)
    assert len(fills) == 0

    # Submit sell to symbol 2 at same price - should NOT match
    sell = make_order(2, ex.Side.Sell, 100, 10)
    fills = engine.submit(symbol_id=2, order=sell)
    assert len(fills) == 0

    # Verify both books have resting orders
    assert engine.get_book(1).book().bid_depth() == 1
    assert engine.get_book(2).book().ask_depth() == 1


def test_cross_symbol_isolation():
    """Orders on different symbols never interact."""
    engine = ex.MultiAssetEngine()

    # Symbol 1: create matching orders
    buy = make_order(1, ex.Side.Buy, 100, 10)
    engine.submit(symbol_id=1, order=buy)
    sell = make_order(2, ex.Side.Sell, 100, 10)
    fills = engine.submit(symbol_id=1, order=sell)
    assert len(fills) == 1
    assert fills[0].price == 100
    assert fills[0].quantity == 10

    # Symbol 2: resting buy should still be there (not affected by symbol 1)
    buy2 = make_order(3, ex.Side.Buy, 100, 10)
    engine.submit(symbol_id=2, order=buy2)
    assert engine.get_book(2).book().bid_depth() == 1


def test_cancel_routes_to_correct_book():
    """Cancel finds the correct symbol's book."""
    engine = ex.MultiAssetEngine()

    # Place on symbol 1
    order1 = make_order(100, ex.Side.Buy, 50, 5)
    engine.submit(symbol_id=1, order=order1)

    # Place on symbol 2
    order2 = make_order(200, ex.Side.Buy, 60, 5)
    engine.submit(symbol_id=2, order=order2)

    # Cancel symbol 1 order
    result = engine.cancel(order_id=100)
    assert result == ex.CancelResult.Success

    # Symbol 1 is empty, symbol 2 still has order
    assert engine.get_book(1).book().bid_depth() == 0
    assert engine.get_book(2).book().bid_depth() == 1


def test_symbols_returns_active():
    """symbols() returns all active symbol IDs."""
    engine = ex.MultiAssetEngine()

    assert len(engine.symbols()) == 0

    o1 = make_order(1, ex.Side.Buy, 100, 10)
    engine.submit(symbol_id=10, order=o1)
    o2 = make_order(2, ex.Side.Buy, 100, 10)
    engine.submit(symbol_id=20, order=o2)
    o3 = make_order(3, ex.Side.Buy, 100, 10)
    engine.submit(symbol_id=30, order=o3)

    syms = sorted(engine.symbols())
    assert syms == [10, 20, 30]


def test_cancel_unknown_order():
    """Cancelling an unknown order returns OrderNotFound."""
    engine = ex.MultiAssetEngine()
    result = engine.cancel(order_id=99999)
    assert result == ex.CancelResult.OrderNotFound


def test_get_book_creates_if_missing():
    """get_book creates a new empty book for a new symbol."""
    engine = ex.MultiAssetEngine()

    book = engine.get_book(42)
    assert book.book().bid_depth() == 0
    assert book.book().ask_depth() == 0
    assert 42 in engine.symbols()
