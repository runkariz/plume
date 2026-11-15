"""A small in-process sliding-window rate limit per client address (reader API is public)."""

import time
from collections import deque
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        per_minute: int,
        clock: Callable[[], float] = time.monotonic,
        exempt: tuple[str, ...] = ("/health",),
    ) -> None:
        super().__init__(app)
        self._limit = per_minute
        self._clock = clock
        self._exempt = exempt
        self._hits: dict[str, deque[float]] = {}

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if self._limit <= 0 or request.url.path in self._exempt or request.method == "OPTIONS":
            return await call_next(request)
        key = request.client.host if request.client else "unknown"
        now = self._clock()
        window = self._hits.setdefault(key, deque())
        while window and now - window[0] >= 60:
            window.popleft()
        if len(window) >= self._limit:
            retry = max(1, int(60 - (now - window[0])))
            return JSONResponse(
                {"error": "rate_limited", "message": f"limit {self._limit}/min"},
                status_code=429,
                headers={"Retry-After": str(retry)},
            )
        window.append(now)
        if len(self._hits) > 10_000:  # forget idle clients
            for k in [k for k, v in self._hits.items() if not v or now - v[-1] >= 60]:
                del self._hits[k]
        return await call_next(request)
