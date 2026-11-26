"""Documents: what a build is made of before chunking.

One endpoint, one model, one guide page or one auth scheme is one document. Endpoint document ids
are built from the HTTP method and the path with the API-version segment replaced by
``{version}``, never from a producer's own id (those change when the vendor version rolls).
"""

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from plume.domain.shared.errors import InvalidIdentifierError
from plume.domain.shared.hashing import ContentHash, content_hash

_DOC_ID = re.compile(r"^[a-z]+:[^\s]{1,400}$")
_DATE_VERSION = re.compile(r"^\d{4}-\d{2}(?:-\d{2})?$")
_SEMVER_VERSION = re.compile(r"^v\d+(?:\.\d+)*$")
_GENERIC_VERSIONS = frozenset({"latest", "unstable", "stable", "current"})
VERSION_PLACEHOLDER = "{version}"
# A trigger document's raw key for its resolved payload (beside the verbatim event JSON).
TRIGGER_PAYLOAD_KEY = "_payload"
# An endpoint's/model's raw key: its field list stops at this nesting level (1 = top level)
# because the schema has more fields than Plume lists; deeper fields are not proven absent.
FIELDS_BOUNDED_KEY = "x-plume-fields-bounded"
# A document's raw key: rules in its text that are stated on several pages -> their URLs
# (sourceUrl first), the rules' citations.
RULE_SOURCES_KEY = "x-plume-rule-sources"
HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})


class DocumentKind(StrEnum):
    ENDPOINT = "endpoint"
    MODEL = "model"
    GUIDE = "guide"
    AUTH = "auth"
    TRIGGER = "trigger"
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
    # enum / minimum / maximum / default / format / pattern, verbatim from the schema
    # (JSON text, so the spec stays hashable); see ``constraint_dict``.
    constraints: str | None = None
    model_id: str | None = None  # the model document a $ref'd type is (model:orderlineitem)
    # the page that documents this field when it is not its document's (x-source-url): Meta's
    # custom_data properties live in POST /{pixel_id}/events but are documented on a page
    source_url: str | None = None

    @property
    def constraint_dict(self) -> dict[str, Any]:
        return constraint_dict(self.constraints)


CONSTRAINT_KEYS = ("enum", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
                   "minLength", "maxLength", "minItems", "maxItems", "default", "format",
                   "pattern")  # fmt: skip


def constraints_of(schema: Mapping[str, Any]) -> str | None:
    """The schema's value constraints as canonical JSON text (None when it states none)."""
    picked = {k: schema[k] for k in CONSTRAINT_KEYS if k in schema and schema[k] is not None}
    if not picked and isinstance(schema.get("items"), dict) and "enum" in schema["items"]:
        picked["enum"] = schema["items"]["enum"]  # an array of enum values
    return json.dumps(picked, sort_keys=True, ensure_ascii=False) if picked else None


