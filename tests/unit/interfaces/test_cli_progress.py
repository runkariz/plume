"""plume load progress: steps as they start, embed done/total with rate and time left."""

from plume.application.ports.job_events import EventStatus, JobEvent
from plume.interfaces.cli.progress import LoadProgress


def _progress(done: int, total: int) -> JobEvent:
    return JobEvent("j", "embed", EventStatus.PROGRESS, data={"done": done, "total": total})


def test_embed_progress_is_throttled_and_ends_at_total() -> None:
    lines: list[str] = []
    now = [0.0]
    seen: list[JobEvent] = []

    class Inner:
        def emit(self, event: JobEvent) -> None:
            seen.append(event)

    p = LoadProgress(lines.append, Inner(), clock=lambda: now[0], every=10.0)
    p.emit(JobEvent("j", "chunk", EventStatus.STARTED))
    p.emit(JobEvent("j", "embed", EventStatus.STARTED))
    now[0] = 5.0
    p.emit(_progress(64, 1000))  # under 10 s since the start: not printed
    now[0] = 20.0
    p.emit(_progress(400, 1000))
    now[0] = 25.0
    p.emit(_progress(500, 1000))  # 5 s after the last line: not printed
    now[0] = 50.0
    p.emit(_progress(1000, 1000))  # the end is always printed
    assert lines == [
        "  chunk ...",
        "  embed ...",
        "  embed: 400/1000 chunks (40%), 20.0/s, ~0m30s left",
        "  embed: 1000/1000 chunks (100%), 20.0/s",
    ]
    assert len(seen) == 6  # everything still reaches the log


def test_a_failed_step_is_printed() -> None:
    lines: list[str] = []
    LoadProgress(lines.append).emit(JobEvent("j", "embed", EventStatus.FAILED, message="quota"))
    assert lines == ["  embed failed: quota"]
