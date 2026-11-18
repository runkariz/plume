"""``plume load`` progress on stderr: each step as it starts, and the embedding as
``chunks embedded / total`` with rate and time left, so a long load is visible."""

import time
from collections.abc import Callable

from plume.application.ports.job_events import EventStatus, JobEvent, JobEvents

EVERY_SECONDS = 10.0  # embed progress at most this often (and always at the end)


class LoadProgress:
    def __init__(
        self,
        write: Callable[[str], None],
        inner: JobEvents | None = None,
        clock: Callable[[], float] = time.monotonic,
        every: float = EVERY_SECONDS,
    ) -> None:
        self._write = write
        self._inner = inner
        self._clock = clock
        self._every = every
        self._started: float | None = None
        self._last: float | None = None

    def emit(self, event: JobEvent) -> None:
        if self._inner is not None:
            self._inner.emit(event)
        if event.status is EventStatus.STARTED:
            self._write(f"  {event.step} ...")
            if event.step == "embed":
                self._started = self._last = self._clock()
        elif event.status is EventStatus.FAILED:
            self._write(f"  {event.step} failed: {event.message}")
        elif event.status is EventStatus.PROGRESS and event.step == "embed":
            self._embed(event)

    def _embed(self, event: JobEvent) -> None:
        done, total = event.data.get("done"), event.data.get("total")
        if not isinstance(done, int) or not isinstance(total, int) or total <= 0:
            return
        now = self._clock()
        if done < total and self._last is not None and now - self._last < self._every:
            return
        self._last = now
        elapsed = now - (self._started if self._started is not None else now)
        line = f"  embed: {done}/{total} chunks ({100 * done // total}%)"
        if elapsed > 0 and done:
            rate = done / elapsed
            line += f", {rate:.1f}/s"
            if done < total:
                line += f", ~{_duration((total - done) / rate)} left"
        self._write(line)


def _duration(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m" if hours else f"{minutes}m{secs:02d}s"
