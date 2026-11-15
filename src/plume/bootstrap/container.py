"""Wires ports to adapters from the settings. Tests build their own container with fakes."""

import uuid
from dataclasses import dataclass, field
from functools import cached_property

from sqlalchemy import Engine

from plume.application.eval.run_eval_gate import RunEvalGate
from plume.application.jobs.build_pipeline import BuildPipeline
from plume.application.jobs.maintainer import MaintainerJobs
from plume.application.knowledge.chunk_documents import ChunkDocuments
from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.embed_build import EmbedBuild
from plume.application.knowledge.export_dump import ExportDump, RestoreDump
from plume.application.knowledge.extract_facts import ExtractFacts
from plume.application.knowledge.import_package import ImportPackage
from plume.application.knowledge.list_builds import ListApis, ListBuilds
from plume.application.knowledge.seal_build import SealBuild
from plume.application.knowledge.tag_build import TagBuild
from plume.application.ports.embedder import Embedder
from plume.application.ports.job_events import JobEvents
from plume.application.reader.resolve import BuildResolver
from plume.application.reader.use_cases import (
    BrowseDocuments,
    CheckCall,
    FindFact,
    GetDocument,
    ListApiOverviews,
    SearchDocs,
)
from plume.application.system.migrate_schema import MigrateSchema
from plume.domain.eval.gate import GatePolicy
from plume.infrastructure.clock import SystemClock
from plume.infrastructure.db.alembic_migrator import AlembicMigrator
from plume.infrastructure.db.archive import PostgresBuildImporter
from plume.infrastructure.db.engine import make_engine
from plume.infrastructure.db.repos.api_repo import PostgresApiRepo
from plume.infrastructure.db.repos.build_repo import PostgresBuildRepo
from plume.infrastructure.db.repos.document_repo import PostgresDocumentRepo
from plume.infrastructure.db.repos.eval_repo import PostgresEvalRepo
from plume.infrastructure.db.repos.tag_repo import PostgresTagRepo
from plume.infrastructure.dumps.local_fs import LocalDumpStore
from plume.infrastructure.embeddings.gemini import GeminiEmbedder
from plume.infrastructure.embeddings.hash_embedder import HashEmbedder
from plume.infrastructure.events.log_events import LoggingJobEvents
from plume.infrastructure.jobs.package_storage import LocalPackageStorage
from plume.infrastructure.jobs.postgres_jobs import PostgresJobEventLog, PostgresJobRepo
from plume.infrastructure.jobs.thread_runner import ThreadJobRunner
from plume.infrastructure.search.pgvector_index import PgVectorIndex
from plume.infrastructure.search.postgres_fact_index import PostgresFactIndex
from plume.infrastructure.search.postgres_search import PostgresFactQuery, PostgresSearchIndex
from plume.infrastructure.settings import Settings, get_settings
from plume.infrastructure.sources.gold_file import JsonGoldSource
from plume.infrastructure.sources.stream_package import StreamPackageSource


