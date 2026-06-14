#pragma once
#include "template.hpp"

#include <cmath>
#include <deque>
#include <numeric>
#include <string>

namespace strategy_cpp {

/**
 * StraddleInventoryScalperStrategy
 *
 * Continuously scalps ATM straddles on the nearest-expiry chain.
 * Maintains a rolling window of ATM IV.
 * - Sells an ATM straddle when IV is high (Z-score > z_entry_) and inventory > -max_inventory_
 * - Buys an ATM straddle when IV is low (Z-score < -z_entry_) and inventory < max_inventory_
 * - Gradually closes out / scalps positions as IV reverts toward the mean (Z-score near 0)
 * - Uses auto-hedging to manage delta risk.
 */
class StraddleInventoryScalperStrategy : public OptionStrategyTemplate {
  public:
    using OptionStrategyTemplate::OptionStrategyTemplate;

    void on_init_logic() override {
        if (auto it = setting_.find("window_size"); it != setting_.end())
            window_size_ = static_cast<int>(it->second);
        if (auto it = setting_.find("z_entry"); it != setting_.end())
            z_entry_ = it->second;
        if (auto it = setting_.find("z_exit"); it != setting_.end())
            z_exit_ = it->second;
        if (auto it = setting_.find("max_inventory"); it != setting_.end())
            max_inventory_ = static_cast<int>(it->second);
        if (auto it = setting_.find("min_dte"); it != setting_.end())
            min_dte_ = static_cast<int>(it->second);
        if (auto it = setting_.find("max_dte"); it != setting_.end())
            max_dte_ = static_cast<int>(it->second);

        // Turn on auto delta-hedging to manage delta risk from inventory accumulation
        register_hedging(5, 0, 15);

        write_log("StraddleInventoryScalper initialized: window=" + std::to_string(window_size_) +
                  " z_entry=" + std::to_string(z_entry_) +
                  " max_inv=" + std::to_string(max_inventory_));
    }

    void on_stop_logic() override {
        close_all_strategy_positions();
        unregister_hedging();
    }

    void on_timer_logic() override {
        if (!portfolio() || !underlying()) return;

        tick_count_++;

        // Find chain
        if (active_chain_sym_.empty()) {
            auto chain_symbols = portfolio()->get_chain_by_expiry(min_dte_, max_dte_);
            if (chain_symbols.empty())
                chain_symbols = portfolio()->get_chain_by_expiry(0, 30);
            if (chain_symbols.empty()) return;
            active_chain_sym_ = chain_symbols[0];
            subscribe_chains(std::span<const std::string>(&active_chain_sym_, 1));
        }

        auto* chain = get_chain(active_chain_sym_);
        if (!chain) return;

        chain->calculate_atm_price();
        auto atm_iv = chain->get_atm_iv();
        if (!atm_iv || *atm_iv <= 0.0) return;

        // Maintain rolling window
        iv_window_.push_back(*atm_iv);
        if (static_cast<int>(iv_window_.size()) > window_size_) {
            iv_window_.pop_front();
        }

        if (static_cast<int>(iv_window_.size()) < window_size_) return;

        // Compute Z-score
        double sum = std::accumulate(iv_window_.begin(), iv_window_.end(), 0.0);
        double mean = sum / iv_window_.size();
        double variance = 0.0;
        for (double v : iv_window_) {
            double diff = v - mean;
            variance += diff * diff;
        }
        variance /= iv_window_.size();
        double stddev = std::sqrt(variance);
        if (stddev < 1e-8) stddev = 1e-8;

        double z_score = (*atm_iv - mean) / stddev;

        // Determine current position inventory
        int current_inventory = get_current_inventory();

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

        // Scalping signals
        if (z_score > z_entry_ && current_inventory > -max_inventory_) {
            // High IV -> Sell straddle
            auto ids = option_order(utilities::ComboType::STRADDLE, option_data,
                                    utilities::Direction::SHORT, 0.0, 1.0,
                                    utilities::OrderType::MARKET);
            if (!ids.empty()) {
                write_log("Scalper entry SELL: inventory=" + std::to_string(current_inventory - 1) +
                          " z=" + std::to_string(z_score) + " iv=" + std::to_string(*atm_iv));
            }
        }
        else if (z_score < -z_entry_ && current_inventory < max_inventory_) {
            // Low IV -> Buy straddle
            auto ids = option_order(utilities::ComboType::STRADDLE, option_data,
                                    utilities::Direction::LONG, 0.0, 1.0,
                                    utilities::OrderType::MARKET);
            if (!ids.empty()) {
                write_log("Scalper entry BUY: inventory=" + std::to_string(current_inventory + 1) +
                          " z=" + std::to_string(z_score) + " iv=" + std::to_string(*atm_iv));
            }
        }
        else if (std::abs(z_score) < z_exit_ && current_inventory != 0) {
            // IV reverted back to mean -> Close inventory toward 0
            utilities::Direction dir = (current_inventory > 0) ? utilities::Direction::SHORT : utilities::Direction::LONG;
            auto ids = option_order(utilities::ComboType::STRADDLE, option_data,
                                    dir, 0.0, 1.0,
                                    utilities::OrderType::MARKET);
            if (!ids.empty()) {
                write_log("Scalper exit/revert: inventory=" + std::to_string(current_inventory + (current_inventory > 0 ? -1 : 1)) +
                          " z=" + std::to_string(z_score));
            }
        }
    }

  private:
    int get_current_inventory() {
        if (!holding()) return 0;
        int calls = 0;
        int puts = 0;
        for (auto& [sym, pos] : holding()->optionPositions) {
            if (pos.quantity == 0) continue;
            // Classify by option type if possible, or simple symbol parse
            if (sym.find("C") != std::string::npos) {
                calls += pos.quantity;
            } else if (sym.find("P") != std::string::npos) {
                puts += pos.quantity;
            }
        }
        // Return average quantity (since straddle contains 1 call and 1 put)
        return (calls + puts) / 2;
    }

    // Parameters
    int window_size_ = 15;
    double z_entry_ = 1.0;
    double z_exit_ = 0.2;
    int max_inventory_ = 3;
    int min_dte_ = 0;
    int max_dte_ = 14;

    // State
    std::deque<double> iv_window_;
    int tick_count_ = 0;
    std::string active_chain_sym_;
};

} // namespace strategy_cpp
