// engine/bench/bench_matching.cpp
#include <benchmark/benchmark.h>
#include "matching_engine.hpp"

using namespace exsim;

static void BM_MatchingEngine_LimitNoMatch(benchmark::State& state) {
    MatchingEngine engine;
    uint64_t id = 1;
    for (auto _ : state) {
        Order o{};
        o.id = id++;
        o.side = Side::Buy;
        o.price = 10000 - (id % 50); // always below asks
        o.quantity = 100;
        o.filled_quantity = 0;
        o.type = OrderType::Limit;
        o.tif = TimeInForce::GTC;
        o.timestamp = id;
        auto fills = engine.submit(o);
        benchmark::DoNotOptimize(fills);
    }
}
BENCHMARK(BM_MatchingEngine_LimitNoMatch);

static void BM_MatchingEngine_LimitFullMatch(benchmark::State& state) {
    MatchingEngine engine;
    uint64_t id = 1;
    for (auto _ : state) {
        // Add a resting order then immediately match it
        Order sell{};
        sell.id = id++;
        sell.side = Side::Sell;
        sell.price = 10000;
        sell.quantity = 100;
        sell.filled_quantity = 0;
        sell.type = OrderType::Limit;
        sell.tif = TimeInForce::GTC;
        sell.timestamp = id;
        engine.submit(sell);

        Order buy{};
        buy.id = id++;
        buy.side = Side::Buy;
        buy.price = 10000;
        buy.quantity = 100;
        buy.filled_quantity = 0;
        buy.type = OrderType::Limit;
        buy.tif = TimeInForce::GTC;
        buy.timestamp = id;
        auto fills = engine.submit(buy);
        benchmark::DoNotOptimize(fills);
    }
}
BENCHMARK(BM_MatchingEngine_LimitFullMatch);

static void BM_MatchingEngine_MarketSweep(benchmark::State& state) {
    // Pre-fill asks, then sweep with market orders
    MatchingEngine engine;
    uint64_t id = 1;

    for (auto _ : state) {
        state.PauseTiming();
        // Reset: add 10 levels of asks
        MatchingEngine fresh_engine;
        for (int i = 0; i < 10; ++i) {
            Order sell{};
            sell.id = id++;
            sell.side = Side::Sell;
            sell.price = 10000 + i * 10;
            sell.quantity = 100;
            sell.filled_quantity = 0;
            sell.type = OrderType::Limit;
            sell.tif = TimeInForce::GTC;
            sell.timestamp = id;
            fresh_engine.submit(sell);
        }
        state.ResumeTiming();

        Order buy{};
        buy.id = id++;
        buy.side = Side::Buy;
        buy.price = 0;
        buy.quantity = 500; // sweep half the book
        buy.filled_quantity = 0;
        buy.type = OrderType::Market;
        buy.tif = TimeInForce::IOC;
        buy.timestamp = id;
        auto fills = fresh_engine.submit(buy);
        benchmark::DoNotOptimize(fills);
    }
}
BENCHMARK(BM_MatchingEngine_MarketSweep);

BENCHMARK_MAIN();
