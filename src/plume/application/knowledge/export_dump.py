"""Use cases: export a sealed build as a dump; restore a dump (verified) into a database."""

from collections.abc import Sequence
from dataclasses import dataclass

from plume.application.errors import ApplicationError, IncompleteBuildError, NotFoundError
from plume.application.knowledge._builds import require_build
from plume.application.ports.api_repo import ApiRepo
from plume.application.ports.asset_repo import AssetRepo
from plume.application.ports.build_repo import BuildRepo
from plume.application.ports.document_repo import DocumentRepo
from plume.application.ports.dump_store import BuildImporter, BuildSnapshot, DumpStore, VectorReader
from plume.application.ports.eval_repo import EvalRepo
from plume.application.ports.fact_index import FactIndex
from plume.application.ports.release_notes_repo import ReleaseNotesRepo
from plume.domain.knowledge.build import Build
from plume.domain.knowledge.fact import facts_of
from plume.domain.shared.ids import BuildId


class DumpIntegrityError(ApplicationError):
    code = "dump_integrity"


@dataclass(frozen=True, slots=True)
class RestoreResult:
    api: str
    build: str
    restored: bool  # False when the build already existed (idempotent restore)
    documents: int
    chunks: int
    facts: int
    tags: tuple[str, ...]


def snapshot_of(
    build_id: BuildId,
    apis: ApiRepo,
    builds: BuildRepo,
    documents: DocumentRepo,
    vectors: VectorReader,
    facts: FactIndex,
    evals: EvalRepo | None,
    assets: AssetRepo | None = None,
    notes: ReleaseNotesRepo | None = None,
) -> BuildSnapshot:
    build = require_build(builds, build_id)
    if not build.is_sealed:
        raise IncompleteBuildError(f"build {build_id} is a draft; only sealed builds export")
    api = apis.get(build.api_id)
    if api is None:  # pragma: no cover - FK
        raise NotFoundError(f"api {build.api_id} missing")
    return BuildSnapshot(
        api=api,
        build=build,
        documents=tuple(documents.list_documents(build_id)),
        chunks=tuple(documents.list_chunks(build_id)),
        vectors=vectors.vectors_of(build_id),
        facts=tuple(facts.list_facts(build_id)),
        eval=evals.get(build_id) if evals else None,
        assets=tuple(assets.list(build_id)) if assets else (),
        release_notes=notes.get(build_id.value) if notes else None,
        package_meta=notes.get_meta(build_id.value) if notes else None,
    )


def verify(snapshot: BuildSnapshot) -> None:
    """A dump must rebuild exactly the sealed build it claims to be."""
    b = snapshot.build
    if not b.is_sealed or b.content_hash is None or b.sealed_at is None:
        raise DumpIntegrityError("the dump's build is not sealed")
    doc_ids = {d.doc_id for d in snapshot.documents}
    if len(doc_ids) != len(snapshot.documents):
        raise DumpIntegrityError("duplicate document ids")
    rebuilt = Build.start(b.api_id, b.created_at, b.build_id, b.spec)
    for chunk in snapshot.chunks:
        if chunk.doc_id not in doc_ids:
            raise DumpIntegrityError(f"chunk {chunk.chunk_id} has no document")
        if chunk.chunk_id not in snapshot.vectors:
            raise DumpIntegrityError(f"chunk {chunk.chunk_id} has no vector")
        rebuilt = rebuilt.with_item(chunk.chunk_id, chunk.content_hash)
    if dict(rebuilt.items) != dict(b.items):
        raise DumpIntegrityError("chunks do not match the build's items")
    sealed = rebuilt.seal(b.sealed_at)
    if sealed.content_hash != b.content_hash:
        raise DumpIntegrityError("content hash mismatch: the dump was altered")
    if b.spec is not None:
        for cid, v in snapshot.vectors.items():
            if len(v) != b.spec.dims:
                raise DumpIntegrityError(f"vector {cid} has {len(v)} dims, expected {b.spec.dims}")
    derived = {f.fact_id for d in snapshot.documents for f in facts_of(d)}
    if {f.fact_id for f in snapshot.facts} != derived:
        raise DumpIntegrityError("facts do not match the documents")
    if snapshot.api.api_id != b.api_id:
        raise DumpIntegrityError("api does not match the build")


class ExportDump:
    def __init__(
        self,
        apis: ApiRepo,
        builds: BuildRepo,
        documents: DocumentRepo,
        vectors: VectorReader,
        facts: FactIndex,
        evals: EvalRepo | None,
        store: DumpStore,
        assets: AssetRepo | None = None,
        notes: ReleaseNotesRepo | None = None,
    ) -> None:
        self._args = (apis, builds, documents, vectors, facts, evals, assets, notes)
        self._store = store

    def snapshot(self, build_id: BuildId) -> BuildSnapshot:
        return snapshot_of(build_id, *self._args)

    def execute(self, build_id: BuildId, name: str | None = None) -> str:
        snap = self.snapshot(build_id)
        verify(snap)
        return self._store.write(snap, name)

    def bytes(self, build_id: BuildId) -> bytes:
        snap = self.snapshot(build_id)
        verify(snap)
        return self._store.encode(snap)


class RestoreDump:
    def __init__(self, store: DumpStore, importer: BuildImporter) -> None:
        self._store = store
        self._importer = importer

    def execute(self, ref: str, tags: Sequence[str] = ()) -> RestoreResult:
        snap = self._store.read(ref)
        verify(snap)
        exists = self._importer.exists(snap.build.build_id)
        if not exists:
            self._importer.restore(snap, tags)
        return RestoreResult(
            api=snap.api.api_id.value,
            build=snap.build.build_id.value,
            restored=not exists,
            documents=len(snap.documents),
            chunks=len(snap.chunks),
            facts=len(snap.facts),
            tags=tuple(tags) if not exists else (),
        )
