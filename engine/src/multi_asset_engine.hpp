// engine/src/multi_asset_engine.hpp
#pragma once

#include "matching_engine.hpp"
#include <unordered_map>
#include <vector>
#include <cstdint>

namespace exsim {

class MultiAssetEngine {
public:
    MultiAssetEngine() = default;

    // Get or create a book for a symbol
    MatchingEngine& get_book(uint32_t symbol_id);

    // Submit to a specific symbol
    std::vector<Fill> submit(uint32_t symbol_id, Order& order);

    // Cancel across any book (routes to correct symbol)
    CancelResult cancel(uint64_t order_id);

    // Get all symbol IDs
    std::vector<uint32_t> symbols() const;

private:
    std::unordered_map<uint32_t, MatchingEngine> books_;
    std::unordered_map<uint64_t, uint32_t> order_to_symbol_; // for cancel routing
};

} // namespace exsim
