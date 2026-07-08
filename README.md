# Exchange Simulator

A high-performance C++20 exchange simulator with a matching engine optimized for low-latency order processing.

## Build

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

## Test

```bash
ctest --test-dir build --output-on-failure
```

## License

MIT
