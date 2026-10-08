"""
Live Proxy Connectivity Test Script for VPS
Run directly on your VPS to test outbound connectivity and IP addresses for:
1. Direct (Own IP)
2. Route 1 (Wireproxy Tunnel 1)
3. Route 2 (Wireproxy Tunnel 2)

Usage:
    python test/test_proxy_live.py
"""

import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

ROUTE_1_PROXY = os.getenv("ROUTE_1_PROXY", "socks5://127.0.0.1:1081")
ROUTE_2_PROXY = os.getenv("ROUTE_2_PROXY", "socks5://127.0.0.1:1082")

ROUTES = [
    ("Direct (Own IP)", None),
    ("Route 1 (Tunnel 1)", ROUTE_1_PROXY),
    ("Route 2 (Tunnel 2)", ROUTE_2_PROXY),
]

TEST_URL = "https://api.ipify.org?format=json"


async def test_single_route(name: str, proxy_url: str | None):
    print(f"\n[*] Testing '{name}' via proxy: {proxy_url or 'None (Direct)'}...")
    try:
        async with httpx.AsyncClient(proxy=proxy_url, timeout=10.0) as client:
            resp = await client.get(TEST_URL)
            if resp.status_code == 200:
                ip = resp.json().get("ip")
                print(f"  [SUCCESS] Outbound IP resolved to: {ip}")
                return True
            else:
                print(f"  [FAILED] HTTP status: {resp.status_code}")
                return False
    except Exception as exc:
        print(f"  [ERROR] Connection failed: {exc}")
        return False


async def main():
    print("=" * 60)
    print("Testing 3 Outbound Proxy Routes...")
    print("=" * 60)

    results = []
    for name, proxy in ROUTES:
        ok = await test_single_route(name, proxy)
        results.append((name, ok))

    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)
    for name, ok in results:
        status = "PASSED" if ok else "FAILED"
        print(f"  - {name}: {status}")


if __name__ == "__main__":
    asyncio.run(main())
