"""Row <-> domain conversions shared by the Postgres repos."""

import json
from collections.abc import Sequence
from typing import Any

from plume.application.ports.embedder import Vector
from plume.domain.knowledge.document import Document, DocumentKind, FieldLocation, FieldSpec


def vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def parse_vector(text: str) -> Vector:
    return tuple(float(x) for x in text.strip("[]").split(",") if x)


def fields_to_json(fields: Sequence[FieldSpec]) -> str:
    return json.dumps(
        [
            {
                "name": f.name,
                "location": f.location.value,
                "type": f.type,
                "required": f.required,
                "description": f.description,
                "pointer": f.pointer,
            }
            for f in fields
        ]
    )


def fields_from_json(raw: Any) -> tuple[FieldSpec, ...]:
    items = json.loads(raw) if isinstance(raw, str) else raw
    return tuple(
        FieldSpec(
            name=i["name"],
            location=FieldLocation(i["location"]),
            type=i.get("type"),
            required=bool(i.get("required")),
            description=i.get("description"),
            pointer=i.get("pointer"),
        )
        for i in items
    )


def document_from_row(row: Any) -> Document:
    return Document(
        doc_id=row.doc_id,
        kind=DocumentKind(row.kind),
        title=row.title,
        text=row.text,
        source_url=row.source_url,
        anchor=row.anchor,
        resource=row.resource,
        method=row.method,
        path=row.path,
        deprecated=row.deprecated,
        complete=row.complete,
        fields=fields_from_json(row.fields),
        scopes=tuple(row.scopes or ()),
        source_id=row.source_id,
        shape=row.shape,
    )
