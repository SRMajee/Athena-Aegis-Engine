import asyncio
import sys
from pathlib import Path
import json

sys.path.append(str(Path(__file__).resolve().parent.parent))

import grpc.aio
from src.proto import otrader_engine_pb2 as pb2
from src.proto import otrader_engine_pb2_grpc as pb2_grpc

async def main():
    grpc_target = "127.0.0.1:50051"
    print(f"Connecting to {grpc_target}...")
    
    # Let's enque/start the backtest stream directly
    async with grpc.aio.insecure_channel(grpc_target) as channel:
        stub = pb2_grpc.EngineServiceStub(channel)
        
        strat_cfg = pb2.StrategyConfig(
            parquet_path="c:\\Users\\User\\Desktop\\Affinity-Core\\data\\SPY\\20100104.parquet",
            strategy_name="StraddleTestStrategy",
            fee_rate=0.35,
            slippage_bps=5.0,
            risk_free_rate=0.05,
            iv_price_mode="mid",
            strategy_setting="{}",
            start_date="2010-01-04",
            end_date="2010-01-08"
        )
        stream_req = pb2.StreamRequest(
            job_id="test-job-id-1234",
            correlation_id="test-corr-id-1234",
            model_ids=[],
            strategy=strat_cfg
        )
        
        print("Sending StartBacktest request...")
        try:
            stream = stub.StartBacktest(stream_req)
            print("Stream started, waiting for updates...")
            count = 0
            async for update in stream:
                count += 1
                if count % 100 == 1 or count < 10:
                    print(f"Update {count}: spot={update.spot_price}, iv={update.implied_vol}, pnl={update.cumulative_pnl}")
            print(f"Stream finished successfully. Received {count} updates.")
        except Exception as e:
            print(f"Stream encountered error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
