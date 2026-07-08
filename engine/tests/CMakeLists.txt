# engine/tests/CMakeLists.txt
add_executable(engine_tests test_types.cpp)
target_link_libraries(engine_tests PRIVATE engine GTest::gtest_main)
include(GoogleTest)
gtest_discover_tests(engine_tests)
