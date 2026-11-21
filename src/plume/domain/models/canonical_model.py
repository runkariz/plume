"""A canonical model draft: canonical fields, where each comes from in every API, with evidence.

Drafts come from outside (Claude, through MCP or HTTP) as JSON and are parsed here into frozen
values. Nothing in a draft is trusted until ``validation.validate`` has checked it against the
pinned builds.
"""

import re
from dataclasses import dataclass
from typing import Any

from plume.domain.shared.errors import DomainError

_FIELD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\[\]]{0,127}$")
_SUB_FIELD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
MAX_FIELDS = 200  # all fields, nested ones included
MAX_DEPTH = 3  # a top-level field is depth 1
CONTAINER_TYPES = ("object", "array")
MAX_QUOTE = 2000


class DraftFormatError(DomainError, ValueError):
    """The draft JSON does not have the expected shape."""


@dataclass(frozen=True, slots=True)
class Evidence:
    doc_id: str
    quote: str
    anchor: str | None = None
    # The field is cited without a quote because its own description has no usable sentence
    # (markup junk, a label): why. Then ``quote`` is empty.
    no_quote: str | None = None


@dataclass(frozen=True, slots=True)
class SourcePath:
    path: str
    type: str | None = None


# How a value must be converted between the API and the canonical model (also used by gold).
CONVERSION_KINDS = frozenset(
    {
        "money-minor",  # integer minor units (cents)
        "money-decimal",
        "money-decimal-string",
        "currency-separate",  # the currency is another field
        "enum",  # value map: {API value: canonical value}
        "code-system",  # a standard code list: format "ISO 3166-1 alpha-3 -> alpha-2"; no map
        "datetime",  # format / time zone in `format`
        "id-type",  # string vs number ids
        "array-vs-single",
        "cardinality",  # e.g. synthesize one variant from product-level fields
        "embedded",  # the entity exists only inside another resource
        "derived",  # taken from the field's name or position (billing_ -> billing address)
        "meta-entry",  # an entry of a key/value list (meta_data[key=_tracking_number])
        "split",  # one value spread over several fields, or a sum of several
        "other",
    }
)


@dataclass(frozen=True, slots=True)
class Conversion:
    kind: str
    note: str | None = None
    enum_map: tuple[tuple[str, str], ...] = ()  # (API value, canonical value)
    format: str | None = None  # datetime format / time zone, meta key, ...
    unmapped: tuple[str, ...] = ()  # enum: API values deliberately left without a target
    # enum with several source paths of different value sets (Google Merchant local vs regional
    # availability): (path, map, unmapped) per path, each checked against its own enum
    by_path: tuple[tuple[str, tuple[tuple[str, str], ...], tuple[str, ...]], ...] = ()

    def path_map(self, path: str) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
        """The (map, unmapped) for one source path: its own when given, else the shared one."""
        for p, mapping, unmapped in self.by_path:
            if p == path:
                return mapping, unmapped
        return self.enum_map, self.unmapped


def parse_conversion(raw: Any, where: str) -> Conversion | None:
    """``{"kind": ..., "map": {...}, "format": ..., "note": ...}`` or None."""
    if raw is None:
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("kind"), str):
        raise DraftFormatError(f"{where}.conversion must be an object with a kind")
    kind = raw["kind"].strip().lower()
    if kind not in CONVERSION_KINDS:
        raise DraftFormatError(
            f"{where}.conversion.kind {kind!r} is not one of {', '.join(sorted(CONVERSION_KINDS))}"
        )
    mapping = raw.get("map") or {}
    if not isinstance(mapping, dict):
        raise DraftFormatError(f"{where}.conversion.map must be an object")

    def text(key: str) -> str | None:
        value = raw.get(key)
        return value.strip() if isinstance(value, str) and value.strip() else None

    if kind == "code-system" and not text("format"):
        raise DraftFormatError(
            f"{where}.conversion: a code-system conversion needs format: the two code systems, "
            'e.g. "ISO 3166-1 alpha-3 -> alpha-2"'
        )
    unmapped = raw.get("unmapped") or []
    if not isinstance(unmapped, list):
        raise DraftFormatError(f"{where}.conversion.unmapped must be a list")
    by_path_raw = raw.get("byPath") or {}
    if not isinstance(by_path_raw, dict):
        raise DraftFormatError(f"{where}.conversion.byPath must be an object {{path: {{map}}}}")
    by_path = []
    for path, entry in by_path_raw.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("map") or {}, dict):
            raise DraftFormatError(
                f"{where}.conversion.byPath[{path!r}] must be {{map: {{...}}, unmapped?: [...]}}"
            )
        sub = entry.get("unmapped") or []
        if not isinstance(sub, list):
            raise DraftFormatError(f"{where}.conversion.byPath[{path!r}].unmapped must be a list")
        pairs = tuple((str(k), str(v)) for k, v in (entry.get("map") or {}).items())
        by_path.append((str(path), pairs, tuple(str(u) for u in sub)))
    return Conversion(
        kind,
        text("note"),
        tuple((str(k), str(v)) for k, v in mapping.items()),
        text("format"),
        tuple(str(u) for u in unmapped),
        tuple(by_path),
    )


