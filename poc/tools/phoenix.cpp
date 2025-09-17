#include <functional>

#include <array>
#include <cerrno>
#include <climits>
#include <cstring>
#include <iostream>
#include <sched.h>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unistd.h>
#include <vector>

#include <hammer/allocation.hpp>
#include <hammer/dram_address.hpp>
#include <hammer/jitted.hpp>
#include <hammer/observer_csv.hpp>
#include <hammer/observer_fanout.hpp>
#include <hammer/observer_progress.hpp>
#include <hammer/pagemap.hpp>

#include <CLI/CLI.hpp>

#include "phoenix_cli.hpp"

#define SUPERPAGE_MEM_SIZE (1UL << 30)

void configure_unbuffered_output() {
    setvbuf(stdout, nullptr, _IONBF, 0);
    setvbuf(stderr, nullptr, _IONBF, 0);
}

void allocate_single_superpage(int dimm_size_gib, int dimm_ranks) {
    std::cout << "[+] Allocating single superpage with:\n"
              << "    DIMM size: " << dimm_size_gib << " GiB\n"
              << "    DIMM ranks: " << dimm_ranks << std::endl;

    allocation alloc;

    alloc.allocate(1);
    dram_address::initialize(std::move(alloc), dimm_size_gib, dimm_ranks);

    void* mem         = dram_address::alloc().ptr();
    auto mem_addr_phy = vaddr2paddr(reinterpret_cast<uint64_t>(mem));

    std::cout << "[+] Mapped 0x" << std::hex << SUPERPAGE_MEM_SIZE
              << " Bytes at vaddr=0x" << reinterpret_cast<uint64_t>(mem)
              << ", paddr=0x" << mem_addr_phy << std::dec << std::endl;
}

const std::unordered_map<std::string_view, hammer_fn_t> kHammerFnRegistry{
    { "self_sync", &hammer_jitted_self_sync },
    { "seq_sync", &hammer_jitted_seq_sync }
};

hammer_fn_t resolve_hammer_fn(std::string_view name) {
    if(const auto it = kHammerFnRegistry.find(name); it != kHammerFnRegistry.end()) {
        return it->second;
    }
    throw std::invalid_argument("unknown hammer function: " + std::string(name));
}

const std::unordered_map<std::string_view, bank_pattern_builder_t> kPatternRegistry{
    { "skh_mod128", &assemble_skh_mod128_pattern },
    { "skh_mod2608", &assemble_skh_mod2608_pattern }
};

bank_pattern_builder_t resolve_pattern_builder(std::string_view name) {
    if(const auto it = kPatternRegistry.find(name); it != kPatternRegistry.end()) {
        return it->second;
    }
    throw std::invalid_argument("unknown pattern: " + std::string(name));
}

void set_thread_affinity(int core_id) {
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(core_id, &cpuset);
    pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset);
}

std::vector<dram_address> get_sync_rows(const cli_params& p) {
    std::vector<dram_address> addrs;
    addrs.reserve(p.sync_row_count);

    for(int row = p.sync_row_start;
        addrs.size() < static_cast<size_t>(p.sync_row_count); ++row) {
        for(int sc : p.target_subch) {
            for(int rk : p.target_ranks) {
                for(int bg : p.target_bg) {
                    for(int bk : p.target_banks) {
                        addrs.emplace_back(sc, rk, bg, bk, row, 0);
                    }
                }
            }
        }
    }
    addrs.resize(p.sync_row_count); // truncate if we over‑shot
    return addrs;
}

bool elevate_to_max_priority() {
    int max_priority = sched_get_priority_max(SCHED_FIFO);
    if(max_priority == -1) {
        std::cerr << "Failed to get max priority: " << strerror(errno) << std::endl;
        return false;
    }

    sched_param param{};
    param.sched_priority = max_priority;

    if(sched_setscheduler(0, SCHED_FIFO, &param) == -1) {
        std::cerr << "Failed to set scheduler: " << strerror(errno) << std::endl;
        return false;
    }

    return true;
}

std::string run_command(const std::string& cmd) {
    std::array<char, 256> buffer{};
    std::string result;

    // Use unique_ptr for RAII-safe pipe closing
    std::unique_ptr<FILE, decltype(&pclose)> pipe(popen(cmd.c_str(), "r"), pclose);
    if(!pipe) {
        throw std::runtime_error("popen() failed!");
    }

    while(fgets(buffer.data(), static_cast<int>(buffer.size()), pipe.get()) != nullptr) {
        result.append(buffer.data());
    }

    return result;
}

int detect_ranks() {
    std::string output = run_command("sudo dmidecode -t memory");
    std::istringstream iss(output);
    std::string line;

    for(; std::getline(iss, line);) {
        if(line.find("Rank:") != std::string::npos) {
            std::string value = line.substr(line.find(":") + 1);
            value.erase(0, value.find_first_not_of(" \t")); // Trim leading space
            if(!value.empty() && value != "Unknown") {
                return std::stoi(value);
            }
        }
    }

    throw std::runtime_error("No valid Rank found.");
}

