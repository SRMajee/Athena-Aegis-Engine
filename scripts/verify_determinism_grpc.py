"""
verify_determinism_grpc.py
==========================
NFR-03 — Deterministic Replay Checksum Test Suite (gRPC streaming path)

Connects to a running `entry_live_grpc` server and calls `StartBacktest` twice
over identical parameters, collecting the full sequence of `EngineStateUpdate`
protobuf messages. Verifies that the SHA-256 of the serialised message stream
is identical between both runs.

This validates the gRPC streaming path specifically, complementing the
subprocess-level checksum in `verify_determinism.py`.

Prerequisites
-------------
  1. `entry_live_grpc` must be running:
       cpp_engine\\build\\entry_live_grpc.exe
  2. A parquet file must be accessible from the engine's working directory.
  3. The backend virtual environment must be active (for grpcio stubs).

Usage
-----
  # From the workspace root, with the backend venv active:
  cd backend_orchestrator
  .venv\\Scripts\\activate
  cd ..

  python scripts/verify_determinism_grpc.py \\
      --parquet data/SPY/2010/01/2010-01-04.parquet \\
      --strategy StraddleTestStrategy

  python scripts/verify_determinism_grpc.py \\
      --parquet data/AAPL/2024/06/2024-06-03.parquet \\
      --strategy IronCondorTestStrategy \\
      --runs 3 \\
      --verbose \\
      --target 127.0.0.1:50051

Exit codes
----------
  0  All runs produced identical SHA-256 checksums.
  1  Checksum mismatch or connection error.
  2  Configuration error.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path bootstrap: allow running from workspace root without installing the pkg
# ---------------------------------------------------------------------------
WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = WORKSPACE_ROOT / "backend_orchestrator"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

try:
    import grpc
    import grpc.aio
    from src.proto import otrader_engine_pb2 as pb2
    from src.proto import otrader_engine_pb2_grpc as pb2_grpc
except ImportError as e:
    print(
        f"ImportError: {e}\n\n"
        "This script requires grpcio and the backend proto stubs.\n"
        "Activate the backend virtual environment:\n"
        "    cd backend_orchestrator && .venv\\Scripts\\activate\n",
        file=sys.stderr,
    )
    sys.exit(2)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_TARGET = "127.0.0.1:50051"
DEFAULT_TIMEOUT = 120  # seconds per run


# ─────────────────────────────────────────────────────────────────────────────
# Single backtest run via gRPC
# ─────────────────────────────────────────────────────────────────────────────

async def run_grpc_backtest(
    target: str,
    parquet_path: str,
    strategy: str,
    fee_rate: float,
    slippage_bps: float,
    risk_free_rate: float,
    iv_price_mode: str,
    run_index: int,
    timeout: float,
) -> list[bytes]:
    """
    Call StartBacktest once and collect all EngineStateUpdate messages,
    serialised to bytes via SerializeToString().

    Returns a list of per-message byte strings in stream order.
    """
    job_id = str(uuid.uuid4())

    strat_cfg = pb2.StrategyConfig(
        parquet_path=str(Path(WORKSPACE_ROOT / parquet_path)),
        strategy_name=strategy,
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
        risk_free_rate=risk_free_rate,
        iv_price_mode=iv_price_mode,
        strategy_setting="{}",
    )
    stream_req = pb2.StreamRequest(
        job_id=job_id,
        correlation_id=f"det-check-{run_index}",
        model_ids=[],
        strategy=strat_cfg,
    )

    message_bytes: list[bytes] = []
    t0 = time.perf_counter()

    async with grpc.aio.insecure_channel(target) as channel:
        stub = pb2_grpc.EngineServiceStub(channel)
        stream = stub.StartBacktest(stream_req, timeout=timeout)
        async for update in stream:
            message_bytes.append(update.SerializeToString())

    elapsed = time.perf_counter() - t0
    print(
        f"  [run {run_index}] {len(message_bytes)} messages received "
        f"({sum(len(b) for b in message_bytes):,} bytes total) in {elapsed:.2f}s"
    )
    return message_bytes


# ─────────────────────────────────────────────────────────────────────────────
# Hashing
# ─────────────────────────────────────────────────────────────────────────────

def compute_stream_checksum(message_bytes: list[bytes]) -> str:
    """
    Concatenate all message byte strings in stream order and SHA-256 hash
    the result. Each message is length-prefixed (4-byte big-endian) so that
    {msg_A, msg_B} ≠ {msg_AB} even if binary concat would collide.
    """
    h = hashlib.sha256()
    for msg in message_bytes:
        length_prefix = len(msg).to_bytes(4, "big")
        h.update(length_prefix)
        h.update(msg)
    return h.hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Diff reporting (field-level)
# ─────────────────────────────────────────────────────────────────────────────

def parse_update_to_dict(raw: bytes) -> dict[str, Any]:
    """Deserialise EngineStateUpdate bytes → Python dict via MessageToDict."""
    from google.protobuf.json_format import MessageToDict
    msg = pb2.EngineStateUpdate()
    msg.ParseFromString(raw)
    return MessageToDict(msg, preserving_proto_field_name=True)


def report_stream_diff(runs: list[list[bytes]], verbose: bool) -> None:
    """Print a diagnostic when stream checksums differ."""
    print("\n── gRPC Stream Mismatch Diagnostic ──────────────────────────────────────────")
    for i, msgs in enumerate(runs):
        print(f"  run {i + 1}: {len(msgs)} messages, "
              f"{sum(len(m) for m in msgs):,} total bytes")

    if len(runs) >= 2 and len(runs[0]) != len(runs[1]):
        print(f"\n  ✗ Message count differs: run 1 = {len(runs[0])}, run 2 = {len(runs[1])}")

    if not verbose:
        print("\nRe-run with --verbose for per-message field diff.")
        return

    min_msgs = min(len(r) for r in runs)
    print(f"\n── Per-Message Diff (first {min_msgs} messages, run 1 vs run 2) ─────────────")
    diffs_found = 0
    for idx in range(min_msgs):
        d1 = parse_update_to_dict(runs[0][idx])
        d2 = parse_update_to_dict(runs[1][idx])
        if d1 != d2:
            diffs_found += 1
            print(f"\n  Message #{idx}: DIFFERS")
            # Show first 5 differing fields
            shown = 0
            for key in sorted(set(d1) | set(d2)):
                v1 = d1.get(key, "<missing>")
                v2 = d2.get(key, "<missing>")
                if v1 != v2:
                    print(f"    .{key}: {v1!r} ≠ {v2!r}")
                    shown += 1
                    if shown >= 5:
                        break
            if diffs_found >= 10:
                print(f"\n  ... (stopped after {diffs_found} differing messages)")
                break

    if diffs_found == 0:
        print("  No per-message differences found — non-determinism may be in "
              "message count or ordering.")
    print("─────────────────────────────────────────────────────────────────────────────\n")


# ─────────────────────────────────────────────────────────────────────────────
# Main async test runner
# ─────────────────────────────────────────────────────────────────────────────

async def run_checksum_test_async(
    target: str,
    parquet_path: str,
    strategy: str,
    fee_rate: float,
    slippage_bps: float,
    risk_free_rate: float,
    iv_price_mode: str,
    num_runs: int,
    timeout: float,
    verbose: bool,
) -> bool:
    """
    Run StartBacktest `num_runs` times against the live gRPC engine and verify
    that all stream checksums match.
    """
    print(f"\n{'─' * 78}")
    print(f"  Target   : {target}")
    print(f"  Parquet  : {parquet_path}")
    print(f"  Strategy : {strategy}")
    print(f"  Runs     : {num_runs}")
    print(f"  Timeout  : {timeout}s per run")
    print(f"{'─' * 78}\n")

    all_runs: list[list[bytes]] = []
    checksums: list[str] = []

    for run_idx in range(1, num_runs + 1):
        print(f"  Starting run {run_idx}...")
        try:
            msgs = await asyncio.wait_for(
                run_grpc_backtest(
                    target=target,
                    parquet_path=parquet_path,
                    strategy=strategy,
                    fee_rate=fee_rate,
                    slippage_bps=slippage_bps,
                    risk_free_rate=risk_free_rate,
                    iv_price_mode=iv_price_mode,
                    run_index=run_idx,
                    timeout=timeout,
                ),
                timeout=timeout + 10,  # asyncio.wait_for adds a small buffer
            )
        except asyncio.TimeoutError:
            print(f"\n  ✗ TIMEOUT: run {run_idx} exceeded {timeout}s.")
            return False
        except grpc.aio.AioRpcError as e:
            print(f"\n  ✗ gRPC ERROR (run {run_idx}): [{e.code()}] {e.details()}")
            if "UNAVAILABLE" in str(e.code()):
                print(f"    Is entry_live_grpc running on {target}?")
            return False

        if not msgs:
            print(f"\n  ✗ Run {run_idx}: received 0 messages — "
                  "backtest may have returned immediately without processing any ticks.")
            return False

        all_runs.append(msgs)
        cs = compute_stream_checksum(msgs)
        checksums.append(cs)
        print(f"  run {run_idx} SHA-256 : {cs}")

        # Brief pause between runs to let the engine fully reset
        if run_idx < num_runs:
            await asyncio.sleep(0.5)

    # Compare all checksums against run 1
    reference = checksums[0]
    all_match = all(cs == reference for cs in checksums)

    if all_match:
        print(f"\n  ✓ GRPC STREAM DETERMINISM CONFIRMED — "
              f"all {num_runs} run(s) produced identical stream checksums.")
        print(f"    SHA-256 : {reference}")
        return True
    else:
        print(f"\n  ✗ GRPC STREAM DETERMINISM VIOLATION — checksum mismatch!")
        for i, cs in enumerate(checksums):
            marker = "✓" if cs == reference else "✗"
            print(f"    run {i + 1}: {marker} {cs}")
        report_stream_diff(all_runs[:2], verbose)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="NFR-03 Deterministic gRPC Stream Checksum Verifier",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--parquet", required=True, metavar="PATH",
        help="Path to a .parquet file (workspace-relative or absolute).",
    )
    p.add_argument(
        "--strategy", default="StraddleTestStrategy", metavar="NAME",
        help="Strategy class name (default: StraddleTestStrategy).",
    )
    p.add_argument(
        "--target", default=DEFAULT_TARGET, metavar="HOST:PORT",
        help=f"gRPC server address (default: {DEFAULT_TARGET}).",
    )
    p.add_argument("--fee-rate", type=float, default=0.35)
    p.add_argument("--slippage-bps", type=float, default=5.0)
    p.add_argument("--risk-free-rate", type=float, default=0.05)
    p.add_argument("--iv-price-mode", default="mid", choices=["mid", "bid", "ask"])
    p.add_argument("--runs", type=int, default=2, metavar="N",
                   help="Number of identical runs (default 2, min 2).")
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                   help=f"Per-run timeout in seconds (default {DEFAULT_TIMEOUT}).")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Show per-message field diff on mismatch.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.runs < 2:
        print("Error: --runs must be >= 2.", file=sys.stderr)
        return 2

    success = asyncio.run(
        run_checksum_test_async(
            target=args.target,
            parquet_path=args.parquet,
            strategy=args.strategy,
            fee_rate=args.fee_rate,
            slippage_bps=args.slippage_bps,
            risk_free_rate=args.risk_free_rate,
            iv_price_mode=args.iv_price_mode,
            num_runs=args.runs,
            timeout=args.timeout,
            verbose=args.verbose,
        )
    )
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
