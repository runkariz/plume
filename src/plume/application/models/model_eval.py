"""Use case: score stored canonical models (or a model set's members) against model gold, and
the release gate built on it. Gold is read here only: the generator's prompts and examples are
never built from it (an architecture test keeps the generator from importing gold)."""

from collections.abc import Callable
from dataclasses import dataclass, replace

from plume.application.errors import NotFoundError
from plume.application.models.concepts import concept_parts
from plume.application.ports.model_gold import ModelGoldSource
from plume.application.ports.model_repo import ModelRepo
from plume.application.ports.model_set_repo import ModelSetRepo
from plume.domain.models.model_eval import ModelEval, ModelGatePolicy, score
from plume.domain.models.model_gold import GoldModel
from plume.domain.models.release import GateFailure
from plume.domain.models.set_gold import SetEval, score_set
from plume.domain.models.snapshot import ModelSnapshot, PinnedInput
from plume.domain.models.validation import Oracle

OracleFor = Callable[[tuple[PinnedInput, ...]], Oracle]


@dataclass(frozen=True, slots=True)
class EvalReport:
    target: str  # model or set id
    results: tuple[tuple[str, ModelEval], ...]  # (model id, result)
    relations: tuple[SetEval, ...] = ()  # a set's relations against the set golds covering it

    def totals(self, held_out: bool) -> dict[str, object]:
        rows = [r for _, r in self.results if r.held_out == held_out]
        counts: dict[str, int] = {}
        for r in rows:
            for k, v in r.counts.items():
                counts[k] = counts.get(k, 0) + v
        correct = counts.get("correct", 0)
        judged = correct + counts.get("wrong", 0) + counts.get("invented", 0)
        expected = sum(1 for r in rows for c in r.cells if c.expected)
        return {
            "models": len(rows),
            "counts": counts,
            "invented": sum(r.invented for r in rows),
            "precision": round(correct / judged, 4) if judged else None,
            "recall": round(correct / expected, 4) if expected else None,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "target": self.target,
            "tuning": self.totals(held_out=False),
            "heldOut": self.totals(held_out=True),
            "results": [{"modelId": m, **r.as_dict()} for m, r in self.results],
            "relations": [r.as_dict() for r in self.relations],
        }


def _set_member(name: str) -> str:
    return "".join(c for c in name.lower() if c.isalnum())


def _without(gold: GoldModel, held: set[str]) -> GoldModel:
    """The gold without the top-level fields another member holds (by name or alias)."""
    if not held:
        return gold
    keep = tuple(f for f in gold.fields if not {_set_member(n) for n in f.names} & held)
    return replace(gold, fields=keep)


def _part(gold: GoldModel, field: str, concept: str) -> GoldModel | None:
    """The gold of an embedded member: the owner gold's field (lines[] -> Order line)."""
    key = _set_member(field)
    sub = next((f for f in gold.fields if key in {_set_member(n) for n in f.names}), None)
    if sub is None or not sub.fields:
        return None
    return replace(gold, concept=concept, fields=sub.fields, operations=(),
                   source=f"{gold.source}#{field}")  # fmt: skip


def _covers(gold: GoldModel, snap: ModelSnapshot) -> bool:
    """Gold covers a model when their main concepts meet ("Product / Offer" covers Product) and
    they share an API."""
    apis = {i.api for i in snap.inputs}
    same = set(concept_parts(gold.concept)[0]) & set(concept_parts(snap.concept)[0])
    return bool(same) and bool(apis & set(gold.apis))