def conversion_json(c: Conversion) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": c.kind}
    if c.enum_map:
        out["map"] = dict(c.enum_map)
    if c.format:
        out["format"] = c.format
    if c.unmapped:
        out["unmapped"] = list(c.unmapped)
    if c.by_path:
        out["byPath"] = {
            p: {"map": dict(m), **({"unmapped": list(u)} if u else {})} for p, m, u in c.by_path
        }
    if c.note:
        out["note"] = c.note
    return out


@dataclass(frozen=True, slots=True)
class FieldSource:
    """How one API provides a canonical field."""

    paths: tuple[SourcePath, ...]
    evidence: tuple[Evidence, ...]
    fetch: str | None = None  # "GET /admin/api/{version}/products.json"
    join: tuple[str, ...] = ()
    transform: str | None = None
    conversion: Conversion | None = None  # structured: what the transform does to the value

    @property
    def derived(self) -> bool:
        return bool(self.transform or self.join or len(self.paths) > 1)


@dataclass(frozen=True, slots=True)
class CanonicalField:
    name: str
    type: str
    description: str
    required: bool
    sources: tuple[tuple[str, FieldSource], ...]  # (api id, source), sorted by api
    fields: tuple["CanonicalField", ...] = ()  # sub-fields of an object / array field

    def source(self, api: str) -> FieldSource | None:
        return dict(self.sources).get(api)

    @property
    def is_container(self) -> bool:
        return bool(self.fields)

    def child_path(self, parent: str) -> str:
        """``variants`` (array) + ``sku`` -> ``variants[].sku``; ``address`` (object) +
        ``city`` -> ``address.city``."""
        return f"{parent}[]" if self.type == "array" else parent


@dataclass(frozen=True, slots=True)
class OpenQuestion:
    question: str
    detail: str | None = None
    options: tuple[str, ...] = ()


OPERATION_KINDS = ("read", "create", "update", "set", "adjust", "delete", "other")
MAX_OPERATIONS = 20


@dataclass(frozen=True, slots=True)
class OperationSource:
    """How one API performs an operation."""

    endpoint: str  # "POST /admin/api/{version}/inventory_levels/set.json"
    fields: tuple[str, ...]  # the request/response fields it uses (available, quantity)
    semantics: str | None  # "absolute; omitted means 0", "delta", "per-call limit 100"
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True, slots=True)
class Operation:
    """What a client does with the concept (read / set / adjust ...), per API."""

    name: str  # "set absolute stock"
    kind: str
    sources: tuple[tuple[str, OperationSource], ...]  # (api, source), sorted by api

    def source(self, api: str) -> OperationSource | None:
        return dict(self.sources).get(api)


