"""Model sessions: pin builds, hand Claude the evidence pack, validate and store its draft."""

import json
import uuid
from dataclasses import dataclass
from typing import Any

from plume.application.errors import ApplicationError, NotFoundError
from plume.application.models.concepts import (
    ModelInputError,
    concept_docs,
    concept_key,
    resolve_apis,
)
from plume.application.ports.document_repo import DocumentRepo
from plume.application.ports.model_repo import ModelRepo, ModelSession
from plume.application.ports.search_index import DocumentSummary, FactQuery, SearchIndex
from plume.application.reader.resolve import BuildResolver
from plume.domain.knowledge.call_check import path_matches
from plume.domain.knowledge.document import DocumentKind, FieldLocation
from plume.domain.knowledge.fact import FactKind
from plume.domain.models.canonical_model import DraftFormatError, parse_draft
from plume.domain.models.snapshot import ModelSnapshot, PinnedInput, snapshot_id_for
from plume.domain.models.validation import Issue, Oracle, validate
from plume.domain.shared.clock import Clock
from plume.domain.shared.ids import BuildId

MAX_DOCS_PER_API = 20
EVIDENCE_BUDGET_CHARS = 20_000
MAX_DESCRIPTION = 300
_DATA_LOCATIONS = (FieldLocation.MODEL, FieldLocation.RESPONSE, FieldLocation.BODY)

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
                    "transform": None,
                    "evidence": [
                        {"doc_id": "model:order", "quote": "exact text copied from the document"}
                    ],
                }
            },
        }
    ],
    "open_questions": [{"question": "Is total before or after tax?", "options": ["gross", "net"]}],
}

INSTRUCTIONS = """\
Write ONE canonical model for the concept, then submit it with submit_model_draft(session_id,
draft). get_model_context lists the documents per API; get_model_evidence(session_id, api)
returns their fields page by page (follow next_cursor). Rules (refused otherwise):
- Map an API under fields[].sources only with fields that appear in that API's evidence: copy
  `paths[].path` exactly as listed (dotted names, [] for arrays).
- Every mapping needs evidence: `doc_id` from the evidence and a `quote` copied verbatim from
  that document's text (a field description is fine). Quotes are checked.
- `fetch` (optional) must be a documented endpoint, written "METHOD /path" as listed.
- Leave an API out of a field's sources when it has no such data; never invent fields.
- Use `transform` / `join` to describe derived values (e.g. "sum of line_items[].price").
- Put semantic choices you cannot settle from the evidence in open_questions; do not decide them.
Refusals come back with codes (MISSING_CITATION, QUOTE_NOT_FOUND, FIELD_NOT_FOUND,
ENDPOINT_NOT_FOUND, DOC_NOT_FOUND, API_NOT_IN_SESSION); fix those mappings and submit again.
"""


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


