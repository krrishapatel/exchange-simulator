// engine/src/order_book.hpp
#pragma once

#include "types.hpp"
#include <cstddef>
#include <map>
#include <unordered_map>
#include <list>

namespace exsim {

struct OrderNode {
    Order order;
    // Intrusive list pointers managed by std::list for now;
    // will optimize to raw intrusive list in Task 5 (optimization pass)
};

struct PriceLevel {
    Price price;
    Quantity total_quantity;
    size_t order_count;
    std::list<OrderNode> orders;

    PriceLevel() : price(0), total_quantity(0), order_count(0) {}
    explicit PriceLevel(Price p) : price(p), total_quantity(0), order_count(0) {}
};

class OrderBook {
public:
    OrderBook() = default;

    bool add(const Order& order);
    CancelResult cancel(OrderId id);

    [[nodiscard]] const PriceLevel* best_bid() const noexcept;
    [[nodiscard]] const PriceLevel* best_ask() const noexcept;
    [[nodiscard]] PriceLevel* best_bid() noexcept;
    [[nodiscard]] PriceLevel* best_ask() noexcept;
    [[nodiscard]] Price spread() const noexcept;
    [[nodiscard]] size_t bid_depth() const noexcept;
    [[nodiscard]] size_t ask_depth() const noexcept;

    // Const iterators for liquidity scanning (FOK pre-check)
    using BidsMap = std::map<Price, PriceLevel, std::greater<Price>>;
    using AsksMap = std::map<Price, PriceLevel, std::less<Price>>;

    [[nodiscard]] BidsMap::const_iterator bids_begin() const noexcept { return bids_.cbegin(); }
    [[nodiscard]] BidsMap::const_iterator bids_end() const noexcept { return bids_.cend(); }
    [[nodiscard]] AsksMap::const_iterator asks_begin() const noexcept { return asks_.cbegin(); }
    [[nodiscard]] AsksMap::const_iterator asks_end() const noexcept { return asks_.cend(); }

private:
    // Bids: highest price first (reverse order)
    std::map<Price, PriceLevel, std::greater<Price>> bids_;
    // Asks: lowest price first (natural order)
    std::map<Price, PriceLevel, std::less<Price>> asks_;
    // Fast lookup by order ID
    struct OrderLocation {
        Side side;
        Price price;
        std::list<OrderNode>::iterator it;
    };
    std::unordered_map<OrderId, OrderLocation> order_map_;
};

} // namespace exsim