@dataclass(frozen=True, slots=True)
class ModelDraft:
    name: str
    description: str
    fields: tuple[CanonicalField, ...]
    open_questions: tuple[OpenQuestion, ...] = ()
    operations: tuple[Operation, ...] = ()

    def walk(self) -> list[tuple[str, CanonicalField]]:
        """Every field with its canonical path (``variants[].sku``), parents before children."""
        out: list[tuple[str, CanonicalField]] = []

        def visit(fields: tuple[CanonicalField, ...], prefix: str) -> None:
            for f in fields:
                path = f"{prefix}.{f.name}" if prefix else f.name
                out.append((path, f))
                if f.fields:
                    visit(f.fields, f.child_path(path))

        visit(self.fields, "")
        return out

    def leaves(self) -> list[tuple[str, CanonicalField]]:
        """Fields without sub-fields: what coverage counts."""
        return [(p, f) for p, f in self.walk() if not f.fields]


def _str(d: dict[str, Any], key: str, where: str, required: bool = True) -> str | None:
    v = d.get(key)
    if v is None and not required:
        return None
    if not isinstance(v, str) or (required and not v.strip()):
        raise DraftFormatError(f"{where}.{key} must be a non-empty string")
    return v


def _list(d: dict[str, Any], key: str, where: str) -> list[Any]:
    v = d.get(key, [])
    if not isinstance(v, list):
        raise DraftFormatError(f"{where}.{key} must be a list")
    return v


def parse_evidence(items: list[Any], where: str) -> list[Evidence]:
    """Citations: {doc_id, quote, anchor?}, or {doc_id, noQuote: "why"} for a field whose own
    description has nothing to quote (fields, operations and relations alike)."""
    evidence = []
    for i, e in enumerate(items):
        if not isinstance(e, dict):
            raise DraftFormatError(f"{where}.evidence[{i}] must be an object")
        if "noQuote" in e and not isinstance(e["noQuote"], str):
            raise DraftFormatError(
                f"{where}.evidence[{i}].noQuote must be a string: why the field cannot be "
                'quoted, e.g. {"doc_id": "model:x", "noQuote": "the description is one word"}'
            )
        no_quote = _str(e, "noQuote", f"{where}.evidence[{i}]", required=False)
        quote = _str(e, "quote", f"{where}.evidence[{i}]", required=not no_quote) or ""
        if len(quote) > MAX_QUOTE:
            raise DraftFormatError(f"{where}.evidence[{i}].quote is too long")
        evidence.append(
            Evidence(
                doc_id=_str(e, "doc_id", f"{where}.evidence[{i}]") or "",
                quote="" if no_quote else quote,
                anchor=_str(e, "anchor", where, required=False),
                no_quote=no_quote.strip()[:300] if no_quote else None,
            )
        )
    return evidence


def _source(raw: Any, where: str) -> FieldSource:
    if not isinstance(raw, dict):
        raise DraftFormatError(f"{where} must be an object")
    paths = []
    for i, p in enumerate(_list(raw, "paths", where)):
        if isinstance(p, str):
            paths.append(SourcePath(p))
        elif isinstance(p, dict):
            path = _str(p, "path", f"{where}.paths[{i}]")
            paths.append(SourcePath(path or "", _str(p, "type", where, required=False)))
        else:
            raise DraftFormatError(f"{where}.paths[{i}] must be a string or an object")
    evidence = parse_evidence(_list(raw, "evidence", where), where)
    fetch = raw.get("fetch")
    if isinstance(fetch, dict):
        fetch = fetch.get("endpoint")
    if fetch is not None and not isinstance(fetch, str):
        raise DraftFormatError(f"{where}.fetch must be a string like 'GET /path'")
    join = tuple(str(j) for j in _list(raw, "join", where))
    transform = _str(raw, "transform", where, required=False)
    conversion = parse_conversion(raw.get("conversion"), where)
    return FieldSource(tuple(paths), tuple(evidence), fetch, join, transform, conversion)


