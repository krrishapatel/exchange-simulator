// engine/src/types.hpp
#pragma once

#include <cstdint>
#include <cstring>

namespace exsim {

using OrderId = uint64_t;
using Price = int64_t;      // fixed-point: price * 10000 (4 decimal places)
using Quantity = uint32_t;
using Timestamp = uint64_t; // nanoseconds since epoch

enum class Side : uint8_t { Buy = 0, Sell = 1 };

enum class OrderType : uint8_t {
    Limit = 0,
    Market = 1,
    Stop = 2,       // Becomes market when stop_price triggered
    StopLimit = 3,  // Becomes limit when stop_price triggered (future)
    Pegged = 4,     // Tracks best bid/ask with an offset, reprices automatically
};

enum class TimeInForce : uint8_t {
    GTC = 0,  // Good-til-cancel
    IOC = 1,  // Immediate-or-cancel
    FOK = 2,  // Fill-or-kill
};

struct alignas(64) Order {
    OrderId id;
    Price price;
    Price stop_price;           // Trigger price for stop orders (0 = not a stop)
    Price peg_offset;           // For pegged orders: offset from reference price (positive = away from mid)
    Quantity quantity;
    Quantity filled_quantity;
    Quantity visible_quantity;  // For iceberg: slice size shown on book. 0 = not an iceberg.
    Quantity hidden_quantity;   // For iceberg: remaining quantity behind the visible slice.
    Side side;
    OrderType type;
    TimeInForce tif;
    Timestamp timestamp;

    [[nodiscard]] Quantity remaining() const noexcept {
        return quantity - filled_quantity;
    }

    [[nodiscard]] bool is_filled() const noexcept {
        return filled_quantity >= quantity;
    }

    [[nodiscard]] bool is_iceberg() const noexcept {
        return visible_quantity > 0;
    }
};

struct Fill {
    OrderId maker_order_id;
    OrderId taker_order_id;
    Price price;
    Quantity quantity;
    Side aggressor_side;
    Timestamp timestamp;
};

enum class Phase : uint8_t {
    PreOpen = 0,     // Orders accepted but no matching (auction collection)
    Continuous = 1,  // Normal matching (current default behavior)
};

enum class CancelResult : uint8_t {
    Success = 0,
    OrderNotFound = 1,
    AlreadyFilled = 2,
};

struct OrderResult {
    enum class Status : uint8_t {
        Accepted = 0,
        Rejected = 1,
        Cancelled = 2,
    };
    Status status;
    OrderId order_id;
};

} // namespace exsim
