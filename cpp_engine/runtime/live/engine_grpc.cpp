extern "C" {
    inline void __assert_fail(const char* /*assertion*/, const char* /*file*/, unsigned int /*line*/, const char* /*function*/) noexcept {}
}
#include <cstdio>
#include <windows.h>
#ifdef ERROR
#undef ERROR
#endif

typedef void* (*LoadModelFn)(const char*);
typedef void (*FreeModelFn)(void*);
typedef float (*RunInferenceFn)(void*, float, float, float, float, float, bool);

static HMODULE g_torch_dll = nullptr;
static LoadModelFn g_load_model = nullptr;
static FreeModelFn g_free_model = nullptr;
static RunInferenceFn g_run_inference = nullptr;

static bool load_torch_inference_dll() {
    if (g_torch_dll) return true;
    std::printf("[TORCH WRAPPER] Setting DLL directory...\n");
    SetDllDirectoryA("C:\\Users\\User\\Desktop\\Affinity-Core\\backend_orchestrator\\.venv\\Lib\\site-packages\\torch\\lib");
    LoadLibraryA("C:\\Users\\User\\Desktop\\Affinity-Core\\backend_orchestrator\\.venv\\Lib\\site-packages\\torch\\lib\\libiomp5md.dll");
    LoadLibraryA("C:\\Users\\User\\Desktop\\Affinity-Core\\backend_orchestrator\\.venv\\Lib\\site-packages\\torch\\lib\\c10.dll");
    LoadLibraryA("C:\\Users\\User\\Desktop\\Affinity-Core\\backend_orchestrator\\.venv\\Lib\\site-packages\\torch\\lib\\torch_cpu.dll");
    
    std::printf("[TORCH WRAPPER] Loading torch_inference.dll...\n");
    g_torch_dll = LoadLibraryA("torch_inference.dll");
    if (!g_torch_dll) {
        g_torch_dll = LoadLibraryA("build/torch_inference.dll");
    }
    if (!g_torch_dll) {
        g_torch_dll = LoadLibraryA("cpp_engine/build/torch_inference.dll");
    }
    SetDllDirectoryA(nullptr);
    
    if (!g_torch_dll) {
        std::printf("[TORCH WRAPPER] FAILED to load torch_inference.dll!\n");
        return false;
    }
    std::printf("[TORCH WRAPPER] Successfully loaded torch_inference.dll. Getting functions...\n");
    g_load_model = (LoadModelFn)GetProcAddress(g_torch_dll, "load_model");
    g_free_model = (FreeModelFn)GetProcAddress(g_torch_dll, "free_model");
    g_run_inference = (RunInferenceFn)GetProcAddress(g_torch_dll, "run_inference");
    
    bool ok = g_load_model && g_free_model && g_run_inference;
    std::printf("[TORCH WRAPPER] Functions retrieved status: %d\n", ok);
    return ok;
}

#include "engine_grpc.hpp"
#include "../../core/engine_log.hpp"
#include "../../strategy/strategy_registry.hpp"
#include "../../strategy/template.hpp"
#include "../../utilities/event.hpp"
#include "../../utilities/thread_affinity.hpp"
#include "../backtest/engine_backtest.hpp"
#include "engine_db_pg.hpp"
#include <nlohmann/json.hpp>
#include <fstream>
#include <ctime>
#include <filesystem>

#include <cstdlib>
#include <exception>
#include <format>

