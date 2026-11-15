from collections.abc import Sequence
from typing import Any

from sqlalchemy import Engine, text

from plume.domain.knowledge.citation import Citation
from plume.domain.knowledge.document import DocumentKind, FieldLocation
from plume.domain.knowledge.fact import Fact, FactKind
from plume.domain.shared.ids import BuildId

_COLUMNS = (
    "kind, owner_id, owner_kind, resource, name, location, type, required, complete, "
    "doc_id, source_url, anchor, quote"
)


def fact_from_row(row: Any) -> Fact:
    return Fact(
        kind=FactKind(row.kind),
        owner_id=row.owner_id,
        owner_kind=DocumentKind(row.owner_kind),
        name=row.name,
        evidence=Citation(
            doc_id=row.doc_id, source_url=row.source_url, anchor=row.anchor, quote=row.quote
        ),
        resource=row.resource,
        location=FieldLocation(row.location) if row.location else None,
        type=row.type,
        required=row.required,
        complete=row.complete,
    )


class PostgresFactIndex:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def replace_facts(self, build_id: BuildId, facts: Sequence[Fact]) -> None:
        with self._engine.begin() as conn:
            conn.execute(text("DELETE FROM facts WHERE build_id = :b"), {"b": build_id.value})
            if not facts:
                return
            conn.execute(
                text(
                    f"INSERT INTO facts (build_id, fact_id, {_COLUMNS}) VALUES "  # noqa: S608
                    "(:b, :id, :kind, :owner_id, :owner_kind, :resource, :name, :location, "
                    ":type, :required, :complete, :doc_id, :source_url, :anchor, :quote)"
                ),
                [
                    {
                        "b": build_id.value,
                        "id": f.fact_id,
                        "kind": f.kind.value,
                        "owner_id": f.owner_id,
                        "owner_kind": f.owner_kind.value,
                        "resource": f.resource,
                        "name": f.name,
                        "location": f.location.value if f.location else None,
                        "type": f.type,
                        "required": f.required,
                        "complete": f.complete,
                        "doc_id": f.evidence.doc_id,
                        "source_url": f.evidence.source_url,
                        "anchor": f.evidence.anchor,
                        "quote": f.evidence.quote,
                    }
                    for f in facts
                ],
            )

    def list_facts(self, build_id: BuildId) -> list[Fact]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM facts WHERE build_id = :b ORDER BY fact_id"  # noqa: S608
                ),
                {"b": build_id.value},
            ).all()
        return [fact_from_row(r) for r in rows]
