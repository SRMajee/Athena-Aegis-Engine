#include "occ_utils.hpp"
#include "constant.hpp"
#include <array>
#include <chrono>
#include <cstdlib>
#include <ctime>
#include <sstream>
#include <stdexcept>
#include <vector>
#ifdef _WIN32
#include <windows.h>
#endif

namespace backtest {

namespace {
using namespace utilities;
}

auto parse_occ_symbol(const std::string& symbol)
    -> std::tuple<std::optional<Timestamp>, std::optional<double>, std::optional<OptionType>> {
    std::string occ_part = symbol;
    if (symbol.size() >= 15U) {
        occ_part = symbol.substr(symbol.size() - 15U);
    }
    if (occ_part.size() < 15U) {
        return {std::nullopt, std::nullopt, std::nullopt};
    }
    try {
        int yy = std::stoi(occ_part.substr(0, 2));
        int mm = std::stoi(occ_part.substr(2, 2));
        int dd = std::stoi(occ_part.substr(4, 2));
        int year = (yy < 80) ? (2000 + yy) : (1900 + yy);
        // Expiry 16:00 ET = 21:00 UTC; build UTC tm and convert to time_t without touching TZ
        std::tm tm_utc{};
        tm_utc.tm_year = year - 1900;
        tm_utc.tm_mon = mm - 1;
        tm_utc.tm_mday = dd;
        tm_utc.tm_hour = 21;
        tm_utc.tm_min = 0;
        tm_utc.tm_sec = 0;
        tm_utc.tm_isdst = 0;
        std::time_t t = 0;
#ifdef _WIN32
        t = _mkgmtime(&tm_utc);
#else
        t = timegm(&tm_utc);
#endif
        if (t == -1) {
            return {std::nullopt, std::nullopt, std::nullopt};
        }
        Timestamp expiry = std::chrono::system_clock::from_time_t(t);

        char cp = static_cast<char>(std::toupper(static_cast<unsigned char>(occ_part[6])));
        if (cp != 'C' && cp != 'P') {
            return {std::nullopt, std::nullopt, std::nullopt};
        }
        double strike = std::stoi(occ_part.substr(7, 8)) / 1000.0;
        OptionType opt_type = (cp == 'C') ? OptionType::CALL : OptionType::PUT;
        return {expiry, strike, opt_type};
    } catch (...) {
        return {std::nullopt, std::nullopt, std::nullopt};
    }
}

auto infer_underlying_from_filename(const std::string& filename) -> std::string {
    // Standardize slashes to forward slash
    std::string path_std = filename;
    for (char& c : path_std) {
        if (c == '\\') {
            c = '/';
        }
    }

    // Split path by '/'
    std::vector<std::string> parts;
    std::string part;
    std::istringstream iss(path_std);
    while (std::getline(iss, part, '/')) {
        if (!part.empty()) {
            parts.push_back(part);
        }
    }

    // Traverse parts to find the symbol under 'data'
    for (size_t i = 0; i < parts.size(); ++i) {
        std::string p = parts[i];
        for (char& c : p) {
            c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        }
        if (p == "data" && i + 1 < parts.size()) {
            std::string symbol = parts[i + 1];
            std::string symbol_lower = symbol;
            for (char& c : symbol_lower) {
                c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
            }
            if (symbol_lower == "temp" && i + 2 < parts.size()) {
                symbol = parts[i + 2];
            }
            // Strip any suffix like "-2025-08"
            auto dash = symbol.find('-');
            if (dash != std::string::npos) {
                symbol = symbol.substr(0, dash);
            }
            // Capitalize and return
            for (char& c : symbol) {
                c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
            }
            return symbol;
        }
    }

    // Fallback filename-based logic
    std::string name = filename;
    auto pos = name.find_last_of("/\\");
    if (pos != std::string::npos) {
        name = name.substr(pos + 1);
    }
    pos = name.find('.');
    if (pos != std::string::npos) {
        name = name.substr(0, pos);
    }

    // backtest_ prefix
    if (name.size() >= 9 && name.starts_with("backtest_")) {
        pos = name.find('_', 9);
        if (pos == std::string::npos) {
            return "";
        }
        std::string underlying = name.substr(9, pos - 9);
        for (char& c : underlying) {
            c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
        }
        return underlying;
    }

    return "";
}

auto format_expiry_yyyymmdd(Timestamp expiry) -> std::string {
    auto t = std::chrono::system_clock::to_time_t(expiry);
    std::tm* tm = std::gmtime(&t);
    if (tm == nullptr) {
        return "";
    }
    std::array<char, 16> buf{};
    std::snprintf(buf.data(), buf.size(), "%04d%02d%02d", tm->tm_year + 1900, tm->tm_mon + 1,
                  tm->tm_mday);
    return buf.data();
}

} // namespace backtest
