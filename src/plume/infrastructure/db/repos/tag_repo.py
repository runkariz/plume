from sqlalchemy import Connection, Engine, text

from plume.domain.knowledge.api import ApiId
from plume.domain.knowledge.tag import Tag, TagName
from plume.domain.shared.ids import BuildId


def set_tag(conn: Connection, tag: Tag) -> None:
    conn.execute(
        text(
            """
            INSERT INTO tags (api_id, name, build_id) VALUES (:a, :n, :b)
            ON CONFLICT (api_id, name)
            DO UPDATE SET build_id = EXCLUDED.build_id, updated_at = now()
            """
        ),
        {"a": tag.api_id.value, "n": tag.name.value, "b": tag.build_id.value},
    )


class PostgresTagRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get(self, api_id: ApiId, name: TagName) -> Tag | None:
        with self._engine.connect() as conn:
            build_id = conn.execute(
                text("SELECT build_id FROM tags WHERE api_id = :a AND name = :n"),
                {"a": api_id.value, "n": name.value},
            ).scalar_one_or_none()
        return Tag(api_id, name, BuildId(build_id)) if build_id else None

    def set(self, tag: Tag) -> None:
        with self._engine.begin() as conn:
            set_tag(conn, tag)

    def list(self, api_id: ApiId) -> list[Tag]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("SELECT name, build_id FROM tags WHERE api_id = :a ORDER BY name"),
                {"a": api_id.value},
            ).all()
        return [Tag(api_id, TagName(r.name), BuildId(r.build_id)) for r in rows]
