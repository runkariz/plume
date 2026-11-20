"""Set gold (``plume.set-gold.v1``): the relations a model set should have, from the eval
tester's relation table, and how a set's relations score against them.

A gold relation names its members (from / to, as the set names them), its design (embedded or
reference, the cardinality, the field), and per API where the relation is documented: the
source paths (the `from` side), a fetch endpoint (a sub-resource or a link), or not available.
Scoring matches a set's relation to the gold relation with the same from / to (case and
spacing ignored): its design is correct when kind and cardinality agree, and each API's source
is correct when one of its paths is a gold path (list marks ignored) or its fetch is the gold
fetch. Gold relations the set lacks are missed; set relations the gold lacks are invented.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from plume.domain.models.model_set import Relation, SetDraft
from plume.domain.shared.errors import DomainError

SET_SCHEMA = "plume.set-gold.v1"


class SetGoldError(DomainError):
    pass


@dataclass(frozen=True, slots=True)
class GoldRelationSource:
    paths: tuple[str, ...] = ()
    fetch: str | None = None
    not_available: bool = False


@dataclass(frozen=True, slots=True)
class GoldRelation:
    id: str
    from_: str
    to: str
    kind: str  # embedded | reference
    cardinality: str  # 1:1 | 1:n | n:1 | n:m
    path: str | None = None  # embedded: the field of `from_`; reference: its key field
    key: str | None = None  # reference: the field of `to` it points at
    apis: dict[str, GoldRelationSource] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SetGold:
    name: str
    apis: tuple[str, ...]
    members: tuple[str, ...]
    relations: tuple[GoldRelation, ...]
    held_out: bool = False
    source: str = ""


def _member(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _path(path: str) -> str:
    return path.strip().lower().replace("[]", "")


def _same_path(a: str, b: str) -> bool:
    """The same relation path in two forms: equal, or one is the other inside a wrapper
    (data[].order_id ~ order_id) or under its container (line_items ~ line_items[].id); list
    marks ignored, at segment boundaries."""
    x, y = _path(a), _path(b)
    return (
        x == y
        or x.endswith("." + y)
        or y.endswith("." + x)
        or x.startswith(y + ".")
        or (y.startswith(x + "."))
    )


def _alternative(relation_id: str) -> bool:
    """A gold row that is an accepted alternative design ("order-customer (embedded
    alternative)"), scored only when the set chose it."""
    return "alternative" in relation_id.lower()


def _fetch(call: str) -> str:
    """ "GET /{version}/orders/{order_id}/products" -> "get orders {} products": the method and
    the path's literals, any parameter as {} (names and a version segment do not matter)."""
    method, _, path = call.strip().partition(" ")
    segs = [s for s in path.strip("/").split("/") if s and s.lower() not in ("{version}", "v1",
            "v2", "v3")]  # fmt: skip
    return " ".join([method.lower(), *("{}" if s.startswith("{") else s.lower() for s in segs)])


def parse_set_gold(raw: Any, source: str = "") -> SetGold:
    if not isinstance(raw, dict) or raw.get("schema") != SET_SCHEMA:
        raise SetGoldError(f"{source or 'set gold'}: schema must be {SET_SCHEMA}")
    relations = []
    for i, r in enumerate(raw.get("relations") or []):
        if not isinstance(r, dict) or not all(isinstance(r.get(k), str) for k in ("from", "to")):
            raise SetGoldError(f"{source}: relations[{i}] needs from and to")
        apis = {
            str(api): GoldRelationSource(
                paths=tuple(str(p) for p in (cell.get("paths") or [])),
                fetch=cell.get("fetch") if isinstance(cell.get("fetch"), str) else None,
                not_available=cell.get("notAvailable") is True,
            )
            for api, cell in (r.get("apis") or {}).items()
            if isinstance(cell, dict)
        }
        relations.append(
            GoldRelation(
                id=str(r.get("id") or f"{r['from']}-{r['to']}"),
                from_=r["from"],
                to=r["to"],
                kind=str(r.get("kind") or ""),
                cardinality=str(r.get("cardinality") or ""),
                path=r.get("field") if isinstance(r.get("field"), str) else None,
                key=r.get("key") if isinstance(r.get("key"), str) else None,
                apis=apis,
            )
        )
    return SetGold(
        name=str(raw.get("name") or ""),
        apis=tuple(str(a) for a in raw.get("apis") or []),
        members=tuple(str(m) for m in raw.get("members") or []),
        relations=tuple(relations),
        held_out=raw.get("heldOut") is True,
        source=source,
    )


