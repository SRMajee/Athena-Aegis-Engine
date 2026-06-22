"""WebSocket handlers and log bridging for OTrader backend."""

import asyncio
import json
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect

from src.infra.state import AppState


def handle_loguru_log(record: dict) -> None:
    """Loguru records → buffer + queue for WebSocket."""
    try:
        level_name = record["level"].name
        timestamp = datetime.fromtimestamp(record["time"].timestamp()).strftime("%d/%m %H:%M:%S")
        gateway_name = record["extra"].get("gateway_name", "Unknown")
        message = record["message"]
        formatted_msg = f"{timestamp} | {level_name:<7} | {gateway_name:<10} | {message}"
        AppState.live.log_buffer.append(formatted_msg)
        if len(AppState.live.log_buffer) > AppState.live.max_logs:
            AppState.live.log_buffer = AppState.live.log_buffer[-AppState.live.max_logs :]
        
        # Thread-safe push into asyncio.Queue
        if AppState.main_loop and AppState.main_loop.is_running():
            AppState.main_loop.call_soon_threadsafe(AppState.live.log_queue.put_nowait, formatted_msg)
        else:
            try:
                AppState.live.log_queue.put_nowait(formatted_msg)
            except Exception:
                pass
    except Exception as e:
        print(f"Error handling loguru log: {e}")


async def log_queue_processor() -> None:
    """Send log queue to WebSocket clients."""
    while True:
        try:
            log_line = await AppState.live.log_queue.get()
            for ws in list(AppState.ws.log_clients):
                try:
                    await ws.send_text(log_line)
                except Exception:
                    AppState.ws.log_clients.discard(ws)
        except Exception:
            await asyncio.sleep(0.1)


async def handle_logs_websocket(ws: WebSocket) -> None:
    """Logs WebSocket: backlog + stream."""
    await ws.accept()
    AppState.ws.log_clients.add(ws)
    for line in AppState.live.log_buffer[-200:]:
        try:
            await ws.send_text(line)
        except Exception:
            break
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        AppState.ws.log_clients.discard(ws)


async def handle_strategies_websocket(ws: WebSocket) -> None:
    """Strategies WebSocket (live C++; connection kept for future push)."""
    await ws.accept()
    AppState.ws.strategy_clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        AppState.ws.strategy_clients.discard(ws)


pubsub_tasks: dict[str, asyncio.Task] = {}


async def subscribe_to_job_channel(job_id: str) -> None:
    """Subscribe to Redis PubSub channel for a job and broadcast to local WS clients."""
    redis_client = getattr(AppState, "redis", None)
    if redis_client is None:
        return

    pubsub = redis_client.pubsub()
    channel_name = f"job_stream:{job_id}"
    await pubsub.subscribe(channel_name)
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message:
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                clients = AppState.ws.job_subscribers.get(job_id, set())
                for ws in list(clients):
                    try:
                        await ws.send_text(data)
                    except Exception:
                        clients.discard(ws)
            await asyncio.sleep(0.01)
    except asyncio.CancelledError:
        await pubsub.unsubscribe(channel_name)
    except Exception as e:
        print(f"Error in pubsub subscription for {job_id}: {e}")


async def handle_stream_websocket(ws: WebSocket, job_id: str) -> None:
    """Subscribes the websocket client to a job_id's Redis PubSub channel updates."""
    await ws.accept()

    # Avoid race conditions by checking if the job is already completed or failed in DB
    from src.infra.db import async_session_maker, BacktestJob
    from uuid import UUID
    try:
        job_uuid = UUID(job_id)
        async with async_session_maker() as session:
            job_record = await session.get(BacktestJob, job_uuid)
            if job_record:
                if job_record.status == "COMPLETE":
                    daily_results = job_record.summary.get("daily_results", []) if job_record.summary else []
                    final_payload = {
                        "status": "ok",
                        "result": job_record.summary,
                        "daily_results": daily_results
                    }
                    await ws.send_text(json.dumps(final_payload))
                    return
                elif job_record.status == "FAILED":
                    error_msg = job_record.summary.get("error", "Unknown error") if job_record.summary else "Unknown error"
                    await ws.send_text(json.dumps({"status": "error", "error": error_msg}))
                    return
                elif job_record.status == "CANCELLED":
                    await ws.send_text(json.dumps({"status": "cancelled", "error": "Backtest cancelled by user"}))
                    return
    except Exception as e:
        print(f"Error checking job status in stream WS: {e}")

    if job_id not in AppState.ws.job_subscribers:
        AppState.ws.job_subscribers[job_id] = set()
    AppState.ws.job_subscribers[job_id].add(ws)

    # Start PubSub subscription task if not active
    if job_id not in pubsub_tasks or pubsub_tasks[job_id].done():
        pubsub_tasks[job_id] = asyncio.create_task(subscribe_to_job_channel(job_id))

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        clients = AppState.ws.job_subscribers.get(job_id, set())
        clients.discard(ws)
        if not clients:
            if job_id in AppState.ws.job_subscribers:
                del AppState.ws.job_subscribers[job_id]
            task = pubsub_tasks.pop(job_id, None)
            if task:
                task.cancel()
