#include <gtest/gtest.h>
#include "memory_pool.hpp"

using namespace exsim;

struct TestItem {
    int value;
    double data;
};

TEST(MemoryPoolTest, AllocateAndDeallocate) {
    MemoryPool<TestItem, 128> pool;
    EXPECT_EQ(pool.size(), 0);
    EXPECT_EQ(pool.capacity(), 128);

    TestItem* item = pool.allocate();
    ASSERT_NE(item, nullptr);
    item->value = 42;
    EXPECT_EQ(pool.size(), 1);

    pool.deallocate(item);
    EXPECT_EQ(pool.size(), 0);
}

TEST(MemoryPoolTest, AllocateAll) {
    MemoryPool<TestItem, 4> pool;
    TestItem* items[4];
    for (int i = 0; i < 4; ++i) {
        items[i] = pool.allocate();
        ASSERT_NE(items[i], nullptr);
    }
    EXPECT_EQ(pool.size(), 4);

    // Pool is full
    TestItem* overflow = pool.allocate();
    EXPECT_EQ(overflow, nullptr);
}

TEST(MemoryPoolTest, ReuseAfterDeallocate) {
    MemoryPool<TestItem, 2> pool;
    TestItem* a = pool.allocate();
    pool.deallocate(a);

    TestItem* b = pool.allocate();
    // Should reuse the same slot
    EXPECT_EQ(a, b);
}

TEST(MemoryPoolTest, NoHeapAllocation) {
    // Pool is stack/static allocated, sizeof should reflect capacity
    MemoryPool<TestItem, 64> pool;
    // Just verify it compiles and works without new/malloc
    for (int i = 0; i < 64; ++i) {
        ASSERT_NE(pool.allocate(), nullptr);
    }
    EXPECT_EQ(pool.size(), 64);
}
