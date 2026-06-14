import os
import sys
import time
import json
import asyncio
import subprocess
from pathlib import Path
import httpx

# Add current directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

PROCESSES = []

async def run_command_async(cmd, name, cwd=None):
    print(f"Starting {name}...")
    log_path = f"{name.lower().replace(' ', '_')}.log"
    log_file = open(log_path, "w")
    p = subprocess.Popen(
        cmd,
        shell=True,
        stdout=log_file,
        stderr=log_file,
        text=True,
        bufsize=1,
        cwd=cwd
    )
    PROCESSES.append((p, name, log_file))
    return p

def cleanup():
    print("\n--- Cleaning up background processes ---")
    for p, name, log_file in PROCESSES:
        if p.poll() is None:
            print(f"Terminating {name}...")
            p.terminate()
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                print(f"Killing {name}...")
                p.kill()
        else:
            print(f"{name} had already exited with code {p.returncode}")
        try:
            log_file.close()
        except Exception:
            pass

async def ensure_playwright_installed():
    print("Checking for Playwright dependency...")
    try:
        import playwright
    except ImportError:
        print("Playwright not found. Installing 'playwright' package...")
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
        print("Installing chromium browser for Playwright...")
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)

def create_mock_data():
    print("Creating mock parquet data for backtesting...")
    # Create data/AAPL directory under the script's directory (FastAPI server CWD)
    root = Path(__file__).resolve().parent
    data_dir = root / "data" / "AAPL"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    pq_path = data_dir / "20260601.parquet"
    if not pq_path.exists():
        try:
            import pandas as pd
            import numpy as np
            # Create a dummy DataFrame with ts_recv and some data
            dates = pd.date_range(start='2026-06-01', end='2026-06-05', freq='h')
            df = pd.DataFrame({
                'ts_recv': dates,
                'spot': np.random.uniform(100, 105, len(dates))
            })
            df.to_parquet(str(pq_path))
            print(f"Created mock parquet file at: {pq_path}")
        except Exception as e:
            print(f"Failed to create mock parquet: {e}")
            # Fallback: create an empty file just so it's listed
            pq_path.touch()

async def check_backend_api():
    print("\nChecking backend API directly via HTTP...")
    async with httpx.AsyncClient() as client:
        try:
            res_files = await client.get("http://localhost:8080/api/files")
            print(f"GET /api/files response (status {res_files.status_code}):")
            print(json.dumps(res_files.json(), indent=2))
        except Exception as e:
            print(f"Failed to query /api/files: {e}")

        try:
            res_strats = await client.get("http://localhost:8080/api/backtest/strategies")
            print(f"GET /api/backtest/strategies response (status {res_strats.status_code}):")
            print(json.dumps(res_strats.json(), indent=2))
        except Exception as e:
            print(f"Failed to query /api/backtest/strategies: {e}")
    print()

async def main():
    print("=== STARTING FRONTEND & BACKEND INTEGRATION VALIDATION ===")
    
    # 0. Ensure Playwright and mock data exist
    await ensure_playwright_installed()
    create_mock_data()
    
    from playwright.async_api import async_playwright

    # 1. Start Docker containers
    print("Ensuring Postgres and Redis are running in Docker...")
    try:
        subprocess.run("docker compose up -d", shell=True, check=True, cwd="..")
        print("Docker containers started successfully.")
    except Exception as e:
        print(f"Error starting Docker containers: {e}")
        sys.exit(1)

    # 2. Run Database Schema Creation
    print("Running DB migrations/schema creation...")
    try:
        subprocess.run(f'"{sys.executable}" db_init.py', shell=True, check=True)
        print("Database tables initialized.")
    except Exception as e:
        print(f"Error initializing database tables: {e}")
        sys.exit(1)

    # 3. Start Mock gRPC Server, ARQ Worker, FastAPI app, and Next.js Dev Server
    grpc_server = await run_command_async(f'"{sys.executable}" -u mock_grpc_server.py', "Mock gRPC Server")
    arq_worker = await run_command_async(f'"{sys.executable}" -u -m arq src.infra.task_queue.WorkerSettings', "ARQ Worker")
    fastapi_app = await run_command_async(f'"{sys.executable}" -u -m uvicorn server_fastapi:app --host 0.0.0.0 --port 8080', "FastAPI Server")
    
    # Start Next.js frontend in development mode
    nextjs_cwd = Path(__file__).resolve().parent.parent / "frontend_terminal"
    nextjs_app = await run_command_async("npm run dev", "Next.js Frontend", cwd=str(nextjs_cwd))

    print("Waiting 12 seconds for all services to boot and bind...")
    await asyncio.sleep(12)

    # Verify processes are running
    for p, name, _ in PROCESSES:
        if p.poll() is not None:
            print(f"ERROR: {name} failed to start or crashed on boot! Exit code: {p.returncode}")
            cleanup()
            sys.exit(1)
    
    print("All backend and frontend services running successfully.")
    
    # Check backend API output directly
    await check_backend_api()
    
    print("Starting browser automation test...")

    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Register browser logging handlers for diagnostic clarity
            page.on("console", lambda msg: print(f"BROWSER CONSOLE: [{msg.type}] {msg.text}"))
            page.on("pageerror", lambda err: print(f"BROWSER RUNTIME ERROR: {err}"))
            
            print("Navigating to OTrader Backtest Page...")
            await page.goto("http://localhost:3000/backtest", timeout=30000)
            
            # Wait for Radix Select components and buttons to render and resolve loading state
            print("Waiting for page inputs and dropdowns to resolve...")
            
            try:
                # Wait until "Loading symbols..." is gone (placeholder change or select trigger enabling)
                await page.wait_for_selector("button#btn-start-backtest:not([disabled])", state="visible", timeout=25000)
            except Exception as select_err:
                print(f"Failed waiting for start button to be enabled: {select_err}")
                await page.screenshot(path="frontend_bt_failed.png")
                print("Captured screenshot of failure state (frontend_bt_failed.png)")
                raise select_err
            
            # Take an initial screenshot showing symbol selected
            await page.screenshot(path="frontend_bt_idle.png")
            print("Captured screenshot of Idle state (frontend_bt_idle.png)")

            # Click the Start Backtest button
            print("Clicking 'Start Backtest' button...")
            await page.click("button#btn-start-backtest")
            
            # Wait for status to show Completed
            print("Waiting for backtest stream execution to complete...")
            await page.wait_for_selector("#bt-completed-banner", state="visible", timeout=30000)
            
            # Take a completion screenshot
            await page.screenshot(path="frontend_bt_completed.png")
            print("Captured screenshot of Completed state (frontend_bt_completed.png)")
            
            await browser.close()
            
        print("\n=== AUTOMATED FRONTEND & BACKEND INTEGRATION TEST PASSED SUCCESSFULLY! ===")

    except Exception as e:
        print(f"\n!!! TEST VERIFICATION EXCEPTION: {e} !!!")
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        cleanup()
        sys.exit(1)

    cleanup()
    print("=== VALIDATION RUN COMPLETE ===")

if __name__ == "__main__":
    asyncio.run(main())
