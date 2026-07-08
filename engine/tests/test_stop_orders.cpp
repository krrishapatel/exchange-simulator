// engine/tests/test_stop_orders.cpp
#include <gtest/gtest.h>
#include "matching_engine.hpp"

using namespace exsim;

class StopOrderTest : public ::testing::Test {
protected:
    MatchingEngine engine;
    uint64_t next_id = 1;
    uint64_t ts = 1000;

    Order make_limit(Side side, Price price, Quantity qty) {
        Order o{};
        o.id = next_id++;
        o.side = side;
        o.price = price;
        o.stop_price = 0;
        o.quantity = qty;
        o.filled_quantity = 0;
        o.visible_quantity = 0;
        o.hidden_quantity = 0;
        o.type = OrderType::Limit;
        o.tif = TimeInForce::GTC;
        o.timestamp = ts++;
        return o;
    }

    Order make_stop(Side side, Price stop_price, Quantity qty) {
        Order o{};
        o.id = next_id++;
        o.side = side;
        o.price = 0;
        o.stop_price = stop_price;
        o.quantity = qty;
        o.filled_quantity = 0;
        o.visible_quantity = 0;
        o.hidden_quantity = 0;
        o.type = OrderType::Stop;
        o.tif = TimeInForce::IOC;
        o.timestamp = ts++;
        return o;
    }
};

TEST_F(StopOrderTest, StopBuyTriggeredWhenPriceRises) {
    // Place a resting sell at 10100
    auto sell = make_limit(Side::Sell, 10100, 50);
    engine.submit(sell);

    // Place a stop buy that triggers at 10050
    auto stop = make_stop(Side::Buy, 10050, 30);
    engine.submit(stop);

    // Verify stop is stored
    EXPECT_EQ(engine.stop_order_count(), 1u);

    // Create a trade at 10100 (above stop price) by placing matching orders
    auto sell2 = make_limit(Side::Sell, 10000, 20);
    engine.submit(sell2);
    auto buy = make_limit(Side::Buy, 10000, 20);
    auto fills = engine.submit(buy);

    // The trade at 10000 triggers the stop buy (10000 >= 10050? No!)
    // Actually 10000 < 10050, so the stop should NOT trigger here.
    // Let's create a trade at 10050+ instead.
    // First, clear up - the stop should still be there
    EXPECT_EQ(engine.stop_order_count(), 1u);

    // Now create a trade at 10100 (above stop_price of 10050)
    auto sell3 = make_limit(Side::Sell, 10100, 10);
    engine.submit(sell3);
    auto buy2 = make_limit(Side::Buy, 10100, 10);
    auto fills2 = engine.submit(buy2);

    // Trade at 10100 >= 10050, so stop buy should trigger
    // The triggered stop becomes a market buy and fills against resting sell at 10100
    EXPECT_EQ(engine.stop_order_count(), 0u);

    // The fills should include: the buy2 vs sell3 trade, plus the triggered stop vs original sell
    // fills2 should have the buy2 fill + triggered stop fills
    ASSERT_GE(fills2.size(), 2u);
    // First fill: buy2 (10 qty) vs sell3 at 10100
    EXPECT_EQ(fills2[0].quantity, 10u);
    EXPECT_EQ(fills2[0].price, 10100);
    // Second fill: triggered stop (30 qty) vs original sell at 10100
    EXPECT_EQ(fills2[1].quantity, 30u);
    EXPECT_EQ(fills2[1].price, 10100);
}

TEST_F(StopOrderTest, StopSellTriggeredWhenPriceDrops) {
    // Place a resting buy at 9900
    auto buy = make_limit(Side::Buy, 9900, 50);
    engine.submit(buy);

    // Place a stop sell that triggers at 9950 (triggers when price drops to or below 9950)
    auto stop = make_stop(Side::Sell, 9950, 30);
    engine.submit(stop);

    EXPECT_EQ(engine.stop_order_count(), 1u);

    // Create a trade at 9950 (at stop price)
    auto buy2 = make_limit(Side::Buy, 9950, 10);
    engine.submit(buy2);
    auto sell = make_limit(Side::Sell, 9950, 10);
    auto fills = engine.submit(sell);

    // Trade at 9950 <= 9950 (stop_price), so stop sell should trigger
    // The triggered stop becomes a market sell and fills against resting buy at 9900
    EXPECT_EQ(engine.stop_order_count(), 0u);

    // fills include: sell vs buy2 at 9950, then triggered stop vs buy at 9900
    ASSERT_GE(fills.size(), 2u);
    EXPECT_EQ(fills[0].quantity, 10u);
    EXPECT_EQ(fills[0].price, 9950);
    EXPECT_EQ(fills[1].quantity, 30u);
    EXPECT_EQ(fills[1].price, 9900);
}

