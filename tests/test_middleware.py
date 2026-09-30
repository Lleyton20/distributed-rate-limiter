from fastapi import FastAPI
from fastapi.testclient import TestClient

from ratelimiter import RateLimitMiddleware, TokenBucketLimiter


def make_client(r, capacity=2):
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limiter=TokenBucketLimiter(r, capacity=capacity, refill_per_sec=0.001))

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/api")
    def api():
        return {"ok": True}

    return TestClient(app)


def test_returns_429_with_headers_after_limit(r):
    c = make_client(r)
    first = c.get("/api")
    assert first.status_code == 200
    assert first.headers["X-RateLimit-Limit"] == "2"
    assert first.headers["X-RateLimit-Remaining"] == "1"
    assert c.get("/api").status_code == 200

    blocked = c.get("/api")
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1
    assert blocked.json()["error"] == "rate_limited"


def test_health_is_exempt(r):
    c = make_client(r, capacity=1)
    c.get("/api")
    assert all(c.get("/health").status_code == 200 for _ in range(5))


def test_api_keys_have_separate_limits(r):
    c = make_client(r, capacity=1)
    assert c.get("/api", headers={"x-api-key": "a"}).status_code == 200
    assert c.get("/api", headers={"x-api-key": "a"}).status_code == 429
    assert c.get("/api", headers={"x-api-key": "b"}).status_code == 200