namespace engines {

namespace {

auto parse_setting_json(const std::string& s) -> std::unordered_map<std::string, double> {
    std::unordered_map<std::string, double> out;
    if (s.empty() || s == "{}") {
        return out;
    }
    for (size_t i = 0; i < s.size();) {
        if (s[i] == '"') {
            ++i;
            size_t start = i;
            while (i < s.size() && s[i] != '"') {
                ++i;
            }
            std::string key = s.substr(start, i - start);
            if (i < s.size()) {
                ++i;
            }
            while (i < s.size() && (s[i] == ' ' || s[i] == ':')) {
                ++i;
            }
            double val = 0;
            if (i < s.size() && ((std::isdigit(static_cast<unsigned char>(s[i])) != 0) ||
                                 s[i] == '-' || s[i] == '.')) {
                char* end = nullptr;
                val = std::strtod(s.c_str() + i, &end);
                if (end != nullptr) {
                    i = static_cast<size_t>(end - s.c_str());
                }
            }
            out[key] = val;
            while (i < s.size() && s[i] != '"' && s[i] != '}') {
                ++i;
            }
        } else {
            ++i;
        }
    }
    return out;
}

} // namespace

GrpcLiveEngineService::GrpcLiveEngineService(MainEngine* main_engine) : main_engine_(main_engine) {}

auto GrpcLiveEngineService::GetStatus(::grpc::ServerContext* /*context*/,
                                      const ::otrader::Empty* /*request*/,
                                      ::otrader::EngineStatus* response) -> ::grpc::Status {
    if (response == nullptr) {
        return ::grpc::Status(::grpc::StatusCode::INTERNAL, "response is null");
    }

    const bool running = (main_engine_ != nullptr);
    response->set_running(running);

    const bool ib_connected = running && (main_engine_->gateway_client() != nullptr) &&
                              main_engine_->gateway_client()->is_connected();
    response->set_connected(ib_connected);

    const bool md_running = running && main_engine_->market_data_running();

    if (!running) {
        response->set_detail("engine: stopped; ib: off; md: off");
    } else {
        response->set_detail(std::format("engine: running; ib: {}; md: {}",
                                         ib_connected ? "on" : "off", md_running ? "on" : "off"));
    }
    return ::grpc::Status::OK;
}

auto GrpcLiveEngineService::ListStrategies(::grpc::ServerContext* /*context*/,
                                           const ::otrader::Empty* /*request*/,
                                           ::grpc::ServerWriter<::otrader::StrategySummary>* writer)
    -> ::grpc::Status {
    if ((writer == nullptr) || (main_engine_ == nullptr) ||
        (main_engine_->option_strategy_engine() == nullptr)) {
        return ::grpc::Status::OK;
    }
    auto* se = main_engine_->option_strategy_engine();
    for (const std::string& name : se->get_strategy_names()) {
        auto* s = se->get_strategy(name);
        if (s == nullptr) {
            continue;
        }
        ::otrader::StrategySummary sum;
        sum.set_strategy_name(s->strategy_name());
        sum.set_class_name(name.substr(0, name.find('_')));
        sum.set_portfolio(s->portfolio_name());
        if (s->error()) {
            sum.set_status("error");
        } else if (s->started()) {
            sum.set_status("running");
        } else if (s->inited()) {
            sum.set_status("stopped");
        } else {
            sum.set_status("created");
        }
        writer->Write(sum);
    }
    return ::grpc::Status::OK;
}

auto GrpcLiveEngineService::ConnectGateway(::grpc::ServerContext* /*context*/,
                                           const ::otrader::Empty* /*request*/,
                                           ::otrader::Empty* /*response*/) -> ::grpc::Status {
    if (main_engine_ == nullptr) {
        return ::grpc::Status(::grpc::StatusCode::FAILED_PRECONDITION, "main engine is null");
    }
    try {
        main_engine_->connect();
        return ::grpc::Status::OK;
    } catch (const std::exception& e) {
        return ::grpc::Status(::grpc::StatusCode::INTERNAL, e.what());
    }
}

auto GrpcLiveEngineService::DisconnectGateway(::grpc::ServerContext* /*context*/,
                                              const ::otrader::Empty* /*request*/,
                                              ::otrader::Empty* /*response*/) -> ::grpc::Status {
    if (main_engine_ == nullptr) {
        return ::grpc::Status(::grpc::StatusCode::FAILED_PRECONDITION, "main engine is null");
    }
    try {
        main_engine_->disconnect();
        return ::grpc::Status::OK;
    } catch (const std::exception& e) {
        return ::grpc::Status(::grpc::StatusCode::INTERNAL, e.what());
    }
}

auto GrpcLiveEngineService::StartMarketData(::grpc::ServerContext* /*context*/,
                                            const ::otrader::Empty* /*request*/,
                                            ::otrader::Empty* /*response*/) -> ::grpc::Status {
    if (main_engine_ == nullptr) {
        return ::grpc::Status(::grpc::StatusCode::FAILED_PRECONDITION, "main engine is null");
    }
    try {
        main_engine_->start_market_data_update();
        return ::grpc::Status::OK;
    } catch (const std::exception& e) {
        return ::grpc::Status(::grpc::StatusCode::INTERNAL, e.what());
    }
}

auto GrpcLiveEngineService::StopMarketData(::grpc::ServerContext* /*context*/,
                                           const ::otrader::Empty* /*request*/,
                                           ::otrader::Empty* /*response*/) -> ::grpc::Status {
    if (main_engine_ == nullptr) {
        return ::grpc::Status(::grpc::StatusCode::FAILED_PRECONDITION, "main engine is null");
    }
    try {
        main_engine_->stop_market_data_update();
        return ::grpc::Status::OK;
    } catch (const std::exception& e) {
        return ::grpc::Status(::grpc::StatusCode::INTERNAL, e.what());
    }
}

auto GrpcLiveEngineService::StartStrategy(::grpc::ServerContext* /*context*/,
                                          const ::otrader::StrategyNameRequest* request,
                                          ::otrader::Empty* /*response*/) -> ::grpc::Status {
    if ((main_engine_ == nullptr) || (main_engine_->option_strategy_engine() == nullptr) ||
        (request == nullptr)) {
        return ::grpc::Status(::grpc::StatusCode::INVALID_ARGUMENT, "missing request or engine");
    }
    try {
        main_engine_->option_strategy_engine()->start_strategy(request->strategy_name());
        return ::grpc::Status::OK;
    } catch (const std::exception& e) {
        return ::grpc::Status(::grpc::StatusCode::INVALID_ARGUMENT, e.what());
    }
}

auto GrpcLiveEngineService::StopStrategy(::grpc::ServerContext* /*context*/,
                                         const ::otrader::StrategyNameRequest* request,
                                         ::otrader::Empty* /*response*/) -> ::grpc::Status {
    if ((main_engine_ == nullptr) || (main_engine_->option_strategy_engine() == nullptr) ||
        (request == nullptr)) {
        return ::grpc::Status(::grpc::StatusCode::INVALID_ARGUMENT, "missing request or engine");
    }
    try {
        main_engine_->option_strategy_engine()->stop_strategy(request->strategy_name());
        return ::grpc::Status::OK;
    } catch (const std::exception& e) {
        return ::grpc::Status(::grpc::StatusCode::INVALID_ARGUMENT, e.what());
    }
}

auto GrpcLiveEngineService::StreamLogs(::grpc::ServerContext* context,
                                       const ::otrader::Empty* /*request*/,
                                       ::grpc::ServerWriter<::otrader::LogLine>* writer)
    -> ::grpc::Status {
    utilities::pin_thread_to_core("GRPC_IO_CPU_CORE", "gRPC StreamLogs");
    if ((main_engine_ == nullptr) || (writer == nullptr)) {
        return ::grpc::Status(::grpc::StatusCode::FAILED_PRECONDITION, "main engine is null");
    }
    while (!context->IsCancelled()) {
        utilities::LogData log;
        if (!main_engine_->pop_log_for_stream(log, 1000)) {
            continue;
        }
        ::otrader::LogLine msg;
        // JSON log line
        std::string level_str = engines::level_to_string(log.level);
        auto escape = [](const std::string& in) -> std::string {
            std::string out;
            out.reserve(in.size());
            for (char c : in) {
                if (c == '\\' || c == '"') {
                    out.push_back('\\');
                }
                out.push_back(c);
            }
            return out;
        };
        std::string json = "{";
        json += R"("src":"live")";
        json += R"(,"time":")" + escape(log.time) + "\"";
        json += ",\"level\":" + std::to_string(log.level);
        json += R"(,"level_str":")" + escape(level_str) + "\"";
        json += R"(,"gateway":")" + escape(log.gateway_name) + "\"";
        json += R"(,"msg":")" + escape(log.msg) + "\"";
        json += "}";
        msg.set_line(json);
        if (!writer->Write(msg)) {
            break;
        }
    }
    return ::grpc::Status::OK;
}