def constraint_dict(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    value = json.loads(text)
    return value if isinstance(value, dict) else {}


_LABELS = (("minimum", "min"), ("exclusiveMinimum", "more than"), ("maximum", "max"),
           ("exclusiveMaximum", "less than"), ("minLength", "min length"),
           ("maxLength", "max length"), ("minItems", "min items"), ("maxItems", "max items"),
           ("default", "default"), ("format", "format"), ("pattern", "pattern"))  # fmt: skip


def constraint_text(text: str | None) -> str:
    """ "one of: ASC, DESC; max 100; default 100" (for document text and fact quotes)."""
    c = constraint_dict(text)
    bits = []
    if "enum" in c and isinstance(c["enum"], list):
        bits.append("one of: " + ", ".join(str(v) for v in c["enum"]))
    for key, label in _LABELS:
        if key in c:
            v = c[key]
            bits.append(f"{label} {json.dumps(v) if isinstance(v, dict | list) else v}")
    return "; ".join(bits)


def normalize_endpoint_path(path: str, known_versions: Iterable[str] = ()) -> str:
    """Replace the API-version segment of a path with ``{version}``.

    A segment counts as a version when it is one of ``known_versions``, a generic alias
    (``latest``, ``unstable``...), a date (``2026-10``) or ``v1``/``v2.1``. A generic alias
    AFTER a version segment is a literal resource name (WooCommerce
    /wp-json/wc/v3/data/currencies/current, Metro /openapi/v1/product-list/export/latest).
    """
    known = frozenset(known_versions)
    query_free = path.split("?", 1)[0]
    out: list[str] = []
    for seg in query_free.split("/"):
        explicit = seg in known or _DATE_VERSION.fullmatch(seg) or _SEMVER_VERSION.fullmatch(seg)
        alias = seg in _GENERIC_VERSIONS and VERSION_PLACEHOLDER not in out
        out.append(VERSION_PLACEHOLDER if explicit or alias else seg)
    normalized = "/".join(out)
    return normalized if normalized.startswith("/") else "/" + normalized


TEMPLATE_VAR = re.compile(r"\{\{\s*(?:req_vars|vars)\.([A-Za-z0-9_]+)\s*\}\}")
TEMPLATE_ANY = re.compile(r"\{\{[^}]*\}\}")


def url_path(url: str) -> str:
    """A package request URL as a path: `{{req_vars.id}}` -> `{id}`, host/env templates gone."""
    path = TEMPLATE_VAR.sub(r"{\1}", url)
    path = TEMPLATE_ANY.sub("", path)
    return re.sub(r"^[a-z]+://[^/]+", "", path)


def real_path(
    request: Mapping[str, Any] | None, normalized: str | None, rolling: bool = False
) -> str | None:
    """The package's own path when the operation FIXES its API version: request.json states
    `apiVersion`, the URL's version segment is it, and the API does not roll its versions
    (app.json apiVersioning.releaseCadence). Amazon `/vendor/orders/v1/...`, Woo
    `/wp-json/wc/v3/...`. None otherwise (Shopify: quarterly versions, keeps `{version}`)."""
    if rolling:
        return None
    url = (request or {}).get("url")
    fixed_version = (request or {}).get("apiVersion")
    if not isinstance(url, str) or not isinstance(fixed_version, str) or not normalized:
        return None
    path = url_path(url).split("?", 1)[0]
    path = path if path.startswith("/") else "/" + path
    if path == normalized:
        return None
    segs, norm = path.split("/"), normalized.split("/")
    if len(segs) != len(norm):
        return None
    fixed = [s for s, n in zip(segs, norm, strict=True) if n == VERSION_PLACEHOLDER and s != n]
    if not fixed or any(s != fixed_version for s in fixed):
        return None
    return path


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
    # Structural hash of a model's schema (title/description/examples ignored): equal shapes
    # are the same structure published under several names.
    shape: str | None = None
    # Tags the package gives the item (e.g. request.json tags[].name: "v3", "webhooks").
    tags: tuple[str, ...] = ()
    # The package's own path when the operation fixes its API version (see real_path).
    real_path: str | None = None
    # The endpoint's rate limit (bucket, cost, group) as JSON text (domain/knowledge/rate_limits).
    rate_limit: str | None = None
    # The package's source JSON for this item, verbatim (request.json, a model schema, an auth
    # scheme + its variables schema, a trigger event). Never derived.
    raw: Mapping[str, Any] | None = field(default=None, hash=False)

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
        base = f"{self.title}\n{self.source_url or ''}\n{self.text}"
        if self.tags or self.raw is not None:  # older documents keep their hash
            extra = json.dumps({"tags": list(self.tags), "raw": self.raw}, sort_keys=True)
            base = f"{base}\n{extra}"
        return content_hash(base)


# OAuth2 auth units: where the header name / prefix comes from (auth/<id>.json headerSource)
HEADER_SOURCE_VENDOR = "vendor"
HEADER_SOURCE_STANDARD = "standard:rfc6750"
STANDARD_HEADER_NOTE = "OAuth 2.0 standard (RFC 6750), not stated in the vendor's docs"


def header_format(name: str, prefix: str | None) -> str:
    """How the header is sent, e.g. "Authorization: Bearer <token>": one space after the
    prefix whether the package writes "Bearer" or "Bearer " (Core never builds the header from
    the prefix; it describes it)."""
    stripped = (prefix or "").strip()
    return f"{name}: {stripped} <token>" if stripped else f"{name}: <token>"


# the guide the loader makes from app.json environments (their base URLs), searchable
ENVIRONMENTS_DOC_ID = "guide:environments-and-base-urls"


# Knowledge topic documents: verbatim quotes, then a model-written summary under this heading
# (owner decision: accepted, always shown with its label, never cited as the vendor's words).
SUMMARY_HEADING = "## Summary of the quotes above"
SUMMARY_LABEL = "Summary of the quotes above (model-written)"
_SUMMARY_SECTION = re.compile(
    r"^## Summary of the quotes above[^\n]*\n.*?(?=^#{1,2} |\Z)", re.MULTILINE | re.DOTALL
)


def without_summaries(text: str) -> str:
    """The text without its model-written summary sections: what evidence may quote."""
    return _SUMMARY_SECTION.sub("", text)


# Producer field x-kariz-conflicts: the docs state different values for one limit. Plume shows
# every statement with its place and never picks one.
CONFLICTS_KEY = "x-kariz-conflicts"


@dataclass(frozen=True, slots=True)
class ConflictStatement:
    where: str  # "description" | "param:<name>" | "page:<url>"
    quote: str  # verbatim
    source_url: str | None = None
    is_example: bool = False


@dataclass(frozen=True, slots=True)
class Conflict:
    limit: str  # what is limited, in the docs' words
    statements: tuple[ConflictStatement, ...]
    # "condition": the docs make a field required in a stated case ("Required if item_id is
    # not provided"): one statement, not a disagreement; Plume says no more than that
    kind: str = "conflict"
    field: str | None = None  # the field it is about (a property's path, or a condition's)
    # where that field is, as the producer states it: "body" | "params" | "response:<status>"
    place: str | None = None

    @property
    def text(self) -> str:
        """\"The docs state different values for <limit>:\" (a condition: \"Condition on
        <field> (required only in this case):\", restating required-ness only; the quote is the
        evidence) and each quote with its place."""
        lines = [
            f"Condition on {self.field or self.limit} (required only in this case):"
            if self.kind == CONDITION
            else f"The docs state different values for {self.limit}:"
        ]
        for st in self.statements:
            mark = " (example)" if st.is_example else ""
            lines.append(f'- {st.where}{mark}: "{st.quote}"')
        return "\n".join(lines)


CONDITION = "condition"
_CONDITION_FIELD = re.compile(r"^field\s+(\S+)\s+required\b", re.IGNORECASE)


def conflicts_of(raw: object, fields: Sequence[str] = ()) -> tuple[Conflict, ...]:
    """The document's x-kariz-conflicts (raw JSON), skipping malformed items (no limit; fewer
    than two statements, or none for a condition). A condition's field comes from "field
    <name> required"; a property-level conflict lifted by the loader carries its field.
    ``fields``: the document's field names; a bare name that exactly one of them ends with
    becomes that path (retailer_id -> items[].retailer_id)."""
    items = raw.get(CONFLICTS_KEY) if isinstance(raw, Mapping) else None
    out: list[Conflict] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, Mapping) or not isinstance(item.get("limit"), str):
            continue
        statements = tuple(
            ConflictStatement(
                where=str(st.get("where") or ""),
                quote=str(st["quote"]),
                source_url=st.get("sourceUrl") if isinstance(st.get("sourceUrl"), str) else None,
                is_example=st.get("isExample") is True,
            )
            for st in item.get("statements") or []
            if isinstance(st, Mapping) and isinstance(st.get("quote"), str)
        )
        kind = CONDITION if item.get("kind") == CONDITION else "conflict"
        explicit = item.get("field") if isinstance(item.get("field"), str) else None
        field = explicit.strip() or None if explicit else None  # the producer's path wins
        if kind == CONDITION and field is None:  # fallback: "field <name> required"
            m = _CONDITION_FIELD.match(item["limit"].strip())
            field = m.group(1) if m else None
        if field and not explicit and "." not in field and field not in fields:
            nested = [f for f in fields if f.endswith((f".{field}", f"[].{field}"))]
            field = nested[0] if len(nested) == 1 else field
        where = item.get("where")
        place = where.strip() if isinstance(where, str) and where.strip() else None
        if len(statements) >= (1 if kind == CONDITION else 2):
            out.append(Conflict(item["limit"], statements, kind, field, place))
    return tuple(out)


