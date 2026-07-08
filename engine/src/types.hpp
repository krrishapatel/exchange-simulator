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
};

enum class TimeInForce : uint8_t {
    GTC = 0,  // Good-til-cancel
    IOC = 1,  // Immediate-or-cancel
    FOK = 2,  // Fill-or-kill
};

struct alignas(64) Order {
    OrderId id;
    Price price;
    Quantity quantity;
    Quantity filled_quantity;
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
};

struct Fill {
    OrderId maker_order_id;
    OrderId taker_order_id;
    Price price;
    Quantity quantity;
    Side aggressor_side;
    Timestamp timestamp;
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
