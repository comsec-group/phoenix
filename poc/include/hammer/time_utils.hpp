#pragma once

#include <chrono>
#include <ctime>
#include <string>

/// ISO‑8601 timestamp (local time) – "YYYY-MM-DDTHH:MM:SS"
inline std::string iso_timestamp() {
    auto now      = std::chrono::system_clock::now();
    std::time_t t = std::chrono::system_clock::to_time_t(now);
    std::tm tm{};
    if(localtime_r(&t, &tm) == nullptr) {
        return "0000-00-00T00:00:00";
    }

    char buf[20]; // "YYYY-MM-DDTHH:MM:SS"
    std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S", &tm);
    return buf;
}

/// Compact timestamp suitable for directory names – "YYYYMMDD_HHMMSS"
inline std::string ymd_hms_timestamp() {
    auto now      = std::chrono::system_clock::now();
    std::time_t t = std::chrono::system_clock::to_time_t(now);
    std::tm tm{};
    if(localtime_r(&t, &tm) == nullptr) {
        return "00000000_000000";
    }

    char buf[16]; // "YYYYMMDD_HHMMSS"
    std::strftime(buf, sizeof(buf), "%Y%m%d_%H%M%S", &tm);
    return buf;
}
