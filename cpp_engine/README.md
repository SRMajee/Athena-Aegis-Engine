# C++ Execution Engine (cpp_engine)

The **C++ Execution Engine** is the core latency-sensitive component of the Affinity-Core platform. It handles tick ingestion, options analytics (Black-Scholes Greeks), neural network inference via LibTorch, and market connectivity (IBKR API via TWS C++ API).

---

## 📊 Component-Level Diagrams

### 1. Ingestion & Inference Flowchart
Describes the lifecycle of a market data tick through parsing and neural-net evaluation:

```mermaid
flowchart TD
    RawTick["Raw Market Tick (Parquet / ZeroMQ)"] --> Queue["Lock-Free SPSC Ring Buffer"]
    Queue --> ThreadAff["Affinity Thread (Core-Pinned)"]
    ThreadAff --> Parse["Tick Parser (Spot, Vol, Strike, DTE)"]
    Parse --> InputArray["Flat Float Array (100-300us)"]
    InputArray --> Tensor["LibTorch Tensor (torch::from_blob)"]
    Tensor --> Inference["LibTorch DLL (Inference)"]
    Inference --> Greeks["BS Analytical Greek Engine"]
    Greeks --> Strategy["Strategy Template Evaluation"]
    Strategy --> Out["gRPC Serialization & Streaming"]
```

### 2. High-Level Design (HLD)
Shows the C++ modules and their execution boundaries:

```mermaid
graph TD
    subgraph MainEngineCore ["MainEngine Core Loop"]
        ME["MainEngine Manager"]
        Aff["Thread Affinity Mask"]
    end

    subgraph DataIngestion ["Data Ingestion & Feed"]
        ZMQ["ZeroMQ Client"]
        FileSim["Parquet File Simulator"]
    end

    subgraph OptionAnalytics ["Analytics & Risk Core"]
        BS["Black-Scholes Calculator"]
        CVaR["Rolling CVaR Estimator"]
    end

    subgraph MLRuntime ["Machine Learning Runtime"]
        Wrapper["torch_inference.dll Wrapper"]
        LibTorch["LibTorch (CPU/CUDA)"]
    end

    subgraph IPCGateways ["IPC & gRPC Interfaces"]
        gRPC["EngineService (gRPC server)"]
        TWS["TWS C++ Client Interface"]
    end

    ZMQ -->|Ticks SPSC RingBuffer| ME
    FileSim -->|Ticks SPSC RingBuffer| ME
    ME -->|Pin thread| Aff
    ME -->|Calculate analytical parameters| BS
    ME -->|Evaluate sliding window| CVaR
    ME -->|Zero-Copy Tensors| Wrapper
    Wrapper -->|Evaluate model weights| LibTorch
    ME -->|Stream states| gRPC
    ME -->|Send orders| TWS
```

### 3. Tick Execution Sequence
Visualizes execution path in the hot tick loop:

```mermaid
sequenceDiagram
    autonumber
    participant Feed as Ingestion Thread
    participant Core as Core Engine Loop
    participant BS as BS Analytical Core
    participant LibTorch as LibTorch Wrapper
    participant Strat as Strategy Logic
    participant gRPC as gRPC Streaming Pipeline

    Feed->>Core: Put tick in Lock-Free Buffer
    activate Core
    Core->>BS: calculate_greeks(Spot, Strike, IV, DTE)
    BS-->>Core: Delta, Gamma, Theta, Vega
    Core->>LibTorch: evaluate_model_weights(Tensor Inputs)
    activate LibTorch
    LibTorch-->>Core: Neural-Net outputs (weights/offsets)
    deactivate LibTorch
    Core->>Strat: on_tick(TickData, Greeks, NetOutputs)
    activate Strat
    Note over Strat: Evaluate hedges,<br/>risk constraints,<br/>trigger orders if delta violates bands
    Strat-->>Core: Execution state / ComboOrders
    deactivate Strat
    Core->>gRPC: serialize_and_stream(EngineStateUpdate)
    deactivate Core
```

---

## 🗂️ Folder Structure

```
cpp_engine/
├── core/                    # Engine implementation (OptionStrategyEngine, Black-Scholes)
├── infra/                   # Networking & client implementations (IB C++ SDK wrapper)
├── proto/                   # Protobuf definitions and gRPC service descriptors
├── runtime/                 # Machine learning DLL wrappers (LibTorch bindings)
├── strategy/                # Base option strategy templates & compiled implementations
├── utilities/               # Helper routines (Affinity pinning, lock-free buffers, logs)
├── thirdparty/              # Vendor dependencies (nlohmann_json, zmq)
├── build/                   # Compilation files (Ninja/CMake)
└── strategy_config.json     # Default trading configuration settings JSON
```

---

## 💾 Data & REST/gRPC Interfaces

* **Data Formats**: Market ticks are ingested as binary packets or mapped from Parquet files containing `ts_recv`, `spot`, `bid`, `ask`, `vol`, `underlying_spot`, `strike`, and `dte` fields.
* **LibTorch Integration**: Tensor inputs are passed to model weights using `torch::from_blob` referencing memory allocations directly to guarantee zero-copy operations.
* **gRPC Pipeline**: Bidirectional streaming runs on `grpcio` inside port `50051`:
  * `StartBacktest`: Stream server updates (`EngineStateUpdate`).
  * `SendCommand`: Client sends remote instruction updates (`ConnectGateway`, `AddStrategy`, etc.).
