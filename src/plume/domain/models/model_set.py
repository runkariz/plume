"""Model sets: several canonical models with relations between them.

See docs/design/model-relations.md.

A set references member MODEL SNAPSHOTS by id (each validated on its own) and adds relations: the
design the user chose (embedded or reference, cardinality, key fields) plus how each API documents
it, with evidence. Like models, set drafts come from outside and are checked by
``validate_set`` against the members and the pinned builds before they are stored.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from plume.domain.models.canonical_model import (
    DraftFormatError,
    Evidence,
    ModelDraft,
    OpenQuestion,
    SourcePath,
)
from plume.domain.models.snapshot import PROMPT_VERSION, Origin, PinnedInput, Visibility
from plume.domain.models.validation import Issue, Oracle, quote_in

MIN_MEMBERS = 1
MAX_MEMBERS = 8
MAX_RELATIONS = 64
KINDS = ("embedded", "reference")
CARDINALITIES = ("1:1", "1:n", "n:1", "n:m")
SOURCE_KINDS = ("nested", "sub_resource", "id_field", "model_ref")


@dataclass(frozen=True, slots=True)
class RelationSource:
    """How one API documents the relation."""

    as_: str  # nested | sub_resource | id_field | model_ref
    paths: tuple[SourcePath, ...]
    evidence: tuple[Evidence, ...]
    fetch: str | None = None


@dataclass(frozen=True, slots=True)
class Relation:
    id: str
    from_: str  # member concept (as named in the set)
    to: str
    kind: str  # embedded | reference
    cardinality: str
    embed_field: str | None  # embedded: the canonical field of `from_` holding `to`
    ref_field: str | None  # reference: the canonical field of `from_` holding the key
    ref_key: str | None  # reference: the canonical field of `to` it points at
    confirmed: bool  # the user chose this design (False = a proposal, shown as undecided)
    candidate: str | None
    sources: tuple[tuple[str, RelationSource], ...]  # (api, source), sorted by api


@dataclass(frozen=True, slots=True)
class SetMember:
    concept: str
    model_id: str


@dataclass(frozen=True, slots=True)
class Alias:
    """The user accepted that differently named concepts are the same (design D2)."""

    names: tuple[tuple[str, str], ...]  # (api, concept key), sorted
    concept: str  # the set's name for it


@dataclass(frozen=True, slots=True)
class SetDraft:
    name: str
    description: str
    members: tuple[SetMember, ...]
    relations: tuple[Relation, ...]
    aliases: tuple[Alias, ...] = ()
    open_questions: tuple[OpenQuestion, ...] = ()

    def member(self, concept: str) -> SetMember | None:
        key = concept.strip().lower()
        return next((m for m in self.members if m.concept.lower() == key), None)


@dataclass(frozen=True, slots=True)
class ModelSetSnapshot:
    set_id: str
    session_id: str
    inputs: tuple[PinnedInput, ...]
    draft: SetDraft
    created_at: datetime
    visibility: str = Visibility.UNLISTED
    origin: str = Origin.USER
    generator: str = "claude"
    lineage_id: str = ""
    version: int = 1
    based_on: str | None = None
    content_key: str = ""
    released_at: datetime | None = None
    prompt_version: str = PROMPT_VERSION

    @property
    def lineage(self) -> str:
        return self.lineage_id or self.set_id

    @property
    def key(self) -> str:
        return self.content_key or self.set_id

    @property
    def undecided(self) -> list[str]:
        return [r.id for r in self.draft.relations if not r.confirmed]


# -- parsing ---------------------------------------------------------------------------------------


def _s(d: dict[str, Any], key: str, where: str, required: bool = True) -> str | None:
    v = d.get(key)
    if v is None and not required:
        return None
    if not isinstance(v, str) or (required and not v.strip()):
        raise DraftFormatError(f"{where}.{key} must be a non-empty string")
    return v.strip()


def _relation_source(raw: Any, where: str) -> RelationSource:
    if not isinstance(raw, dict):
        raise DraftFormatError(f"{where} must be an object")
    as_ = _s(raw, "as", where) or ""
    if as_ not in SOURCE_KINDS:
        raise DraftFormatError(f"{where}.as must be one of {', '.join(SOURCE_KINDS)}")
    paths = []
    for i, p in enumerate(raw.get("paths") or []):
        if isinstance(p, str):
            paths.append(SourcePath(p))
        elif isinstance(p, dict) and isinstance(p.get("path"), str):
            paths.append(SourcePath(p["path"]))
        else:
            raise DraftFormatError(f"{where}.paths[{i}] must be a string or {{path}}")
    evidence = []
    for i, e in enumerate(raw.get("evidence") or []):
        if not isinstance(e, dict):
            raise DraftFormatError(f"{where}.evidence[{i}] must be an object")
        evidence.append(
            Evidence(
                doc_id=_s(e, "doc_id", f"{where}.evidence[{i}]") or "",
                quote=_s(e, "quote", f"{where}.evidence[{i}]") or "",
                anchor=_s(e, "anchor", where, required=False),
            )
        )
    fetch = raw.get("fetch")
    if fetch is not None and not isinstance(fetch, str):
        raise DraftFormatError(f"{where}.fetch must be a string like 'GET /path'")
    return RelationSource(as_, tuple(paths), tuple(evidence), fetch)


def _relation(raw: Any, where: str) -> Relation:
    if not isinstance(raw, dict):
        raise DraftFormatError(f"{where} must be an object")
    kind = _s(raw, "kind", where) or ""
    if kind not in KINDS:
        raise DraftFormatError(f"{where}.kind must be embedded or reference")
    cardinality = _s(raw, "cardinality", where) or ""
    if cardinality not in CARDINALITIES:
        raise DraftFormatError(f"{where}.cardinality must be one of {', '.join(CARDINALITIES)}")
    embed = raw.get("embed") or {}
    ref = raw.get("ref") or {}
    if not isinstance(embed, dict) or not isinstance(ref, dict):
        raise DraftFormatError(f"{where}.embed / .ref must be objects")
    if kind == "embedded" and not embed.get("field"):
        raise DraftFormatError(f"{where}: an embedded relation needs embed.field")
    if kind == "reference" and not (ref.get("field") and ref.get("key")):
        raise DraftFormatError(f"{where}: a reference needs ref.field and ref.key")
    sources_raw = raw.get("sources") or {}
    if not isinstance(sources_raw, dict):
        raise DraftFormatError(f"{where}.sources must be an object keyed by api id")
    sources = tuple(
        sorted(
            (str(api), _relation_source(src, f"{where}.sources.{api}"))
            for api, src in sources_raw.items()
            if src is not None  # null = the API does not document the relation
        )
    )
    frm = _s(raw, "from", where) or ""
    to = _s(raw, "to", where) or ""
    return Relation(
        id=_s(raw, "id", where, required=False) or f"{frm.lower()}-{to.lower()}",
        from_=frm,
        to=to,
        kind=kind,
        cardinality=cardinality,
        embed_field=str(embed["field"]) if kind == "embedded" else None,
        ref_field=str(ref["field"]) if kind == "reference" else None,
        ref_key=str(ref["key"]) if kind == "reference" else None,
        confirmed=raw.get("confirmed") is True,
        candidate=_s(raw, "candidate", where, required=False),
        sources=sources,
    )


def _members(raw: dict[str, Any]) -> tuple[SetMember, ...]:
    members_raw = raw.get("members")
    if isinstance(members_raw, dict):  # {"Product": "m-…"} shorthand
        members_raw = [{"concept": c, "model_id": m} for c, m in members_raw.items()]
    if not isinstance(members_raw, list):
        raise DraftFormatError("set.members must be a list of {concept, model_id}")
    if not MIN_MEMBERS <= len(members_raw) <= MAX_MEMBERS:
        raise DraftFormatError(f"a set has {MIN_MEMBERS}..{MAX_MEMBERS} members")
    members = []
    seen: set[str] = set()
    for i, m in enumerate(members_raw):
        if not isinstance(m, dict):
            raise DraftFormatError(f"members[{i}] must be an object")
        concept = _s(m, "concept", f"members[{i}]") or ""
        model_id = _s(m, "model_id", f"members[{i}]", required=False) or _s(
            m, "modelId", f"members[{i}]"
        )
        if concept.lower() in seen:
            raise DraftFormatError(f"duplicate member {concept!r}")
        seen.add(concept.lower())
        members.append(SetMember(concept, model_id or ""))
    return tuple(members)


def _relations(raw: dict[str, Any]) -> tuple[Relation, ...]:
    relations_raw = raw.get("relations") or []
    if not isinstance(relations_raw, list) or len(relations_raw) > MAX_RELATIONS:
        raise DraftFormatError(f"set.relations must be a list of at most {MAX_RELATIONS}")
    relations = tuple(_relation(r, f"relations[{i}]") for i, r in enumerate(relations_raw))
    ids = [r.id for r in relations]
    if len(ids) != len(set(ids)):
        raise DraftFormatError("relation ids must be unique")
    return relations


def _aliases(raw: dict[str, Any]) -> tuple[Alias, ...]:
    aliases = []
    for i, a in enumerate(raw.get("aliases") or []):
        if not isinstance(a, dict) or not isinstance(a.get("names"), dict):
            raise DraftFormatError(f"aliases[{i}] must be {{names: {{api: concept}}, concept}}")
        aliases.append(
            Alias(
                tuple(sorted((str(k), str(v)) for k, v in a["names"].items())),
                _s(a, "concept", f"aliases[{i}]") or "",
            )
        )
    return tuple(aliases)


def _questions(raw: dict[str, Any]) -> tuple[OpenQuestion, ...]:
    questions = []
    for i, q in enumerate(raw.get("open_questions") or []):
        if isinstance(q, str):
            questions.append(OpenQuestion(q))
        elif isinstance(q, dict):
            questions.append(
                OpenQuestion(
                    _s(q, "question", f"open_questions[{i}]") or "",
                    _s(q, "detail", "q", required=False),
                    tuple(str(o) for o in q.get("options") or []),
                )
            )
    return tuple(questions)


def parse_set_draft(raw: Any) -> SetDraft:
    if not isinstance(raw, dict):
        raise DraftFormatError("the set must be a JSON object")
    return SetDraft(
        name=_s(raw, "name", "set") or "",
        description=_s(raw, "description", "set", required=False) or "",
        members=_members(raw),
        relations=_relations(raw),
        aliases=_aliases(raw),
        open_questions=_questions(raw),
    )


def set_draft_json(d: SetDraft) -> dict[str, Any]:
    return {
        "name": d.name,
        "description": d.description,
        "members": [{"concept": m.concept, "model_id": m.model_id} for m in d.members],
        "relations": [
            {
                "id": r.id,
                "from": r.from_,
                "to": r.to,
                "kind": r.kind,
                "cardinality": r.cardinality,
                "embed": {"field": r.embed_field} if r.embed_field else None,
                "ref": {"field": r.ref_field, "key": r.ref_key} if r.ref_field else None,
                "confirmed": r.confirmed,
                "candidate": r.candidate,
                "sources": {
                    api: {
                        "as": s.as_,
                        "paths": [p.path for p in s.paths],
                        "fetch": s.fetch,
                        "evidence": [
                            {"doc_id": e.doc_id, "quote": e.quote, "anchor": e.anchor}
                            for e in s.evidence
                        ],
                    }
                    for api, s in r.sources
                },
            }
            for r in d.relations
        ],
        "aliases": [{"names": dict(a.names), "concept": a.concept} for a in d.aliases],
        "open_questions": [
            {"question": q.question, "detail": q.detail, "options": list(q.options)}
            for q in d.open_questions
        ],
    }


def set_content_key(inputs: tuple[PinnedInput, ...], draft: SetDraft) -> str:
    payload = json.dumps(
        {
            "inputs": [[i.api, i.build] for i in sorted(inputs, key=lambda i: i.api)],
            "set": set_draft_json(draft),
            "prompt_version": PROMPT_VERSION,
        },
        sort_keys=True,
    )
    return "ms-" + hashlib.sha256(payload.encode()).hexdigest()[:24]


# -- validation -----------------------------------------------------------------------------------


def _field_type(draft: ModelDraft, path: str) -> str | None:
    """The type of a canonical field of a member model, by name or by canonical path; a
    nested field is named by its path inside the member (``lines[].order_line_id``; the
    ``[]`` may be left out). So a relation can start or end inside a member: Shipment's
    lines[].order_line_id -> Order line.id."""
    wanted = path.replace("[]", "")
    for p, f in draft.walk():
        if path in (p, f.name) or (wanted and wanted == p.replace("[]", "")):
            return f.type
    return None


def validate_set(
    draft: SetDraft,
    members: dict[str, ModelDraft],  # member concept -> its (already validated) model draft
    apis: frozenset[str],
    oracle: Oracle,
) -> list[Issue]:
    """Relations only: every member model was validated on its own when it was stored."""
    issues: list[Issue] = []
    names = {m.concept.lower(): m.concept for m in draft.members}
    for r in draft.relations:
        where = r.id
        ends = {r.from_.lower(), r.to.lower()}
        missing = sorted(ends - set(names))
        if missing:
            issues.append(
                Issue("RELATION_END_NOT_FOUND", where, None, f"not a member: {', '.join(missing)}")
            )
            continue
        frm, to = members[names[r.from_.lower()]], members[names[r.to.lower()]]
        if r.kind == "embedded":
            ftype = _field_type(frm, r.embed_field or "")
            if ftype is None:
                issues.append(
                    Issue(
                        "RELATION_FIELD_NOT_FOUND",
                        where,
                        None,
                        f"{r.from_} has no field {r.embed_field!r}",
                    )
                )
            elif (r.cardinality in ("1:n", "n:m")) != (ftype == "array"):
                issues.append(
                    Issue(
                        "RELATION_SHAPE_MISMATCH",
                        where,
                        None,
                        f"{r.cardinality} embedded needs an "
                        f"{'array' if r.cardinality in ('1:n', 'n:m') else 'object'} field; "
                        f"{r.from_}.{r.embed_field} is {ftype}",
                    )
                )
        else:
            for model, field_name, label in (
                (frm, r.ref_field, r.from_),
                (to, r.ref_key, r.to),
            ):
                if _field_type(model, field_name or "") is None:
                    issues.append(
                        Issue(
                            "RELATION_FIELD_NOT_FOUND",
                            where,
                            None,
                            f"{label} has no field {field_name!r}",
                        )
                    )
        issues += _source_issues(r, apis, oracle)
    return issues


def _source_issues(r: Relation, apis: frozenset[str], oracle: Oracle) -> list[Issue]:
    where = r.id
    issues: list[Issue] = []
    if not r.sources:
        issues.append(Issue("NO_SOURCES", where, None, "no API documents this relation (cite one)"))
    for api, src in r.sources:
        if api not in apis:
            issues.append(Issue("API_NOT_IN_SET", where, api, f"{api} is not in this set"))
            continue
        if not src.evidence:
            issues.append(Issue("MISSING_CITATION", where, api, "the relation cites nothing"))
        for e in src.evidence:
            text = oracle.doc_text(api, e.doc_id)
            if text is None:
                issues.append(Issue("DOC_NOT_FOUND", where, api, f"{e.doc_id} is not in the build"))
            elif not quote_in(e.quote, text):
                issues.append(
                    Issue(
                        "QUOTE_NOT_FOUND",
                        where,
                        api,
                        f"the quote is not in {e.doc_id}: {e.quote[:80]!r}",
                    )
                )
        for p in src.paths:
            if src.as_ != "sub_resource" and not oracle.field_exists(api, p.path):
                issues.append(
                    Issue(
                        "FIELD_NOT_FOUND",
                        where,
                        api,
                        f"{p.path} is not a documented field of {api}",
                    )
                )
        if src.fetch and not oracle.endpoint_exists(api, src.fetch):
            issues.append(Issue("ENDPOINT_NOT_FOUND", where, api, f"{src.fetch} is not documented"))
        if src.as_ == "sub_resource" and not src.fetch:
            issues.append(
                Issue(
                    "ENDPOINT_NOT_FOUND",
                    where,
                    api,
                    "a sub_resource source needs fetch: the documented endpoint",
                )
            )
    return issues
