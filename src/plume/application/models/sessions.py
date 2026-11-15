"""Model sessions: pin builds, hand Claude the evidence pack, validate and store its draft."""

import hashlib
import json
import secrets
import uuid
from collections.abc import Sequence
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
from plume.domain.models.snapshot import (
    ModelSnapshot,
    Origin,
    PinnedInput,
    Visibility,
    draft_json,
    snapshot_id_for,
)
from plume.domain.models.validation import Issue, Oracle, validate
from plume.domain.shared.clock import Clock
from plume.domain.shared.ids import BuildId

MAX_DOCS_PER_API = 20
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
                    "transform": None,
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
  that document's text (a field description is fine). Quotes are checked.
- `fetch` (optional) must be a documented endpoint, written "METHOD /path" as listed.
- Leave an API out of a field's sources when it has no such data; never invent fields.
- Use `transform` / `join` to describe derived values (e.g. "sum of line_items[].price").
- Put semantic choices you cannot settle from the evidence in open_questions; do not decide them.
- Nested objects: a field of type "object" or "array" may carry its own "fields" (at most 3
  levels). Map and cite every sub-field like a top-level one; its source paths are the API's
  full paths (e.g. "variants[].sku"). A container needs sources only when it is mapped as a
  whole; coverage counts the sub-fields.
Refusals come back with codes (MISSING_CITATION, QUOTE_NOT_FOUND, FIELD_NOT_FOUND,
ENDPOINT_NOT_FOUND, DOC_NOT_FOUND, API_NOT_IN_SESSION); fix those mappings and submit again.
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


def _last_literal_of(path: str) -> str:
    for seg in reversed(path.strip("/").split("/")):
        if seg and "{" not in seg:
            return seg.split(".", 1)[0]
    return ""


class ModelStateError(ApplicationError):
    code = "invalid_state"


def owner_key_hash(key: str) -> str:
    return hashlib.sha256(key.strip().encode()).hexdigest()


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
    owner_key: str | None = None  # shown once, when a user's submit starts a new lineage


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
        concept on the APIs' current builds, if any. Never someone's unlisted model."""
        resolved = resolve_apis(self._resolver, apis)
        pins = {(r.api.api_id.value, r.build.build_id.value) for r in resolved}
        key = concept_key(concept)
        visible = _visible(maintainer)
        allowed = tuple(v for v in visible if v != Visibility.UNLISTED)
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
        key = concept_key(concept)
        summaries, _ = self._index.browse(build, (), None, 100_000, 0)
        docs = list(concept_docs(summaries).get(key, []))
        if not docs:  # derived: documents whose text mentions the concept
            hits = self._index.text(
                build, concept, MAX_DOCS_PER_API, (DocumentKind.ENDPOINT, DocumentKind.MODEL)
            )
            docs = list(self._index.summaries(build, [h.doc_id for h in hits]).values())
        docs.sort(key=lambda d: _evidence_rank(d, key))
        return docs[:max_docs]

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
                        "endpoint": f"{d.method} {d.path}" if d.method else None,
                        "fields": sum(1 for f in full.fields if f.location in _DATA_LOCATIONS),
                        "complete": full.complete,
                    }
                )
            entry: dict[str, Any] = {"api": pin.api, "build": pin.build, "documents": items}
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

    def submit(
        self,
        session_id: str,
        raw: Any,
        based_on: str | None = None,
        maintainer: bool = False,
        generator: str = "claude",
    ) -> SubmitResult:
        """Validate and store a draft. A maintainer's model is stored unreleased (official only
        after ``release``); a user's is unlisted (readable by anyone with its id). ``based_on``
        (or the session's) makes it the next version of that model's lineage when the caller may
        add to it; otherwise a new lineage that records where it came from."""
        session = self.get(session_id)
        if len(json.dumps(raw, default=str)) > MAX_DRAFT_CHARS:
            raise ModelDraftRefusedError(
                [Issue("INVALID_FORMAT", "", None, f"draft over {MAX_DRAFT_CHARS} characters")]
            )
        try:
            draft = parse_draft(raw)
        except DraftFormatError as exc:
            raise ModelDraftRefusedError([Issue("INVALID_FORMAT", "", None, str(exc))]) from exc
        apis = frozenset(p.api for p in session.inputs)
        issues = validate(draft, apis, self._oracle(session))
        if issues:
            raise ModelDraftRefusedError(issues)
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
                    return SubmitResult(prior, False)
        visibility = Visibility.UNRELEASED if maintainer else Visibility.UNLISTED
        origin = Origin.MAINTAINER if maintainer else Origin.USER
        owner_key = None if maintainer or same_lineage else new_owner_key()
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
            )
            created = self._models.save_snapshot(
                snapshot, owner_key_hash(owner_key) if owner_key else None
            )
            if created:
                return SubmitResult(snapshot, True, owner_key)
            stored = self._models.get_snapshot(snapshot.snapshot_id)
            if stored is not None:  # same content already stored (maintainer ids are hashes)
                return SubmitResult(stored, False)
        raise ModelStateError("the model was changed concurrently; submit again")

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

    def release(self, snapshot_id: str) -> ModelSnapshot:
        s = self.snapshot(snapshot_id)
        if s.visibility != Visibility.UNRELEASED:
            raise ModelStateError(f"model {snapshot_id} is {s.visibility}, not unreleased")
        self._models.set_visibility(snapshot_id, Visibility.OFFICIAL, self._clock.now())
        return self.snapshot(snapshot_id)

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
        return items[:limit]


def _visible(maintainer: bool) -> tuple[str, ...]:
    return Visibility.ALL if maintainer else Visibility.PUBLIC
