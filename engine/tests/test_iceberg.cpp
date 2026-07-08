// engine/tests/test_iceberg.cpp
#include <gtest/gtest.h>
#include "matching_engine.hpp"

using namespace exsim;

class IcebergTest : public ::testing::Test {
protected:
    MatchingEngine engine;
    uint64_t next_id = 1;
    uint64_t ts = 1000;

    Order make_iceberg(Side side, Price price, Quantity total, Quantity visible) {
        Order o{};
        o.id = next_id++;
        o.side = side;
        o.price = price;
        o.quantity = total;
        o.filled_quantity = 0;
        o.visible_quantity = visible;
        o.hidden_quantity = 0;
        o.type = OrderType::Limit;
        o.tif = TimeInForce::GTC;
        o.timestamp = ts++;
        return o;
    }

    Order make_limit(Side side, Price price, Quantity qty) {
        Order o{};
        o.id = next_id++;
        o.side = side;
        o.price = price;
        o.quantity = qty;
        o.filled_quantity = 0;
        o.visible_quantity = 0;
        o.hidden_quantity = 0;
        o.type = OrderType::Limit;
        o.tif = TimeInForce::GTC;
        o.timestamp = ts++;
        return o;
    }
};

TEST_F(IcebergTest, IcebergShowsOnlyVisibleQuantity) {
    auto iceberg = make_iceberg(Side::Sell, 10000, 100, 20);
    engine.submit(iceberg);

    // Book should show only the visible portion
    ASSERT_NE(engine.book().best_ask(), nullptr);
    EXPECT_EQ(engine.book().best_ask()->total_quantity, 20);
}

TEST_F(IcebergTest, IcebergRefillsAfterFill) {
    auto iceberg = make_iceberg(Side::Sell, 10000, 100, 20);
    engine.submit(iceberg);

    // Buy 20 — should fill the visible portion
    auto buy = make_limit(Side::Buy, 10000, 20);
    auto fills = engine.submit(buy);

    EXPECT_EQ(fills.size(), 1);
    EXPECT_EQ(fills[0].quantity, 20);

    // Iceberg should refill: show another 20
    ASSERT_NE(engine.book().best_ask(), nullptr);
    EXPECT_EQ(engine.book().best_ask()->total_quantity, 20);
}

TEST_F(IcebergTest, IcebergLastSliceSmallerThanVisible) {
    // Total 50, visible 20: slices are 20, 20, 10
    auto iceberg = make_iceberg(Side::Sell, 10000, 50, 20);
    engine.submit(iceberg);

    // Fill first slice (20)
    auto buy1 = make_limit(Side::Buy, 10000, 20);
    engine.submit(buy1);
    // Fill second slice (20)
    auto buy2 = make_limit(Side::Buy, 10000, 20);
    engine.submit(buy2);

    // Third slice should be 10 (remaining)
    ASSERT_NE(engine.book().best_ask(), nullptr);
    EXPECT_EQ(engine.book().best_ask()->total_quantity, 10);

    // Fill last slice
    auto buy3 = make_limit(Side::Buy, 10000, 10);
    engine.submit(buy3);
    EXPECT_EQ(engine.book().best_ask(), nullptr);
}

TEST_F(IcebergTest, IcebergLosesPriorityOnRefill) {
    // Iceberg at 10000, then a regular order at 10000
    auto iceberg = make_iceberg(Side::Sell, 10000, 100, 20);
    engine.submit(iceberg);
    auto regular = make_limit(Side::Sell, 10000, 30);
    engine.submit(regular);

    // Buy 20: should match iceberg first (it was there first)
    auto buy1 = make_limit(Side::Buy, 10000, 20);
    auto fills1 = engine.submit(buy1);
    EXPECT_EQ(fills1[0].maker_order_id, iceberg.id);

    // After refill, iceberg goes to back of queue at this price
    // Buy 30: should match the regular order first
    auto buy2 = make_limit(Side::Buy, 10000, 30);
    auto fills2 = engine.submit(buy2);
    EXPECT_EQ(fills2[0].maker_order_id, regular.id);
}
