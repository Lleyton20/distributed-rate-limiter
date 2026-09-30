"""Measure decision latency and throughput of the limiter against Redis.

    python bench/bench_limiter.py --workers 16 --requests 5000
"""

from __future__ import annotations

import argparse
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import redis

from ratelimiter import SlidingWindowLimiter, TokenBucketLimiter


def run(algorithm: str, url: str, workers: int, requests: int, keys: int) -> None:
    client = redis.Redis.from_url(url, decode_responses=True, max_connections=workers * 2)
    client.flushdb()
    if algorithm == "token_bucket":
        rl = TokenBucketLimiter(client, capacity=1_000, refill_per_sec=500)
    else:
        rl = SlidingWindowLimiter(client, limit=1_000, window_sec=1)

    def worker(wid: int) -> list[float]:
        lat = []
        for i in range(requests):
            t0 = time.perf_counter()
            rl.check(f"user-{(wid * requests + i) % keys}")
            lat.append((time.perf_counter() - t0) * 1000)
        return lat

    start = time.perf_counter()
    with ThreadPoolExecutor(workers) as pool:
        latencies = [x for chunk in pool.map(worker, range(workers)) for x in chunk]
    elapsed = time.perf_counter() - start

    q = statistics.quantiles(latencies, n=100)
    print(
        f"{algorithm:15s} {len(latencies):>7d} decisions  "
        f"{len(latencies) / elapsed:>9,.0f}/s  p50={q[49]:.2f}ms  p99={q[98]:.2f}ms"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="redis://localhost:6379/14")
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--requests", type=int, default=5000, help="per worker")
    p.add_argument("--keys", type=int, default=1000)
    a = p.parse_args()
    for algo in ("token_bucket", "sliding_window"):
        run(algo, a.url, a.workers, a.requests, a.keys)
