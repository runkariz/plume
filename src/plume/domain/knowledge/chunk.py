"""Chunks: the unit that is embedded and searched.

Policy (``CHUNKER_VERSION``): an endpoint or model is one chunk unless it is longer than
``max_chars``; guides are split at markdown headings, then by paragraphs to fit ``max_chars``.
Chunk ids are ``<doc id>#<ordinal>``. Changing the policy means bumping ``CHUNKER_VERSION``,
which tells the diff to treat everything as re-chunked.
"""

import itertools
import re
from dataclasses import dataclass

from plume.domain.knowledge.document import Document, DocumentKind
from plume.domain.shared.hashing import ContentHash, content_hash

# Bump when chunking OR the package reader changes what documents contain (it is part of
# the build id, so a reload builds anew; unchanged chunks reuse cached vectors).
# 5: documents with unresolved include tags are flagged (incomplete + note) at load.
# 6: the reader follows $ref to sibling schema files and #/$defs (model -> item model fields).
# 7: knowledge-export page guides record their endpoints (search keeps one next to the page).
# 8: models record the operations whose response names them (raw x-plume-returned-by).
CHUNKER_VERSION = "8"
DEFAULT_MAX_CHARS = 6000
_HEADING = re.compile(r"^#{1,3} ", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_id: str
    doc_id: str
    ordinal: int
    heading: str
    text: str

    @property
    def embed_text(self) -> str:
        """What the embedding model sees."""
        return f"{self.heading}\n\n{self.text}" if self.heading else self.text

    @property
    def embed_hash(self) -> ContentHash:
        """Decides re-embedding: equal embed hashes reuse a cached vector."""
        return content_hash(self.embed_text)

    @property
    def content_hash(self) -> ContentHash:
        """Decides whether a chunk changed between builds."""
        return content_hash(f"{self.doc_id}\n{self.heading}\n{self.text}")


def _split_sections(text: str) -> list[str]:
    starts = [m.start() for m in _HEADING.finditer(text)]
    if not starts or starts[0] != 0:
        starts = [0, *starts]
    bounds = [*starts, len(text)]
    return [text[a:b].strip() for a, b in itertools.pairwise(bounds)]


def _split_to_size(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    current = ""
    for raw in text.split("\n\n"):
        paragraph = raw
        while len(paragraph) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(paragraph[:max_chars])
            paragraph = paragraph[max_chars:]
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > max_chars:
            pieces.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def chunk_document(document: Document, max_chars: int = DEFAULT_MAX_CHARS) -> list[Chunk]:
    if max_chars < 200:
        raise ValueError("max_chars must be at least 200")
    if document.kind in (DocumentKind.GUIDE, DocumentKind.AUTH, DocumentKind.APP):
        sections = [s for s in _split_sections(document.text) if s]
    else:
        sections = [document.text.strip()]
    texts = [piece for section in sections for piece in _split_to_size(section, max_chars) if piece]
    if not texts:
        texts = [document.title]
    return [
        Chunk(
            chunk_id=f"{document.doc_id}#{ordinal}",
            doc_id=document.doc_id,
            ordinal=ordinal,
            heading=document.title,
            text=text,
        )
        for ordinal, text in enumerate(texts)
    ]
