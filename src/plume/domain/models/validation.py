"""The citation rule: every mapping must cite, and every citation must hold in the pinned builds.

Issue codes (stable; clients key on them):

- ``API_NOT_IN_SESSION``: a field maps an API that is not one of the session's APIs.
- ``MISSING_CITATION``: a mapping has no evidence.
- ``DOC_NOT_FOUND``: evidence cites a document that is not in that API's pinned build.
- ``QUOTE_NOT_FOUND``: the quoted text is not in the cited document.
- ``PATH_NOT_IN_FETCH``: the mapping names a fetch endpoint, and the path is not a field of that
  endpoint's response (a field of some model is not enough).
- ``SCALAR_FROM_OBJECT``: a scalar canonical field (string, number, date, money, ...) maps a path
  that is an object in the API; map one of its fields (the refusal lists them).
- ``ARRAY_FOR_SINGLE``: a scalar canonical field maps a list, without a cardinality /
  array-vs-single / split conversion.
- ``QUOTE_NOT_ON_FIELD``: the quote is in the document but not about the mapped field: when the
  cited document lists the field, the quote must come from that field's own entry (its line or
  description); otherwise the quote must name the field.
- ``FIELD_NOT_FOUND``: a source path is not a documented field of that API.
- ``ENDPOINT_NOT_FOUND``: the fetch endpoint is not documented in that API.
- ``NO_SOURCES``: a canonical field maps no API at all.

Warning codes (stored with the model, never a refusal):

- ``WRITE_ONLY_SOURCE``: a mapping cites only write operations (a request body, or what a
  POST/PUT/PATCH/DELETE echoes); a model or a GET response says what the API returns. When the
  docs have no read source, it is the only evidence and stays.
- ``NO_COVERAGE``: an input API is not mapped by any field. Server generation sends it back
  for repair on every round and stores the model with the warning only after the last one; a
  Claude or pasted draft is stored with the warning.
"""

import html
import re
from collections.abc import Callable
from dataclasses import dataclass

from plume.domain.models.canonical_model import CanonicalField, FieldSource, ModelDraft

_WS = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class Issue:
    code: str
    field: str
    api: str | None
    message: str


@dataclass(frozen=True, slots=True)
class Oracle:
    """Lookups into the pinned builds (one per API); supplied by the application layer."""

    doc_text: Callable[[str, str], str | None]  # (api, doc_id) -> text
    field_exists: Callable[[str, str], bool]  # (api, path) -> documented?
    endpoint_exists: Callable[[str, str], bool]  # (api, "GET /path") -> documented?
    write_only: Callable[[str, str], bool] = lambda _api, _doc: False  # (api, doc_id) -> a write?
    # (api, doc_id, path) -> the field's own text in that document (its line and description),
    # None when the document does not list the field. Unset: quotes are not tied to fields.
    field_texts: Callable[[str, str, str], tuple[str, ...] | None] | None = None
    # (api, "METHOD /path") -> the response field names of that endpoint (None: unknown/none)
    fetch_fields: Callable[[str, str], frozenset[str] | None] | None = None
    # (api, path) -> (the types the API states for it, its direct sub-field names)
    path_shape: Callable[[str, str], tuple[frozenset[str], tuple[str, ...]]] | None = None


_TAG = re.compile(r"<[^>]{0,200}>")


def _norm(text: str) -> str:
    """Markup-free, case-, whitespace- and backtick-insensitive: HTML tags become spaces and
    entities are decoded on both sides (descriptions with <br>, <ul>, &amp;)."""
    plain = html.unescape(_TAG.sub(" ", text)).replace("`", "")
    return _WS.sub(" ", plain).strip().lower()


def _names(path: str) -> set[str]:
    leaf = path.replace("[]", "").split(".")[-1].lower()
    return {leaf, leaf.replace("_", " ")} if leaf else set()


def quote_on_field(quote: str, paths: list[str], api: str, doc_id: str, oracle: Oracle) -> bool:
    """The quote is about one of the mapped fields: from its own entry when the cited document
    lists it, else naming it."""
    lookup = oracle.field_texts
    if lookup is None:
        return True
    found = [lookup(api, doc_id, p) for p in paths]
    texts = [t for f in found for t in (f or ())]
    listed = any(f is not None for f in found)
    if listed:
        return any(quote_in(quote, t) for t in texts)
    said = _norm(quote)
    return any(re.search(rf"(?<![a-z0-9_]){re.escape(n)}(?![a-z0-9_])", said)
               for p in paths for n in _names(p))  # fmt: skip


def quote_in(quote: str, text: str) -> bool:
    """Whitespace-, case- and backtick-insensitive containment."""
    return _norm(quote) in _norm(text)


_PRIMITIVE = frozenset({"string", "integer", "number", "boolean", "null"})
_CONTAINER_TYPES = ("object", "array", "list", "map", "dict")
_PLURAL_OK = frozenset({"array-vs-single", "cardinality", "split"})


def _scalar(canonical_type: str) -> bool:
    t = canonical_type.strip().lower()
    return bool(t) and not t.startswith(_CONTAINER_TYPES) and not t.endswith("[]")


def _same_path(a: str, b: str) -> bool:
    x, y = a.lower().replace("[]", ""), b.lower().replace("[]", "")
    return x == y or x.endswith("." + y) or y.endswith("." + x)


