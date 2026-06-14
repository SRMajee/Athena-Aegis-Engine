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


async def run_backtest_job(ctx, job_payload: dict) -> dict:
    job_id = ctx["job_id"]
    started_at = datetime.utcnow()

    # Update job status in PostgreSQL to RUNNING
    async with async_session_maker() as session:
        job_record = await session.get(BacktestJob, UUID(job_id))
        if job_record:
            job_record.status = "RUNNING"
            job_record.started_at = started_at
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
        # Build StreamRequest and StrategyConfig
        strat_cfg = pb2.StrategyConfig(
            parquet_path=job_payload["parquet"],
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
            
            async for update in stream:
                # Check for cancellation
                if await ctx["redis"].exists(f"job_cancel:{job_id}"):
                    await ctx["redis"].delete(f"job_cancel:{job_id}")
                    raise asyncio.CancelledError("Job cancelled by user")

                update_dict = MessageToDict(update, preserving_proto_field_name=True)
                
                # Publish state update to Redis PubSub
                await ctx["redis"].publish(f"job_stream:{job_id}", json.dumps(update_dict))

                # Track metrics
                pnl = update.cumulative_pnl
                delta = update.greeks.delta
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

                # Collect RiskSnapshot
                snapshots.append(RiskSnapshot(
                    job_id=UUID(job_id),
                    model_id=update.model_results[0].model_id if update.model_results else "baseline",
                    tick_idx=len(pnl_list) - 1,
                    delta=delta,
                    gamma=gamma,
                    cvar_95=update.cvar.cvar_95,
                    cvar_99=update.cvar.cvar_99,
                    pnl=update.pnl
                ))

        # Query database orders & trades for this strategy to compute total trades and fees
        async with async_session_maker() as session:
            trades_result = await session.execute(
                sa.text("SELECT timestamp, price, volume FROM trades WHERE strategy_name = :name"),
                {"name": job_payload["strategy"]}
            )
            trades_rows = trades_result.fetchall()
            
            total_trades = len(trades_rows)
            fee_rate = float(job_payload.get("fee_rate", 0.35))
            total_fees = 0.0
            
            for t_row in trades_rows:
                ts_str, price, volume = t_row
                fee = float(price) * float(volume) * fee_rate
                total_fees += fee
                
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
            daily_results_list.append({
                "file": f"data/{job_payload['strategy']}/{d_str}.parquet",
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
            "processed_timesteps": len(pnl_list)
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

    except asyncio.CancelledError:
        async with async_session_maker() as session:
            job_record = await session.get(BacktestJob, UUID(job_id))
            if job_record:
                job_record.status = "CANCELLED"
                job_record.completed_at = datetime.utcnow()
                await session.commit()
        await ctx["redis"].publish(f"job_stream:{job_id}", json.dumps({"status": "cancelled", "error": "Backtest cancelled by user"}))
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
