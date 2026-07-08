// engine/bench/bench_order_book.cpp
#include <benchmark/benchmark.h>
#include "order_book.hpp"

using namespace exsim;

static void BM_OrderBook_AddLimit(benchmark::State& state) {
    OrderBook book;
    uint64_t id = 1;
    for (auto _ : state) {
        Order o{};
        o.id = id++;
        o.side = (id % 2 == 0) ? Side::Buy : Side::Sell;
        o.price = 10000 + (id % 100) * 10;
        o.quantity = 100;
        o.filled_quantity = 0;
        o.type = OrderType::Limit;
        o.tif = TimeInForce::GTC;
        o.timestamp = id;
        benchmark::DoNotOptimize(book.add(o));
    }
}
BENCHMARK(BM_OrderBook_AddLimit);

static void BM_OrderBook_Cancel(benchmark::State& state) {
    OrderBook book;
    // Pre-fill book
    std::vector<OrderId> ids;
    for (uint64_t i = 1; i <= 10000; ++i) {
        Order o{};
        o.id = i;
        o.side = (i % 2 == 0) ? Side::Buy : Side::Sell;
        o.price = 10000 + (i % 100) * 10;
        o.quantity = 100;
        o.filled_quantity = 0;
        o.type = OrderType::Limit;
        o.tif = TimeInForce::GTC;
        o.timestamp = i;
        book.add(o);
        ids.push_back(i);
    }

    size_t idx = 0;
    for (auto _ : state) {
        if (idx >= ids.size()) {
            state.PauseTiming();
            // Re-add cancelled orders
            for (auto id : ids) {
                Order o{};
                o.id = id;
                o.side = (id % 2 == 0) ? Side::Buy : Side::Sell;
                o.price = 10000 + (id % 100) * 10;
                o.quantity = 100;
                o.filled_quantity = 0;
                o.type = OrderType::Limit;
                o.tif = TimeInForce::GTC;
                o.timestamp = id;
                book.add(o);
            }
            idx = 0;
            state.ResumeTiming();
        }
        benchmark::DoNotOptimize(book.cancel(ids[idx++]));
    }
}
BENCHMARK(BM_OrderBook_Cancel);

BENCHMARK_MAIN();
