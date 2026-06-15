#pragma once
#include "template.hpp"

#include <cmath>
#include <deque>
#include <numeric>
#include <string>

namespace strategy_cpp {

/**
 * IvMeanRevertStrategy
 *
 * Trades ATM straddles based on IV Z-score mean reversion.
 * Maintains a rolling window of ATM IV observations.
 * When IV spikes > z_entry_threshold above the rolling mean, sells a straddle.
 * When IV drops > z_entry_threshold below the mean, buys a straddle.
 * Exits at z_exit_threshold or after max_hold_ticks ticks.
 */
class IvMeanRevertStrategy : public OptionStrategyTemplate {
  public:
    using OptionStrategyTemplate::OptionStrategyTemplate;

    void on_init_logic() override {
        if (auto it = setting_.find("window_size"); it != setting_.end())
            window_size_ = static_cast<int>(it->second);
        if (auto it = setting_.find("z_entry"); it != setting_.end())
            z_entry_ = it->second;
        if (auto it = setting_.find("z_exit"); it != setting_.end())
            z_exit_ = it->second;
        if (auto it = setting_.find("max_hold_ticks"); it != setting_.end())
            max_hold_ticks_ = static_cast<int>(it->second);
        if (auto it = setting_.find("min_dte"); it != setting_.end())
            min_dte_ = static_cast<int>(it->second);
        if (auto it = setting_.find("max_dte"); it != setting_.end())
            max_dte_ = static_cast<int>(it->second);

        write_log("IvMeanRevert initialized: window=" + std::to_string(window_size_) +
                  " z_entry=" + std::to_string(z_entry_) +
                  " z_exit=" + std::to_string(z_exit_));
    }

    void on_stop_logic() override {
        close_all_strategy_positions();
    }

    void on_timer_logic() override {
        if (!portfolio() || !underlying()) return;

        tick_count_++;

        // Find a chain to trade
        if (active_chain_sym_.empty() || !position_open_) {
            auto chain_symbols = portfolio()->get_chain_by_expiry(min_dte_, max_dte_);
            if (chain_symbols.empty())
                chain_symbols = portfolio()->get_chain_by_expiry(0, 30);
            if (chain_symbols.empty()) return;
            if (chain_symbols[0] != active_chain_sym_) {
                active_chain_sym_ = chain_symbols[0];
                subscribe_chains(std::span<const std::string>(&active_chain_sym_, 1));
            }
        }

        auto* chain = get_chain(active_chain_sym_);
        if (!chain) return;

        chain->calculate_atm_price();
        auto atm_iv = chain->get_atm_iv();
        if (!atm_iv || *atm_iv <= 0.0) return;

        // Add to rolling window
        iv_window_.push_back(*atm_iv);
        if (static_cast<int>(iv_window_.size()) > window_size_) {
            iv_window_.pop_front();
        }

        // Need full window before trading
        if (static_cast<int>(iv_window_.size()) < window_size_) return;

        // Compute Z-score
        double mean = std::accumulate(iv_window_.begin(), iv_window_.end(), 0.0) /
                       static_cast<double>(iv_window_.size());
        double variance = 0.0;
        for (double v : iv_window_) {
            double diff = v - mean;
            variance += diff * diff;
        }
        variance /= static_cast<double>(iv_window_.size());
        double stddev = std::sqrt(variance);
        if (stddev < 1e-8) return;

        double z_score = (*atm_iv - mean) / stddev;

        // Manage existing position
        if (position_open_) {
            hold_ticks_++;

            // Exit on Z-score reversal or timeout
            bool should_exit = false;
            if (is_short_vol_ && z_score < z_exit_) should_exit = true;
            if (!is_short_vol_ && z_score > -z_exit_) should_exit = true;
            if (hold_ticks_ >= max_hold_ticks_) should_exit = true;

            if (should_exit) {
                write_log("Closing IV mean-revert position: z=" + std::to_string(z_score) +
                          " hold=" + std::to_string(hold_ticks_));
                close_all_strategy_positions();
                position_open_ = false;
                hold_ticks_ = 0;
            }
            return;
        }

        // Entry logic
        if (chain->atm_index.empty()) return;
        auto call_it = chain->calls.find(chain->atm_index);
        auto put_it = chain->puts.find(chain->atm_index);
        if (call_it == chain->calls.end() || put_it == chain->puts.end()) return;

        utilities::OptionData* atm_call = call_it->second;
        utilities::OptionData* atm_put = put_it->second;
        if (atm_call->bid_price <= 0 || atm_put->bid_price <= 0) return;

        std::unordered_map<std::string, utilities::OptionData*> option_data;
        option_data["call"] = atm_call;
        option_data["put"] = atm_put;

        if (z_score > z_entry_) {
            // IV too high → sell straddle (vol will revert down)
            auto ids = option_order(utilities::ComboType::STRADDLE, option_data,
                                    utilities::Direction::SHORT, 0.0, 1.0,
                                    utilities::OrderType::MARKET);
            if (!ids.empty()) {
                position_open_ = true;
                is_short_vol_ = true;
                hold_ticks_ = 0;
                write_log("Short vol entry: z=" + std::to_string(z_score) +
                          " iv=" + std::to_string(*atm_iv));
            }
        } else if (z_score < -z_entry_) {
            // IV too low → buy straddle (vol will revert up)
            auto ids = option_order(utilities::ComboType::STRADDLE, option_data,
                                    utilities::Direction::LONG, 0.0, 1.0,
                                    utilities::OrderType::MARKET);
            if (!ids.empty()) {
                position_open_ = true;
                is_short_vol_ = false;
                hold_ticks_ = 0;
                write_log("Long vol entry: z=" + std::to_string(z_score) +
                          " iv=" + std::to_string(*atm_iv));
            }
        }
    }

  private:
    // Parameters
    int window_size_ = 5;
    double z_entry_ = 0.5;
    double z_exit_ = 0.1;
    int max_hold_ticks_ = 60;
    int min_dte_ = 0;
    int max_dte_ = 14;

    // State
    std::deque<double> iv_window_;
    bool position_open_ = false;
    bool is_short_vol_ = false;
    int hold_ticks_ = 0;
    int tick_count_ = 0;
    std::string active_chain_sym_;
};

} // namespace strategy_cpp
