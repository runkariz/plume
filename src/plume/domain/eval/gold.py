"""Gold questions: what a good build must answer."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from plume.domain.shared.errors import InvalidIdentifierError

# Where a question was written from: the vendor's docs pages, its spec (OpenAPI etc.), or a
# tester's real-developer questions; any other lowercase label is accepted and reported apart.
DOCS = "docs"
SPEC = "spec"
TESTER = "tester"
GOLD_SOURCES = (DOCS, SPEC, TESTER)  # the known labels, in report order
_SOURCE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")


def source_order(names: Iterable[str]) -> list[str]:
    """Known sources first (docs, spec, tester), then the others alphabetically."""
    unique = set(names)
    return [s for s in GOLD_SOURCES if s in unique] + sorted(unique - set(GOLD_SOURCES))


class GoldKind(StrEnum):
    SEARCH = "search"  # the expected documents must be retrieved
    ABSENT = "absent"  # find_fact(name) must report found=false with complete=true
    PRESENT = "present"  # find_fact(name) must report found=true


@dataclass(frozen=True, slots=True)
class GoldQuestion:
    qid: str
    kind: GoldKind
    question: str
    expect_docs: tuple[str, ...] = ()
    fact_name: str | None = None
    source: str = DOCS

    def __post_init__(self) -> None:
        if not _SOURCE.match(self.source):
            raise ValueError(
                f"{self.qid}: source {self.source!r} must be a lowercase label "
                f"(e.g. {', '.join(GOLD_SOURCES)})"
            )
        if not self.qid.strip():
            raise InvalidIdentifierError("gold question id is empty")
        if self.kind is GoldKind.SEARCH and not self.expect_docs:
            raise ValueError(f"{self.qid}: a search question needs expected documents")
        if self.kind is not GoldKind.SEARCH and not self.fact_name:
            raise ValueError(f"{self.qid}: a fact question needs fact_name")


@dataclass(frozen=True, slots=True)
class GoldSet:
    api: str
    questions: tuple[GoldQuestion, ...]
    version: str = "1"

    def __post_init__(self) -> None:
        ids = [q.qid for q in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate gold question ids")
        if not self.questions:
            raise ValueError("a gold set needs at least one question")
