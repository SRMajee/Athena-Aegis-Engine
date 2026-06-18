import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import grpc.aio
from src.proto import otrader_engine_pb2 as pb2
from src.proto import otrader_engine_pb2_grpc as pb2_grpc

async def main():
    grpc_target = "127.0.0.1:50051"
    print(f"Connecting to {grpc_target}...")
    
    async with grpc.aio.insecure_channel(grpc_target) as channel:
        stub = pb2_grpc.EngineServiceStub(channel)
        
        strat_cfg = pb2.StrategyConfig(
            parquet_path="c:\\Users\\User\\Desktop\\Affinity-Core\\data\\SPY\\2010\\01\\2010-01-04.parquet",
            strategy_name="StraddleTestStrategy",
            fee_rate=0.35,
            slippage_bps=5.0,
            risk_free_rate=0.05,
            iv_price_mode="mid",
            strategy_setting="{}",
            start_date="2010-01-04",
            end_date="2010-01-04"
        )
        stream_req = pb2.StreamRequest(
            job_id="test-job-models",
            correlation_id="test-corr-models",
            model_ids=["deep_hedge_ffnn", "deep_hedge_lstm", "deep_hedge_adversarial"],
            strategy=strat_cfg
        )
        
        print("Sending StartBacktest request with models...")
        try:
            stream = stub.StartBacktest(stream_req)
            count = 0
            async for update in stream:
                count += 1
                if len(update.model_results) > 0 or count < 5:
                    print(f"Update {count}: spot={update.spot_price}, models_count={len(update.model_results)}")
                    for mr in update.model_results:
                        print(f"  -> Model: {mr.model_id} | Ratio: {mr.hedge_ratio:.4f} | PnL: {mr.pnl:.4f} | Latency: {mr.inference_latency_ns} ns")
            print(f"Finished. Total updates: {count}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
