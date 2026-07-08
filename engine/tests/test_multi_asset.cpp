// engine/tests/test_multi_asset.cpp
#include <gtest/gtest.h>
#include "multi_asset_engine.hpp"

using namespace exsim;

namespace {

Order make_order(OrderId id, Side side, Price price, Quantity qty, Timestamp ts = 1000) {
    Order o{};
    o.id = id;
    o.side = side;
    o.price = price;
    o.quantity = qty;
    o.filled_quantity = 0;
    o.visible_quantity = 0;
    o.hidden_quantity = 0;
    o.type = OrderType::Limit;
    o.tif = TimeInForce::GTC;
    o.timestamp = ts;
    return o;
}

} // anonymous namespace

TEST(MultiAssetEngine, OrdersOnDifferentSymbolsDontInteract) {
    MultiAssetEngine engine;

    // Place a buy on symbol 1
    auto buy = make_order(1, Side::Buy, 100, 10);
    auto fills = engine.submit(1, buy);
    EXPECT_TRUE(fills.empty());

    // Place a sell on symbol 2 at the same price - should NOT match
    auto sell = make_order(2, Side::Sell, 100, 10);
    fills = engine.submit(2, sell);
    EXPECT_TRUE(fills.empty());

    // Verify both books have resting orders
    EXPECT_EQ(engine.get_book(1).book().bid_depth(), 1u);
    EXPECT_EQ(engine.get_book(2).book().ask_depth(), 1u);
}

TEST(MultiAssetEngine, FillsOnlyOccurWithinSameSymbol) {
    MultiAssetEngine engine;

    // Place a buy on symbol 1
    auto buy = make_order(1, Side::Buy, 100, 10);
    engine.submit(1, buy);

    // Place a sell on symbol 1 that should match
    auto sell = make_order(2, Side::Sell, 100, 10);
    auto fills = engine.submit(1, sell);
    EXPECT_EQ(fills.size(), 1u);
    EXPECT_EQ(fills[0].price, 100);
    EXPECT_EQ(fills[0].quantity, 10u);
}

TEST(MultiAssetEngine, CancelRoutesToCorrectBook) {
    MultiAssetEngine engine;

    // Place orders on different symbols
    auto order1 = make_order(100, Side::Buy, 50, 5);
    engine.submit(1, order1);

    auto order2 = make_order(200, Side::Buy, 60, 5);
    engine.submit(2, order2);

    // Cancel order on symbol 1
    auto result = engine.cancel(100);
    EXPECT_EQ(result, CancelResult::Success);

    // Verify symbol 1 book is empty, symbol 2 still has order
    EXPECT_EQ(engine.get_book(1).book().bid_depth(), 0u);
    EXPECT_EQ(engine.get_book(2).book().bid_depth(), 1u);
}

TEST(MultiAssetEngine, CancelUnknownOrderReturnsNotFound) {
    MultiAssetEngine engine;

    auto result = engine.cancel(99999);
    EXPECT_EQ(result, CancelResult::OrderNotFound);
}

TEST(MultiAssetEngine, MultipleSymbolsActiveSimultaneously) {
    MultiAssetEngine engine;

    // Set up order books on 5 different symbols
    for (uint32_t sym = 1; sym <= 5; sym++) {
        auto buy = make_order(sym * 100, Side::Buy, 100 + sym, 10);
        engine.submit(sym, buy);
        auto sell = make_order(sym * 100 + 1, Side::Sell, 200 + sym, 10);
        engine.submit(sym, sell);
    }

    auto syms = engine.symbols();
    EXPECT_EQ(syms.size(), 5u);

    // Verify each symbol has correct order book state
    for (uint32_t sym = 1; sym <= 5; sym++) {
        auto& book = engine.get_book(sym).book();
        EXPECT_EQ(book.bid_depth(), 1u);
        EXPECT_EQ(book.ask_depth(), 1u);
    }
}

TEST(MultiAssetEngine, SymbolsReturnsAllActiveSymbols) {
    MultiAssetEngine engine;

    // Initially no symbols
    EXPECT_TRUE(engine.symbols().empty());

    // Add orders to three symbols
    auto o1 = make_order(1, Side::Buy, 100, 10);
    engine.submit(10, o1);
    auto o2 = make_order(2, Side::Buy, 100, 10);
    engine.submit(20, o2);
    auto o3 = make_order(3, Side::Buy, 100, 10);
    engine.submit(30, o3);

    auto syms = engine.symbols();
    EXPECT_EQ(syms.size(), 3u);

    // All three should be present (order not guaranteed)
    std::sort(syms.begin(), syms.end());
    EXPECT_EQ(syms[0], 10u);
    EXPECT_EQ(syms[1], 20u);
    EXPECT_EQ(syms[2], 30u);
}

TEST(MultiAssetEngine, GetBookCreatesNewBookIfNotExists) {
    MultiAssetEngine engine;

    // get_book on a non-existent symbol should create it
    auto& book = engine.get_book(42);
    EXPECT_EQ(book.book().bid_depth(), 0u);
    EXPECT_EQ(book.book().ask_depth(), 0u);

    // Now it should show up in symbols
    auto syms = engine.symbols();
    EXPECT_EQ(syms.size(), 1u);
    EXPECT_EQ(syms[0], 42u);
}

TEST(MultiAssetEngine, CrossSymbolIsolationWithMatching) {
    MultiAssetEngine engine;

    // Symbol 1: create a filled trade
    auto buy1 = make_order(1, Side::Buy, 100, 10);
    engine.submit(1, buy1);
    auto sell1 = make_order(2, Side::Sell, 100, 10);
    auto fills1 = engine.submit(1, sell1);
    EXPECT_EQ(fills1.size(), 1u);

    // Symbol 2: same price orders but independent
    auto buy2 = make_order(3, Side::Buy, 100, 10);
    engine.submit(2, buy2);

    // Symbol 2 should still have resting order (not matched by symbol 1 trade)
    EXPECT_EQ(engine.get_book(2).book().bid_depth(), 1u);
    EXPECT_EQ(engine.get_book(1).book().bid_depth(), 0u);
    EXPECT_EQ(engine.get_book(1).book().ask_depth(), 0u);
}
