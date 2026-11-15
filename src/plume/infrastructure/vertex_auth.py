"""How Plume authenticates to Vertex AI: an API key (express mode or a project URL), or
Application Default Credentials (Workload Identity on GKE, `gcloud auth application-default
login` locally) as a refreshed Bearer token. ADC needs a project: express-mode URLs take keys
only. Neither the key nor the token ever reaches a URL, a log line or an error message."""

import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)
REFRESH_MARGIN_S = 300  # refresh a token this long before it expires


class VertexAuthError(Exception):
    """ADC is not available (no credentials found) or the token cannot be refreshed."""


class TokenSource(Protocol):
    def token(self) -> str: ...

    def available(self) -> bool: ...


class AdcTokenSource:
    """google-auth Application Default Credentials, refreshed when close to expiry.
    ``loader`` returns ``(credentials, project)`` like ``google.auth.default`` (tests pass a
    fake); ``refresh`` refreshes credentials (default: google-auth's requests transport)."""

    def __init__(
        self,
        loader: Callable[[], tuple[Any, str | None]] | None = None,
        refresh: Callable[[Any], None] | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._loader = loader or _default_loader
        self._refresh = refresh or _default_refresh
        self._now = now
        self._lock = threading.Lock()
        self._credentials: Any = None
        self._error: str | None = None

    def _creds(self) -> Any:
        if self._credentials is None and self._error is None:
            try:
                self._credentials, _ = self._loader()
            except Exception as exc:
                self._error = type(exc).__name__
        if self._credentials is None:
            raise VertexAuthError(f"no Application Default Credentials ({self._error})")
        return self._credentials

    def available(self) -> bool:
        try:
            self._creds()
        except VertexAuthError:
            return False
        return True

    def token(self) -> str:
        with self._lock:
            creds = self._creds()
            expiry = getattr(creds, "expiry", None)
            left = (expiry.timestamp() - self._now()) if expiry is not None else -1
            if not getattr(creds, "token", None) or left < REFRESH_MARGIN_S:
                try:
                    self._refresh(creds)
                except Exception as exc:
                    raise VertexAuthError(
                        f"refreshing Application Default Credentials failed: {type(exc).__name__}"
                    ) from None
            token = getattr(creds, "token", None)
            if not token:
                raise VertexAuthError("Application Default Credentials returned no token")
            return str(token)


def _default_loader() -> tuple[Any, str | None]:
    import google.auth  # noqa: PLC0415 - only when ADC is used

    credentials, project = google.auth.default(scopes=list(SCOPES))
    return credentials, project


def _default_refresh(credentials: Any) -> None:
    from google.auth.transport.requests import Request  # noqa: PLC0415

    credentials.refresh(Request())


def auth_headers(key: str | None, tokens: TokenSource | None) -> dict[str, str]:
    """The request headers for Vertex: the key when there is one, else an ADC Bearer token."""
    if key:
        return {"x-goog-api-key": key}
    if tokens is not None:
        return {"Authorization": f"Bearer {tokens.token()}"}
    raise VertexAuthError("no Vertex key and no Application Default Credentials configured")


def vertex_host(location: str) -> str:
    return (
        "aiplatform.googleapis.com"
        if location == "global"
        else f"{location}-aiplatform.googleapis.com"
    )
