import json
from typing import Any

from sqlalchemy import Engine, text

from plume.application.ports.model_repo import ModelSession
from plume.domain.models.canonical_model import parse_draft
from plume.domain.models.snapshot import ModelSnapshot, PinnedInput, draft_json


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
    )


class PostgresModelRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def save_session(self, session: ModelSession) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO model_sessions (session_id, concept, inputs, created_at) "
                    "VALUES (:s, :c, CAST(:i AS jsonb), :t)"
                ),
                {
                    "s": session.session_id,
                    "c": session.concept,
                    "i": _inputs_json(session.inputs),
                    "t": session.created_at,
                },
            )

    def get_session(self, session_id: str) -> ModelSession | None:
        with self._engine.connect() as conn:
            r = conn.execute(
                text("SELECT * FROM model_sessions WHERE session_id = :s"), {"s": session_id}
            ).one_or_none()
        if r is None:
            return None
        return ModelSession(r.session_id, r.concept, _inputs(r.inputs), r.created_at)

    def save_snapshot(self, snapshot: ModelSnapshot) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO model_snapshots (snapshot_id, session_id, concept, apis, inputs, "
                    "model, citations_checked, prompt_version, created_at) VALUES "
                    "(:id, :s, :c, :apis, CAST(:i AS jsonb), CAST(:m AS jsonb), :n, :pv, :t) "
                    "ON CONFLICT (snapshot_id) DO NOTHING"
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
                },
            )
        return bool(result.rowcount)

    def get_snapshot(self, snapshot_id: str) -> ModelSnapshot | None:
        with self._engine.connect() as conn:
            r = conn.execute(
                text("SELECT * FROM model_snapshots WHERE snapshot_id = :s"), {"s": snapshot_id}
            ).one_or_none()
        return _snapshot(r) if r else None

    def list_snapshots(self, api: str | None = None, limit: int = 50) -> list[ModelSnapshot]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT * FROM model_snapshots "
                    "WHERE CAST(:a AS text) IS NULL OR :a = ANY(apis) "
                    "ORDER BY created_at DESC, snapshot_id LIMIT :n"
                ),
                {"a": api, "n": limit},
            ).all()
        return [_snapshot(r) for r in rows]
