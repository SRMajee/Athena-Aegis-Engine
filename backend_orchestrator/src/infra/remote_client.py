from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

from google.protobuf.json_format import MessageToDict
import grpc.aio

from src.proto import otrader_engine_pb2 as pb2
from src.proto import otrader_engine_pb2_grpc as pb2_grpc


class EngineClient:
    """gRPC client for C++ live EngineService (gateway, strategies, orders/trades, holdings)."""

    def __init__(self, target: str | None = None) -> None:
        if target is None:
            target = os.getenv("LIVE_GRPC_TARGET", "127.0.0.1:50051")
        self._target = target
        self._channel = grpc.aio.insecure_channel(self._target)
        self._stub = pb2_grpc.EngineServiceStub(self._channel)

    def _reconnect(self) -> None:
        """Close current channel and recreate connection to target."""
        try:
            self._channel = grpc.aio.insecure_channel(self._target)
            self._stub = pb2_grpc.EngineServiceStub(self._channel)
        except Exception:
            pass

    async def _execute_with_retry(self, method_name: str, *args, **kwargs) -> Any:
        import asyncio
        max_retries = 3
        backoff = 0.5
        for attempt in range(max_retries):
            try:
                method = getattr(self._stub, method_name)
                return await method(*args, **kwargs)
            except grpc.RpcError as e:
                if attempt == max_retries - 1:
                    raise e
                self._reconnect()
                await asyncio.sleep(backoff)
                backoff *= 2

    async def get_status(self) -> Dict[str, Any]:
        resp = await self._execute_with_retry("GetStatus", pb2.Empty())
        return {
            "status": "running" if resp.running else "stopped",
            "connected": bool(resp.connected),
            "detail": resp.detail,
        }

    async def get_orders_and_trades(self) -> Dict[str, Any]:
        resp = await self._execute_with_retry("GetOrdersAndTrades", pb2.Empty())
        return self._convert_orders_and_trades(resp)

    @staticmethod
    def _format_timestamp(ts: str) -> str:
        if not ts:
            return "-"
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.strftime("%m/%d/%Y %H:%M:%S")
        except Exception:
            return ts

    def _convert_orders_and_trades(self, resp: Any) -> Dict[str, Any]:
        records: List[Dict[str, Any]] = []
        for o in resp.orders:
            records.append(
                {
                    "record_type": "Order",
                    "timestamp": o.timestamp,
                    "strategy_name": o.strategy_name,
                    "orderid": o.orderid,
                    "symbol": o.symbol,
                    "exchange": o.exchange,
                    "trading_class": o.trading_class,
                    "type": o.type,
                    "direction": o.direction,
                    "price": o.price if o.price else None,
                    "volume": o.volume if o.volume else None,
                    "traded": o.traded if o.traded else None,
                    "status": o.status,
                    "datetime": o.datetime,
                    "reference": o.reference,
                    "is_combo": o.is_combo,
                    "legs_info": o.legs_info,
                    "formatted_price": f"{o.price:.2f}" if o.price else "-",
                    "formatted_quantity": str(o.traded or o.volume) if (o.traded or o.volume) else "-",
                    "formatted_timestamp": self._format_timestamp(o.timestamp),
                }
            )
        for t in resp.trades:
            records.append(
                {
                    "record_type": "Trade",
                    "timestamp": t.timestamp,
                    "strategy_name": t.strategy_name,
                    "tradeid": t.tradeid,
                    "symbol": t.symbol,
                    "exchange": t.exchange,
                    "orderid": t.orderid,
                    "direction": t.direction,
                    "price": t.price if t.price else None,
                    "volume": t.volume if t.volume else None,
                    "datetime": t.datetime,
                    "formatted_price": f"{t.price:.2f}" if t.price else "-",
                    "formatted_quantity": str(t.volume) if t.volume else "-",
                    "formatted_timestamp": self._format_timestamp(t.timestamp),
                }
            )
        records.sort(key=lambda x: x["timestamp"], reverse=True)
        return {"records": records}

    async def get_portfolio_names(self) -> List[str]:
        resp = await self._execute_with_retry("ListPortfolios", pb2.Empty())
        return list(resp.portfolios)

    async def list_strategies(self) -> List[Dict[str, Any]]:
        resp_iter = self._stub.ListStrategies(pb2.Empty())
        out = []
        async for s in resp_iter:
            out.append(
                {
                    "strategy_name": s.strategy_name,
                    "class_name": s.class_name,
                    "portfolio": s.portfolio,
                    "status": s.status,
                }
            )
        return out

    async def get_strategy_classes(self) -> List[str]:
        resp = await self._execute_with_retry("ListStrategyClasses", pb2.Empty())
        return list(resp.classes)

    async def get_strategy_class_defaults(self, strategy_class: str) -> Dict[str, float]:
        """Return default strategy settings for a class (from strategy_config.json)."""
        req = pb2.GetStrategyClassDefaultsRequest(strategy_class=strategy_class)
        resp = await self._execute_with_retry("GetStrategyClassDefaults", req)
        return dict(resp.settings)

    async def get_portfolios_meta(self) -> List[str]:
        resp = await self._execute_with_retry("ListPortfolios", pb2.Empty())
        return list(resp.portfolios)

    async def get_removed_strategies(self) -> List[str]:
        resp = await self._execute_with_retry("GetRemovedStrategies", pb2.Empty())
        return list(resp.removed_strategies)

    async def add_strategy(
        self,
        strategy_class: str,
        portfolio_name: str,
        setting: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        req = pb2.AddStrategyRequest(
            strategy_class=strategy_class,
            portfolio_name=portfolio_name,
            setting_json=json.dumps(setting or {}),
        )
        resp = await self._execute_with_retry("AddStrategy", req)
        return {"status": "ok", "strategy_name": resp.strategy_name}

    async def init_strategy(self, strategy_name: str) -> Dict[str, Any]:
        await self._execute_with_retry("InitStrategy", pb2.StrategyNameRequest(strategy_name=strategy_name))
        return {"status": "ok"}

    async def start_strategy(self, strategy_name: str) -> Dict[str, Any]:
        await self._execute_with_retry("StartStrategy", pb2.StrategyNameRequest(strategy_name=strategy_name))
        return {"status": "ok"}

    async def stop_strategy(self, strategy_name: str) -> Dict[str, Any]:
        await self._execute_with_retry("StopStrategy", pb2.StrategyNameRequest(strategy_name=strategy_name))
        return {"status": "ok"}

    async def remove_strategy(self, strategy_name: str) -> Dict[str, Any]:
        resp = await self._execute_with_retry("RemoveStrategy", pb2.StrategyNameRequest(strategy_name=strategy_name))
        return {"status": "ok", "removed": bool(resp.removed)}

    async def delete_strategy(self, strategy_name: str) -> Dict[str, Any]:
        resp = await self._execute_with_retry("DeleteStrategy", pb2.StrategyNameRequest(strategy_name=strategy_name))
        return {"status": "ok", "deleted": bool(resp.deleted)}

    async def get_strategy_holdings(self) -> Dict[str, Any]:
        resp = await self._execute_with_retry("GetStrategyHoldings", pb2.Empty())
        holdings: Dict[str, Any] = {}
        for name, data_str in resp.holdings.items():
            try:
                raw_bytes = data_str.encode('utf-8', errors='surrogateescape') if isinstance(data_str, str) else data_str
                msg = pb2.StrategyHoldingMsg()
                msg.ParseFromString(raw_bytes)
                holdings[name] = MessageToDict(msg, preserving_proto_field_name=True)
            except Exception as e:
                logging.getLogger("uvicorn").error(f"Error parsing holding for {name}: {e}")
                holdings[name] = {}
        return {"holdings": holdings}

    async def connect_gateway(self) -> Dict[str, Any]:
        """Connect IBKR gateway (account/order channel); market data is separate."""
        try:
            await self._execute_with_retry("ConnectGateway", pb2.Empty())
        except Exception as e:
            return {"status": "error", "message": f"Connect failed: {e}"}

        status = await self.get_status()
        # Confirm C++ side reports IB connected
        if not status.get("connected"):
            detail = status.get("detail") or ""
            return {
                "status": "error",
                "message": "IBKR gateway not connected. Check TWS/Gateway API settings.",
                "gateway": status,
                "detail": detail,
            }

        return {
            "status": "ok",
            "message": "IBKR gateway connected (no market data auto-start).",
            "gateway": status,
        }

    async def disconnect_gateway(self) -> Dict[str, Any]:
        try:
            try:
                await self._execute_with_retry("StopMarketData", pb2.Empty())
            except Exception:
                # Ignore StopMarketData errors on disconnect
                pass
            await self._execute_with_retry("DisconnectGateway", pb2.Empty())
            status = await self.get_status()
            return {
                "status": "ok",
                "message": "Disconnected successfully (gRPC live engine)",
                "gateway": status,
            }
        except Exception as e:
            return {"status": "error", "message": f"Disconnect failed: {e}"}

    async def start_market_data(self) -> Dict[str, Any]:
        """Start market data (gateway state unchanged)."""
        try:
            await self._execute_with_retry("StartMarketData", pb2.Empty())
            status = await self.get_status()
            return {
                "status": "ok",
                "message": "Market data started.",
                "gateway": status,
            }
        except Exception as e:
            return {"status": "error", "message": f"StartMarketData failed: {e}"}

    async def stop_market_data(self) -> Dict[str, Any]:
        """Stop market data (gateway state unchanged)."""
        try:
            await self._execute_with_retry("StopMarketData", pb2.Empty())
            status = await self.get_status()
            return {
                "status": "ok",
                "message": "Market data stopped.",
                "gateway": status,
            }
        except Exception as e:
            return {"status": "error", "message": f"StopMarketData failed: {e}"}

    async def stream_logs(self):
        """Yield log lines from C++ via gRPC StreamLogs (server-formatted) with auto-reconnect."""
        import asyncio
        backoff = 0.5
        while True:
            try:
                async for msg in self._stub.StreamLogs(pb2.Empty()):
                    backoff = 0.5
                    yield msg.line
            except grpc.RpcError:
                self._reconnect()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10.0)
            except Exception:
                return

    async def send_command(self, action: str, payload: dict) -> Dict[str, Any]:
        """Send manual commands (e.g. order, cancel) via the streaming SendCommand RPC."""
        import uuid
        command_id = str(uuid.uuid4())

        async def request_generator():
            yield pb2.CommandRequest(
                command_id=command_id,
                action=action,
                payload_json=json.dumps(payload),
            )

        try:
            resp = await self._stub.SendCommand(request_generator())
            return {
                "command_id": resp.command_id,
                "success": resp.success,
                "error_message": resp.error_message,
            }
        except Exception as e:
            return {
                "command_id": command_id,
                "success": False,
                "error_message": str(e),
            }
