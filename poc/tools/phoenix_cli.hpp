#pragma once

#include <CLI/CLI.hpp>
#include <filesystem>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

struct cli_params {
    /* CPU & geometry */
    int cpu_core{};
    int sync_row_count{};
    int sync_row_start{};

    /* timing knobs */
    int ref_threshold{};
    std::string self_sync_cycles_str;
    std::string reads_per_trefi_str;
    std::vector<int> self_sync_cycles;
    std::vector<int> reads_per_trefi;
    int trefi_sync_count{};

    /* pattern layout */
    int aggressor_row_start{};
    int aggressor_row_end{};
    int aggressor_spacing{};
    int column_stride{};
    int pattern_trefi_offset_per_bank{};

    /* selectors */
    std::string hammer_fn{ "self_sync" };
    std::string pattern_id{ "skh_mod128" };

    /* topology masks */
    std::vector<int> target_subch;
    std::vector<int> target_ranks;
    std::vector<int> target_bg;
    std::vector<int> target_banks;

    /* output */
    std::filesystem::path csv_path{ "results/bit_flips.csv" };

    /* formatted dump for logging */
    friend std::ostream& operator<<(std::ostream& os, const cli_params& p) {
        constexpr int W = 28;
        auto line       = [&](std::string_view lbl, auto&& val) {
            os << std::left << std::setw(W) << lbl << ": " << val << '\n';
        };

        auto join = [](const std::vector<int>& v) {
            std::ostringstream ss;
            for(std::size_t i = 0; i < v.size(); ++i) {
                if(i)
                    ss << ',';
                ss << v[i];
            }
            return ss.str();
        };

        line("cpu_core", p.cpu_core);
        line("sync_row_count", p.sync_row_count);
        line("sync_row_start", p.sync_row_start);

        line("ref_threshold", p.ref_threshold);
        line("self_sync_cycles", '[' + join(p.self_sync_cycles) + ']');
        line("reads_per_trefi", '[' + join(p.reads_per_trefi) + ']');
        line("trefi_sync_count", p.trefi_sync_count);

        line("aggressor_row_start", p.aggressor_row_start);
        line("aggressor_row_end", p.aggressor_row_end);
        line("aggressor_spacing", p.aggressor_spacing);
        line("column_stride", p.column_stride);
        line("pattern_trefi_offset_per_bank", p.pattern_trefi_offset_per_bank);

        line("hammer_fn", p.hammer_fn);
        line("pattern_id", p.pattern_id);

        line("target_subch", '[' + join(p.target_subch) + ']');
        line("target_ranks", '[' + join(p.target_ranks) + ']');
        line("target_bg", '[' + join(p.target_bg) + ']');
        line("target_banks", '[' + join(p.target_banks) + ']');

        line("csv_path", p.csv_path.string());
        return os;
    }
};

inline std::vector<int> parse_range(const std::string& input) {
    std::vector<int> values;

    size_t first_colon = input.find(':');
    if(first_colon == std::string::npos) {
        // Single value
        values.push_back(std::stoi(input));
    } else {
        size_t second_colon = input.find(':', first_colon + 1);
        if(second_colon == std::string::npos) {
            throw std::invalid_argument(
                "Range must be in the form start:end:step");
        }

        int start = std::stoi(input.substr(0, first_colon));
        int end = std::stoi(input.substr(first_colon + 1, second_colon - first_colon - 1));
        int step = std::stoi(input.substr(second_colon + 1));

        if(step <= 0) {
            throw std::invalid_argument("Step must be positive in range");
        }

        for(int val = start; val <= end; val += step) {
            values.push_back(val);
        }
    }

    return values;
}

