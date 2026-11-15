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
MAX_FIELDS = 200
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

    def source(self, api: str) -> FieldSource | None:
        return dict(self.sources).get(api)


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


def parse_draft(raw: Any) -> ModelDraft:
    """Parse draft JSON (the shape documented in the model context) into a ``ModelDraft``."""
    if not isinstance(raw, dict):
        raise DraftFormatError("the draft must be a JSON object")
    name = _str(raw, "name", "model") or ""
    description = _str(raw, "description", "model", required=False) or ""
    fields_raw = _list(raw, "fields", "model")
    if not fields_raw:
        raise DraftFormatError("model.fields must not be empty")
    if len(fields_raw) > MAX_FIELDS:
        raise DraftFormatError(f"at most {MAX_FIELDS} fields")
    fields = []
    seen: set[str] = set()
    for i, f in enumerate(fields_raw):
        where = f"fields[{i}]"
        if not isinstance(f, dict):
            raise DraftFormatError(f"{where} must be an object")
        fname = _str(f, "name", where) or ""
        if not _FIELD_NAME.fullmatch(fname):
            raise DraftFormatError(f"{where}.name {fname!r} is not a valid field name")
        if fname in seen:
            raise DraftFormatError(f"duplicate field {fname!r}")
        seen.add(fname)
        sources_raw = f.get("sources", {})
        if not isinstance(sources_raw, dict):
            raise DraftFormatError(f"{where}.sources must be an object keyed by api id")
        sources = tuple(
            sorted(
                (str(api), _source(src, f"{where}.sources.{api}"))
                for api, src in sources_raw.items()
            )
        )
        fields.append(
            CanonicalField(
                name=fname,
                type=_str(f, "type", where) or "",
                description=_str(f, "description", where, required=False) or "",
                required=bool(f.get("required", False)),
                sources=sources,
            )
        )
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