def _fields(raw: list[Any], where: str, depth: int, count: list[int]) -> tuple[CanonicalField, ...]:
    out = []
    seen: set[str] = set()
    for i, f in enumerate(raw):
        here = f"{where}[{i}]"
        count[0] += 1
        if count[0] > MAX_FIELDS:
            raise DraftFormatError(f"at most {MAX_FIELDS} fields (nested ones included)")
        if not isinstance(f, dict):
            raise DraftFormatError(f"{here} must be an object")
        fname = _str(f, "name", here) or ""
        pattern = _FIELD_NAME if depth == 1 else _SUB_FIELD_NAME
        if not pattern.fullmatch(fname):
            raise DraftFormatError(f"{here}.name {fname!r} is not a valid field name")
        if fname in seen:
            raise DraftFormatError(f"duplicate field {fname!r} in {where}")
        seen.add(fname)
        sources_raw = f.get("sources", {})
        if not isinstance(sources_raw, dict):
            raise DraftFormatError(f"{here}.sources must be an object keyed by api id")
        sources = tuple(
            sorted(
                (str(api), _source(src, f"{here}.sources.{api}"))
                for api, src in sources_raw.items()
            )
        )
        ftype = _str(f, "type", here) or ""
        children_raw = _list(f, "fields", here)
        if children_raw and ftype not in CONTAINER_TYPES:
            raise DraftFormatError(f"{here}: only object or array fields can have sub-fields")
        if children_raw and depth >= MAX_DEPTH:
            raise DraftFormatError(f"{here}: fields nest at most {MAX_DEPTH} levels deep")
        out.append(
            CanonicalField(
                name=fname,
                type=ftype,
                description=_str(f, "description", here, required=False) or "",
                required=bool(f.get("required", False)),
                sources=sources,
                fields=_fields(children_raw, f"{here}.fields", depth + 1, count)
                if children_raw
                else (),
            )
        )
    return tuple(out)


def parse_draft(raw: Any) -> ModelDraft:
    """Parse draft JSON (the shape documented in the model context) into a ``ModelDraft``."""
    if not isinstance(raw, dict):
        raise DraftFormatError("the draft must be a JSON object")
    name = _str(raw, "name", "model") or ""
    description = _str(raw, "description", "model", required=False) or ""
    fields_raw = _list(raw, "fields", "model")
    if not fields_raw:
        raise DraftFormatError("model.fields must not be empty")
    count = [0]
    fields = _fields(fields_raw, "fields", 1, count)
    questions = []
    for i, q in enumerate(_list(raw, "open_questions", "model")):
        if isinstance(q, str):
            questions.append(OpenQuestion(q))
        elif isinstance(q, dict):
            questions.append(
                OpenQuestion(
                    question=_str(q, "question", f"open_questions[{i}]") or "",
                    detail=_str(q, "detail", "q", required=False),
                    options=tuple(str(o) for o in q.get("options", []) or []),
                )
            )
        else:
            raise DraftFormatError(f"open_questions[{i}] must be a string or an object")
    operations = _operations(_list(raw, "operations", "model"))
    return ModelDraft(
        name.strip(), description.strip(), tuple(fields), tuple(questions), operations
    )


def _operations(raw: list[Any]) -> tuple[Operation, ...]:
    if len(raw) > MAX_OPERATIONS:
        raise DraftFormatError(f"model.operations has more than {MAX_OPERATIONS} entries")
    out = []
    for i, op in enumerate(raw):
        where = f"operations[{i}]"
        if not isinstance(op, dict):
            raise DraftFormatError(f"{where} must be an object")
        kind = (_str(op, "kind", where) or "").strip().lower()
        if kind not in OPERATION_KINDS:
            raise DraftFormatError(f"{where}.kind must be one of {', '.join(OPERATION_KINDS)}")
        sources_raw = op.get("sources", {})
        if not isinstance(sources_raw, dict):
            raise DraftFormatError(f"{where}.sources must be an object keyed by api id")
        sources = []
        for api, src in sorted(sources_raw.items()):
            here = f"{where}.sources.{api}"
            if not isinstance(src, dict):
                raise DraftFormatError(f"{here} must be an object")
            parsed = _source({"paths": [], **src}, here)  # evidence parsing as for fields
            sources.append(
                (
                    str(api),
                    OperationSource(
                        endpoint=_str(src, "endpoint", here) or "",
                        fields=tuple(str(f) for f in _list(src, "fields", here)),
                        semantics=_str(src, "semantics", here, required=False),
                        evidence=parsed.evidence,
                    ),
                )
            )
        out.append(Operation((_str(op, "name", where) or "").strip(), kind, tuple(sources)))
    return tuple(out)
