#!/usr/bin/env python3
"""Test script for exchange_simulator Python bindings."""

import exchange_simulator as ex


def test_enums():
    """Verify all enum values are accessible."""
    assert ex.Side.Buy != ex.Side.Sell
    assert ex.OrderType.Limit != ex.OrderType.Market
    assert ex.OrderType.Stop != ex.OrderType.Pegged
    assert ex.TimeInForce.GTC != ex.TimeInForce.IOC
    assert ex.TimeInForce.FOK != ex.TimeInForce.GTC
    assert ex.Phase.PreOpen != ex.Phase.Continuous
    assert ex.CancelResult.Success != ex.CancelResult.OrderNotFound
    assert ex.CancelResult.AlreadyFilled != ex.CancelResult.Success
    print("  [PASS] test_enums")


def test_order_creation():
    """Verify Order struct fields are readable/writable."""
    order = ex.Order()
    order.id = 42
    order.price = 10000
    order.stop_price = 0
    order.peg_offset = 0
    order.quantity = 100
    order.filled_quantity = 0
    order.visible_quantity = 0
    order.hidden_quantity = 0
    order.side = ex.Side.Buy
    order.type = ex.OrderType.Limit
    order.tif = ex.TimeInForce.GTC
    order.timestamp = 1000

    assert order.id == 42
    assert order.price == 10000
    assert order.quantity == 100
    assert order.remaining() == 100
    assert not order.is_filled()
    assert not order.is_iceberg()
    print("  [PASS] test_order_creation")


def test_basic_match():
    """Test a simple buy/sell limit order match."""
    engine = ex.MatchingEngine()

    sell = ex.Order()
    sell.id = 1
    sell.side = ex.Side.Sell
    sell.price = 10000
    sell.stop_price = 0
    sell.peg_offset = 0
    sell.quantity = 50
    sell.filled_quantity = 0
    sell.visible_quantity = 0
    sell.hidden_quantity = 0
    sell.type = ex.OrderType.Limit
    sell.tif = ex.TimeInForce.GTC
    sell.timestamp = 1

    fills = engine.submit(sell)
    assert len(fills) == 0

    buy = ex.Order()
    buy.id = 2
    buy.side = ex.Side.Buy
    buy.price = 10000
    buy.stop_price = 0
    buy.peg_offset = 0
    buy.quantity = 50
    buy.filled_quantity = 0
    buy.visible_quantity = 0
    buy.hidden_quantity = 0
    buy.type = ex.OrderType.Limit
    buy.tif = ex.TimeInForce.GTC
    buy.timestamp = 2

    fills = engine.submit(buy)
    assert len(fills) == 1
    assert fills[0].quantity == 50
    assert fills[0].price == 10000
    assert fills[0].maker_order_id == 1
    assert fills[0].taker_order_id == 2
    assert fills[0].aggressor_side == ex.Side.Buy
    print("  [PASS] test_basic_match")


def test_cancel():
    """Test cancelling a resting order."""
    engine = ex.MatchingEngine()

    order = ex.Order()
    order.id = 10
    order.side = ex.Side.Buy
    order.price = 9500
    order.stop_price = 0
    order.peg_offset = 0
    order.quantity = 100
    order.filled_quantity = 0
    order.visible_quantity = 0
    order.hidden_quantity = 0
    order.type = ex.OrderType.Limit
    order.tif = ex.TimeInForce.GTC
    order.timestamp = 1

    engine.submit(order)

    result = engine.cancel(10)
    assert result == ex.CancelResult.Success

    result = engine.cancel(10)
    assert result == ex.CancelResult.OrderNotFound

    result = engine.cancel(999)
    assert result == ex.CancelResult.OrderNotFound
    print("  [PASS] test_cancel")


def test_book_access():
    """Test read-only access to the order book."""
    engine = ex.MatchingEngine()

    order = ex.Order()
    order.id = 1
    order.side = ex.Side.Buy
    order.price = 9800
    order.stop_price = 0
    order.peg_offset = 0
    order.quantity = 100
    order.filled_quantity = 0
    order.visible_quantity = 0
    order.hidden_quantity = 0
    order.type = ex.OrderType.Limit
    order.tif = ex.TimeInForce.GTC
    order.timestamp = 1

    engine.submit(order)

    book = engine.book()
    assert book.bid_depth() == 1
    assert book.ask_depth() == 0
    print("  [PASS] test_book_access")


def test_phase_control():
    """Test auction phase control."""
    engine = ex.MatchingEngine()
    assert engine.phase() == ex.Phase.Continuous

    engine.set_phase(ex.Phase.PreOpen)
    assert engine.phase() == ex.Phase.PreOpen

    # In PreOpen, orders are collected but not matched
    sell = ex.Order()
    sell.id = 1
    sell.side = ex.Side.Sell
    sell.price = 10000
    sell.stop_price = 0
    sell.peg_offset = 0
    sell.quantity = 50
    sell.filled_quantity = 0
    sell.visible_quantity = 0
    sell.hidden_quantity = 0
    sell.type = ex.OrderType.Limit
    sell.tif = ex.TimeInForce.GTC
    sell.timestamp = 1

    buy = ex.Order()
    buy.id = 2
    buy.side = ex.Side.Buy
    buy.price = 10000
    buy.stop_price = 0
    buy.peg_offset = 0
    buy.quantity = 50
    buy.filled_quantity = 0
    buy.visible_quantity = 0
    buy.hidden_quantity = 0
    buy.type = ex.OrderType.Limit
    buy.tif = ex.TimeInForce.GTC
    buy.timestamp = 2

    fills = engine.submit(sell)
    assert len(fills) == 0
    fills = engine.submit(buy)
    assert len(fills) == 0  # No matching in PreOpen

    # Uncross to execute auction
    fills = engine.uncross()
    assert len(fills) == 1
    assert fills[0].price == 10000
    assert fills[0].quantity == 50
    assert engine.phase() == ex.Phase.Continuous
    print("  [PASS] test_phase_control")


def test_ioc_order():
    """Test IOC order that partially fills."""
    engine = ex.MatchingEngine()

    # Place a small sell
    sell = ex.Order()
    sell.id = 1
    sell.side = ex.Side.Sell
    sell.price = 10000
    sell.stop_price = 0
    sell.peg_offset = 0
    sell.quantity = 30
    sell.filled_quantity = 0
    sell.visible_quantity = 0
    sell.hidden_quantity = 0
    sell.type = ex.OrderType.Limit
    sell.tif = ex.TimeInForce.GTC
    sell.timestamp = 1
    engine.submit(sell)

    # IOC buy for more than available
    buy = ex.Order()
    buy.id = 2
    buy.side = ex.Side.Buy
    buy.price = 10000
    buy.stop_price = 0
    buy.peg_offset = 0
    buy.quantity = 100
    buy.filled_quantity = 0
    buy.visible_quantity = 0
    buy.hidden_quantity = 0
    buy.type = ex.OrderType.Limit
    buy.tif = ex.TimeInForce.IOC
    buy.timestamp = 2

    fills = engine.submit(buy)
    assert len(fills) == 1
    assert fills[0].quantity == 30
    # IOC remainder should be cancelled, not resting on book
    assert engine.book().bid_depth() == 0
    print("  [PASS] test_ioc_order")


if __name__ == "__main__":
    print("Running Python binding tests...")
    test_enums()
    test_order_creation()
    test_basic_match()
    test_cancel()
    test_book_access()
    test_phase_control()
    test_ioc_order()
    print("\nAll Python binding tests passed!")
