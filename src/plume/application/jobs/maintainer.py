"""Maintainer jobs: upload -> review -> build (staged) -> publish | discard.

The wizard flow of the web UI and the maintainer API. Builds run through the same
``BuildPipeline`` as ``plume load``, but stage the build (no tag); publishing moves the tag
and is refused when the quality gate failed.
"""

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from plume.application.errors import (
    ApplicationError,
    GateFailedError,
    NotFoundError,
    SourcePackageError,
)
from plume.application.jobs.build_pipeline import BuildPipeline
from plume.application.knowledge.export_dump import ExportDump
from plume.application.knowledge.tag_build import TagBuild
from plume.application.ports.build_repo import BuildRepo
from plume.application.ports.embedder import Embedder
from plume.application.ports.eval_repo import EvalRepo
from plume.application.ports.job_events import EventStatus, JobEvent
from plume.application.ports.jobs import (
    Job,
    JobEventLog,
    JobRepo,
    JobRunner,
    JobStatus,
    JsonObj,
    PackageStorage,
)
from plume.application.ports.package_source import PackageSource, SourcePackage
from plume.application.ports.tag_repo import TagRepo
from plume.application.ports.vector_index import VectorIndex
from plume.domain.eval.metrics import EvalMetrics
from plume.domain.knowledge.api import ApiId
from plume.domain.knowledge.chunk import chunk_document
from plume.domain.knowledge.diff import diff_items
from plume.domain.knowledge.tag import TagName
from plume.domain.shared.errors import InvalidIdentifierError
from plume.domain.shared.ids import BuildId

logger = logging.getLogger("plume.jobs")
DIFF_ITEMS_SHOWN = 200
USD_PER_MILLION_TOKENS = 0.15  # gemini-embedding-001 list price; an estimate only


class JobStateError(ApplicationError):
    code = "invalid_state"


