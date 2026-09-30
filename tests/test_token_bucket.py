import time

import pytest

from ratelimiter import TokenBucketLimiter


def test_allows_burst_up_to_capacity_then_denies(r):
    rl = TokenBucketLimiter(r, capacity=5, refill_per_sec=0.001)
    results = [rl.check("user").allowed for _ in range(7)]
    assert results == [True] * 5 + [False] * 2


def test_remaining_counts_down(r):
    rl = TokenBucketLimiter(r, capacity=3, refill_per_sec=0.001)
    assert [rl.check("u").remaining for _ in range(3)] == [2, 1, 0]


def test_denied_request_reports_retry_after(r):
    rl = TokenBucketLimiter(r, capacity=1, refill_per_sec=2)  # one token every 500 ms
    assert rl.check("u").allowed
    d = rl.check("u")
    assert not d.allowed
    assert 400 <= d.retry_after_ms <= 500


def test_refills_over_time(r):
    rl = TokenBucketLimiter(r, capacity=2, refill_per_sec=20)  # one token every 50 ms
    assert rl.check("u").allowed and rl.check("u").allowed
    assert not rl.check("u").allowed
    time.sleep(0.12)
    assert rl.check("u").allowed


def test_never_refills_above_capacity(r):
    rl = TokenBucketLimiter(r, capacity=3, refill_per_sec=1000)
    rl.check("u")
    time.sleep(0.05)  # would be 50 tokens without the cap
    assert rl.check("u").remaining == 2


def test_cost_greater_than_one(r):
    rl = TokenBucketLimiter(r, capacity=10, refill_per_sec=0.001)
    assert rl.check("u", cost=7).allowed
    assert not rl.check("u", cost=4).allowed
    assert rl.check("u", cost=3).allowed


def test_keys_are_isolated(r):
    rl = TokenBucketLimiter(r, capacity=1, refill_per_sec=0.001)
    assert rl.check("alice").allowed
    assert not rl.check("alice").allowed
    assert rl.check("bob").allowed


def test_idle_keys_expire(r):
    rl = TokenBucketLimiter(r, capacity=10, refill_per_sec=10)
    rl.check("u")
    ttl_ms = r.pttl("rl:tb:u")
    assert 0 < ttl_ms <= 2000


@pytest.mark.parametrize("capacity,rate", [(0, 1), (1, 0), (-1, 1)])
def test_rejects_invalid_config(r, capacity, rate):
    with pytest.raises(ValueError):
        TokenBucketLimiter(r, capacity=capacity, refill_per_sec=rate)
