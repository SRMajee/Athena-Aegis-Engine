With the workspace restructured into the three domain silos, the development path must follow an "Inside-Out" progression. Building from the data contract outward ensures that by the time you reach the frontend, the data streaming from the C++ core is already perfectly shaped for both the immediate Black-Scholes baseline and the future ML models.

Here is the high-level roadmap to build out Phase 1 (the Black-Scholes baseline with ML scaffolding) and Phase 2 (the Machine Learning integration).

### Phase 1: The Contract Layer (gRPC / Protobuf)

Before touching any C++, Python, or TypeScript logic, the communication interface must be locked down.

* **Objective:** Define the exact `EngineStateUpdate` payload that the C++ engine will stream to the Python orchestrator.
* **Actions:**
* Modify `cpp_engine/proto/otrader_engine.proto` to include the standard Black-Scholes Greeks, P&L, and an empty/mock `repeated ModelResult model_results` array.
* Run `protoc` to generate both the C++ headers and the Python stubs (`_pb2.py`).



### Phase 2: The C++ Execution Core (Low-Latency Plumbing)

With the contract defined, the C++ engine must be configured to process market data, run the analytical math, and emit the stream.

* 
**Objective:** Achieve a deterministic execution loop that streams out the Black-Scholes baseline data via gRPC.


* **Actions:**
* Wire the `MainEngine` (in `cpp_engine/src/runtime/`) to the ZMQ market data ingestion.


* Ensure the execution loop calculates standard Greeks via `black_scholes.cpp`.


* Update the `engine_grpc.cpp` emission thread to serialize the event loop data into the new Protobuf schema.


* *ML Scaffolding:* Leave a commented-out stub in the execution loop (e.g., `// TODO: evaluate_ml_models()`) and pass empty dummy data into the Protobuf `model_results` array.



### Phase 3: The Python Orchestration Plane (Async Migration)

The C++ engine is now streaming high-speed data. The Python backend must act as an ultra-fast router to catch it and manage long-running jobs.

* 
**Objective:** Replace legacy blocking calls with an asynchronous, non-blocking architecture.


* **Actions:**
* 
**Data Models:** Replace raw `psycopg2` SQL queries in `backend_orchestrator/src/infra/db.py` with `SQLModel` schemas (e.g., `Strategy`, `BacktestJob`).


* **Task Queues:** Delete the subprocess-based `backtest_runner.py`. Implement `ARQ` (Async Redis Queue) worker coroutines to handle historical replays without spiking the API's CPU.


* 
**Stream Consumption:** Upgrade `remote_client.py` to use `grpc.aio`, iterating over the C++ stream and pushing the parsed Protobuf dictionaries into the FastAPI WebSocket broadcast loop.





### Phase 4: The Frontend Terminal (High-Frequency Telemetry)

The data is now flowing through the WebSockets. The UI must render it without crashing the browser.

* 
**Objective:** Build a resilient, 60Hz visualization surface.


* **Actions:**
* Update `frontend_terminal/src/store/useTradeStore.ts` to consume the new JSON payload structure.
* Implement the strict 10,000 data point FIFO eviction policy inside Zustand to prevent memory leaks.


* Wrap the Recharts components using a `requestAnimationFrame` hook to decouple the charting render cycle from the underlying WebSocket arrival rate.





---

### Phase 5: Machine Learning Integration (Future State)

Because the Protobuf schemas, database columns, and UI stores were built to handle the `model_results` array from the beginning, dropping in the ML models will require almost zero rework of the orchestrator or frontend.

* **Actions:**
* Build the Python ML research lab to train the FFNN, LSTM, and Adversarial models using the differentiable CVaR loss.


* Export the trained models as frozen `.pt` TorchScript artifacts.


* In the C++ `MainEngine`, replace the stub from Phase 2 with the LibTorch embedding. Use `torch::from_blob` to marshal the C++ structs into tensors without triggering heap allocations, execute the model, and populate the `model_results` Protobuf array.





To begin executing this plan, open `cpp_engine/proto/otrader_engine.proto`.