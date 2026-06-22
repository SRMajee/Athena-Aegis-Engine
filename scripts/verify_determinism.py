"""
verify_determinism.py
=====================
NFR-03 - Deterministic Replay Checksum Test Suite (subprocess path)

Runs the C++ `entry_backtest` binary twice over identical inputs and asserts
that the SHA-256 checksums of the emitted stdout payloads are equal.

Usage
-----
  # Single parquet file, strategy by class name:
  python -X utf8 scripts/verify_determinism.py \\
      --parquet data/SPY/2010/01/2010-01-04.parquet \\
      --strategy StraddleTestStrategy

  # Symbol (auto-resolve date range from data/):
  python -X utf8 scripts/verify_determinism.py \\
      --symbol SPY \\
      --start-date 2010-01-04 \\
      --end-date 2010-01-06 \\
      --strategy IronCondorTestStrategy \\
      --runs 3 \\
      --verbose \\
      --timeout 1200

  # Quick self-test against any available file:
  python -X utf8 scripts/verify_determinism.py --auto

Exit codes
----------
  0  All runs produced identical SHA-256 checksums - determinism confirmed.
  1  Checksum mismatch or execution error - non-determinism detected.
  2  Usage / configuration error.

Notes
-----
  Multi-file mode (--symbol with a date range spanning multiple days) invokes
  the entry_backtest `--files` code path, which uses a 4-thread worker pool to
  process days in parallel.  For symbols with many option chains (e.g. SPY),
  each file can take 30-300s to process.  Raise --timeout accordingly when
  testing multi-file spans (recommended: 1200s for 3+ day ranges).

  The MINGW64_BIN env var can override the default C:\\msys64\\mingw64\\bin DLL
  search path used to launch the entry_backtest subprocess on Windows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Force UTF-8 output on Windows (avoids cp1252 encode errors for Unicode symbols).
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Fields whose values are allowed to differ between runs (pure wall-clock timing).
# These are stripped from the JSON payload before hashing so that execution
# speed variation does not produce false negatives.
TIMING_FIELDS_TO_STRIP = {"duration_ms", "duration_seconds"}

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = WORKSPACE_ROOT / "cpp_engine" / "build"
BINARY_NAME = "entry_backtest.exe"


# ─────────────────────────────────────────────────────────────────────────────
# Binary resolution
# ─────────────────────────────────────────────────────────────────────────────

def find_binary() -> Path:
    """Locate entry_backtest.exe in the build tree."""
    direct = BUILD_DIR / BINARY_NAME
    if direct.is_file():
        return direct
    # Walk up to 3 levels inside build/ (handles Debug/Release sub-dirs)
    for candidate in BUILD_DIR.rglob(BINARY_NAME):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"Could not find '{BINARY_NAME}' under {BUILD_DIR}.\n"
        "Please build the C++ engine first: "
        "cd cpp_engine/build && ninja entry_backtest"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Parquet path resolution  (mirrors task_queue.resolve_parquet_path logic)
# ─────────────────────────────────────────────────────────────────────────────

def _collect_parquet_files(symbol: str, start_date: str, end_date: str) -> list[str]:
    """Return sorted absolute paths for a symbol within the given date range."""
    data_dir = WORKSPACE_ROOT / "data" / symbol
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    start_clean = start_date.replace("-", "") if start_date else ""
    end_clean = end_date.replace("-", "") if end_date else ""

    files: list[str] = []
    for f in sorted(data_dir.rglob("*.parquet")):
        stem = f.stem.replace("-", "")
        if len(stem) == 8 and stem.isdigit():
            if start_clean and end_clean:
                if start_clean <= stem <= end_clean:
                    files.append(str(f))
            else:
                files.append(str(f))

    if not files:
        raise FileNotFoundError(
            f"No parquet files found for symbol '{symbol}' "
            f"in date range {start_date!r} – {end_date!r}"
        )
    return files


def resolve_parquet_args(args: argparse.Namespace) -> list[str]:
    """
    Return the CLI fragment(s) that specify the parquet input to entry_backtest.
    Either: [single_path]  or  ["--files", f1, f2, ...]
    """
    if args.parquet:
        p = Path(args.parquet)
        if not p.is_absolute():
            p = WORKSPACE_ROOT / p
        if not p.is_file():
            raise FileNotFoundError(f"Parquet file not found: {p}")
        return [str(p)]

    if args.symbol:
        files = _collect_parquet_files(
            args.symbol,
            getattr(args, "start_date", "") or "",
            getattr(args, "end_date", "") or "",
        )
        if len(files) == 1:
            return [files[0]]
        return ["--files"] + files

    raise ValueError("Provide --parquet or --symbol")


def auto_find_test_file() -> tuple[str, str]:
    """Return (parquet_path, strategy_name) for the first usable test case."""
    strategy = "StraddleTestStrategy"
    for sym in ("SPY", "AAPL", "MSFT", "NVDA"):
        d = WORKSPACE_ROOT / "data" / sym
        if d.is_dir():
            for f in sorted(d.rglob("*.parquet")):
                return str(f), strategy
    raise RuntimeError("No parquet data found for auto-test. Download some data first.")


# ─────────────────────────────────────────────────────────────────────────────
# Execution
# ─────────────────────────────────────────────────────────────────────────────

def build_cmd(
    binary: Path,
    parquet_args: list[str],
    strategy: str,
    fee_rate: float,
    slippage_bps: float,
    risk_free_rate: float,
    iv_price_mode: str,
    extra_settings: dict[str, float],
) -> list[str]:
    cmd = [str(binary)] + parquet_args + [strategy]
    cmd += ["--fee-rate", str(fee_rate)]
    cmd += ["--slippage-bps", str(slippage_bps)]
    cmd += ["--risk-free-rate", str(risk_free_rate)]
    cmd += ["--iv-price-mode", iv_price_mode]
    for k, v in extra_settings.items():
        cmd.append(f"{k}={v}")
    return cmd


def run_backtest(cmd: list[str], timeout: int, run_index: int) -> bytes:
    """
    Execute entry_backtest and return its stdout as raw bytes.
    Raises RuntimeError if the process exits non-zero or times out.
    """
    env = os.environ.copy()
    # Suppress debug logs that carry wall-clock timestamps (they go to stderr,
    # but belt-and-suspenders: disable explicitly).
    env["BACKTEST_LOG"] = "0"

    # On Windows the binary is built with MSYS2/MinGW64; ensure runtime DLLs
    # are on PATH. Mirrors the `$env:PATH = "C:\msys64\mingw64\bin;$env:PATH"`
    # injection in start.ps1. Configurable via MINGW64_BIN env var.
    mingw_bin = os.getenv("MINGW64_BIN", r"C:\msys64\mingw64\bin")
    if mingw_bin and os.path.isdir(mingw_bin):
        env["PATH"] = mingw_bin + os.pathsep + env.get("PATH", "")

    print(f"  [run {run_index}] $ {' '.join(cmd[:6])}{'...' if len(cmd) > 6 else ''}")
    t0 = time.perf_counter()

    result = subprocess.run(
        cmd,
        capture_output=True,
        timeout=timeout,
        env=env,
    )

    elapsed = time.perf_counter() - t0
    print(f"  [run {run_index}] completed in {elapsed:.2f}s, "
          f"stdout={len(result.stdout)} bytes, returncode={result.returncode}")

    if result.returncode != 0:
        stderr_tail = result.stderr[-2000:].decode("utf-8", errors="replace") if result.stderr else ""
        stdout_tail = result.stdout[-500:].decode("utf-8", errors="replace") if result.stdout else ""
        raise RuntimeError(
            f"Run {run_index}: entry_backtest exited with code {result.returncode}.\n"
            f"stderr tail:\n{stderr_tail}\n"
            f"stdout tail:\n{stdout_tail}"
        )

    if not result.stdout:
        raise RuntimeError(f"Run {run_index}: entry_backtest produced no stdout output.")

    return result.stdout


# ─────────────────────────────────────────────────────────────────────────────
# Hashing & comparison
# ─────────────────────────────────────────────────────────────────────────────

def strip_timing(obj: Any) -> Any:
    """Recursively remove timing-only fields from a JSON-parsed object."""
    if isinstance(obj, dict):
        return {
            k: strip_timing(v)
            for k, v in obj.items()
            if k not in TIMING_FIELDS_TO_STRIP
        }
    if isinstance(obj, list):
        return [strip_timing(item) for item in obj]
    return obj


def compute_checksum(raw_bytes: bytes) -> str:
    """
    Parse stdout as JSON, strip non-deterministic timing fields, re-serialise
    with sorted keys and no whitespace, then compute SHA-256.

    This is more robust than hashing raw bytes because:
      1. Duration fields are excluded.
      2. Dict key ordering is normalised (Python dict is insertion-ordered but
         C++ JSON output is already stable; this is belt-and-suspenders).
    """
    try:
        obj = json.loads(raw_bytes.decode("utf-8"))
    except json.JSONDecodeError as e:
        # Fall back to raw bytes if not valid JSON (will expose the error later)
        raise ValueError(f"entry_backtest stdout is not valid JSON: {e}\n"
                         f"Stdout head: {raw_bytes[:300]!r}")

    obj = strip_timing(obj)
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_raw_checksum(raw_bytes: bytes) -> str:
    """SHA-256 of the raw byte string (backup comparison)."""
    return hashlib.sha256(raw_bytes).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Diff reporting
# ─────────────────────────────────────────────────────────────────────────────

def _diff_json(a: Any, b: Any, path: str = "root") -> list[str]:
    """Return a list of human-readable diff lines between two JSON-parsed objects."""
    diffs: list[str] = []

    if type(a) != type(b):
        diffs.append(f"  {path}: type changed {type(a).__name__!r} → {type(b).__name__!r}")
        return diffs

    if isinstance(a, dict):
        all_keys = set(a) | set(b)
        for k in sorted(all_keys):
            child_path = f"{path}.{k}"
            if k not in a:
                diffs.append(f"  {child_path}: MISSING in run 1 (run 2 = {b[k]!r})")
            elif k not in b:
                diffs.append(f"  {child_path}: MISSING in run 2 (run 1 = {a[k]!r})")
            else:
                diffs.extend(_diff_json(a[k], b[k], child_path))

    elif isinstance(a, list):
        if len(a) != len(b):
            diffs.append(f"  {path}: list length {len(a)} vs {len(b)}")
            min_len = min(len(a), len(b))
            for i in range(min_len):
                diffs.extend(_diff_json(a[i], b[i], f"{path}[{i}]"))
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                diffs.extend(_diff_json(x, y, f"{path}[{i}]"))

    elif isinstance(a, float) and isinstance(b, float):
        if a != b:
            diffs.append(f"  {path}: {a!r} ≠ {b!r}  (diff = {abs(a - b):.6g})")

    else:
        if a != b:
            diffs.append(f"  {path}: {a!r} ≠ {b!r}")

    return diffs


def report_diff(outputs: list[bytes], verbose: bool) -> None:
    """Print a diagnostic report when checksums differ."""
    print("\n── Mismatch Diagnostic ──────────────────────────────────────────────────────")
    for i, raw in enumerate(outputs):
        print(f"  run {i + 1} raw size : {len(raw)} bytes")
        cs_raw = compute_raw_checksum(raw)
        print(f"  run {i + 1} raw SHA-256: {cs_raw}")

    if not verbose:
        print("\nRe-run with --verbose for a per-field diff report.")
        return

    try:
        parsed = []
        for raw in outputs:
            obj = json.loads(raw.decode("utf-8"))
            obj = strip_timing(obj)
            parsed.append(obj)
    except Exception as e:
        print(f"  Could not parse JSON for diff: {e}")
        return

    print("\n── Per-Field Diff (run 1 vs run 2) ─────────────────────────────────────────")
    diffs = _diff_json(parsed[0], parsed[1])
    if not diffs:
        print("  No structural differences found in JSON fields.")
        print("  Non-determinism may be in whitespace/encoding — check raw bytes.")
    else:
        max_diffs_shown = 50
        for line in diffs[:max_diffs_shown]:
            print(line)
        if len(diffs) > max_diffs_shown:
            print(f"  ... ({len(diffs) - max_diffs_shown} more differences not shown)")
    print("─────────────────────────────────────────────────────────────────────────────\n")


# ─────────────────────────────────────────────────────────────────────────────
# Quick sanity pre-check
# ─────────────────────────────────────────────────────────────────────────────

def pre_check(outputs: list[bytes]) -> bool:
    """
    Fast structural pre-check before full SHA-256.
    Parses JSON from each output and compares strategy_name + total_timesteps.
    Returns True if all match, False on mismatch.
    """
    records: list[dict] = []
    for i, raw in enumerate(outputs):
        try:
            obj = json.loads(raw.decode("utf-8"))
        except Exception as e:
            print(f"  [pre-check] run {i+1}: JSON parse error: {e}")
            return False
        if obj.get("status") != "ok":
            print(f"  [pre-check] run {i+1}: status != 'ok': {obj.get('error', '?')}")
            return False
        records.append(obj.get("result", {}))

    ref = records[0]
    for i, rec in enumerate(records[1:], start=2):
        for key in ("strategy_name", "total_timesteps", "processed_timesteps", "total_frames"):
            if ref.get(key) != rec.get(key):
                print(f"  [pre-check] MISMATCH at result.{key}: "
                      f"run 1={ref.get(key)!r}, run {i}={rec.get(key)!r}")
                return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Main test runner
# ─────────────────────────────────────────────────────────────────────────────

def run_checksum_test(
    parquet_args: list[str],
    strategy: str,
    fee_rate: float,
    slippage_bps: float,
    risk_free_rate: float,
    iv_price_mode: str,
    extra_settings: dict[str, float],
    num_runs: int,
    timeout: int,
    verbose: bool,
) -> bool:
    """
    Execute the backtest `num_runs` times and verify all SHA-256 checksums match.
    Returns True on success (deterministic), False on failure.
    """
    binary = find_binary()
    cmd = build_cmd(
        binary, parquet_args, strategy,
        fee_rate, slippage_bps, risk_free_rate, iv_price_mode, extra_settings,
    )

    print(f"\n{'─' * 78}")
    print(f"  Binary   : {binary}")
    print(f"  Strategy : {strategy}")
    print(f"  Parquet  : {parquet_args}")
    print(f"  Runs     : {num_runs}")
    print(f"  Timeout  : {timeout}s per run")
    print(f"{'─' * 78}\n")

    outputs: list[bytes] = []
    for run_idx in range(1, num_runs + 1):
        try:
            raw = run_backtest(cmd, timeout, run_idx)
            outputs.append(raw)
        except subprocess.TimeoutExpired:
            print(f"\n  ✗ TIMEOUT: run {run_idx} exceeded {timeout}s.")
            return False
        except RuntimeError as e:
            print(f"\n  ✗ EXECUTION ERROR (run {run_idx}):\n{e}")
            return False

    # Pre-check
    print("\n  Running pre-check (strategy_name / timesteps)...")
    if not pre_check(outputs):
        print("  ✗ PRE-CHECK FAILED: structural mismatch before hashing.")
        if verbose:
            report_diff(outputs[:2], verbose)
        return False
    print("  ✓ Pre-check passed.")

    # Compute checksums
    checksums: list[str] = []
    for i, raw in enumerate(outputs):
        try:
            cs = compute_checksum(raw)
        except ValueError as e:
            print(f"\n  ✗ CHECKSUM ERROR (run {i+1}): {e}")
            return False
        checksums.append(cs)
        print(f"  run {i + 1} SHA-256 : {cs}")

    # Compare
    reference = checksums[0]
    all_match = all(cs == reference for cs in checksums)

    if all_match:
        print(f"\n  ✓ DETERMINISM CONFIRMED — all {num_runs} run(s) produced identical checksums.")
        print(f"    SHA-256 : {reference}")
        return True
    else:
        print(f"\n  ✗ DETERMINISM VIOLATION — checksum mismatch detected!")
        for i, cs in enumerate(checksums):
            marker = "✓" if cs == reference else "✗"
            print(f"    run {i + 1}: {marker} {cs}")
        report_diff(outputs[:2], verbose)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="NFR-03 Deterministic Replay Checksum Verifier",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Input specification (mutually exclusive)
    input_group = p.add_mutually_exclusive_group()
    input_group.add_argument(
        "--parquet", metavar="PATH",
        help="Absolute or workspace-relative path to a .parquet file."
    )
    input_group.add_argument(
        "--symbol", metavar="SYM",
        help="Symbol name to resolve from data/<SYM>/ directory."
    )
    input_group.add_argument(
        "--auto", action="store_true",
        help="Auto-discover the first available parquet file and run the test."
    )

    # Date range (for --symbol)
    p.add_argument("--start-date", metavar="YYYY-MM-DD", default="",
                   help="Start date filter (inclusive) when using --symbol.")
    p.add_argument("--end-date", metavar="YYYY-MM-DD", default="",
                   help="End date filter (inclusive) when using --symbol.")

    # Strategy
    p.add_argument(
        "--strategy", metavar="NAME", default="StraddleTestStrategy",
        help="Strategy class name (default: StraddleTestStrategy). "
             "Available: StraddleTestStrategy, IronCondorTestStrategy, "
             "IvMeanRevertStrategy, StraddleInventoryScalperStrategy."
    )

    # Backtest parameters (must match what the production pipeline sends)
    p.add_argument("--fee-rate", type=float, default=0.35, metavar="N",
                   help="Fee rate per contract (default 0.35).")
    p.add_argument("--slippage-bps", type=float, default=5.0, metavar="N",
                   help="Slippage in basis points (default 5.0).")
    p.add_argument("--risk-free-rate", type=float, default=0.05, metavar="N",
                   help="Risk-free rate (default 0.05).")
    p.add_argument("--iv-price-mode", default="mid", choices=["mid", "bid", "ask"],
                   help="IV price mode (default: mid).")
    p.add_argument("--setting", metavar="KEY=VAL", action="append", default=[],
                   help="Extra strategy settings as key=value pairs.")

    # Test options
    p.add_argument("--runs", type=int, default=2, metavar="N",
                   help="Number of identical runs to compare (default 2, min 2).")
    p.add_argument("--timeout", type=int, default=300, metavar="SEC",
                   help="Per-run timeout in seconds (default 300).")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Print per-field JSON diff on mismatch.")

    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.runs < 2:
        print("Error: --runs must be >= 2.", file=sys.stderr)
        return 2

    # Extra strategy settings
    extra_settings: dict[str, float] = {}
    for kv in args.setting:
        if "=" not in kv:
            print(f"Error: --setting must be KEY=VALUE, got: {kv!r}", file=sys.stderr)
            return 2
        k, _, v = kv.partition("=")
        try:
            extra_settings[k] = float(v)
        except ValueError:
            print(f"Error: --setting value must be numeric, got: {v!r}", file=sys.stderr)
            return 2

    # Resolve input
    try:
        if args.auto:
            parquet_path, strategy = auto_find_test_file()
            parquet_args = [parquet_path]
            strategy_name = strategy
            print(f"[auto] Using: {parquet_path}  strategy={strategy_name}")
        else:
            parquet_args = resolve_parquet_args(args)
            strategy_name = args.strategy
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    # Run the test
    success = run_checksum_test(
        parquet_args=parquet_args,
        strategy=strategy_name,
        fee_rate=args.fee_rate,
        slippage_bps=args.slippage_bps,
        risk_free_rate=args.risk_free_rate,
        iv_price_mode=args.iv_price_mode,
        extra_settings=extra_settings,
        num_runs=args.runs,
        timeout=args.timeout,
        verbose=args.verbose,
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