# Pipeline step -> wizard step key (web STEP_KEYS: validate chunk diff embed store evaluate).
_STEP_KEYS = {
    "import": "validate",
    "chunk": "chunk",
    "embed": "embed",
    "facts": "store",
    "seal": "store",
    "evaluate": "evaluate",
}
_SOURCES = {"embedder": "gemini", "postgres": "postgres", "plume": "plume"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _check(key: str, title: str, detail: str, status: str) -> JsonObj:
    return {"key": key, "title": title, "detail": detail, "status": status}


def _package_info(
    filename: str, files: int, size: int, pkg: SourcePackage | None, error: str | None
) -> JsonObj:
    checks: list[JsonObj] = []
    contents = {"endpoints": 0, "models": 0, "guides": 0}
    suggested = {"apiId": "", "displayName": "", "tag": "latest"}
    if pkg is None:
        checks.append(_check("readable", "Package readable", error or "unreadable", "fail"))
    else:
        kinds = [d.kind.value for d in pkg.documents]
        contents = {
            "endpoints": kinds.count("endpoint"),
            "models": kinds.count("model"),
            "guides": kinds.count("guide"),
        }
        checks.append(
            _check(
                "contract",
                "Package contract",
                f"connector/package.json schemaVersion {pkg.contract_version or 'unknown'}",
                "ok" if pkg.contract_version else "warn",
            )
        )
        checks.append(
            _check(
                "endpoints",
                "Endpoints",
                f"{contents['endpoints']} endpoints, {contents['models']} models, "
                f"{contents['guides']} guides",
                "ok" if contents["endpoints"] else "fail",
            )
        )
        cat = pkg.api.category
        if cat is None:
            checks.append(_check("category", "Category", "no category in app.json", "warn"))
        else:
            low = cat.confidence is not None and cat.confidence < 0.5
            checks.append(
                _check(
                    "category",
                    "Category",
                    f"{cat.key} (confidence {cat.confidence})",
                    "warn" if low else "ok",
                )
            )
        checks.append(
            _check(
                "warnings",
                "Reader warnings",
                "; ".join(pkg.warnings) or "none",
                "warn" if pkg.warnings else "ok",
            )
        )
        suggested = {"apiId": pkg.api.api_id.value, "displayName": pkg.api.name, "tag": "latest"}
    return {
        "filename": filename,
        "sizeBytes": size,
        "files": files,
        "contents": contents,
        "validation": checks,
        "suggested": suggested,
    }


def _metric_values(m: EvalMetrics | None) -> dict[str, float | int]:
    """Flat metric values; per-source search metrics as ``<source>.<metric>``."""
    if m is None:
        return {}
    out: dict[str, float | int] = {k: v for k, v in m.as_dict().items() if k != "by_source"}
    for src, sm in m.by_source:
        out.update({f"{src}.{k}": v for k, v in sm.as_dict().items()})
    return out


def _valid(job: Job) -> bool:
    return not any(c["status"] == "fail" for c in job.package.get("validation", []))


def _web_events(event: JobEvent) -> list[JsonObj]:
    """Pipeline event -> job event payloads (the API's event contract)."""
    t = _now()
    source = _SOURCES.get(event.source, "plume")
    key = _STEP_KEYS.get(event.step)
    out: list[JsonObj] = []
    if event.status is EventStatus.PROGRESS and event.step == "evaluate":
        return [{"type": "log", "t": t, "source": "plume", "message": event.message}]
    if event.status is EventStatus.PROGRESS and event.step == "embed":
        done = int(event.data.get("done") or 0)
        total = int(event.data.get("total") or 0)
        out.append({"type": "progress", "done": done, "total": total, "etaSeconds": None})
        return out
    if key is None:
        if event.message:
            out.append({"type": "log", "t": t, "source": source, "message": event.message})
        return out
    status = {
        EventStatus.STARTED: "running",
        EventStatus.DONE: "done",
        EventStatus.SKIPPED: "done",
        EventStatus.FAILED: "failed",
        EventStatus.PROGRESS: "running",
    }[event.status]
    if event.step == "facts" and status == "done":
        status = "running"  # store finishes with seal
    detail = event.message or f"{event.step} {event.status.value}"
    out.append({"type": "step", "key": key, "status": status, "detail": detail})
    out.append({"type": "log", "t": t, "source": source, "message": detail})
    return out


class EventLogSink:
    """``JobEvents`` adapter: writes pipeline events into the job's event log."""

    def __init__(self, log: JobEventLog, job_id: str) -> None:
        self._log = log
        self._job_id = job_id

    def emit(self, event: JobEvent) -> None:
        for payload in _web_events(event):
            self._log.append(self._job_id, payload)


class MaintainerJobs:
    def __init__(
        self,
        jobs: JobRepo,
        events: JobEventLog,
        storage: PackageStorage,
        source: PackageSource,
        builds: BuildRepo,
        tags: TagRepo,
        vectors: VectorIndex,
        evals: EvalRepo,
        embedder: Embedder,
        pipeline: Callable[[EventLogSink], BuildPipeline],
        tag_build: TagBuild,
        export: ExportDump,
        runner: JobRunner,
        max_chars: int = 6000,
    ) -> None:
        self._jobs = jobs
        self._events = events
        self._storage = storage
        self._source = source
        self._builds = builds
        self._tags = tags
        self._vectors = vectors
        self._evals = evals
        self._embedder = embedder
        self._pipeline = pipeline
        self._tag_build = tag_build
        self._export = export
        self._runner = runner
        self._max_chars = max_chars

    # -- queries ---------------------------------------------------------------------------------

    def get(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise NotFoundError(f"job {job_id} not found")
        return job

    def wait_events(self, job_id: str, seq: int, timeout: float) -> bool:
        return self._events.wait(job_id, seq, timeout)

    def events_after(self, job_id: str, seq: int) -> list[tuple[int, JsonObj]]:
        self.get(job_id)
        return [(e.seq, e.payload) for e in self._events.after(job_id, seq)]

    def recover(self) -> list[str]:
        """At startup: builds that were running when the server stopped are marked failed."""
        message = "interrupted: the server restarted during the build; build again"
        ids = self._jobs.fail_interrupted(message)
        for job_id in ids:
            self._events.append(job_id, {"type": "done", "status": "failed", "message": message})
        return ids

    # -- upload ----------------------------------------------------------------------------------

    def upload(self, filename: str, data: bytes) -> Job:
        if not filename.lower().endswith(".zip"):
            raise SourcePackageError("only .zip packages are accepted")
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        stored = self._storage.save(job_id, filename, data)
        pkg: SourcePackage | None = None
        error: str | None = None
        try:
            pkg = self._source.load(stored.path)
        except SourcePackageError as exc:
            error = str(exc)
        job = Job(
            job_id=job_id,
            status=JobStatus.UPLOADED,
            package_path=stored.path,
            package=_package_info(filename, stored.files, stored.size_bytes, pkg, error),
            api_id=pkg.api.api_id.value if pkg else None,
            display_name=pkg.api.name if pkg else None,
        )
        self._jobs.create(job)
        return self.get(job_id)

    # -- review ----------------------------------------------------------------------------------

    def review(self, job_id: str, api_id: str, display_name: str, tag: str) -> Job:
        job = self.get(job_id)
        if job.status not in (JobStatus.UPLOADED, JobStatus.REVIEWED):
            raise JobStateError(f"job {job_id} is {job.status}; review needs uploaded")
        if not _valid(job):
            raise JobStateError("the package failed validation; upload a fixed package")
        try:
            TagName(tag)
            api = ApiId(api_id)
        except InvalidIdentifierError as exc:
            raise SourcePackageError(str(exc)) from exc
        pkg = self._source.load(job.package_path)
        if api != pkg.api.api_id:
            raise SourcePackageError(
                f"the package is {pkg.api.api_id}; renaming an API is not supported yet"
            )
        chunks = [c for d in pkg.documents for c in chunk_document(d, self._max_chars)]
        staged_items = {c.chunk_id: c.content_hash for c in chunks}
        titles = {d.doc_id: d for d in pkg.documents}
        live_tag = self._tags.get(api, TagName(tag))
        live = self._builds.get(live_tag.build_id) if live_tag else None
        diff = diff_items(live.items if live else {}, staged_items)
        items: list[JsonObj] = []
        for change, ids in (
            ("new", diff.added),
            ("changed", diff.changed),
            ("removed", diff.removed),
        ):
            for cid in ids:
                doc_id = cid.split("#", 1)[0]
                d = titles.get(doc_id)
                items.append(
                    {
                        "change": change,
                        "kind": d.kind.value if d else doc_id.split(":", 1)[0],
                        "title": d.title if d else doc_id,
                        "method": d.method if d else None,
                        "path": d.path if d else None,
                        "note": cid,
                    }
                )
        hashes = {c.embed_hash.value: c for c in chunks}
        cached = self._vectors.cached(self._embedder.model, self._embedder.dims, hashes)
        to_embed = [c for h, c in hashes.items() if h not in cached]
        tokens = sum(len(c.embed_text) for c in to_embed) // 4
        plan = {
            "toEmbed": len(to_embed),
            "total": len(chunks),
            "model": self._embedder.model,
            "dimensions": self._embedder.dims,
            "estimatedTokens": f"{tokens:,}",
            "estimatedCost": f"${tokens / 1_000_000 * USD_PER_MILLION_TOKENS:.4f}",
        }
        diff_view = {
            "since": live.build_id.value if live else "",
            "counts": {
                "new": len(diff.added),
                "changed": len(diff.changed),
                "removed": len(diff.removed),
                "unchanged": diff.unchanged,
            },
            "items": items[:DIFF_ITEMS_SHOWN],
            "totalItems": len(items),
        }
        new = replace(
            job,
            status=JobStatus.REVIEWED,
            api_id=api.value,
            display_name=display_name.strip() or pkg.api.name,
            tag=tag,
            diff=diff_view,
            plan=plan,
            live_build=live.build_id.value if live else None,
        )
        self._jobs.save(new)
        return self.get(job_id)

    # -- build -----------------------------------------------------------------------------------

    def start_build(self, job_id: str) -> Job:
        job = self.get(job_id)
        building = replace(job, status=JobStatus.BUILDING, error=None)
        if not self._jobs.compare_and_set(job_id, {JobStatus.REVIEWED, JobStatus.FAILED}, building):
            raise JobStateError(f"job {job_id} is {job.status}; build needs reviewed")
        self._events.append(
            job_id,
            {"type": "service", "service": "postgres", "detail": "connected; staging a new build"},
        )
        self._events.append(
            job_id,
            {
                "type": "service",
                "service": "gemini",
                "detail": f"embedder {self._embedder.model} ({self._embedder.dims} dims)",
            },
        )
        self._runner.submit(lambda: self._run(job_id))
        return self.get(job_id)

    def _run(self, job_id: str) -> None:
        job = self.get(job_id)
        sink = EventLogSink(self._events, job_id)
        started = time.perf_counter()
        try:
            self._events.append(
                job_id,
                {"type": "step", "key": "diff", "status": "done", "detail": "computed at review"},
            )
            result = self._pipeline(sink).execute(
                job_id, job.package_path, tag=None, api_id=ApiId(job.api_id or "")
            )
        except Exception as exc:
            # Application errors are meant for users; anything else (database, driver) may carry
            # internals such as SQL, so it is logged and replaced by a generic message.
            if isinstance(exc, ApplicationError):
                message = str(exc)[:500]
            else:
                logger.exception("build of job %s failed", job_id)
                message = f"internal error ({type(exc).__name__}); see the server log"
            self._jobs.save(replace(self.get(job_id), status=JobStatus.FAILED, error=message))
            self._events.append(job_id, {"type": "done", "status": "failed", "message": message})
            return
        eval_view = self._eval_view(job, result.build_id)
        self._jobs.save(
            replace(
                self.get(job_id),
                status=JobStatus.STAGED,
                staged_build=result.build_id.value,
                eval=eval_view,
            )
        )
        took = round(time.perf_counter() - started, 1)
        self._events.append(
            job_id,
            {
                "type": "done",
                "status": "staged",
                "message": f"build {result.build_id} staged in {took}s"
                + (f"; {result.gate.message}" if result.gate else ""),
            },
        )

    def _eval_view(self, job: Job, staged: BuildId) -> JsonObj | None:
        record = self._evals.get(staged)
        if record is None:
            return None
        live = self._evals.get(BuildId(job.live_build)) if job.live_build else None
        rows: list[JsonObj] = []
        staged_m, live_m = (
            _metric_values(record.metrics),
            _metric_values(live.metrics if live else None),
        )
        keys: list[tuple[str, str, str]] = [
            ("recall_at_k", f"Recall@{record.metrics.k}", "up"),
            ("mrr", "MRR", "up"),
            ("top1_rate", "Top-1 hit rate", "up"),
            ("fact_accuracy", "Fact accuracy", "up"),
            ("missing_expected", "Missing expected docs", "down"),
        ]
        if len(record.metrics.by_source) > 1:
            for src, _ in record.metrics.by_source:
                keys += [
                    (f"{src}.recall_at_k", f"Recall@{record.metrics.k} ({src} questions)", "up"),
                    (f"{src}.mrr", f"MRR ({src} questions)", "up"),
                ]
        for key, label, better in keys:
            s_val = staged_m[key]
            l_val = live_m.get(key)
            delta = None if l_val is None else float(s_val) - float(l_val)
            tone = "neutral"
            if delta is not None and abs(delta) > 1e-9:
                good = delta > 0 if better == "up" else delta < 0
                tone = "ok" if good else "bad"
            rows.append(
                {
                    "key": key,
                    "label": label,
                    "live": "-" if l_val is None else str(l_val),
                    "staged": str(s_val),
                    "delta": "-" if delta is None else f"{delta:+.4g}",
                    "tone": tone,
                }
            )
        return {
            "gate": {"passed": record.passed, "message": record.message},
            "metrics": rows,
            "release": {
                "version": staged.value,
                "knowledgeFile": f"{job.api_id}/{staged.value}.plume.jsonl.gz",
                "notes": f"{job.display_name}: staged build {staged.value}",
            },
        }

    # -- publish / discard / dump ---------------------------------------------------------------

    def publish(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job.status is not JobStatus.STAGED or job.staged_build is None:
            raise JobStateError(f"job {job_id} is {job.status}; publish needs staged")
        if job.eval is not None and not job.eval["gate"]["passed"]:
            raise GateFailedError(job.eval["gate"]["message"])
        self._tag_build.execute(BuildId(job.staged_build), job.tag)
        self._jobs.save(replace(job, status=JobStatus.PUBLISHED, live_build=job.staged_build))
        self._events.append(
            job_id,
            {
                "type": "log",
                "t": _now(),
                "source": "plume",
                "message": f"published: {job.tag} -> {job.staged_build}",
            },
        )
        return self.get(job_id)

    def discard(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job.status in (JobStatus.BUILDING, JobStatus.PUBLISHED):
            raise JobStateError(f"job {job_id} is {job.status}; it cannot be discarded")
        self._jobs.save(replace(job, status=JobStatus.DISCARDED))
        return self.get(job_id)

    def dump(self, job_id: str) -> tuple[str, bytes]:
        job = self.get(job_id)
        if job.staged_build is None:
            raise JobStateError(f"job {job_id} has no staged build")
        data = self._export.bytes(BuildId(job.staged_build))
        return f"{job.api_id}-{job.staged_build}.plume.jsonl.gz", data


def job_payload(job: Job) -> dict[str, Any]:
    """The Job JSON of the maintainer API."""
    return {
        "id": job.job_id,
        "apiId": job.api_id or job.package.get("suggested", {}).get("apiId", ""),
        "displayName": job.display_name or job.package.get("suggested", {}).get("displayName", ""),
        "status": job.status.value,
        "tag": job.tag,
        "liveBuild": job.live_build,
        "stagedBuild": job.staged_build,
        "package": dict(job.package),
        "diff": dict(job.diff) if job.diff else None,
        "plan": dict(job.plan) if job.plan else None,
        "eval": dict(job.eval) if job.eval else None,
        "error": job.error,
    }
