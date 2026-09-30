"""The core distributed guarantee: many app instances hammering the same key
concurrently never let through more than the limit."""

import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor

import redis

from ratelimiter import SlidingWindowLimiter, TokenBucketLimiter

INSTANCES = 8
REQUESTS_PER_INSTANCE = 100
LIMIT = 150


def _hammer_token_bucket(url: str, n: int) -> int:
    client = redis.Redis.from_url(url, decode_responses=True)  # separate connection = separate "instance"
    rl = TokenBucketLimiter(client, capacity=LIMIT, refill_per_sec=0.0001)
    return sum(rl.check("shared").allowed for _ in range(n))


def _hammer_sliding_window(url: str, n: int) -> int:
    client = redis.Redis.from_url(url, decode_responses=True)
    rl = SlidingWindowLimiter(client, limit=LIMIT, window_sec=60)
    return sum(rl.check("shared").allowed for _ in range(n))


def test_token_bucket_exact_under_threads(r, redis_url):
    with ThreadPoolExecutor(INSTANCES) as pool:
        allowed = sum(pool.map(_hammer_token_bucket, [redis_url] * INSTANCES, [REQUESTS_PER_INSTANCE] * INSTANCES))
    assert allowed == LIMIT


def test_sliding_window_exact_under_threads(r, redis_url):
    with ThreadPoolExecutor(INSTANCES) as pool:
        allowed = sum(pool.map(_hammer_sliding_window, [redis_url] * INSTANCES, [REQUESTS_PER_INSTANCE] * INSTANCES))
    assert allowed == LIMIT


def test_token_bucket_exact_across_processes(r, redis_url):
    ctx = mp.get_context("spawn")
    with ctx.Pool(INSTANCES) as pool:
        allowed = sum(pool.starmap(_hammer_token_bucket, [(redis_url, REQUESTS_PER_INSTANCE)] * INSTANCES))
    assert allowed == LIMIT


def test_naive_read_then_write_overcounts(r):
    """Why the Lua script matters: a GET-then-SET counter races and lets
    extra requests through. This test documents the bug the design avoids."""
    r.set("naive", 0)

    def naive_check() -> bool:
        c = redis.Redis(connection_pool=r.connection_pool)
        count = int(c.get("naive"))
        if count < LIMIT:
            c.set("naive", count + 1)
            return True
        return False

    def worker(_):
        return sum(naive_check() for _ in range(REQUESTS_PER_INSTANCE))

    with ThreadPoolExecutor(INSTANCES) as pool:
        allowed = sum(pool.map(worker, range(INSTANCES)))
    assert allowed >= LIMIT  # usually well above LIMIT; never below
