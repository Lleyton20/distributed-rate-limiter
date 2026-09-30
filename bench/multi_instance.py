"""End-to-end check: several API replicas share ONE limit.

Sends concurrent requests with the same API key, spread round-robin across
every replica, and verifies the total number of 200s equals the configured
capacity (no replica hands out extra requests).

    python bench/multi_instance.py --urls http://localhost:8001 http://localhost:8002 http://localhost:8003 --capacity 100
"""

from __future__ import annotations

import argparse
import asyncio
import collections

import httpx


async def main(urls: list[str], total: int, capacity: int, concurrency: int) -> None:
    sem = asyncio.Semaphore(concurrency)
    statuses: collections.Counter = collections.Counter()
    served_by: collections.Counter = collections.Counter()

    async with httpx.AsyncClient(timeout=5) as client:

        async def one(i: int) -> None:
            async with sem:
                resp = await client.get(f"{urls[i % len(urls)]}/api/resource", headers={"x-api-key": "load-test"})
                statuses[resp.status_code] += 1
                if resp.status_code == 200:
                    served_by[urls[i % len(urls)]] += 1

        await asyncio.gather(*(one(i) for i in range(total)))

    print(f"sent {total} requests across {len(urls)} replicas")
    print(f"status codes: {dict(statuses)}")
    print(f"allowed per replica: {dict(served_by)}")
    ok = statuses[200] == capacity
    print(f"global limit {'HELD' if ok else 'VIOLATED'}: {statuses[200]} allowed vs capacity {capacity}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--urls", nargs="+", required=True)
    p.add_argument("--total", type=int, default=1000)
    p.add_argument("--capacity", type=int, default=100)
    p.add_argument("--concurrency", type=int, default=50)
    a = p.parse_args()
    asyncio.run(main(a.urls, a.total, a.capacity, a.concurrency))
