import os
import sys
import time
import json
import asyncio
import subprocess
from pathlib import Path
# pyrefly: ignore [missing-import]
import httpx
# pyrefly: ignore [missing-import]
import websockets

# Add current directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

PROCESSES = []

async def run_command_async(cmd, name):
    print(f"Starting {name}...")
    log_path = f"{name.lower().replace(' ', '_')}.log"
    log_file = open(log_path, "w")
    p = subprocess.Popen(
        cmd,
        shell=True,
        stdout=log_file,
        stderr=log_file,
        text=True,
        bufsize=1
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

async def main():
    print("=== STARTING INTEGRATION VALIDATION ===")
    
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

    # 3. Start Mock gRPC Server, ARQ Worker, and FastAPI app
    grpc_server = await run_command_async(f'"{sys.executable}" -u mock_grpc_server.py', "Mock gRPC Server")
    arq_worker = await run_command_async(f'"{sys.executable}" -u -m arq src.infra.task_queue.WorkerSettings', "ARQ Worker")
    fastapi_app = await run_command_async(f'"{sys.executable}" -u -m uvicorn server_fastapi:app --host 0.0.0.0 --port 8080', "FastAPI Server")

    print("Waiting 7 seconds for services to boot and bind...")
    await asyncio.sleep(7)

    # Verify processes are running
    for p, name, _ in PROCESSES:
        if p.poll() is not None:
            print(f"ERROR: {name} failed to start or crashed on boot! Exit code: {p.returncode}")
            cleanup()
            sys.exit(1)
    
    print("All services running successfully. Starting verification tests...")

    try:
        async with httpx.AsyncClient() as client:
            # ==========================================
            # TEST 1: Submit a Backtest Replay Job
            # ==========================================
            print("\n[TEST 1] Submitting backtest job...")
            payload = {
                "parquet": "AAPL",
                "strategy": "OptionHedgeStrategy",
                "fee_rate": 0.35,
                "slippage_bps": 5.0,
                "risk_free_rate": 0.05,
                "iv_price_mode": "mid",
                "strategy_setting": {},
                "start_date": "2026-06-01",
                "end_date": "2026-06-05"
            }
            resp = await client.post("http://localhost:8080/api/run_backtest", json=payload, timeout=10.0)
            if resp.status_code != 202:
                raise Exception(f"Failed to submit backtest job. Status code: {resp.status_code}, Response: {resp.text}")
            
            job_data = resp.json()
            job_id = job_data.get("job_id")
            print(f"Job submitted successfully. Job ID: {job_id}")

            # ==========================================
            # TEST 2: Listen to the Real-Time Broadcast
            # ==========================================
            print(f"\n[TEST 2] Connecting to WebSocket for job {job_id}...")
            ws_url = f"ws://localhost:8080/ws/stream?jobId={job_id}"
            
            updates_received = 0
            final_summary_received = False
            
            async with websockets.connect(ws_url) as websocket:
                print("Connected to WebSocket stream.")
                # We expect to receive mock ticks followed by a final completion summary
                while True:
                    try:
                        msg_raw = await asyncio.wait_for(websocket.recv(), timeout=15.0)
                        msg = json.loads(msg_raw)
                        
                        status = msg.get("status")
                        if status == "ok" and "result" in msg:
                            print("\nFinal completion summary received!")
                            print(f"Summary metrics: {json.dumps(msg.get('result'), indent=2)}")
                            print(f"Chart SVG preview (first 50 chars): {msg.get('chart_svg')[:50]}...")
                            final_summary_received = True
                            break
                        elif status == "error":
                            print(f"Received error from stream: {msg.get('error')}")
                            break
                        else:
                            updates_received += 1
                            if updates_received % 20 == 0:
                                print(f"Received {updates_received} tick updates... Latest spot: {msg.get('spot')}, PnL: {msg.get('pnl')}")
                    except asyncio.TimeoutError:
                        print("Timeout waiting for WebSocket message.")
                        break

            if updates_received > 0 and final_summary_received:
                print("TEST 2 PASSED: Successfully streamed ticks and completed job.")
            else:
                raise Exception("TEST 2 FAILED: Stream ended without receiving expected ticks or final summary.")

            # ==========================================
            # TEST 3: Verify Job Cancellation
            # ==========================================
            print("\n[TEST 3] Submitting a new job for cancellation test...")
            resp = await client.post("http://localhost:8080/api/run_backtest", json=payload, timeout=10.0)
            if resp.status_code != 202:
                raise Exception(f"Failed to submit second backtest job. Status code: {resp.status_code}")
            
            cancel_job_id = resp.json().get("job_id")
            print(f"Second Job ID: {cancel_job_id}")

            cancel_ws_url = f"ws://localhost:8080/ws/stream?jobId={cancel_job_id}"
            print("Connecting to second job's WebSocket...")
            
            async with websockets.connect(cancel_ws_url) as cancel_ws:
                # Wait for first update
                first_msg = await cancel_ws.recv()
                print("Received first update from second job. Initiating cancellation request...")
                
                # Send cancel request
                cancel_payload = {"job_id": cancel_job_id}
                cancel_resp = await client.post("http://localhost:8080/api/backtest/cancel", json=cancel_payload, timeout=10.0)
                if cancel_resp.status_code != 200:
                    raise Exception(f"Failed to submit cancel request. Status code: {cancel_resp.status_code}, Response: {cancel_resp.text}")
                
                print(f"Cancel request status: {cancel_resp.json()}")

                # Wait for cancellation event on WebSocket
                cancelled_event_received = False
                while True:
                    try:
                        msg_raw = await asyncio.wait_for(cancel_ws.recv(), timeout=5.0)
                        msg = json.loads(msg_raw)
                        if msg.get("status") == "cancelled":
                            print("Received cancelled event on WebSocket successfully!")
                            cancelled_event_received = True
                            break
                    except asyncio.TimeoutError:
                        print("Timeout waiting for cancel confirmation.")
                        break

            if cancelled_event_received:
                print("TEST 3 PASSED: Successfully cancelled a running backtest job.")
            else:
                raise Exception("TEST 3 FAILED: Job was not cancelled successfully via WebSocket.")

        print("\n=== ALL VERIFICATION TESTS PASSED SUCCESSFULLY! ===")

    except Exception as e:
        print(f"\n!!! TEST VERIFICATION EXCEPTION: {e} !!!")
        cleanup()
        sys.exit(1)

    cleanup()
    print("=== VALIDATION RUN COMPLETE ===")

if __name__ == "__main__":
    asyncio.run(main())
