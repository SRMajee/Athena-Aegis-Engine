import asyncio
import grpc
import time
import random
import sys
import json
from datetime import datetime
from pathlib import Path

# Add backend_orchestrator to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dotenv
dotenv.load_dotenv()
from src.infra.db import get_connection

from src.proto import otrader_engine_pb2 as pb2
from src.proto import otrader_engine_pb2_grpc as pb2_grpc

class MockEngineService(pb2_grpc.EngineServiceServicer):
    def __init__(self):
        self.ibkr_connected = False
        self.market_data_active = False
        self.log_queues = []
        # Initialize some mock strategies in memory
        self.strategies = {
            "BS_Hedge_ETH_01": {
                "strategy_name": "BS_Hedge_ETH_01",
                "class_name": "BlackScholesDeltaHedge",
                "portfolio": "ETHUSD-OPT",
                "status": "running"
            },
            "ML_LSTM_BTC_Hedge": {
                "strategy_name": "ML_LSTM_BTC_Hedge",
                "class_name": "LSTMAgentHedge",
                "portfolio": "BTCUSD-OPT",
                "status": "stopped"
            }
        }
        self.log("Engine Service started on port 50051.")

    def log(self, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        formatted_log = f"{timestamp} | {message}"
        print(f"Mock Engine Log: {formatted_log}")
        for q in list(self.log_queues):
            try:
                q.put_nowait(formatted_log)
            except Exception:
                pass

    async def GetStatus(self, request, context):
        ib_status = "on" if self.ibkr_connected else "off"
        md_status = "on" if self.market_data_active else "off"
        detail = f"engine: running; ib: {ib_status}; md: {md_status}"
        return pb2.EngineStatus(
            running=True,
            connected=self.ibkr_connected,
            detail=detail
        )

    async def ConnectGateway(self, request, context):
        print("Mock gRPC: ConnectGateway called")
        self.ibkr_connected = True
        self.log("IBKR gateway connected (no market data auto-start).")
        return pb2.Empty()

    async def DisconnectGateway(self, request, context):
        print("Mock gRPC: DisconnectGateway called")
        self.ibkr_connected = False
        self.market_data_active = False
        self.log("IBKR gateway disconnected.")
        return pb2.Empty()

    async def StartMarketData(self, request, context):
        print("Mock gRPC: StartMarketData called")
        self.market_data_active = True
        self.log("Market data stream started.")
        return pb2.Empty()

    async def StopMarketData(self, request, context):
        print("Mock gRPC: StopMarketData called")
        self.market_data_active = False
        self.log("Market data stream stopped.")
        return pb2.Empty()

    async def StreamLogs(self, request, context):
        print("Mock gRPC: StreamLogs called")
        q = asyncio.Queue()
        self.log_queues.append(q)
        yield pb2.LogLine(line="[Mock Engine] System initialized.")
        yield pb2.LogLine(line="[Mock Engine] Ready for connection.")
        try:
            while True:
                if context.cancelled():
                    break
                try:
                    log_line = await asyncio.wait_for(q.get(), timeout=1.0)
                    yield pb2.LogLine(line=log_line)
                except asyncio.TimeoutError:
                    continue
        finally:
            if q in self.log_queues:
                self.log_queues.remove(q)

    async def StreamStrategyUpdates(self, request, context):
        print("Mock gRPC: StreamStrategyUpdates called")
        while True:
            if context.cancelled():
                break
            await asyncio.sleep(1.0)

    async def SendCommand(self, request_iterator, context):
        print("Mock gRPC: SendCommand called")
        async for req in request_iterator:
            print(f"Mock gRPC: Received command {req.action} ({req.command_id})")
        return pb2.CommandAck(command_id="ack", success=True)

    async def RestoreStrategy(self, request, context):
        print(f"Mock gRPC: RestoreStrategy called for {request.strategy_name}")
        return pb2.Empty()

    async def ListStrategies(self, request, context):
        print("Mock gRPC: ListStrategies called")
        for s in self.strategies.values():
            yield pb2.StrategySummary(
                strategy_name=s["strategy_name"],
                class_name=s["class_name"],
                portfolio=s["portfolio"],
                status=s["status"]
            )

    async def ListStrategyClasses(self, request, context):
        print("Mock gRPC: ListStrategyClasses called")
        return pb2.ListStrategyClassesResponse(
            classes=["BlackScholesDeltaHedge", "LSTMAgentHedge", "FFNNAgentHedge"]
        )

    async def GetPortfoliosMeta(self, request, context):
        print("Mock gRPC: GetPortfoliosMeta called")
        return pb2.ListPortfoliosResponse(
            portfolios=["ETHUSD-OPT", "BTCUSD-OPT"]
        )

    async def GetRemovedStrategies(self, request, context):
        print("Mock gRPC: GetRemovedStrategies called")
        return pb2.GetRemovedStrategiesResponse(removed_strategies=[])

    async def AddStrategy(self, request, context):
        print(f"Mock gRPC: AddStrategy called - class={request.strategy_class}, portfolio={request.portfolio_name}")
        # Generate name like BS_Hedge_ETH_02
        strat_name = f"BS_Hedge_Custom_{random.randint(10, 99)}"
        self.strategies[strat_name] = {
            "strategy_name": strat_name,
            "class_name": request.strategy_class,
            "portfolio": request.portfolio_name,
            "status": "stopped"
        }
        return pb2.AddStrategyResponse(strategy_name=strat_name)

    async def InitStrategy(self, request, context):
        print(f"Mock gRPC: InitStrategy called - name={request.strategy_name}")
        if request.strategy_name in self.strategies:
            self.strategies[request.strategy_name]["status"] = "initialized"
        return pb2.Empty()

    async def StartStrategy(self, request, context):
        print(f"Mock gRPC: StartStrategy called - name={request.strategy_name}")
        if request.strategy_name in self.strategies:
            self.strategies[request.strategy_name]["status"] = "running"
        return pb2.Empty()

    async def StopStrategy(self, request, context):
        print(f"Mock gRPC: StopStrategy called - name={request.strategy_name}")
        if request.strategy_name in self.strategies:
            self.strategies[request.strategy_name]["status"] = "stopped"
        return pb2.Empty()

    async def RemoveStrategy(self, request, context):
        print(f"Mock gRPC: RemoveStrategy called - name={request.strategy_name}")
        self.strategies.pop(request.strategy_name, None)
        return pb2.RemoveStrategyResponse(removed=True)

    async def DeleteStrategy(self, request, context):
        print(f"Mock gRPC: DeleteStrategy called - name={request.strategy_name}")
        self.strategies.pop(request.strategy_name, None)
        return pb2.DeleteStrategyResponse(deleted=True)

    async def GetStrategyClassDefaults(self, request, context):
        print(f"Mock gRPC: GetStrategyClassDefaults called - class={request.strategy_class}")
        return pb2.GetStrategyClassDefaultsResponse(settings={
            "strike": 3000.0,
            "vol": 0.50,
            "cvar_limit": 0.95
        })

    async def GetStrategyHoldings(self, request, context):
        print("Mock gRPC: GetStrategyHoldings called")
        return pb2.StrategyHoldingsResponse(holdings={})

    async def GetOrdersAndTrades(self, request, context):
        print("Mock gRPC: GetOrdersAndTrades called")
        return pb2.OrdersAndTradesResponse(orders=[], trades=[])

    async def ListPortfolios(self, request, context):
        print("Mock gRPC: ListPortfolios called")
        return pb2.ListPortfoliosResponse(portfolios=["ETHUSD-OPT", "BTCUSD-OPT"])

    async def StartBacktest(self, request, context):
        print(f"Mock gRPC server starting backtest stream for job: {request.job_id}")
        cum_pnl = 0.0
        strategy_name = request.strategy.strategy_name

        # Clear trades for this strategy in PostgreSQL trades table
        conn = None
        try:
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute("DELETE FROM trades WHERE strategy_name = %s", (strategy_name,))
            conn.commit()
        except Exception as e:
            print(f"Mock gRPC database error during trade delete: {e}")
        finally:
            if conn:
                conn.close()

        # Parse date range or default to 2010
        start_date_str = request.strategy.start_date
        end_date_str = request.strategy.end_date
        
        try:
            from datetime import timezone
            start_dt = datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            from datetime import timezone
            start_dt = datetime(2010, 1, 4, tzinfo=timezone.utc)
            
        try:
            from datetime import timezone
            end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            from datetime import timezone
            end_dt = datetime(2010, 12, 31, tzinfo=timezone.utc)
            
        if end_dt < start_dt:
            end_dt = start_dt

        start_ts = start_dt.timestamp()
        end_ts = end_dt.timestamp()
        total_seconds = end_ts - start_ts

        # Scale mock trades based on date range duration
        num_days = max(1, (end_dt - start_dt).days)
        # Generate between 1 and 2 trades per day, capped at 90 total trades
        num_trades = max(2, min(90, int(num_days * random.uniform(1.2, 1.8))))
        # Pick unique random indices for trades
        trade_indices = set(random.sample(range(1, 99), num_trades))

        # Stream 100 mock ticks
        for i in range(100):
            # Check for client cancellation
            if context.cancelled():
                print("Mock gRPC backtest stream cancelled by client.")
                break
                
            # Random walk calculations
            spot = 100.0 + random.normalvariate(0, 1.0)
            iv = 0.2 + random.normalvariate(0, 0.01)
            delta = random.normalvariate(0.5, 0.1)
            gamma = random.normalvariate(0.05, 0.01)
            theta = random.normalvariate(-0.02, 0.005)
            cvar_95 = random.uniform(5.0, 10.0)
            cvar_99 = random.uniform(10.0, 15.0)
            pnl_tick = random.normalvariate(10, 50)
            cum_pnl += pnl_tick
            
            # Interpolated timestamp
            ts = start_ts + (i / 99) * total_seconds
            ts_ns = int(ts * 1e9)

            # Insert simulated trade on selected tick indices
            if i in trade_indices:
                trade_id = f"mock_trade_{request.job_id}_{i}"
                trade_dt = datetime.utcfromtimestamp(ts)
                trade_ts_str = trade_dt.isoformat() + "Z"
                
                conn = None
                try:
                    conn = get_connection()
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO trades (timestamp, strategy_name, tradeid, symbol, direction, price, volume)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """,
                            (trade_ts_str, strategy_name, trade_id, "SPY", "BUY" if i % 2 == 0 else "SELL", spot, 10.0)
                        )
                    conn.commit()
                except Exception as e:
                    print(f"Mock gRPC database error during trade insert: {e}")
                finally:
                    if conn:
                        conn.close()
            
            greeks = pb2.GreeksPayload(
                delta=delta,
                gamma=gamma,
                vega=0.1,
                theta=theta,
                rho=0.01
            )
            cvar = pb2.CVaRPayload(
                cvar_95=cvar_95,
                cvar_99=cvar_99
            )
            model_res = pb2.ModelResult(
                model_id="baseline",
                hedge_ratio=0.5,
                pnl=pnl_tick,
                cumulative_pnl=cum_pnl,
                inference_latency_ns=120000
            )
            
            update = pb2.EngineStateUpdate(
                job_id=request.job_id,
                tick_timestamp_ns=ts_ns,
                spot_price=spot,
                implied_vol=iv,
                greeks=greeks,
                cvar=cvar,
                pnl=pnl_tick,
                cumulative_pnl=cum_pnl,
                model_results=[model_res]
            )
            
            yield update
            await asyncio.sleep(0.05)  # 50ms delay per tick (total backtest takes ~5 seconds)
            
        print("Mock gRPC backtest stream finished.")

async def serve():
    server = grpc.aio.server()
    pb2_grpc.add_EngineServiceServicer_to_server(MockEngineService(), server)
    server.add_insecure_port("0.0.0.0:50051")
    print("Starting mock C++ gRPC engine server on port 50051...")
    await server.start()
    await server.wait_for_termination()

if __name__ == "__main__":
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        print("Mock gRPC server stopped.")