TEST_F(StopOrderTest, StopNotTriggeredIfPriceNotCrossed) {
    // Place a resting sell at 10100
    auto sell = make_limit(Side::Sell, 10100, 50);
    engine.submit(sell);

    // Place a stop buy that triggers at 10200 (needs price to rise to 10200+)
    auto stop = make_stop(Side::Buy, 10200, 30);
    engine.submit(stop);

    EXPECT_EQ(engine.stop_order_count(), 1u);

    // Trade at 10000 - below stop price, should NOT trigger
    auto sell2 = make_limit(Side::Sell, 10000, 20);
    engine.submit(sell2);
    auto buy = make_limit(Side::Buy, 10000, 20);
    engine.submit(buy);

    // Stop should still be dormant
    EXPECT_EQ(engine.stop_order_count(), 1u);

    // The resting sell at 10100 should still be untouched
    ASSERT_NE(engine.book().best_ask(), nullptr);
    EXPECT_EQ(engine.book().best_ask()->total_quantity, 50u);
}

TEST_F(StopOrderTest, CascadingStops) {
    // Setup: multiple stop orders that cascade
    // Sell resting at 10200 (qty 100) and 10300 (qty 100)
    auto sell1 = make_limit(Side::Sell, 10200, 100);
    engine.submit(sell1);
    auto sell2 = make_limit(Side::Sell, 10300, 100);
    engine.submit(sell2);

    // Stop buy #1: triggers at 10100
    auto stop1 = make_stop(Side::Buy, 10100, 50);
    engine.submit(stop1);

    // Stop buy #2: triggers at 10200 (will cascade when stop1 fills at 10200)
    auto stop2 = make_stop(Side::Buy, 10200, 40);
    engine.submit(stop2);

    EXPECT_EQ(engine.stop_order_count(), 2u);

    // Create a trade at 10100 to trigger the first stop
    auto sell3 = make_limit(Side::Sell, 10100, 10);
    engine.submit(sell3);
    auto buy = make_limit(Side::Buy, 10100, 10);
    auto fills = engine.submit(buy);

    // First trade at 10100 triggers stop1 (10100 >= 10100)
    // stop1 becomes market buy, fills 50 at 10200 (from sell1)
    // That fill at 10200 triggers stop2 (10200 >= 10200)
    // stop2 becomes market buy, fills 40 at 10200 (from sell1, 50 remaining)
    EXPECT_EQ(engine.stop_order_count(), 0u);

    // Total fills: buy vs sell3 (10 @ 10100) + stop1 vs sell1 (50 @ 10200) + stop2 vs sell1 (40 @ 10200)
    ASSERT_EQ(fills.size(), 3u);
    EXPECT_EQ(fills[0].quantity, 10u);
    EXPECT_EQ(fills[0].price, 10100);
    EXPECT_EQ(fills[1].quantity, 50u);
    EXPECT_EQ(fills[1].price, 10200);
    EXPECT_EQ(fills[2].quantity, 40u);
    EXPECT_EQ(fills[2].price, 10200);
}

TEST_F(StopOrderTest, StopOrderDoesNotRestOnBook) {
    // A stop order should not appear on the order book
    auto stop = make_stop(Side::Buy, 10000, 100);
    engine.submit(stop);

    EXPECT_EQ(engine.book().best_bid(), nullptr);
    EXPECT_EQ(engine.book().best_ask(), nullptr);
    EXPECT_EQ(engine.stop_order_count(), 1u);
}

TEST_F(StopOrderTest, StopSellNotTriggeredByHigherPrice) {
    // Stop sell at 9900 should NOT trigger if price trades at 10000 (above stop)
    auto buy = make_limit(Side::Buy, 9800, 50);
    engine.submit(buy);

    auto stop = make_stop(Side::Sell, 9900, 30);
    engine.submit(stop);

    // Trade at 10000 (above stop price of 9900) - should NOT trigger stop sell
    auto buy2 = make_limit(Side::Buy, 10000, 10);
    engine.submit(buy2);
    auto sell = make_limit(Side::Sell, 10000, 10);
    engine.submit(sell);

    // Stop should still be dormant
    EXPECT_EQ(engine.stop_order_count(), 1u);
}
