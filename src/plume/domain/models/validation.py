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
- ``TYPE_MISMATCH``: a boolean canonical field maps a string / number API field without a
  conversion (which values mean true).
- ``SINGLE_FOR_ARRAY``: a list canonical field maps a scalar API field, without a cardinality /
  array-vs-single conversion.
- ``ENUM_KEY_UNKNOWN``: an enum conversion maps a value the cited documents' enum does not have
  (a map shared by several source paths: none of their enums; a byPath map: its own path's).
- ``ENUM_MAP_INCOMPLETE``: an enum conversion leaves values of that enum neither mapped nor
  listed in ``unmapped``. A standard code list is a ``code-system`` conversion instead (no map,
  not checked value by value).
- ``OPERATION_FIELD_NOT_FOUND``: an operation names a field its endpoint does not document.
- ``QUOTE_TOO_SHORT``: the quote carries no information (fewer than 4 words and 20 letters),
  unless it is the field's whole own description of 2+ words.
- ``NO_QUOTE_NOT_ALLOWED``: ``noQuote`` cites a field whose document does not list it, or whose
  own description has a usable sentence to quote.
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

from plume.domain.models.canonical_model import CanonicalField, Evidence, FieldSource, ModelDraft

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
    # (api, path, cited doc ids) -> the enum values those documents state for it (None: none)
    path_enum: Callable[[str, str, tuple[str, ...]], tuple[str, ...] | None] | None = None
    # (api, "METHOD /path") -> every field name of that endpoint (request and response)
    call_fields: Callable[[str, str], frozenset[str] | None] | None = None


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
    out.extend(_enum_issues(path, api, src, oracle))
    plural_ok = src.conversion is not None and src.conversion.kind in _PLURAL_OK
    if (
        oracle.path_shape is not None
        and not _scalar(f.type)
        and f.type.lower().startswith(("array", "list"))
        and not plural_ok
    ):
        for p in src.paths:
            types = oracle.path_shape(api, p.path)[0]
            kinds = {t.lower() for t in types}
            # any type but a list is one value: a scalar, an object, a $ref'd model (bol
            # salutation: Salutation | string)
            if kinds and "array" not in kinds and not p.path.endswith("[]"):
                out.append(Issue("SINGLE_FOR_ARRAY", path, api,
                                 f"{p.path} is a single {'/'.join(sorted(types))} in {api} and "
                                 f"{path} is a list: map a list, or state a conversion "
                                 "(cardinality or array-vs-single)"))  # fmt: skip
    if oracle.path_shape is None or f.fields or not _scalar(f.type):
        return out
    for p in src.paths:
        types, subs = oracle.path_shape(api, p.path)
        kinds = {t.lower() for t in types}
        if (
            f.type.lower() in ("boolean", "bool")
            and src.conversion is None
            and kinds
            and kinds <= {"string", "integer", "number", "null"}
            and kinds - {"null"}
        ):  # tax_exempt (boolean) <- tax_exempt_category (a code): which values mean true?
            out.append(Issue("TYPE_MISMATCH", path, api,
                             f"{p.path} is a {'/'.join(sorted(types))} in {api} and {path} is a "
                             "boolean: map a boolean field, or state a conversion (enum: which "
                             "values mean true)"))  # fmt: skip
            continue
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


_WORD = re.compile(r"[^\W\d_]{2,}")
MIN_QUOTE_WORDS = 4
MIN_QUOTE_LETTERS = 20


def substantive(quote: str) -> bool:
    """A quote that carries information: at least 4 words or 20 letters (not "Important!")."""
    plain = _norm(quote)
    return (
        len(_WORD.findall(plain)) >= MIN_QUOTE_WORDS
        or sum(c.isalpha() for c in plain) >= MIN_QUOTE_LETTERS
    )


# value lists, formats and examples are not sentences (Mirakl order_state: "Order's state" +
# 'Enum: "STAGING", ...')
_NOT_A_SENTENCE = re.compile(
    r"^\s*(enum|enums|allowed values?|possible values?|values?|format|pattern|example|examples|"
    r"e\.g\.|default|min(imum)?|max(imum)?|min ?length|max ?length|deprecated)\b\s*[:=]",
    re.IGNORECASE,
)


_VALUE_TAIL = re.compile(
    r"(?<=[.;,)])\s+(?:enum|allowed values|possible values|format|example)s?\s*:", re.IGNORECASE
)


def usable_sentence(own: list[str]) -> str | None:
    """The first substantive sentence of a field's own descriptions (not its field-list lines,
    not enum / format / example lines), or None when there is nothing to quote."""
    for text in own:
        if text.lstrip().startswith("- `"):
            continue
        for raw in text.splitlines():
            line = _VALUE_TAIL.split(raw, maxsplit=1)[0].strip()  # "Order's state. Enum: ..."
            if line and not _NOT_A_SENTENCE.match(line) and substantive(line):
                return line
    return None


def _own_texts(api: str, doc_id: str, paths: list[str], oracle: Oracle) -> list[str] | None:
    """The mapped fields' own texts in the document (None: it lists none of them)."""
    if oracle.field_texts is None:
        return None
    found = [oracle.field_texts(api, doc_id, p) for p in paths]
    if all(f is None for f in found):
        return None
    return [t for f in found for t in (f or ())]


def _quote_issue(
    e: Evidence, path: str, api: str, src: FieldSource, oracle: Oracle
) -> Issue | None:
    """Substance: a short quote passes only as a field's whole own description (2+ words);
    noQuote only when the field's own texts have nothing substantive to quote."""
    paths = [p.path for p in src.paths]
    own = _own_texts(api, e.doc_id, paths, oracle) if paths else None
    if e.no_quote:
        if own is None:
            listed = ", ".join(paths) or "the field"
            return Issue("NO_QUOTE_NOT_ALLOWED", path, api,
                         f"noQuote needs {e.doc_id} to list {listed}")  # fmt: skip
        sentence = usable_sentence(own)
        if sentence is not None:
            return Issue("NO_QUOTE_NOT_ALLOWED", path, api,
                         f"the field's own description has a usable sentence: quote it: "
                         f"{sentence[:200]!r}")  # fmt: skip
        return None
    whole = own is not None and any(
        _norm(t) == _norm(e.quote) and len(_WORD.findall(_norm(t))) >= 2 for t in own
    )
    if substantive(e.quote) or whole:
        return None
    return Issue("QUOTE_TOO_SHORT", path, api,
                 f"the quote carries no information ({e.quote[:40]!r}): quote a sentence of "
                 "at least 4 words, or, when the field's own description has none, cite it as "
                 '{"doc_id": "...", "noQuote": "<why>"}')  # fmt: skip


def evidence_issues(path: str, api: str, src: FieldSource, oracle: Oracle) -> list[Issue]:
    """Each citation: in the build, its quote in the document, substantive, and about the
    mapped field."""
    out: list[Issue] = []
    if not src.evidence:
        out.append(Issue("MISSING_CITATION", path, api, "the mapping cites no evidence"))
    for e in src.evidence:
        text = oracle.doc_text(api, e.doc_id)
        if text is None:
            out.append(Issue("DOC_NOT_FOUND", path, api, f"{e.doc_id} is not in the build"))
            continue
        exists = bool(src.paths) and all(oracle.field_exists(api, p.path) for p in src.paths)
        if e.no_quote:
            issue = _quote_issue(e, path, api, src, oracle) if exists else None
            out.extend([issue] if issue else [])
        elif not quote_in(e.quote, text):
            out.append(Issue("QUOTE_NOT_FOUND", path, api,
                             f"the quote is not in {e.doc_id}: {e.quote[:80]!r}"))  # fmt: skip
        elif exists and not quote_on_field(
            e.quote, [p.path for p in src.paths], api, e.doc_id, oracle
        ):
            out.append(Issue("QUOTE_NOT_ON_FIELD", path, api,
                             f"the quote from {e.doc_id} is not about "
                             f"{', '.join(p.path for p in src.paths)}: quote that field's own "
                             f"description or line ({e.quote[:80]!r})"))  # fmt: skip
        elif exists and (issue := _quote_issue(e, path, api, src, oracle)) is not None:
            out.append(issue)
    return out


ENUM_SHOWN = 40  # values named in an ENUM_MAP_INCOMPLETE refusal
CODE_LIST_SIZE = 40  # an enum this long is likely a standard code list


def _enum_issues(path: str, api: str, src: FieldSource, oracle: Oracle) -> list[Issue]:
    """An enum conversion against the enum the cited documents state for the path."""
    conv = src.conversion
    if conv is None or conv.kind != "enum" or oracle.path_enum is None:
        return []
    cited = tuple(dict.fromkeys(e.doc_id for e in src.evidence))
    out: list[Issue] = []
    enums = {p.path: oracle.path_enum(api, p.path, cited) for p in src.paths}
    # a shared map over several paths (local + regional availability) may hold keys of either
    # enum: a key is unknown only when no path has it; byPath maps answer to their own enum
    every = {v.lower() for vs in enums.values() for v in vs or ()}
    own = {path for path, _, _ in conv.by_path}
    for p in src.paths:
        values = enums[p.path]
        if not values:
            continue
        mapping, unmapped = conv.path_map(p.path)
        known = {v.lower() for v in values} if p.path in own else every
        keys = {k.lower(): k for k, _ in mapping}
        unknown = [k for low, k in keys.items() if low not in known]
        if unknown:
            out.append(Issue("ENUM_KEY_UNKNOWN", path, api,
                             f"{p.path} has no value {', '.join(unknown)} in {api} (its values: "
                             f"{', '.join(values)})"))  # fmt: skip
        covered = set(keys) | {u.lower() for u in unmapped}
        missing = [v for v in values if v.lower() not in covered]
        if missing:
            shown = ", ".join(missing[:ENUM_SHOWN]) + (
                f" and {len(missing) - ENUM_SHOWN} more" if len(missing) > ENUM_SHOWN else ""
            )
            hint = (
                "; a standard code list (countries, currencies, languages) is a code-system "
                'conversion with format, e.g. "ISO 3166-1 alpha-3 -> alpha-2"'
                if len(values) > CODE_LIST_SIZE
                else ""
            )
            out.append(Issue("ENUM_MAP_INCOMPLETE", path, api,
                             f"the enum map leaves {shown} of {p.path} unmapped: map them, or "
                             f"list them in conversion.unmapped{hint}"))  # fmt: skip
    return out


def _cited(where: str, api: str, evidence: tuple[Evidence, ...], oracle: Oracle) -> list[Issue]:
    """Citations not tied to one field: in the build, quoted verbatim, substantive."""
    if not evidence:
        return [Issue("MISSING_CITATION", where, api, "it cites nothing")]
    out: list[Issue] = []
    for e in evidence:
        text = oracle.doc_text(api, e.doc_id)
        if text is None:
            out.append(Issue("DOC_NOT_FOUND", where, api, f"{e.doc_id} is not in the build"))
        elif not quote_in(e.quote, text):
            message = f"the quote is not in {e.doc_id}: {e.quote[:80]!r}"
            out.append(Issue("QUOTE_NOT_FOUND", where, api, message))
        elif not substantive(e.quote):
            message = f"the quote carries no information ({e.quote[:40]!r})"
            out.append(Issue("QUOTE_TOO_SHORT", where, api, message))
    return out


def _operation_issues(draft: ModelDraft, apis: frozenset[str], oracle: Oracle) -> list[Issue]:
    """Operations: a documented endpoint per API, its fields on that endpoint, cited."""
    out: list[Issue] = []
    for op in draft.operations:
        where = f"operation:{op.name}"
        for api, src in op.sources:
            if api not in apis:
                out.append(Issue("API_NOT_IN_SESSION", where, api, f"{api} is not in this session"))
                continue
            if not oracle.endpoint_exists(api, src.endpoint):
                out.append(Issue("ENDPOINT_NOT_FOUND", where, api,
                                 f"{src.endpoint} is not documented in {api}"))  # fmt: skip
                continue
            known = oracle.call_fields(api, src.endpoint) if oracle.call_fields else None
            for name in src.fields:
                if known is not None and not any(_same_path(name, k) for k in known):
                    out.append(Issue("OPERATION_FIELD_NOT_FOUND", where, api,
                                     f"{name} is not a field of {src.endpoint}"))  # fmt: skip
            out.extend(_cited(where, api, src.evidence, oracle))
    return out


def validate(draft: ModelDraft, apis: frozenset[str], oracle: Oracle) -> list[Issue]:
    issues: list[Issue] = _operation_issues(draft, apis, oracle)
    for path, f in draft.walk():
        if not f.sources and not f.fields:  # a container may be mapped through its sub-fields
            issues.append(Issue("NO_SOURCES", path, None, "the field maps no API"))
        for api, src in f.sources:
            if api not in apis:
                issues.append(
                    Issue("API_NOT_IN_SESSION", path, api, f"{api} is not in this session")
                )
                continue
            issues.extend(evidence_issues(path, api, src, oracle))
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
