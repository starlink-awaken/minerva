"""Web middleware — input validation, rate limiting, error boundaries."""

from __future__ import annotations

import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class InputGuardMiddleware(BaseHTTPMiddleware):
    """Enforce input limits on all requests."""

    async def dispatch(self, request: Request, call_next):
        # Query string length limit
        if len(request.url.query) > 4096:
            return JSONResponse({"error": "Query string too long (>4KB)"}, status_code=414)
        # Body size limit
        if request.headers.get("content-length"):
            try:
                if int(request.headers["content-length"]) > 65536:
                    return JSONResponse({"error": "Body too large (>64KB)"}, status_code=413)
            except ValueError:
                pass
        # Query param value limits
        for key, value in request.query_params.items():
            if len(value) > 2048:
                return JSONResponse({"error": f"Parameter '{key}' too long (>2KB)"}, status_code=414)
        return await call_next(request)


class RateLimiter:
    """Simple in-memory token bucket rate limiter."""

    def __init__(self, max_requests: int = 30, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window = window_seconds
        self._buckets: dict[str, list[float]] = {}

    def acquire(self, key: str = "default") -> bool:
        now = time.monotonic()
        if key not in self._buckets:
            self._buckets[key] = []
        cutoff = now - self.window
        self._buckets[key] = [t for t in self._buckets[key] if t > cutoff]
        if len(self._buckets[key]) >= self.max_requests:
            return False
        self._buckets[key].append(now)
        return True


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Simple API key authentication for protected endpoints.

    Set MINERVA_API_KEY env var to enable. If unset, all requests pass through.
    Clients pass key via X-API-Key header or ?api_key= query param.
    """

    def __init__(self, app, api_key: str | None = None):
        super().__init__(app)
        import os
        self.api_key = api_key or os.environ.get("MINERVA_API_KEY", "")

    async def dispatch(self, request, call_next):
        if not self.api_key:
            return await call_next(request)
        # Only protect mutation endpoints
        if request.url.path in ("/api/research", "/api/report/pdf"):
            key = request.headers.get("X-API-Key") or request.query_params.get("api_key", "")
            if key != self.api_key:
                return JSONResponse({"error": "Invalid or missing API key"}, status_code=401)
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply rate limiting to research endpoints."""

    def __init__(self, app, limiter: RateLimiter | None = None):
        super().__init__(app)
        self.limiter = limiter or RateLimiter()

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/research"):
            key = request.client.host if request.client else "unknown"
            if not self.limiter.acquire(key):
                return JSONResponse(
                    {"error": "Rate limit exceeded. Max 30 requests/min.", "retry_after": 60},
                    status_code=429,
                )
        return await call_next(request)
