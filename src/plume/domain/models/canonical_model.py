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


@dataclass(frozen=True, slots=True)
class SourcePath:
    path: str
    type: str | None = None


@dataclass(frozen=True, slots=True)
class FieldSource:
    """How one API provides a canonical field."""

    paths: tuple[SourcePath, ...]
    evidence: tuple[Evidence, ...]
    fetch: str | None = None  # "GET /admin/api/{version}/products.json"
    join: tuple[str, ...] = ()
    transform: str | None = None

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


@dataclass(frozen=True, slots=True)
class ModelDraft:
    name: str
    description: str
    fields: tuple[CanonicalField, ...]
    open_questions: tuple[OpenQuestion, ...] = ()

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
    evidence = []
    for i, e in enumerate(_list(raw, "evidence", where)):
        if not isinstance(e, dict):
            raise DraftFormatError(f"{where}.evidence[{i}] must be an object")
        quote = _str(e, "quote", f"{where}.evidence[{i}]") or ""
        if len(quote) > MAX_QUOTE:
            raise DraftFormatError(f"{where}.evidence[{i}].quote is too long")
        evidence.append(
            Evidence(
                doc_id=_str(e, "doc_id", f"{where}.evidence[{i}]") or "",
                quote=quote,
                anchor=_str(e, "anchor", where, required=False),
            )
        )
    fetch = raw.get("fetch")
    if isinstance(fetch, dict):
        fetch = fetch.get("endpoint")
    if fetch is not None and not isinstance(fetch, str):
        raise DraftFormatError(f"{where}.fetch must be a string like 'GET /path'")
    join = tuple(str(j) for j in _list(raw, "join", where))
    transform = _str(raw, "transform", where, required=False)
    return FieldSource(tuple(paths), tuple(evidence), fetch, join, transform)


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
    return ModelDraft(name.strip(), description.strip(), tuple(fields), tuple(questions))