auto GrpcLiveEngineService::StreamStrategyUpdates(
    ::grpc::ServerContext* context, const ::otrader::Empty* /*request*/,
    ::grpc::ServerWriter<::otrader::StrategyUpdate>* writer) -> ::grpc::Status {
    utilities::pin_thread_to_core("GRPC_IO_CPU_CORE", "gRPC StreamStrategyUpdates");
    if ((main_engine_ == nullptr) || (writer == nullptr)) {
        return ::grpc::Status(::grpc::StatusCode::FAILED_PRECONDITION, "main engine is null");
    }
    while (!context->IsCancelled()) {
        utilities::StrategyUpdateData upd;
        if (!main_engine_->pop_strategy_update(upd, 1000)) {
            continue;
        }
        ::otrader::StrategyUpdate msg;
        msg.set_strategy_name(upd.strategy_name);
        msg.set_class_name(upd.class_name);
        msg.set_portfolio(upd.portfolio);
        msg.set_json_payload(upd.json_payload);
        if (!writer->Write(msg)) {
            break;
        }
    }
    return ::grpc::Status::OK;
}

auto GrpcLiveEngineService::GetOrdersAndTrades(::grpc::ServerContext* /*context*/,
                                               const ::otrader::Empty* /*request*/,
                                               ::otrader::OrdersAndTradesResponse* response)
    -> ::grpc::Status {
    if ((response == nullptr) || (main_engine_ == nullptr) ||
        (main_engine_->db_engine() == nullptr)) {
        return ::grpc::Status(::grpc::StatusCode::INTERNAL, "missing engine or response");
    }
    try {
        auto orders = main_engine_->db_engine()->get_all_history_orders();
        auto trades = main_engine_->db_engine()->get_all_history_trades();
        for (const auto& row : orders) {
            auto* r = response->add_orders();
            if (!row.empty()) {
                r->set_timestamp(row[0]);
            }
            if (row.size() > 1) {
                r->set_strategy_name(row[1]);
            }
            if (row.size() > 2) {
                r->set_orderid(row[2]);
            }
            if (row.size() > 3) {
                r->set_symbol(row[3]);
            }
            if (row.size() > 4) {
                r->set_exchange(row[4]);
            }
            if (row.size() > 5) {
                r->set_trading_class(row[5]);
            }
            if (row.size() > 6) {
                r->set_type(row[6]);
            }
            if (row.size() > 7) {
                r->set_direction(row[7]);
            }
            if (row.size() > 8 && !row[8].empty()) {
                r->set_price(std::stod(row[8]));
            }
            if (row.size() > 9 && !row[9].empty()) {
                r->set_volume(std::stod(row[9]));
            }
            if (row.size() > 10 && !row[10].empty()) {
                r->set_traded(std::stod(row[10]));
            }
            if (row.size() > 11) {
                r->set_status(row[11]);
            }
            if (row.size() > 12) {
                r->set_datetime(row[12]);
            }
            if (row.size() > 13) {
                r->set_reference(row[13]);
            }
            if (row.size() > 14 && !row[14].empty()) {
                r->set_is_combo(std::stoi(row[14]) != 0);
            }
            if (row.size() > 15) {
                r->set_legs_info(row[15]);
            }
        }
        for (const auto& row : trades) {
            auto* r = response->add_trades();
            if (!row.empty()) {
                r->set_timestamp(row[0]);
            }
            if (row.size() > 1) {
                r->set_strategy_name(row[1]);
            }
            if (row.size() > 2) {
                r->set_tradeid(row[2]);
            }
            if (row.size() > 3) {
                r->set_symbol(row[3]);
            }
            if (row.size() > 4) {
                r->set_exchange(row[4]);
            }
            if (row.size() > 5) {
                r->set_orderid(row[5]);
            }
            if (row.size() > 6) {
                r->set_direction(row[6]);
            }
            if (row.size() > 7 && !row[7].empty()) {
                r->set_price(std::stod(row[7]));
            }
            if (row.size() > 8 && !row[8].empty()) {
                r->set_volume(std::stod(row[8]));
            }
            if (row.size() > 9) {
                r->set_datetime(row[9]);
            }
        }
        return ::grpc::Status::OK;
    } catch (const std::exception& e) {
        return ::grpc::Status(::grpc::StatusCode::INTERNAL, e.what());
    }
}

