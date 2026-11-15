"""The citation rule: every mapping must cite, and every citation must hold in the pinned builds.

Issue codes (stable; clients key on them):

- ``API_NOT_IN_SESSION``: a field maps an API that is not one of the session's APIs.
- ``MISSING_CITATION``: a mapping has no evidence.
- ``DOC_NOT_FOUND``: evidence cites a document that is not in that API's pinned build.
- ``QUOTE_NOT_FOUND``: the quoted text is not in the cited document.
- ``FIELD_NOT_FOUND``: a source path is not a documented field of that API.
- ``ENDPOINT_NOT_FOUND``: the fetch endpoint is not documented in that API.
- ``NO_SOURCES``: a canonical field maps no API at all.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from plume.domain.models.canonical_model import ModelDraft

_WS = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class Issue:
    code: str
    field: str
    api: str | None
    message: str


@dataclass(frozen=True, slots=True)
class Oracle:
    """Lookups into the pinned builds (one per API); supplied by the application layer."""

    doc_text: Callable[[str, str], str | None]  # (api, doc_id) -> text
    field_exists: Callable[[str, str], bool]  # (api, path) -> documented?
    endpoint_exists: Callable[[str, str], bool]  # (api, "GET /path") -> documented?


def _norm(text: str) -> str:
    return _WS.sub(" ", text.replace("`", "")).strip().lower()


def quote_in(quote: str, text: str) -> bool:
    """Whitespace-, case- and backtick-insensitive containment."""
    return _norm(quote) in _norm(text)


def validate(draft: ModelDraft, apis: frozenset[str], oracle: Oracle) -> list[Issue]:
    issues: list[Issue] = []
    for path, f in draft.walk():
        if not f.sources and not f.fields:  # a container may be mapped through its sub-fields
            issues.append(Issue("NO_SOURCES", path, None, "the field maps no API"))
        for api, src in f.sources:
            if api not in apis:
                issues.append(
                    Issue("API_NOT_IN_SESSION", path, api, f"{api} is not in this session")
                )
                continue
            if not src.evidence:
                issues.append(Issue("MISSING_CITATION", path, api, "the mapping cites no evidence"))
            for e in src.evidence:
                text = oracle.doc_text(api, e.doc_id)
                if text is None:
                    issues.append(
                        Issue("DOC_NOT_FOUND", path, api, f"{e.doc_id} is not in the build")
                    )
                elif not quote_in(e.quote, text):
                    issues.append(
                        Issue(
                            "QUOTE_NOT_FOUND",
                            path,
                            api,
                            f"the quote is not in {e.doc_id}: {e.quote[:80]!r}",
                        )
                    )
            for p in src.paths:
                if not oracle.field_exists(api, p.path):
                    issues.append(
                        Issue(
                            "FIELD_NOT_FOUND",
                            path,
                            api,
                            f"{p.path} is not a documented field of {api}",
                        )
                    )
            if src.fetch and not oracle.endpoint_exists(api, src.fetch):
                issues.append(
                    Issue(
                        "ENDPOINT_NOT_FOUND", path, api, f"{src.fetch} is not documented in {api}"
                    )
                )
    return issues
