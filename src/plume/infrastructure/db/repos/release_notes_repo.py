import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, text


def _j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


class PostgresReleaseNotesRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def save_meta(self, build_id: str, meta: Mapping[str, Any]) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO build_package_meta (build_id, meta) "
                    "VALUES (:b, CAST(:m AS jsonb)) "
                    "ON CONFLICT (build_id) DO UPDATE SET meta = EXCLUDED.meta"
                ),
                {"b": build_id, "m": json.dumps(dict(meta))},
            )

    def get_meta(self, build_id: str) -> dict[str, Any] | None:
        with self._engine.connect() as conn:
            v = conn.execute(
                text("SELECT meta FROM build_package_meta WHERE build_id = :b"), {"b": build_id}
            ).scalar()
        return _j(v) if v is not None else None

    def save(self, notes: Mapping[str, Any]) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO release_notes (to_build, api_id, from_build, computed_at, review, "
                    "body) VALUES (:t, :a, :f, :c, :r, CAST(:b AS jsonb)) ON CONFLICT (to_build) "
                    "DO UPDATE SET api_id = EXCLUDED.api_id, from_build = EXCLUDED.from_build, "
                    "computed_at = EXCLUDED.computed_at, review = EXCLUDED.review, "
                    "body = EXCLUDED.body"
                ),
                {
                    "t": notes["to"],
                    "a": notes["api"],
                    "f": notes["from"],
                    "c": datetime.fromisoformat(notes["computedAt"]),
                    "r": notes["review"],
                    "b": json.dumps(dict(notes), ensure_ascii=False),
                },
            )

    def get(self, to_build: str) -> dict[str, Any] | None:
        with self._engine.connect() as conn:
            v = conn.execute(
                text("SELECT body FROM release_notes WHERE to_build = :t"), {"t": to_build}
            ).scalar()
        return _j(v) if v is not None else None

    def card_notes(self, to_builds: list[str]) -> dict[str, dict[str, Any]]:
        """Projected in the database: the latest notes of 45 APIs are 5 MB of items, a card
        needs four fields of the visible ones."""
        if not to_builds:
            return {}
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT to_build, jsonb_build_object("
                    "'api', body->'api', 'to', body->'to', 'toDocsAsOf', body->'toDocsAsOf', "
                    "'items', coalesce((SELECT jsonb_agg(jsonb_build_object("
                    "'visibleToUsers', i->'visibleToUsers', 'class', i->'class', "
                    "'breaking', i->'breaking', 'wordingOnly', i->'wordingOnly', "
                    "'kind', i->'kind')) "
                    "FROM jsonb_array_elements(body->'items') i "
                    "WHERE i->'visibleToUsers' = 'true'::jsonb), '[]'::jsonb)) AS card "
                    "FROM release_notes WHERE to_build = ANY(:t)"
                ),
                {"t": list(to_builds)},
            ).all()
        return {r.to_build: _j(r.card) for r in rows}

    def for_api(self, api_id: str) -> list[dict[str, Any]]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT body FROM release_notes WHERE api_id = :a "
                    "ORDER BY computed_at DESC, to_build"
                ),
                {"a": api_id},
            ).all()
        return [_j(r.body) for r in rows]
