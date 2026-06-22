# Athena Aegis Engine — Interview Talking Points

> **How to use**: Read each section aloud as a fluid, spoken answer. The numbered headers match the 6 questions exactly.

---

## 1 / Problem & Objective

So the core problem Athena Aegis Engine is solving is a really hard one in quantitative finance:
how do you dynamically hedge an options portfolio in near-real-time, while simultaneously
being able to backtest that exact same strategy against years of historical tick data — and
do it all at institutional-grade latency and throughput?

Standard approaches typically force you to choose between a robust backtesting harness
*or* a live execution engine. What we built here is a unified platform where the same
domain logic — position tracking, delta hedging, P&L accounting, CVaR risk computations —
runs identically in both modes. In live mode, it connects to Interactive Brokers via the
TWS C++ API and streams real-time option chain snapshots. In backtest mode, it replays
historical Parquet tick files through the exact same event pipeline.

On top of that, the platform is a *deep hedging research platform*, meaning it integrates
trained PyTorch neural networks — LSTM, feed-forward, and minimax adversarial models — as
alternative hedging agents that can be evaluated head-to-head against the Black-Scholes
analytical delta as a baseline. So it's simultaneously an execution platform, a risk
analytics system, and an ML research evaluation loop.

---

## 2 / My Role

I was the sole developer and architect of this system from the ground up. I designed the
entire multi-process architecture, wrote the C++20 execution engine, built the Python
FastAPI orchestration layer, the PostgreSQL data models, the ARQ task queue integration,
and the Next.js dashboard. I also did the ML research work — training the LSTM, FFNN, and
minimax adversarial deep hedging models in PyTorch, exporting them as TorchScript `.pt`
files, and wiring them into the inference path inside the C++ engine via LibTorch.

The project also has a lineage — it evolved from an earlier prototype called OTrader. I
took that legacy foundation, refactored and modernized it into a clean microservices
architecture with strict process boundaries, a proper gRPC IPC layer, and a well-defined
separation between domain core, runtime, and infrastructure.

---

## 3 / The Data

There are several distinct data streams and datasets this system handles, and it's worth
being precise about each one.

**Live market data** comes in as real-time option chain snapshots from Interactive Brokers
via the TWS C++ API. These snapshots are `PortfolioSnapshot` protobuf messages containing
per-contract bid/ask/last prices, implied volatility, delta, gamma, theta, and vega
vectors — essentially the full Greeks surface for every subscribed option. These flow into
the C++ engine through a ZeroMQ PUB/SUB channel from the `entry_market_data` process on
port 5558.

**Historical backtest data** is stored as Apache Parquet files, organized by symbol and
date — for example `data/SPY/2024/20240315.parquet`. Each file represents one trading day
of tick-by-tick option chain frames, ingested by the C++ `BacktestDataEngine` using the
Apache Arrow/Parquet C++ library. The engine also supports multi-day runs by loading and
concatenating multiple Parquet files, with up to four files processed in parallel via
worker threads.

**Order chain and contract metadata** is seeded into PostgreSQL using Python crawlers in
the `scripts/` directory that pull from the Alpaca Options API — option chains, strikes,
expiries, and contract specs.

**The ML models** consume 5-dimensional feature tensors per tick: spot price, normalized
strike distance (S/K - 1), time-to-maturity in years, implied volatility, and the
previous-tick delta. These are defined in the research lab's training notebooks and match
the LibTorch inference input shape exactly.

**Persistent state** is stored in PostgreSQL using SQLModel ORM models: `Strategy`,
`BacktestJob`, `ModelRegistry`, `RiskSnapshot` (per-tick delta, gamma, CVaR-95, CVaR-99,
P&L), and `OrderRecord`/`TradeRecord` tables with execution timestamps and fill prices.

---

## 4 / Tools & Techniques

Let me break this down by layer:

**C++ Execution Engine (cpp_engine)** — Written in C++20, compiled with CMake and Ninja.
The core uses a pipelined, multi-threaded event architecture with lock-free MPSC ring
buffers for the main event stream and SPSC rings for the strategy stream, eliminating
mutex contention on the hot path. Memory allocation on hot paths is managed through object
pools — pre-allocated batches of Events, Orders, Trades, Snapshots, and LogData objects
that are acquired, filled, dispatched, and released rather than heap-allocated per-call.
Heavy payloads are passed by pointer, and backtest data is accessed as zero-copy columnar
views from Arrow arrays. For multi-day backtests, up to four `jthread`-based workers
process one Parquet file each in parallel, merging results in chronological order.

