#pragma once
#include "template.hpp"

#include <cmath>
#include <string>
#include <ctime>

namespace strategy_cpp {

/**
 * StraddleTestStrategy
 *
 * Sells an ATM straddle on the nearest-expiry chain (0–7 DTE).
 * Manages with take-profit at 30% of premium received and stop-loss at 50%.
 * Registers delta-hedging every 5 ticks to stay delta-neutral.
 */
class StraddleTestStrategy : public OptionStrategyTemplate {
  public:
    using OptionStrategyTemplate::OptionStrategyTemplate;

    void on_init_logic() override {
        // Read configurable parameters from strategy settings
        if (auto it = setting_.find("min_dte"); it != setting_.end())
            min_dte_ = static_cast<int>(it->second);
        if (auto it = setting_.find("max_dte"); it != setting_.end())
            max_dte_ = static_cast<int>(it->second);
        if (auto it = setting_.find("take_profit_pct"); it != setting_.end())
            take_profit_pct_ = it->second;
        if (auto it = setting_.find("stop_loss_pct"); it != setting_.end())
            stop_loss_pct_ = it->second;

        register_hedging(5, 0, 10);
        last_day_ = -1;
        tick_count_ = 0;
        write_log("StraddleTest initialized: DTE=[" + std::to_string(min_dte_) + "," +
                  std::to_string(max_dte_) + "] TP=" + std::to_string(take_profit_pct_) +
                  " SL=" + std::to_string(stop_loss_pct_));
    }

    void on_stop_logic() override {
        close_all_strategy_positions();
        unregister_hedging();
    }

    void on_timer_logic() override {
        if (!portfolio() || !underlying()) return;

        auto current_time = portfolio()->dte_ref();
        std::time_t tt = std::chrono::system_clock::to_time_t(current_time);
        std::tm tm{};
#if defined(_WIN32)
        gmtime_s(&tm, &tt);
#else
        gmtime_r(&tt, &tm);
#endif
        int current_day = tm.tm_yday + tm.tm_year * 1000;
        if (current_day != last_day_) {
            last_day_ = current_day;
            tick_count_ = 0;
        }

        tick_count_++;

        // If we have a position, manage it
        if (position_open_) {
            manage_position();
            return;
        }

        // Only enter once per day (first few ticks)
        if (tick_count_ > 5) return;

        // Find nearest-expiry chain
        auto chain_symbols = portfolio()->get_chain_by_expiry(min_dte_, max_dte_);
        write_log("Found " + std::to_string(chain_symbols.size()) + " chains for DTE range [" + std::to_string(min_dte_) + "," + std::to_string(max_dte_) + "]");
        if (chain_symbols.empty()) {
            // Try wider range
            chain_symbols = portfolio()->get_chain_by_expiry(0, 30);
            write_log("Found " + std::to_string(chain_symbols.size()) + " chains for DTE range [0,30]");
        }
        if (chain_symbols.empty()) return;

        // Subscribe to the first chain
        subscribe_chains(std::span<const std::string>(chain_symbols.data(), 1));
        auto* chain = get_chain(chain_symbols[0]);
        if (!chain) return;

        // Need ATM index
        chain->calculate_atm_price();
        if (chain->atm_index.empty()) return;

        // Get ATM call and put
        auto call_it = chain->calls.find(chain->atm_index);
        auto put_it = chain->puts.find(chain->atm_index);
        if (call_it == chain->calls.end() || put_it == chain->puts.end()) return;

        utilities::OptionData* atm_call = call_it->second;
        utilities::OptionData* atm_put = put_it->second;

        // Need valid prices
        if (atm_call->bid_price <= 0 || atm_put->bid_price <= 0) return;

        // Sell ATM straddle (SHORT direction, MARKET order)
        std::unordered_map<std::string, utilities::OptionData*> option_data;
        option_data["call"] = atm_call;
        option_data["put"] = atm_put;

        auto order_ids = option_order(
            utilities::ComboType::STRADDLE, option_data,
            utilities::Direction::SHORT, 0.0, 1.0,
            utilities::OrderType::MARKET);

        if (!order_ids.empty()) {
            position_open_ = true;
            entry_premium_ = atm_call->bid_price + atm_put->bid_price;
            entry_tick_ = tick_count_;
            chain_symbol_ = chain_symbols[0];
            write_log("Opened short straddle: premium=" + std::to_string(entry_premium_) +
                      " chain=" + chain_symbol_);
        }
    }

  private:
    void manage_position() {
        if (!holding()) return;

        double current_pnl = holding()->summary.pnl;
        double premium_100 = entry_premium_ * 100.0; // multiply by contract size

        // Take profit: 30% of premium received
        if (current_pnl >= premium_100 * take_profit_pct_) {
            write_log("Take profit triggered: pnl=" + std::to_string(current_pnl));
            close_all_strategy_positions();
            position_open_ = false;
            return;
        }

        // Stop loss: 50% of premium
        if (current_pnl <= -premium_100 * stop_loss_pct_) {
            write_log("Stop loss triggered: pnl=" + std::to_string(current_pnl));
            close_all_strategy_positions();
            position_open_ = false;
            return;
        }
    }

    // Configurable parameters
    int min_dte_ = 0;
    int max_dte_ = 7;
    double take_profit_pct_ = 0.30;
    double stop_loss_pct_ = 0.50;

    // State
    bool position_open_ = false;
    double entry_premium_ = 0.0;
    int entry_tick_ = 0;
    int tick_count_ = 0;
    int last_day_ = -1;
    std::string chain_symbol_;
};

} // namespace strategy_cpp
