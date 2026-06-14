cmake_minimum_required(VERSION 3.20)
project(AffinityCoreEngine CXX)

# Require C++20
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# compiler flags for MSYS2 MinGW64
if(CMAKE_COMPILER_IS_GNUCXX)
    add_compile_options(-Wall -Wextra -O3 -pthread)
endif()

# Find package dependencies
find_package(Protobuf REQUIRED)
find_package(gRPC REQUIRED)
find_package(cppzmq REQUIRED)
find_package(Arrow REQUIRED)
find_package(Parquet REQUIRED)
find_package(absl REQUIRED)
find_package(CURL REQUIRED)

# lets_be_rational library compilation
set(LETS_BE_RATIONAL_SRC
    thirdparty/lets_be_rational/src/erf_cody.cpp
    thirdparty/lets_be_rational/src/LetsBeRational.cpp
    thirdparty/lets_be_rational/src/normaldistribution.cpp
    thirdparty/lets_be_rational/src/rationalcubic.cpp
)

add_library(lets_be_rational STATIC ${LETS_BE_RATIONAL_SRC})
target_include_directories(lets_be_rational PUBLIC
    thirdparty/lets_be_rational/src
)

# TWS C++ API client compilation
set(TWS_API_DIR "C:/TWS API/source/CppClient/client")
file(GLOB TWS_API_SRC
    "${TWS_API_DIR}/*.cpp"
    "${TWS_API_DIR}/protobuf/*.pb.cc"
)

add_library(tws_api STATIC ${TWS_API_SRC})
target_include_directories(tws_api PUBLIC 
    ${TWS_API_DIR}
    ${TWS_API_DIR}/protobuf
)
target_link_libraries(tws_api PUBLIC
    protobuf::libprotobuf
    ws2_32
    absl::log_internal_message
    absl::log_internal_nullguard
    absl::log_internal_check_op
    absl::raw_logging_internal
    CURL::libcurl
)

# Shared sources used across multiple executables
set(ENGINE_SOURCES
    core/engine_execution.cpp
    core/engine_hedge.cpp
    core/engine_log.cpp
    core/engine_option_strategy.cpp
    core/engine_position.cpp
    core/portfolio_structure.cpp
    
    infra/db/engine_db_pg.cpp
    infra/gateway/engine_gateway_ib.cpp
    infra/gateway/zmq_gateway_schema.cpp
    infra/marketdata/engine_data_historical.cpp
    infra/marketdata/engine_data_tradier.cpp
    infra/marketdata/zmq_marketdata_schema.cpp
    
    runtime/backtest/engine_backtest.cpp
    runtime/backtest/engine_event.cpp
    runtime/backtest/engine_main.cpp
    runtime/live/engine_event.cpp
    runtime/live/engine_grpc.cpp
    runtime/live/engine_main.cpp
    runtime/live/gateway_client.cpp
    runtime/live/market_data_client.cpp
    
    strategy/strategy_registry.cpp
    strategy/template.cpp
    
    utilities/black_scholes.cpp
    utilities/combo_builder.cpp
    utilities/decimal_mock.cpp
    utilities/object.cpp
    utilities/occ_utils.cpp
    utilities/parquet_loader.cpp
    utilities/portfolio.cpp
    utilities/utility.cpp
    
    # Generated protobuf and gRPC stubs
    proto/otrader_engine.pb.cc
    proto/otrader_engine.grpc.pb.cc
    proto/zmq_messages.pb.cc
)

# Common include directories
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/core
    ${CMAKE_CURRENT_SOURCE_DIR}/proto
    ${CMAKE_CURRENT_SOURCE_DIR}/runtime/backtest
    ${CMAKE_CURRENT_SOURCE_DIR}/runtime/live
    ${CMAKE_CURRENT_SOURCE_DIR}/utilities
    ${CMAKE_CURRENT_SOURCE_DIR}/strategy
    ${CMAKE_CURRENT_SOURCE_DIR}/infra
    ${CMAKE_CURRENT_SOURCE_DIR}/infra/db
    ${CMAKE_CURRENT_SOURCE_DIR}/infra/gateway
    ${CMAKE_CURRENT_SOURCE_DIR}/infra/marketdata
)

# 1. Target: entry_backtest
add_executable(entry_backtest
    entry_backtest.cpp
    ${ENGINE_SOURCES}
)
target_link_libraries(entry_backtest PRIVATE
    lets_be_rational
    tws_api
    Arrow::arrow_shared
    Parquet::parquet_shared
    protobuf::libprotobuf
    gRPC::grpc++
    cppzmq
)

# 2. Target: entry_live_grpc
add_executable(entry_live_grpc
    entry_live_grpc.cpp
    ${ENGINE_SOURCES}
)
target_link_libraries(entry_live_grpc PRIVATE
    lets_be_rational
    tws_api
    Arrow::arrow_shared
    Parquet::parquet_shared
    protobuf::libprotobuf
    gRPC::grpc++
    cppzmq
)

# 3. Target: entry_gateway
add_executable(entry_gateway
    entry_gateway.cpp
    ${ENGINE_SOURCES}
)
target_link_libraries(entry_gateway PRIVATE
    lets_be_rational
    tws_api
    Arrow::arrow_shared
    Parquet::parquet_shared
    protobuf::libprotobuf
    gRPC::grpc++
    cppzmq
)

# 4. Target: entry_market_data
add_executable(entry_market_data
    entry_market_data.cpp
    ${ENGINE_SOURCES}
)
target_link_libraries(entry_market_data PRIVATE
    lets_be_rational
    tws_api
    Arrow::arrow_shared
    Parquet::parquet_shared
    protobuf::libprotobuf
    gRPC::grpc++
    cppzmq
)

# 5. Target: entry_live
add_executable(entry_live
    entry_live.cpp
    ${ENGINE_SOURCES}
)
target_link_libraries(entry_live PRIVATE
    lets_be_rational
    tws_api
    Arrow::arrow_shared
    Parquet::parquet_shared
    protobuf::libprotobuf
    gRPC::grpc++
    cppzmq
)
