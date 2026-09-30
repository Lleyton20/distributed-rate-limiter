"""Demo API protected by the distributed rate limiter.

Run several copies behind a load balancer (see docker-compose.yml): they all
share one limit because the state lives in Redis.
"""

from __future__ import annotations

import os
import socket

import redis
from fastapi import FastAPI

from .limiter import SlidingWindowLimiter, TokenBucketLimiter
from .middleware import RateLimitMiddleware

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ALGORITHM = os.getenv("RL_ALGORITHM", "token_bucket")
CAPACITY = int(os.getenv("RL_CAPACITY", "10"))
REFILL_PER_SEC = float(os.getenv("RL_REFILL_PER_SEC", "5"))
WINDOW_SEC = float(os.getenv("RL_WINDOW_SEC", "1"))
FAIL_OPEN = os.getenv("RL_FAIL_OPEN", "true").lower() == "true"

client = redis.Redis.from_url(
    REDIS_URL, socket_timeout=0.05, socket_connect_timeout=0.05, decode_responses=True
)

if ALGORITHM == "sliding_window":
    limiter = SlidingWindowLimiter(client, limit=CAPACITY, window_sec=WINDOW_SEC, fail_open=FAIL_OPEN)
else:
    limiter = TokenBucketLimiter(
        client, capacity=CAPACITY, refill_per_sec=REFILL_PER_SEC, fail_open=FAIL_OPEN
    )

app = FastAPI(title="Distributed Rate Limiter Demo")
app.add_middleware(RateLimitMiddleware, limiter=limiter)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/resource")
def resource() -> dict:
    # `instance` shows which replica served the request.
    return {"message": "ok", "instance": socket.gethostname()}
