"""Server-side model generation (maintainer): Plume builds the evidence pack, an LLM writes the
draft, and the SAME validation as for Claude's drafts decides. Refusals go back to the LLM with
the issues for a few rounds. The result is stored unreleased; a maintainer releases or discards
it. Progress is a job with events (SSE), like builds."""

import json
import logging
import re
import uuid
from dataclasses import replace
from typing import Any

from plume.application.errors import NotFoundError
from plume.application.models.concepts import concept_key
from plume.application.models.model_sets import ModelSets
from plume.application.models.sessions import (
    DRAFT_FORMAT,
    INSTRUCTIONS,
    ModelDraftRefusedError,
    ModelSessions,
)
from plume.application.ports.jobs import JobEventLog, JobRunner
from plume.application.ports.model_repo import ModelJob, ModelJobRepo
from plume.application.ports.model_writer import (
    ModelWriter,
    ModelWriterError,
    ModelWriterUnavailableError,
    Turn,
)
from plume.domain.models.snapshot import Origin
from plume.domain.models.validation import Issue
from plume.domain.shared.clock import Clock

logger = logging.getLogger("plume.models.generate")

MAX_ROUNDS = 3
EVIDENCE_BUDGET_CHARS = 200_000
ENDED = ("succeeded", "failed")

SYSTEM = (
    "You write canonical data models for Plume from API documentation evidence. You never invent "
    "knowledge: every mapping must be backed by the evidence you are given, with quotes copied "
    "verbatim. Reply with exactly ONE JSON object: the draft, in the draft_format shown. No prose, "
    "no code fences.\n\n" + INSTRUCTIONS
)


def _issues(issues: list[Issue]) -> list[dict[str, Any]]:
    return [{"code": i.code, "field": i.field, "api": i.api, "message": i.message} for i in issues]


def _add_usage(total: dict[str, int] | None, more: dict[str, int]) -> dict[str, int]:
    out = dict(total or {})
    for k, v in more.items():
        out[k] = out.get(k, 0) + v
    return out


def _camel_usage(usage: dict[str, int]) -> dict[str, int]:
    """{prompt, response, thoughts, total} -> {promptTokens, responseTokens, ...} for events."""
    return {f"{k}Tokens": v for k, v in usage.items()}


def parse_reply(text: str) -> Any:
    """The JSON object in an LLM reply (tolerates a code fence around it)."""
    body = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", body, re.DOTALL)
    if fence:
        body = fence.group(1)
    return json.loads(body)


