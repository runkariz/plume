"""The citation rule: every mapping must cite, and every citation must hold in the pinned builds.

Issue codes (stable; clients key on them):

- ``API_NOT_IN_SESSION``: a field maps an API that is not one of the session's APIs.
- ``MISSING_CITATION``: a mapping has no evidence.
- ``DOC_NOT_FOUND``: evidence cites a document that is not in that API's pinned build.
- ``QUOTE_NOT_FOUND``: the quoted text is not in the cited document.
- ``QUOTE_NOT_ON_FIELD``: the quote is in the document but not about the mapped field: when the
  cited document lists the field, the quote must come from that field's own entry (its line or
  description); otherwise the quote must name the field.
- ``FIELD_NOT_FOUND``: a source path is not a documented field of that API.
- ``ENDPOINT_NOT_FOUND``: the fetch endpoint is not documented in that API.
- ``NO_SOURCES``: a canonical field maps no API at all.

Warning codes (stored with the model, never a refusal):

- ``WRITE_ONLY_SOURCE``: a mapping cites only write operations (a request body, or what a
  POST/PUT/PATCH/DELETE echoes); a model or a GET response says what the API returns. When the
  docs have no read source, it is the only evidence and stays.
- ``NO_COVERAGE``: an input API is not mapped by any field. Server generation sends it back
  for repair on every round and stores the model with the warning only after the last one; a
  Claude or pasted draft is stored with the warning.
"""

import html
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
    write_only: Callable[[str, str], bool] = lambda _api, _doc: False  # (api, doc_id) -> a write?
    # (api, doc_id, path) -> the field's own text in that document (its line and description),
    # None when the document does not list the field. Unset: quotes are not tied to fields.
    field_texts: Callable[[str, str, str], tuple[str, ...] | None] | None = None


_TAG = re.compile(r"<[^>]{0,200}>")


def _norm(text: str) -> str:
    """Markup-free, case-, whitespace- and backtick-insensitive: HTML tags become spaces and
    entities are decoded on both sides (descriptions with <br>, <ul>, &amp;)."""
    plain = html.unescape(_TAG.sub(" ", text)).replace("`", "")
    return _WS.sub(" ", plain).strip().lower()


def _names(path: str) -> set[str]:
    leaf = path.replace("[]", "").split(".")[-1].lower()
    return {leaf, leaf.replace("_", " ")} if leaf else set()


def quote_on_field(quote: str, paths: list[str], api: str, doc_id: str, oracle: Oracle) -> bool:
    """The quote is about one of the mapped fields: from its own entry when the cited document
    lists it, else naming it."""
    lookup = oracle.field_texts
    if lookup is None:
        return True
    found = [lookup(api, doc_id, p) for p in paths]
    texts = [t for f in found for t in (f or ())]
    listed = any(f is not None for f in found)
    if listed:
        return any(quote_in(quote, t) for t in texts)
    said = _norm(quote)
    return any(re.search(rf"(?<![a-z0-9_]){re.escape(n)}(?![a-z0-9_])", said)
               for p in paths for n in _names(p))  # fmt: skip


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
                elif (
                    src.paths
                    and all(oracle.field_exists(api, p.path) for p in src.paths)
                    and not quote_on_field(
                        e.quote, [p.path for p in src.paths], api, e.doc_id, oracle
                    )
                ):
                    issues.append(
                        Issue(
                            "QUOTE_NOT_ON_FIELD",
                            path,
                            api,
                            f"the quote from {e.doc_id} is not about "
                            f"{', '.join(p.path for p in src.paths)}: quote that field's own "
                            f"description or line ({e.quote[:80]!r})",
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


def warnings(draft: ModelDraft, apis: frozenset[str], oracle: Oracle) -> list[Issue]:
    """Mappings that hold but are weak (see the warning codes above)."""
    out: list[Issue] = []
    mapped = {api for _, f in draft.walk() for api, _ in f.sources}
    for api in sorted(apis - mapped):
        out.append(
            Issue(
                "NO_COVERAGE",
                "",
                api,
                f"no field maps {api}: map its documented fields (or say in open_questions why "
                "it has none)",
            )
        )
    for path, f in draft.walk():
        for api, src in f.sources:
            if api not in apis or not src.evidence:
                continue
            fetch_read = (src.fetch or "").strip().upper().startswith("GET ")
            if not fetch_read and all(oracle.write_only(api, e.doc_id) for e in src.evidence):
                cited = ", ".join(sorted({e.doc_id for e in src.evidence}))
                out.append(
                    Issue(
                        "WRITE_ONLY_SOURCE",
                        path,
                        api,
                        f"cites only write operations ({cited}); for what the API returns, "
                        "prefer a model or a GET response field when the docs have one",
                    )
                )
    return out
