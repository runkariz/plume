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
    paths = {_path(p.path) for p in src.paths}
    gold_paths = {_path(p) for p in gold.paths}
    if paths & gold_paths:
        return "correct"
    if gold.fetch and src.fetch and _fetch(src.fetch).endswith(_fetch(gold.fetch)):
        return "correct"
    return "wrong"


def score_set(draft: SetDraft, gold: SetGold) -> SetEval:
    """A set's relations against the set gold (see the module doc)."""
    by_pair: dict[tuple[str, str], Relation] = {
        (_member(r.from_), _member(r.to)): r for r in draft.relations
    }
    scores = []
    matched: set[str] = set()
    for g in gold.relations:
        found = by_pair.get((_member(g.from_), _member(g.to)))
        if found is not None:
            matched.add(found.id)
            design_ok = found.kind == g.kind and found.cardinality == g.cardinality
            verdict = "correct" if design_ok else "wrong"
        else:
            verdict = "missed"
        sources = {api: _source_verdict(src, found, api) for api, src in g.apis.items()}
        scores.append(
            RelationScore(g.id, g.from_, g.to, verdict, found.id if found else None, sources)
        )
    invented = tuple(r.id for r in draft.relations if r.id not in matched)
    return SetEval(gold.source, gold.held_out, tuple(scores), invented)
