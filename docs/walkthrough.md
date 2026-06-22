# Walkthrough — Protobuf Data Contract (Phase 1)

We have successfully defined and compiled the new real-time options risk and backtesting data contract.

## Changes Made

### 1. Protobuf Definitions
In [otrader_engine.proto](file:///c:/Users/User/Desktop/Affinity-Core/cpp_engine/proto/otrader_engine.proto), we added:
- **`StrategyConfig`**: Configuration parameters of the options trading strategy.
- **`StreamRequest`**: Input payload requesting a risk/state update stream.
- **`GreeksPayload`**: Standard Black-Scholes Greeks (Delta, Gamma, Vega, Theta, Rho).
- **`CVaRPayload`**: Real-time tail risk statistics (VaR/CVaR at 95% and 99%).
- **`ModelResult`**: Output metrics for each hedging model (hedge ratio, latency, P&L).
- **`EngineStateUpdate`**: Emitted event stream data structure linking baseline Greeks, P&L, timestamps, and model results.
- **`CommandRequest` & `CommandAck`**: Interface for downstream control execution commands (pause, resume, stop, model swap).
- **`EngineService`**: Added `StartBacktest` (server-side stream) and `SendCommand` (client-side stream).

### 2. Compiled Stubs
- **Python**: Generated stubs in [backend_orchestrator/src/proto/](file:///c:/Users/User/Desktop/Affinity-Core/backend_orchestrator/src/proto/):
  - `otrader_engine_pb2.py`
  - `otrader_engine_pb2_grpc.py`
- **C++**: Generated stubs in [cpp_engine/proto/](file:///c:/Users/User/Desktop/Affinity-Core/cpp_engine/proto/):
  - `otrader_engine.pb.h` / `otrader_engine.pb.cc`
  - `otrader_engine.grpc.pb.h` / `otrader_engine.grpc.pb.cc`

---

## Verification Results

### gRPC Method Registrations

We ran search scripts verifying that the compiled stubs contain the new methods:
- **Python stubs (`otrader_engine_pb2_grpc.py`)**: `StartBacktest` (unary-to-stream) and `SendCommand` (stream-to-unary) are present in the service client/server classes.
- **C++ headers (`otrader_engine.grpc.pb.h`)**: The C++ virtual methods and client interfaces for `StartBacktest` are successfully declared.
