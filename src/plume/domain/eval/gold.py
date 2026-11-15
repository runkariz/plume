"""Gold questions: what a good build must answer."""

from dataclasses import dataclass
from enum import StrEnum

from plume.domain.shared.errors import InvalidIdentifierError


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

    def __post_init__(self) -> None:
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
