from typing import Any

from sqlalchemy import Connection, Engine, text

from plume.domain.knowledge.api import ApiId, ApiInfo, Category

_COLUMNS = (
    "api_id, name, summary, doc_link, icon_url, category_key, category_reason, "
    "category_confidence, category_bundle, versions"
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
    )


def upsert_api(conn: Connection, info: ApiInfo) -> None:
    cat = info.category
    conn.execute(
        text(
            f"""
            INSERT INTO apis ({_COLUMNS})
            VALUES (:api_id, :name, :summary, :doc_link, :icon_url, :ck, :cr, :cc, :cb,
                    :versions)
            ON CONFLICT (api_id) DO UPDATE SET
                name = EXCLUDED.name, summary = EXCLUDED.summary,
                doc_link = EXCLUDED.doc_link, icon_url = EXCLUDED.icon_url,
                category_key = EXCLUDED.category_key,
                category_reason = EXCLUDED.category_reason,
                category_confidence = EXCLUDED.category_confidence,
                category_bundle = EXCLUDED.category_bundle,
                versions = EXCLUDED.versions, updated_at = now()
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
        },
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
                text(f"SELECT {_COLUMNS} FROM apis WHERE api_id = :a"),  # noqa: S608
                {"a": api_id.value},
            ).one_or_none()
        return _from_row(row) if row else None

    def list(self) -> list[ApiInfo]:
        with self._engine.connect() as conn:
            rows = conn.execute(text(f"SELECT {_COLUMNS} FROM apis ORDER BY api_id")).all()  # noqa: S608
        return [_from_row(r) for r in rows]