@dataclass
class Container:
    settings: Settings = field(default_factory=get_settings)

    # -- adapters -------------------------------------------------------------------------------

    @cached_property
    def engine(self) -> Engine:
        return make_engine(self.settings.sqlalchemy_url)

    @cached_property
    def clock(self) -> SystemClock:
        return SystemClock()

    @cached_property
    def apis(self) -> PostgresApiRepo:
        return PostgresApiRepo(self.engine)

    @cached_property
    def builds(self) -> PostgresBuildRepo:
        return PostgresBuildRepo(self.engine)

    @cached_property
    def tags(self) -> PostgresTagRepo:
        return PostgresTagRepo(self.engine)

    @cached_property
    def documents(self) -> PostgresDocumentRepo:
        return PostgresDocumentRepo(self.engine)

    @cached_property
    def vectors(self) -> PgVectorIndex:
        return PgVectorIndex(self.engine)

    @cached_property
    def facts(self) -> PostgresFactIndex:
        return PostgresFactIndex(self.engine)

    @cached_property
    def evals(self) -> PostgresEvalRepo:
        return PostgresEvalRepo(self.engine)

    @cached_property
    def gold(self) -> JsonGoldSource:
        return JsonGoldSource(self.settings.gold_dirs)

    @cached_property
    def dumps(self) -> LocalDumpStore:
        return LocalDumpStore(self.settings.data_dir / "dumps")

    @cached_property
    def importer(self) -> PostgresBuildImporter:
        return PostgresBuildImporter(self.engine)

    @cached_property
    def search_index(self) -> PostgresSearchIndex:
        return PostgresSearchIndex(self.engine)

    @cached_property
    def fact_query(self) -> PostgresFactQuery:
        return PostgresFactQuery(self.engine)

    @cached_property
    def embedder(self) -> Embedder:
        s = self.settings
        kind = s.resolved_embedder
        if kind == "hash":
            return HashEmbedder(s.embed_dims)
        key = s.vertex_api_key if kind == "vertex" else s.gemini_api_key
        return GeminiEmbedder(
            api_key=key.get_secret_value() if key is not None else "",
            backend=kind,
            model=s.embed_model,
            dims=s.embed_dims,
            batch_size=s.embed_batch_size,
        )

    @cached_property
    def events(self) -> JobEvents:
        return LoggingJobEvents()

    # -- use cases ------------------------------------------------------------------------------

    def migrate_schema(self) -> MigrateSchema:
        return MigrateSchema(AlembicMigrator(self.engine))

    @cached_property
    def jobs(self) -> PostgresJobRepo:
        return PostgresJobRepo(self.engine)

    @cached_property
    def job_events(self) -> PostgresJobEventLog:
        return PostgresJobEventLog(self.engine)

    @cached_property
    def job_runner(self) -> ThreadJobRunner:
        return ThreadJobRunner()

    def maintainer(self) -> MaintainerJobs:
        s = self.settings
        return MaintainerJobs(
            jobs=self.jobs,
            events=self.job_events,
            storage=LocalPackageStorage(s.data_dir, s.max_upload_bytes),
            source=StreamPackageSource(),
            builds=self.builds,
            tags=self.tags,
            vectors=self.vectors,
            evals=self.evals,
            embedder=self.embedder,
            pipeline=self.build_pipeline,
            tag_build=self.tag_build(),
            export=self.export_dump(),
            runner=self.job_runner,
            max_chars=s.chunk_max_chars,
        )

    def build_pipeline(self, events: JobEvents | None = None) -> BuildPipeline:
        embedder = self.embedder
        return BuildPipeline(
            import_package=ImportPackage(
                StreamPackageSource(),
                self.apis,
                self.builds,
                self.documents,
                self.clock,
                embed_model=embedder.model,
                dims=embedder.dims,
            ),
            chunk=ChunkDocuments(self.builds, self.documents, self.settings.chunk_max_chars),
            embed=EmbedBuild(self.builds, self.documents, self.vectors, embedder),
            facts=ExtractFacts(self.builds, self.documents, self.facts),
            seal=SealBuild(self.builds, self.vectors, self.clock),
            tag=self.tag_build(),
            events=events or self.events,
            evaluate=self.run_eval(),
            gold=self.gold,
        )

    def list_apis(self) -> ListApis:
        return ListApis(self.apis)

    def list_builds(self) -> ListBuilds:
        return ListBuilds(self.builds, self.tags)

    def diff_builds(self) -> DiffBuilds:
        return DiffBuilds(self.builds)

    def tag_build(self) -> TagBuild:
        return TagBuild(self.builds, self.tags, self.evals)

    def run_eval(self) -> RunEvalGate:
        s = self.settings
        return RunEvalGate(
            self.builds,
            self.tags,
            self.documents,
            self.search_index,
            self.fact_query,
            self.embedder,
            self.evals,
            self.clock,
            GatePolicy(min_recall=s.gate_min_recall, max_drop=s.gate_max_drop),
        )

    def export_dump(self) -> ExportDump:
        return ExportDump(
            self.apis,
            self.builds,
            self.documents,
            self.vectors,
            self.facts,
            self.evals,
            self.dumps,
        )

    def restore_dump(self) -> RestoreDump:
        return RestoreDump(self.dumps, self.importer)

    # -- reader -------------------------------------------------------------------------------

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

    @staticmethod
    def new_job_id() -> str:
        return f"job-{uuid.uuid4().hex[:12]}"
