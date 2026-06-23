import asyncio
import sys
import uuid
from pathlib import Path

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
    print(f"Error importing grpc/stubs: {e}")
    sys.exit(1)

async def test_v2_backtest():
    target = "127.0.0.1:50051"
    job_id = str(uuid.uuid4())
    
    # We will request our new V2 models!
    model_ids = ["deep_hedge_ffnn_v2", "deep_hedge_lstm_v2", "deep_hedge_adversarial_v2"]
    
    strat_cfg = pb2.StrategyConfig(
        parquet_path=str(WORKSPACE_ROOT / "data/SPY/2010/01/2010-01-04.parquet"),
        strategy_name="StraddleTestStrategy",
        fee_rate=0.35,
        slippage_bps=5.0,
        risk_free_rate=0.05,
        iv_price_mode="mid",
        strategy_setting="{}",
    )
    
    stream_req = pb2.StreamRequest(
        job_id=job_id,
        correlation_id=f"verify-v2-models",
        model_ids=model_ids,
        strategy=strat_cfg,
    )
    
    print(f"Connecting to C++ gRPC engine at {target}...")
    print(f"Requesting backtest with V2 models: {model_ids}")
    
    try:
        async with grpc.aio.insecure_channel(target) as channel:
            stub = pb2_grpc.EngineServiceStub(channel)
            stream = stub.StartBacktest(stream_req, timeout=30.0)
            
            count = 0
            async for update in stream:
                count += 1
                if count <= 5:
                    print(f"Update {count}: spot={update.spot_price:.2f}, IV={update.implied_vol:.4f}")
                    for mr in update.model_results:
                        print(f"  -> Model: {mr.model_id} | Ratio: {mr.hedge_ratio:.4f} | PnL: {mr.pnl:.4f} | Latency: {mr.inference_latency_ns} ns")
            
            print(f"Backtest stream finished. Received {count} updates.")
            if count > 0:
                print("SUCCESS: V2 models evaluated successfully in C++ engine!")
                return True
            else:
                print("FAILURE: No updates received.")
                return False
    except Exception as e:
        print(f"Error during backtest run: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_v2_backtest())
    sys.exit(0 if success else 1)
