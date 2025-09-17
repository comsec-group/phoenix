#pragma once

#define MEM_ALIGN (1ULL << 30)

#include <cstdint>
#include <utility>
#include <vector>

class allocation {
    public:
    allocation() = default;
    ~allocation();

    allocation(allocation const&) = delete;
    allocation& operator=(allocation const&) = delete;

    allocation(allocation&& other) noexcept
    : allocation_ptr(other.allocation_ptr), allocation_size(other.allocation_size) {
        other.allocation_ptr  = nullptr;
        other.allocation_size = 0;
    }
    allocation& operator=(allocation&& other) noexcept {
        std::swap(allocation_ptr, other.allocation_ptr);
        std::swap(allocation_size, other.allocation_size);
        return *this;
    }

    bool allocate(size_t num_superpages);

    // The functions return 0 (nullptr) if the address falls outside this allocation mapping.
    uint64_t virt_to_phys(volatile char* virt);
    volatile char* phys_to_virt(uint64_t phys);

    volatile char* get_rand_addr();

    [[nodiscard]] void* ptr() const {
        return allocation_ptr;
    }
    [[nodiscard]] size_t size() const {
        return allocation_size;
    }

    private:
    void* allocation_ptr{ nullptr };
    size_t allocation_size{ 0 };

    std::vector<std::pair<volatile char*, uint64_t>> virt_phys_mappings;
};
