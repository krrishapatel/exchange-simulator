// engine/src/matching_engine.cpp
#include "matching_engine.hpp"
#include <algorithm>

namespace exsim {

std::vector<Fill> MatchingEngine::submit(Order& order) {
    current_ts_ = order.timestamp;

    switch (order.type) {
        case OrderType::Limit:
            return match_limit(order);
        case OrderType::Market:
            return match_market(order);
    }
    return {};
}

CancelResult MatchingEngine::cancel(OrderId id) {
    return book_.cancel(id);
}

std::vector<Fill> MatchingEngine::match_limit(Order& order) {
    // FOK: reject entirely if full quantity is not available
    if (order.tif == TimeInForce::FOK) {
        Quantity available = available_quantity(order);
        if (available < order.quantity) {
            return {};
        }
    }

    auto fills = match_against_book(order);

    // Rest remaining quantity on the book (GTC orders only)
    if (order.remaining() > 0 && order.tif == TimeInForce::GTC) {
        book_.add(order);
    }
    // IOC/FOK: remaining quantity is discarded (no rest on book)
    return fills;
}

std::vector<Fill> MatchingEngine::match_market(Order& order) {
    // Market orders match what's available, don't rest on the book
    return match_against_book(order);
}

std::vector<Fill> MatchingEngine::match_against_book(Order& order) {
    std::vector<Fill> fills;

    if (order.side == Side::Buy) {
        while (order.remaining() > 0) {
            auto* best = book_.best_ask();
            if (!best) break;
            if (order.type == OrderType::Limit && best->price > order.price) break;

            // Walk orders at this price level
            while (order.remaining() > 0 && !best->orders.empty()) {
                auto& maker_node = best->orders.front();
                Order& maker = maker_node.order;
                Quantity fill_qty = std::min(order.remaining(), maker.remaining());

                Fill fill{};
                fill.maker_order_id = maker.id;
                fill.taker_order_id = order.id;
                fill.price = maker.price;
                fill.quantity = fill_qty;
                fill.aggressor_side = Side::Buy;
                fill.timestamp = current_ts_;
                fills.push_back(fill);

                order.filled_quantity += fill_qty;

                // Update the price level's total quantity to reflect the fill
                best->total_quantity -= fill_qty;
                maker.filled_quantity += fill_qty;

                if (maker.is_filled()) {
                    book_.cancel(maker.id);
                    // Re-fetch best after cancel (pointer may be invalidated)
                    best = book_.best_ask();
                    if (!best) break;
                }
            }
        }
    } else {
        while (order.remaining() > 0) {
            auto* best = book_.best_bid();
            if (!best) break;
            if (order.type == OrderType::Limit && best->price < order.price) break;

            while (order.remaining() > 0 && !best->orders.empty()) {
                auto& maker_node = best->orders.front();
                Order& maker = maker_node.order;
                Quantity fill_qty = std::min(order.remaining(), maker.remaining());

                Fill fill{};
                fill.maker_order_id = maker.id;
                fill.taker_order_id = order.id;
                fill.price = maker.price;
                fill.quantity = fill_qty;
                fill.aggressor_side = Side::Sell;
                fill.timestamp = current_ts_;
                fills.push_back(fill);

                order.filled_quantity += fill_qty;

                // Update the price level's total quantity to reflect the fill
                best->total_quantity -= fill_qty;
                maker.filled_quantity += fill_qty;

                if (maker.is_filled()) {
                    book_.cancel(maker.id);
                    // Re-fetch best after cancel (pointer may be invalidated)
                    best = book_.best_bid();
                    if (!best) break;
                }
            }
        }
    }

    return fills;
}

Quantity MatchingEngine::available_quantity(const Order& order) const noexcept {
    Quantity available = 0;
    if (order.side == Side::Buy) {
        for (auto it = book_.asks_begin(); it != book_.asks_end(); ++it) {
            if (order.type == OrderType::Limit && it->first > order.price) break;
            available += it->second.total_quantity;
            if (available >= order.quantity) return available;
        }
    } else {
        for (auto it = book_.bids_begin(); it != book_.bids_end(); ++it) {
            if (order.type == OrderType::Limit && it->first < order.price) break;
            available += it->second.total_quantity;
            if (available >= order.quantity) return available;
        }
    }
    return available;
}

} // namespace exsim
