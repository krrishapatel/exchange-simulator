// engine/tests/test_matching_engine.cpp
#include <gtest/gtest.h>
#include "matching_engine.hpp"

using namespace exsim;

class MatchingEngineTest : public ::testing::Test {
protected:
    MatchingEngine engine;
    uint64_t next_id = 1;
    uint64_t ts = 1000;

    Order make_limit(Side side, Price price, Quantity qty) {
        Order o{};
        o.id = next_id++;
        o.side = side;
        o.price = price;
        o.quantity = qty;
        o.filled_quantity = 0;
        o.type = OrderType::Limit;
        o.tif = TimeInForce::GTC;
        o.timestamp = ts++;
        return o;
    }

    Order make_market(Side side, Quantity qty) {
        Order o{};
        o.id = next_id++;
        o.side = side;
        o.price = 0;
        o.quantity = qty;
        o.filled_quantity = 0;
        o.type = OrderType::Market;
        o.tif = TimeInForce::IOC;
        o.timestamp = ts++;
        return o;
    }
};

TEST_F(MatchingEngineTest, LimitOrderNoMatch) {
    auto buy = make_limit(Side::Buy, 10000, 50);
    auto fills = engine.submit(buy);
    EXPECT_TRUE(fills.empty());
    EXPECT_NE(engine.book().best_bid(), nullptr);
}

TEST_F(MatchingEngineTest, LimitOrderFullMatch) {
    auto sell = make_limit(Side::Sell, 10000, 50);
    engine.submit(sell);

    auto buy = make_limit(Side::Buy, 10000, 50);
    auto fills = engine.submit(buy);

    ASSERT_EQ(fills.size(), 1);
    EXPECT_EQ(fills[0].quantity, 50);
    EXPECT_EQ(fills[0].price, 10000);
    EXPECT_EQ(fills[0].maker_order_id, sell.id);
    EXPECT_EQ(fills[0].taker_order_id, buy.id);
    EXPECT_EQ(fills[0].aggressor_side, Side::Buy);
}

TEST_F(MatchingEngineTest, LimitOrderPartialMatch) {
    auto sell = make_limit(Side::Sell, 10000, 30);
    engine.submit(sell);

    auto buy = make_limit(Side::Buy, 10000, 50);
    auto fills = engine.submit(buy);

    ASSERT_EQ(fills.size(), 1);
    EXPECT_EQ(fills[0].quantity, 30);
    // Remaining 20 should rest on the book
    EXPECT_NE(engine.book().best_bid(), nullptr);
    EXPECT_EQ(engine.book().best_bid()->total_quantity, 20);
}

TEST_F(MatchingEngineTest, MarketOrderFullFill) {
    auto sell = make_limit(Side::Sell, 10000, 50);
    engine.submit(sell);

    auto buy_mkt = make_market(Side::Buy, 50);
    auto fills = engine.submit(buy_mkt);

    ASSERT_EQ(fills.size(), 1);
    EXPECT_EQ(fills[0].quantity, 50);
    EXPECT_EQ(fills[0].price, 10000);
}

TEST_F(MatchingEngineTest, MarketOrderNoLiquidity) {
    auto buy_mkt = make_market(Side::Buy, 50);
    auto fills = engine.submit(buy_mkt);
    // No fills, order cancelled (market orders don't rest)
    EXPECT_TRUE(fills.empty());
    EXPECT_EQ(engine.book().best_bid(), nullptr);
}

TEST_F(MatchingEngineTest, PriceTimePriorityMatching) {
    // Two sells at same price, first one should fill first
    auto s1 = make_limit(Side::Sell, 10000, 30);
    auto s2 = make_limit(Side::Sell, 10000, 30);
    engine.submit(s1);
    engine.submit(s2);

    auto buy = make_limit(Side::Buy, 10000, 40);
    auto fills = engine.submit(buy);

    // Should fill s1 fully (30), then s2 partially (10)
    ASSERT_EQ(fills.size(), 2);
    EXPECT_EQ(fills[0].maker_order_id, s1.id);
    EXPECT_EQ(fills[0].quantity, 30);
    EXPECT_EQ(fills[1].maker_order_id, s2.id);
    EXPECT_EQ(fills[1].quantity, 10);
}

TEST_F(MatchingEngineTest, BuyMatchesBestAsk) {
    // Buy at higher price matches the lowest ask
    auto s1 = make_limit(Side::Sell, 10200, 20);
    auto s2 = make_limit(Side::Sell, 10100, 30);
    engine.submit(s1);
    engine.submit(s2);

    auto buy = make_limit(Side::Buy, 10200, 25);
    auto fills = engine.submit(buy);

    // Should match against 10100 first (best ask)
    ASSERT_EQ(fills.size(), 1);
    EXPECT_EQ(fills[0].price, 10100);
    EXPECT_EQ(fills[0].quantity, 25);
}

TEST_F(MatchingEngineTest, CancelOrder) {
    auto sell = make_limit(Side::Sell, 10000, 50);
    engine.submit(sell);
    auto result = engine.cancel(sell.id);
    EXPECT_EQ(result, CancelResult::Success);
    EXPECT_EQ(engine.book().best_ask(), nullptr);
}
