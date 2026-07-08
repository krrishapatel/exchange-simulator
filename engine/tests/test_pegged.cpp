// engine/tests/test_pegged.cpp
#include <gtest/gtest.h>
#include "matching_engine.hpp"

using namespace exsim;

class PeggedTest : public ::testing::Test {
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
        o.peg_offset = 0;
        o.quantity = qty;
        o.filled_quantity = 0;
        o.visible_quantity = 0;
        o.hidden_quantity = 0;
        o.type = OrderType::Limit;
        o.tif = TimeInForce::GTC;
        o.timestamp = ts++;
        return o;
    }

    Order make_pegged(Side side, Price offset, Quantity qty) {
        Order o{};
        o.id = next_id++;
        o.side = side;
        o.price = 0;
        o.stop_price = 0;
        o.peg_offset = offset;
        o.quantity = qty;
        o.filled_quantity = 0;
        o.visible_quantity = 0;
        o.hidden_quantity = 0;
        o.type = OrderType::Pegged;
        o.tif = TimeInForce::GTC;
        o.timestamp = ts++;
        return o;
    }
};

TEST_F(PeggedTest, PeggedBuyRestsAtBestBidMinusOffset) {
    // Set up a market with best bid at 10000
    auto buy1 = make_limit(Side::Buy, 10000, 50);
    engine.submit(buy1);
    auto sell1 = make_limit(Side::Sell, 10200, 50);
    engine.submit(sell1);

    // Pegged buy with offset 10 (peg to best bid - 10)
    auto pegged = make_pegged(Side::Buy, 10, 30);
    engine.submit(pegged);

    // Pegged should rest at 10000 - 10 = 9990
    // The best bid is now the original order at 10000 (pegged at 9990 is lower)
    EXPECT_EQ(engine.pegged_order_count(), 1u);
    ASSERT_NE(engine.book().best_bid(), nullptr);
    EXPECT_EQ(engine.book().best_bid()->price, 10000);

    // Check that there's a bid level at 9990
    auto it = engine.book().bids_begin();
    ASSERT_NE(it, engine.book().bids_end());
    EXPECT_EQ(it->first, 10000);  // best bid
    ++it;
    ASSERT_NE(it, engine.book().bids_end());
    EXPECT_EQ(it->first, 9990);   // pegged order
    EXPECT_EQ(it->second.total_quantity, 30u);
}

TEST_F(PeggedTest, PeggedSellRestsAtBestAskPlusOffset) {
    // Set up a market with best ask at 10200
    auto buy1 = make_limit(Side::Buy, 10000, 50);
    engine.submit(buy1);
    auto sell1 = make_limit(Side::Sell, 10200, 50);
    engine.submit(sell1);

    // Pegged sell with offset 10 (peg to best ask + 10)
    auto pegged = make_pegged(Side::Sell, 10, 30);
    engine.submit(pegged);

    // Pegged should rest at 10200 + 10 = 10210
    EXPECT_EQ(engine.pegged_order_count(), 1u);
    ASSERT_NE(engine.book().best_ask(), nullptr);
    EXPECT_EQ(engine.book().best_ask()->price, 10200);

    // Check that there's an ask level at 10210
    auto it = engine.book().asks_begin();
    ASSERT_NE(it, engine.book().asks_end());
    EXPECT_EQ(it->first, 10200);  // best ask
    ++it;
    ASSERT_NE(it, engine.book().asks_end());
    EXPECT_EQ(it->first, 10210);  // pegged order
    EXPECT_EQ(it->second.total_quantity, 30u);
}

TEST_F(PeggedTest, PeggedBuyRepricesWhenReferencePriceChanges) {
    // Set up: best bid at 10000, best ask at 10200
    auto buy1 = make_limit(Side::Buy, 10000, 50);
    engine.submit(buy1);
    auto sell1 = make_limit(Side::Sell, 10200, 50);
    engine.submit(sell1);

    // Pegged buy with offset 10: rests at 10000 - 10 = 9990
    auto pegged = make_pegged(Side::Buy, 10, 30);
    engine.submit(pegged);

    // Verify initial placement
    {
        auto it = engine.book().bids_begin();
        ++it;
        ASSERT_NE(it, engine.book().bids_end());
        EXPECT_EQ(it->first, 9990);
    }

    // Now add a new best bid at 10100
    auto buy2 = make_limit(Side::Buy, 10100, 20);
    engine.submit(buy2);

    // The pegged order has NOT repriced yet (no match has occurred)
    // To trigger repricing, we need a match
    // Submit a sell that matches the buy at 10100
    auto sell2 = make_limit(Side::Sell, 10100, 20);
    auto fills = engine.submit(sell2);
    ASSERT_FALSE(fills.empty());

    // After the match, best bid reverts to 10000, so pegged should be at 10000 - 10 = 9990
    // But wait - the match consumed buy2 at 10100. Now best bid is 10000 again.
    // Pegged should stay at 9990.
    {
        auto it = engine.book().bids_begin();
        ASSERT_NE(it, engine.book().bids_end());
        EXPECT_EQ(it->first, 10000);
        ++it;
        ASSERT_NE(it, engine.book().bids_end());
        EXPECT_EQ(it->first, 9990);
        EXPECT_EQ(it->second.total_quantity, 30u);
    }
}

