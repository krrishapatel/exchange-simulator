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
        if (order.is_iceberg()) {
            // For iceberg orders resting on the book, split into visible slice + hidden
            add_iceberg_to_book(order);
        } else {
            book_.add(order);
        }
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
                    // Check for iceberg refill before cancelling
                    Order refill_order{};
                    bool needs_refill = (maker.hidden_quantity > 0);
                    if (needs_refill) {
                        refill_order = make_iceberg_refill(maker);
                    }

                    book_.cancel(maker.id);

                    // Refill iceberg: add new visible slice to back of queue
                    if (needs_refill) {
                        add_iceberg_to_book(refill_order);
                    }

                    // Re-fetch best after cancel/refill (pointer may be invalidated)
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
                    // Check for iceberg refill before cancelling
                    Order refill_order{};
                    bool needs_refill = (maker.hidden_quantity > 0);
                    if (needs_refill) {
                        refill_order = make_iceberg_refill(maker);
                    }

                    book_.cancel(maker.id);

                    // Refill iceberg: add new visible slice to back of queue
                    if (needs_refill) {
                        add_iceberg_to_book(refill_order);
                    }

                    // Re-fetch best after cancel/refill (pointer may be invalidated)
                    best = book_.best_bid();
                    if (!best) break;
                }
            }
        }
    }

    return fills;
}

void MatchingEngine::add_iceberg_to_book(Order& order) {
    // Only show the visible slice on the book
    Quantity total_remaining = order.remaining();
    Quantity visible_slice = std::min(order.visible_quantity, total_remaining);
    Quantity hidden = total_remaining - visible_slice;

    Order book_order = order;
    book_order.quantity = visible_slice;
    book_order.filled_quantity = 0;
    book_order.hidden_quantity = hidden;
    book_order.timestamp = current_ts_++;  // New timestamp for queue priority

    book_.add(book_order);
}

Order MatchingEngine::make_iceberg_refill(const Order& filled_maker) {
    // Create a new order representing the next visible slice of the iceberg
    Order refill{};
    refill.id = filled_maker.id;  // Same order ID
    refill.side = filled_maker.side;
    refill.price = filled_maker.price;
    refill.type = filled_maker.type;
    refill.tif = filled_maker.tif;
    refill.visible_quantity = filled_maker.visible_quantity;
    // The total remaining is the hidden_quantity
    refill.quantity = filled_maker.hidden_quantity;
    refill.filled_quantity = 0;
    refill.hidden_quantity = 0;  // Will be recalculated in add_iceberg_to_book
    refill.timestamp = current_ts_;
    return refill;
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
