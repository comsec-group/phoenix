#pragma once

#include "bit_flips.hpp"
#include "pattern.hpp"

#include <vector>

struct FuzzPoint {
    int pattern_idx;
    int pattern_reads_per_trefi;
    const hammer_pattern_t& pattern;
    int self_sync_threshold;
    int agg_base_row;
};


struct IHammerObserver {
    virtual void on_pre_iteration(const FuzzPoint&) = 0;
    virtual void on_post_iteration(const FuzzPoint&, const std::vector<bit_flip_t>&) = 0;
    virtual ~IHammerObserver() = default;
};