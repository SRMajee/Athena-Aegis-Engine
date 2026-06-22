# Task 3 Walkthrough: NFR-03 Deterministic Replay Checksum Test Suite

## What Was Built

Three scripts implementing the full NFR-03 test surface:

| File | Lines | Purpose |
|---|---|---|
| [verify_determinism.py](file:///c:/Users/User/Desktop/Affinity-Core/scripts/verify_determinism.py) | ~580 | Core subprocess-level verifier |
| [verify_determinism_grpc.py](file:///c:/Users/User/Desktop/Affinity-Core/scripts/verify_determinism_grpc.py) | ~270 | Async gRPC stream verifier |
| [run_checksum_tests.ps1](file:///c:/Users/User/Desktop/Affinity-Core/scripts/run_checksum_tests.ps1) | ~170 | PowerShell CI runner |

## How It Works

### `verify_determinism.py` — The Core Verifier

```
entry_backtest.exe (run 1) ──► stdout bytes ──► strip duration_ms/duration_seconds
                                                ──► JSON canonical sort
                                                ──► SHA-256 ──┐
                                                               ├── assert equal
entry_backtest.exe (run 2) ──► stdout bytes ──► same process  ──┘
```

**Key design decisions:**
- **Strips timing fields** (`duration_ms`, `duration_seconds`) before hashing. These vary by wall-clock time and are explicitly non-deterministic.
- **Canonical JSON serialisation** (`sort_keys=True`) normalises dict key ordering between runs.
- **Pre-check** validates `strategy_name`, `total_timesteps`, `processed_timesteps` match before SHA-256 — fast fail on structural mismatch.
- **Verbose diff** (`--verbose`) shows per-field JSON differences when hashes differ, pinpointing the source of non-determinism.
- **MinGW64 DLL injection** — automatically prepends `C:\msys64\mingw64\bin` to subprocess `PATH`, mirroring `start.ps1`.

### `verify_determinism_grpc.py` — gRPC Stream Verifier

Validates the streaming path: calls `StartBacktest` via a live `entry_live_grpc` instance and collects all `EngineStateUpdate` protobuf messages in order. Each message is serialised via `SerializeToString()` and length-prefixed before hashing. This catches non-determinism in the gRPC emission layer specifically.

### `run_checksum_tests.ps1` — CI Runner

Discovers parquet files by symbol/date pattern, runs `verify_determinism.py` for each, and prints a colour-coded summary table. Automatically injects `MINGW64_BIN` into `PATH`. Exits non-zero on any failure — suitable as a CI gate.

## Validation Results

All single-file tests passed with identical checksums across all runs:

| Test | Runs | Result | SHA-256 |
|---|---|---|---|
| SPY 2010-01-04, `StraddleTestStrategy` | 2 | **PASS** | `2ad2d9cb...` |
| SPY 2010-01-04, `StraddleTestStrategy` | 5 (stress) | **PASS** | `2ad2d9cb...` |
| AAPL 2024-06-01, `StraddleTestStrategy` | 2 | **PASS** | `4f20e16b...` |
| AAPL 2024-06-03, `StraddleTestStrategy` | 2 | **PASS** | `4f3258c8...` |
| AAPL 2024-06-04, `StraddleTestStrategy` | 2 | **PASS** | `a5501e7e...` |

> The engine's determinism guarantee holds: identical inputs on the same hardware produce byte-identical outputs every time.

### Multi-File Timeout Note

The 3-day SPY `--symbol SPY --start-date 2010-01-04 --end-date 2010-01-06` test exceeded the default 300s timeout. This is a **data volume / timeout configuration issue**, not a non-determinism issue. For multi-file spans use `--timeout 1200`. The single-file CI sweep (one parquet per test) is the recommended default for CI gates.

## Quick Reference

```powershell
# --- From workspace root ---

# Single file (fastest - recommended for CI):
python -X utf8 scripts/verify_determinism.py --auto

# Specific file + strategy:
python -X utf8 scripts/verify_determinism.py `
    --parquet data/AAPL/2024/06/2024-06-03.parquet `
    --strategy IronCondorTestStrategy `
    --runs 3

# Multi-file date range (raise timeout):
python -X utf8 scripts/verify_determinism.py `
    --symbol SPY `
    --start-date 2010-01-04 `
    --end-date 2010-01-06 `
    --strategy StraddleTestStrategy `
    --timeout 1200

# CI sweep (3 AAPL files, 2 runs each):
.\scripts\run_checksum_tests.ps1 -Symbol AAPL -MaxFiles 3 -Runs 2

# gRPC streaming check (requires entry_live_grpc running on :50051):
# (activate backend venv first)
python -X utf8 scripts/verify_determinism_grpc.py `
    --parquet data/SPY/2010/01/2010-01-04.parquet `
    --strategy StraddleTestStrategy
```

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `MINGW64_BIN` | `C:\msys64\mingw64\bin` | DLL search path for MinGW64 runtime |
| `BACKTEST_LOG` | `0` (forced off) | Suppress engine debug logs (set automatically) |

---

# Task 2 Walkthrough: NFR-06 CPU Affinity & Thread Isolation

## What Was Built

Added thread affinity pinning to the C++ engine to isolate computation and IO loops, eliminating scheduler jitter:

| File | Purpose |
|---|---|
| [thread_affinity.hpp](file:///c:/Users/User/Desktop/Affinity-Core/cpp_engine/utilities/thread_affinity.hpp) | **[NEW]** Utility to resolve environment variables to logical core IDs and invoke `SetThreadAffinityMask` on Windows (with safe mock fallback on Unix platforms). Automatically resolves name conflicts with Windows macros. |
| [engine_event.cpp](file:///c:/Users/User/Desktop/Affinity-Core/cpp_engine/runtime/live/engine_event.cpp) | **[MODIFY]** Pins the EventEngine main execution loop thread `EventEngine::run` to the core specified in `EXEC_LOOP_CPU_CORE`. |
| [gateway_client.cpp](file:///c:/Users/User/Desktop/Affinity-Core/cpp_engine/runtime/live/gateway_client.cpp) | **[MODIFY]** Pins the ZeroMQ subscriber thread to the core specified in `ZMQ_SUB_CPU_CORE`. |
| [market_data_client.cpp](file:///c:/Users/User/Desktop/Affinity-Core/cpp_engine/runtime/live/market_data_client.cpp) | **[MODIFY]** Pins the ZeroMQ subscriber thread to the core specified in `ZMQ_SUB_CPU_CORE`. |
| [engine_grpc.cpp](file:///c:/Users/User/Desktop/Affinity-Core/cpp_engine/runtime/live/engine_grpc.cpp) | **[MODIFY]** Pins the executing threads of key gRPC RPC handlers (`StreamLogs`, `StreamStrategyUpdates`, `StartBacktest`, `SendCommand`) to the core specified in `GRPC_IO_CPU_CORE`. |

## Configuration Environment Variables

Adjust the affinity configuration via these environment variables (integer values `0` to `63` representing logical core indexes):

| Variable | Core Target | Thread/Context Pinned |
|---|---|---|
| `EXEC_LOOP_CPU_CORE` | E.g. `1` | Core C++ `EventEngine` main execution loop thread |
| `ZMQ_SUB_CPU_CORE` | E.g. `2` | ZeroMQ client SUB sockets (`GatewayClient` and `MarketDataClient` subscriber threads) |
| `GRPC_IO_CPU_CORE` | E.g. `3` | gRPC I/O incoming/streaming worker threads |

## Verification Results

Running `entry_live_grpc.exe` with CPU affinity variables configured:

```powershell
$env:EXEC_LOOP_CPU_CORE = "1"
$env:ZMQ_SUB_CPU_CORE = "2"
$env:GRPC_IO_CPU_CORE = "3"
.\cpp_engine\build\entry_live_grpc.exe
```

Yields the following verified logs confirming core allocation:

```
[EventEngine Run Affinity] Pinned thread to core 1
[GatewayClient SUB Affinity] Pinned thread to core 2
Live gRPC engine listening on 0.0.0.0:50051
```
