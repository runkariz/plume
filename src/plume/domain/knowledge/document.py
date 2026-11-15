"""Documents: what a build is made of before chunking.

One endpoint, one model, one guide page or one auth scheme is one document. Endpoint document ids
are built from the HTTP method and the path with the API-version segment replaced by
``{version}``, never from a producer's own id (those change when the vendor version rolls).
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from plume.domain.shared.errors import InvalidIdentifierError
from plume.domain.shared.hashing import ContentHash, content_hash

_DOC_ID = re.compile(r"^[a-z]+:[^\s]{1,400}$")
_DATE_VERSION = re.compile(r"^\d{4}-\d{2}(?:-\d{2})?$")
_SEMVER_VERSION = re.compile(r"^v\d+(?:\.\d+)*$")
_GENERIC_VERSIONS = frozenset({"latest", "unstable", "stable", "current"})
VERSION_PLACEHOLDER = "{version}"
HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})


class DocumentKind(StrEnum):
    ENDPOINT = "endpoint"
    MODEL = "model"
    GUIDE = "guide"
    AUTH = "auth"
    APP = "app"


class FieldLocation(StrEnum):
    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    BODY = "body"
    RESPONSE = "response"
    MODEL = "model"


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One documented field of an endpoint or model, as the source states it.

    ``pointer`` is a JSON pointer into the source document (the evidence), ``name`` is the dotted
    path (``product.variants[].sku``).
    """

    name: str
    location: FieldLocation
    type: str | None = None
    required: bool = False
    description: str | None = None
    pointer: str | None = None


def normalize_endpoint_path(path: str, known_versions: Iterable[str] = ()) -> str:
    """Replace the API-version segment of a path with ``{version}``.

    A segment counts as a version when it is one of ``known_versions``, a generic alias
    (``latest``, ``unstable``...), a date (``2026-10``) or ``v1``/``v2.1``.
    """
    known = frozenset(known_versions)
    query_free = path.split("?", 1)[0]
    segments = query_free.split("/")
    out = [
        VERSION_PLACEHOLDER
        if seg in known
        or seg in _GENERIC_VERSIONS
        or _DATE_VERSION.fullmatch(seg)
        or _SEMVER_VERSION.fullmatch(seg)
        else seg
        for seg in segments
    ]
    normalized = "/".join(out)
    return normalized if normalized.startswith("/") else "/" + normalized


def endpoint_doc_id(method: str, normalized_path: str) -> str:
    method_upper = method.upper()
    if method_upper not in HTTP_METHODS:
        raise InvalidIdentifierError(f"unknown HTTP method: {method!r}")
    return f"endpoint:{method_upper} {normalized_path}".replace(" ", "~")


def slug_doc_id(kind: DocumentKind, slug: str) -> str:
    return f"{kind.value}:{slug}"


@dataclass(frozen=True, slots=True)
class Document:
    doc_id: str
    kind: DocumentKind
    title: str
    text: str
    source_url: str | None = None
    anchor: str | None = None
    resource: str | None = None
    method: str | None = None
    path: str | None = None
    deprecated: bool = False
    complete: bool = True
    fields: tuple[FieldSpec, ...] = ()
    scopes: tuple[str, ...] = ()
    source_id: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not _DOC_ID.fullmatch(self.doc_id):
            raise InvalidIdentifierError(f"invalid document id: {self.doc_id!r}")
        if not self.doc_id.startswith(f"{self.kind.value}:"):
            raise InvalidIdentifierError(f"document id {self.doc_id!r} does not match {self.kind}")
        if not self.title.strip():
            raise ValueError(f"document {self.doc_id} has no title")

    @property
    def content_hash(self) -> ContentHash:
        """Hash of what is shown for this document (title, text, source)."""
        return content_hash(f"{self.title}\n{self.source_url or ''}\n{self.text}")
