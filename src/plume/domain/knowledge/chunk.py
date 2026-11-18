"""Chunks: the unit that is embedded and searched.

Policy (``CHUNKER_VERSION``): an endpoint or model is one chunk unless it is longer than
``max_chars``, and at most ``MAX_SCHEMA_CHUNKS`` (its head: title, path, description, then
fields in order; the full text stays on the document for reading); guides are split at
markdown headings, then by paragraphs to fit ``max_chars``.
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
# 9: endpoints sharing METHOD + path get "<id>@<package endpoint id>" document ids.
# 10: auth companion files (<scheme>.<suffix>.{sample,schema}.json) are no schemes.
# 11: field constraints (enum, min/max, default, format, pattern) in fields and text; an
# endpoint's fixed-version real path and its rate limit in its text.
# 12: endpoint text back to v10 (constraints, real path, rate limit stay off the embedded
# text; they are on fields, facts and payloads).
# 13: knowledge-export resource rules also go into their page's endpoints of that resource.
# 14: links in raw (text unchanged): units' endpointId/endpointIds both ways, auth schemes'
# endpoints per scope from requiredScopes.
# 15: knowledge-export rules with endpointIds go into those endpoints; unit-links.json adds
#     page/slug unit links (raw only).
# 16: an empty page fragment ("#") is no anchor (endpoint docAnchor, export items and rules).
# 17: trigger events read payloadSchemaRef / sampleRef (payload fields or model in the text);
#     events/*.payload.{schema,sample}.json are companions, not triggers.
# 18: manifest.json warnings kept on the app document (raw only; text unchanged).
# 19: endpoint and model chunks capped at MAX_SCHEMA_CHUNKS; loader lists at most 2000 fields
#     per schema (the deepest nesting level that fits).
# 20: bounded endpoint/model documents record the listed level in raw (find_fact: not listed).
# 21: knowledge-export rules find their page by a loose URL key (percent-decoded; without a
#     query when only one page has the path).
CHUNKER_VERSION = "21"
DEFAULT_MAX_CHARS = 6000
# Endpoint/model chunks embedded per document. The largest reference documents (Magento
# order endpoints) take 23; Shopware's entity graph took up to 14,000 before the field bound.
MAX_SCHEMA_CHUNKS = 24
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
    if document.kind in (DocumentKind.ENDPOINT, DocumentKind.MODEL):
        texts = texts[:MAX_SCHEMA_CHUNKS]
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
