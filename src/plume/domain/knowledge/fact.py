"""Exact facts: an endpoint, a field or a required scope is documented in a build.

Vector search never proves absence; facts do. Every fact carries its evidence (a citation into
the build's documents) and whether the source was complete (``x-complete: false`` = partial).
"""

from dataclasses import dataclass
from enum import StrEnum

from plume.domain.knowledge.citation import Citation
from plume.domain.knowledge.document import Document, DocumentKind, FieldLocation
from plume.domain.knowledge.rate_limits import describe
from plume.domain.shared.hashing import content_hash


class FactKind(StrEnum):
    ENDPOINT = "endpoint"
    FIELD = "field"
    SCOPE = "scope"
    RATE_LIMIT = "rate_limit"


@dataclass(frozen=True, slots=True)
class Fact:
    kind: FactKind
    owner_id: str
    owner_kind: DocumentKind
    name: str
    evidence: Citation
    resource: str | None = None
    location: FieldLocation | None = None
    type: str | None = None
    required: bool = False
    complete: bool = True
    constraints: str | None = None  # JSON text, see FieldSpec.constraints

    @property
    def fact_id(self) -> str:
        key = f"{self.kind}\0{self.owner_id}\0{self.location or ''}\0{self.name}"
        return content_hash(key).short(24)


def facts_of(document: Document) -> list[Fact]:
    """Derive the exact facts a document states."""
    facts: list[Fact] = []
    base = Citation(doc_id=document.doc_id, source_url=document.source_url, anchor=document.anchor)
    if document.kind is DocumentKind.ENDPOINT and document.method and document.path:
        facts.append(
            Fact(
                kind=FactKind.ENDPOINT,
                owner_id=document.doc_id,
                owner_kind=document.kind,
                name=f"{document.method} {document.path}",
                evidence=base,
                resource=document.resource,
                complete=document.complete,
            )
        )
    for spec in document.fields:
        facts.append(
            Fact(
                kind=FactKind.FIELD,
                owner_id=document.doc_id,
                owner_kind=document.kind,
                name=spec.name,
                # a field documented on its own page cites that page (the pointer into the
                # package file would read as an anchor of the page: dropped)
                evidence=Citation(
                    doc_id=document.doc_id,
                    source_url=spec.source_url or document.source_url,
                    anchor=None if spec.source_url else spec.pointer,
                    quote=spec.description,
                ),
                resource=document.resource,
                location=spec.location,
                type=spec.type,
                required=spec.required,
                complete=document.complete,
                constraints=spec.constraints,
            )
        )
    if document.rate_limit:
        facts.append(
            Fact(
                kind=FactKind.RATE_LIMIT,
                owner_id=document.doc_id,
                owner_kind=document.kind,
                name="rate limit",
                evidence=Citation(
                    doc_id=document.doc_id,
                    source_url=document.source_url,
                    anchor=document.anchor,
                    quote=describe(document.rate_limit),
                ),
                resource=document.resource,
                complete=document.complete,
                constraints=document.rate_limit,
            )
        )
    for scope in document.scopes:
        facts.append(
            Fact(
                kind=FactKind.SCOPE,
                owner_id=document.doc_id,
                owner_kind=document.kind,
                name=scope,
                evidence=base,
                resource=document.resource,
                complete=document.complete,
            )
        )
    unique: dict[str, Fact] = {}
    for fact in facts:
        unique.setdefault(fact.fact_id, fact)
    return list(unique.values())
