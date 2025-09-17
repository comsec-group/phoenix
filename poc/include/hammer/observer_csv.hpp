#pragma once

#include "bit_flips.hpp"
#include "observer.hpp"
#include "time_utils.hpp"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <sys/stat.h>
#include <unistd.h>
#include <utility>
#include <vector>

namespace fs = std::filesystem;

class CsvWriterObserver final : public IHammerObserver {
    public:
    explicit CsvWriterObserver(fs::path file_path)
    : csv_path_{ std::move(file_path) } {
        if(csv_path_.empty()) {
            throw std::invalid_argument("CsvWriterObserver: empty file path");
        }
        fs::create_directories(csv_path_.parent_path());

        constexpr char kHeader[] =
            "timestamp,reads_per_trefi,sync_cycles_threshold,row_base_offset,"
            "virt_addr,subch,rank,bg,bank,row,col,expected_hex,actual_hex";

        bool needs_header = true;
        if(fs::exists(csv_path_) && fs::file_size(csv_path_) > 0) {
            std::ifstream probe(csv_path_);
            std::string first_line;
            std::getline(probe, first_line);
            needs_header = first_line.rfind(kHeader, 0) != 0; // header missing?
        }

        csv_.open(csv_path_, std::ios::out | std::ios::app);
        if(!csv_) {
            throw std::runtime_error("Cannot open " + csv_path_.string());
        }

        if(needs_header) {
            csv_ << kHeader << '\n';
        }

        if(geteuid() == 0) {
            const char* sudo_uid = std::getenv("SUDO_UID");
            const char* sudo_gid = std::getenv("SUDO_GID");

            if(sudo_uid && sudo_gid) {
                uid_t uid = static_cast<uid_t>(std::stoi(sudo_uid));
                gid_t gid = static_cast<gid_t>(std::stoi(sudo_gid));

                if(chown(csv_path_.c_str(), uid, gid) != 0) {
                    std::cerr << "[!] Warning: Failed to chown CSV to invoking "
                                 "user\n";
                }
            } else {
                std::cerr << "[!] Warning: SUDO_UID or SUDO_GID not set\n";
            }
        }
    }

    void on_pre_iteration(const FuzzPoint&) override {
    }

    void on_post_iteration(const FuzzPoint& fp, const std::vector<bit_flip_t>& flips) override {
        if(flips.empty()) {
            return;
        }

        std::vector<bit_flip_t> sorted = flips;
        std::sort(sorted.begin(), sorted.end(), [](const bit_flip_t& lhs_bf, const bit_flip_t& rhs_bf) {
            const dram_address& lhs = lhs_bf.address;
            const dram_address& rhs = rhs_bf.address;
            return std::make_tuple(lhs.subchannel(), lhs.rank(), lhs.bank_group(),
                                   lhs.bank(), lhs.row(), lhs.column()) <
                std::make_tuple(rhs.subchannel(), rhs.rank(), rhs.bank_group(),
                                rhs.bank(), rhs.row(), rhs.column());
        });

        for(const auto& bf : sorted) {
            const dram_address& a = bf.address;
            auto vaddr = reinterpret_cast<std::uintptr_t>(a.to_virt());

            csv_ << iso_timestamp() << ',' << fp.pattern_reads_per_trefi << ','
                 << fp.self_sync_threshold << ',' << fp.agg_base_row << ','
                 << "0x" << std::uppercase << std::hex << vaddr << std::dec << ','
                 << a.subchannel() << ',' << a.rank() << ',' << a.bank_group()
                 << ',' << a.bank() << ',' << a.row() << ',' << a.column()
                 << ',' << "0x" << std::uppercase << std::hex << std::setw(2)
                 << std::setfill('0') << static_cast<unsigned>(bf.expected_value)
                 << ',' << "0x" << std::setw(2) << std::setfill('0')
                 << static_cast<unsigned>(bf.actual_value) << std::dec << '\n';
        }
        csv_.flush(); // make data visible immediately
    }

    const fs::path& path() const noexcept {
        return csv_path_;
    }

    private:
    fs::path csv_path_;
    std::ofstream csv_;
};