@dataclass(frozen=True, slots=True)
class RelationScore:
    gold_id: str
    from_: str
    to: str
    verdict: str  # correct | wrong | missed
    found_id: str | None
    sources: dict[str, str]  # api -> correct | wrong | missed | not_available_correct | invented

    def as_dict(self) -> dict[str, object]:
        return {
            "goldId": self.gold_id,
            "from": self.from_,
            "to": self.to,
            "verdict": self.verdict,
            "foundId": self.found_id,
            "sources": self.sources,
        }


@dataclass(frozen=True, slots=True)
class SetEval:
    gold: str
    held_out: bool
    relations: tuple[RelationScore, ...]
    invented: tuple[str, ...]  # set relation ids the gold does not have

    @property
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.relations:
            out[r.verdict] = out.get(r.verdict, 0) + 1
        out["invented"] = len(self.invented)
        return out

    @property
    def source_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.relations:
            for v in r.sources.values():
                out[v] = out.get(v, 0) + 1
        return out

    def as_dict(self) -> dict[str, object]:
        return {"gold": self.gold, "heldOut": self.held_out, "counts": self.counts,
                "sourceCounts": self.source_counts, "invented": list(self.invented),
                "relations": [r.as_dict() for r in self.relations]}  # fmt: skip


def _source_verdict(gold: GoldRelationSource, found: Relation | None, api: str) -> str:
    src = dict(found.sources).get(api) if found is not None else None
    if gold.not_available:
        return "not_available_correct" if src is None else "invented"
    if src is None:
        return "missed"
    if any(_same_path(p.path, g) for p in src.paths for g in gold.paths):
        return "correct"
    if gold.fetch and src.fetch and _fetch(src.fetch).endswith(_fetch(gold.fetch)):
        return "correct"
    return "wrong"


def _field_of(r: Relation) -> str:
    return _path(r.embed_field or r.ref_field or "")


def _pick(g: GoldRelation, draft: SetDraft, used: set[str]) -> Relation | None:
    """The set's relation for a gold relation: the same id, else the same from / to and field,
    else the same from / to (each set relation used once: billing and shipping address are
    both Order -> Address)."""
    free = [r for r in draft.relations if r.id not in used]
    pair = [
        r for r in free if (_member(r.from_), _member(r.to)) == (_member(g.from_), _member(g.to))
    ]
    return (
        next((r for r in pair if r.id == _base(g.id)), None)
        or next((r for r in pair if g.path and _same_path(_field_of(r), g.path)), None)
        or next(iter(pair), None)
    )


def _base(relation_id: str) -> str:
    return re.sub(r"\s*\(.*\)\s*$", "", relation_id)


def score_set(draft: SetDraft, gold: SetGold) -> SetEval:
    """A set's relations against the set gold (see the module doc). A gold row's alternatives
    ("<id> (… alternative)") are other accepted designs: the set's relation is judged against
    the one its design matches; an alternative with no main row counts only when chosen."""
    mains = [r for r in gold.relations if not _alternative(r.id)]
    alternatives = [r for r in gold.relations if _alternative(r.id)]
    scores = []
    used: set[str] = set()
    for g in mains:
        found = _pick(g, draft, used)
        options = [g, *(a for a in alternatives if _base(a.id) == g.id)]
        if found is not None:
            used.add(found.id)
            chosen = next(
                (o for o in options if (o.kind, o.cardinality) == (found.kind, found.cardinality)),
                None,
            )
            verdict = "correct" if chosen is not None else "wrong"
        else:
            chosen, verdict = None, "missed"
        row = chosen or g
        sources = {api: _source_verdict(src, found, api) for api, src in row.apis.items()}
        scores.append(
            RelationScore(row.id, row.from_, row.to, verdict, found.id if found else None, sources)
        )
    for a in alternatives:  # an alternative of no main row: only when the set chose it
        if any(_base(a.id) == m.id for m in mains):
            continue
        found = _pick(a, draft, used)
        if found is None or (found.kind, found.cardinality) != (a.kind, a.cardinality):
            continue
        used.add(found.id)
        sources = {api: _source_verdict(src, found, api) for api, src in a.apis.items()}
        scores.append(RelationScore(a.id, a.from_, a.to, "correct", found.id, sources))
    invented = tuple(r.id for r in draft.relations if r.id not in used)
    return SetEval(gold.source, gold.held_out, tuple(scores), invented)
