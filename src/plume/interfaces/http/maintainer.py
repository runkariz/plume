"""Maintainer API: bearer-token auth, package upload, jobs, live events (SSE), publish, dump."""

import functools
import hmac
import json
from collections.abc import AsyncIterator, Callable
from typing import Annotated, Any

import anyio
from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

from plume.application.jobs.maintainer import MaintainerJobs, job_payload
from plume.application.ports.jobs import JobStatus
from plume.interfaces.http import schemas as s

# A stream of a job in one of these states ends once its events are drained (no `done` follows).
ENDED = {JobStatus.PUBLISHED, JobStatus.DISCARDED}
WAIT_SECONDS = 5.0  # max time one wait blocks (then disconnects and job state are rechecked)
KEEPALIVE_SECONDS = 15.0


def make_auth(tokens: tuple[str, ...]) -> Callable[..., str]:
    def require_maintainer(
        authorization: Annotated[str | None, Header()] = None,
    ) -> str:
        if not tokens:
            raise HTTPException(503, "maintainer API not configured (PLUME_MAINTAINER_TOKENS)")
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "missing bearer token", {"WWW-Authenticate": "Bearer"})
        if not any(hmac.compare_digest(token.encode(), t.encode()) for t in tokens):
            raise HTTPException(401, "invalid token", {"WWW-Authenticate": "Bearer"})
        return "maintainer"

    return require_maintainer


def _sse(seq: int, payload: dict[str, Any]) -> str:
    body = {**payload, "id": str(seq)}
    return f"id: {seq}\nevent: {payload.get('type', 'log')}\ndata: {json.dumps(body)}\n\n"


def maintainer_router(
    jobs: Callable[[], MaintainerJobs],
    tokens: tuple[str, ...],
    max_upload_bytes: int,
    generation: Callable[[], bool] | None = None,
) -> APIRouter:
    auth = make_auth(tokens)
    router = APIRouter(dependencies=[Depends(auth)], tags=["maintainer"])
    errors: dict[int | str, dict[str, Any]] = {
        401: {"model": s.ErrorBody},
        404: {"model": s.ErrorBody},
        409: {"model": s.ErrorBody},
    }

    @router.get("/v1/maintainer/me", response_model=s.Me, responses=errors)
    def me() -> s.Me:
        return s.Me(name="maintainer", generation=bool(generation and generation()))

    @router.post("/v1/packages", response_model=s.JobOut, status_code=201, responses=errors)
    async def upload(file: Annotated[UploadFile, File()]) -> dict[str, Any]:
        name = file.filename or ""
        if not name.lower().endswith(".zip"):
            raise HTTPException(415, "Only .zip packages are accepted")
        data = await file.read(max_upload_bytes + 1)
        if len(data) > max_upload_bytes:
            raise HTTPException(413, f"package larger than {max_upload_bytes} bytes")
        job = await anyio.to_thread.run_sync(lambda: jobs().upload(name, data))
        return job_payload(job)

    @router.get("/v1/jobs/{job_id}", response_model=s.JobOut, responses=errors)
    def get_job(job_id: str) -> dict[str, Any]:
        return job_payload(jobs().get(job_id))

    @router.post("/v1/jobs/{job_id}/review", response_model=s.JobOut, responses=errors)
    def review(job_id: str, body: s.ReviewRequest) -> dict[str, Any]:
        return job_payload(jobs().review(job_id, body.api_id, body.display_name, body.tag))

    @router.post("/v1/jobs/{job_id}/build", response_model=s.JobOut, responses=errors)
    def build(job_id: str) -> dict[str, Any]:
        return job_payload(jobs().start_build(job_id))

    @router.post("/v1/jobs/{job_id}/publish", response_model=s.JobOut, responses=errors)
    def publish(job_id: str) -> dict[str, Any]:
        return job_payload(jobs().publish(job_id))

    @router.post("/v1/jobs/{job_id}/discard", response_model=s.JobOut, responses=errors)
    def discard(job_id: str) -> dict[str, Any]:
        return job_payload(jobs().discard(job_id))

    @router.get(
        "/v1/jobs/{job_id}/dump",
        responses={**errors, 200: {"content": {"application/gzip": {}}}},
        response_class=Response,
    )
    def dump(job_id: str) -> Response:
        name, data = jobs().dump(job_id)
        return Response(
            content=data,
            media_type="application/gzip",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    @router.get(
        "/v1/jobs/{job_id}/events",
        responses={**errors, 200: {"content": {"text/event-stream": {}}}},
        response_class=StreamingResponse,
    )
    async def events(
        job_id: str,
        request: Request,
        last_event_id: Annotated[str | None, Header()] = None,
    ) -> StreamingResponse:
        """Server-sent events: `id:` per message, `event:` = log|step|progress|service|done.
        Resume with the Last-Event-ID header. The stream ends after `done`."""
        service = jobs()
        await anyio.to_thread.run_sync(lambda: service.get(job_id))  # 404 before streaming
        try:
            start = int(last_event_id) if last_event_id else 0
        except ValueError:
            start = 0

        async def stream() -> AsyncIterator[str]:
            seq = start
            idle = 0.0
            while True:
                batch = await anyio.to_thread.run_sync(
                    functools.partial(service.events_after, job_id, seq)
                )
                for n, payload in batch:
                    seq = n
                    yield _sse(n, payload)
                    if payload.get("type") == "done":
                        return
                if batch:
                    idle = 0.0
                    continue
                job = await anyio.to_thread.run_sync(functools.partial(service.get, job_id))
                if job.status in ENDED or await request.is_disconnected():
                    return
                # Wait for a NOTIFY (or the fallback poll) instead of sleeping in a loop.
                woke = await anyio.to_thread.run_sync(
                    functools.partial(service.wait_events, job_id, seq, WAIT_SECONDS)
                )
                idle = 0.0 if woke else idle + WAIT_SECONDS
                if idle >= KEEPALIVE_SECONDS:
                    idle = 0.0
                    yield ": keepalive\n\n"

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
