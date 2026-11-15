"""Job: import -> chunk -> embed -> facts -> seal -> tag, one event per step.

Each step is idempotent per build, so a failed run can be repeated. Re-running the same package
finds the sealed build (same build id) and only moves the tag. The eval gate and export steps
join in slice 4.
"""

from collections.abc import Callable
from typing import TypeVar

from plume.application.dto import PipelineResult, TagResult
from plume.application.knowledge.chunk_documents import ChunkDocuments
from plume.application.knowledge.embed_build import EmbedBuild
from plume.application.knowledge.extract_facts import ExtractFacts
from plume.application.knowledge.import_package import ImportPackage
from plume.application.knowledge.seal_build import SealBuild
from plume.application.knowledge.tag_build import TagBuild
from plume.application.ports.job_events import EventStatus, JobEvent, JobEvents
from plume.domain.knowledge.api import ApiId

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
    ) -> None:
        self._import = import_package
        self._chunk = chunk
        self._embed = embed
        self._facts = facts
        self._seal = seal
        self._tag = tag
        self._events = events

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

    def execute(
        self, job_id: str, ref: str, tag: str | None = "latest", api_id: ApiId | None = None
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
        tagged: TagResult | None = None
        if tag is not None:
            tagged = self._step(job_id, "tag", lambda: self._tag.execute(build_id, tag))
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
        )
