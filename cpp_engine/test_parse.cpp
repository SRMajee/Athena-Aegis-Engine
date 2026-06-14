#include "utilities/occ_utils.hpp"
#include <iostream>
#include <iomanip>

int main() {
    std::string test_sym = "SPY   101022C00107000";
    auto [expiry, strike, opt_type] = backtest::parse_occ_symbol(test_sym);
    
    if (!expiry) {
        std::cout << "Expiry is nullopt!" << std::endl;
    } else {
        auto t = std::chrono::system_clock::to_time_t(*expiry);
        std::tm tm_utc{};
#ifdef _WIN32
        gmtime_s(&tm_utc, &t);
#else
        gmtime_r(&t, &tm_utc);
#endif
        std::cout << "Expiry: " << std::put_time(&tm_utc, "%Y-%m-%d %H:%M:%S") << std::endl;
    }
    
    if (!strike) {
        std::cout << "Strike is nullopt!" << std::endl;
    } else {
        std::cout << "Strike: " << *strike << std::endl;
    }
    
    if (!opt_type) {
        std::cout << "OptionType is nullopt!" << std::endl;
    } else {
        std::cout << "OptionType: " << (*opt_type == utilities::OptionType::CALL ? "CALL" : "PUT") << std::endl;
    }
    return 0;
}
