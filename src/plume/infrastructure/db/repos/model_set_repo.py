import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, text

from plume.application.ports.model_set_repo import SetSession
from plume.domain.models.model_set import ModelSetSnapshot, parse_set_draft, set_draft_json
from plume.domain.models.snapshot import PinnedInput, Visibility


def _j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def _inputs(raw: Any) -> tuple[PinnedInput, ...]:
    return tuple(PinnedInput(i["api"], i["build"]) for i in _j(raw))


def _inputs_json(inputs: tuple[PinnedInput, ...]) -> str:
    return json.dumps([{"api": i.api, "build": i.build} for i in inputs])


def _set(r: Any) -> ModelSetSnapshot:
    return ModelSetSnapshot(
        set_id=r.set_id,
        session_id=r.session_id,
        inputs=_inputs(r.inputs),
        draft=parse_set_draft(_j(r.body)),
        created_at=r.created_at,
        visibility=r.visibility,
        origin=r.origin,
        generator=r.generator,
        lineage_id="" if r.lineage_id == r.set_id else r.lineage_id,
        version=r.version,
        based_on=r.based_on,
        content_key="" if r.content_key == r.set_id else r.content_key,
        released_at=r.released_at,
        prompt_version=r.prompt_version,
    )


class PostgresModelSetRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def save_session(self, session: SetSession) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO model_set_sessions (session_id, inputs, concepts, "
                    "member_sessions, origin, based_on, created_at) "
                    "VALUES (:s, CAST(:i AS jsonb), :c, CAST(:m AS jsonb), :o, :b, :t)"
                ),
                {
                    "s": session.session_id,
                    "i": _inputs_json(session.inputs),
                    "c": list(session.concepts),
                    "m": json.dumps([list(p) for p in session.member_sessions]),
                    "o": session.origin,
                    "b": session.based_on,
                    "t": session.created_at,
                },
            )

    def get_session(self, session_id: str) -> SetSession | None:
        with self._engine.connect() as conn:
            r = conn.execute(
                text("SELECT * FROM model_set_sessions WHERE session_id = :s"), {"s": session_id}
            ).one_or_none()
        if r is None:
            return None
        return SetSession(
            r.session_id,
            _inputs(r.inputs),
            tuple(r.concepts),
            tuple((str(c), str(s)) for c, s in _j(r.member_sessions)),
            r.created_at,
            r.origin,
            r.based_on,
        )

    def save_set(self, snapshot: ModelSetSnapshot, owner_key_hash: str | None = None) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO model_sets (set_id, session_id, name, apis, inputs, body, "
                    "prompt_version, created_at, visibility, origin, generator, lineage_id, "
                    "version, based_on, content_key, released_at) VALUES (:id, :s, :n, :apis, "
                    "CAST(:i AS jsonb), CAST(:b AS jsonb), :pv, :t, :vis, :o, :g, :l, :v, :bo, "
                    ":k, :r) ON CONFLICT DO NOTHING"
                ),
                {
                    "id": snapshot.set_id,
                    "s": snapshot.session_id,
                    "n": snapshot.draft.name,
                    "apis": [i.api for i in snapshot.inputs],
                    "i": _inputs_json(snapshot.inputs),
                    "b": json.dumps(set_draft_json(snapshot.draft)),
                    "pv": snapshot.prompt_version,
                    "t": snapshot.created_at,
                    "vis": snapshot.visibility,
                    "o": snapshot.origin,
                    "g": snapshot.generator,
                    "l": snapshot.lineage,
                    "v": snapshot.version,
                    "bo": snapshot.based_on,
                    "k": snapshot.key,
                    "r": snapshot.released_at,
                },
            )
            created = bool(result.rowcount)
            if created:
                for m in snapshot.draft.members:
                    conn.execute(
                        text(
                            "INSERT INTO model_set_members (set_id, concept, snapshot_id) "
                            "VALUES (:s, :c, :m)"
                        ),
                        {"s": snapshot.set_id, "c": m.concept, "m": m.model_id},
                    )
                if snapshot.lineage == snapshot.set_id:
                    conn.execute(
                        text(
                            "INSERT INTO model_set_lineages (lineage_id, owner_key_hash, "
                            "created_at) VALUES (:l, :h, :t) ON CONFLICT DO NOTHING"
                        ),
                        {"l": snapshot.set_id, "h": owner_key_hash, "t": snapshot.created_at},
                    )
        return created

    def get_set(self, set_id: str) -> ModelSetSnapshot | None:
        with self._engine.connect() as conn:
            r = conn.execute(
                text("SELECT * FROM model_sets WHERE set_id = :s"), {"s": set_id}
            ).one_or_none()
        return _set(r) if r else None

    def list_sets(
        self,
        api: str | None = None,
        limit: int = 50,
        visibilities: Sequence[str] = (Visibility.OFFICIAL,),
    ) -> list[ModelSetSnapshot]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT * FROM model_sets WHERE (CAST(:a AS text) IS NULL OR :a = ANY(apis)) "
                    "AND visibility = ANY(:vis) ORDER BY created_at DESC, set_id LIMIT :n"
                ),
                {"a": api, "n": limit, "vis": list(visibilities)},
            ).all()
        return [_set(r) for r in rows]

    def lineage(self, lineage_id: str) -> list[ModelSetSnapshot]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM model_sets WHERE lineage_id = :l ORDER BY version"),
                {"l": lineage_id},
            ).all()
        return [_set(r) for r in rows]

    def by_session(self, session_id: str) -> list[ModelSetSnapshot]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT * FROM model_sets WHERE session_id = :s "
                    "ORDER BY created_at DESC, version DESC"
                ),
                {"s": session_id},
            ).all()
        return [_set(r) for r in rows]

    def set_visibility(self, set_id: str, visibility: str, released_at: datetime | None) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text("UPDATE model_sets SET visibility = :v, released_at = :r WHERE set_id = :s"),
                {"v": visibility, "r": released_at, "s": set_id},
            )

    def lineages_for_owner(self, key_hashes: Sequence[str]) -> list[str]:
        if not key_hashes:
            return []
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT lineage_id FROM model_set_lineages WHERE owner_key_hash = ANY(:h) "
                    "ORDER BY created_at DESC"
                ),
                {"h": list(key_hashes)},
            ).all()
        return [r.lineage_id for r in rows]

    def sets_using(self, snapshot_id: str) -> list[str]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("SELECT set_id FROM model_set_members WHERE snapshot_id = :m ORDER BY set_id"),
                {"m": snapshot_id},
            ).all()
        return [r.set_id for r in rows]
