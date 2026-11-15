"""A full set of fakes wired like the bootstrap container (for use-case tests)."""

from dataclasses import dataclass, field
from pathlib import Path

from plume.application.eval.run_eval_gate import RunEvalGate
from plume.application.jobs.build_pipeline import BuildPipeline
from plume.application.jobs.maintainer import MaintainerJobs
from plume.application.knowledge.chunk_documents import ChunkDocuments
from plume.application.knowledge.embed_build import EmbedBuild
from plume.application.knowledge.export_dump import ExportDump, RestoreDump
from plume.application.knowledge.extract_facts import ExtractFacts
from plume.application.knowledge.import_package import ImportPackage
from plume.application.knowledge.seal_build import SealBuild
from plume.application.knowledge.tag_build import TagBuild
from plume.application.ports.job_events import JobEvents
from plume.application.ports.package_source import PackageSource
from plume.application.reader.resolve import BuildResolver
from plume.application.reader.use_cases import (
    BrowseDocuments,
    CheckCall,
    FindFact,
    GetDocument,
    ListApiOverviews,
    SearchDocs,
)
from plume.domain.eval.gate import GatePolicy
from plume.infrastructure.dumps.local_fs import LocalDumpStore
from plume.infrastructure.jobs.package_storage import LocalPackageStorage
from plume.infrastructure.jobs.thread_runner import InlineJobRunner
from plume.infrastructure.sources.gold_file import JsonGoldSource
from plume.infrastructure.sources.stream_package import StreamPackageSource
from tests.fakes.jobs import InMemoryBuildImporter, InMemoryJobEventLog, InMemoryJobRepo
from tests.fakes.knowledge import (
    DeterministicEmbedder,
    FakeClock,
    InMemoryApiRepo,
    InMemoryBuildRepo,
    InMemoryDocumentRepo,
    InMemoryEvalRepo,
    InMemoryFactIndex,
    InMemoryTagRepo,
    InMemoryVectorIndex,
    RecordingEvents,
)
from tests.fakes.search import InMemoryFactQuery, InMemorySearchIndex


@dataclass
class FakeStack:
    source: PackageSource = field(default_factory=StreamPackageSource)
    apis: InMemoryApiRepo = field(default_factory=InMemoryApiRepo)
    builds: InMemoryBuildRepo = field(default_factory=InMemoryBuildRepo)
    tags: InMemoryTagRepo = field(default_factory=InMemoryTagRepo)
    documents: InMemoryDocumentRepo = field(default_factory=InMemoryDocumentRepo)
    facts: InMemoryFactIndex = field(default_factory=InMemoryFactIndex)
    embedder: DeterministicEmbedder = field(default_factory=DeterministicEmbedder)
    clock: FakeClock = field(default_factory=FakeClock)
    events: RecordingEvents = field(default_factory=RecordingEvents)
    batch_size: int = 8
    max_chars: int = 6000
    evals: InMemoryEvalRepo = field(default_factory=InMemoryEvalRepo)
    gold: JsonGoldSource = field(default_factory=JsonGoldSource)
    policy: GatePolicy = field(default_factory=GatePolicy)
    data_dir: Path | None = None

    def __post_init__(self) -> None:
        self.vectors = InMemoryVectorIndex(self.documents)
        self.search_index = InMemorySearchIndex(self.documents)
        self.fact_query = InMemoryFactQuery(self.facts, self.documents)

    def import_package(self) -> ImportPackage:
        return ImportPackage(
            self.source,
            self.apis,
            self.builds,
            self.documents,
            self.clock,
            self.embedder.model,
            self.embedder.dims,
        )

    def chunk(self) -> ChunkDocuments:
        return ChunkDocuments(self.builds, self.documents, self.max_chars)

    def embed(self) -> EmbedBuild:
        return EmbedBuild(self.builds, self.documents, self.vectors, self.embedder, self.batch_size)

    def extract_facts(self) -> ExtractFacts:
        return ExtractFacts(self.builds, self.documents, self.facts)

    def seal(self) -> SealBuild:
        return SealBuild(self.builds, self.vectors, self.clock)

    def tag(self) -> TagBuild:
        return TagBuild(self.builds, self.tags, self.evals)

    def run_eval(self) -> RunEvalGate:
        return RunEvalGate(
            self.builds,
            self.tags,
            self.documents,
            self.search_index,
            self.fact_query,
            self.embedder,
            self.evals,
            self.clock,
            self.policy,
        )

    def pipeline(self, events: JobEvents | None = None) -> BuildPipeline:
        return BuildPipeline(
            self.import_package(),
            self.chunk(),
            self.embed(),
            self.extract_facts(),
            self.seal(),
            self.tag(),
            events or self.events,
            evaluate=self.run_eval(),
            gold=self.gold,
        )

    def dumps(self) -> LocalDumpStore:
        assert self.data_dir is not None, "FakeStack(data_dir=...) is needed for dumps"
        return LocalDumpStore(self.data_dir / "dumps")

    def export(self) -> ExportDump:
        return ExportDump(
            self.apis,
            self.builds,
            self.documents,
            self.vectors,
            self.facts,
            self.evals,
            self.dumps(),
        )

    def restore(self) -> RestoreDump:
        return RestoreDump(self.dumps(), InMemoryBuildImporter(self))

    def maintainer(self) -> MaintainerJobs:
        assert self.data_dir is not None
        if not hasattr(self, "_jobs"):
            self._jobs = InMemoryJobRepo()
            self._job_events = InMemoryJobEventLog()
        return MaintainerJobs(
            jobs=self._jobs,
            events=self._job_events,
            storage=LocalPackageStorage(self.data_dir, 50 * 1024 * 1024),
            source=self.source,
            builds=self.builds,
            tags=self.tags,
            vectors=self.vectors,
            evals=self.evals,
            embedder=self.embedder,
            pipeline=self.pipeline,
            tag_build=self.tag(),
            export=self.export(),
            runner=InlineJobRunner(),
            max_chars=self.max_chars,
        )

    # -- reader --------------------------------------------------------------------------------

    def resolver(self) -> BuildResolver:
        return BuildResolver(self.apis, self.builds, self.tags)

    def overviews(self) -> ListApiOverviews:
        return ListApiOverviews(self.apis, self.builds, self.tags, self.search_index)

    def browse(self) -> BrowseDocuments:
        return BrowseDocuments(self.resolver(), self.search_index)

    def search(self) -> SearchDocs:
        return SearchDocs(self.resolver(), self.search_index, self.embedder, self.documents)

    def get_document(self) -> GetDocument:
        return GetDocument(self.resolver(), self.documents)

    def find_fact(self) -> FindFact:
        return FindFact(self.resolver(), self.fact_query, self.search_index)

    def check_call(self) -> CheckCall:
        return CheckCall(self.resolver(), self.fact_query, self.search_index)

    def load(self, path: str, tag: str | None = "latest") -> str:
        """Run the pipeline on a package; returns the build id."""
        return self.pipeline().execute("job-test", path, tag=tag).build_id.value