TEST_F(PeggedTest, PeggedBuyRepricesUpward) {
    // Set up: best bid at 10000, best ask at 10500
    auto buy1 = make_limit(Side::Buy, 10000, 50);
    engine.submit(buy1);
    auto sell1 = make_limit(Side::Sell, 10500, 50);
    engine.submit(sell1);

    // Pegged buy with offset 10: rests at 10000 - 10 = 9990
    auto pegged = make_pegged(Side::Buy, 10, 30);
    engine.submit(pegged);

    // Add a higher bid and then trigger a match to force reprice
    auto buy2 = make_limit(Side::Buy, 10200, 40);
    engine.submit(buy2);

    // Now best bid is 10200. We need a match to trigger repricing.
    // Place a sell at 10500 qty 10 and a buy that matches against existing sell at 10500
    auto buy3 = make_limit(Side::Buy, 10500, 10);
    auto fills = engine.submit(buy3);
    ASSERT_FALSE(fills.empty());

    // After match, best bid is 10200, so pegged should move to 10200 - 10 = 10190
    // Check: the pegged order should now be at price 10190
    bool found_10190 = false;
    for (auto it = engine.book().bids_begin(); it != engine.book().bids_end(); ++it) {
        if (it->first == 10190) {
            found_10190 = true;
            EXPECT_EQ(it->second.total_quantity, 30u);
        }
    }
    EXPECT_TRUE(found_10190) << "Pegged order should have repriced to 10190";
}

TEST_F(PeggedTest, PeggedBuyDoesNotCrossSpread) {
    // Set up: best bid at 10000, best ask at 10100
    auto buy1 = make_limit(Side::Buy, 10000, 50);
    engine.submit(buy1);
    auto sell1 = make_limit(Side::Sell, 10100, 50);
    engine.submit(sell1);

    // Pegged buy with negative offset (would put it above best bid, possibly crossing)
    // offset = -200 means price = 10000 - (-200) = 10200, which crosses ask at 10100
    // Should be capped at best_ask - 1 = 10099
    auto pegged = make_pegged(Side::Buy, -200, 30);
    engine.submit(pegged);

    EXPECT_EQ(engine.pegged_order_count(), 1u);

    // The pegged order should be capped at 10099 (best_ask - 1)
    bool found_10099 = false;
    for (auto it = engine.book().bids_begin(); it != engine.book().bids_end(); ++it) {
        if (it->first == 10099) {
            found_10099 = true;
            EXPECT_EQ(it->second.total_quantity, 30u);
        }
    }
    EXPECT_TRUE(found_10099) << "Pegged buy should be capped at best_ask - 1 = 10099";
}

TEST_F(PeggedTest, PeggedSellDoesNotCrossSpread) {
    // Set up: best bid at 10000, best ask at 10100
    auto buy1 = make_limit(Side::Buy, 10000, 50);
    engine.submit(buy1);
    auto sell1 = make_limit(Side::Sell, 10100, 50);
    engine.submit(sell1);

    // Pegged sell with negative offset (would put it below best ask, possibly crossing)
    // offset = -200 means price = 10100 + (-200) = 9900, which crosses bid at 10000
    // Should be capped at best_bid + 1 = 10001
    auto pegged = make_pegged(Side::Sell, -200, 30);
    engine.submit(pegged);

    EXPECT_EQ(engine.pegged_order_count(), 1u);

    // The pegged order should be capped at 10001 (best_bid + 1)
    bool found_10001 = false;
    for (auto it = engine.book().asks_begin(); it != engine.book().asks_end(); ++it) {
        if (it->first == 10001) {
            found_10001 = true;
            EXPECT_EQ(it->second.total_quantity, 30u);
        }
    }
    EXPECT_TRUE(found_10001) << "Pegged sell should be capped at best_bid + 1 = 10001";
}

TEST_F(PeggedTest, PeggedOrderRejectedWhenNoReferencePrice) {
    // Empty book - no best bid or best ask
    // Pegged buy should be rejected (no fills, not placed on book)
    auto pegged_buy = make_pegged(Side::Buy, 10, 30);
    auto fills = engine.submit(pegged_buy);

    EXPECT_TRUE(fills.empty());
    EXPECT_EQ(engine.book().best_bid(), nullptr);
    // The order should not be stored as pegged either since there's no reference
    EXPECT_EQ(engine.pegged_order_count(), 0u);
}

TEST_F(PeggedTest, PeggedSellRejectedWhenNoReferencePrice) {
    // Only bids on book, no asks (pegged sell needs best ask)
    auto buy1 = make_limit(Side::Buy, 10000, 50);
    engine.submit(buy1);

    auto pegged_sell = make_pegged(Side::Sell, 10, 30);
    auto fills = engine.submit(pegged_sell);

    EXPECT_TRUE(fills.empty());
    // Pegged sell should not be stored
    EXPECT_EQ(engine.pegged_order_count(), 0u);
}
