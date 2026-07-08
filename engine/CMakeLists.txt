# engine/CMakeLists.txt
add_library(engine
    src/order_book.cpp
    src/matching_engine.cpp
    src/multi_asset_engine.cpp
)
target_include_directories(engine PUBLIC src)
set_target_properties(engine PROPERTIES CXX_STANDARD 20)

include(FetchContent)

# Google Test
FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG v1.15.2
)
FetchContent_MakeAvailable(googletest)

# Google Benchmark
FetchContent_Declare(
    benchmark
    GIT_REPOSITORY https://github.com/google/benchmark.git
    GIT_TAG v1.9.1
)
set(BENCHMARK_ENABLE_TESTING OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(benchmark)

enable_testing()
add_subdirectory(tests)
add_subdirectory(bench)
