from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager


@asynccontextmanager
async def live_client_lifespan() -> AsyncGenerator[None, None]:
    """Manage C++ live gRPC client, status polling, and log streaming."""
    from src.infra.state import AppState  # imported lazily
    from src.infra.remote_client import EngineClient

    live_status_task: asyncio.Task | None = None

    # Init C++ live gRPC client
    if AppState.live.live_client is None:
        try:
            AppState.live.live_client = EngineClient()
        except Exception as e:  # pragma: no cover - defensive
            print(
                f"Failed to initialize gRPC live client (backend will stay in backtest-only mode): {e}"
            )

    # Heartbeat task for live_status
    async def _poll_live_status() -> None:
        while True:
            if AppState.live.live_client is None:
                AppState.live.live_status = {
                    "status": "stopped",
                    "connected": False,
                    "detail": "live_client not initialized",
                }
            else:
                try:
                    AppState.live.live_status = await AppState.live.live_client.get_status()
                except Exception as e:  # noqa: BLE001
                    AppState.live.live_status = {
                        "status": "error",
                        "connected": False,
                        "detail": f"gRPC client error: {e}",
                    }
            await asyncio.sleep(2.0)

    live_status_task = asyncio.create_task(_poll_live_status())

    # Log stream task → log_queue / log_buffer
    async def _stream_live_logs() -> None:
        if AppState.live.live_client is None:
            return
        try:
            AppState.live.log_stream_alive = True
            async for line in AppState.live.live_client.stream_logs():
                try:
                    AppState.live.log_buffer.append(line)
                    if len(AppState.live.log_buffer) > AppState.live.max_logs:
                        AppState.live.log_buffer = AppState.live.log_buffer[
                            -AppState.live.max_logs :
                        ]
                except Exception as be:
                    print(f"Failed to buffer live log line: {be}")
                AppState.live.log_queue.put_nowait(line)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"live log stream stopped: {e}")
        finally:
            AppState.live.log_stream_alive = False

    try:
        # Start log stream once
        try:
            from src.infra.state import AppState as _S  # type: ignore[import]

            if _S.live.live_log_task is None:
                _S.live.live_log_task = asyncio.create_task(_stream_live_logs())
        except Exception as e:  # pragma: no cover - defensive
            print(f"Failed to start live log stream task: {e}")

        yield
    finally:
        if live_status_task is not None:
            live_status_task.cancel()
            try:
                await live_status_task
            except asyncio.CancelledError:
                pass
        
        try:
            from src.infra.state import AppState as _S2  # type: ignore[import]

            if _S2.live.live_log_task is not None:
                _S2.live.live_log_task.cancel()
                try:
                    await _S2.live.live_log_task
                except asyncio.CancelledError:
                    pass
        except Exception:
            pass
