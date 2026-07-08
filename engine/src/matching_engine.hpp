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
    [[nodiscard]] size_t stop_order_count() const noexcept { return stop_orders_.size(); }

private:
    std::vector<Fill> match_limit(Order& order);
    std::vector<Fill> match_market(Order& order);
    std::vector<Fill> match_against_book(Order& order);

    // Iceberg support
    void add_iceberg_to_book(Order& order);
    Order make_iceberg_refill(const Order& filled_maker);

    // Stop order support
    void check_stop_triggers(Price last_trade_price, std::vector<Fill>& fills);

    // FOK pre-check: how much liquidity is available at order's price or better
    [[nodiscard]] Quantity available_quantity(const Order& order) const noexcept;

    OrderBook book_;
    std::vector<Order> stop_orders_;  // Dormant stop orders awaiting trigger
    Timestamp current_ts_ = 0;
    Price last_trade_price_ = 0;      // Most recent trade price
};

} // namespace exsim
