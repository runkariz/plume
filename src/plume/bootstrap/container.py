"""Wires ports to adapters from the settings. Tests build their own container with fakes."""

import secrets
import uuid
from dataclasses import dataclass, field
from functools import cached_property

from sqlalchemy import Engine

from plume.application.eval.run_eval_gate import RunEvalGate
from plume.application.jobs.build_pipeline import BuildPipeline
from plume.application.jobs.maintainer import MaintainerJobs
from plume.application.knowledge.api_display import ApiDisplayName
from plume.application.knowledge.chunk_documents import ChunkDocuments
from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.embed_build import EmbedBuild
from plume.application.knowledge.export_dump import ExportDump, RestoreDump
from plume.application.knowledge.extract_facts import ExtractFacts
from plume.application.knowledge.import_package import ImportPackage
from plume.application.knowledge.list_builds import ListApis, ListBuilds
from plume.application.knowledge.public_changes import PublicChanges
from plume.application.knowledge.release_notes import ReleaseNotes
from plume.application.knowledge.remove_api import RemoveApi
from plume.application.knowledge.seal_build import SealBuild
from plume.application.knowledge.tag_build import TagBuild
from plume.application.models.collections import Collections
from plume.application.models.concepts import SuggestConcepts
from plume.application.models.generate import GenerateModels
from plume.application.models.impact import ModelImpact
from plume.application.models.model_eval import ModelEvaluation
from plume.application.models.model_sets import ModelSets
from plume.application.models.relations import SuggestRelated
from plume.application.models.sessions import ModelSessions
from plume.application.ports.embedder import Embedder
from plume.application.ports.job_events import JobEvents
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
from plume.application.reports.service import ReportedQuestions
from plume.application.system.migrate_schema import MigrateSchema
from plume.domain.eval.gate import GatePolicy
from plume.domain.models.model_eval import ModelGatePolicy
from plume.domain.reports.redact import RedactionPolicy
from plume.infrastructure.clock import SystemClock
from plume.infrastructure.db.alembic_migrator import AlembicMigrator
from plume.infrastructure.db.archive import PostgresBuildImporter
from plume.infrastructure.db.engine import make_engine
from plume.infrastructure.db.repos.api_removal import PostgresApiRemoval
from plume.infrastructure.db.repos.api_repo import PostgresApiRepo
from plume.infrastructure.db.repos.asset_repo import PostgresAssetRepo
from plume.infrastructure.db.repos.build_repo import PostgresBuildRepo
from plume.infrastructure.db.repos.collection_repo import PostgresCollectionRepo
from plume.infrastructure.db.repos.document_repo import PostgresDocumentRepo
from plume.infrastructure.db.repos.eval_repo import PostgresEvalRepo
from plume.infrastructure.db.repos.model_repo import PostgresModelJobRepo, PostgresModelRepo
from plume.infrastructure.db.repos.model_set_repo import PostgresModelSetRepo
from plume.infrastructure.db.repos.release_notes_repo import PostgresReleaseNotesRepo
from plume.infrastructure.db.repos.report_repo import PostgresReportRepo
from plume.infrastructure.db.repos.tag_repo import PostgresTagRepo
from plume.infrastructure.dumps.local_fs import LocalDumpStore
from plume.infrastructure.embeddings.gemini import GeminiEmbedder, uses_content_api
from plume.infrastructure.embeddings.hash_embedder import HashEmbedder
from plume.infrastructure.events.log_events import LoggingJobEvents
from plume.infrastructure.jobs.package_storage import LocalPackageStorage
from plume.infrastructure.jobs.postgres_jobs import PostgresJobEventLog, PostgresJobRepo
from plume.infrastructure.jobs.thread_runner import ThreadJobRunner
from plume.infrastructure.llm.vertex_gemini import VertexGeminiWriter
from plume.infrastructure.models.gold_files import JsonModelGold
from plume.infrastructure.search.pgvector_index import PgVectorIndex
from plume.infrastructure.search.postgres_fact_index import PostgresFactIndex
from plume.infrastructure.search.postgres_search import PostgresFactQuery, PostgresSearchIndex
from plume.infrastructure.settings import Settings, get_settings
from plume.infrastructure.sources.gold_file import JsonGoldSource
from plume.infrastructure.sources.package_meta import StreamPackageMetaReader
from plume.infrastructure.sources.stream_package import StreamPackageSource
from plume.infrastructure.vertex_auth import AdcTokenSource


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
    def report_repo(self) -> PostgresReportRepo:
        return PostgresReportRepo(self.engine)

    @cached_property
    def reported_questions(self) -> ReportedQuestions:
        s = self.settings
        salt = s.reports_salt.get_secret_value().encode() if s.reports_salt else None
        return ReportedQuestions(
            self.report_repo,
            self.embedder,
            self.resolver(),
            self.clock,
            enabled=s.reports,
            salt=salt or secrets.token_bytes(32),
            per_hour=s.reports_per_hour,
            retention_days=s.reports_retention_days,
            duplicate_similarity=s.reports_duplicate_similarity,
            policy=RedactionPolicy(
                keep_error_codes=s.reports_keep_error_codes,
                keep_rpc_method=s.reports_keep_rpc_method,
            ),
        )

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
        if kind == "vertex" and (s.vertex_uses_adc() or uses_content_api(s.embed_model)):
            return GeminiEmbedder(
                api_key="",
                backend="vertex",
                model=s.embed_model,
                dims=s.embed_dims,
                batch_size=s.embed_batch_size,
                concurrency=s.embed_concurrency,
                token_source=self.vertex_tokens,
                project=s.vertex_project,
                location=s.vertex_embed_location,
                prompt=s.embed_prompt == "gemini",
            )
        if kind == "vertex":
            return GeminiEmbedder(
                api_key=s.vertex_key() or "",
                backend="vertex",
                model=s.embed_model,
                dims=s.embed_dims,
                batch_size=s.embed_batch_size,
                concurrency=s.embed_concurrency,
                project=s.vertex_project,  # set: the project path at the embedding location
                location=s.vertex_embed_location,
            )
        api_key = s.gemini_api_key.get_secret_value() if s.gemini_api_key is not None else ""
        return GeminiEmbedder(
            api_key=api_key,
            backend=kind,
            model=s.embed_model,
            dims=s.embed_dims,
            batch_size=s.embed_batch_size,
            concurrency=s.embed_concurrency,
        )

    @cached_property
    def vertex_tokens(self) -> AdcTokenSource:
        """Application Default Credentials, shared by embeddings and generation."""
        return AdcTokenSource()

    @cached_property
    def events(self) -> JobEvents:
        return LoggingJobEvents()

    # -- use cases ------------------------------------------------------------------------------

    def migrate_schema(self) -> MigrateSchema:
        return MigrateSchema(AlembicMigrator(self.engine))

    @cached_property
    def assets(self) -> PostgresAssetRepo:
        return PostgresAssetRepo(self.engine)

    @cached_property
    def models_repo(self) -> PostgresModelRepo:
        return PostgresModelRepo(self.engine)

    @cached_property
    def model_sets_repo(self) -> PostgresModelSetRepo:
        return PostgresModelSetRepo(self.engine)

    @cached_property
    def collections_repo(self) -> PostgresCollectionRepo:
        return PostgresCollectionRepo(self.engine)

    def collections(self) -> Collections:
        return Collections(
            self.collections_repo, self.models_repo, self.model_sets_repo, self.clock
        )

    def model_sets(self) -> ModelSets:
        return ModelSets(
            self.resolver(),
            self.models(),
            self.models_repo,
            self.model_sets_repo,
            self.suggest_related(),
            self.clock,
            self.collections(),
        )

    def suggest_related(self) -> SuggestRelated:
        return SuggestRelated(self.resolver(), self.search_index, self.facts, self.documents)

    def suggest(self) -> SuggestConcepts:
        return SuggestConcepts(self.resolver(), self.search_index, self.facts)

    def models(self) -> ModelSessions:
        return ModelSessions(
            self.resolver(),
            self.search_index,
            self.fact_query,
            self.documents,
            self.models_repo,
            self.clock,
            self.collections(),
            release_gate=lambda snap: self.model_evaluation().gate(snap),
        )

    @cached_property
    def model_gold(self) -> JsonModelGold:
        return JsonModelGold(self.settings.model_gold_dirs)

    def model_evaluation(self) -> ModelEvaluation:
        sessions = ModelSessions(  # no release gate: only its citation oracle is used
            self.resolver(),
            self.search_index,
            self.fact_query,
            self.documents,
            self.models_repo,
            self.clock,
        )
        return ModelEvaluation(
            self.models_repo,
            self.model_sets_repo,
            sessions.oracle_for,
            self.model_gold,
            ModelGatePolicy(self.settings.model_gate_min_recall),
        )

    @cached_property
    def model_jobs(self) -> PostgresModelJobRepo:
        return PostgresModelJobRepo(self.engine)

    @cached_property
    def model_writer(self) -> VertexGeminiWriter:
        s = self.settings
        adc = s.vertex_uses_adc()
        return VertexGeminiWriter(
            None if adc else s.vertex_key_file,
            s.model_llm,
            project=s.vertex_project,
            location=s.vertex_location,
            token_source=self.vertex_tokens if adc else None,
        )

    @cached_property
    def model_job_runner(self) -> ThreadJobRunner:
        return ThreadJobRunner(workers=2)

    def generate(self) -> GenerateModels:
        return GenerateModels(
            self.models(),
            self.model_writer,
            self.model_jobs,
            self.job_events,
            self.model_job_runner,
            self.clock,
            self.settings.model_max_rounds,
            evidence_budget=self.settings.evidence_budget_chars,
        )

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
                assets=self.assets,
            ),
            chunk=ChunkDocuments(self.builds, self.documents, self.settings.chunk_max_chars),
            embed=EmbedBuild(self.builds, self.documents, self.vectors, embedder),
            facts=ExtractFacts(self.builds, self.documents, self.facts),
            seal=SealBuild(self.builds, self.vectors, self.clock),
            tag=self.tag_build(),
            events=events or self.events,
            evaluate=self.run_eval(),
            gold=self.gold,
            notes=self.release_notes(),
            package_meta=StreamPackageMetaReader(),
        )

    @cached_property
    def release_notes_repo(self) -> PostgresReleaseNotesRepo:
        return PostgresReleaseNotesRepo(self.engine)

    def api_display(self) -> ApiDisplayName:
        return ApiDisplayName(self.apis)

    def remove_api(self) -> RemoveApi:
        return RemoveApi(
            self.apis, PostgresApiRemoval(self.engine), self.models_repo, self.model_sets_repo
        )

    def public_changes(self) -> PublicChanges:
        return PublicChanges(self.release_notes_repo, self.tags)

    def model_impact(self) -> ModelImpact:
        return ModelImpact(self.public_changes())

    def release_notes(self) -> ReleaseNotes:
        return ReleaseNotes(
            self.builds,
            self.documents,
            self.tags,
            self.release_notes_repo,
            self.clock,
            self.evals,
            self.settings.gate_max_drop,
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
            GatePolicy(min_recall=s.gate_floor(), max_drop=s.gate_max_drop, source=s.gate_source),
            s.fusion(),
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
            self.assets,
            self.release_notes_repo,
        )

    def restore_dump(self) -> RestoreDump:
        return RestoreDump(self.dumps, self.importer)

    # -- reader -------------------------------------------------------------------------------

    def resolver(self) -> BuildResolver:
        return BuildResolver(self.apis, self.builds, self.tags)

    def overviews(self) -> ListApiOverviews:
        return ListApiOverviews(
            self.apis, self.builds, self.tags, self.search_index, self.evals, self.assets
        )

    def sections(self) -> PackageSections:
        return PackageSections(
            self.resolver(), self.search_index, self.documents, self.assets, self.fact_query
        )

    def browse(self) -> BrowseDocuments:
        return BrowseDocuments(self.resolver(), self.search_index)

    def search(self) -> SearchDocs:
        return SearchDocs(
            self.resolver(),
            self.search_index,
            self.embedder,
            self.documents,
            self.settings.fusion(),
        )

    def get_document(self) -> GetDocument:
        return GetDocument(self.resolver(), self.documents)

    def find_fact(self) -> FindFact:
        return FindFact(self.resolver(), self.fact_query, self.search_index, self.documents)

    def check_call(self) -> CheckCall:
        return CheckCall(self.resolver(), self.fact_query, self.search_index, self.documents)

    @staticmethod
    def new_job_id() -> str:
        return f"job-{uuid.uuid4().hex[:12]}"
