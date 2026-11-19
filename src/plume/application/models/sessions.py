"""Model sessions: pin builds, hand Claude the evidence pack, validate and store its draft."""

import json
import re
import secrets
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from plume.application.errors import ApplicationError, NotFoundError
from plume.application.models.collections import (
    KIND_MODEL,
    CollectionRef,
    Collections,
    owner_key_hash,
)
from plume.application.models.concepts import (
    ROLE_SYNONYMS,
    ModelInputError,
    concept_docs,
    concept_key,
    concept_parts,
    last_literal,
    resolve_apis,
)
from plume.application.models.oracle import PinnedLookups
from plume.application.ports.document_repo import DocumentRepo
from plume.application.ports.model_repo import ModelRepo, ModelSession
from plume.application.ports.search_index import DocumentSummary, FactQuery, SearchIndex
from plume.application.reader.resolve import BuildResolver
from plume.domain.knowledge.document import Document, DocumentKind, FieldLocation
from plume.domain.models.canonical_model import DraftFormatError, ModelDraft, parse_draft
from plume.domain.models.release import GateFailure
from plume.domain.models.snapshot import (
    ModelSnapshot,
    Origin,
    PinnedInput,
    Visibility,
    draft_json,
    snapshot_id_for,
)
from plume.domain.models.validation import Issue, Oracle, validate, warnings
from plume.domain.shared.clock import Clock
from plume.domain.shared.ids import BuildId

MAX_DOCS_PER_API = 30
MIN_OWN_DOCS = 5  # below this, full-text hits are added (a short relevant context wins)
EVIDENCE_BUDGET_CHARS = 20_000
MAX_DESCRIPTION = 300
MAX_DRAFT_CHARS = 1_000_000
MAX_OWNER_KEYS = 200
_SAVE_ATTEMPTS = 5
_DATA_LOCATIONS = (FieldLocation.MODEL, FieldLocation.RESPONSE, FieldLocation.BODY)

_EVIDENCE = {"doc_id": "model:order", "quote": "exact text copied from the document"}
DRAFT_FORMAT: dict[str, Any] = {
    "name": "Order",
    "description": "One sentence on what the canonical model represents.",
    "fields": [
        {
            "name": "total",
            "type": "decimal",
            "description": "Total amount billed.",
            "required": True,
            "sources": {
                "<api id>": {
                    "paths": [{"path": "orders[].total", "type": "string"}],
                    "fetch": "GET /api/{version}/orders",
                    "join": [],
                    "transform": "parse the decimal string",
                    "conversion": {"kind": "money-decimal-string", "note": "currency in currency"},
                    "evidence": [
                        {"doc_id": "model:order", "quote": "exact text copied from the document"}
                    ],
                }
            },
        }
    ],
    "open_questions": [{"question": "Is total before or after tax?", "options": ["gross", "net"]}],
    "_nested_field_example": {
        "name": "line_items",
        "type": "array",
        "description": "The order's lines.",
        "sources": {"<api id>": {"paths": [{"path": "line_items"}], "evidence": [_EVIDENCE]}},
        "fields": [
            {
                "name": "sku",
                "type": "string",
                "sources": {
                    "<api id>": {"paths": [{"path": "line_items[].sku"}], "evidence": [_EVIDENCE]}
                },
            }
        ],
    },
}

INSTRUCTIONS = """\
Write ONE canonical model for the concept, then submit it with submit_model_draft(model_session,
draft). get_model_context lists the documents per API; get_model_evidence(model_session, api)
returns their fields page by page (follow next_cursor). Rules (refused otherwise):
- Map an API under fields[].sources only with fields that appear in that API's evidence: copy
  `paths[].path` exactly as listed (dotted names, [] for arrays).
- Every mapping needs evidence: `doc_id` from the evidence and a `quote` copied verbatim from
  that document's text, about the mapped field: when the document lists the field, quote that
  field's own description or line; otherwise the quote must name the field. Quotes are checked
  and must carry information (4+ words or 20+ letters, or the field's whole description). When
  the field's own description has no usable sentence (markup, a label), cite it with
  {"doc_id": ..., "noQuote": "why"} instead of a junk quote.
- `fetch` (optional) must be a documented endpoint, written "METHOD /path" as listed.
- Leave an API out of a field's sources when it has no such data; never invent fields.
- Use `transform` / `join` to describe derived values (e.g. "sum of line_items[].price").
- State every conversion the value needs in `conversion` {kind, map?, format?, note?}. Kinds:
  money-minor (integer cents), money-decimal, money-decimal-string, currency-separate, enum
  (map: {API value: canonical value} covering every value of the API's enum, or list the ones
  without a target in "unmapped"), datetime (format: e.g. "ISO 8601 UTC", "local, no tz"),
  id-type (string vs number), array-vs-single, cardinality (e.g. one variant synthesized from
  product fields), embedded (only inside another resource), derived (from a field's name or
  position, e.g. billing_ prefix), meta-entry (an entry of a key/value list; format: the key),
  split (one value over several fields, or a sum), other. Money, status enums and dates
  break integrations when unstated.
- Prefer fields from a model or a response for what the API returns; cite a request body only
  for what a client sends (e.g. the order's status as read, not as written).
- Put semantic choices you cannot settle from the evidence in open_questions; do not decide them.
- Nested objects: a field of type "object" or "array" may carry its own "fields" (at most 3
  levels). Map and cite every sub-field like a top-level one; its source paths are the API's
  full paths (e.g. "variants[].sku"). A container needs sources only when it is mapped as a
  whole; coverage counts the sub-fields.
- A scalar field (string, number, date, money, ...) maps a scalar path: when the API's field is
  an object (an address region, a country, a money object), map one of its fields (region.name,
  country.iso, amount.value); a list needs a conversion (array-vs-single, cardinality, split).
- With `fetch`, the paths must be fields of that endpoint's response.
Refusals come back with codes (MISSING_CITATION, QUOTE_NOT_FOUND, QUOTE_NOT_ON_FIELD,
FIELD_NOT_FOUND, ENDPOINT_NOT_FOUND, DOC_NOT_FOUND, API_NOT_IN_SESSION, PATH_NOT_IN_FETCH,
SCALAR_FROM_OBJECT, ARRAY_FOR_SINGLE, SINGLE_FOR_ARRAY, ENUM_KEY_UNKNOWN, ENUM_MAP_INCOMPLETE,
QUOTE_TOO_SHORT, NO_QUOTE_NOT_ALLOWED); fix those mappings and submit again.
"""


