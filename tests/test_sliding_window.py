import time

from ratelimiter import SlidingWindowLimiter


def test_allows_limit_per_window(r):
    rl = SlidingWindowLimiter(r, limit=4, window_sec=10)
    assert [rl.check("u").allowed for _ in range(6)] == [True] * 4 + [False] * 2


def test_window_slides(r):
    rl = SlidingWindowLimiter(r, limit=2, window_sec=0.1)
    assert rl.check("u").allowed and rl.check("u").allowed
    assert not rl.check("u").allowed
    time.sleep(0.12)
    assert rl.check("u").allowed


def test_denied_requests_are_not_recorded(r):
    rl = SlidingWindowLimiter(r, limit=1, window_sec=10)
    rl.check("u")
    for _ in range(5):
        rl.check("u")
    assert r.zcard("rl:sw:u") == 1


def test_retry_after_points_to_oldest_request(r):
    rl = SlidingWindowLimiter(r, limit=1, window_sec=1)
    rl.check("u")
    d = rl.check("u")
    assert not d.allowed
    assert 900 <= d.retry_after_ms <= 1000
