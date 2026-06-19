from __future__ import annotations

import os
import json
import asyncio
from datetime import datetime
from uuid import UUID
import numpy as np
import sqlalchemy as sa

import grpc.aio
from google.protobuf.json_format import MessageToDict
from arq.connections import RedisSettings

from src.infra.db import async_session_maker, BacktestJob, RiskSnapshot
from src.proto import otrader_engine_pb2 as pb2
from src.proto import otrader_engine_pb2_grpc as pb2_grpc
from src.utils.chart import render_backtest_chart_svg, render_backtest_chart_base64

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))


def resolve_parquet_path(parquet_input: str, start_date: str = "", end_date: str = "", job_id: str = "") -> tuple[str, bool]:
    """
    Resolves the symbol or file path to a single parquet file path.
    If multiple files exist in the date range, they are concatenated into a temporary combined file.
    Returns (resolved_absolute_path, is_temporary_file).
    """
    if os.path.isabs(parquet_input) and os.path.isfile(parquet_input):
        return parquet_input, False

    workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    
    candidate = os.path.abspath(os.path.join(workspace_root, parquet_input))
    if os.path.isfile(candidate):
        return candidate, False

    symbol = os.path.basename(parquet_input)
    dir_candidate = os.path.join(workspace_root, "data", symbol)
    if not os.path.isdir(dir_candidate):
        return candidate, False

    # Get all matching parquet files in date range recursively (supports symbol/year/date.parquet)
    files = []
    start_clean = start_date.replace("-", "") if start_date else ""
    end_clean = end_date.replace("-", "") if end_date else ""
    
    for root_dir, _, filenames in os.walk(dir_candidate):
        for f in filenames:
            if f.endswith(".parquet"):
                stem = f[:-8]  # Remove ".parquet"
                stem_clean = stem.replace("-", "")
                if len(stem_clean) == 8 and stem_clean.isdigit():
                    if start_clean and end_clean:
                        if start_clean <= stem_clean <= end_clean:
                            files.append(os.path.join(root_dir, f))
                    else:
                        files.append(os.path.join(root_dir, f))

    if not files:
        raise FileNotFoundError(f"No parquet data files found for symbol '{symbol}' within date range {start_date} ~ {end_date}")

    if len(files) == 1:
        return os.path.abspath(files[0]), False

    # Combine multiple files
    import pandas as pd
    dfs = []
    for f in sorted(files):
        dfs.append(pd.read_parquet(f))
    combined = pd.concat(dfs, ignore_index=True)
    if "ts_recv" in combined.columns:
        combined["ts_recv"] = pd.to_datetime(combined["ts_recv"], errors="coerce")
        combined.sort_values("ts_recv", inplace=True)
        
    temp_dir = os.path.join(workspace_root, "data", "temp", symbol)
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.abspath(os.path.join(temp_dir, f"combined_{job_id}.parquet"))
    combined.to_parquet(temp_path)
    return temp_path, True