def normalize_concept(concept: str) -> str:
    """One spelling per concept: trimmed, single spaces, first letter upper case when the user
    typed it all lower case ("order" -> "Order"; "Product/Offer" and "SKU" stay as typed)."""
    text = " ".join(concept.split())
    return text[:1].upper() + text[1:] if text == text.lower() else text


def _evidence_rank(d: DocumentSummary, key: str) -> tuple[bool, bool, bool, int, str]:
    """Models first, then reads, the concept's OWN endpoints (/orders, /orders/{id}: the full
    object) before its sub-resources (/orders/{id}/notes), shorter paths first."""
    own = d.path is not None and concept_key(_last_literal_of(d.path)) == key
    depth = len((d.path or "").strip("/").split("/"))
    return (d.kind is not DocumentKind.MODEL, d.method != "GET", not own, depth, d.doc_id)


_PARENS_TEXT = re.compile(r"\([^)]*\)")


_ERROR_MODEL = re.compile(
    r"(?:^|[-_ ])(?:[45]\d\d|errors?|problem(?:detail)?s?|fault|exception)(?:[-_ ]|$)", re.I
)


def _error_model(d: DocumentSummary) -> bool:
    """A 4xx/5xx or error / problem-detail response model: never a concept's data."""
    name = d.doc_id.removeprefix("model:").lower()
    return d.kind is DocumentKind.MODEL and bool(
        _ERROR_MODEL.search(name)
        or _ERROR_MODEL.search(d.title or "")
        or name.endswith(("error", "errors", "problemdetail", "problemdetails"))
    )


def _parent_of(key: str, names: tuple[str, ...]) -> str:
    return next((key[: -len(n)] for n in names if key != n and key.endswith(n)), "")


def _under(path: str, main: tuple[str, ...]) -> bool:
    """A literal segment of the path names a main concept (/customers/search.json)."""
    return any(
        seg and "{" not in seg and concept_key(seg.split(".", 1)[0]) in main
        for seg in path.strip("/").split("/")
    )


def _child_of(key: str, main: tuple[str, ...], children: set[str]) -> bool:
    """``variation`` under Product is the child ``productvariation``."""
    return any(f"{m}{key}" in children for m in main)


def _returned_ids(doc: Document | None) -> set[str]:
    ops = (
        doc.raw.get("x-plume-returned-by")
        if doc is not None and isinstance(doc.raw, dict)
        else None
    )
    return {str(o) for o in ops} if isinstance(ops, list) else set()


def _last_literal_of(path: str) -> str:
    for seg in reversed(path.strip("/").split("/")):
        if seg and "{" not in seg:
            return seg.split(".", 1)[0]
    return ""


class ModelStateError(ApplicationError):
    code = "invalid_state"


def new_owner_key() -> str:
    return "pk_" + secrets.token_urlsafe(24)


def new_unlisted_id() -> str:
    """128 random bits: an unlisted model is readable by anyone who has its id (the link)."""
    return "u-" + secrets.token_urlsafe(16)


def claude_prompt(session: "ModelSession", maintainer: bool) -> str:
    server = "Plume maintainer MCP" if maintainer else "Plume MCP"
    based = f', based_on="{session.based_on}"' if session.based_on else ""
    start = (
        f"revise the canonical {session.concept} model {session.based_on} (its current draft is "
        "the starting point)"
        if session.based_on
        else f"write the canonical {session.concept} model for "
        + ", ".join(i.api for i in session.inputs)
    )
    return (
        f'Use the {server}: get_model_context("{session.session_id}"), {start}, then '
        f'submit_model_draft("{session.session_id}", draft{based}).'
    )


def revise_prompt(snapshot_id: str) -> str:
    return (
        f'Use the Plume MCP: revise_model("{snapshot_id}") opens a session on the current docs '
        "with this model as the starting draft. Make the changes I ask for, keep every citation "
        "verbatim, then submit_model_draft(model_session, draft, "
        f'based_on="{snapshot_id}") to save a new version.'
    )


class ModelDraftRefusedError(ApplicationError):
    code = "draft_refused"

    def __init__(self, issues: list[Issue]) -> None:
        self.issues = issues
        summary = "; ".join(f"{i.code} {i.field}/{i.api}" for i in issues[:10])
        super().__init__(f"{len(issues)} issue(s): {summary}")


