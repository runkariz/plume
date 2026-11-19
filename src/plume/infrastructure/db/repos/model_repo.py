import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, text

from plume.application.ports.model_repo import ModelJob, ModelSession
from plume.domain.models.canonical_model import parse_draft
from plume.domain.models.snapshot import ModelSnapshot, PinnedInput, Visibility, draft_json
from plume.domain.models.validation import Issue


def _issue(w: Issue) -> dict[str, Any]:
    return {"code": w.code, "field": w.field, "api": w.api, "message": w.message}


def _j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def _inputs(raw: Any) -> tuple[PinnedInput, ...]:
    return tuple(PinnedInput(i["api"], i["build"]) for i in _j(raw))


def _inputs_json(inputs: tuple[PinnedInput, ...]) -> str:
    return json.dumps([{"api": i.api, "build": i.build} for i in inputs])


def _snapshot(r: Any) -> ModelSnapshot:
    return ModelSnapshot(
        snapshot_id=r.snapshot_id,
        session_id=r.session_id,
        concept=r.concept,
        inputs=_inputs(r.inputs),
        draft=parse_draft(_j(r.model)),
        created_at=r.created_at,
        citations_checked=r.citations_checked,
        prompt_version=r.prompt_version,
        visibility=r.visibility,
        origin=r.origin,
        generator=r.generator,
        lineage_id="" if r.lineage_id == r.snapshot_id else r.lineage_id,
        version=r.version,
        based_on=r.based_on,
        content_key="" if r.content_key == r.snapshot_id else r.content_key,
        released_at=r.released_at,
        generator_usage=_j(r.generator_usage) if r.generator_usage is not None else None,
        warnings=tuple(
            Issue(w["code"], w["field"], w.get("api"), w["message"]) for w in _j(r.warnings) or []
        ),
        superseded_by=r.superseded_by,
        superseded_at=r.superseded_at,
        release_override=_j(r.release_override) if r.release_override is not None else None,
    )


class PostgresModelRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def save_session(self, session: ModelSession) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO model_sessions (session_id, concept, inputs, created_at, origin, "
                    "based_on, aliases) VALUES (:s, :c, CAST(:i AS jsonb), :t, :o, :b, "
                    "CAST(:a AS jsonb))"
                ),
                {
                    "s": session.session_id,
                    "c": session.concept,
                    "i": _inputs_json(session.inputs),
                    "t": session.created_at,
                    "o": session.origin,
                    "b": session.based_on,
                    "a": json.dumps(dict(session.aliases)),
                },
            )

    def get_session(self, session_id: str) -> ModelSession | None:
        with self._engine.connect() as conn:
            r = conn.execute(
                text("SELECT * FROM model_sessions WHERE session_id = :s"), {"s": session_id}
            ).one_or_none()
        if r is None:
            return None
        return ModelSession(
            r.session_id,
            r.concept,
            _inputs(r.inputs),
            r.created_at,
            r.origin,
            r.based_on,
            tuple(sorted(_j(r.aliases).items())),
        )

    def save_snapshot(self, snapshot: ModelSnapshot, owner_key_hash: str | None = None) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO model_snapshots (snapshot_id, session_id, concept, apis, inputs, "
                    "model, citations_checked, prompt_version, created_at, visibility, origin, "
                    "generator, lineage_id, version, based_on, content_key, released_at, "
                    "generator_usage, warnings) VALUES "
                    "(:id, :s, :c, :apis, CAST(:i AS jsonb), CAST(:m AS jsonb), :n, :pv, :t, :vis, "
                    ":o, :g, :l, :v, :b, :k, :r, CAST(:u AS jsonb), CAST(:w AS jsonb)) "
                    "ON CONFLICT DO NOTHING"
                ),
                {
                    "id": snapshot.snapshot_id,
                    "s": snapshot.session_id,
                    "c": snapshot.concept,
                    "apis": [i.api for i in snapshot.inputs],
                    "i": _inputs_json(snapshot.inputs),
                    "m": json.dumps(draft_json(snapshot.draft)),
                    "n": snapshot.citations_checked,
                    "pv": snapshot.prompt_version,
                    "t": snapshot.created_at,
                    "vis": snapshot.visibility,
                    "o": snapshot.origin,
                    "g": snapshot.generator,
                    "l": snapshot.lineage,
                    "v": snapshot.version,
                    "b": snapshot.based_on,
                    "k": snapshot.key,
                    "r": snapshot.released_at,
                    "w": json.dumps([_issue(w) for w in snapshot.warnings]),
                    "u": json.dumps(snapshot.generator_usage)
                    if snapshot.generator_usage is not None
                    else None,
                },
            )
            created = bool(result.rowcount)
            if created and snapshot.lineage == snapshot.snapshot_id:
                conn.execute(
                    text(
                        "INSERT INTO model_lineages (lineage_id, owner_key_hash, created_at) "
                        "VALUES (:l, :h, :t) ON CONFLICT DO NOTHING"
                    ),
                    {"l": snapshot.snapshot_id, "h": owner_key_hash, "t": snapshot.created_at},
                )
        return created

    def replace_owner_key(self, lineage_id: str, owner_key_hash: str) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(
                text(
                    "UPDATE model_lineages SET owner_key_hash = :h "
                    "WHERE lineage_id = :l AND owner_key_hash IS NOT NULL"
                ),
                {"l": lineage_id, "h": owner_key_hash},
            )
        return bool(result.rowcount)

    def get_snapshot(self, snapshot_id: str) -> ModelSnapshot | None:
        with self._engine.connect() as conn:
            r = conn.execute(
                text("SELECT * FROM model_snapshots WHERE snapshot_id = :s"), {"s": snapshot_id}
            ).one_or_none()
        return _snapshot(r) if r else None

    def list_snapshots(
        self,
        api: str | None = None,
        limit: int = 50,
        visibilities: Sequence[str] = (Visibility.OFFICIAL,),
    ) -> list[ModelSnapshot]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT * FROM model_snapshots "
                    "WHERE (CAST(:a AS text) IS NULL OR :a = ANY(apis)) "
                    "AND visibility = ANY(:vis) "
                    "ORDER BY created_at DESC, snapshot_id LIMIT :n"
                ),
                {"a": api, "n": limit, "vis": list(visibilities)},
            ).all()
        return [_snapshot(r) for r in rows]

    def lineage(self, lineage_id: str) -> list[ModelSnapshot]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM model_snapshots WHERE lineage_id = :l ORDER BY version"),
                {"l": lineage_id},
            ).all()
        return [_snapshot(r) for r in rows]

    def by_session(self, session_id: str) -> list[ModelSnapshot]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT * FROM model_snapshots WHERE session_id = :s "
                    "ORDER BY created_at DESC, version DESC"
                ),
                {"s": session_id},
            ).all()
        return [_snapshot(r) for r in rows]

    def set_visibility(
        self,
        snapshot_id: str,
        visibility: str,
        released_at: datetime | None,
        release_override: dict[str, Any] | None = None,
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE model_snapshots SET visibility = :v, released_at = :r, "
                    "release_override = COALESCE(CAST(:o AS jsonb), release_override) "
                    "WHERE snapshot_id = :s"
                ),
                {
                    "v": visibility,
                    "r": released_at,
                    "s": snapshot_id,
                    "o": json.dumps(release_override) if release_override else None,
                },
            )

    def supersede(self, snapshot_id: str, by: str, at: datetime) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(
                text(
                    "UPDATE model_snapshots SET visibility = 'superseded', superseded_by = :b, "
                    "superseded_at = :t WHERE snapshot_id = :s AND visibility = 'official'"
                ),
                {"s": snapshot_id, "b": by, "t": at},
            )
        return bool(result.rowcount)

    def lineages_for_owner(self, key_hashes: Sequence[str]) -> list[str]:
        if not key_hashes:
            return []
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT lineage_id FROM model_lineages WHERE owner_key_hash = ANY(:h) "
                    "ORDER BY created_at DESC"
                ),
                {"h": list(key_hashes)},
            ).all()
        return [r.lineage_id for r in rows]