auto GrpcLiveEngineService::ListPortfolios(::grpc::ServerContext* /*context*/,
                                           const ::otrader::Empty* /*request*/,
                                           ::otrader::ListPortfoliosResponse* response)
    -> ::grpc::Status {
    if ((response == nullptr) || (main_engine_ == nullptr)) {
        return ::grpc::Status::OK;
    }
    try {
        for (const std::string& n : main_engine_->get_all_portfolio_names()) {
            response->add_portfolios(n);
        }
        return ::grpc::Status::OK;
    } catch (const std::exception& e) {
        return ::grpc::Status(::grpc::StatusCode::INTERNAL, e.what());
    }
}

auto GrpcLiveEngineService::ListStrategyClasses(::grpc::ServerContext* /*context*/,
                                                const ::otrader::Empty* /*request*/,
                                                ::otrader::ListStrategyClassesResponse* response)
    -> ::grpc::Status {
    if (response == nullptr) {
        return ::grpc::Status::OK;
    }
    try {
        for (const std::string& c :
             strategy_cpp::StrategyRegistry::get_all_strategy_class_names()) {
            response->add_classes(c);
        }
        return ::grpc::Status::OK;
    } catch (const std::exception& e) {
        return ::grpc::Status(::grpc::StatusCode::INTERNAL, e.what());
    }
}

auto GrpcLiveEngineService::GetStrategyClassDefaults(
    ::grpc::ServerContext* /*context*/, const ::otrader::GetStrategyClassDefaultsRequest* request,
    ::otrader::GetStrategyClassDefaultsResponse* response) -> ::grpc::Status {
    if ((request == nullptr) || (response == nullptr) || (main_engine_ == nullptr) ||
        (main_engine_->option_strategy_engine() == nullptr)) {
        return ::grpc::Status(::grpc::StatusCode::INVALID_ARGUMENT, "missing request or engine");
    }
    try {
        std::unordered_map<std::string, double> defaults =
            main_engine_->option_strategy_engine()->get_default_setting(request->strategy_class());
        for (const auto& [k, v] : defaults) {
            (*response->mutable_settings())[k] = v;
        }
        return ::grpc::Status::OK;
    } catch (const std::exception& e) {
        return ::grpc::Status(::grpc::StatusCode::INTERNAL, e.what());
    }
}

auto GrpcLiveEngineService::GetPortfoliosMeta(::grpc::ServerContext* /*context*/,
                                              const ::otrader::Empty* /*request*/,
                                              ::otrader::ListPortfoliosResponse* response)
    -> ::grpc::Status {
    return ListPortfolios(nullptr, nullptr, response);
}

auto GrpcLiveEngineService::GetRemovedStrategies(::grpc::ServerContext* /*context*/,
                                                 const ::otrader::Empty* /*request*/,
                                                 ::otrader::GetRemovedStrategiesResponse* response)
    -> ::grpc::Status {
    if (response == nullptr) {
        return ::grpc::Status::OK;
    }
    return ::grpc::Status::OK;
}

auto GrpcLiveEngineService::AddStrategy(::grpc::ServerContext* /*context*/,
                                        const ::otrader::AddStrategyRequest* request,
                                        ::otrader::AddStrategyResponse* response)
    -> ::grpc::Status {
    if ((request == nullptr) || (response == nullptr) || (main_engine_ == nullptr) ||
        (main_engine_->option_strategy_engine() == nullptr)) {
        return ::grpc::Status(::grpc::StatusCode::INVALID_ARGUMENT, "missing request or engine");
    }
    try {
        auto setting = parse_setting_json(request->setting_json());
        main_engine_->option_strategy_engine()->add_strategy(request->strategy_class(),
                                                             request->portfolio_name(), setting);
        response->set_strategy_name(request->strategy_class() + "_" + request->portfolio_name());
        return ::grpc::Status::OK;
    } catch (const std::exception& e) {
        return ::grpc::Status(::grpc::StatusCode::INVALID_ARGUMENT, e.what());
    }
}

