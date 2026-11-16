"""A full set of fakes wired like the bootstrap container (for use-case tests)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plume.application.eval.run_eval_gate import RunEvalGate
from plume.application.jobs.build_pipeline import BuildPipeline
from plume.application.jobs.maintainer import MaintainerJobs
from plume.application.knowledge.api_display import ApiDisplayName
from plume.application.knowledge.chunk_documents import ChunkDocuments
from plume.application.knowledge.embed_build import EmbedBuild
from plume.application.knowledge.export_dump import ExportDump, RestoreDump
from plume.application.knowledge.extract_facts import ExtractFacts
from plume.application.knowledge.import_package import ImportPackage
from plume.application.knowledge.public_changes import PublicChanges
from plume.application.knowledge.release_notes import ReleaseNotes
from plume.application.knowledge.remove_api import RemoveApi
from plume.application.knowledge.seal_build import SealBuild
from plume.application.knowledge.tag_build import TagBuild
from plume.application.models.collections import Collections
from plume.application.models.concepts import SuggestConcepts
from plume.application.models.generate import GenerateModels
from plume.application.models.impact import ModelImpact
from plume.application.models.model_sets import ModelSets
from plume.application.models.relations import SuggestRelated
from plume.application.models.sessions import ModelSessions
from plume.application.ports.job_events import JobEvents
from plume.application.ports.package_source import PackageSource
from plume.application.reader.resolve import BuildResolver
from plume.application.reader.sections import PackageSections
from plume.application.reader.use_cases import (
    BrowseDocuments,
    CheckCall,
    FindFact,
    GetDocument,
    ListApiOverviews,
    SearchDocs,
)
from plume.domain.eval.gate import GatePolicy
from plume.domain.knowledge.api import ApiId
from plume.infrastructure.dumps.local_fs import LocalDumpStore
from plume.infrastructure.jobs.package_storage import LocalPackageStorage
from plume.infrastructure.jobs.thread_runner import InlineJobRunner
from plume.infrastructure.sources.gold_file import JsonGoldSource
from plume.infrastructure.sources.package_meta import StreamPackageMetaReader
from plume.infrastructure.sources.stream_package import StreamPackageSource
from tests.fakes.jobs import InMemoryBuildImporter, InMemoryJobEventLog, InMemoryJobRepo
from tests.fakes.knowledge import (
    DeterministicEmbedder,
    FakeClock,
    InMemoryApiRepo,
    InMemoryAssetRepo,
    InMemoryBuildRepo,
    InMemoryDocumentRepo,
    InMemoryEvalRepo,
    InMemoryFactIndex,
    InMemoryTagRepo,
    InMemoryVectorIndex,
    RecordingEvents,
)
from tests.fakes.models import (
    InMemoryCollectionRepo,
    InMemoryModelJobRepo,
    InMemoryModelRepo,
    InMemoryModelSetRepo,
    InMemoryReleaseNotesRepo,
    ScriptedModelWriter,
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
    models_repo: InMemoryModelRepo = field(default_factory=InMemoryModelRepo)
    assets: InMemoryAssetRepo = field(default_factory=InMemoryAssetRepo)
    writer: ScriptedModelWriter = field(default_factory=ScriptedModelWriter)
    model_jobs: InMemoryModelJobRepo = field(default_factory=InMemoryModelJobRepo)
    model_events: InMemoryJobEventLog = field(default_factory=InMemoryJobEventLog)
    sets_repo: InMemoryModelSetRepo = field(default_factory=InMemoryModelSetRepo)
    collections_repo: InMemoryCollectionRepo = field(default_factory=InMemoryCollectionRepo)
    notes_repo: InMemoryReleaseNotesRepo = field(default_factory=InMemoryReleaseNotesRepo)

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
            self.assets,
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
            notes=self.release_notes(),
            package_meta=StreamPackageMetaReader(),
        )

    def api_display(self) -> ApiDisplayName:
        return ApiDisplayName(self.apis)

    def remove_api(self) -> RemoveApi:
        return RemoveApi(self.apis, _FakeRemoval(self), self.models_repo, self.sets_repo)

    def public_changes(self) -> PublicChanges:
        return PublicChanges(self.notes_repo, self.tags)

    def model_impact(self) -> ModelImpact:
        return ModelImpact(self.public_changes())

    def release_notes(self) -> ReleaseNotes:
        return ReleaseNotes(
            self.builds, self.documents, self.tags, self.notes_repo, self.clock, self.evals
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
            self.assets,
            self.notes_repo,
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
        return ListApiOverviews(
            self.apis, self.builds, self.tags, self.search_index, self.evals, self.assets
        )

    def sections(self) -> PackageSections:
        return PackageSections(self.resolver(), self.search_index, self.documents, self.assets)

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

    def suggest(self) -> SuggestConcepts:
        return SuggestConcepts(self.resolver(), self.search_index, self.facts)

    def model_sets(self) -> ModelSets:
        return ModelSets(
            self.resolver(),
            self.models(),
            self.models_repo,
            self.sets_repo,
            self.suggest_related(),
            self.clock,
            self.collections(),
        )

    def collections(self) -> Collections:
        return Collections(self.collections_repo, self.models_repo, self.sets_repo, self.clock)

    def suggest_related(self) -> SuggestRelated:
        return SuggestRelated(self.resolver(), self.search_index, self.facts, self.documents)

    def models(self) -> ModelSessions:
        return ModelSessions(
            self.resolver(),
            self.search_index,
            self.fact_query,
            self.documents,
            self.models_repo,
            self.clock,
            self.collections(),
        )

    def generate(self) -> GenerateModels:
        return GenerateModels(
            self.models(),
            self.writer,
            self.model_jobs,
            self.model_events,
            InlineJobRunner(),
            self.clock,
        )


class _FakeRemoval:
    """The in-memory twin of PostgresApiRemoval (same counts, an audit list)."""

    def __init__(self, stack: FakeStack) -> None:
        self.s = stack

    def remove(
        self, api_id: ApiId, audit: Mapping[str, Any], retire: Sequence[Mapping[str, str]] = ()
    ) -> dict[str, int]:
        s, api = self.s, api_id.value
        for r in retire:
            repo = s.models_repo if r["type"] == "model" else s.sets_repo
            repo.set_visibility(r["id"], r["now"], None)
        builds = [b for b, x in s.builds.builds.items() if x.api_id.value == api]
        notes = [k for k, v in s.notes_repo.notes.items() if v.get("api") == api]
        counts = {
            "documents": sum(len(s.documents.documents.get(b, {})) for b in builds),
            "releaseNotes": len(notes),
            "packageMeta": sum(1 for b in builds if b in s.notes_repo.meta),
            "tags": sum(1 for k in s.tags.tags if k[0] == api),
            "jobs": 0,
            "evals": sum(1 for b in builds if b in s.evals.records),
            "builds": len(builds),
            "displayName": int(api in s.apis.overrides),
            "api": int(api in s.apis.apis),
        }
        for k in notes:
            del s.notes_repo.notes[k]
        for b in builds:
            s.notes_repo.meta.pop(b, None)
            s.evals.records.pop(b, None)
            for store in (s.documents.documents, s.documents.chunks, s.documents.vectors,
                          s.facts.facts):  # fmt: skip
                store.pop(b, None)
            del s.builds.builds[b]
        for tag in [t for t in s.tags.tags if t[0] == api]:
            del s.tags.tags[tag]
        s.apis.overrides.pop(api, None)
        s.apis.apis.pop(api, None)
        REMOVALS.append({"api": api, **audit, "counts": counts})
        return counts


REMOVALS: list[dict[str, Any]] = []