def _job(r: Any) -> ModelJob:
    return ModelJob(
        job_id=r.job_id,
        status=r.status,
        apis=tuple(r.apis),
        concept=r.concept,
        created_at=r.created_at,
        updated_at=r.updated_at,
        session_id=r.session_id,
        round=r.round,
        max_rounds=r.max_rounds,
        snapshot_id=r.snapshot_id,
        error=r.error,
        generator=r.generator,
        usage=_j(r.usage) if r.usage is not None else None,
    )


class PostgresModelJobRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def _params(self, job: ModelJob) -> dict[str, Any]:
        return {
            "id": job.job_id,
            "st": job.status,
            "apis": list(job.apis),
            "c": job.concept,
            "s": job.session_id,
            "r": job.round,
            "mr": job.max_rounds,
            "snap": job.snapshot_id,
            "e": job.error,
            "g": job.generator,
            "ct": job.created_at,
            "ut": job.updated_at,
            "u": json.dumps(job.usage) if job.usage is not None else None,
        }

    def create(self, job: ModelJob) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO model_jobs (job_id, status, apis, concept, session_id, round, "
                    "max_rounds, snapshot_id, error, generator, created_at, updated_at, usage) "
                    "VALUES (:id, :st, :apis, :c, :s, :r, :mr, :snap, :e, :g, :ct, :ut, "
                    "CAST(:u AS jsonb))"
                ),
                self._params(job),
            )

    def get(self, job_id: str) -> ModelJob | None:
        with self._engine.connect() as conn:
            r = conn.execute(
                text("SELECT * FROM model_jobs WHERE job_id = :j"), {"j": job_id}
            ).one_or_none()
        return _job(r) if r else None

    def save(self, job: ModelJob) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE model_jobs SET status = :st, session_id = :s, round = :r, "
                    "max_rounds = :mr, snapshot_id = :snap, error = :e, generator = :g, "
                    "updated_at = :ut, usage = CAST(:u AS jsonb) WHERE job_id = :id"
                ),
                self._params(job),
            )

    def fail_interrupted(self, message: str) -> list[str]:
        with self._engine.begin() as conn:
            rows = conn.execute(
                text(
                    "UPDATE model_jobs SET status = 'failed', error = :m, updated_at = now() "
                    "WHERE status IN ('queued', 'running') RETURNING job_id"
                ),
                {"m": message},
            ).all()
        return [r.job_id for r in rows]
