"""Use case: chunk a draft build's documents and record the chunks as the build's items."""

from plume.application.knowledge._builds import require_build
from plume.application.ports.build_repo import BuildRepo
from plume.application.ports.document_repo import DocumentRepo
from plume.domain.knowledge.build import Build
from plume.domain.knowledge.chunk import DEFAULT_MAX_CHARS, chunk_document
from plume.domain.shared.ids import BuildId


class ChunkDocuments:
    def __init__(
        self, builds: BuildRepo, documents: DocumentRepo, max_chars: int = DEFAULT_MAX_CHARS
    ) -> None:
        self._builds = builds
        self._documents = documents
        self._max_chars = max_chars

    def execute(self, build_id: BuildId) -> int:
        build = require_build(self._builds, build_id)
        if build.is_sealed:
            return len(build)
        chunks = [
            chunk
            for document in self._documents.list_documents(build_id)
            for chunk in chunk_document(document, self._max_chars)
        ]
        self._documents.replace_chunks(build_id, chunks)
        fresh = Build.start(build.api_id, build.created_at, build.build_id, build.spec)
        for chunk in chunks:
            fresh = fresh.with_item(chunk.chunk_id, chunk.content_hash)
        self._builds.save(fresh)
        return len(chunks)