cli_params parse_cli(int argc, char* argv[]) {
    cli_params p;
    CLI::App app{ "Phoenix" };

    //------------------------------------------------------------------
    // Validators
    //------------------------------------------------------------------
    const CLI::Validator even{ [](const std::string& v) {
                                  int n = std::stoi(v);
                                  if(n % 2 != 0)
                                      return std::string{ "value must be "
                                                          "divisible by 2" };
                                  return std::string{};
                              },
                               "even number" };

    app.add_option("-c,--core", p.cpu_core, "CPU core to pin the running process to")
        ->default_val(5);

    app.add_option("--sync-rows", p.sync_row_count, "Number of rows to use for synchronization")
        ->default_val(8);

    app.add_option("--sync-row-start", p.sync_row_start,
                   "Starting row index from which to allocate sync rows")
        ->default_val(512);

    //------------------------------------------------------------------
    // Timing knobs
    //------------------------------------------------------------------
    app.add_option("--self-sync-cycles", p.self_sync_cycles_str, "Self-synchronization delay thresholds for detecting missed REF commands (format: start:end:step). The program will fuzz these parameters.")
        ->default_val("23000:26000:1000");

    app.add_option("--reads-per-trefi", p.reads_per_trefi_str, "Number of memory reads to issue per tREFI interval (format: start:end:step). The program will fuzz these parameters.")
        ->default_val("86:92:2");

    app.add_option("--trefi-repeat", p.trefi_sync_count, "Number of tREFI intervals to execute the access pattern")
        ->default_val(2048000);

    app.add_option("--ref-threshold", p.ref_threshold, "Latency threshold to infer that a REF command occurred (by detecting access slowdowns)")
        ->default_val(1150);

    //------------------------------------------------------------------
    // Selectors
    //------------------------------------------------------------------
    app.add_option("--hammer-fn", p.hammer_fn, "Which hammer function to use (e.g., self_sync or seq_sync)");

    app.add_option("-p,--pattern", p.pattern_id,
                   "Which pattern to use (e.g., skh_mod128 or skh_mod2608)");

    //------------------------------------------------------------------
    // Pattern layout
    //------------------------------------------------------------------
    app.add_option("--aggressor-row-start", p.aggressor_row_start, "Starting row index for the first aggressor pair; each iteration advances this start row until --aggressor-row-end")
        ->default_val(0);

    app.add_option("--aggressor-row-end", p.aggressor_row_end, "Row index at which to stop advancing the first aggressor pair")
        ->default_val(8);

    app.add_option("--aggressor-spacing", p.aggressor_spacing, "Distance between each aggressor pair within the same bank (4 pairs tested per bank)")
        ->default_val(8);

    app.add_option("--column-stride", p.column_stride, "Stride in columns between adjacent memory accesses")
        ->default_val(512);

    app.add_option("--pattern-trefi-offset-per-bank",
                   p.pattern_trefi_offset_per_bank, "Number of tREFI intervals to offset pattern start time per additional bank (increases chance of hitting vulnerable REF alignment)")
        ->default_val(16)
        ->check(CLI::NonNegativeNumber);

    //------------------------------------------------------------------
    // Target selection
    //------------------------------------------------------------------
    app.add_option("-S,--target-subch", p.target_subch, "Index of the target subchannel (default: 0)")
        ->default_val(0)
        ->expected(1, -1);

    app.add_option("-R,--target-ranks", p.target_ranks, "Index of the target memory rank (default: 0)")
        ->default_val(0)
        ->expected(1, -1);

    app.add_option("-G,--target-bg", p.target_bg, "List of target bank groups to test (default: 0 1 2 3)")
        ->default_val(std::vector<int>{ 0, 1, 2, 3 })
        ->expected(1, -1);

    app.add_option("-B,--target-banks", p.target_banks,
                   "Index of the target bank within each group (default: 0)")
        ->default_val(0)
        ->expected(1, -1);

    //------------------------------------------------------------------
    // Output
    //------------------------------------------------------------------
    app.add_option("--csv", p.csv_path, "Path to output CSV file containing bit flip results");

    try {
        app.parse(argc, argv);
    } catch(const CLI::ParseError& e) {
        std::exit(app.exit(e));
    }

    //------------------------------------------------------------------
    // Post-parse range evaluation
    //------------------------------------------------------------------
    try {
        p.self_sync_cycles = parse_range(p.self_sync_cycles_str);
        p.reads_per_trefi  = parse_range(p.reads_per_trefi_str);
    } catch(const std::exception& e) {
        std::cerr << "Failed to parse --self-sync-cycles or --reads-per-trefi: "
                  << e.what() << "\n";
        std::exit(1);
    }

    return p;
}
