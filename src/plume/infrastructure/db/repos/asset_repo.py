from collections.abc import Sequence
from typing import Any

from sqlalchemy import Connection, Engine, text

from plume.domain.knowledge.asset import Asset
from plume.domain.shared.ids import BuildId


def put_assets(conn: Connection, build_id: BuildId, assets: Sequence[Asset]) -> None:
    for a in assets:
        conn.execute(
            text(
                "INSERT INTO build_assets (build_id, name, content_type, data, sha256, source) "
                "VALUES (:b, :n, :c, :d, :h, :s) ON CONFLICT (build_id, name) DO UPDATE SET "
                "content_type = EXCLUDED.content_type, data = EXCLUDED.data, "
                "sha256 = EXCLUDED.sha256, source = EXCLUDED.source"
            ),
            {
                "b": build_id.value,
                "n": a.name,
                "c": a.content_type,
                "d": a.data,
                "h": a.sha256,
                "s": a.source,
            },
        )


def _asset(r: Any) -> Asset:
    return Asset(r.name, r.content_type, bytes(r.data), r.source)


class PostgresAssetRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def put(self, build_id: BuildId, assets: Sequence[Asset]) -> None:
        with self._engine.begin() as conn:
            put_assets(conn, build_id, assets)

    def get(self, build_id: BuildId, name: str) -> Asset | None:
        with self._engine.connect() as conn:
            r = conn.execute(
                text("SELECT * FROM build_assets WHERE build_id = :b AND name = :n"),
                {"b": build_id.value, "n": name},
            ).one_or_none()
        return _asset(r) if r else None

    def list(self, build_id: BuildId) -> list[Asset]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM build_assets WHERE build_id = :b ORDER BY name"),
                {"b": build_id.value},
            ).all()
        return [_asset(r) for r in rows]