auto GrpcLiveEngineService::RestoreStrategy(::grpc::ServerContext* /*context*/,
                                            const ::otrader::StrategyNameRequest* /*request*/,
                                            ::otrader::Empty* /*response*/) -> ::grpc::Status {
    return ::grpc::Status(::grpc::StatusCode::UNIMPLEMENTED,
                          "RestoreStrategy not supported in C++ live");
}

auto GrpcLiveEngineService::InitStrategy(::grpc::ServerContext* /*context*/,
                                         const ::otrader::StrategyNameRequest* request,
                                         ::otrader::Empty* /*response*/) -> ::grpc::Status {
    if ((main_engine_ == nullptr) || (main_engine_->option_strategy_engine() == nullptr) ||
        (request == nullptr)) {
        return ::grpc::Status(::grpc::StatusCode::INVALID_ARGUMENT, "missing request or engine");
    }
    try {
        main_engine_->option_strategy_engine()->init_strategy(request->strategy_name());
        return ::grpc::Status::OK;
    } catch (const std::exception& e) {
        return ::grpc::Status(::grpc::StatusCode::INVALID_ARGUMENT, e.what());
    }
}

auto GrpcLiveEngineService::RemoveStrategy(::grpc::ServerContext* /*context*/,
                                           const ::otrader::StrategyNameRequest* request,
                                           ::otrader::RemoveStrategyResponse* response)
    -> ::grpc::Status {
    if ((request == nullptr) || (response == nullptr) || (main_engine_ == nullptr) ||
        (main_engine_->option_strategy_engine() == nullptr)) {
        return ::grpc::Status(::grpc::StatusCode::INVALID_ARGUMENT, "missing request or engine");
    }
    response->set_removed(
        main_engine_->option_strategy_engine()->remove_strategy(request->strategy_name()));
    return ::grpc::Status::OK;
}

auto GrpcLiveEngineService::DeleteStrategy(::grpc::ServerContext* /*context*/,
                                           const ::otrader::StrategyNameRequest* request,
                                           ::otrader::DeleteStrategyResponse* response)
    -> ::grpc::Status {
    if ((request == nullptr) || (response == nullptr) || (main_engine_ == nullptr) ||
        (main_engine_->option_strategy_engine() == nullptr)) {
        return ::grpc::Status(::grpc::StatusCode::INVALID_ARGUMENT, "missing request or engine");
    }
    response->set_deleted(
        main_engine_->option_strategy_engine()->remove_strategy(request->strategy_name()));
    return ::grpc::Status::OK;
}

auto GrpcLiveEngineService::GetStrategyHoldings(::grpc::ServerContext* /*context*/,
                                                const ::otrader::Empty* /*request*/,
                                                ::otrader::StrategyHoldingsResponse* response)
    -> ::grpc::Status {
    if ((response == nullptr) || (main_engine_ == nullptr) ||
        (main_engine_->option_strategy_engine() == nullptr) ||
        (main_engine_->position_engine() == nullptr)) {
        return ::grpc::Status::OK;
    }
    try {
        for (const std::string& name :
             main_engine_->option_strategy_engine()->get_strategy_names()) {
            try {
                std::string json = main_engine_->position_engine()->serialize_holding(name);
                (*response->mutable_holdings())[name] = json;
            } catch (...) {
                continue;
            }
        }
        return ::grpc::Status::OK;
    } catch (const std::exception& e) {
        return ::grpc::Status(::grpc::StatusCode::INTERNAL, e.what());
    }
}

