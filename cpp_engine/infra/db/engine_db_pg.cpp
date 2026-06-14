#include "engine_db_pg.hpp"
#include <chrono>
#include <cstdlib>
#include <iostream>

namespace pqxx {
class connection {
public:
    connection(const std::string&) {}
};
}

namespace engines {

DatabaseEngine::DatabaseEngine(utilities::MainEngine* main_engine, const std::string& conninfo)
    : BaseEngine(main_engine, "Database"),
      conninfo_(conninfo) {
    write_log("Mock Database engine initialized (No-op)", INFO);
}

DatabaseEngine::~DatabaseEngine() {
    DatabaseEngine::close();
}

void DatabaseEngine::create_tables() {}

void DatabaseEngine::cleanup_expired_options() {}

void DatabaseEngine::load_contracts(
    const std::function<void(const utilities::ContractData&)>& apply_option,
    const std::function<void(const utilities::ContractData&)>& apply_underlying) {
    (void)apply_option;
    (void)apply_underlying;
}

auto DatabaseEngine::load_option_contract_data(const std::string* symbol_key)
    -> std::unordered_map<std::string, utilities::ContractData> {
    (void)symbol_key;
    return {};
}

auto DatabaseEngine::load_equity_contract_data(const std::string* symbol_key)
    -> std::unordered_map<std::string, utilities::ContractData> {
    (void)symbol_key;
    return {};
}

void DatabaseEngine::save_order_data(const std::string& strategy_name,
                                     const utilities::OrderData& order) {
    (void)strategy_name;
    (void)order;
}

void DatabaseEngine::save_trade_data(const std::string& strategy_name,
                                     const utilities::TradeData& trade) {
    (void)strategy_name;
    (void)trade;
}

auto DatabaseEngine::get_all_history_orders() -> std::vector<std::vector<std::string>> {
    return {};
}

auto DatabaseEngine::get_all_history_trades() -> std::vector<std::vector<std::string>> {
    return {};
}

void DatabaseEngine::wipe_trading_data() {}

void DatabaseEngine::close() {}

} // namespace engines
