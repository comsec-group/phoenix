#pragma once

#include "dram_address.hpp"

#include <cstdint>

struct bit_flip_t {
    dram_address address;
    uint8_t expected_value{};
    uint8_t actual_value{};
};

std::vector<bit_flip_t> collect_bit_flips(const std::vector<dram_address>& dram_addresses_victims,
                                          uint64_t data_pattern_victim);


void initialize_data_pattern(const std::vector<dram_address>& dram_addresses_aggs,
                             uint64_t data_pattern);
