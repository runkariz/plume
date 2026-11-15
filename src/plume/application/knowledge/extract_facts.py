"""Use case: derive the exact facts index of a build from its documents."""

from plume.application.knowledge._builds import require_build
from plume.application.ports.build_repo import BuildRepo
from plume.application.ports.document_repo import DocumentRepo
from plume.application.ports.fact_index import FactIndex
from plume.domain.knowledge.fact import facts_of
from plume.domain.shared.ids import BuildId


class ExtractFacts:
    def __init__(self, builds: BuildRepo, documents: DocumentRepo, facts: FactIndex) -> None:
        self._builds = builds
        self._documents = documents
        self._facts = facts

    def execute(self, build_id: BuildId) -> int:
        build = require_build(self._builds, build_id)
        if build.is_sealed:
            return len(self._facts.list_facts(build_id))
        facts = [f for d in self._documents.list_documents(build_id) for f in facts_of(d)]
        self._facts.replace_facts(build_id, facts)
        return len(facts)