def conflict_concerns(conflict: Conflict, name: str, request: bool = False) -> bool:
    """The conflict is about this field or parameter: a statement at param:<name>, or its field
    (a nested name matches by its last parts: items[].retailer_id and retailer_id).
    ``request``: the name is one a call sends, so a conflict the producer places in a
    response ("response:200") is not about it."""
    if request and (conflict.place or "").lower().startswith("response"):
        return False
    want = name.lower().replace("[]", "")
    if any(st.where.lower() == f"param:{name.lower()}" for st in conflict.statements):
        return True
    if conflict.field is None:
        return False
    field = conflict.field.lower().replace("[]", "")
    return want == field or want.endswith("." + field) or field.endswith("." + want)


def standard_header(scheme: Mapping[str, object]) -> bool:
    """headerSource standard:rfc6750 holds only for the standard's own header: Authorization
    with a Bearer prefix. On any other header (Shopify X-Shopify-Access-Token) it is treated as
    unknown: no standard label (the producer's mistake, reported to maintainers)."""
    name = scheme.get("headerName")
    prefix = scheme.get("headerPrefix")
    return (
        scheme.get("headerSource") == HEADER_SOURCE_STANDARD
        and isinstance(name, str)
        and name.strip().lower() == "authorization"
        and isinstance(prefix, str)
        and prefix.strip().lower() == "bearer"
    )


HEADER_SOURCE_MISUSED = "plume-header-source-not-standard"
