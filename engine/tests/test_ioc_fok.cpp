// engine/tests/test_ioc_fok.cpp
#include <gtest/gtest.h>
#include "matching_engine.hpp"

using namespace exsim;

class IOCFOKTest : public ::testing::Test {
protected:
    MatchingEngine engine;
    uint64_t next_id = 1;
    uint64_t ts = 1000;

    Order make_limit(Side side, Price price, Quantity qty, TimeInForce tif = TimeInForce::GTC) {
        Order o{};
        o.id = next_id++;
        o.side = side;
        o.price = price;
        o.quantity = qty;
        o.filled_quantity = 0;
        o.type = OrderType::Limit;
        o.tif = tif;
        o.timestamp = ts++;
        return o;
    }
};

TEST_F(IOCFOKTest, IOCPartialFillCancelsRemainder) {
    // Resting sell of 30
    auto sell = make_limit(Side::Sell, 10000, 30);
    engine.submit(sell);

    // IOC buy of 50 — should fill 30, cancel remaining 20
    auto buy = make_limit(Side::Buy, 10000, 50, TimeInForce::IOC);
    auto fills = engine.submit(buy);

    EXPECT_EQ(fills.size(), 1);
    EXPECT_EQ(fills[0].quantity, 30);
    // Nothing should rest on the book
    EXPECT_EQ(engine.book().best_bid(), nullptr);
}

TEST_F(IOCFOKTest, IOCNoMatchCancels) {
    // IOC buy with no sells available
    auto buy = make_limit(Side::Buy, 10000, 50, TimeInForce::IOC);
    auto fills = engine.submit(buy);

    EXPECT_TRUE(fills.empty());
    EXPECT_EQ(engine.book().best_bid(), nullptr);
}

TEST_F(IOCFOKTest, IOCFullFill) {
    // Resting sell of 50
    auto sell = make_limit(Side::Sell, 10000, 50);
    engine.submit(sell);

    // IOC buy of 50 — full fill, nothing to cancel
    auto buy = make_limit(Side::Buy, 10000, 50, TimeInForce::IOC);
    auto fills = engine.submit(buy);

    EXPECT_EQ(fills.size(), 1);
    EXPECT_EQ(fills[0].quantity, 50);
    EXPECT_EQ(engine.book().best_bid(), nullptr);
    EXPECT_EQ(engine.book().best_ask(), nullptr);
}

TEST_F(IOCFOKTest, FOKFullFill) {
    // Resting sell of 50
    auto sell = make_limit(Side::Sell, 10000, 50);
    engine.submit(sell);

    // FOK buy of 50 — full qty available, should fill
    auto buy = make_limit(Side::Buy, 10000, 50, TimeInForce::FOK);
    auto fills = engine.submit(buy);

    EXPECT_EQ(fills.size(), 1);
    EXPECT_EQ(fills[0].quantity, 50);
}

TEST_F(IOCFOKTest, FOKRejectsIfInsufficientQuantity) {
    // Resting sell of 30
    auto sell = make_limit(Side::Sell, 10000, 30);
    engine.submit(sell);

    // FOK buy of 50 — only 30 available, should reject entirely
    auto buy = make_limit(Side::Buy, 10000, 50, TimeInForce::FOK);
    auto fills = engine.submit(buy);

    EXPECT_TRUE(fills.empty());
    // The resting sell should still be there (untouched)
    ASSERT_NE(engine.book().best_ask(), nullptr);
    EXPECT_EQ(engine.book().best_ask()->total_quantity, 30);
}

TEST_F(IOCFOKTest, FOKRejectsIfNoLiquidity) {
    auto buy = make_limit(Side::Buy, 10000, 50, TimeInForce::FOK);
    auto fills = engine.submit(buy);

    EXPECT_TRUE(fills.empty());
    EXPECT_EQ(engine.book().best_bid(), nullptr);
}

TEST_F(IOCFOKTest, FOKFillAcrossMultiplePriceLevels) {
    // Resting sells at different prices
    auto sell1 = make_limit(Side::Sell, 10000, 20);
    engine.submit(sell1);
    auto sell2 = make_limit(Side::Sell, 10100, 30);
    engine.submit(sell2);

    // FOK buy of 50 at price 10100 — 20 + 30 = 50, should fill
    auto buy = make_limit(Side::Buy, 10100, 50, TimeInForce::FOK);
    auto fills = engine.submit(buy);

    EXPECT_EQ(fills.size(), 2);
    Quantity total_filled = 0;
    for (const auto& f : fills) total_filled += f.quantity;
    EXPECT_EQ(total_filled, 50);
}

TEST_F(IOCFOKTest, FOKRejectsAcrossMultiplePriceLevelsInsufficientQty) {
    // Resting sells: 20 at 10000, 20 at 10100
    auto sell1 = make_limit(Side::Sell, 10000, 20);
    engine.submit(sell1);
    auto sell2 = make_limit(Side::Sell, 10100, 20);
    engine.submit(sell2);

    // FOK buy of 50 at price 10100 — only 40 available, reject
    auto buy = make_limit(Side::Buy, 10100, 50, TimeInForce::FOK);
    auto fills = engine.submit(buy);

    EXPECT_TRUE(fills.empty());
    // Both price levels untouched
    EXPECT_EQ(engine.book().ask_depth(), 2);
}

TEST_F(IOCFOKTest, FOKSellSide) {
    // Resting buy of 50
    auto bid = make_limit(Side::Buy, 10000, 50);
    engine.submit(bid);

    // FOK sell of 50 — full qty available, should fill
    auto sell = make_limit(Side::Sell, 10000, 50, TimeInForce::FOK);
    auto fills = engine.submit(sell);

    EXPECT_EQ(fills.size(), 1);
    EXPECT_EQ(fills[0].quantity, 50);
}

TEST_F(IOCFOKTest, FOKSellRejectsInsufficientQty) {
    // Resting buy of 30
    auto bid = make_limit(Side::Buy, 10000, 30);
    engine.submit(bid);

    // FOK sell of 50 — only 30 available, reject
    auto sell = make_limit(Side::Sell, 10000, 50, TimeInForce::FOK);
    auto fills = engine.submit(sell);

    EXPECT_TRUE(fills.empty());
    ASSERT_NE(engine.book().best_bid(), nullptr);
    EXPECT_EQ(engine.book().best_bid()->total_quantity, 30);
}

TEST_F(IOCFOKTest, IOCSellPartialFill) {
    // Resting buy of 30
    auto bid = make_limit(Side::Buy, 10000, 30);
    engine.submit(bid);

    // IOC sell of 50 — should fill 30, cancel remaining
    auto sell = make_limit(Side::Sell, 10000, 50, TimeInForce::IOC);
    auto fills = engine.submit(sell);

    EXPECT_EQ(fills.size(), 1);
    EXPECT_EQ(fills[0].quantity, 30);
    EXPECT_EQ(engine.book().best_ask(), nullptr);
}
