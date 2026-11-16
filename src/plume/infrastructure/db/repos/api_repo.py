from typing import Any

from sqlalchemy import Connection, Engine, text

from plume.domain.knowledge.api import ApiId, ApiInfo, Category

_COLUMNS = (
    "api_id, name, summary, doc_link, icon_url, category_key, category_reason, "
    "category_confidence, category_bundle, versions, name_source"
)
_SELECT = (
    "SELECT a.api_id, a.name, a.summary, a.doc_link, a.icon_url, a.category_key, "
    "a.category_reason, a.category_confidence, a.category_bundle, a.versions, a.name_source, "
    "o.name AS name_override FROM apis a LEFT JOIN api_display_names o USING (api_id)"
)


def _from_row(row: Any) -> ApiInfo:
    category = None
    if row.category_key:
        category = Category(
            key=row.category_key,
            reason=row.category_reason,
            confidence=row.category_confidence,
            bundle_version=row.category_bundle,
        )
    return ApiInfo(
        api_id=ApiId(row.api_id),
        name=row.name,
        summary=row.summary,
        doc_link=row.doc_link,
        icon_url=row.icon_url,
        category=category,
        versions=tuple(row.versions or ()),
        name_source=row.name_source,
        name_override=row.name_override,
    )


def upsert_api(conn: Connection, info: ApiInfo) -> None:
    cat = info.category
    conn.execute(
        text(
            f"""
            INSERT INTO apis ({_COLUMNS})
            VALUES (:api_id, :name, :summary, :doc_link, :icon_url, :ck, :cr, :cc, :cb,
                    :versions, :name_source)
            ON CONFLICT (api_id) DO UPDATE SET
                name = EXCLUDED.name, summary = EXCLUDED.summary,
                doc_link = EXCLUDED.doc_link, icon_url = EXCLUDED.icon_url,
                category_key = EXCLUDED.category_key,
                category_reason = EXCLUDED.category_reason,
                category_confidence = EXCLUDED.category_confidence,
                category_bundle = EXCLUDED.category_bundle,
                versions = EXCLUDED.versions, name_source = EXCLUDED.name_source,
                updated_at = now()
            """  # noqa: S608 - column list is a constant
        ),
        {
            "api_id": info.api_id.value,
            "name": info.name,
            "summary": info.summary,
            "doc_link": info.doc_link,
            "icon_url": info.icon_url,
            "ck": cat.key if cat else None,
            "cr": cat.reason if cat else None,
            "cc": cat.confidence if cat else None,
            "cb": cat.bundle_version if cat else None,
            "versions": list(info.versions),
            "name_source": info.name_source,
        },
    )
    if info.name_override:  # a restored dump carries the override; a package load never does
        set_display_name(conn, info.api_id, info.name_override)


def set_display_name(conn: Connection, api_id: ApiId, name: str | None) -> None:
    if name is None:
        conn.execute(text("DELETE FROM api_display_names WHERE api_id = :a"), {"a": api_id.value})
        return
    conn.execute(
        text(
            """
            INSERT INTO api_display_names (api_id, name) VALUES (:a, :n)
            ON CONFLICT (api_id) DO UPDATE SET name = EXCLUDED.name, updated_at = now()
            """
        ),
        {"a": api_id.value, "n": name},
    )


class PostgresApiRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def upsert(self, info: ApiInfo) -> None:
        with self._engine.begin() as conn:
            upsert_api(conn, info)

    def get(self, api_id: ApiId) -> ApiInfo | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(f"{_SELECT} WHERE a.api_id = :a"),
                {"a": api_id.value},
            ).one_or_none()
        return _from_row(row) if row else None

    def list(self) -> list[ApiInfo]:
        with self._engine.connect() as conn:
            rows = conn.execute(text(f"{_SELECT} ORDER BY a.api_id")).all()
        return [_from_row(r) for r in rows]

    def set_display_name(self, api_id: ApiId, name: str | None) -> None:
        with self._engine.begin() as conn:
            set_display_name(conn, api_id, name)