Key C++ dependencies: **gRPC** and **Protobuf** for IPC with the Python layer; **ZeroMQ
(cppzmq)** for intra-process messaging between the gateway, market data, and runtime
processes; **Apache Arrow + Parquet** for tick data ingestion; **libcurl** for HTTP;
**IB TWS C++ API** for broker connectivity; **lets_be_rational** (a third-party library)
for numerically precise Black-Scholes implied volatility inversion; and **LibTorch** (the
PyTorch C++ frontend) for loading and running the trained deep hedging models via
`torch::jit::load` with zero-copy tensor construction using `torch::from_blob`.
CUDA support is conditionally compiled via a `USE_CUDA` CMake flag.

**Python Backend Orchestrator (backend_orchestrator)** — FastAPI + Uvicorn for the REST
and WebSocket API layer. **ARQ** (async task queue backed by Redis) for durable,
cancellable backtest job execution. **asyncpg + SQLModel** for async PostgreSQL access.
**gRPC (grpcio)** for communication with the C++ `entry_live_grpc` process. The WebSocket
layer broadcasts at 60 Hz to connected frontend clients. **ReportLab** is used to
auto-generate PDF strategy performance reports after each backtest.

**ML Research Lab (research)** — **PyTorch** for training three model architectures:
LSTM (2-layer LSTM + Linear), FFNN (3-layer dense + ReLU), and a Minimax adversarial
model where a "Hedger" generator competes against a "Market Shocker" adversary. All models
are optimized against **Conditional Value-at-Risk (CVaR)** as the loss function rather
than MSE, making them directly tail-risk-aware. Models are exported via `torch.jit.trace`
as TorchScript `.pt` files and registered in the `ModelRegistry` table.

**Infrastructure** — **PostgreSQL** (port 5433) as the primary database, **Redis** (port
6379) as both the ARQ job queue and PubSub event broker, and **Docker Compose** to spin
up both services. The **Next.js** frontend provides the browser dashboard on port 3000.

---

## 5 / End-to-End Process Walkthrough

Let me walk you through what happens from the moment a user requests a backtest to when
results appear on the dashboard — because this captures most of the interesting engineering.

**Step 1 — API Request**: The user submits a `POST /api/run_backtest` request from the
Next.js frontend, specifying a strategy name, the Parquet data path, date range, fee rate,
slippage in basis points, risk-free rate, IV pricing mode (bid/ask/mid), and optionally
one or more deep hedging model IDs.

**Step 2 — Job Enqueuing**: The FastAPI handler creates a `Strategy` and `BacktestJob`
record in PostgreSQL with status `PENDING`, generates a correlation UUID, enqueues a
`run_backtest_job` task on the ARQ Redis queue, and immediately returns HTTP 202 with the
job ID.

**Step 3 — ARQ Worker Picks Up**: The ARQ worker dequeues the job, updates the status to
`RUNNING`, and resolves the Parquet path — if a date range spans multiple daily files, it
concatenates them into a temporary combined Parquet file using pandas.

**Step 4 — gRPC Stream to C++**: The Python worker opens an async gRPC channel to the
C++ `entry_live_grpc` process on `127.0.0.1:50051` and calls `StartBacktest` as a
server-streaming RPC, passing a `StreamRequest` proto with the `StrategyConfig`. The C++
engine receives this, loads the Parquet file using Apache Arrow, precomputes
`PortfolioSnapshot` objects for all timesteps in a single pass, and enters the event loop.

**Step 5 — C++ Tick Processing**: For each timestep, the engine dispatches a `Snapshot`
event, which updates the `PortfolioStructure` with current prices and Greeks. It then
dispatches a `Timer` event, triggering the `OptionStrategyEngine` (the registered strategy
logic) and the `HedgeEngine`. The `HedgeEngine` evaluates whether the portfolio's total
delta falls outside the configured `[delta_target ± delta_range]` band; if it does, it
computes the required hedge volume against the underlying and emits an `OrderRequest`. The
`BacktestEngine` matches this order immediately against the current bid or ask price with
configured slippage. Black-Scholes Greeks are computed analytically using `lets_be_rational`
for IV inversion and then applied to update the position summary.

