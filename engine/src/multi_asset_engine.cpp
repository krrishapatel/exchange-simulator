// engine/src/multi_asset_engine.cpp
#include "multi_asset_engine.hpp"

namespace exsim {

MatchingEngine& MultiAssetEngine::get_book(uint32_t symbol_id) {
    auto [it, _] = books_.try_emplace(symbol_id);
    return it->second;
}

std::vector<Fill> MultiAssetEngine::submit(uint32_t symbol_id, Order& order) {
    order_to_symbol_[order.id] = symbol_id;
    auto& engine = get_book(symbol_id);
    return engine.submit(order);
}

CancelResult MultiAssetEngine::cancel(uint64_t order_id) {
    auto it = order_to_symbol_.find(order_id);
    if (it == order_to_symbol_.end()) {
        return CancelResult::OrderNotFound;
    }
    uint32_t symbol_id = it->second;
    auto book_it = books_.find(symbol_id);
    if (book_it == books_.end()) {
        return CancelResult::OrderNotFound;
    }
    return book_it->second.cancel(order_id);
}

std::vector<uint32_t> MultiAssetEngine::symbols() const {
    std::vector<uint32_t> result;
    result.reserve(books_.size());
    for (const auto& [id, _] : books_) {
        result.push_back(id);
    }
    return result;
}

} // namespace exsim
