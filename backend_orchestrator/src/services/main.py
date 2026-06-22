"""Main engine service: gateway, orders-trades, logs."""

from datetime import datetime

from fastapi import HTTPException

from src.infra.state import AppState
from src.infra.remote_client import EngineClient


class MainService:
    """Gateway, orders-trades, and log operations."""

    @staticmethod
    def _get_client_or_400() -> EngineClient:
        client: EngineClient | None = AppState.live.live_client
        if client is None:
            raise HTTPException(status_code=400, detail="live engine (gRPC) not started")
        return client

    @staticmethod
    async def connect_gateway() -> dict:
        client = MainService._get_client_or_400()
        return await client.connect_gateway()

    @staticmethod
    async def disconnect_gateway() -> dict:
        client = MainService._get_client_or_400()
        return await client.disconnect_gateway()

    @staticmethod
    async def get_gateway_status() -> dict:
        client: EngineClient | None = AppState.live.live_client
        if client is None:
            return {"status": "stopped", "connected": False}
        try:
            status = await client.get_status()
            # detail e.g. "engine: running; ib: on; md: off"
            detail = status.get("detail") or ""
            ib_on = "ib: on" in detail
            return {
                "status": "running" if ib_on else "stopped",
                "connected": ib_on,
                "detail": detail,
            }
        except Exception as e:
            return {"status": "error", "connected": False, "detail": str(e)}

    @staticmethod
    async def get_market_status() -> dict:
        client: EngineClient | None = AppState.live.live_client
        if client is None:
            return {"status": "stopped", "connected": False}
        try:
            status = await client.get_status()
            detail = status.get("detail") or ""
            md_on = "md: on" in detail
            return {
                "status": "running" if md_on else "stopped",
                "connected": md_on,
                "detail": detail,
            }
        except Exception as e:
            return {"status": "error", "connected": False, "detail": str(e)}

    @staticmethod
    async def start_market_data() -> dict:
        client = MainService._get_client_or_400()
        return await client.start_market_data()

    @staticmethod
    async def stop_market_data() -> dict:
        client = MainService._get_client_or_400()
        return await client.stop_market_data()

    @staticmethod
    async def get_orders_and_trades() -> dict:
        client = MainService._get_client_or_400()
        return await client.get_orders_and_trades()

    @staticmethod
    async def get_portfolio_names() -> dict:
        client = MainService._get_client_or_400()
        names = await client.get_portfolio_names()
        return {"portfolios": names}

    @staticmethod
    def get_logs(limit: int = 200) -> dict:
        if limit <= 0:
            limit = 200
        return {"logs": AppState.live.log_buffer[-limit:]}

    @staticmethod
    def get_logs_api() -> dict:
        return {"logs": AppState.live.log_buffer[-50:]}

    @staticmethod
    def clear_logs() -> dict:
        """Clear log buffer (e.g. Clear button)."""
        AppState.live.log_buffer.clear()
        return {"status": "ok"}

    @staticmethod
    def _format_timestamp(timestamp_str: str) -> str:
        if not timestamp_str:
            return "-"
        try:
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            return dt.strftime("%m/%d/%Y %H:%M:%S")
        except Exception:
            return timestamp_str