**Step 6 — Per-Tick gRPC Streaming**: After each timestep, the C++ engine streams an
`EngineStateUpdate` protobuf message back to Python containing `cumulative_pnl`, `greeks`
(delta, gamma, theta, vega), `cvar` (CVaR at 95% and 99%), and `model_results` for each
registered deep hedging model. Python deserializes each message, publishes it to a Redis
PubSub channel (`job_stream:{job_id}`), and accumulates it into `RiskSnapshot` objects for
bulk DB insert.

**Step 7 — Real-Time UI Updates**: The frontend has an active WebSocket connection. The
backend subscribes to the Redis PubSub channel and forwards each `EngineStateUpdate` to
all connected WebSocket clients in real-time, driving live chart updates on the dashboard.
There's also a parallel polling task that reads intermediate trade/order JSON files written
by the C++ engine and inserts them into PostgreSQL as the backtest progresses.

**Step 8 — Completion & Report**: When the C++ stream ends, the ARQ worker computes
aggregate summary statistics: final P&L, net P&L after fees, max drawdown (computed by
stitching per-day PnL curves), and the annualized Sharpe ratio from daily returns. It bulk-
inserts all `RiskSnapshot` records, updates the `BacktestJob` status to `COMPLETE`, and
auto-generates a multi-page PDF report using ReportLab with embedded Matplotlib P&L charts.
The frontend polls `GET /api/backtest/jobs/{id}/report` to download the PDF.

---

## 6 / Challenges & Learnings

One of the most technically thorny challenges was managing the **concurrent cancellation
of a live gRPC stream** without leaving the system in a corrupt state.

Here's the concrete problem: A backtest job runs as a long-lived async gRPC server-
streaming call from the Python ARQ worker to the C++ engine. While this stream is active,
there are *three* concurrent asyncio tasks running in the same worker coroutine: the
primary `async for update in stream` loop consuming gRPC messages, a `poll_and_insert_temp_files`
task writing intermediate trade data to PostgreSQL every 500ms, and a `check_cancellation_loop`
task polling Redis every 100ms for a cancel signal.

The challenge is that if the user cancels mid-run, you need to simultaneously cancel the
gRPC stream (via `stream.cancel()`), cancel both background asyncio tasks, update the job
status to `CANCELLED` in PostgreSQL, clean up temporary Parquet and JSON files, and publish
a cancellation event to the Redis PubSub channel — all without leaking resources or
leaving half-written data in the database.

The way I resolved this was through a disciplined `try/except/finally` structure in the
`run_backtest_job` coroutine. The `finally` block unconditionally cancels both background
tasks and cleans up temporary files regardless of how the coroutine exits. The
`check_cancellation_loop` detects the Redis cancel key and calls `stream.cancel()`, which
raises an `AioRpcError` with `StatusCode.CANCELLED` in the main loop — this is caught and
re-raised as a proper `asyncio.CancelledError` so ARQ handles job lifecycle correctly.
The database is updated to `CANCELLED` only in that specific catch branch, not in the
general error handler.

The lesson was that in an async system with multiple concurrent tasks sharing mutable
external state — a database, a file system, a Redis channel, and a live gRPC connection —
you need to think very carefully about what "partial completion" means and design your
cancellation path as a first-class code path, not an afterthought. In high-throughput
financial systems, a half-committed state is often worse than a clean failure.

On the C++ side, a related challenge was ensuring the **parallel backtest workers** didn't
corrupt shared result structures. The solution was strict isolation: each `jthread` worker
owns its own `BacktestEngine` instance with no shared mutable state, communicates results
only by writing to a pre-allocated `daily_results[file_idx]` slot under a `std::mutex`
lock, and uses a shared `std::stop_source` so any worker encountering a fatal error can
signal all others to stop cleanly. Results are merged in deterministic file-index order
after all threads join, avoiding the need for a sort.

---

*Prepared from direct analysis of the Athena Aegis Engine codebase (cpp_engine, backend_orchestrator, research) — June 2026.*
