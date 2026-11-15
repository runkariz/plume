"""Use case: read a package and store it as a draft build (or find the build it already is)."""

from plume.application.dto import ImportResult
from plume.application.errors import SourcePackageError
from plume.application.ports.api_repo import ApiRepo
from plume.application.ports.asset_repo import AssetRepo
from plume.application.ports.build_repo import BuildRepo
from plume.application.ports.document_repo import DocumentRepo
from plume.application.ports.package_source import PackageSource
from plume.domain.knowledge.api import ApiId
from plume.domain.knowledge.build import Build, BuildSpec
from plume.domain.knowledge.chunk import CHUNKER_VERSION
from plume.domain.shared.clock import Clock


class ImportPackage:
    def __init__(
        self,
        source: PackageSource,
        apis: ApiRepo,
        builds: BuildRepo,
        documents: DocumentRepo,
        clock: Clock,
        embed_model: str,
        dims: int,
        assets: AssetRepo | None = None,
    ) -> None:
        self._assets = assets
        self._source = source
        self._apis = apis
        self._builds = builds
        self._documents = documents
        self._clock = clock
        self._embed_model = embed_model
        self._dims = dims

    def execute(self, ref: str, api_id: ApiId | None = None) -> ImportResult:
        package = self._source.load(ref)
        if not package.documents:
            raise SourcePackageError(f"package {ref} has no documents")
        info = package.api
        if api_id is not None and api_id != info.api_id:
            raise SourcePackageError(f"package is {info.api_id}, not {api_id}")
        spec = BuildSpec(
            package_hash=package.package_hash,
            chunker_version=CHUNKER_VERSION,
            embed_model=self._embed_model,
            dims=self._dims,
            source_ref=package.source_ref,
            run_id=package.run_id,
        )
        build_id = spec.build_id_for(info.api_id)
        existing = self._builds.get(build_id)
        if existing is not None and existing.is_sealed:
            return ImportResult(
                api_id=info.api_id,
                build_id=build_id,
                created=False,
                already_sealed=True,
                documents=len(package.documents),
                warnings=package.warnings,
            )
        self._apis.upsert(info)
        if existing is None:
            self._builds.save(Build.start(info.api_id, self._clock.now(), spec=spec))
        self._documents.add_documents(build_id, package.documents)
        if self._assets is not None and package.assets:
            self._assets.put(build_id, package.assets)
        return ImportResult(
            api_id=info.api_id,
            build_id=build_id,
            created=existing is None,
            already_sealed=False,
            documents=len(package.documents),
            warnings=package.warnings,
        )
