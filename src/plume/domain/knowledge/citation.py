"""Citation: where a statement comes from (document, anchor/pointer, optional quote)."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Citation:
    doc_id: str
    source_url: str | None = None
    anchor: str | None = None
    quote: str | None = None
