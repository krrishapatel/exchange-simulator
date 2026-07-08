// engine/tests/test_auction.cpp
#include <gtest/gtest.h>
#include "matching_engine.hpp"

using namespace exsim;

class AuctionTest : public ::testing::Test {
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

TEST_F(AuctionTest, PreOpenAcceptsOrdersNoMatching) {
    engine.set_phase(Phase::PreOpen);
    auto buy = make_limit(Side::Buy, 10000, 50);
    engine.submit(buy);
    auto sell = make_limit(Side::Sell, 9900, 30);
    engine.submit(sell);

    // Crossing orders should NOT match during pre-open
    EXPECT_NE(engine.book().best_bid(), nullptr);
    EXPECT_NE(engine.book().best_ask(), nullptr);
    EXPECT_EQ(engine.book().best_bid()->price, 10000);
    EXPECT_EQ(engine.book().best_ask()->price, 9900);
}

TEST_F(AuctionTest, PreOpenReturnsNoFills) {
    engine.set_phase(Phase::PreOpen);
    auto buy = make_limit(Side::Buy, 10000, 50);
    auto fills = engine.submit(buy);
    EXPECT_TRUE(fills.empty());

    auto sell = make_limit(Side::Sell, 9900, 30);
    fills = engine.submit(sell);
    EXPECT_TRUE(fills.empty());
}

TEST_F(AuctionTest, UncrossFindsEquilibriumPrice) {
    engine.set_phase(Phase::PreOpen);
    auto b1 = make_limit(Side::Buy, 10200, 30);
    engine.submit(b1);
    auto b2 = make_limit(Side::Buy, 10100, 50);
    engine.submit(b2);
    auto s1 = make_limit(Side::Sell, 9900, 40);
    engine.submit(s1);
    auto s2 = make_limit(Side::Sell, 10000, 20);
    engine.submit(s2);

    auto fills = engine.uncross();
    // Total buy volume at 10000: buy@10200(30) + buy@10100(50) = 80
    // Total sell volume at 10000: sell@9900(40) + sell@10000(20) = 60
    // Executable volume at 10000 = min(80, 60) = 60
    //
    // Total buy volume at 10100: buy@10200(30) + buy@10100(50) = 80
    // Total sell volume at 10100: sell@9900(40) + sell@10000(20) = 60
    // Executable volume at 10100 = min(80, 60) = 60
    //
    // Total buy volume at 10200: buy@10200(30) = 30
    // Total sell volume at 10200: sell@9900(40) + sell@10000(20) = 60
    // Executable volume at 10200 = min(30, 60) = 30
    //
    // Total buy volume at 9900: all buys = 80
    // Total sell volume at 9900: sell@9900(40) = 40
    // Executable volume at 9900 = min(80, 40) = 40
    //
    // Max executable volume is 60, at prices 10000 or 10100
    EXPECT_FALSE(fills.empty());

    // Total fill quantity should equal executable volume
    Quantity total_filled = 0;
    for (const auto& f : fills) {
        total_filled += f.quantity;
    }
    EXPECT_EQ(total_filled, 60u);
}

TEST_F(AuctionTest, UncrossExecutesAtSinglePrice) {
    engine.set_phase(Phase::PreOpen);
    auto b1 = make_limit(Side::Buy, 10200, 30);
    engine.submit(b1);
    auto b2 = make_limit(Side::Buy, 10100, 50);
    engine.submit(b2);
    auto s1 = make_limit(Side::Sell, 9900, 40);
    engine.submit(s1);
    auto s2 = make_limit(Side::Sell, 10000, 20);
    engine.submit(s2);

    auto fills = engine.uncross();
    ASSERT_FALSE(fills.empty());

    // All fills must be at the same equilibrium price
    Price auction_price = fills[0].price;
    for (const auto& f : fills) {
        EXPECT_EQ(f.price, auction_price);
    }
}

TEST_F(AuctionTest, UncrossSwitchesToContinuous) {
    engine.set_phase(Phase::PreOpen);
    auto b1 = make_limit(Side::Buy, 10000, 50);
    engine.submit(b1);
    auto s1 = make_limit(Side::Sell, 9900, 30);
    engine.submit(s1);

    engine.uncross();
    EXPECT_EQ(engine.phase(), Phase::Continuous);
}

TEST_F(AuctionTest, EmptyBookUncrossProducesNoFills) {
    engine.set_phase(Phase::PreOpen);
    auto fills = engine.uncross();
    EXPECT_TRUE(fills.empty());
    EXPECT_EQ(engine.phase(), Phase::Continuous);
}

TEST_F(AuctionTest, ContinuousPhaseMatchesNormally) {
    engine.set_phase(Phase::Continuous);
    auto sell = make_limit(Side::Sell, 10000, 50);
    engine.submit(sell);
    auto buy = make_limit(Side::Buy, 10000, 50);
    auto fills = engine.submit(buy);
    EXPECT_EQ(fills.size(), 1u);
    EXPECT_EQ(fills[0].quantity, 50u);
}

TEST_F(AuctionTest, NonCrossingBookUncrossProducesNoFills) {
    engine.set_phase(Phase::PreOpen);
    // Bids below asks - no crossing
    auto b1 = make_limit(Side::Buy, 9800, 50);
    engine.submit(b1);
    auto s1 = make_limit(Side::Sell, 10200, 30);
    engine.submit(s1);

    auto fills = engine.uncross();
    EXPECT_TRUE(fills.empty());
    EXPECT_EQ(engine.phase(), Phase::Continuous);
}

TEST_F(AuctionTest, UncrossPartialFillLeavesResidual) {
    engine.set_phase(Phase::PreOpen);
    // Buy 100 @ 10000, Sell 60 @ 9900
    auto b1 = make_limit(Side::Buy, 10000, 100);
    engine.submit(b1);
    auto s1 = make_limit(Side::Sell, 9900, 60);
    engine.submit(s1);

    auto fills = engine.uncross();
    Quantity total = 0;
    for (const auto& f : fills) {
        total += f.quantity;
    }
    EXPECT_EQ(total, 60u);

    // Residual buy of 40 should remain on book
    EXPECT_NE(engine.book().best_bid(), nullptr);
    EXPECT_EQ(engine.book().best_bid()->total_quantity, 40u);
}

TEST_F(AuctionTest, UncrossMultiplePriceLevels) {
    engine.set_phase(Phase::PreOpen);
    // Multiple price levels on each side
    auto b1 = make_limit(Side::Buy, 10300, 10);
    engine.submit(b1);
    auto b2 = make_limit(Side::Buy, 10200, 20);
    engine.submit(b2);
    auto b3 = make_limit(Side::Buy, 10100, 30);
    engine.submit(b3);
    auto s1 = make_limit(Side::Sell, 9900, 15);
    engine.submit(s1);
    auto s2 = make_limit(Side::Sell, 10000, 25);
    engine.submit(s2);
    auto s3 = make_limit(Side::Sell, 10100, 35);
    engine.submit(s3);

    auto fills = engine.uncross();
    ASSERT_FALSE(fills.empty());

    // All fills at same price
    Price auction_price = fills[0].price;
    for (const auto& f : fills) {
        EXPECT_EQ(f.price, auction_price);
    }

    // Verify total volume
    Quantity total = 0;
    for (const auto& f : fills) {
        total += f.quantity;
    }
    // At price 10100: buy_vol = 10+20+30=60, sell_vol = 15+25+35=75, exec=60
    // At price 10000: buy_vol = 10+20+30=60, sell_vol = 15+25=40, exec=40
    // At price 10200: buy_vol = 10+20=30, sell_vol = 15+25+35=75, exec=30
    // Max is at 10100: exec=60
    EXPECT_EQ(total, 60u);
}

TEST_F(AuctionTest, AfterUncrossContinuousWorks) {
    engine.set_phase(Phase::PreOpen);
    auto b1 = make_limit(Side::Buy, 10000, 50);
    engine.submit(b1);
    auto s1 = make_limit(Side::Sell, 9900, 50);
    engine.submit(s1);

    engine.uncross();
    EXPECT_EQ(engine.phase(), Phase::Continuous);

    // Now normal matching should work
    auto sell = make_limit(Side::Sell, 10500, 20);
    engine.submit(sell);
    auto buy = make_limit(Side::Buy, 10500, 20);
    auto fills = engine.submit(buy);
    EXPECT_EQ(fills.size(), 1u);
    EXPECT_EQ(fills[0].quantity, 20u);
}