async def poll_and_insert_temp_files(job_id: str, strategy_name: str, fee_rate: float, trades_json_path: str, orders_json_path: str):
    inserted_trades = set()
    inserted_orders = {} # orderid -> status
    
    while True:
        try:
            # Poll trades
            if os.path.exists(trades_json_path):
                try:
                    with open(trades_json_path, "r") as f:
                        trades = json.load(f)
                except Exception:
                    trades = []
                
                new_trades = [t for t in trades if t.get("tradeid") not in inserted_trades]
                if new_trades:
                    async with async_session_maker() as session:
                        await session.execute(
                            sa.text("""
                                INSERT INTO trades (timestamp, strategy_name, tradeid, symbol, direction, price, volume)
                                VALUES (:timestamp, :strategy_name, :tradeid, :symbol, :direction, :price, :volume)
                            """),
                            [
                                {
                                    "timestamp": t.get("timestamp"),
                                    "strategy_name": strategy_name,
                                    "tradeid": t.get("tradeid"),
                                    "symbol": t.get("symbol"),
                                    "direction": t.get("direction"),
                                    "price": float(t.get("price", 0.0)),
                                    "volume": float(t.get("volume", 0.0))
                                }
                                for t in new_trades
                            ]
                        )
                        await session.commit()
                    for t in new_trades:
                        inserted_trades.add(t.get("tradeid"))
            
            # Poll orders
            if os.path.exists(orders_json_path):
                try:
                    with open(orders_json_path, "r") as f:
                        orders = json.load(f)
                except Exception:
                    orders = []
                
                new_or_updated_orders = []
                for o in orders:
                    oid = o.get("orderid")
                    status = o.get("status")
                    if oid not in inserted_orders or inserted_orders[oid] != status:
                        new_or_updated_orders.append(o)
                
                if new_or_updated_orders:
                    async with async_session_maker() as session:
                        for o in new_or_updated_orders:
                            oid = o.get("orderid")
                            if oid in inserted_orders:
                                await session.execute(
                                    sa.text("DELETE FROM orders WHERE orderid = :oid"),
                                    {"oid": oid}
                                )
                        await session.execute(
                            sa.text("""
                                INSERT INTO orders (timestamp, strategy_name, orderid, symbol, direction, price, volume, traded, status)
                                VALUES (:timestamp, :strategy_name, :orderid, :symbol, :direction, :price, :volume, :traded, :status)
                            """),
                            [
                                {
                                    "timestamp": o.get("timestamp"),
                                    "strategy_name": strategy_name,
                                    "orderid": o.get("orderid"),
                                    "symbol": o.get("symbol"),
                                    "direction": o.get("direction"),
                                    "price": float(o.get("price", 0.0)),
                                    "volume": float(o.get("volume", 0.0)),
                                    "traded": float(o.get("traded", 0.0)),
                                    "status": o.get("status")
                                }
                                for o in new_or_updated_orders
                            ]
                        )
                        await session.commit()
                    for o in new_or_updated_orders:
                        inserted_orders[o.get("orderid")] = o.get("status")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"Error in poll_and_insert_temp_files: {e}")
        
        await asyncio.sleep(0.5)



async def check_cancellation_loop(job_id: str, stream: Any, redis_client: Any) -> None:
    """Poll Redis for a cancel signal and cancel the gRPC stream immediately if detected."""
    while True:
        try:
            if await redis_client.exists(f"job_cancel:{job_id}"):
                await redis_client.delete(f"job_cancel:{job_id}")
                print(f"[Cancellation] Job {job_id} cancellation detected. Cancelling gRPC stream.")
                stream.cancel()
                break
        except Exception as e:
            print(f"Error in cancel check loop: {e}")
        await asyncio.sleep(0.1)