class ModelSessions:
    def __init__(
        self,
        resolver: BuildResolver,
        index: SearchIndex,
        facts: FactQuery,
        documents: DocumentRepo,
        models: ModelRepo,
        clock: Clock,
    ) -> None:
        self._resolver = resolver
        self._index = index
        self._facts = facts
        self._documents = documents
        self._models = models
        self._clock = clock

    # -- sessions --------------------------------------------------------------------------------

    def start(self, apis: list[str], concept: str) -> ModelSession:
        if not concept_key(concept):
            raise ModelInputError("concept is empty")
        resolved = resolve_apis(self._resolver, apis)
        session = ModelSession(
            session_id=f"s-{uuid.uuid4().hex[:16]}",
            concept=concept.strip(),
            inputs=tuple(PinnedInput(r.api.api_id.value, r.build.build_id.value) for r in resolved),
            created_at=self._clock.now(),
        )
        self._models.save_session(session)
        return session

    def existing(self, apis: list[str], concept: str) -> ModelSnapshot | None:
        """A stored snapshot for the same concept on the APIs' current builds, if any."""
        resolved = resolve_apis(self._resolver, apis)
        pins = {(r.api.api_id.value, r.build.build_id.value) for r in resolved}
        key = concept_key(concept)
        for snap in self._models.list_snapshots(resolved[0].api.api_id.value, 200):
            if concept_key(snap.concept) == key and {(i.api, i.build) for i in snap.inputs} == pins:
                return snap
        return None

    def get(self, session_id: str) -> ModelSession:
        s = self._models.get_session(session_id)
        if s is None:
            raise NotFoundError(f"model session {session_id} not found")
        return s

    def _concept_docs(self, concept: str, build: BuildId) -> list[DocumentSummary]:
        key = concept_key(concept)
        summaries, _ = self._index.browse(build, (), None, 100_000, 0)
        docs = list(concept_docs(summaries).get(key, []))
        if not docs:  # derived: documents whose text mentions the concept
            hits = self._index.text(
                build, concept, MAX_DOCS_PER_API, (DocumentKind.ENDPOINT, DocumentKind.MODEL)
            )
            docs = list(self._index.summaries(build, [h.doc_id for h in hits]).values())
        docs.sort(key=lambda d: (d.kind is not DocumentKind.MODEL, d.method != "GET", d.doc_id))
        return docs[:MAX_DOCS_PER_API]

    def _pin(self, session: ModelSession, api: str) -> BuildId:
        for p in session.inputs:
            if p.api == api:
                return BuildId(p.build)
        raise ModelInputError(f"{api} is not in session {session.session_id}")

    def context(self, session_id: str) -> dict[str, Any]:
        """A compact index of the evidence (small enough for any client): per API, the
        concept's documents with their field counts. Read the fields with ``evidence``."""
        session = self.get(session_id)
        per_api: list[dict[str, Any]] = []
        for pin in session.inputs:
            build = BuildId(pin.build)
            items = []
            for d in self._concept_docs(session.concept, build):
                full = self._documents.get_document(build, d.doc_id)
                if full is None:  # pragma: no cover
                    continue
                items.append(
                    {
                        "doc_id": d.doc_id,
                        "kind": d.kind.value,
                        "title": d.title,
                        "endpoint": f"{d.method} {d.path}" if d.method else None,
                        "fields": sum(1 for f in full.fields if f.location in _DATA_LOCATIONS),
                        "complete": full.complete,
                    }
                )
            per_api.append({"api": pin.api, "build": pin.build, "documents": items})
        return {
            "session_id": session.session_id,
            "concept": session.concept,
            "apis": per_api,
            "next": "Call get_model_evidence(session_id, api) for each API (follow next_cursor) "
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
            wanted = [d.doc_id for d in self._concept_docs(session.concept, build)]
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
        builds = {p.api: BuildId(p.build) for p in session.inputs}

        def doc_text(api: str, doc_id: str) -> str | None:
            d = self._documents.get_document(builds[api], doc_id)
            if d is None:
                return None
            descriptions = " ".join(f.description or "" for f in d.fields)
            return f"{d.title}\n{d.text}\n{descriptions}"

        def field_exists(api: str, path: str) -> bool:
            return bool(self._facts.find(builds[api], path, kind=FactKind.FIELD))

        def endpoint_exists(api: str, call: str) -> bool:
            method, _, path = call.strip().partition(" ")
            for f in self._facts.endpoints(builds[api]):
                m, _, p = f.name.partition(" ")
                if m == method.upper() and (p == path.strip() or path_matches(p, path.strip())):
                    return True
            return False

        return Oracle(doc_text, field_exists, endpoint_exists)

    def submit(self, session_id: str, raw: Any) -> SubmitResult:
        session = self.get(session_id)
        try:
            draft = parse_draft(raw)
        except DraftFormatError as exc:
            raise ModelDraftRefusedError([Issue("INVALID_FORMAT", "", None, str(exc))]) from exc
        apis = frozenset(p.api for p in session.inputs)
        issues = validate(draft, apis, self._oracle(session))
        if issues:
            raise ModelDraftRefusedError(issues)
        checked = sum(len(s.evidence) for f in draft.fields for _, s in f.sources)
        snapshot = ModelSnapshot(
            snapshot_id=snapshot_id_for(session.inputs, session.concept, draft),
            session_id=session.session_id,
            concept=session.concept,
            inputs=session.inputs,
            draft=draft,
            created_at=self._clock.now(),
            citations_checked=checked,
        )
        created = self._models.save_snapshot(snapshot)
        stored = self._models.get_snapshot(snapshot.snapshot_id)
        return SubmitResult(stored or snapshot, created)

    # -- snapshots -------------------------------------------------------------------------------

    def snapshot(self, snapshot_id: str) -> ModelSnapshot:
        s = self._models.get_snapshot(snapshot_id)
        if s is None:
            raise NotFoundError(f"model {snapshot_id} not found")
        return s

    def list(self, api: str | None = None, limit: int = 50) -> list[ModelSnapshot]:
        return self._models.list_snapshots(api, max(1, min(limit, 200)))