class ModelEvaluation:
    def __init__(
        self,
        models: ModelRepo,
        sets: ModelSetRepo | None,
        oracle_for: OracleFor,
        gold: ModelGoldSource,
        policy: ModelGatePolicy | None = None,
    ) -> None:
        self._models = models
        self._sets = sets
        self._oracle_for = oracle_for
        self._gold = gold
        self._policy = policy or ModelGatePolicy()

    def _score(self, snap: ModelSnapshot, gold: GoldModel) -> ModelEval:
        oracle = self._oracle_for(snap.inputs)
        apis = tuple(i.api for i in snap.inputs)
        return score(snap.draft, gold, apis, oracle.field_exists, oracle.endpoint_exists)

    def _members(self, target: str) -> list[ModelSnapshot]:
        snap = self._models.get_snapshot(target)
        if snap is not None:
            return [snap]
        stored = self._sets.get_set(target) if self._sets is not None else None
        if stored is None:
            raise NotFoundError(f"no model or model set {target}")
        out = []
        for m in stored.draft.members:
            member = self._models.get_snapshot(m.model_id)
            if member is not None:
                out.append(member)
        return out

    def evaluate(self, target: str, gold_ref: str | None = None) -> EvalReport:
        """Score a model, or each member of a set, against the gold models that cover its
        concept: those of ``gold_ref``, else every configured gold file."""
        golds = self._gold.load(gold_ref) if gold_ref else self._gold.all()
        results = self._member_scores(target, golds)
        relations = self._relations(target, gold_ref)
        if gold_ref and not results and not relations:
            concepts = ", ".join(sorted({g.concept for g in golds}))
            raise NotFoundError(f"{gold_ref} has no gold for {target} (it covers: {concepts})")
        return EvalReport(target, tuple(results), relations)

    def _member_scores(
        self, target: str, golds: tuple[GoldModel, ...]
    ) -> list[tuple[str, ModelEval]]:
        """A model against its concept golds. A set's member against its concept gold without
        the fields its embedded relations hold (order-prod's lines[] and shipping_address are
        the Order line and Address members); an embedded member against that part of its
        owner's gold (Order line against order-prod's lines[])."""
        snaps = self._members(target)
        stored = self._sets.get_set(target) if self._sets is not None else None
        if stored is None:
            return [
                (s.snapshot_id, self._score(s, g)) for s in snaps for g in golds if _covers(g, s)
            ]
        by_concept = {_set_member(m.concept): self._models.get_snapshot(m.model_id)
                      for m in stored.draft.members}  # fmt: skip
        embedded = [(r.from_, r.to, r.embed_field) for r in stored.draft.relations
                    if r.kind == "embedded" and r.embed_field]  # fmt: skip
        out: list[tuple[str, ModelEval]] = []
        for snap in snaps:
            held = {
                _set_member(f)
                for frm, _, f in embedded
                if _set_member(frm) == _set_member(snap.concept)
            }
            for g in golds:
                if _covers(g, snap):
                    out.append((snap.snapshot_id, self._score(snap, _without(g, held))))
        for frm, to, field in embedded:
            owner, member = by_concept.get(_set_member(frm)), by_concept.get(_set_member(to))
            if owner is None or member is None:
                continue
            for g in golds:
                part = _part(g, field, to) if _covers(g, owner) else None
                if part is not None and not any(_covers(x, member) for x in golds):
                    out.append((member.snapshot_id, self._score(member, part)))
        return out

    def _relations(self, target: str, gold_ref: str | None) -> tuple[SetEval, ...]:
        """A set's relations against the set golds that cover it (same members, an API in
        common); a model is no set."""
        stored = self._sets.get_set(target) if self._sets is not None else None
        if stored is None:
            return ()
        golds = self._gold.load_sets(gold_ref) if gold_ref else self._gold.sets()
        members = {_set_member(m.concept) for m in stored.draft.members}
        apis = {i.api for i in stored.inputs}
        return tuple(
            score_set(stored.draft, g)
            for g in golds
            if {_set_member(m) for m in g.members} <= members and apis & set(g.apis)
        )

    def gate(self, snap: ModelSnapshot) -> list[GateFailure]:
        """Why ``snap`` may not be released (empty: it may). Without gold for its concept it may
        (not evaluated)."""
        out: list[GateFailure] = []
        for g in self._gold.all():
            if _covers(g, snap):
                out.extend(
                    GateFailure(f"{g.source}: {f.message}", f.overridable)
                    for f in self._policy.failures(self._score(snap, g))
                )
        return out
