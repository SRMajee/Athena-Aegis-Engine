from __future__ import annotations

import json
import os
from typing import Any, Dict, List

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

    async def get_status(self) -> Dict[str, Any]:
        resp = await self._stub.GetStatus(pb2.Empty())
        return {
            "status": "running" if resp.running else "stopped",
            "connected": bool(resp.connected),
            "detail": resp.detail,
        }

    async def get_orders_and_trades(self) -> Dict[str, Any]:
        resp = await self._stub.GetOrdersAndTrades(pb2.Empty())
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
        resp = await self._stub.ListPortfolios(pb2.Empty())
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
        resp = await self._stub.ListStrategyClasses(pb2.Empty())
        return list(resp.classes)

    async def get_strategy_class_defaults(self, strategy_class: str) -> Dict[str, float]:
        """Return default strategy settings for a class (from strategy_config.json)."""
        req = pb2.GetStrategyClassDefaultsRequest(strategy_class=strategy_class)
        resp = await self._stub.GetStrategyClassDefaults(req)
        return dict(resp.settings)

    async def get_portfolios_meta(self) -> List[str]:
        resp = await self._stub.ListPortfolios(pb2.Empty())
        return list(resp.portfolios)

    async def get_removed_strategies(self) -> List[str]:
        resp = await self._stub.GetRemovedStrategies(pb2.Empty())
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
        resp = await self._stub.AddStrategy(req)
        return {"status": "ok", "strategy_name": resp.strategy_name}

    async def init_strategy(self, strategy_name: str) -> Dict[str, Any]:
        await self._stub.InitStrategy(pb2.StrategyNameRequest(strategy_name=strategy_name))
        return {"status": "ok"}

    async def start_strategy(self, strategy_name: str) -> Dict[str, Any]:
        await self._stub.StartStrategy(pb2.StrategyNameRequest(strategy_name=strategy_name))
        return {"status": "ok"}

    async def stop_strategy(self, strategy_name: str) -> Dict[str, Any]:
        await self._stub.StopStrategy(pb2.StrategyNameRequest(strategy_name=strategy_name))
        return {"status": "ok"}

    async def remove_strategy(self, strategy_name: str) -> Dict[str, Any]:
        resp = await self._stub.RemoveStrategy(pb2.StrategyNameRequest(strategy_name=strategy_name))
        return {"status": "ok", "removed": bool(resp.removed)}

    async def delete_strategy(self, strategy_name: str) -> Dict[str, Any]:
        resp = await self._stub.DeleteStrategy(pb2.StrategyNameRequest(strategy_name=strategy_name))
        return {"status": "ok", "deleted": bool(resp.deleted)}

    async def get_strategy_holdings(self) -> Dict[str, Any]:
        resp = await self._stub.GetStrategyHoldings(pb2.Empty())
        holdings: Dict[str, Any] = {}
        for name, json_str in resp.holdings.items():
            try:
                holdings[name] = json.loads(json_str) if json_str else {}
            except json.JSONDecodeError:
                holdings[name] = {}
        return {"holdings": holdings}

    async def connect_gateway(self) -> Dict[str, Any]:
        """Connect IBKR gateway (account/order channel); market data is separate."""
        try:
            await self._stub.ConnectGateway(pb2.Empty())
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
                await self._stub.StopMarketData(pb2.Empty())
            except Exception:
                # Ignore StopMarketData errors on disconnect
                pass
            await self._stub.DisconnectGateway(pb2.Empty())
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
            await self._stub.StartMarketData(pb2.Empty())
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
            await self._stub.StopMarketData(pb2.Empty())
            status = await self.get_status()
            return {
                "status": "ok",
                "message": "Market data stopped.",
                "gateway": status,
            }
        except Exception as e:
            return {"status": "error", "message": f"StopMarketData failed: {e}"}

    async def stream_logs(self):
        """Yield log lines from C++ via gRPC StreamLogs (server-formatted)."""
        try:
            async for msg in self._stub.StreamLogs(pb2.Empty()):
                # msg.line is a plain text line
                yield msg.line
        except Exception:
            # Connection dropped or stream ended
            return
