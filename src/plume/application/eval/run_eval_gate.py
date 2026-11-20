"""Use case: run a gold set against a build (draft or sealed) and decide the release gate.

The baseline is the build the ``latest`` tag points at (the live release), when it has an eval
for the same gold set.
"""

from dataclasses import dataclass
from functools import partial

from plume.application.errors import ApplicationError
from plume.application.knowledge._builds import require_build
from plume.application.ports.build_repo import BuildRepo
from plume.application.ports.document_repo import DocumentRepo
from plume.application.ports.embedder import Embedder, Vector
from plume.application.ports.eval_repo import EvalRecord, EvalRepo
from plume.application.ports.search_index import FactQuery, SearchIndex
from plume.application.ports.tag_repo import TagRepo
from plume.application.reader.use_cases import (
    DEFAULT_FUSION,
    WIDER_POOL,
    all_endpoint_ids,
    fuse_hits,
    own_auth_docs,
    rank_order,
)
from plume.domain.eval.gate import GateDecision, GatePolicy, decide
from plume.domain.eval.gold import GoldKind, GoldSet
from plume.domain.eval.metrics import K, QuestionOutcome, score
from plume.domain.knowledge.document import DocumentKind
from plume.domain.knowledge.ranking import Fusion
from plume.domain.knowledge.tag import LATEST, TagName
from plume.domain.shared.clock import Clock
from plume.domain.shared.ids import BuildId

POOL = 20


@dataclass(frozen=True, slots=True)
class EvalRun:
    record: EvalRecord
    decision: GateDecision
    outcomes: tuple[QuestionOutcome, ...]
    baseline: EvalRecord | None
    stored: bool = True  # kept as the build's eval (False: an ad-hoc run)


class RunEvalGate:
    def __init__(
        self,
        builds: BuildRepo,
        tags: TagRepo,
        documents: DocumentRepo,
        index: SearchIndex,
        facts: FactQuery,
        embedder: Embedder,
        evals: EvalRepo,
        clock: Clock,
        policy: GatePolicy | None = None,
        fusion: Fusion = DEFAULT_FUSION,
    ) -> None:
        self._fusion = fusion
        self._builds = builds
        self._tags = tags
        self._documents = documents
        self._index = index
        self._facts = facts
        self._embedder = embedder
        self._evals = evals
        self._clock = clock
        self._policy = policy or GatePolicy()

    def _endpoints_for(self, build_id: BuildId, vector: Vector) -> list[str]:
        hits = self._index.dense(build_id, vector, WIDER_POOL, (DocumentKind.ENDPOINT,))
        return list(dict.fromkeys(h.doc_id for h in hits))

    def execute(
        self, build_id: BuildId, gold: GoldSet, gold_hash: str, *, store: bool | None = None
    ) -> EvalRun:
        """Score the build on the gold set. ``store``: keep it as the build's eval (its quality
        card and gate). None: only when the build has no eval yet or this is the same gold set
        (by hash) as the stored one, the gate eval plume load ran; another gold is ad hoc and
        never replaces it (tester-gold scoring replaced Mirakl's 150-question card)."""
        if store is None:
            stored = self._evals.get(build_id)
            store = stored is None or stored.gold_hash == gold_hash
        build = require_build(self._builds, build_id)
        if build.spec is not None and build.spec.embed_model != self._embedder.model:
            # Scores from vectors of two different models would be meaningless, not low.
            raise ApplicationError(
                f"build {build_id} was embedded with {build.spec.embed_model}; this server "
                f"embeds queries with {self._embedder.model}: evaluate it with that embedder, "
                "or load the package again with this one"
            )
        known = {s.doc_id for s in self._index.browse(build_id, (), None, 100_000, 0)[0]}
        outcomes: list[QuestionOutcome] = []
        details: list[dict[str, object]] = []
        endpoints = partial(all_endpoint_ids, self._index, build_id)
        for q in gold.questions:
            if q.kind is GoldKind.SEARCH:
                vector = self._embedder.embed_query(q.question)
                dense = self._index.dense(build_id, vector, POOL)
                text = self._index.text(build_id, q.question, POOL)
                fused = [h.doc_id for h in fuse_hits(dense, text, q.question, POOL, self._fusion)]
                wider = partial(self._endpoints_for, build_id, vector)
                own = partial(
                    own_auth_docs, self._index, build_id, (DocumentKind.AUTH, DocumentKind.APP)
                )
                ranked = tuple(
                    rank_order(
                        self._documents,
                        build_id,
                        fused,
                        K,
                        wider,
                        q.question,
                        own,
                        endpoints,
                    )
                )
                # Expected docs are alternatives: missing only when none of them is in the build.
                present = [d for d in q.expect_docs if d in known]
                missing = () if present else tuple(q.expect_docs)
                o = QuestionOutcome(q.qid, q.kind, ranked=ranked, missing_expected=missing)
                rank = o.first_hit_rank(q.expect_docs)
                details.append(
                    {
                        "qid": q.qid,
                        "kind": q.kind.value,
                        "source": q.source,
                        "rank": rank,
                        "top": list(ranked[:K]),
                        "missing": list(missing),
                    }
                )
            else:
                found = self._facts.find(build_id, q.fact_name or "")
                incomplete = self._facts.incomplete_owners(build_id)
                o = QuestionOutcome(q.qid, q.kind, found=bool(found), complete=not incomplete)
                details.append(
                    {
                        "qid": q.qid,
                        "kind": q.kind.value,
                        "found": bool(found),
                        "complete": not incomplete,
                    }
                )
            outcomes.append(o)
        metrics = score(gold.questions, outcomes)

        baseline: EvalRecord | None = None
        live = self._tags.get(build.api_id, TagName(LATEST))
        if live is not None and live.build_id != build_id:
            candidate = self._evals.get(live.build_id)
            if candidate is not None and candidate.gold_hash == gold_hash:
                baseline = candidate
        decision = decide(self._policy, metrics, baseline.metrics if baseline else None)
        record = EvalRecord(
            build_id=build_id,
            api_id=build.api_id,
            gold_hash=gold_hash,
            metrics=metrics,
            passed=decision.passed,
            message=decision.message,
            baseline_build=baseline.build_id if baseline else None,
            evaluated_at=self._clock.now(),
            details=tuple(details),
        )
        if store:
            self._evals.save(record)
        return EvalRun(record, decision, tuple(outcomes), baseline, stored=store)
