import sys
import asyncio
from pathlib import Path

# Add backend directory to path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from src.infra.remote_client import EngineClient

async def run_test():
    print("Initializing EngineClient...")
    client = EngineClient()
    
    print("Testing send_command: 'order'...")
    order_payload = {
        "symbol": "AAPL-20240607-C-190.0",
        "exchange": "SMART",
        "direction": "LONG",
        "type": "LIMIT",
        "volume": 1.0,
        "price": 5.25,
        "reference": "manual_test_order",
        "is_combo": False
    }
    
    resp = await client.send_command("order", order_payload)
    print("Order Send Response:", resp)
    
    print("Testing send_command: 'cancel'...")
    cancel_payload = {
        "orderid": "backtest_order_1",
        "symbol": "AAPL-20240607-C-190.0",
        "exchange": "LOCAL",
        "is_combo": False
    }
    
    resp = await client.send_command("cancel", cancel_payload)
    print("Cancel Response:", resp)

if __name__ == "__main__":
    asyncio.run(run_test())
