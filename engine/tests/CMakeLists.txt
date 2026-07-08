# engine/tests/CMakeLists.txt
add_executable(engine_tests
    test_types.cpp
    test_memory_pool.cpp
    test_order_book.cpp
)
target_link_libraries(engine_tests PRIVATE engine GTest::gtest_main)
include(GoogleTest)
gtest_discover_tests(engine_tests)
