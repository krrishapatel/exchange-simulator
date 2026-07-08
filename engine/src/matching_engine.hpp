// engine/src/matching_engine.hpp
#pragma once

#include "order_book.hpp"
#include "types.hpp"
#include <vector>

namespace exsim {

class MatchingEngine {
public:
    MatchingEngine() = default;

    std::vector<Fill> submit(Order& order);
    CancelResult cancel(OrderId id);

    [[nodiscard]] const OrderBook& book() const noexcept { return book_; }

private:
    std::vector<Fill> match_limit(Order& order);
    std::vector<Fill> match_market(Order& order);
    std::vector<Fill> match_against_book(Order& order);

    OrderBook book_;
    Timestamp current_ts_ = 0;
};

} // namespace exsim
