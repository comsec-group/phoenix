#include <hammer/bit_flips.hpp>
#include <hammer/dram_address.hpp>

#include <cstdint>
#include <emmintrin.h>
#include <immintrin.h>
#include <unordered_set>
#include <vector>

std::vector<bit_flip_t> collect_bit_flips(const std::vector<dram_address>& dram_addresses_victims,
                                          const uint64_t data_pattern_victim) {
    // Interpret the 8-byte data pattern as individual bytes.
    const auto* pattern_bytes = reinterpret_cast<const uint8_t*>(&data_pattern_victim);

    std::vector<bit_flip_t> found_bitflips;

    // Remove all duplicates
    std::unordered_set<uintptr_t> all_victim_vaddrs;
    for(auto da : dram_addresses_victims) {
        for(auto vaddr : da.get_vaddrs_whole_row()) {
            // reinterpret the value as an integer we can mask
            auto addr = reinterpret_cast<uint64_t>(vaddr);

            // insert only if 8-byte aligned (i.e. the lower 3 bits are zero)
            if((addr & (alignof(uint64_t) - 1)) == 0) { // alignof(uint64_t) == 8
                all_victim_vaddrs.insert(addr);
            }
        }
    }

    // Go through all the victim addresses in steps of 8 bytes.
    for(auto vaddr : all_victim_vaddrs) {
        // Make sure we do not read a cached value, but actually from DRAM.
        _mm_clflushopt((void*)vaddr);
        _mm_mfence();

        // Iterate over each byte in the 8-byte data pattern.
        const auto value_ptr = reinterpret_cast<volatile uint8_t*>(vaddr);
        for(int i = 0; i < 8; ++i) {
            uint8_t actual_byte   = value_ptr[i];
            uint8_t expected_byte = pattern_bytes[i];
            if(actual_byte != expected_byte) {
                auto addr = dram_address::from_virt(
                    reinterpret_cast<const volatile char*>(vaddr + i));
                found_bitflips.push_back({ addr, expected_byte, actual_byte });
            }
        }

        // Restore the original value of the entire 8-byte pattern.
        volatile auto* addr = reinterpret_cast<volatile uint64_t*>(vaddr);
        *addr               = data_pattern_victim;
        _mm_clflushopt((void*)value_ptr);
    }

    return found_bitflips;
}

void initialize_data_pattern(const std::vector<dram_address>& dram_addresses_aggs,
                             uint64_t data_pattern) {
    for(const auto& da : dram_addresses_aggs) {
        auto row = da.get_whole_row();

        for(size_t i = 0; i < row.size(); i += 8) {
            if(row[i].column() % 8 == 0) {
                auto vaddr                                   = row[i].to_virt();
                *reinterpret_cast<volatile uint64_t*>(vaddr) = data_pattern;
                _mm_clflushopt(const_cast<void*>(static_cast<const volatile void*>(vaddr)));
            }
        }
    }
    _mm_mfence();
}
