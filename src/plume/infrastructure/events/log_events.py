import logging

from plume.application.ports.job_events import JobEvent

logger = logging.getLogger("plume.jobs")


class LoggingJobEvents:
    """Writes job events to the log (and keeps them, for the CLI summary)."""

    def __init__(self) -> None:
        self.events: list[JobEvent] = []

    def emit(self, event: JobEvent) -> None:
        self.events.append(event)
        logger.info(
            "job=%s step=%s status=%s source=%s %s %s",
            event.job_id,
            event.step,
            event.status.value,
            event.source,
            event.message,
            dict(event.data) if event.data else "",
        )