auto GrpcLiveEngineService::StartBacktest(
    ::grpc::ServerContext* context,
    const ::otrader::StreamRequest* request,
    ::grpc::ServerWriter<::otrader::EngineStateUpdate>* writer) -> ::grpc::Status {
    utilities::pin_thread_to_core("GRPC_IO_CPU_CORE", "gRPC StartBacktest");

    if ((request == nullptr) || (writer == nullptr)) {
        return ::grpc::Status(::grpc::StatusCode::INVALID_ARGUMENT, "request or writer is null");
    }

    const auto& strategy_pb = request->strategy();
    backtest::BacktestEngine engine;

    try {
        engine.configure_execution(strategy_pb.fee_rate(), strategy_pb.slippage_bps());
        if (engine.main_engine() != nullptr) {
            engine.main_engine()->set_log_level(engines::DISABLED);
        }

        size_t last_trade_count = 0;
        size_t last_order_count = 0;

        auto write_temp_files = [&]() {
            auto* me = engine.main_engine();
            if (!me) return;
            auto trades = me->get_all_trades();
            std::string trades_path = "../../data/temp/trades_" + request->job_id() + ".json";
            std::string trades_tmp = trades_path + ".tmp";
            std::ofstream out_t(trades_tmp);
            if (out_t.is_open()) {
                out_t << "[\n";
                for (size_t i = 0; i < trades.size(); ++i) {
                    const auto& t = trades[i];
                    std::string dt_str = "";
                    if (t.datetime.has_value()) {
                        std::time_t tt = std::chrono::system_clock::to_time_t(*t.datetime);
                        std::tm tm{};
#if defined(_WIN32)
                        gmtime_s(&tm, &tt);
#else
                        gmtime_r(&tt, &tm);
#endif
                        char buf[64];
                        std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &tm);
                        dt_str = buf;
                    }
                    std::string dir_str = t.direction.has_value() ? utilities::to_string(*t.direction) : "LONG";
                    out_t << "  {\n"
                          << "    \"timestamp\": \"" << dt_str << "\",\n"
                          << "    \"tradeid\": \"" << t.tradeid << "\",\n"
                          << "    \"symbol\": \"" << t.symbol << "\",\n"
                          << "    \"exchange\": \"" << utilities::to_string(t.exchange) << "\",\n"
                          << "    \"orderid\": \"" << t.orderid << "\",\n"
                          << "    \"direction\": \"" << dir_str << "\",\n"
                          << "    \"price\": " << t.price << ",\n"
                          << "    \"volume\": " << t.volume << "\n"
                          << "  }" << (i + 1 < trades.size() ? "," : "") << "\n";
                }
                out_t << "]\n";
                out_t.close();
                std::error_code ec;
                std::filesystem::rename(trades_tmp, trades_path, ec);
            }

            auto orders = me->get_all_orders();
            std::string orders_path = "../../data/temp/orders_" + request->job_id() + ".json";
            std::string orders_tmp = orders_path + ".tmp";
            std::ofstream out_o(orders_tmp);
            if (out_o.is_open()) {
                out_o << "[\n";
                for (size_t i = 0; i < orders.size(); ++i) {
                    const auto& o = orders[i];
                    std::string dt_str = "";
                    if (o.datetime.has_value()) {
                        std::time_t tt = std::chrono::system_clock::to_time_t(*o.datetime);
                        std::tm tm{};
#if defined(_WIN32)
                        gmtime_s(&tm, &tt);
#else
                        gmtime_r(&tt, &tm);
#endif
                        char buf[64];
                        std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &tm);
                        dt_str = buf;
                    }
                    std::string dir_str = o.direction.has_value() ? utilities::to_string(*o.direction) : "LONG";
                    out_o << "  {\n"
                          << "    \"timestamp\": \"" << dt_str << "\",\n"
                          << "    \"orderid\": \"" << o.orderid << "\",\n"
                          << "    \"symbol\": \"" << o.symbol << "\",\n"
                          << "    \"exchange\": \"" << utilities::to_string(o.exchange) << "\",\n"
                          << "    \"trading_class\": \"" << (o.trading_class.has_value() ? *o.trading_class : "") << "\",\n"
                          << "    \"type\": \"" << utilities::to_string(o.type) << "\",\n"
                          << "    \"direction\": \"" << dir_str << "\",\n"
                          << "    \"price\": " << o.price << ",\n"
                          << "    \"volume\": " << o.volume << ",\n"
                          << "    \"traded\": " << o.traded << ",\n"
                          << "    \"status\": \"" << utilities::to_string(o.status) << "\",\n"
                          << "    \"reference\": \"" << o.reference << "\",\n"
                          << "    \"is_combo\": " << (o.is_combo ? "true" : "false") << "\n"
                          << "  }" << (i + 1 < orders.size() ? "," : "") << "\n";
                }
                out_o << "]\n";
                out_o.close();
                std::error_code ec;
                std::filesystem::rename(orders_tmp, orders_path, ec);
            }
        };

        std::unordered_map<std::string, void*> ml_models;
        const bool has_dll = load_torch_inference_dll();
        std::printf("[TORCH WRAPPER] has_dll: %d\n", has_dll);
        if (has_dll) {
            for (int i = 0; i < request->model_ids_size(); ++i) {
                std::string model_id = request->model_ids(i);
                std::string model_path = "../../models/" + model_id + ".pt";
                if (!std::filesystem::exists(model_path)) {
                    model_path = "../models/" + model_id + ".pt";
                }
                if (!std::filesystem::exists(model_path)) {
                    model_path = "models/" + model_id + ".pt";
                }
                std::printf("[TORCH WRAPPER] Resolved path for %s: %s (exists: %d)\n",
                            model_id.c_str(), model_path.c_str(), std::filesystem::exists(model_path));
                void* model = g_load_model(model_path.c_str());
                std::printf("[TORCH WRAPPER] Loaded model %s pointer: %p\n", model_id.c_str(), model);
                if (model != nullptr) {
                    ml_models[model_id] = model;
                }
            }
        }

        double last_spot_price = 0.0;
        double last_baseline_delta = 0.0;
        std::unordered_map<std::string, double> model_prev_deltas;
        std::unordered_map<std::string, double> model_diff_cumulative_pnl;
        std::unordered_map<std::string, std::unordered_map<std::string, double>> model_contract_prev_deltas;

        engine.register_timestep_callback([&](int /*timestep*/, backtest::Timestamp ts) {
            if (context->IsCancelled()) {
                return;
            }

            auto* me = engine.main_engine();
            if (me != nullptr) {
                auto trades_size = me->get_all_trades().size();
                auto orders_size = me->get_all_orders().size();
                if (trades_size != last_trade_count || orders_size != last_order_count) {
                    last_trade_count = trades_size;
                    last_order_count = orders_size;
                    write_temp_files();
                }
            }

            ::otrader::EngineStateUpdate update;
            update.set_job_id(request->job_id());

            auto epoch_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                ts.time_since_epoch()
            ).count();
            update.set_tick_timestamp_ns(epoch_ns);

            double spot_price = 0.0;
            double implied_vol = 0.0;
            auto* holding = me != nullptr ? me->option_strategy_engine()->get_strategy_holding() : nullptr;

            auto* me_ptr = engine.main_engine();
            if (me_ptr != nullptr) {
                if (me_ptr->option_strategy_engine() != nullptr) {
                    if (holding != nullptr) {
                        const double pnl = holding->summary.pnl;
                        update.set_pnl(pnl);
                        update.set_cumulative_pnl(pnl);

                        auto* greeks = update.mutable_greeks();
                        greeks->set_delta(holding->summary.delta);
                        greeks->set_gamma(holding->summary.gamma);
                        greeks->set_theta(holding->summary.theta);
                        greeks->set_vega(holding->summary.vega);
                        greeks->set_rho(0.0);
                    }

                    auto* strategy = me_ptr->option_strategy_engine()->get_strategy();
                    if (strategy != nullptr) {
                        auto* portfolio = me_ptr->get_portfolio(strategy->portfolio_name());
                        if (portfolio != nullptr) {
                            if (portfolio->underlying != nullptr) {
                                spot_price = portfolio->underlying->mid_price;
                            }
                            if (!portfolio->chains.empty()) {
                                auto it = portfolio->chains.begin();
                                if ((it != portfolio->chains.end()) && (it->second != nullptr)) {
                                    auto atm_iv = it->second->get_atm_iv();
                                    if (atm_iv.has_value()) {
                                        implied_vol = atm_iv.value();
                                    }
                                }
                            }
                        }
                    }
                }
            }

            update.set_spot_price(spot_price);
            update.set_implied_vol(implied_vol);

            double spot_change = 0.0;
            if (last_spot_price > 0.0) {
                spot_change = spot_price - last_spot_price;
            }

            double strike = spot_price;
            double dte = 30.0 / 365.25;

            if (me_ptr != nullptr && me_ptr->option_strategy_engine() != nullptr && holding != nullptr) {
                if (!holding->optionPositions.empty()) {
                    auto it = holding->optionPositions.begin();
                    auto* contract = me_ptr->get_contract(it->first);
                    if (contract != nullptr) {
                        if (contract->option_strike.has_value()) {
                            strike = contract->option_strike.value();
                        }
                        if (contract->option_expiry.has_value()) {
                            auto expiry = contract->option_expiry.value();
                            auto diff = std::chrono::duration_cast<std::chrono::seconds>(expiry - ts).count();
                            dte = static_cast<double>(diff) / (365.25 * 24.0 * 3600.0);
                            if (dte < 0.0) dte = 0.0;
                        }
                    }
                }
            }

            for (const auto& [model_id, model_ptr] : ml_models) {
                double prev_d = model_prev_deltas[model_id];
                double total_model_delta = 0.0;
                auto start_time = std::chrono::high_resolution_clock::now();
                const bool is_lstm = (model_id.find("lstm") != std::string::npos);
                
                if (me_ptr != nullptr && me_ptr->option_strategy_engine() != nullptr && holding != nullptr) {
                    for (const auto& [symbol, pos] : holding->optionPositions) {
                        if (pos.quantity == 0) continue;
                        auto* contract = me_ptr->get_contract(symbol);
                        if (contract == nullptr) continue;
                        double contract_strike = spot_price;
                        double contract_dte = 30.0 / 365.25;
                        if (contract->option_strike.has_value()) {
                            contract_strike = contract->option_strike.value();
                        }
                        if (contract->option_expiry.has_value()) {
                            auto expiry = contract->option_expiry.value();
                            auto diff = std::chrono::duration_cast<std::chrono::seconds>(expiry - ts).count();
                            contract_dte = static_cast<double>(diff) / (365.25 * 24.0 * 3600.0);
                            if (contract_dte < 0.0) contract_dte = 0.0;
                        }

                        double contract_delta = 0.0;
                        if (model_ptr != nullptr && g_run_inference != nullptr) {
                            double prev_contract_delta = model_contract_prev_deltas[model_id][symbol];
                            contract_delta = g_run_inference(model_ptr,
                                                             static_cast<float>(spot_price),
                                                             static_cast<float>((spot_price / contract_strike) - 1.0),
                                                             static_cast<float>(contract_dte),
                                                             static_cast<float>(implied_vol),
                                                             static_cast<float>(prev_contract_delta),
                                                             is_lstm);
                            if (!std::isfinite(contract_delta) || std::isnan(contract_delta)) {
                                contract_delta = 0.0;
                            }
                            model_contract_prev_deltas[model_id][symbol] = contract_delta;
                        }
                        if (contract->option_type.has_value() && *contract->option_type == utilities::OptionType::PUT) {
                            contract_delta = contract_delta - 1.0;
                        }
                        total_model_delta += contract_delta * pos.quantity;
                    }
                }
                auto end_time = std::chrono::high_resolution_clock::now();
                auto latency_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(end_time - start_time).count();

                if (last_spot_price > 0.0) {
                    double diff_pnl = (last_baseline_delta - prev_d) * spot_change * 100.0;
                    model_diff_cumulative_pnl[model_id] += diff_pnl;
                }

                double baseline_pnl = holding != nullptr ? holding->summary.pnl : 0.0;
                double model_cum_pnl = baseline_pnl + model_diff_cumulative_pnl[model_id];

                auto* mr = update.add_model_results();
                mr->set_model_id(model_id);
                mr->set_hedge_ratio(total_model_delta);
                mr->set_pnl(model_cum_pnl - baseline_pnl);
                mr->set_cumulative_pnl(model_cum_pnl);
                mr->set_inference_latency_ns(latency_ns);

                model_prev_deltas[model_id] = total_model_delta;
            }

            last_spot_price = spot_price;
            if (holding != nullptr) {
                last_baseline_delta = holding->summary.delta;
            }

            // Circular tail risk stats (var/cvar)
            auto* cvar = update.mutable_cvar();
            cvar->set_var_95(0.0);
            cvar->set_cvar_95(0.0);
            cvar->set_var_99(0.0);
            cvar->set_cvar_99(0.0);

            writer->Write(update);
        });

        engine.load_backtest_data(strategy_pb.parquet_path());

        auto settings = parse_setting_json(strategy_pb.strategy_setting());
        engine.add_strategy(strategy_pb.strategy_name(), settings);

        if (engine.main_engine() != nullptr) {
            auto* de = engine.main_engine()->get_data_engine();
            if (de != nullptr) {
                de->set_risk_free_rate(strategy_pb.risk_free_rate());
                de->set_iv_price_mode(strategy_pb.iv_price_mode());
            }
        }

        engine.run();

        write_temp_files();

        if (has_dll && g_free_model != nullptr) {
            for (auto& [model_id, model_ptr] : ml_models) {
                if (model_ptr != nullptr) {
                    g_free_model(model_ptr);
                }
            }
        }

        return ::grpc::Status::OK;
    } catch (const std::exception& e) {
        return ::grpc::Status(::grpc::StatusCode::INTERNAL, e.what());
    } catch (...) {
        return ::grpc::Status(::grpc::StatusCode::INTERNAL, "unknown C++ backtest error");
    }
}

