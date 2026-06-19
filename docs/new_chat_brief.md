# Deep Hedging & Execution Platform: Continuation Brief

Hello! We are resuming the development of the **Institutional-Grade Multi-Model Deep Hedging & Execution Platform**.

The core backtesting pipeline (C++ LibTorch engine, Python FastAPI orchestrator, Next.js frontend, and the ML model registry) is fully operational. We want to start building the remaining production features outlined in the PRD.

Please read the PRD located at [DeepHedging_Platform_PRD_v2_Python.txt](file:///c:/Users/User/Desktop/Affinity-Core/docs/DeepHedging_Platform_PRD_v2_Python.txt) and help me implement the following remaining tasks:

### 1. ZMQ Live Trading & Market Data Ingestion Flow (`FR-02`)
*   Wire the C++ `entry_gateway` (TWS API connector) and `entry_market_data` processes to receive live snapshot streams via ZeroMQ PUB/SUB sockets (`5556` and `5558`).
*   Establish the command loop to send orders and cancellations from the orchestrator through the gRPC commands thread to the execution core.

### 2. Thread isolation and CPU Affinity (`NFR-06`)
*   Pin the main C++ execution loop thread, ZeroMQ subscriber, and gRPC I/O threads to isolated CPU cores using `SetThreadAffinityMask` (since we are on Windows).
*   Add configuration environment variables to adjust affinity masks.

### 3. Automated Replay Checksum Test Suite (`NFR-03`)
*   Write a deterministic verification script that runs the C++ backtest twice over the same data span and asserts that the SHA-256 checksums of the emitted `EngineStateUpdate` stream logs match 100%.

### 4. PDF Strategy Report Generator
*   Build the `report_queue` worker task using ARQ to aggregate completed strategy results and generate PDF summaries.

---
Let's start with **Task 1: Wiring the ZeroMQ Live Ingestion Flow** or **Task 3: Deterministic Replay Checksum Test Suite**. What do you recommend?