async def run_backtest_job(ctx, job_payload: dict) -> dict:
    job_id = ctx["job_id"]
    started_at = datetime.utcnow()
    temp_file_to_cleanup = None
    polling_task = None
    cancel_check_task = None
    
    workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    trades_json_path = os.path.join(workspace_root, "data", "temp", f"trades_{job_id}.json")
    orders_json_path = os.path.join(workspace_root, "data", "temp", f"orders_{job_id}.json")

    # Update job status in PostgreSQL to RUNNING and clear stale trades/orders
    async with async_session_maker() as session:
        job_record = await session.get(BacktestJob, UUID(job_id))
        if job_record:
            job_record.status = "RUNNING"
            job_record.started_at = started_at
        
        # Clear old orders and trades for this strategy to prevent stale calculations
        await session.execute(
            sa.text("DELETE FROM trades WHERE strategy_name = :name"),
            {"name": job_payload["strategy"]}
        )
        await session.execute(
            sa.text("DELETE FROM orders WHERE strategy_name = :name"),
            {"name": job_payload["strategy"]}
        )
        await session.commit()

    # Target live C++ engine gRPC server
    grpc_target = os.getenv("LIVE_GRPC_TARGET", "127.0.0.1:50051")
    
    pnl_list = []
    delta_list = []
    theta_list = []
    gamma_list = []
    ts_list = []
    snapshots = []
    daily_pnls = {}
    daily_fees = {}
    daily_trades = {}
    daily_timesteps = {}
    daily_rows = {}

    try:
        # Ensure data/temp directory exists for engine exports
        temp_dir = os.path.join(workspace_root, "data", "temp")
        os.makedirs(temp_dir, exist_ok=True)

        # Build StreamRequest and StrategyConfig
        resolved_path, is_temp = resolve_parquet_path(
            job_payload["parquet"],
            job_payload.get("start_date", ""),
            job_payload.get("end_date", ""),
            job_id
        )
        if is_temp:
            temp_file_to_cleanup = resolved_path
        strat_cfg = pb2.StrategyConfig(
            parquet_path=resolved_path,
            strategy_name=job_payload["strategy"],
            fee_rate=float(job_payload.get("fee_rate", 0.35)),
            slippage_bps=float(job_payload.get("slippage_bps", 5.0)),
            risk_free_rate=float(job_payload.get("risk_free_rate", 0.05)),
            iv_price_mode=job_payload.get("iv_price_mode", "mid"),
            strategy_setting=json.dumps(job_payload.get("strategy_setting", {})),
            start_date=job_payload.get("start_date", ""),
            end_date=job_payload.get("end_date", "")
        )
        stream_req = pb2.StreamRequest(
            job_id=job_id,
            correlation_id=job_payload.get("correlation_id", job_id),
            model_ids=job_payload.get("model_ids", []),
            strategy=strat_cfg
        )

        # Connect to C++ gRPC engine
        async with grpc.aio.insecure_channel(grpc_target) as channel:
            stub = pb2_grpc.EngineServiceStub(channel)
            metadata = [("x-correlation-id", job_payload.get("correlation_id", job_id))]
            
            stream = stub.StartBacktest(stream_req, metadata=metadata)
            
            # Start cancellation checker task
            cancel_check_task = asyncio.create_task(
                check_cancellation_loop(job_id, stream, ctx["redis"])
            )
            
            polling_task = asyncio.create_task(
                poll_and_insert_temp_files(
                    job_id=job_id,
                    strategy_name=job_payload["strategy"],
                    fee_rate=float(job_payload.get("fee_rate", 0.35)),
                    trades_json_path=trades_json_path,
                    orders_json_path=orders_json_path
                )
            )

            async for update in stream:
                # Check for cancellation
                if await ctx["redis"].exists(f"job_cancel:{job_id}"):
                    await ctx["redis"].delete(f"job_cancel:{job_id}")
                    raise asyncio.CancelledError("Job cancelled by user")

                update_dict = MessageToDict(update, preserving_proto_field_name=True)
                
                # Real-time trades/fees telemetry
                total_trades_val = 0
                total_fees_val = 0.0
                daily_trades_dict = {}
                daily_fees_dict = {}
                if os.path.exists(trades_json_path):
                    try:
                        with open(trades_json_path, "r") as f:
                            trades_data = json.load(f)
                            total_trades_val = len(trades_data)
                            fee_rate_val = float(job_payload.get("fee_rate", 0.35))
                            
                            for t in trades_data:
                                t_ts = t.get("timestamp")
                                if t_ts:
                                    d_str = t_ts[:10]
                                    daily_trades_dict[d_str] = daily_trades_dict.get(d_str, 0) + 1
                                    daily_fees_dict[d_str] = daily_fees_dict.get(d_str, 0.0) + (float(t.get("volume", 0.0)) * fee_rate_val)
                                    
                            total_fees_val = sum(daily_fees_dict.values())
                    except Exception:
                        pass
                
                update_dict["total_trades"] = total_trades_val
                update_dict["total_fees"] = total_fees_val
                update_dict["daily_trades"] = daily_trades_dict
                update_dict["daily_fees"] = daily_fees_dict

                # Publish state update to Redis PubSub
                await ctx["redis"].publish(f"job_stream:{job_id}", json.dumps(update_dict))

                # Track metrics
                pnl = update.cumulative_pnl
                delta = update.greeks.delta
                
                # If a specific Deep Hedging model is requested, use its metrics for tracking & summary
                model_ids = job_payload.get("model_ids", [])
                active_model_id = model_ids[0] if model_ids else None
                if active_model_id and active_model_id != "black_scholes":
                    for mr in update.model_results:
                        if mr.model_id == active_model_id:
                            pnl = mr.cumulative_pnl
                            delta = mr.hedge_ratio
                            break
                            
                theta = update.greeks.theta
                gamma = update.greeks.gamma
                ts = update.tick_timestamp_ns
                
                pnl_list.append(pnl)
                delta_list.append(delta)
                theta_list.append(theta)
                gamma_list.append(gamma)
                ts_list.append(ts)

                # Parse date for daily results
                dt = datetime.utcfromtimestamp(ts / 1e9).date()
                date_str = dt.strftime("%Y%m%d")
                
                daily_pnls[date_str] = pnl
                daily_timesteps[date_str] = daily_timesteps.get(date_str, 0) + 1
                daily_rows[date_str] = daily_rows.get(date_str, 0) + 1

                # Collect RiskSnapshot for baseline
                snapshots.append(RiskSnapshot(
                    job_id=UUID(job_id),
                    model_id="baseline",
                    tick_idx=len(pnl_list) - 1,
                    delta=delta,
                    gamma=gamma,
                    cvar_95=update.cvar.cvar_95,
                    cvar_99=update.cvar.cvar_99,
                    pnl=update.pnl
                ))
                
                # Collect RiskSnapshot for each deep hedging model
                for mr in update.model_results:
                    snapshots.append(RiskSnapshot(
                        job_id=UUID(job_id),
                        model_id=mr.model_id,
                        tick_idx=len(pnl_list) - 1,
                        delta=mr.hedge_ratio,
                        gamma=gamma,
                        cvar_95=update.cvar.cvar_95,
                        cvar_99=update.cvar.cvar_99,
                        pnl=mr.pnl
                    ))

        # Stop polling task
        if polling_task and not polling_task.done():
            polling_task.cancel()
            try:
                await polling_task
            except BaseException:
                pass

        # Clear trades/orders one final time before final insert
        async with async_session_maker() as session:
            await session.execute(
                sa.text("DELETE FROM trades WHERE strategy_name = :name"),
                {"name": job_payload["strategy"]}
            )
            await session.execute(
                sa.text("DELETE FROM orders WHERE strategy_name = :name"),
                {"name": job_payload["strategy"]}
            )
            await session.commit()

        # Read and insert temp trades/orders from JSON files
        trades_to_insert = []
        orders_to_insert = []
        if os.path.exists(trades_json_path):
            try:
                with open(trades_json_path, "r") as f:
                    trades_to_insert = json.load(f)
            except Exception as e:
                print(f"Error loading trades JSON: {e}")
        if os.path.exists(orders_json_path):
            try:
                with open(orders_json_path, "r") as f:
                    orders_to_insert = json.load(f)
            except Exception as e:
                print(f"Error loading orders JSON: {e}")

        # Insert trades & orders to DB
        strategy_name = job_payload["strategy"]
        async with async_session_maker() as session:
            if trades_to_insert:
                await session.execute(
                    sa.text("""
                        INSERT INTO trades (timestamp, strategy_name, tradeid, symbol, direction, price, volume)
                        VALUES (:timestamp, :strategy_name, :tradeid, :symbol, :direction, :price, :volume)
                    """),
                    [
                        {
                            "timestamp": t.get("timestamp"),
                            "strategy_name": strategy_name,
                            "tradeid": t.get("tradeid"),
                            "symbol": t.get("symbol"),
                            "direction": t.get("direction"),
                            "price": float(t.get("price", 0.0)),
                            "volume": float(t.get("volume", 0.0))
                        }
                        for t in trades_to_insert
                    ]
                )
            if orders_to_insert:
                await session.execute(
                    sa.text("""
                        INSERT INTO orders (timestamp, strategy_name, orderid, symbol, direction, price, volume, traded, status)
                        VALUES (:timestamp, :strategy_name, :orderid, :symbol, :direction, :price, :volume, :traded, :status)
                    """),
                    [
                        {
                            "timestamp": o.get("timestamp"),
                            "strategy_name": strategy_name,
                            "orderid": o.get("orderid"),
                            "symbol": o.get("symbol"),
                            "direction": o.get("direction"),
                            "price": float(o.get("price", 0.0)),
                            "volume": float(o.get("volume", 0.0)),
                            "traded": float(o.get("traded", 0.0)),
                            "status": o.get("status")
                        }
                        for o in orders_to_insert
                    ]
                )
            await session.commit()

        # Query database orders & trades for this strategy to compute total trades and fees
        async with async_session_maker() as session:
            trades_result = await session.execute(
                sa.text("SELECT timestamp, price, volume, symbol FROM trades WHERE strategy_name = :name"),
                {"name": job_payload["strategy"]}
            )
            trades_rows = trades_result.fetchall()
            
            fee_rate = float(job_payload.get("fee_rate", 0.35))
            total_fees = 0.0
            total_trades = 0
            
            for t_row in trades_rows:
                ts_str, price, volume, symbol = t_row
                if "_" in symbol:
                    continue
                fee = float(volume) * fee_rate
                total_fees += fee
                total_trades += 1
                
                # Assign trade to daily trades/fees
                try:
                    t_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).date()
                    t_date_str = t_dt.strftime("%Y%m%d")
                    daily_fees[t_date_str] = daily_fees.get(t_date_str, 0.0) + fee
                    daily_trades[t_date_str] = daily_trades.get(t_date_str, 0) + 1
                except Exception:
                    pass

        # Compute summary metrics
        final_pnl = pnl_list[-1] if pnl_list else 0.0
        net_pnl = final_pnl - total_fees
        
        # Max drawdown
        peak = -999999999.0
        max_dd = 0.0
        for pnl in pnl_list:
            if pnl > peak:
                peak = pnl
            dd = peak - pnl
            if dd > max_dd:
                max_dd = dd

        # Daily returns & Sharpe
        sorted_dates = sorted(daily_pnls.keys())
        daily_returns = []
        prev_p = 0.0
        for d_str in sorted_dates:
            curr_p = daily_pnls[d_str]
            daily_returns.append(curr_p - prev_p)
            prev_p = curr_p
            
        if len(daily_returns) > 1:
            std = float(np.std(daily_returns, ddof=1))
            mean = float(np.mean(daily_returns))
            rf_daily = float(job_payload.get("risk_free_rate", 0.05)) / 252.0
            sharpe = (mean - rf_daily) / std * np.sqrt(252) if std > 0 else 0.0
        else:
            sharpe = 0.0

        # Construct daily results list
        daily_results_list = []
        for d_str in sorted_dates:
            p_end = daily_pnls[d_str]
            p_prev = daily_pnls[sorted_dates[sorted_dates.index(d_str) - 1]] if sorted_dates.index(d_str) > 0 else 0.0
            
            # Check if nested year/month/date directory exists
            year_val = d_str[:4]
            month_val = d_str[4:6]
            formatted_date = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:8]}"
            
            # Check options-data style: data/symbol/year/month/year-month-date.parquet
            check_deep_nested = os.path.join(workspace_root, "data", job_payload['parquet'], year_val, month_val, f"{formatted_date}.parquet")
            # Check our style: data/symbol/year/date.parquet
            check_nested = os.path.join(workspace_root, "data", job_payload['parquet'], year_val, f"{d_str}.parquet")
            
            if os.path.isfile(check_deep_nested):
                rel_file_path = f"data/{job_payload['parquet']}/{year_val}/{month_val}/{formatted_date}.parquet"
            elif os.path.isfile(check_nested):
                rel_file_path = f"data/{job_payload['parquet']}/{year_val}/{d_str}.parquet"
            else:
                rel_file_path = f"data/{job_payload['parquet']}/{d_str}.parquet"
                
            daily_results_list.append({
                "file": rel_file_path,
                "pnl": p_end - p_prev,
                "net_pnl": (p_end - p_prev) - daily_fees.get(d_str, 0.0),
                "fees": daily_fees.get(d_str, 0.0),
                "trades": daily_trades.get(d_str, 0),
                "timesteps": daily_timesteps.get(d_str, 0),
                "rows": daily_rows.get(d_str, 0)
            })

        # Render matplotlib chart
        # Compute day boundaries as indices in pnl_list where date changes
        day_boundaries = []
        prev_date = None
        for idx, ts in enumerate(ts_list):
            dt = datetime.utcfromtimestamp(ts / 1e9).date()
            if prev_date is not None and dt != prev_date:
                day_boundaries.append(idx)
            prev_date = dt

        chart_data = {
            "pnl": pnl_list,
            "delta": delta_list,
            "theta": theta_list,
            "gamma": gamma_list,
            "x_greek": [float(i) for i in range(len(pnl_list))],
            "day_boundaries": day_boundaries
        }
        
        chart_svg = render_backtest_chart_svg(chart_data)
        chart_image_base64 = render_backtest_chart_base64(chart_data)

        summary = {
            "final_pnl": final_pnl,
            "net_pnl": net_pnl,
            "total_trades": total_trades,
            "total_fees": total_fees,
            "max_drawdown": max_dd,
            "daily_sharpe": sharpe,
            "num_days": len(sorted_dates),
            "duration_seconds": (datetime.utcnow() - started_at).total_seconds(),
            "processed_timesteps": len(pnl_list),
            "daily_results": daily_results_list
        }

        # Update database with results
        async with async_session_maker() as session:
            job_record = await session.get(BacktestJob, UUID(job_id))
            if job_record:
                job_record.status = "COMPLETE"
                job_record.completed_at = datetime.utcnow()
                job_record.summary = summary
                
                # Bulk insert RiskSnapshots
                session.add_all(snapshots)
                await session.commit()

        # Publish final results to Redis PubSub
        final_payload = {
            "status": "ok",
            "result": summary,
            "daily_results": daily_results_list,
            "chart_svg": chart_svg,
            "chart_image_base64": chart_image_base64
        }
        await ctx["redis"].publish(f"job_stream:{job_id}", json.dumps(final_payload))

        return final_payload

    except (asyncio.CancelledError, grpc.aio.AioRpcError) as e:
        is_cancelled = isinstance(e, asyncio.CancelledError)
        if not is_cancelled and hasattr(e, "code") and e.code() == grpc.StatusCode.CANCELLED:
            is_cancelled = True
            
        if is_cancelled:
            async with async_session_maker() as session:
                job_record = await session.get(BacktestJob, UUID(job_id))
                if job_record:
                    job_record.status = "CANCELLED"
                    job_record.completed_at = datetime.utcnow()
                    await session.commit()
            await ctx["redis"].publish(f"job_stream:{job_id}", json.dumps({"status": "cancelled", "error": "Backtest cancelled by user"}))
            raise asyncio.CancelledError("Job cancelled by user")
        else:
            raise

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Error executing backtest job: {e}\n{tb}")
        
        async with async_session_maker() as session:
            job_record = await session.get(BacktestJob, UUID(job_id))
            if job_record:
                job_record.status = "FAILED"
                job_record.completed_at = datetime.utcnow()
                job_record.summary = {"error": str(e)}
                await session.commit()
        
        await ctx["redis"].publish(f"job_stream:{job_id}", json.dumps({"status": "error", "error": str(e)}))
        return {"status": "error", "error": str(e)}
    finally:
        if cancel_check_task and not cancel_check_task.done():
            cancel_check_task.cancel()
            try:
                await cancel_check_task
            except BaseException:
                pass

        if polling_task and not polling_task.done():
            polling_task.cancel()
            try:
                await polling_task
            except BaseException:
                pass

        if temp_file_to_cleanup and os.path.exists(temp_file_to_cleanup):
            try:
                os.remove(temp_file_to_cleanup)
            except Exception as cleanup_err:
                print(f"Error cleaning up temp file {temp_file_to_cleanup}: {cleanup_err}")

        # Clean up trades/orders JSON files
        for p in [trades_json_path, orders_json_path]:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception as cleanup_err:
                    print(f"Error cleaning up temp json {p}: {cleanup_err}")



async def notify_model_updated(ctx, *args, **kwargs):
    pass


async def generate_report(ctx, *args, **kwargs):
    pass


class WorkerSettings:
    functions = [run_backtest_job, notify_model_updated, generate_report]
    redis_settings = RedisSettings(host=REDIS_HOST, port=REDIS_PORT)
    max_jobs = 10
    job_timeout = 3600
    keep_result = 86400
    retry_jobs = True
    max_tries = 3
