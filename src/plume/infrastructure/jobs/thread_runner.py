import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

logger = logging.getLogger("plume.jobs")


class ThreadJobRunner:
    """Runs builds in a small in-process pool (one at a time by default)."""

    def __init__(self, workers: int = 1) -> None:
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="plume-job")

    def submit(self, fn: Callable[[], None]) -> None:
        future: Future[None] = self._pool.submit(fn)
        future.add_done_callback(
            lambda f: logger.error("job crashed", exc_info=f.exception()) if f.exception() else None
        )


class InlineJobRunner:
    """Runs the job immediately (tests, CLI)."""

    def submit(self, fn: Callable[[], None]) -> None:
        fn()
