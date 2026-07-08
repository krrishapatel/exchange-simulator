// engine/src/matching_engine.cpp
#include "matching_engine.hpp"
#include <algorithm>

namespace exsim {

std::vector<Fill> MatchingEngine::submit(Order& order) {
    current_ts_ = order.timestamp;

    switch (order.type) {
        case OrderType::Limit: {
            auto fills = match_limit(order);
            if (!fills.empty()) {
                last_trade_price_ = fills.back().price;
                check_stop_triggers(last_trade_price_, fills);
                reprice_pegged_orders(fills);
            }
            return fills;
        }
        case OrderType::Market: {
            auto fills = match_market(order);
            if (!fills.empty()) {
                last_trade_price_ = fills.back().price;
                check_stop_triggers(last_trade_price_, fills);
                reprice_pegged_orders(fills);
            }
            return fills;
        }
        case OrderType::Stop:
        case OrderType::StopLimit:
            // Stop orders don't match immediately; store them dormant
            stop_orders_.push_back(order);
            return {};
        case OrderType::Pegged: {
            // Calculate initial price based on current best bid/ask + offset
            Price ref_price = 0;
            if (order.side == Side::Buy) {
                const auto* best = book_.best_bid();
                if (!best) {
                    // No reference price available; reject the order
                    return {};
                }
                ref_price = best->price - order.peg_offset;
                // Cap: pegged buy cannot cross the spread
                const auto* ask = book_.best_ask();
                if (ask && ref_price >= ask->price) {
                    ref_price = ask->price - 1;
                }
            } else {
                const auto* best = book_.best_ask();
                if (!best) {
                    // No reference price available; reject the order
                    return {};
                }
                ref_price = best->price + order.peg_offset;
                // Cap: pegged sell cannot cross the spread
                const auto* bid = book_.best_bid();
                if (bid && ref_price <= bid->price) {
                    ref_price = bid->price + 1;
                }
            }
            // Store the pegged order metadata for repricing
            pegged_orders_.push_back(order);
            // Place as a limit order on the book
            Order limit_order = order;
            limit_order.price = ref_price;
            limit_order.type = OrderType::Limit;
            limit_order.tif = TimeInForce::GTC;
            book_.add(limit_order);
            return {};
        }
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

void MatchingEngine::reprice_pegged_orders(std::vector<Fill>& fills) {
    if (pegged_orders_.empty()) return;

    for (auto it = pegged_orders_.begin(); it != pegged_orders_.end(); ) {
        // Cancel the existing limit order from the book
        book_.cancel(it->id);

        // Calculate new price
        Price new_price = 0;
        bool has_reference = false;

        if (it->side == Side::Buy) {
            const auto* best = book_.best_bid();
            if (best) {
                has_reference = true;
                new_price = best->price - it->peg_offset;
                // Cap: cannot cross spread
                const auto* ask = book_.best_ask();
                if (ask && new_price >= ask->price) {
                    new_price = ask->price - 1;
                }
            }
        } else {
            const auto* best = book_.best_ask();
            if (best) {
                has_reference = true;
                new_price = best->price + it->peg_offset;
                // Cap: cannot cross spread
                const auto* bid = book_.best_bid();
                if (bid && new_price <= bid->price) {
                    new_price = bid->price + 1;
                }
            }
        }

        if (!has_reference) {
            // No reference price; keep pegged order dormant (don't place on book)
            ++it;
            continue;
        }

        // Re-add to book at new price
        Order limit_order = *it;
        limit_order.price = new_price;
        limit_order.type = OrderType::Limit;
        limit_order.tif = TimeInForce::GTC;
        limit_order.timestamp = current_ts_;
        book_.add(limit_order);
        ++it;
    }
}

void MatchingEngine::check_stop_triggers(Price last_trade_price, std::vector<Fill>& fills) {
    // Iterate and trigger stops. Handle cascading: a triggered stop may produce
    // fills that trigger additional stops, so we loop until no more triggers fire.
    bool triggered_any = true;
    while (triggered_any) {
        triggered_any = false;
        for (auto it = stop_orders_.begin(); it != stop_orders_.end(); ) {
            bool should_trigger = false;

            if (it->side == Side::Buy) {
                // Stop buy triggers when last trade price >= stop_price (market rising)
                should_trigger = (last_trade_price >= it->stop_price);
            } else {
                // Stop sell triggers when last trade price <= stop_price (market falling)
                should_trigger = (last_trade_price <= it->stop_price);
            }

            if (should_trigger) {
                // Convert to market order and submit
                Order triggered = *it;
                triggered.type = OrderType::Market;
                triggered.price = 0;
                triggered.stop_price = 0;
                it = stop_orders_.erase(it);

                auto new_fills = match_market(triggered);
                if (!new_fills.empty()) {
                    last_trade_price = new_fills.back().price;
                    last_trade_price_ = last_trade_price;
                    fills.insert(fills.end(), new_fills.begin(), new_fills.end());
                    triggered_any = true;  // Restart scan for cascading triggers
                    break;  // Restart the for-loop since vector was modified
                }
            } else {
                ++it;
            }
        }
    }
}

} // namespace exsim
