#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace exsim {

template <typename T, size_t Capacity>
class MemoryPool {
public:
    MemoryPool() noexcept {
        // Build free list linking all slots
        for (size_t i = 0; i < Capacity - 1; ++i) {
            *reinterpret_cast<size_t*>(&storage_[i]) = i + 1;
        }
        *reinterpret_cast<size_t*>(&storage_[Capacity - 1]) = INVALID;
        free_head_ = 0;
        size_ = 0;
    }

    [[nodiscard]] T* allocate() noexcept {
        if (free_head_ == INVALID) return nullptr;
        size_t idx = free_head_;
        free_head_ = *reinterpret_cast<size_t*>(&storage_[idx]);
        ++size_;
        return reinterpret_cast<T*>(&storage_[idx]);
    }

    void deallocate(T* ptr) noexcept {
        size_t idx = static_cast<size_t>(
            reinterpret_cast<Storage*>(ptr) - storage_.data()
        );
        *reinterpret_cast<size_t*>(&storage_[idx]) = free_head_;
        free_head_ = idx;
        --size_;
    }

    [[nodiscard]] size_t size() const noexcept { return size_; }
    [[nodiscard]] constexpr size_t capacity() const noexcept { return Capacity; }

private:
    static constexpr size_t INVALID = ~size_t{0};

    struct alignas(alignof(T)) Storage {
        unsigned char data[sizeof(T) < sizeof(size_t) ? sizeof(size_t) : sizeof(T)];
    };

    std::array<Storage, Capacity> storage_;
    size_t free_head_;
    size_t size_;
};

} // namespace exsim