class GenerateModels:
    def __init__(
        self,
        sessions: ModelSessions,
        writer: ModelWriter,
        jobs: ModelJobRepo,
        events: JobEventLog,
        runner: JobRunner,
        clock: Clock,
        max_rounds: int = MAX_ROUNDS,
        evidence_budget: int = EVIDENCE_BUDGET_CHARS,
    ) -> None:
        self._sessions = sessions
        self._writer = writer
        self._jobs = jobs
        self._events = events
        self._runner = runner
        self._clock = clock
        self._max_rounds = max(1, max_rounds)
        self._budget = evidence_budget

    def available(self) -> bool:
        return self._writer.available()

    def start(self, apis: list[str], concept: str) -> ModelJob:
        if not self._writer.available():
            raise ModelWriterUnavailableError(
                "server-side generation is not configured (PLUME_VERTEX_KEY_FILE)"
            )
        session = self._sessions.start(apis, concept, Origin.MAINTAINER)  # validates the input
        now = self._clock.now()
        job = ModelJob(
            job_id=f"mj-{uuid.uuid4().hex[:16]}",
            status="queued",
            apis=tuple(i.api for i in session.inputs),
            concept=session.concept,
            created_at=now,
            updated_at=now,
            session_id=session.session_id,
            max_rounds=self._max_rounds,
            generator=self._writer.name,
        )
        self._jobs.create(job)
        self._emit(job.job_id, "queued", jobId=job.job_id)
        self._runner.submit(lambda: self._run(job.job_id))
        return job

    def start_set(
        self,
        sets: ModelSets,
        apis: list[str],
        concepts: list[str],
        aliases: list[dict[str, Any]] | None = None,
    ) -> ModelJob:
        """Plume writes every member model, then PROPOSES relations from the documented
        candidates (confirmed: false: the maintainer decides them before release)."""
        if not self._writer.available():
            raise ModelWriterUnavailableError(
                "server-side generation is not configured (PLUME_VERTEX_KEY_FILE)"
            )
        session = sets.start(apis, concepts, Origin.MAINTAINER, aliases=aliases or ())
        now = self._clock.now()
        job = ModelJob(
            job_id=f"mj-{uuid.uuid4().hex[:16]}",
            status="queued",
            apis=tuple(i.api for i in session.inputs),
            concept=" + ".join(session.concepts),
            created_at=now,
            updated_at=now,
            session_id=session.session_id,
            max_rounds=self._max_rounds,
            generator=self._writer.name,
        )
        self._jobs.create(job)
        self._emit(job.job_id, "queued", jobId=job.job_id, kind="model_set")
        self._runner.submit(lambda: self._run_set(job.job_id, sets))
        return job

    def _run_set(self, job_id: str, sets: ModelSets) -> None:
        job = self.get(job_id)
        try:
            job = self._save(job, status="running")
            session = sets.get_session(job.session_id or "")
            self._emit(job_id, "started", apis=list(job.apis), concept=job.concept)
            members: dict[str, str] = {}
            for concept, member_session in session.member_sessions:
                sid = self._write_model(self.get(job_id), member_session, concept)
                if sid is None:
                    self._fail(self.get(job_id), "draft_refused", f"no valid {concept} model")
                    return
                members[concept] = sid
            relations, questions = sets.propose_relations(session.session_id, members)
            self._emit(
                job_id,
                "proposals",
                relations=[r["id"] for r in relations],
                openQuestions=len(questions),
            )
            draft = {
                "name": job.concept,
                "members": members,
                "relations": relations,
                "open_questions": questions,
                "aliases": [
                    {"concept": c, "names": {api: concept_key(n) for api, n in names}}
                    for c, names in session.aliases
                ],
            }
            try:
                result = sets.submit(
                    session.session_id, draft, maintainer=True, generator=self._writer.name
                )
            except ModelDraftRefusedError as exc:  # drop the refused proposals, keep the rest
                refused = {i.field for i in exc.issues}
                self._emit(job_id, "refused", round=0, issues=_issues(exc.issues), kind="set")
                draft["relations"] = [r for r in relations if r["id"] not in refused]
                draft["open_questions"] = questions + [
                    {"question": f"Relation {r['id']}: the proposal did not validate; decide it."}
                    for r in relations
                    if r["id"] in refused
                ]
                result = sets.submit(
                    session.session_id, draft, maintainer=True, generator=self._writer.name
                )
            set_id = result.snapshot.set_id
            self._save(self.get(job_id), status="succeeded", snapshot_id=set_id)
            usage = _camel_usage(self.get(job_id).usage or {})
            self._emit(job_id, "accepted", setId=set_id, kind="model_set", **usage)
            self._emit(job_id, "done", status="succeeded", snapshotId=None, setId=set_id, **usage)
        except (ModelWriterUnavailableError, ModelWriterError) as exc:
            self._fail(job, exc.code, str(exc))
        except Exception as exc:
            logger.exception("model set job %s failed", job_id)
            self._fail(job, "internal_error", type(exc).__name__)

    def get(self, job_id: str) -> ModelJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise NotFoundError(f"model job {job_id} not found")
        return job

    def events_after(self, job_id: str, seq: int) -> list[tuple[int, dict[str, Any]]]:
        return [(e.seq, e.payload) for e in self._events.after(job_id, seq)]

    def wait_events(self, job_id: str, seq: int, timeout: float) -> bool:
        return self._events.wait(job_id, seq, timeout)

    def recover(self) -> list[str]:
        ids = self._jobs.fail_interrupted("interrupted by a restart")
        for job_id in ids:
            self._emit(job_id, "failed", code="interrupted", message="interrupted by a restart")
            self._emit(job_id, "done", status="failed", snapshotId=None)
        return ids

    # -- the run ----------------------------------------------------------------------------------

    def _emit(self, job_id: str, event_type: str, **data: Any) -> None:
        self._events.append(job_id, {"type": event_type, **data})

    def _save(self, job: ModelJob, **changes: Any) -> ModelJob:
        job = replace(job, updated_at=self._clock.now(), **changes)
        self._jobs.save(job)
        return job

    def _evidence_pack(self, session_id: str) -> tuple[dict[str, Any], int, int]:
        context = self._sessions.context(session_id)
        pack: dict[str, Any] = {
            "session_id": session_id,
            "concept": context["concept"],
            "draft_format": DRAFT_FORMAT,
            "apis": [],
        }
        used = documents = fields = 0
        for api in context["apis"]:
            docs: list[dict[str, Any]] = []
            cursor: int | None = 0
            while cursor is not None and used < self._budget:
                page = self._sessions.evidence(session_id, api["api"], None, cursor)
                docs.extend(page["documents"])
                used += len(json.dumps(page["documents"], ensure_ascii=False))
                fields += int(page["returned"])
                cursor = page["next_cursor"]
            documents += len(docs)
            pack["apis"].append(
                {
                    "api": api["api"],
                    "documents": docs,
                    "truncated": cursor is not None,
                }
            )
        return pack, documents, fields

    def _write_model(
        self, job: ModelJob, session_id: str, concept: str | None = None
    ) -> str | None:
        """The LLM writes one model in a session (same validation, refusals fed back). Returns
        the stored snapshot id, or None after the last refused round."""
        tag = {"concept": concept} if concept else {}
        pack, documents, fields = self._evidence_pack(session_id)
        self._emit(job.job_id, "context", documents=documents, fields=fields, **tag)
        turns = [
            Turn(
                "user",
                "Write the canonical model from this evidence pack:\n"
                + json.dumps(pack, ensure_ascii=False),
            )
        ]
        spent: dict[str, int] | None = None  # tokens for this model (all its rounds)
        for n in range(1, self._max_rounds + 1):
            job = self._save(job, round=n)
            self._emit(job.job_id, "round", n=n, of=self._max_rounds, **tag)
            reply = self._writer.write(SYSTEM, turns)
            used = self._writer.last_usage
            if used:
                spent = _add_usage(spent, used)
                job = self._save(job, usage=_add_usage(job.usage, used))
                self._emit(job.job_id, "usage", round=n, **_camel_usage(used), **tag)
            turns.append(Turn("model", reply))
            try:
                draft = parse_reply(reply)
                result = self._sessions.submit(
                    session_id,
                    draft,
                    maintainer=True,
                    generator=self._writer.name,
                    generator_usage=spent,
                )
            except (json.JSONDecodeError, ModelDraftRefusedError) as exc:
                issues = (
                    exc.issues
                    if isinstance(exc, ModelDraftRefusedError)
                    else [Issue("INVALID_FORMAT", "", None, f"not JSON: {exc}")]
                )
                self._emit(job.job_id, "refused", round=n, issues=_issues(issues), **tag)
                turns.append(
                    Turn(
                        "user",
                        "Plume refused the draft:\n"
                        + json.dumps(_issues(issues), ensure_ascii=False)
                        + "\nFix those mappings (drop any you cannot support from the "
                        "evidence) and reply with the full corrected draft as one JSON object.",
                    )
                )
                continue
            sid = result.snapshot.snapshot_id
            if concept:
                self._emit(job.job_id, "member", concept=concept, snapshotId=sid, round=n)
            return sid
        return None

    def _run(self, job_id: str) -> None:
        job = self.get(job_id)
        try:
            job = self._save(job, status="running")
            self._emit(job_id, "started", apis=list(job.apis), concept=job.concept)
            sid = self._write_model(job, job.session_id or "")
            if sid is None:
                self._fail(
                    job, "draft_refused", f"no valid draft after {self._max_rounds} round(s)"
                )
                return
            self._save(self.get(job_id), status="succeeded", snapshot_id=sid)
            usage = _camel_usage(self.get(job_id).usage or {})
            self._emit(job_id, "accepted", snapshotId=sid, round=self.get(job_id).round, **usage)
            self._emit(job_id, "done", status="succeeded", snapshotId=sid, **usage)
        except (ModelWriterUnavailableError, ModelWriterError) as exc:
            self._fail(job, exc.code, str(exc))
        except Exception as exc:
            logger.exception("model job %s failed", job_id)
            self._fail(job, "internal_error", type(exc).__name__)

    def _fail(self, job: ModelJob, code: str, message: str) -> None:
        self._save(job, status="failed", error=f"{code}: {message}")
        self._emit(job.job_id, "failed", code=code, message=message)
        self._emit(job.job_id, "done", status="failed", snapshotId=None)