def _shape_issues(
    path: str, f: CanonicalField, api: str, src: FieldSource, oracle: Oracle
) -> list[Issue]:
    """Scalars mapped from objects or lists; paths outside the named fetch's response."""
    out: list[Issue] = []
    if oracle.fetch_fields is not None and src.fetch:
        known = oracle.fetch_fields(api, src.fetch)
        for p in src.paths:
            if known and not any(_same_path(p.path, k) for k in known):
                out.append(Issue("PATH_NOT_IN_FETCH", path, api,
                                 f"{p.path} is not in the response of {src.fetch}: cite a path "
                                 "of that response, or drop fetch"))  # fmt: skip
    if oracle.path_shape is None or f.fields or not _scalar(f.type):
        return out
    plural_ok = src.conversion is not None and src.conversion.kind in _PLURAL_OK
    for p in src.paths:
        types, subs = oracle.path_shape(api, p.path)
        kinds = {t.lower() for t in types}
        if not kinds or kinds & _PRIMITIVE - {"null"}:
            continue  # the API states a scalar somewhere: fine
        if kinds <= {"array", "null"}:
            if not plural_ok and not p.path.endswith("[]"):
                out.append(Issue("ARRAY_FOR_SINGLE", path, api,
                                 f"{p.path} is a list in {api} and {path} is a single "
                                 f"{f.type}: map one item's field, or state a conversion "
                                 "(array-vs-single, cardinality or split)"))  # fmt: skip
            continue
        listed = ", ".join(subs[:12]) + (", …" if len(subs) > 12 else "")
        out.append(Issue("SCALAR_FROM_OBJECT", path, api,
                         f"{p.path} is an object in {api} ({', '.join(sorted(types))}); map one "
                         f"of its fields" + (f": {listed}" if listed else "")))  # fmt: skip
    return out


def _evidence_issues(path: str, api: str, src: FieldSource, oracle: Oracle) -> list[Issue]:
    """Each citation: in the build, its quote in the document, and about the mapped field."""
    out: list[Issue] = []
    if not src.evidence:
        out.append(Issue("MISSING_CITATION", path, api, "the mapping cites no evidence"))
    for e in src.evidence:
        text = oracle.doc_text(api, e.doc_id)
        if text is None:
            out.append(Issue("DOC_NOT_FOUND", path, api, f"{e.doc_id} is not in the build"))
        elif not quote_in(e.quote, text):
            out.append(
                Issue(
                    "QUOTE_NOT_FOUND",
                    path,
                    api,
                    f"the quote is not in {e.doc_id}: {e.quote[:80]!r}",
                )
            )
        elif (
            src.paths
            and all(oracle.field_exists(api, p.path) for p in src.paths)
            and not quote_on_field(e.quote, [p.path for p in src.paths], api, e.doc_id, oracle)
        ):
            out.append(
                Issue(
                    "QUOTE_NOT_ON_FIELD",
                    path,
                    api,
                    f"the quote from {e.doc_id} is not about "
                    f"{', '.join(p.path for p in src.paths)}: quote that field's own "
                    f"description or line ({e.quote[:80]!r})",
                )
            )
    return out


def validate(draft: ModelDraft, apis: frozenset[str], oracle: Oracle) -> list[Issue]:
    issues: list[Issue] = []
    for path, f in draft.walk():
        if not f.sources and not f.fields:  # a container may be mapped through its sub-fields
            issues.append(Issue("NO_SOURCES", path, None, "the field maps no API"))
        for api, src in f.sources:
            if api not in apis:
                issues.append(
                    Issue("API_NOT_IN_SESSION", path, api, f"{api} is not in this session")
                )
                continue
            issues.extend(_evidence_issues(path, api, src, oracle))
            for p in src.paths:
                if not oracle.field_exists(api, p.path):
                    issues.append(
                        Issue(
                            "FIELD_NOT_FOUND",
                            path,
                            api,
                            f"{p.path} is not a documented field of {api}",
                        )
                    )
            if src.fetch and not oracle.endpoint_exists(api, src.fetch):
                issues.append(
                    Issue(
                        "ENDPOINT_NOT_FOUND", path, api, f"{src.fetch} is not documented in {api}"
                    )
                )
            elif all(oracle.field_exists(api, p.path) for p in src.paths):
                issues.extend(_shape_issues(path, f, api, src, oracle))
    return issues


def warnings(draft: ModelDraft, apis: frozenset[str], oracle: Oracle) -> list[Issue]:
    """Mappings that hold but are weak (see the warning codes above)."""
    out: list[Issue] = []
    mapped = {api for _, f in draft.walk() for api, _ in f.sources}
    for api in sorted(apis - mapped):
        out.append(
            Issue(
                "NO_COVERAGE",
                "",
                api,
                f"no field maps {api}: map its documented fields (or say in open_questions why "
                "it has none)",
            )
        )
    for path, f in draft.walk():
        for api, src in f.sources:
            if api not in apis or not src.evidence:
                continue
            fetch_read = (src.fetch or "").strip().upper().startswith("GET ")
            if not fetch_read and all(oracle.write_only(api, e.doc_id) for e in src.evidence):
                cited = ", ".join(sorted({e.doc_id for e in src.evidence}))
                out.append(
                    Issue(
                        "WRITE_ONLY_SOURCE",
                        path,
                        api,
                        f"cites only write operations ({cited}); for what the API returns, "
                        "prefer a model or a GET response field when the docs have one",
                    )
                )
    return out
