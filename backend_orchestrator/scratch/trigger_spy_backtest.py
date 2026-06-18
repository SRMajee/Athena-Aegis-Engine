import asyncio
import json
import httpx
import websockets

async def main():
    print("=== TRIGGERING BACKTEST ON SPY VIA API ===")
    
    # 1. Start backtest via POST request
    url = "http://localhost:8085/api/run_backtest"
    payload = {
        "parquet": "SPY",
        "strategy": "IronCondorTestStrategy", # or whatever strategy class is available
        "fee_rate": 0.35,
        "slippage_bps": 5.0,
        "risk_free_rate": 0.05,
        "iv_price_mode": "mid",
        "strategy_setting": {},
        "start_date": "2010-01-04",
        "end_date": "2010-01-29",
        "model_ids": ["deep_hedge_ffnn", "deep_hedge_lstm", "deep_hedge_adversarial"]
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, timeout=10.0)
            if resp.status_code not in (200, 202):
                print(f"Failed to trigger backtest. Code: {resp.status_code}, Response: {resp.text}")
                return
            
            data = resp.json()
            job_id = data.get("job_id")
            print(f"Backtest triggered. Job ID: {job_id}")
        except Exception as e:
            print(f"Request failed: {e}")
            return
            
    # 2. Connect to WebSocket stream to monitor progress
    ws_url = f"ws://localhost:8085/ws/stream?jobId={job_id}"
    print(f"Connecting to websocket: {ws_url}")
    
    ticks_count = 0
    async with websockets.connect(ws_url) as websocket:
        while True:
            try:
                msg_raw = await asyncio.wait_for(websocket.recv(), timeout=20.0)
                msg = json.loads(msg_raw)
                
                status = msg.get("status")
                if status == "ok" and "result" in msg:
                    print("\n[SUCCESS] Backtest completed successfully!")
                    print(f"Result summary: {json.dumps(msg.get('result'), indent=2)}")
                    break
                elif status == "error":
                    print(f"\n[ERROR] Backtest failed with error: {msg.get('error')}")
                    break
                elif status == "cancelled":
                    print("\n[CANCELLED] Backtest job cancelled.")
                    break
                else:
                    ticks_count += 1
                    print(f"Stream update: {msg}")
            except asyncio.TimeoutError:
                print("Timeout waiting for WebSocket update.")
                break
            except Exception as e:
                print(f"Connection error: {e}")
                break

if __name__ == "__main__":
    asyncio.run(main())
