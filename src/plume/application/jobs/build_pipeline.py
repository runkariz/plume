"""Job: import -> chunk -> embed -> facts -> seal -> tag, one event per step.

Each step is idempotent per build, so a failed run can be repeated. Re-running the same package
finds the sealed build (same build id) and only moves the tag. The eval gate and export steps
join in slice 4.
"""

from collections.abc import Callable
from typing import Any, TypeVar

from plume.application.dto import GateSummary, PipelineResult, TagResult
from plume.application.eval.run_eval_gate import RunEvalGate
from plume.application.knowledge.chunk_documents import ChunkDocuments
from plume.application.knowledge.embed_build import EmbedBuild
from plume.application.knowledge.extract_facts import ExtractFacts
from plume.application.knowledge.import_package import ImportPackage
from plume.application.knowledge.release_notes import ReleaseNotes
from plume.application.knowledge.seal_build import SealBuild
from plume.application.knowledge.tag_build import TagBuild
from plume.application.ports.eval_repo import GoldSource
from plume.application.ports.job_events import EventStatus, JobEvent, JobEvents
from plume.application.ports.release_notes_repo import PackageMetaReader
from plume.application.ports.table_stats import TableStats
from plume.domain.knowledge.api import ApiId
from plume.domain.shared.ids import BuildId

T = TypeVar("T")


class BuildPipeline:
    def __init__(
        self,
        import_package: ImportPackage,
        chunk: ChunkDocuments,
        embed: EmbedBuild,
        facts: ExtractFacts,
        seal: SealBuild,
        tag: TagBuild,
        events: JobEvents,
        evaluate: RunEvalGate | None = None,
        gold: GoldSource | None = None,
        notes: ReleaseNotes | None = None,
        package_meta: PackageMetaReader | None = None,
        stats: TableStats | None = None,
    ) -> None:
        self._stats = stats  # planner statistics refreshed after the rows are written
        self._notes = notes
        self._package_meta = package_meta
        self._import = import_package
        self._chunk = chunk
        self._embed = embed
        self._facts = facts
        self._seal = seal
        self._tag = tag
        self._events = events
        self._evaluate = evaluate
        self._gold = gold

    def _step(self, job_id: str, step: str, run: Callable[[], T], source: str = "plume") -> T:
        self._events.emit(JobEvent(job_id, step, EventStatus.STARTED, source=source))
        try:
            result = run()
        except Exception as exc:
            self._events.emit(
                JobEvent(job_id, step, EventStatus.FAILED, message=str(exc), source=source)
            )
            raise
        self._events.emit(JobEvent(job_id, step, EventStatus.DONE, source=source))
        return result

    def _release_notes(
        self, job_id: str, ref: str, api_id: ApiId, build_id: BuildId
    ) -> dict[str, Any] | None:
        """Notes against the build `latest` points to, before the tag moves. Never fails or
        holds a load (the maintainer reviews afterwards)."""
        if self._notes is None:
            return None
        self._events.emit(JobEvent(job_id, "notes", EventStatus.STARTED))
        try:
            meta = self._package_meta.read(ref) if self._package_meta else None
            notes = self._notes.on_load(api_id, build_id, meta)
        except Exception as exc:
            self._events.emit(JobEvent(job_id, "notes", EventStatus.FAILED, message=str(exc)))
            return None
        if notes is None:
            self._events.emit(
                JobEvent(job_id, "notes", EventStatus.SKIPPED, message="no previous build")
            )
            return None
        summary = {
            "from": notes["from"],
            "to": notes["to"],
            "counts": notes["counts"],
            "docsUpdated": notes.get("docsUpdated"),
            "needsAttention": notes["needsAttention"],
            "attentionReason": notes["attentionReason"],
        }
        self._events.emit(
            JobEvent(
                job_id,
                "notes",
                EventStatus.DONE,
                message=notes["attentionReason"] or "",
                data=summary,
            )
        )
        return summary

    def execute(
        self,
        job_id: str,
        ref: str,
        tag: str | None = "latest",
        api_id: ApiId | None = None,
        gold_ref: str | None = None,
    ) -> PipelineResult:
        imported = self._step(job_id, "import", lambda: self._import.execute(ref, api_id))
        build_id = imported.build_id
        chunks = embedded = from_cache = facts = 0
        if imported.already_sealed:
            for step in ("chunk", "embed", "facts", "seal"):
                self._events.emit(
                    JobEvent(job_id, step, EventStatus.SKIPPED, message="build already sealed")
                )
        else:
            chunks = self._step(
                job_id, "chunk", lambda: self._chunk.execute(build_id), source="postgres"
            )

            def progress(done: int, total: int) -> None:
                self._events.emit(
                    JobEvent(
                        job_id,
                        "embed",
                        EventStatus.PROGRESS,
                        source="embedder",
                        data={"done": done, "total": total},
                    )
                )

            embed = self._step(
                job_id, "embed", lambda: self._embed.execute(build_id, progress), "embedder"
            )
            embedded, from_cache = embed.embedded, embed.from_cache
            facts = self._step(
                job_id, "facts", lambda: self._facts.execute(build_id), source="postgres"
            )
            self._step(job_id, "seal", lambda: self._seal.execute(build_id), source="postgres")
            if self._stats is not None:  # before the eval gate's searches and the tag
                stats = self._stats
                self._step(job_id, "analyze", stats.refresh, source="postgres")
        gate: GateSummary | None = None
        gold_ref = gold_ref or (self._gold.for_api(imported.api_id.value) if self._gold else None)
        evaluate = self._evaluate
        if gold_ref is not None and evaluate is not None and self._gold is not None:
            gold, gold_hash = self._gold.load(gold_ref)
            run = self._step(
                job_id, "evaluate", lambda: evaluate.execute(build_id, gold, gold_hash, store=True)
            )
            gate = GateSummary(
                passed=run.decision.passed,
                message=run.decision.message,
                metrics=run.record.metrics.as_dict(),
                baseline=run.baseline.build_id.value if run.baseline else None,
            )
            self._events.emit(
                JobEvent(
                    job_id,
                    "evaluate",
                    EventStatus.PROGRESS,
                    message=gate.message,
                    data=dict(gate.metrics),
                )
            )
        else:
            self._events.emit(
                JobEvent(job_id, "evaluate", EventStatus.SKIPPED, message="no gold questions")
            )
        notes = self._release_notes(job_id, ref, imported.api_id, build_id)
        tagged: TagResult | None = None
        if tag is not None and (gate is None or gate.passed):
            tagged = self._step(job_id, "tag", lambda: self._tag.execute(build_id, tag))
        elif tag is not None:
            self._events.emit(
                JobEvent(job_id, "tag", EventStatus.SKIPPED, message="quality gate failed")
            )
        return PipelineResult(
            api_id=imported.api_id,
            build_id=build_id,
            reused=imported.already_sealed,
            documents=imported.documents,
            chunks=chunks,
            embedded=embedded,
            from_cache=from_cache,
            facts=facts,
            tag=tagged,
            gate=gate,
            notes=notes,
        )
