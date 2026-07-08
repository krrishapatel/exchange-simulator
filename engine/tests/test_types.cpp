// engine/tests/test_types.cpp
#include <gtest/gtest.h>
#include "types.hpp"

using namespace exsim;

TEST(TypesTest, OrderRemainingQuantity) {
    Order order{};
    order.quantity = 100;
    order.filled_quantity = 30;
    EXPECT_EQ(order.remaining(), 70);
}

TEST(TypesTest, OrderIsFilled) {
    Order order{};
    order.quantity = 100;
    order.filled_quantity = 100;
    EXPECT_TRUE(order.is_filled());
}

TEST(TypesTest, OrderIsNotFilled) {
    Order order{};
    order.quantity = 100;
    order.filled_quantity = 50;
    EXPECT_FALSE(order.is_filled());
}

TEST(TypesTest, OrderCacheLineAligned) {
    EXPECT_EQ(alignof(Order), 64);
}

TEST(TypesTest, SideEnum) {
    EXPECT_EQ(static_cast<uint8_t>(Side::Buy), 0);
    EXPECT_EQ(static_cast<uint8_t>(Side::Sell), 1);
}
