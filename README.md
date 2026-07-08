# Exchange Simulator

High-performance simulated exchange with a C++ matching engine and ML trading agents.

## Performance

Benchmarked on Apple Silicon (Release build):

| Operation | Latency | Throughput |
|-----------|---------|------------|
| Order book add | ~61 ns | 16.5M ops/sec |
| Order book cancel | ~34 ns | 29.8M ops/sec |
| Limit order match | ~118 ns | 8.5M matches/sec |
| Market order sweep (5 levels) | ~1029 ns | 972K sweeps/sec |

All operations well under the 1μs target.

## Architecture

- **C++ Matching Engine** — Price-time priority order book, limit/market orders, zero-allocation memory pool
- **ML Agents** (coming) — Classical strategies → gradient-boosted models → deep RL via self-play
- **Market Data** (coming) — Synthetic (Hawkes process) + real data replay (Lobster/Databento)
- **Dashboard** (coming) — Live latency histograms, book visualization, agent PnL

## Build

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

## Test

```bash
ctest --test-dir build --output-on-failure
```

## Benchmark

```bash
./build/engine/bench/bench_order_book
./build/engine/bench/bench_matching
```

## Project Structure

```
exchange-simulator/
├── engine/
│   ├── src/
│   │   ├── types.hpp              # Core types: Order, Fill, Side, Price
│   │   ├── memory_pool.hpp        # Fixed-size pool allocator (zero heap alloc)
│   │   ├── order_book.hpp/cpp     # L2/L3 order book, price-time priority
│   │   └── matching_engine.hpp/cpp # Order execution engine
│   ├── tests/                     # Google Test suite (26 tests)
│   └── bench/                     # Google Benchmark suite
└── CMakeLists.txt
```

## Status

- [x] Core types and memory pool
- [x] Order book (price-time priority)
- [x] Matching engine (limit + market orders)
- [x] Benchmark suite
- [ ] IOC/FOK/Iceberg/Stop/Pegged orders
- [ ] Auction phases (opening/closing)
- [ ] Python bindings (pybind11)
- [ ] Agent framework (classical + ML + RL)
- [ ] Synthetic data generator (Hawkes process)
- [ ] Real data replay (Lobster/Databento)
- [ ] Performance dashboard (WebSocket + React)

## License

MIT
