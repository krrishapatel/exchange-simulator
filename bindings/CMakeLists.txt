# bindings/CMakeLists.txt
find_package(Python COMPONENTS Interpreter Development REQUIRED)

include(FetchContent)

FetchContent_Declare(
    pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG v2.13.6
)
FetchContent_MakeAvailable(pybind11)

pybind11_add_module(exchange_simulator py_exchange.cpp)
target_link_libraries(exchange_simulator PRIVATE engine)
