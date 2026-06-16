# Phase 5: Machine Learning & Adversarial Deep Hedging Plan

## 1. What to Say in the New Conversation (Copy & Paste)
> "Hello! I am starting a new conversation to implement **Phase 5: Machine Learning & Adversarial Deep Hedging Integration**.
> 
> The project structure consists of a Next.js frontend terminal, a FastAPI backend orchestrator (port 8085), and a native C++ gRPC backtest engine (port 50051). The analytical Black-Scholes baseline is fully operational.
> 
> Please read the comprehensive plan details located in `phase5_start_plan.md` in the workspace root, as well as the research references `HFT_CAMP_CODE.ipynb` and `AdversialDeepHedging.pdf` to guide the implementation of the deep hedging models and LibTorch C++ integration."

---

## 2. Current State & Infrastructure Context
* **C++ Engine Port**: `50051` (implements the gRPC interface `StartBacktest` defined in `otrader_engine.proto`).
* **FastAPI Backend Port**: `8085` (manages PostgreSQL via SQLModel and enqueues tasks via Redis/ARQ).
* **Data Directories**: OSI-structured daily options parquet datasets located at `data/{SYMBOL}/{YYYY}/{MM}/{YYYY-MM-DD}.parquet` (e.g. AAPL, SPY, MSFT).
* **Option Symbol Parsing**: Normalization is complete. The C++ parser extracts expiration and strike fields from option symbols of any length (length >= 15).
* **Websocket Telemetry**: Zustand store `useTradeStore.ts` merges streamed daily trades and fees dynamically.

---

## 3. Models to Build & Compare
We will build three comparative models to evaluate against the analytical Black-Scholes baseline:

1. **Feedforward Neural Network (FFNN)** (Standard Baseline):
   * **Inputs**: Delta, Days to Expiration (DTE), Strike Distance (Spot/Strike - 1), Implied Volatility (IV), and Spot Price.
   * **Outputs**: Optimal hedge ratio.
   * **Loss**: Differentiable CVaR (Conditional Value at Risk) loss.
2. **LSTM Policy Network** (Sequence Baseline):
   * Same inputs and loss as FFNN, but configured as a recurrent model to track historical spot/vol paths.
3. **Adversarial Deep Hedging System**:
   * **Hedger Network (Agent)**: Learns the optimal delta hedge policy.
   * **Market Generator Network (Adversary)**: Generates synthetic price and volatility paths designed to maximize the Hedger's loss.
   * **Training**: Minimax adversarial training loop.

---

## 4. Step-by-Step Implementation Plan

### **Step 1: Build the Python ML Workspace**
* Create `backend_orchestrator/src/ml/` folder.
* Implement training pipelines in PyTorch using data from options parquets, leveraging helper modules/code from `HFT_CAMP_CODE.ipynb` and referencing formulas in `AdversialDeepHedging.pdf`.
* Implement the differentiable CVaR loss function.

### **Step 2: Export Models to TorchScript**
* Save the trained FFNN, LSTM, and Adversarial policies as serialized `.pt` JIT modules:
  * `models/deep_hedge_ffnn.pt`
  * `models/deep_hedge_lstm.pt`
  * `models/deep_hedge_adversarial.pt`

### **Step 3: Integrate LibTorch in the C++ Execution Core**
* Link `LibTorch` in `cpp_engine/CMakeLists.txt`.
* Modify `cpp_engine/strategy/template.hpp` and `MainEngine` to load JIT models dynamically. The path to the `.pt` file will be passed dynamically via the `strategy_setting` JSON.
* In the hot-path execution loop:
  - Construct input tensors via `torch::from_blob` (avoiding memory allocations).
  - Execute forward pass (`model.forward()`).
  - Stream out results by populating the `repeated ModelResult model_results` array in the `EngineStateUpdate` Protobuf message.

### **Step 4: Stream and Visualize Results**
* Stream the model's calculated hedge ratio/delta live via WebSockets.
* In the Next.js Frontend, overlay the model's hedge ratio side-by-side with Black-Scholes Delta on the live charts, and show a comparative performance summary (final PnL, CVaR loss, tracking error) at backtest completion.
