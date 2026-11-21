"""Capture of reader calls into the query log: best-effort and off the reader's path.

``record`` only puts the raw call on a bounded in-memory queue and returns (when the queue is
full the call is dropped and counted). A daemon thread redacts and builds the events, writes
them in batches, and purges events older than the retention once a day. Every error in that
work is swallowed and counted: the log can never slow or fail a reader call. The raw text is
only held in memory until it is redacted; it is never written.
"""

import logging
import queue
import threading
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from plume.application.ports.query_log import QueryLogRepo
from plume.domain.querylog.event import LOGGED_TOOLS, QueryEvent, build_event
from plume.domain.querylog.redact import STRICT, RedactionPolicy
from plume.domain.shared.clock import Clock

logger = logging.getLogger(__name__)
PURGE_EVERY = timedelta(days=1)


@dataclass(frozen=True, slots=True)
class _RawCall:
    tool: str
    surface: str
    args: dict[str, Any]
    payload: Any
    at: datetime
    latency_ms: int
    error_class: str | None
    client_name: str | None
    session_id: str | None


@dataclass
class RecorderStats:
    queued: int = 0
    written: int = 0
    dropped: int = 0  # the queue was full
    errors: int = 0  # building or writing failed (swallowed)
    purged: int = 0
    last_errors: list[str] = field(default_factory=list)


class QueryRecorder:
    def __init__(
        self,
        repo: QueryLogRepo,
        clock: Clock,
        *,
        enabled: bool,
        salt: bytes,
        policy: RedactionPolicy = STRICT,
        retention_days: int = 90,
        queue_size: int = 10_000,
        batch_size: int = 100,
        flush_seconds: float = 1.0,
    ) -> None:
        self._repo = repo
        self._clock = clock
        self._enabled = enabled
        self._salt = salt
        self._policy = policy
        self._retention = timedelta(days=max(1, retention_days))
        self._queue: queue.Queue[_RawCall] = queue.Queue(maxsize=queue_size)
        self._batch = batch_size
        self._flush = flush_seconds
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_purge: datetime | None = None
        self.stats = RecorderStats()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def record(
        self,
        tool: str,
        surface: str,
        args: Mapping[str, Any],
        payload: Any,
        latency_ms: int,
        error_class: str | None = None,
        client_name: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Queue one reader call (never raises, never blocks)."""
        if not self._enabled or tool not in LOGGED_TOOLS:
            return
        try:
            call = _RawCall(tool, surface, dict(args), payload, self._clock.now(), latency_ms,
                            error_class, client_name, session_id)  # fmt: skip
            self._queue.put_nowait(call)
            self.stats.queued += 1
            self._ensure_worker()
        except queue.Full:
            self.stats.dropped += 1
        except Exception as exc:
            self._error(exc)

    def flush(self, timeout: float = 5.0) -> None:
        """Wait until the queued calls are written (tests, shutdown)."""
        deadline = time.monotonic() + timeout
        while self._queue.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.01)

    def _ensure_worker(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._work, name="plume-query-log", daemon=True
                )
                self._thread.start()

    def _work(self) -> None:
        while True:
            calls = self._take()
            if calls:
                self._write(calls)
            self._maybe_purge()

    def _take(self) -> list[_RawCall]:
        calls: list[_RawCall] = []
        deadline = time.monotonic() + self._flush
        while len(calls) < self._batch:
            wait = deadline - time.monotonic()
            if wait <= 0:
                break
            try:
                calls.append(self._queue.get(timeout=wait))
            except queue.Empty:
                break
        return calls

    def _write(self, calls: list[_RawCall]) -> None:
        events: list[QueryEvent] = []
        for c in calls:
            try:
                events.append(self._event(c))
            except Exception as exc:
                self._error(exc)
        try:
            if events:
                self._repo.add_many(events)
                self.stats.written += len(events)
        except Exception as exc:
            self._error(exc)
        finally:
            for _ in calls:
                self._queue.task_done()

    def _event(self, c: _RawCall) -> QueryEvent:
        payload = c.payload
        if hasattr(payload, "model_dump"):  # an HTTP response model
            payload = payload.model_dump(mode="json")
        args = {k: (v.model_dump(mode="json") if hasattr(v, "model_dump") else v)
                for k, v in c.args.items()}  # fmt: skip
        flat: dict[str, Any] = {}
        for k, v in args.items():  # an HTTP body model's fields count as arguments
            if isinstance(v, dict) and k == "body":
                flat.update(v)
            else:
                flat[k] = v
        return build_event(
            c.tool, c.surface, flat, payload if isinstance(payload, Mapping) else None,
            at=c.at, latency_ms=c.latency_ms, error_class=c.error_class,
            client_name=c.client_name, session_id=c.session_id, salt=self._salt,
            policy=self._policy,
        )  # fmt: skip

    def _maybe_purge(self) -> None:
        now = self._clock.now()
        if self._last_purge is not None and now - self._last_purge < PURGE_EVERY:
            return
        self._last_purge = now
        try:
            self.stats.purged += self._repo.purge(now - self._retention)
        except Exception as exc:
            self._error(exc)

    def _error(self, exc: Exception) -> None:
        self.stats.errors += 1
        self.stats.last_errors = [*self.stats.last_errors[-4:], type(exc).__name__]
        logger.debug("query log: %s", type(exc).__name__)  # never the message (may hold text)


class PurgeQueryLog:
    def __init__(self, repo: QueryLogRepo, clock: Clock, retention_days: int) -> None:
        self._repo = repo
        self._clock = clock
        self._retention_days = retention_days

    def execute(self, older_than_days: int | None = None) -> int:
        days = older_than_days if older_than_days is not None else self._retention_days
        return self._repo.purge(self._clock.now() - timedelta(days=max(0, days)))


class ExportQueryLog:
    def __init__(self, repo: QueryLogRepo) -> None:
        self._repo = repo

    def execute(self, since: datetime | None, api: str | None) -> Iterator[dict[str, Any]]:
        for e in self._repo.export(since, api):
            yield e.as_dict()
