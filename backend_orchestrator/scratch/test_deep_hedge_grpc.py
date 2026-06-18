import asyncio
import json
import httpx
import websockets

async def main():
    url = "http://localhost:8085/api/run_backtest"
    payload = {
        "parquet": "AAPL",
        "strategy": "StraddleTestStrategy",
        "fee_rate": 0.35,
        "slippage_bps": 5.0,
        "risk_free_rate": 0.05,
        "iv_price_mode": "mid",
        "strategy_setting": {},
        "start_date": "2026-06-01",
        "end_date": "2026-06-01",
        "model_ids": ["deep_hedge_ffnn", "deep_hedge_lstm", "deep_hedge_adversarial"]
    }
    
    print("Submitting backtest job with deep hedging models...")
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, timeout=15.0)
        if resp.status_code != 202:
            print(f"Error submitting backtest: {resp.status_code} - {resp.text}")
            return
        
        job_data = resp.json()
        job_id = job_data.get("job_id")
        print(f"Job submitted successfully. Job ID: {job_id}")
        
    ws_url = f"ws://localhost:8085/ws/stream?jobId={job_id}"
    print(f"Connecting to WebSocket stream at {ws_url}...")
    
    updates_count = 0
    async with websockets.connect(ws_url) as ws:
        while True:
            try:
                msg_raw = await asyncio.wait_for(ws.recv(), timeout=20.0)
                msg = json.loads(msg_raw)
                
                status = msg.get("status")
                if status == "ok" and "result" in msg:
                    print("\n=== Backtest Completed ===")
                    print(json.dumps(msg.get("result"), indent=2))
                    break
                elif status == "error":
                    print(f"Error from stream: {msg.get('error')}")
                    break
                else:
                    updates_count += 1
                    model_results = msg.get("model_results", [])
                    if updates_count % 10 == 0 or len(model_results) > 0:
                        print(f"Tick update #{updates_count} - Spot: {msg.get('spot')}, Baseline Delta: {msg.get('delta')}")
                        for mr in model_results:
                            print(f"  -> Model: {mr.get('model_id')} | Hedge Ratio: {mr.get('hedge_ratio'):.4f} | PnL: {mr.get('pnl'):.4f}")
            except asyncio.TimeoutError:
                print("Timeout waiting for WebSocket message.")
                break
            except Exception as e:
                print(f"WebSocket error: {e}")
                break

if __name__ == "__main__":
    asyncio.run(main())
