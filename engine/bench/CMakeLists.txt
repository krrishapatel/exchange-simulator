# engine/bench/CMakeLists.txt
add_executable(bench_order_book bench_order_book.cpp)
target_link_libraries(bench_order_book PRIVATE engine benchmark::benchmark)

add_executable(bench_matching bench_matching.cpp)
target_link_libraries(bench_matching PRIVATE engine benchmark::benchmark)
