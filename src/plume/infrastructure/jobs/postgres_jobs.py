import json
import logging
import time
from typing import Any

from sqlalchemy import Engine, text

from plume.application.ports.jobs import Job, JobStatus, JsonObj, StoredEvent

logger = logging.getLogger("plume.jobs")
CHANNEL = "plume_job_events"
_COLS = (
    "job_id, status, api_id, display_name, tag, package_path, package, diff, plan, eval, "
    "live_build, staged_build, error, created_at, updated_at"
)


def _j(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _from_row(r: Any) -> Job:
    return Job(
        job_id=r.job_id,
        status=JobStatus(r.status),
        package_path=r.package_path,
        package=_j(r.package),
        api_id=r.api_id,
        display_name=r.display_name,
        tag=r.tag,
        diff=_j(r.diff),
        plan=_j(r.plan),
        eval=_j(r.eval),
        live_build=r.live_build,
        staged_build=r.staged_build,
        error=r.error,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def _params(job: Job) -> dict[str, Any]:
    def dump(v: Any) -> str | None:
        return json.dumps(v) if v is not None else None

    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "api_id": job.api_id,
        "display_name": job.display_name,
        "tag": job.tag,
        "package_path": job.package_path,
        "package": json.dumps(dict(job.package)),
        "diff": dump(dict(job.diff) if job.diff else None),
        "plan": dump(dict(job.plan) if job.plan else None),
        "eval": dump(dict(job.eval) if job.eval else None),
        "live_build": job.live_build,
        "staged_build": job.staged_build,
        "error": job.error,
    }


_UPDATE = """
UPDATE jobs SET status = :status, api_id = :api_id, display_name = :display_name, tag = :tag,
    package_path = :package_path, package = CAST(:package AS jsonb),
    diff = CAST(:diff AS jsonb), plan = CAST(:plan AS jsonb), eval = CAST(:eval AS jsonb),
    live_build = :live_build, staged_build = :staged_build, error = :error, updated_at = now()
WHERE job_id = :job_id
"""


class PostgresJobRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(self, job: Job) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO jobs (job_id, status, api_id, display_name, tag, package_path, "
                    "package, diff, plan, eval, live_build, staged_build, error) VALUES "
                    "(:job_id, :status, :api_id, :display_name, :tag, :package_path, "
                    "CAST(:package AS jsonb), CAST(:diff AS jsonb), CAST(:plan AS jsonb), "
                    "CAST(:eval AS jsonb), :live_build, :staged_build, :error)"
                ),
                _params(job),
            )

    def get(self, job_id: str) -> Job | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT {_COLS} FROM jobs WHERE job_id = :j"),  # noqa: S608
                {"j": job_id},
            ).one_or_none()
        return _from_row(row) if row else None

    def save(self, job: Job) -> None:
        with self._engine.begin() as conn:
            conn.execute(text(_UPDATE), _params(job))

    def compare_and_set(self, job_id: str, expected: set[JobStatus], new: Job) -> bool:
        with self._engine.begin() as conn:
            current = conn.execute(
                text("SELECT status FROM jobs WHERE job_id = :j FOR UPDATE"), {"j": job_id}
            ).scalar_one_or_none()
            if current is None or JobStatus(current) not in expected:
                return False
            conn.execute(text(_UPDATE), _params(new))
            return True

    def fail_interrupted(self, message: str) -> list[str]:
        with self._engine.begin() as conn:
            return list(
                conn.execute(
                    text(
                        "UPDATE jobs SET status = 'failed', error = :m, updated_at = now() "
                        "WHERE status = 'building' RETURNING job_id"
                    ),
                    {"m": message},
                ).scalars()
            )


class PostgresJobEventLog:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def append(self, job_id: str, payload: JsonObj) -> int:
        with self._engine.begin() as conn:
            seq = conn.execute(
                text(
                    "INSERT INTO job_events (job_id, payload) VALUES (:j, CAST(:p AS jsonb)) "
                    "RETURNING seq"
                ),
                {"j": job_id, "p": json.dumps(payload)},
            ).scalar_one()
            # Delivered at commit; SSE streams of this job wake up instead of polling.
            conn.execute(text("SELECT pg_notify(:c, :j)"), {"c": CHANNEL, "j": job_id})
        return int(seq)

    def wait(self, job_id: str, seq: int, timeout: float) -> bool:
        """LISTEN for this job's NOTIFY; falls back to a short sleep if listening fails."""
        try:
            with self._engine.connect() as conn:
                raw = conn.connection.driver_connection
                if raw is None or not hasattr(raw, "notifies"):
                    raise RuntimeError("driver without LISTEN support")
                raw.autocommit = True
                try:
                    raw.execute(f"LISTEN {CHANNEL}")
                    if self.after(job_id, seq, 1):  # appended before LISTEN took effect
                        return True
                    deadline = time.monotonic() + timeout
                    while (left := deadline - time.monotonic()) > 0:
                        for note in raw.notifies(timeout=left, stop_after=1):
                            if note.payload == job_id:
                                return True
                    return False
                finally:
                    raw.execute(f"UNLISTEN {CHANNEL}")
                    raw.autocommit = False
        except Exception:
            logger.warning("LISTEN failed; polling job events", exc_info=True)
            time.sleep(min(timeout, 0.25))
            return True

    def after(self, job_id: str, seq: int, limit: int = 500) -> list[StoredEvent]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT seq, payload FROM job_events WHERE job_id = :j AND seq > :s "
                    "ORDER BY seq LIMIT :n"
                ),
                {"j": job_id, "s": seq, "n": limit},
            ).all()
        return [StoredEvent(int(r.seq), _j(r.payload)) for r in rows]
