#pragma once
#include "template.hpp"

#include <cmath>
#include <string>
#include <ctime>

namespace strategy_cpp {

/**
 * IronCondorTestStrategy
 *
 * Sells an Iron Condor: short the ~16-delta OTM call and put,
 * long wings further OTM for protection.
 * Enters on the first tick once an eligible chain is found.
 * Manages to 50% max profit (take-profit) or 100% loss (stop-loss).
 */
class IronCondorTestStrategy : public OptionStrategyTemplate {
  public:
    using OptionStrategyTemplate::OptionStrategyTemplate;

    void on_init_logic() override {
        if (auto it = setting_.find("min_dte"); it != setting_.end())
            min_dte_ = static_cast<int>(it->second);
        if (auto it = setting_.find("max_dte"); it != setting_.end())
            max_dte_ = static_cast<int>(it->second);
        if (auto it = setting_.find("target_delta"); it != setting_.end())
            target_delta_ = it->second;
        if (auto it = setting_.find("wing_width"); it != setting_.end())
            wing_width_ = static_cast<int>(it->second);
        if (auto it = setting_.find("take_profit_pct"); it != setting_.end())
            take_profit_pct_ = it->second;
        if (auto it = setting_.find("stop_loss_pct"); it != setting_.end())
            stop_loss_pct_ = it->second;

        last_day_ = -1;
        tick_count_ = 0;
        write_log("IronCondorTest initialized: DTE=[" + std::to_string(min_dte_) + "," +
                  std::to_string(max_dte_) + "] delta=" + std::to_string(target_delta_) +
                  " wings=" + std::to_string(wing_width_));
    }

    void on_stop_logic() override {
        close_all_strategy_positions();
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

        // Manage existing position
        if (position_open_) {
            manage_position();
            return;
        }

        // Only enter in the first few ticks
        if (tick_count_ > 5) return;

        // Find chain
        auto chain_symbols = portfolio()->get_chain_by_expiry(min_dte_, max_dte_);
        if (chain_symbols.empty())
            chain_symbols = portfolio()->get_chain_by_expiry(0, 45);
        if (chain_symbols.empty()) return;

        subscribe_chains(std::span<const std::string>(chain_symbols.data(), 1));
        auto* chain = get_chain(chain_symbols[0]);
        if (!chain) return;

        chain->calculate_atm_price();
        if (chain->atm_index.empty() || chain->indexes.size() < 8) return;

        double spot = underlying()->mid_price;
        if (spot <= 0) return;

        // Find short put and short call strikes near target_delta_
        // Put: OTM, strike < spot, delta ~ -target_delta_
        // Call: OTM, strike > spot, delta ~ target_delta_
        utilities::OptionData* short_put = nullptr;
        utilities::OptionData* short_call = nullptr;
        utilities::OptionData* long_put = nullptr;
        utilities::OptionData* long_call = nullptr;
        double best_put_diff = 1e9;
        double best_call_diff = 1e9;

        for (auto& [idx, opt] : chain->puts) {
            if (!opt || !opt->strike_price) continue;
            double k = *opt->strike_price;
            if (k >= spot) continue; // OTM puts only
            double d = std::abs(opt->delta) / (opt->size != 0 ? opt->size : 1.0);
            double diff = std::abs(d - target_delta_);
            if (diff < best_put_diff && opt->bid_price > 0) {
                best_put_diff = diff;
                short_put = opt;
            }
        }
        for (auto& [idx, opt] : chain->calls) {
            if (!opt || !opt->strike_price) continue;
            double k = *opt->strike_price;
            if (k <= spot) continue; // OTM calls only
            double d = std::abs(opt->delta) / (opt->size != 0 ? opt->size : 1.0);
            double diff = std::abs(d - target_delta_);
            if (diff < best_call_diff && opt->bid_price > 0) {
                best_call_diff = diff;
                short_call = opt;
            }
        }

        if (!short_put || !short_call) return;

        // Find wing strikes: further OTM by wing_width_ index steps
        double short_put_strike = *short_put->strike_price;
        double short_call_strike = *short_call->strike_price;

        // Find long put: lower strike than short put
        for (auto& [idx, opt] : chain->puts) {
            if (!opt || !opt->strike_price) continue;
            double k = *opt->strike_price;
            if (k < short_put_strike && (!long_put || k > *long_put->strike_price)) {
                long_put = opt;
            }
        }
        // Find long call: higher strike than short call
        for (auto& [idx, opt] : chain->calls) {
            if (!opt || !opt->strike_price) continue;
            double k = *opt->strike_price;
            if (k > short_call_strike && (!long_call || k < *long_call->strike_price)) {
                long_call = opt;
            }
        }

        if (!long_put || !long_call) return;

        // Place Iron Condor order
        std::unordered_map<std::string, utilities::OptionData*> option_data;
        option_data["put_lower"] = long_put;
        option_data["put_upper"] = short_put;
        option_data["call_lower"] = short_call;
        option_data["call_upper"] = long_call;

        auto order_ids = option_order(
            utilities::ComboType::IRON_CONDOR, option_data,
            utilities::Direction::SHORT, 0.0, 1.0,
            utilities::OrderType::MARKET);

        if (!order_ids.empty()) {
            position_open_ = true;
            // Net credit = short premium - long premium
            entry_credit_ = (short_put->bid_price + short_call->bid_price) -
                            (long_put->ask_price + long_call->ask_price);
            write_log("Opened Iron Condor: credit=" + std::to_string(entry_credit_) +
                      " SP=" + std::to_string(short_put_strike) +
                      " SC=" + std::to_string(short_call_strike));
        }
    }

  private:
    void manage_position() {
        if (!holding()) return;

        double pnl = holding()->summary.pnl;
        double credit_100 = entry_credit_ * 100.0;

        // Take profit: 50% of credit received
        if (pnl >= credit_100 * take_profit_pct_) {
            write_log("IC take profit: pnl=" + std::to_string(pnl));
            close_all_strategy_positions();
            position_open_ = false;
            return;
        }

        // Stop loss: 100% of credit
        if (pnl <= -credit_100 * stop_loss_pct_) {
            write_log("IC stop loss: pnl=" + std::to_string(pnl));
            close_all_strategy_positions();
            position_open_ = false;
            return;
        }
    }

    // Parameters
    int min_dte_ = 14;
    int max_dte_ = 45;
    double target_delta_ = 0.16;
    int wing_width_ = 5;
    double take_profit_pct_ = 0.50;
    double stop_loss_pct_ = 1.00;

    bool position_open_ = false;
    double entry_credit_ = 0.0;
    int tick_count_ = 0;
    int last_day_ = -1;
};

} // namespace strategy_cpp
