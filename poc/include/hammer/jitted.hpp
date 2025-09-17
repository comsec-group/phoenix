#pragma once

#include "pattern.hpp"


using hammer_fn_t = void (*)(const hammer_pattern_t& /* pattern   */,
                             std::vector<dram_address>& /* sync rows */,
                             int /* ref threshold */,
                             int /* pattern repetitions */,
                             int /* self_sync_thresh */);

void hammer_jitted_self_sync(const hammer_pattern_t& pattern,
                             std::vector<dram_address>& sync_rows,
                             int ref_threshold,
                             int pattern_repetitions,
                             int self_sync_threshold);

void hammer_jitted_seq_sync(const hammer_pattern_t& pattern,
                            std::vector<dram_address>& sync_rows,
                            int ref_threshold,
                            int pattern_repetitions,
                            int self_sync_threshold);
