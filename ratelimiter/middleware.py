"""ASGI middleware that applies a limiter to every request."""

from __future__ import annotations

import math
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .limiter import Limiter


def default_identity(request: Request) -> str:
    """Limit per API key when present, otherwise per client IP."""
    api_key = request.headers.get("x-api-key")
    if api_key:
        return f"key:{api_key}"
    client = request.client.host if request.client else "unknown"
    return f"ip:{client}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        limiter: Limiter,
        identity: Callable[[Request], str] = default_identity,
        exempt_paths: frozenset[str] = frozenset({"/health"}),
    ) -> None:
        super().__init__(app)
        self.limiter = limiter
        self.identity = identity
        self.exempt_paths = exempt_paths

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in self.exempt_paths:
            return await call_next(request)

        decision = self.limiter.check(self.identity(request))
        headers = {
            "X-RateLimit-Limit": str(decision.limit),
            "X-RateLimit-Remaining": str(decision.remaining),
        }
        if decision.degraded:
            headers["X-RateLimit-Degraded"] = "true"

        if not decision.allowed:
            headers["Retry-After"] = str(max(1, math.ceil(decision.retry_after_ms / 1000)))
            return JSONResponse(
                {"error": "rate_limited", "retry_after_ms": decision.retry_after_ms},
                status_code=429,
                headers=headers,
            )

        response = await call_next(request)
        response.headers.update(headers)
        return response