@dataclass(frozen=True, slots=True)
class SubmitResult:
    snapshot: ModelSnapshot
    created: bool
    owner_key: str | None = None  # no longer issued (My models link); kept for the shape
    collection: CollectionRef | None = None  # the user's My models link


class ModelSessions:
    def __init__(
        self,
        resolver: BuildResolver,
        index: SearchIndex,
        facts: FactQuery,
        documents: DocumentRepo,
        models: ModelRepo,
        clock: Clock,
        collections: Collections | None = None,
        release_gate: Callable[[ModelSnapshot], list[GateFailure]] | None = None,
    ) -> None:
        self._collections = collections
        self._release_gate = release_gate
        self._resolver = resolver
        self._index = index
        self._facts = facts
        self._documents = documents
        self._models = models
        self._clock = clock

    # -- sessions --------------------------------------------------------------------------------

    def start(
        self,
        apis: list[str],
        concept: str,
        origin: str = Origin.MAINTAINER,
        based_on: str | None = None,
    ) -> ModelSession:
        if not concept_key(concept):
            raise ModelInputError("concept is empty")
        resolved = resolve_apis(self._resolver, apis)
        session = ModelSession(
            session_id=f"s-{uuid.uuid4().hex[:16]}",
            concept=normalize_concept(concept),
            inputs=tuple(PinnedInput(r.api.api_id.value, r.build.build_id.value) for r in resolved),
            created_at=self._clock.now(),
            origin=origin,
            based_on=based_on,
        )
        self._models.save_session(session)
        return session

    def start_pinned(
        self,
        inputs: tuple[PinnedInput, ...],
        concept: str,
        origin: str = Origin.MAINTAINER,
        based_on: str | None = None,
        aliases: tuple[tuple[str, str], ...] = (),
    ) -> ModelSession:
        """A session on given pins (a model set pins its builds once for all members). An
        accepted alias makes the concept's evidence in that API be searched under its name."""
        if not concept_key(concept):
            raise ModelInputError("concept is empty")
        session = ModelSession(
            session_id=f"s-{uuid.uuid4().hex[:16]}",
            concept=normalize_concept(concept),
            inputs=inputs,
            created_at=self._clock.now(),
            origin=origin,
            based_on=based_on,
            aliases=tuple(sorted(aliases)),
        )
        self._models.save_session(session)
        return session

    def oracle_for(self, inputs: tuple[PinnedInput, ...]) -> Oracle:
        """Citation checks against these pinned builds (for relation evidence)."""
        return self._oracle(ModelSession("-", "-", inputs, self._clock.now()))

    def reusable(
        self, inputs: tuple[PinnedInput, ...], concept: str, maintainer: bool
    ) -> list[ModelSnapshot]:
        """Visible models of this concept pinned to exactly these builds (newest first)."""
        pins = {(i.api, i.build) for i in inputs}
        key = concept_key(concept)
        visible = tuple(v for v in _visible(maintainer) if v != Visibility.DISCARDED)
        out = []
        for snap in self._models.list_snapshots(inputs[0].api, 200, visible):
            if concept_key(snap.concept) == key and {(i.api, i.build) for i in snap.inputs} == pins:
                out.append(snap)
        return out

    def existing(
        self, apis: list[str], concept: str, maintainer: bool = False
    ) -> ModelSnapshot | None:
        """A model the caller may see (official; unreleased too for a maintainer) for the same
        concept on the APIs' current builds, if any. Never someone's unlisted model, and never
        a discarded or superseded one (a thrown-away draft must not be offered as "ready")."""
        resolved = resolve_apis(self._resolver, apis)
        pins = {(r.api.api_id.value, r.build.build_id.value) for r in resolved}
        key = concept_key(concept)
        allowed: tuple[str, ...] = (
            (Visibility.OFFICIAL, Visibility.UNRELEASED) if maintainer else (Visibility.OFFICIAL,)
        )
        for snap in self._models.list_snapshots(resolved[0].api.api_id.value, 200, allowed):
            if concept_key(snap.concept) == key and {(i.api, i.build) for i in snap.inputs} == pins:
                return snap
        return None

    def session_status(self, session_id: str) -> dict[str, Any]:
        """For pollers: the latest model accepted in this session, if any."""
        session = self.get(session_id)
        done = [s for s in self._models.by_session(session_id) if s.visibility in Visibility.ALL]
        latest = done[0] if done else None
        return {
            "model_session": session.session_id,
            "session_id": session.session_id,
            "status": "submitted" if latest else "open",
            "snapshot_id": latest.snapshot_id if latest else None,
            "visibility": latest.visibility if latest else None,
            "apis": [i.api for i in session.inputs],
            "concept": session.concept,
            "based_on": session.based_on,
        }

    def get(self, session_id: str) -> ModelSession:
        s = self._models.get_session(session_id)
        if s is None:
            raise NotFoundError(f"model session {session_id} not found")
        return s

    def _concept_docs(
        self, concept: str, build: BuildId, max_docs: int = MAX_DOCS_PER_API
    ) -> list[DocumentSummary]:
        """The concept's documents (see ``_ranked_docs``), never error-response models."""
        docs = self._ranked_docs(concept, build, max_docs + 20)
        return [d for d in docs if not _error_model(d)][:max_docs]

    def _ranked_docs(
        self, concept: str, build: BuildId, max_docs: int = MAX_DOCS_PER_API
    ) -> list[DocumentSummary]:
        """The documents a model of ``concept`` is built from, best first: the concept's own
        list/get endpoints and the models they return, then its child resources and the
        sub-concepts named in parentheses ("Order (with order line)"), then other reads under
        it, then writes and request models."""
        main, subs = concept_parts(concept)
        summaries, _ = self._index.browse(build, (), None, 100_000, 0)
        groups = concept_docs(summaries)
        children = {k for k in groups for m in main if k != m and k.startswith(m)} | set(subs)
        picked: dict[str, DocumentSummary] = {}
        for k in (*main, *sorted(children)):
            for d in groups.get(k, []):
                picked.setdefault(d.doc_id, d)
        for d in summaries:  # endpoints under the concept's path (/customers/search.json)
            if d.kind is DocumentKind.ENDPOINT and d.path and _under(d.path, main):
                picked.setdefault(d.doc_id, d)
        has_main = any(groups.get(k) for k in main) or any(
            d.kind is DocumentKind.ENDPOINT and d.path and _under(d.path, main) for d in summaries
        )
        if not has_main and picked:  # only sub-concepts or children matched: the main first
            own = self._fallback_docs(concept, main, groups, build, max_docs)
            rest = [d for d in picked.values() if d.doc_id not in {o.doc_id for o in own}]
            return [*own, *rest][:max_docs]
        docs = list(picked.values())
        if docs:
            ranks = self._tiers(build, docs, main, children)
            docs = [d for d in docs if d.doc_id in ranks]
            docs.sort(key=lambda d: (*ranks[d.doc_id], *_evidence_rank(d, main[0])))
            if len(docs) < MIN_OWN_DOCS:  # few of its own: documents that mention it help
                hits = self._index.text(
                    build, _PARENS_TEXT.sub(" ", concept), max_docs,
                    (DocumentKind.ENDPOINT, DocumentKind.MODEL),
                )  # fmt: skip
                have = {d.doc_id for d in docs}
                extra = self._index.summaries(
                    build, [h.doc_id for h in hits if h.doc_id not in have]
                )
                docs += list(extra.values())
            return docs[:max_docs]
        return self._fallback_docs(concept, main, groups, build, max_docs)

    def _fallback_docs(
        self,
        concept: str,
        main: tuple[str, ...],
        groups: dict[str, list[DocumentSummary]],
        build: BuildId,
        max_docs: int,
    ) -> list[DocumentSummary]:
        """No document carries the concept's name: the concept under a parent, its role under
        another name, else documents whose text mentions it. Never calls back into the ranking
        (each name is tried once)."""
        text = _PARENS_TEXT.sub(" ", concept).strip() or concept
        key = main[0]
        names = (*main, *(r for m in main for r in ROLE_SYNONYMS.get(m, ()) if r not in main))
        groups_parent = sorted(  # the concept under a parent: productimage under Product,
            (  # or its role under another name: orderdelivery for Shipment
                k
                for k in groups
                for n in names
                if k == n or (k != n and k.endswith(n) and k[: -len(n)] in groups)
            ),
            key=lambda k: (k not in names, -len(groups.get(_parent_of(k, names), [])), k),
        )
        docs = list({d.doc_id: d for k in groups_parent for d in groups[k]}.values())
        synonyms = [n for n in names if n not in main]
        if any(k.endswith(n) for k in groups_parent for n in synonyms):  # another name: reads first
            docs.sort(key=lambda d: _evidence_rank(d, concept_key(last_literal(d.path or ""))))
        if not docs:  # derived: documents whose text mentions the concept
            hits = self._index.text(
                build, text, MAX_DOCS_PER_API, (DocumentKind.ENDPOINT, DocumentKind.MODEL)
            )
            docs = list(self._index.summaries(build, [h.doc_id for h in hits]).values())
            docs.sort(key=lambda d: _evidence_rank(d, key))
        return docs[:max_docs]

    def _own_resource(self, concept: str, build: BuildId) -> bool:
        """An endpoint path names the concept or its role (/customers, /order-delivery): the
        API has the resource. A model alone (an order's ``customer`` object) is not one."""
        main, _ = concept_parts(concept)
        roles = tuple(r for m in main for r in ROLE_SYNONYMS.get(m, ()) if r not in main)
        summaries, _ = self._index.browse(build, (DocumentKind.ENDPOINT,), None, 100_000, 0)
        keys = {
            concept_key(seg.split(".", 1)[0])
            for d in summaries
            for seg in (d.path or "").strip("/").split("/")
            if seg and "{" not in seg
        }
        return any(k in main or any(k == r or k.endswith(r) for r in roles) for k in keys)

    def _tiers(
        self,
        build: BuildId,
        docs: list[DocumentSummary],
        main: tuple[str, ...],
        children: set[str],
    ) -> dict[str, tuple[int, int]]:
        """(tier, -data fields for child and other models) per document. Tier 0: own list/get
        endpoints and the models they return (or named as the concept); 1: child resources
        and sub-concepts; 2: other reads and models under the concept; 3: writes and request
        models. Child and other models without data fields are left out."""
        own = {
            d.doc_id
            for d in docs
            if d.kind is DocumentKind.ENDPOINT
            and d.method == "GET"
            and concept_key(last_literal(d.path or "")) in main
        }
        out: dict[str, tuple[int, int]] = {}
        for d in docs:
            if d.kind is DocumentKind.ENDPOINT:
                key = concept_key(last_literal(d.path or ""))
                if d.method != "GET":
                    out[d.doc_id] = (3, 0)
                elif d.doc_id in own:
                    out[d.doc_id] = (0, 0)
                else:
                    child = key in children or _child_of(key, main, children)
                    out[d.doc_id] = (1 if child else 2, 0)
                continue
            full = self._documents.get_document(build, d.doc_id)
            returned = _returned_ids(full)
            key = concept_key(d.title.split(" / ")[-1])
            fields = sum(1 for f in full.fields if f.location in _DATA_LOCATIONS) if full else 0
            if "request" in d.doc_id.lower() and not returned:
                out[d.doc_id] = (3, 0)
            elif returned & own or (key in main and not returned):
                out[d.doc_id] = (0, 0)  # returned by its own reads, or the concept's model
            elif fields:
                out[d.doc_id] = (1 if key in children else 2, -fields)
        return out

    def _pin(self, session: ModelSession, api: str) -> BuildId:
        for p in session.inputs:
            if p.api == api:
                return BuildId(p.build)
        raise ModelInputError(f"{api} is not in session {session.session_id}")

    def context(self, session_id: str, max_docs: int = MAX_DOCS_PER_API) -> dict[str, Any]:
        """A compact index of the evidence (small enough for any client): per API, the
        concept's documents with their field counts. Read the fields with ``evidence``."""
        session = self.get(session_id)
        per_api: list[dict[str, Any]] = []
        for pin in session.inputs:
            build = BuildId(pin.build)
            items = []
            for d in self._concept_docs(session.name_in(pin.api), build, max_docs):
                full = self._documents.get_document(build, d.doc_id)
                if full is None:  # pragma: no cover
                    continue
                items.append(
                    {
                        "doc_id": d.doc_id,
                        "kind": d.kind.value,
                        "title": d.title,
                        "endpoint": f"{d.method} {d.path}" if d.method else _returned_by(full),
                        "fields": sum(1 for f in full.fields if f.location in _DATA_LOCATIONS),
                        "complete": full.complete,
                    }
                )
            entry: dict[str, Any] = {"api": pin.api, "build": pin.build, "documents": items}
            if not self._own_resource(session.name_in(pin.api), build):
                entry["note"] = (
                    f"{pin.api} has no {session.name_in(pin.api)} resource of its own: the "
                    "documents below only mention it. Its data may be embedded in another "
                    "resource (map those paths and say so in a transform), or not available."
                )
            if session.name_in(pin.api) != session.concept:
                entry["searched_as"] = session.name_in(pin.api)  # an accepted alias
            per_api.append(entry)
        return {
            "model_session": session.session_id,
            "session_id": session.session_id,
            "concept": session.concept,
            "apis": per_api,
            "next": "Call get_model_evidence(model_session, api) for each API (follow next_cursor) "
            "to read the fields with their descriptions, then write the draft.",
            "instructions": INSTRUCTIONS,
            "draft_format": DRAFT_FORMAT,
            "status": "Plume validates citations; the result is generated, unverified.",
        }

    def evidence(
        self,
        session_id: str,
        api: str,
        doc_ids: list[str] | None = None,
        cursor: int = 0,
        budget_chars: int = EVIDENCE_BUDGET_CHARS,
    ) -> dict[str, Any]:
        """Fields (path, type, location, required, description) of the concept's documents in
        one API (or of ``doc_ids``), paged: at most ``budget_chars`` of JSON per call."""
        session = self.get(session_id)
        build = self._pin(session, api)
        if doc_ids:
            wanted = list(dict.fromkeys(doc_ids))[:50]
        else:
            wanted = [d.doc_id for d in self._concept_docs(session.name_in(api), build)]
        rows: list[tuple[dict[str, Any], dict[str, Any]]] = []  # (doc header, field)
        missing: list[str] = []
        for doc_id in wanted:
            full = self._documents.get_document(build, doc_id)
            if full is None:
                missing.append(doc_id)
                continue
            header = {
                "doc_id": full.doc_id,
                "title": full.title,
                "endpoint": f"{full.method} {full.path}" if full.method else None,
                "source_url": full.source_url,
                "complete": full.complete,
            }
            for f in full.fields:
                if f.location not in _DATA_LOCATIONS:
                    continue
                desc = f.description or ""
                rows.append(
                    (
                        header,
                        {
                            "path": f.name,
                            "type": f.type,
                            "location": f.location.value,
                            "required": f.required,
                            "description": desc[:MAX_DESCRIPTION]
                            + ("…" if len(desc) > MAX_DESCRIPTION else ""),
                        },
                    )
                )
        cursor = max(0, cursor)
        out: dict[str, dict[str, Any]] = {}
        used = 0
        position = cursor
        while position < len(rows):
            header, field_row = rows[position]
            cost = len(json.dumps(field_row, ensure_ascii=False)) + 2
            if header["doc_id"] not in out:
                cost += len(json.dumps(header, ensure_ascii=False)) + 20
            if used + cost > budget_chars and position > cursor:
                break
            doc = out.setdefault(str(header["doc_id"]), {**header, "fields": []})
            doc["fields"].append(field_row)
            used += cost
            position += 1
        return {
            "model_session": session.session_id,
            "session_id": session.session_id,
            "api": api,
            "build": build.value,
            "documents": list(out.values()),
            "returned": position - cursor,
            "total_fields": len(rows),
            "next_cursor": position if position < len(rows) else None,
            "missing_doc_ids": missing,
        }

    # -- drafts ----------------------------------------------------------------------------------

    def _oracle(self, session: ModelSession) -> Oracle:
        """Lookups into the pinned builds, cached for one validation."""
        builds = {p.api: BuildId(p.build) for p in session.inputs}
        return PinnedLookups(builds, self._facts, self._documents).oracle()

    def _validated(self, session: ModelSession, raw: Any) -> tuple[ModelDraft, list[Issue]]:
        """Parse and validate (refusals raise); returns the draft and its warnings."""
        if len(json.dumps(raw, default=str)) > MAX_DRAFT_CHARS:
            raise ModelDraftRefusedError(
                [Issue("INVALID_FORMAT", "", None, f"draft over {MAX_DRAFT_CHARS} characters")]
            )
        try:
            draft = parse_draft(raw)
        except DraftFormatError as exc:
            raise ModelDraftRefusedError([Issue("INVALID_FORMAT", "", None, str(exc))]) from exc
        apis = frozenset(p.api for p in session.inputs)
        oracle = self._oracle(session)
        issues = validate(draft, apis, oracle)
        if issues:
            raise ModelDraftRefusedError(issues)
        return draft, warnings(draft, apis, oracle)

    def check(self, session_id: str, raw: Any) -> list[Issue]:
        """Validate without storing: raises on refusal, returns the warnings."""
        return self._validated(self.get(session_id), raw)[1]

    def submit(
        self,
        session_id: str,
        raw: Any,
        based_on: str | None = None,
        maintainer: bool = False,
        generator: str = "claude",
        generator_usage: dict[str, int] | None = None,
        collection: str | None = None,
    ) -> SubmitResult:
        """Validate and store a draft. A maintainer's model is stored unreleased (official only
        after ``release``); a user's is unlisted (readable by anyone with its id). ``based_on``
        (or the session's) makes it the next version of that model's lineage when the caller may
        add to it; otherwise a new lineage that records where it came from."""
        session = self.get(session_id)
        draft, found_warnings = self._validated(session, raw)
        checked = sum(len(s.evidence) for _, f in draft.walk() for _, s in f.sources)
        content_key = snapshot_id_for(session.inputs, session.concept, draft)
        base_id = based_on or session.based_on
        base = self.visible_snapshot(base_id, maintainer) if base_id else None
        if base is not None and base.visibility == Visibility.DISCARDED:
            raise ModelStateError(f"model {base.snapshot_id} was discarded")
        same_lineage = base is not None and (
            base.visibility in (Visibility.OFFICIAL, Visibility.UNRELEASED)
            if maintainer
            else base.visibility == Visibility.UNLISTED
        )
        if (
            base is not None
            and same_lineage
            and concept_key(base.concept) != concept_key(session.concept)
        ):
            raise ModelStateError(
                f"model {base.snapshot_id} is a {base.concept} model; this session is for "
                f"{session.concept}"
            )
        if not maintainer:  # a retry of the same draft returns the stored model
            for prior in self._models.by_session(session.session_id):
                if prior.key == content_key and prior.visibility != Visibility.DISCARDED:
                    return SubmitResult(
                        prior,
                        False,
                        collection=self._collect(collection, prior.lineage, prior.snapshot_id),
                    )
        visibility = Visibility.UNRELEASED if maintainer else Visibility.UNLISTED
        origin = Origin.MAINTAINER if maintainer else Origin.USER
        for _ in range(_SAVE_ATTEMPTS):
            lineage = self._models.lineage(base.lineage) if base and same_lineage else []
            snapshot = ModelSnapshot(
                snapshot_id=content_key if maintainer else new_unlisted_id(),
                session_id=session.session_id,
                concept=session.concept,
                inputs=session.inputs,
                draft=draft,
                created_at=self._clock.now(),
                citations_checked=checked,
                visibility=visibility,
                origin=origin,
                generator=generator,
                lineage_id=lineage[0].lineage if lineage else "",
                version=(max(s.version for s in lineage) + 1) if lineage else 1,
                based_on=base.snapshot_id if base else None,
                content_key="" if maintainer else content_key,
                generator_usage=generator_usage,
                warnings=tuple(found_warnings),
            )
            if self._models.save_snapshot(snapshot):
                ref = (
                    None
                    if maintainer
                    else self._collect(collection, snapshot.lineage, snapshot.snapshot_id)
                )
                return SubmitResult(snapshot, True, collection=ref)
            stored = self._models.get_snapshot(snapshot.snapshot_id)
            if stored is not None:  # same content already stored (maintainer ids are hashes)
                return SubmitResult(stored, False)
        raise ModelStateError("the model was changed concurrently; submit again")

    def _collect(
        self, collection: str | None, lineage: str, version_id: str
    ) -> CollectionRef | None:
        if self._collections is None:
            return None
        return self._collections.save(collection, KIND_MODEL, lineage, version_id)

    # -- snapshots -------------------------------------------------------------------------------

    def snapshot(self, snapshot_id: str) -> ModelSnapshot:
        s = self._models.get_snapshot(snapshot_id)
        if s is None:
            raise NotFoundError(f"model {snapshot_id} not found")
        return s

    def visible_snapshot(self, snapshot_id: str, maintainer: bool = False) -> ModelSnapshot:
        """Official and unlisted models for anyone with the id; unreleased and discarded ones
        only for a maintainer (404 otherwise, so their existence is not revealed)."""
        s = self._models.get_snapshot(snapshot_id)
        if s is None or s.visibility not in _visible(maintainer):
            raise NotFoundError(f"model {snapshot_id} not found")
        return s

    def lineage_info(self, snap: ModelSnapshot, maintainer: bool = False) -> dict[str, Any]:
        visible = _visible(maintainer)
        versions = [s for s in self._models.lineage(snap.lineage) if s.visibility in visible]
        if not any(s.snapshot_id == snap.snapshot_id for s in versions):
            versions.append(snap)
            versions.sort(key=lambda s: s.version)
        latest = versions[-1]
        return {
            "id": snap.lineage,
            "version": snap.version,
            "versions": len(versions),
            "based_on": snap.based_on,
            "latest_id": latest.snapshot_id,
            "history": [
                {
                    "id": s.snapshot_id,
                    "version": s.version,
                    "created_at": s.created_at.isoformat(),
                    "visibility": s.visibility,
                }
                for s in versions
            ],
        }

    def revise(self, snapshot_id: str, maintainer: bool = False) -> dict[str, Any]:
        """A new session on the CURRENT builds of the model's APIs, with the model as the
        starting draft; submitting it with based_on makes the next version."""
        base = self.visible_snapshot(snapshot_id, maintainer)
        if base.visibility == Visibility.DISCARDED:
            raise ModelStateError(f"model {snapshot_id} was discarded")
        session = self.start(
            [i.api for i in base.inputs],
            base.concept,
            Origin.MAINTAINER if maintainer else Origin.USER,
            based_on=base.snapshot_id,
        )
        return {
            "model_session": session.session_id,
            "session_id": session.session_id,
            "based_on": base.snapshot_id,
            "concept": session.concept,
            "inputs": [{"api": i.api, "build": i.build} for i in session.inputs],
            "starting_draft": draft_json(base.draft),
            "claude_prompt": claude_prompt(session, maintainer),
            "next": "Call get_model_context(model_session), edit starting_draft, then "
            f'submit_model_draft(model_session, draft, based_on="{base.snapshot_id}").',
        }

    def release(
        self, snapshot_id: str, supersedes: Sequence[str] = (), override_reason: str | None = None
    ) -> ModelSnapshot:
        """Make an unreleased model official. ``supersedes``: official models of the same concept
        (case-insensitive, any API set) the maintainer chose to replace: they become superseded
        (readable by id, not listed, superseded_by this one). Never automatic."""
        s = self.snapshot(snapshot_id)
        if s.visibility != Visibility.UNRELEASED:
            raise ModelStateError(f"model {snapshot_id} is {s.visibility}, not unreleased")
        wanted = self._check_supersedes(s, supersedes)
        override = self.check_release_gate(s, override_reason)
        now = self._clock.now()
        if override is not None:
            override = {**override, "at": now.isoformat()}
        self._models.set_visibility(snapshot_id, Visibility.OFFICIAL, now, override)
        for old in wanted:
            self._models.supersede(old, snapshot_id, now)
        return self.snapshot(snapshot_id)

    def check_release_gate(
        self, snap: ModelSnapshot, override_reason: str | None = None
    ) -> dict[str, Any] | None:
        """The model gold gate (no invented mapping; recall at least the threshold once set);
        a model without gold for its concept passes. A maintainer's reason overrides the
        overridable failures (never an invented mapping): returns {reason, failures} to keep
        with the release, or None when nothing was overridden."""
        failures = self._release_gate(snap) if self._release_gate is not None else []
        if not failures:
            return None
        text = "; ".join(f.message for f in failures)
        reason = (override_reason or "").strip()
        hard = [f for f in failures if not f.overridable]
        if hard or not reason:
            hint = "" if hard else " (a maintainer may release over it with a reason)"
            raise ModelStateError(
                f"model {snap.snapshot_id} fails the model gold gate: {text}{hint}"
            )
        return {"reason": reason[:500], "failures": [f.message for f in failures]}

    def supersede(self, snapshot_id: str, supersedes: Sequence[str]) -> ModelSnapshot:
        """An already official model retires older official models of its concept (the same
        rules as release; maintainer only, never automatic)."""
        s = self.snapshot(snapshot_id)
        if s.visibility != Visibility.OFFICIAL:
            raise ModelStateError(f"model {snapshot_id} is {s.visibility}, not official")
        wanted = self._check_supersedes(s, supersedes)
        if not wanted:
            raise ModelInputError("supersedes is empty")
        now = self._clock.now()
        for old in wanted:
            self._models.supersede(old, snapshot_id, now)
        return s

    def _check_supersedes(self, s: ModelSnapshot, supersedes: Sequence[str]) -> list[str]:
        wanted = list(dict.fromkeys(supersedes))
        allowed = {c["id"] for c in self.supersedable(s)}
        bad = [i for i in wanted if i not in allowed]
        if bad:
            raise ModelStateError(
                f"not an official {normalize_concept(s.concept)} model that this one can "
                f"supersede: {', '.join(bad)}"
            )
        return wanted

    def replaced_by(self, snap: ModelSnapshot) -> tuple[str, ...]:
        """The models this one superseded (their superseded_by is it), newest first."""
        api = snap.inputs[0].api if snap.inputs else None
        return tuple(
            o.snapshot_id
            for o in self._models.list_snapshots(api, 200, (Visibility.SUPERSEDED,))
            if o.superseded_by == snap.snapshot_id
        )

    def supersedable(self, snap: ModelSnapshot) -> list[dict[str, Any]]:
        """Official models of the same concept (case-insensitive) over ANY API set, other than
        this lineage, newest first; ``covered`` = its APIs are a subset of this model's."""
        mine = {i.api for i in snap.inputs}
        key = concept_key(snap.concept)
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for api in sorted(mine):
            for o in self._models.list_snapshots(api, 200, (Visibility.OFFICIAL,)):
                if concept_key(o.concept) != key or o.lineage == snap.lineage:
                    continue
                if o.snapshot_id in seen:
                    continue
                seen.add(o.snapshot_id)
                apis = [i.api for i in o.inputs]
                out.append(
                    {
                        "id": o.snapshot_id,
                        "name": o.draft.name,
                        "concept": normalize_concept(o.concept),
                        "apis": apis,
                        "version": o.version,
                        "stale": bool(self.stale_inputs(o)),
                        "covered": set(apis) <= mine,
                        "createdAt": o.created_at.isoformat(),
                    }
                )
        return sorted(out, key=lambda c: c["createdAt"], reverse=True)

    def discard(self, snapshot_id: str) -> ModelSnapshot:
        s = self.snapshot(snapshot_id)
        if s.visibility != Visibility.UNRELEASED:
            raise ModelStateError(f"model {snapshot_id} is {s.visibility}, not unreleased")
        self._models.set_visibility(snapshot_id, Visibility.DISCARDED, None)
        return self.snapshot(snapshot_id)

    def mine(self, owner_keys: Sequence[str]) -> list[ModelSnapshot]:
        """The latest version of every lineage started with one of these owner keys."""
        keys = [k for k in dict.fromkeys(owner_keys) if isinstance(k, str) and k.strip()]
        if len(keys) > MAX_OWNER_KEYS:
            raise ModelInputError(f"at most {MAX_OWNER_KEYS} owner keys")
        out: list[ModelSnapshot] = []
        for lineage_id in self._models.lineages_for_owner([owner_key_hash(k) for k in keys]):
            versions = [
                s for s in self._models.lineage(lineage_id) if s.visibility != Visibility.DISCARDED
            ]
            if versions:
                out.append(versions[-1])
        return sorted(out, key=lambda s: s.created_at, reverse=True)

    def stale_inputs(self, snapshot: ModelSnapshot) -> list[dict[str, str | None]]:
        """Pinned builds that are no longer their API's ``latest`` (empty = current)."""
        out: list[dict[str, str | None]] = []
        for pin in snapshot.inputs:
            try:
                current: str | None = self._resolver.resolve(pin.api).build.build_id.value
            except NotFoundError:
                current = None
            if current != pin.build:
                out.append({"api": pin.api, "pinned": pin.build, "current": current})
        return out

    def list(
        self,
        api: str | None = None,
        limit: int = 50,
        visibilities: Sequence[str] = (Visibility.OFFICIAL,),
    ) -> list[ModelSnapshot]:
        """Newest first. Public lists show official models only, one per lineage (its latest
        official version)."""
        limit = max(1, min(limit, 200))
        items = self._models.list_snapshots(api, limit * 4, tuple(visibilities))
        if tuple(visibilities) == (Visibility.OFFICIAL,):
            seen: set[str] = set()
            latest = []
            for s in sorted(items, key=lambda s: (s.lineage, -s.version)):
                if s.lineage not in seen:
                    seen.add(s.lineage)
                    latest.append(s)
            items = sorted(latest, key=lambda s: (-s.created_at.timestamp(), s.snapshot_id))
            # One official model per concept (case-insensitive) and API set: the newest; the
            # others stay readable by id and are named by same_concept() (never deleted).
            groups: set[tuple[str, frozenset[str]]] = set()
            grouped = []
            for s in items:
                key = _concept_group(s)
                if key not in groups:
                    groups.add(key)
                    grouped.append(s)
            items = grouped
        return items[:limit]

    def same_concept(self, snap: ModelSnapshot) -> tuple[str, ...]:
        """Other official models of the same concept (case-insensitive) over the same APIs,
        newest first (e.g. "Order" and "order" made before concept spelling was normalised)."""
        key = _concept_group(snap)
        api = snap.inputs[0].api if snap.inputs else None
        others = [
            s
            for s in self._models.list_snapshots(api, 200, (Visibility.OFFICIAL,))
            if _concept_group(s) == key and s.lineage != snap.lineage
        ]
        seen: set[str] = set()
        out = []
        for s in others:
            if s.lineage not in seen:
                seen.add(s.lineage)
                out.append(s.snapshot_id)
        return tuple(out)


def _returned_by(doc: Document) -> str | None:
    """A model's operation, when the package names it (x-plume-returned-by: endpoint ids)."""
    ops = doc.raw.get("x-plume-returned-by") if isinstance(doc.raw, dict) else None
    if not ops:
        return None
    method, _, path = str(ops[0]).removeprefix("endpoint:").split("@", 1)[0].partition("~")
    return f"{method} {path}"


def _concept_group(s: ModelSnapshot) -> tuple[str, frozenset[str]]:
    return concept_key(s.concept), frozenset(i.api for i in s.inputs)


def _visible(maintainer: bool) -> tuple[str, ...]:
    return Visibility.ALL if maintainer else Visibility.PUBLIC
