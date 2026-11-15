"""A small in-process sliding-window rate limit per client address (reader API is public)."""

import hmac
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
        trusted_tokens: tuple[str, ...] = (),
        trusted_proxy_hops: int = 0,
    ) -> None:
        super().__init__(app)
        self._hops = max(0, trusted_proxy_hops)
        self._trusted = tuple(t.encode() for t in trusted_tokens)
        self._limit = per_minute
        self._clock = clock
        self._exempt = exempt
        self._hits: dict[str, deque[float]] = {}

    def _trusted_request(self, request: Request) -> bool:
        if not self._trusted:
            return False
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            return False
        value = token.encode()
        return any(hmac.compare_digest(value, t) for t in self._trusted)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if self._limit <= 0 or request.url.path in self._exempt or request.method == "OPTIONS":
            return await call_next(request)
        if self._trusted_request(request):
            return await call_next(request)  # authenticated maintainers are not rate limited
        key = client_address(request, self._hops)
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


def client_address(request: Request, trusted_proxy_hops: int = 0) -> str:
    """The client the limit counts. Without trusted proxies: the TCP peer. Behind N trusted
    proxies, the client is the Nth X-Forwarded-For entry from the right (Werkzeug ProxyFix
    x_for=N); entries further left could be written by the client. Fewer than N entries: the
    peer. Example: Traefik replaces XFF with the client's address and nginx appends Traefik's,
    so Plume sees "client, traefik"; with N=2 the limit counts "client"."""
    peer = request.client.host if request.client else "unknown"
    if trusted_proxy_hops <= 0:
        return peer
    hops = [
        h.strip()
        for v in request.headers.getlist("x-forwarded-for")
        for h in v.split(",")
        if h.strip()
    ]
    return hops[-trusted_proxy_hops] if len(hops) >= trusted_proxy_hops else peer


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Refuse a request whose declared body is larger than the limit before it is read."""

    def __init__(
        self,
        app: ASGIApp,
        max_bytes: int,
        default_bytes: int = 1024 * 1024,
        upload_paths: tuple[str, ...] = ("/v1/packages",),
    ) -> None:
        super().__init__(app)
        self._max = max_bytes
        self._default = default_bytes
        self._upload_paths = upload_paths

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method in ("POST", "PUT", "PATCH"):
            limit = self._max if request.url.path in self._upload_paths else self._default
            declared = request.headers.get("content-length")
            if declared is not None and (not declared.isdigit() or int(declared) > limit):
                return JSONResponse(
                    {
                        "error": "too_large",
                        "message": f"request body over {limit} bytes",
                        "detail": f"request body over {limit} bytes",
                    },
                    status_code=413,
                )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        return response