int detect_dimm_gib() {
    std::string output = run_command("sudo dmidecode -t memory");
    std::istringstream iss(output);
    std::string line;
    int min_gib           = INT_MAX;
    bool found_valid_dimm = false;

    while(std::getline(iss, line)) {
        if(line.find("Size:") == std::string::npos ||
           line.find("No Module") != std::string::npos)
            continue;

        std::string value = line.substr(line.find(":") + 1);
        std::istringstream valss(value);
        int size;
        std::string unit;
        valss >> size >> unit;

        if(size == 0)
            continue;

        int gib = (unit == "MB") ? size / 1024 : size;
        if(gib > 0) {
            found_valid_dimm = true;
            if(gib < min_gib) {
                min_gib = gib;
            }
        }
    }

    if(!found_valid_dimm || min_gib == INT_MAX || min_gib == 0) {
        throw std::runtime_error("No valid non-zero DIMM size found.");
    }

    return min_gib;
}

// Helper to trim whitespace from both ends of a string
static std::string trim(const std::string& s) {
    auto first = s.find_first_not_of(" \t\n\r");
    if(first == std::string::npos)
        return "";
    auto last = s.find_last_not_of(" \t\n\r");
    return s.substr(first, last - first + 1);
}

// Uses your existing run_command() helper
static std::string get_cpu_model_string() {
    // Grab the first "model name" line, strip off the "model name : " prefix
    const std::string cmd =
        "grep \"model name\" /proc/cpuinfo | head -1 | cut -d: -f2-";
    std::string raw = run_command(cmd);
    return trim(raw);
}

int main(int argc, char* argv[]) {
    auto params = parse_cli(argc, argv);

    static constexpr std::array<const char*, 1> AllowedModels = {
        "AMD Ryzen 7 7700X 8-Core Processor"
    };

    try {
        auto cpu_model = get_cpu_model_string();
        std::cout << "CPU model: " << cpu_model << '\n';
    } catch(const std::exception& e) {
        std::cerr << "Failed to detect CPU model: " << e.what() << '\n';
        return EXIT_FAILURE;
    }

    if(geteuid() != 0) {
        std::cerr << "[!] This program must be run with sudo/root privileges." << std::endl;
        return EXIT_FAILURE;
    }

    if(!elevate_to_max_priority()) {
        std::cerr << "Warning: Running without elevated priority.\n";
    } else {
        std::cout << "Running with maximum scheduling priority.\n";
    }

    configure_unbuffered_output();

    std::cout << params << '\n';

    int dimm_ranks    = detect_ranks();
    int dimm_size_gib = detect_dimm_gib();
    allocate_single_superpage(dimm_size_gib, dimm_ranks);

    auto hammer_fn       = resolve_hammer_fn(params.hammer_fn);
    auto pattern_builder = resolve_pattern_builder(params.pattern_id);

    int total_iterations = params.reads_per_trefi.size() *
        params.self_sync_cycles.size() *
        (params.aggressor_row_end - params.aggressor_row_start);
    ProgressBarObserver ui(total_iterations);
    CsvWriterObserver csv(params.csv_path);
    FanOutObserver observer{ { &ui, &csv } };

    set_thread_affinity(params.cpu_core);

    constexpr uint64_t aggressor_fill = 0x0068'0005'5555'5FD3ULL;
    constexpr uint64_t victim_fill    = 0x0068'000A'AAAA'AFD3ULL;

    auto sync_rows = get_sync_rows(params);
    std::cout << "Sync rows:" << '\n';
    for(const auto& sync_row : sync_rows) {
        std::cout << sync_row.to_string() << '\n';
    }

    for(int row = params.aggressor_row_start; row < params.aggressor_row_end; ++row) {
        for(int reads : params.reads_per_trefi) {
            for(int sync_cycles : params.self_sync_cycles) {

                auto pat = assemble_multi_bank_pattern(
                    pattern_builder, params.target_subch, params.target_ranks,
                    params.target_bg, params.target_banks, row, reads, params.column_stride,
                    params.pattern_trefi_offset_per_bank, params.aggressor_spacing);

                auto aggressors = pattern_aggressors(pat);
                auto victims    = pattern_victims(pat);

                initialize_data_pattern(aggressors, aggressor_fill);
                initialize_data_pattern(victims, victim_fill);

                FuzzPoint fp{ row, reads, pat, sync_cycles, row };

                observer.on_pre_iteration(fp);

                hammer_fn(pat, sync_rows, params.ref_threshold,
                          params.trefi_sync_count, sync_cycles);

                auto flips = collect_bit_flips(victims, victim_fill);
                observer.on_post_iteration(fp, flips);
            }
        }
    }

    return 0;
}
