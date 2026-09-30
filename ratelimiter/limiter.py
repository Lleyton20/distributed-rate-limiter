"""Distributed rate limiters backed by Redis.

All state lives in Redis and every decision is a single Lua script, so any
number of app instances can share one limit without race conditions.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from importlib import resources
from typing import Protocol

import redis

log = logging.getLogger("ratelimiter")


def _load_script(name: str) -> str:
    return resources.files("ratelimiter.lua").joinpath(name).read_text()


@dataclass(frozen=True)
class Decision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_ms: int
    degraded: bool = False  # True when Redis was unreachable and the fail policy decided


class Limiter(Protocol):
    limit: int

    def check(self, key: str) -> Decision: ...


class _RedisLimiter:
    """Shared plumbing: script registration, key prefixing, fail-open/closed."""

    script_name: str

    def __init__(self, client: redis.Redis, *, prefix: str, fail_open: bool) -> None:
        self.client = client
        self.prefix = prefix
        self.fail_open = fail_open
        # register_script uses EVALSHA and transparently reloads the script
        # if Redis restarted and lost its script cache.
        self._script = client.register_script(_load_script(self.script_name))

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    def _on_redis_error(self, exc: Exception) -> Decision:
        # Availability trade-off: if the limiter's store is down, either let
        # traffic through (fail open) or reject it (fail closed).
        log.warning("rate limiter store unavailable (%s); fail_open=%s", exc, self.fail_open)
        return Decision(
            allowed=self.fail_open,
            limit=self.limit,
            remaining=0,
            retry_after_ms=0 if self.fail_open else 1000,
            degraded=True,
        )


class TokenBucketLimiter(_RedisLimiter):
    """Allows bursts up to `capacity`, then a steady `refill_per_sec`."""

    script_name = "token_bucket.lua"

    def __init__(
        self,
        client: redis.Redis,
        *,
        capacity: int,
        refill_per_sec: float,
        prefix: str = "rl:tb",
        fail_open: bool = True,
    ) -> None:
        if capacity <= 0 or refill_per_sec <= 0:
            raise ValueError("capacity and refill_per_sec must be positive")
        self.limit = capacity
        self.refill_per_sec = refill_per_sec
        super().__init__(client, prefix=prefix, fail_open=fail_open)

    def check(self, key: str, cost: int = 1) -> Decision:
        try:
            allowed, remaining, retry_ms = self._script(
                keys=[self._key(key)], args=[self.limit, self.refill_per_sec, cost]
            )
        except redis.RedisError as exc:
            return self._on_redis_error(exc)
        return Decision(
            allowed=bool(allowed),
            limit=self.limit,
            remaining=int(float(remaining)),
            retry_after_ms=int(retry_ms),
        )


class SlidingWindowLimiter(_RedisLimiter):
    """Exactly `limit` requests in any rolling `window_sec` period."""

    script_name = "sliding_window.lua"

    def __init__(
        self,
        client: redis.Redis,
        *,
        limit: int,
        window_sec: float,
        prefix: str = "rl:sw",
        fail_open: bool = True,
    ) -> None:
        if limit <= 0 or window_sec <= 0:
            raise ValueError("limit and window_sec must be positive")
        self.limit = limit
        self.window_us = int(window_sec * 1_000_000)
        super().__init__(client, prefix=prefix, fail_open=fail_open)

    def check(self, key: str) -> Decision:
        try:
            allowed, remaining, retry_ms = self._script(
                keys=[self._key(key)], args=[self.limit, self.window_us, uuid.uuid4().hex]
            )
        except redis.RedisError as exc:
            return self._on_redis_error(exc)
        return Decision(
            allowed=bool(allowed),
            limit=self.limit,
            remaining=int(remaining),
            retry_after_ms=int(retry_ms),
        )
