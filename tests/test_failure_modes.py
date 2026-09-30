import redis

from ratelimiter import SlidingWindowLimiter, TokenBucketLimiter


def _dead_redis():
    # Nothing listens on this port, so every call fails fast.
    return redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.05, socket_timeout=0.05)


def test_fail_open_allows_when_store_is_down():
    d = TokenBucketLimiter(_dead_redis(), capacity=5, refill_per_sec=1, fail_open=True).check("u")
    assert d.allowed and d.degraded


def test_fail_closed_rejects_when_store_is_down():
    d = SlidingWindowLimiter(_dead_redis(), limit=5, window_sec=1, fail_open=False).check("u")
    assert not d.allowed and d.degraded and d.retry_after_ms > 0


def test_recovers_after_script_cache_flush(r):
    rl = TokenBucketLimiter(r, capacity=3, refill_per_sec=0.001)
    assert rl.check("u").allowed
    r.script_flush()  # simulates a Redis restart / failover losing cached scripts
    assert rl.check("u").allowed
    assert rl.check("u").remaining == 0