auto GrpcLiveEngineService::SendCommand(
    ::grpc::ServerContext* /*context*/,
    ::grpc::ServerReader<::otrader::CommandRequest>* reader,
    ::otrader::CommandAck* response) -> ::grpc::Status {
    utilities::pin_thread_to_core("GRPC_IO_CPU_CORE", "gRPC SendCommand");

    if ((reader == nullptr) || (response == nullptr)) {
        return ::grpc::Status(::grpc::StatusCode::INVALID_ARGUMENT, "reader or response is null");
    }

    ::otrader::CommandRequest cmd;
    std::string last_cmd_id;
    bool all_ok = true;
    std::string err_msg;

    while (reader->Read(&cmd)) {
        last_cmd_id = cmd.command_id();
        std::string action = cmd.action();
        std::string payload_json = cmd.payload_json();

        try {
            if (action == "order" || action == "send_order") {
                nlohmann::json j = nlohmann::json::parse(payload_json);
                utilities::OrderRequest req;
                req.symbol = j.value("symbol", "");
                req.exchange = utilities::from_string_exchange(j.value("exchange", "SMART"));
                req.direction = utilities::from_string_direction(j.value("direction", "LONG"));
                req.type = utilities::from_string_ordertype(j.value("type", "LIMIT"));
                req.volume = j.value("volume", 0.0);
                req.price = j.value("price", 0.0);
                req.reference = j.value("reference", "");
                if (j.contains("trading_class") && !j["trading_class"].is_null()) {
                    req.trading_class = j.value("trading_class", "");
                }
                req.is_combo = j.value("is_combo", false);

                if (main_engine_ != nullptr) {
                    main_engine_->send_order(req);
                } else {
                    all_ok = false;
                    err_msg = "Main engine is not running";
                }
            } else if (action == "cancel" || action == "cancel_order") {
                nlohmann::json j = nlohmann::json::parse(payload_json);
                utilities::CancelRequest req;
                req.orderid = j.value("orderid", "");
                req.symbol = j.value("symbol", "");
                req.exchange = utilities::from_string_exchange(j.value("exchange", "LOCAL"));
                req.is_combo = j.value("is_combo", false);

                if (main_engine_ != nullptr) {
                    main_engine_->cancel_order(req);
                } else {
                    all_ok = false;
                    err_msg = "Main engine is not running";
                }
            } else {
                std::printf("[gRPC SendCommand] Ignored unknown action: %s\n", action.c_str());
                std::fflush(stdout);
            }
        } catch (const std::exception& e) {
            all_ok = false;
            err_msg = std::string("JSON parse error: ") + e.what();
            std::printf("[gRPC SendCommand] Error processing action %s: %s\n", action.c_str(), e.what());
            std::fflush(stdout);
        }
    }

    response->set_command_id(last_cmd_id);
    response->set_success(all_ok);
    if (!all_ok) {
        response->set_error_message(err_msg);
    }
    return ::grpc::Status::OK;
}

} // namespace engines
