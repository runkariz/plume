"""Model sets: sessions, the set context (members + relation candidates), validated submits,
versions, visibility and release (docs/design/model-relations.md)."""

import json
import secrets
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from plume.application.errors import NotFoundError
from plume.application.models.concepts import ModelInputError, concept_key, resolve_apis
from plume.application.models.relations import SuggestRelated
from plume.application.models.sessions import (
    MAX_DRAFT_CHARS,
    MAX_OWNER_KEYS,
    ModelDraftRefusedError,
    ModelSessions,
    ModelStateError,
    new_owner_key,
    normalize_concept,
    owner_key_hash,
)
from plume.application.ports.model_repo import ModelRepo
from plume.application.ports.model_set_repo import ModelSetRepo, SetSession
from plume.application.reader.resolve import BuildResolver, ResolvedBuild
from plume.domain.models.canonical_model import DraftFormatError
from plume.domain.models.model_set import (
    MAX_MEMBERS,
    ModelSetSnapshot,
    parse_set_draft,
    set_content_key,
    set_draft_json,
    validate_set,
)
from plume.domain.models.snapshot import ModelSnapshot, Origin, PinnedInput, Visibility
from plume.domain.models.validation import Issue
from plume.domain.shared.clock import Clock

CONTEXT_DOCS_FEW = 20
CONTEXT_DOCS_MANY = 10  # per concept per API when a set has more than 3 concepts
_SAVE_ATTEMPTS = 5

SET_INSTRUCTIONS = """\
A model set is several canonical models (members) with relations between them. Steps:
1. For each member concept: reuse a listed model pinned to these builds, or write one in its
   member session (get_model_context / get_model_evidence / submit_model_draft) as usual.
2. Relations: read relation_candidates. For EVERY relation you want to include, ASK THE USER
   which design they want, offering the candidate's options (embedded: the parent model holds
   the child, e.g. Product.variants; reference: the child holds a key, e.g. Variant.product_id
   -> Product.id; and the cardinality). Never decide a design silently. Put a relation the user
   has not decided in open_questions, or submit it with "confirmed": false.
3. A relation's fields must exist in the member models (embed.field on `from`; ref.field on
   `from`, ref.key on `to`): add them to the member model first if needed. Cite, per API, how the
   API documents it (sources.<api>: {as, paths, fetch, evidence}), from the candidate's evidence.
4. Aliases (different names at the same documented position, e.g. Shopify variant / WooCommerce
   variation) are offers: include one under "aliases" only if the user accepts it.
5. submit_model_set(set_session, draft). Refusals come back with codes; fix and resubmit.
"""

SET_DRAFT_FORMAT: dict[str, Any] = {
    "name": "Catalog",
    "description": "Products with their variants.",
    "members": [
        {"concept": "Product", "model_id": "<model snapshot id>"},
        {"concept": "Variant", "model_id": "<model snapshot id>"},
    ],
    "relations": [
        {
            "id": "product-variants",
            "from": "Product",
            "to": "Variant",
            "kind": "embedded",
            "cardinality": "1:n",
            "embed": {"field": "variants"},
            "confirmed": True,
            "candidate": "product>variant",
            "sources": {
                "<api id>": {
                    "as": "nested",
                    "paths": ["products[].variants"],
                    "evidence": [{"doc_id": "...", "quote": "verbatim text"}],
                },
                "<other api>": {
                    "as": "sub_resource",
                    "fetch": "GET /products/{product_id}/variations",
                    "evidence": [{"doc_id": "...", "quote": "verbatim text"}],
                },
            },
        },
        {
            "id": "variant-product",
            "from": "Variant",
            "to": "Product",
            "kind": "reference",
            "cardinality": "n:1",
            "ref": {"field": "product_id", "key": "id"},
            "confirmed": False,
            "sources": {"<api id>": {"as": "id_field", "paths": ["product_id"], "evidence": []}},
        },
    ],
    "aliases": [{"names": {"<api>": "variant", "<other api>": "variation"}, "concept": "Variant"}],
    "open_questions": [{"question": "Embed variants or reference them?"}],
}


def new_unlisted_set_id() -> str:
    return "us-" + secrets.token_urlsafe(16)


def _visible(maintainer: bool) -> tuple[str, ...]:
    return Visibility.ALL if maintainer else Visibility.PUBLIC


@dataclass(frozen=True, slots=True)
class SetSubmitResult:
    snapshot: ModelSetSnapshot
    created: bool
    owner_key: str | None = None


@dataclass(frozen=True, slots=True)
class SetRelease:
    snapshot: ModelSetSnapshot
    released_members: tuple[str, ...]  # member model ids released with the set (design D3)


class ModelSets:
    def __init__(
        self,
        resolver: BuildResolver,
        sessions: ModelSessions,
        models: ModelRepo,
        sets: ModelSetRepo,
        related: SuggestRelated,
        clock: Clock,
    ) -> None:
        self._resolver = resolver
        self._sessions = sessions
        self._models = models
        self._sets = sets
        self._related = related
        self._clock = clock

    # -- sessions --------------------------------------------------------------------------------

    def start(
        self,
        apis: list[str],
        concepts: list[str],
        origin: str = Origin.USER,
        based_on: str | None = None,
        aliases: Sequence[dict[str, Any]] = (),
    ) -> SetSession:
        """`aliases`: accepted ones, [{concept, names: {api: that API's name}}] (design D2):
        that member's evidence in that API is searched under the alias name."""
        resolved = resolve_apis(self._resolver, apis)
        names = list(dict.fromkeys(normalize_concept(c) for c in concepts if concept_key(c)))
        if not 1 <= len(names) <= MAX_MEMBERS:
            raise ModelInputError(f"pick 1..{MAX_MEMBERS} different concepts")
        inputs = tuple(PinnedInput(r.api.api_id.value, r.build.build_id.value) for r in resolved)
        accepted = self._aliases(aliases, names, {i.api for i in inputs})
        by_concept = dict(accepted)
        members = tuple(
            (
                c,
                self._sessions.start_pinned(
                    inputs, c, origin, aliases=by_concept.get(c, ())
                ).session_id,
            )
            for c in names
        )
        session = SetSession(
            session_id=f"ss-{uuid.uuid4().hex[:16]}",
            inputs=inputs,
            concepts=tuple(names),
            member_sessions=members,
            created_at=self._clock.now(),
            origin=origin,
            based_on=based_on,
            aliases=accepted,
        )
        self._sets.save_session(session)
        return session

    @staticmethod
    def _aliases(
        raw: Sequence[Any], concepts: list[str], apis: set[str]
    ) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
        by_key = {concept_key(c): c for c in concepts}
        out: dict[str, dict[str, str]] = {}
        for i, a in enumerate(raw or ()):
            if not isinstance(a, dict) or not isinstance(a.get("names"), dict):
                raise ModelInputError(f"aliases[{i}] must be {{concept, names: {{api: name}}}}")
            concept = by_key.get(concept_key(str(a.get("concept", ""))))
            if concept is None:
                raise ModelInputError(f"aliases[{i}].concept must be one of the set's concepts")
            for api, name in a["names"].items():
                if api not in apis or not isinstance(name, str) or not concept_key(name):
                    raise ModelInputError(f"aliases[{i}]: {api!r} is not one of the set's APIs")
                out.setdefault(concept, {})[api] = name.strip()
        return tuple((c, tuple(sorted(n.items()))) for c, n in sorted(out.items()))

    def get_session(self, session_id: str) -> SetSession:
        s = self._sets.get_session(session_id)
        if s is None:
            raise NotFoundError(f"model set session {session_id} not found")
        return s

    def _pinned(self, inputs: tuple[PinnedInput, ...]) -> tuple[ResolvedBuild, ...]:
        return tuple(self._resolver.resolve(i.api, i.build) for i in inputs)

    def context(self, session_id: str, maintainer: bool = False) -> dict[str, Any]:
        """Members (each a model session with its evidence index and reusable models) and the
        relation candidates between them, bounded."""
        s = self.get_session(session_id)
        cap = CONTEXT_DOCS_MANY if len(s.concepts) > 3 else CONTEXT_DOCS_FEW
        keys = {concept_key(c): c for c in s.concepts}
        members = []
        for concept, member_session in s.member_sessions:
            ctx = self._sessions.context(member_session, cap)
            members.append(
                {
                    "concept": concept,
                    "model_session": member_session,
                    "session_id": member_session,
                    "apis": ctx["apis"],
                    "reusable_models": [
                        {
                            "model_id": m.snapshot_id,
                            "name": m.draft.name,
                            "version": m.version,
                            "visibility": m.visibility,
                        }
                        for m in self._sessions.reusable(s.inputs, concept, maintainer)[:5]
                    ],
                }
            )
        candidates, aliases, labels = self._related.candidates(self._pinned(s.inputs))
        relevant = [c for c in candidates if c.parent in keys and c.child in keys]
        alias_list = [a for a in aliases if a.parent in keys]
        return {
            "set_session": s.session_id,
            "set_session_id": s.session_id,
            "inputs": [{"api": i.api, "build": i.build} for i in s.inputs],
            "accepted_aliases": s.aliases_json(),
            "members": members,
            "relation_candidates": [
                {
                    "id": c.id,
                    "from": keys[c.parent],
                    "to": keys[c.child],
                    "options": [
                        {"kind": o.kind, "cardinality": o.cardinality, "needs": o.needs}
                        for o in c.options(labels)
                    ],
                    "sources": {
                        api: [
                            {
                                "as": e.kind,
                                "doc_id": e.doc_id,
                                "quote": e.quote,
                                "paths": list(e.paths),
                                "fetch": e.fetch,
                            }
                            for e in es
                        ]
                        for api, es in sorted(c.sources.items())
                    },
                }
                for c in relevant
            ],
            "aliases": [
                {
                    "parent": keys[a.parent],
                    "names": a.names,
                    "evidence": {
                        api: {"as": e.kind, "doc_id": e.doc_id, "quote": e.quote, "fetch": e.fetch}
                        for api, e in a.evidence.items()
                    },
                }
                for a in alias_list
            ],
            "instructions": SET_INSTRUCTIONS,
            "draft_format": SET_DRAFT_FORMAT,
        }

    def session_status(self, session_id: str) -> dict[str, Any]:
        s = self.get_session(session_id)
        done = self._sets.by_session(session_id)
        latest = done[0] if done else None
        return {
            "set_session": s.session_id,
            "set_session_id": s.session_id,
            "status": "submitted" if latest else "open",
            "set_id": latest.set_id if latest else None,
            "visibility": latest.visibility if latest else None,
            "concepts": list(s.concepts),
            "member_sessions": dict(s.member_sessions),
            "based_on": s.based_on,
            "aliases": s.aliases_json(),
        }

    # -- submit ----------------------------------------------------------------------------------

    def _members(
        self, draft_members: Sequence[Any], inputs: tuple[PinnedInput, ...], maintainer: bool
    ) -> tuple[dict[str, ModelSnapshot], list[Issue]]:
        found: dict[str, ModelSnapshot] = {}
        issues: list[Issue] = []
        pins = {(i.api, i.build) for i in inputs}
        allowed = (
            (Visibility.OFFICIAL, Visibility.UNRELEASED)
            if maintainer
            else (Visibility.OFFICIAL, Visibility.UNLISTED)
        )
        for m in draft_members:
            snap = self._models.get_snapshot(m.model_id)
            if snap is None or snap.visibility not in allowed:
                issues.append(
                    Issue(
                        "MEMBER_NOT_VISIBLE",
                        m.concept,
                        None,
                        f"{m.model_id} is not a model this set may use",
                    )
                )
                continue
            if concept_key(snap.concept) != concept_key(m.concept):
                issues.append(
                    Issue(
                        "MEMBER_CONCEPT_MISMATCH",
                        m.concept,
                        None,
                        f"{m.model_id} is a {snap.concept} model",
                    )
                )
            if {(i.api, i.build) for i in snap.inputs} != pins:
                issues.append(
                    Issue(
                        "MEMBER_STALE",
                        m.concept,
                        None,
                        f"{m.model_id} is pinned to other builds: revise it in this set session",
                    )
                )
            found[m.concept] = snap
        return found, issues

    def submit(
        self,
        session_id: str,
        raw: Any,
        based_on: str | None = None,
        maintainer: bool = False,
        generator: str = "claude",
    ) -> SetSubmitResult:
        s = self.get_session(session_id)
        if len(json.dumps(raw, default=str)) > MAX_DRAFT_CHARS:
            raise ModelDraftRefusedError(
                [Issue("INVALID_FORMAT", "", None, f"set over {MAX_DRAFT_CHARS} characters")]
            )
        try:
            draft = parse_set_draft(raw)
        except DraftFormatError as exc:
            raise ModelDraftRefusedError([Issue("INVALID_FORMAT", "", None, str(exc))]) from exc
        members, issues = self._members(draft.members, s.inputs, maintainer)
        if not issues:
            issues = validate_set(
                draft,
                {c: m.draft for c, m in members.items()},
                frozenset(i.api for i in s.inputs),
                self._sessions.oracle_for(s.inputs),
            )
        if issues:
            raise ModelDraftRefusedError(issues)
        content_key = set_content_key(s.inputs, draft)
        base_id = based_on or s.based_on
        base = self.visible(base_id, maintainer) if base_id else None
        if base is not None and base.visibility == Visibility.DISCARDED:
            raise ModelStateError(f"model set {base.set_id} was discarded")
        same_lineage = base is not None and (
            base.visibility in (Visibility.OFFICIAL, Visibility.UNRELEASED)
            if maintainer
            else base.visibility == Visibility.UNLISTED
        )
        if not maintainer:
            for prior in self._sets.by_session(session_id):
                if prior.key == content_key and prior.visibility != Visibility.DISCARDED:
                    return SetSubmitResult(prior, False)
        owner_key = None if maintainer or same_lineage else new_owner_key()
        for _ in range(_SAVE_ATTEMPTS):
            lineage = self._sets.lineage(base.lineage) if base and same_lineage else []
            snap = ModelSetSnapshot(
                set_id=content_key if maintainer else new_unlisted_set_id(),
                session_id=session_id,
                inputs=s.inputs,
                draft=draft,
                created_at=self._clock.now(),
                visibility=Visibility.UNRELEASED if maintainer else Visibility.UNLISTED,
                origin=Origin.MAINTAINER if maintainer else Origin.USER,
                generator=generator,
                lineage_id=lineage[0].lineage if lineage else "",
                version=(max(x.version for x in lineage) + 1) if lineage else 1,
                based_on=base.set_id if base else None,
                content_key="" if maintainer else content_key,
            )
            if self._sets.save_set(snap, owner_key_hash(owner_key) if owner_key else None):
                return SetSubmitResult(snap, True, owner_key)
            stored = self._sets.get_set(snap.set_id)
            if stored is not None:
                return SetSubmitResult(stored, False)
        raise ModelStateError("the set was changed concurrently; submit again")

    # -- reading, versions, release ----------------------------------------------------------------

    def visible(self, set_id: str, maintainer: bool = False) -> ModelSetSnapshot:
        s = self._sets.get_set(set_id)
        if s is None or s.visibility not in _visible(maintainer):
            raise NotFoundError(f"model set {set_id} not found")
        return s

    def member_models(self, s: ModelSetSnapshot) -> dict[str, ModelSnapshot | None]:
        return {m.concept: self._models.get_snapshot(m.model_id) for m in s.draft.members}

    def stale_inputs(self, s: ModelSetSnapshot) -> list[dict[str, str | None]]:
        out: list[dict[str, str | None]] = []
        for pin in s.inputs:
            try:
                current: str | None = self._resolver.resolve(pin.api).build.build_id.value
            except NotFoundError:
                current = None
            if current != pin.build:
                out.append({"api": pin.api, "pinned": pin.build, "current": current})
        return out

    def lineage_info(self, s: ModelSetSnapshot, maintainer: bool = False) -> dict[str, Any]:
        visible = _visible(maintainer)
        versions = [x for x in self._sets.lineage(s.lineage) if x.visibility in visible]
        if not any(x.set_id == s.set_id for x in versions):
            versions = sorted([*versions, s], key=lambda x: x.version)
        return {
            "id": s.lineage,
            "version": s.version,
            "versions": len(versions),
            "based_on": s.based_on,
            "latest_id": versions[-1].set_id,
            "history": [
                {
                    "id": x.set_id,
                    "version": x.version,
                    "created_at": x.created_at.isoformat(),
                    "visibility": x.visibility,
                }
                for x in versions
            ],
        }

    def propose_relations(
        self, session_id: str, members: dict[str, str]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Relation PROPOSALS for generated members (confirmed: false), from the documented
        candidates only, with the first design whose fields exist in the member models. A
        candidate no design fits becomes an open question for the maintainer."""
        s = self.get_session(session_id)
        keys = {concept_key(c): c for c in s.concepts}
        drafts = {}
        for concept, model_id in members.items():
            snap = self._models.get_snapshot(model_id)
            if snap is not None:
                drafts[concept] = dict(snap.draft.walk())
        candidates, _, labels = self._related.candidates(self._pinned(s.inputs))
        relations: list[dict[str, Any]] = []
        questions: list[dict[str, Any]] = []
        for c in candidates:
            if c.parent not in keys or c.child not in keys:
                continue
            parent, child = keys[c.parent], keys[c.child]
            fp, fc = drafts.get(parent, {}), drafts.get(child, {})
            sources = {
                api: {
                    "as": es[0].kind,
                    "paths": list(es[0].paths) if es[0].kind == "id_field" else [],
                    "fetch": es[0].fetch,
                    "evidence": [{"doc_id": e.doc_id, "quote": e.quote} for e in es[:2]],
                }
                for api, es in sorted(c.sources.items())
            }
            design = None
            for o in c.options(labels):
                if o.kind == "embedded":
                    want = "array" if o.cardinality == "1:n" else "object"
                    holder = next(
                        (
                            p
                            for p, f in fp.items()
                            if f.type == want and concept_key(f.name) == c.child
                        ),
                        None,
                    )
                    if holder:
                        design = {
                            "from": parent,
                            "to": child,
                            "kind": "embedded",
                            "cardinality": o.cardinality,
                            "embed": {"field": holder},
                        }
                else:
                    key_field = next(
                        (p for p in fc if p.split(".")[-1] in (f"{c.parent}_id", "parent_id")),
                        None,
                    )
                    if key_field and "id" in fp:
                        design = {
                            "from": child,
                            "to": parent,
                            "kind": "reference",
                            "cardinality": o.cardinality,
                            "ref": {"field": key_field, "key": "id"},
                        }
                if design:
                    break
            if design is None:
                kinds = sorted({e.kind for es in c.sources.values() for e in es})
                questions.append(
                    {
                        "question": f"How should {parent} and {child} relate?",
                        "detail": f"The docs relate them ({', '.join(kinds)}), but the generated "
                        "models have no field for any documented design yet.",
                        "options": [f"{o.kind} {o.cardinality}" for o in c.options(labels)],
                    }
                )
                continue
            relations.append(
                {
                    "id": f"{c.parent}-{c.child}",
                    **design,
                    "confirmed": False,
                    "candidate": c.id,
                    "sources": sources,
                }
            )
        return relations, questions

    def editable_options(self, x: ModelSetSnapshot) -> dict[str, list[dict[str, Any]]]:
        """Per relation, the designs the web may switch to without new fields: the current one,
        the other kind (embedded <-> reference) and the other cardinality. A design whose fields
        are missing from the member models is listed with `editable: false` and `missing`."""
        drafts = {c: m.draft for c, m in self.member_models(x).items() if m is not None}
        out: dict[str, list[dict[str, Any]]] = {}
        for r in x.draft.relations:
            parent, child = (r.from_, r.to) if r.kind == "embedded" else (r.to, r.from_)
            options: list[dict[str, Any]] = []
            p_model, c_model = drafts.get(parent), drafts.get(child)
            if p_model is None or c_model is None:
                out[r.id] = options
                continue
            fields_p = dict(p_model.walk())
            fields_c = dict(c_model.walk())
            # embedded: a field of the parent holding the child (named after it)
            holder = next(
                (
                    p
                    for p, f in fields_p.items()
                    if f.type in ("array", "object")
                    and (concept_key(f.name) == concept_key(child) or p == r.embed_field)
                ),
                None,
            )
            for card in ("1:n", "1:1"):
                want = "array" if card == "1:n" else "object"
                ok = holder is not None and fields_p[holder].type == want
                options.append(
                    {
                        "kind": "embedded",
                        "from": parent,
                        "to": child,
                        "cardinality": card,
                        "embed": {"field": holder or f"{concept_key(child)}s"},
                        "ref": None,
                        "editable": ok,
                        "missing": [] if ok else [f"{parent}: an {want} field holding {child}"],
                    }
                )
            # reference: the child holds the parent's key
            key_field = next(
                (
                    p
                    for p in fields_c
                    if p.split(".")[-1] in (f"{concept_key(parent)}_id", "parent_id")
                    or p == r.ref_field
                ),
                None,
            )
            has_key = "id" in fields_p or (r.ref_key in fields_p if r.ref_key else False)
            key = r.ref_key if r.ref_key and r.ref_key in fields_p else "id"
            for card in ("n:1", "1:1"):
                missing = []
                if key_field is None:
                    missing.append(f"{child}: a field holding the {parent} id")
                if not has_key:
                    missing.append(f"{parent}: an id field")
                options.append(
                    {
                        "kind": "reference",
                        "from": child,
                        "to": parent,
                        "cardinality": card,
                        "embed": None,
                        "ref": {"field": key_field or f"{concept_key(parent)}_id", "key": key},
                        "editable": not missing,
                        "missing": missing,
                    }
                )
            for o in options:
                o["current"] = (
                    o["kind"] == r.kind
                    and o["cardinality"] == r.cardinality
                    and o["from"] == r.from_
                )
            out[r.id] = options
        return out

    def edit_relations(
        self,
        set_id: str,
        changes: Sequence[dict[str, Any]],
        maintainer: bool = False,
    ) -> SetSubmitResult:
        """The web edit: change relation DESIGNS (kind, cardinality, embed/ref, confirmed) of the
        latest version of a set; the evidence stays. Saved as a new version through the same
        validation (unlisted without the token, unreleased with it)."""
        base = self.visible(set_id, maintainer)
        latest = self.lineage_info(base, maintainer)["latest_id"]
        if latest != base.set_id:
            raise ModelStateError(f"{set_id} is not the latest version ({latest}); reload it")
        raw = set_draft_json(base.draft)
        by_id = {r["id"]: r for r in raw["relations"]}
        allowed = {"kind", "cardinality", "embed", "ref", "confirmed", "from", "to"}
        for change in changes:
            rel = by_id.get(str(change.get("id")))
            if rel is None:
                raise ModelInputError(f"no relation {change.get('id')!r} in {set_id}")
            extra = set(change) - allowed - {"id"}
            if extra:
                raise ModelInputError(f"only the design can change here, not {sorted(extra)}")
            ends = {rel["from"], rel["to"]}
            if {change.get("from", rel["from"]), change.get("to", rel["to"])} != ends:
                raise ModelInputError("a relation keeps its two members")
            rel.update({k: v for k, v in change.items() if k != "id"})
            rel["embed"] = rel["embed"] if rel["kind"] == "embedded" else None
            rel["ref"] = rel["ref"] if rel["kind"] == "reference" else None
        return self.submit(base.session_id, raw, base.set_id, maintainer, base.generator)

    def revise(self, set_id: str, maintainer: bool = False) -> dict[str, Any]:
        base = self.visible(set_id, maintainer)
        if base.visibility == Visibility.DISCARDED:
            raise ModelStateError(f"model set {set_id} was discarded")
        session = self.start(
            [i.api for i in base.inputs],
            [m.concept for m in base.draft.members],
            Origin.MAINTAINER if maintainer else Origin.USER,
            based_on=base.set_id,
            aliases=[{"concept": a.concept, "names": dict(a.names)} for a in base.draft.aliases],
        )
        pins = {(i.api, i.build) for i in session.inputs}
        current = {}
        for m in base.draft.members:
            snap = self._models.get_snapshot(m.model_id)
            current[m.concept] = bool(snap and {(i.api, i.build) for i in snap.inputs} == pins)
        return {
            "set_session": session.session_id,
            "set_session_id": session.session_id,
            "based_on": base.set_id,
            "member_sessions": dict(session.member_sessions),
            "starting_draft": set_draft_json(base.draft),
            "members_current": current,
            "next": "Members pinned to older builds (members_current false) must be revised "
            "(revise_model, then submit in this set session's member session). Ask the user "
            "about any relation change, then submit_model_set(set_session, draft, "
            f'based_on="{set_id}").',
        }

    def release(self, set_id: str) -> SetRelease:
        """Make an unreleased set official and release its unreleased members with it (D3).
        Refused while a relation is undecided or a member can't be released."""
        s = self._sets.get_set(set_id)
        if s is None:
            raise NotFoundError(f"model set {set_id} not found")
        if s.visibility != Visibility.UNRELEASED:
            raise ModelStateError(f"model set {set_id} is {s.visibility}, not unreleased")
        if s.undecided:
            raise ModelStateError(
                f"relations not decided by the user: {', '.join(s.undecided)}; confirm them first"
            )
        members = [self._models.get_snapshot(m.model_id) for m in s.draft.members]
        blocked = [
            m.model_id
            for m, snap in zip(s.draft.members, members, strict=True)
            if snap is None or snap.visibility not in (Visibility.OFFICIAL, Visibility.UNRELEASED)
        ]
        if blocked:
            raise ModelStateError(f"members that cannot be released: {', '.join(blocked)}")
        now = self._clock.now()
        released = []
        for snap in members:
            if snap is not None and snap.visibility == Visibility.UNRELEASED:
                self._models.set_visibility(snap.snapshot_id, Visibility.OFFICIAL, now)
                released.append(snap.snapshot_id)
        self._sets.set_visibility(set_id, Visibility.OFFICIAL, now)
        stored = self._sets.get_set(set_id)
        assert stored is not None  # noqa: S101 - just written
        return SetRelease(stored, tuple(released))

    def discard(self, set_id: str) -> ModelSetSnapshot:
        s = self._sets.get_set(set_id)
        if s is None:
            raise NotFoundError(f"model set {set_id} not found")
        if s.visibility != Visibility.UNRELEASED:
            raise ModelStateError(f"model set {set_id} is {s.visibility}, not unreleased")
        self._sets.set_visibility(set_id, Visibility.DISCARDED, None)
        stored = self._sets.get_set(set_id)
        assert stored is not None  # noqa: S101
        return stored

    def mine(self, owner_keys: Sequence[str]) -> list[ModelSetSnapshot]:
        keys = [k for k in dict.fromkeys(owner_keys) if isinstance(k, str) and k.strip()]
        if len(keys) > MAX_OWNER_KEYS:
            raise ModelInputError(f"at most {MAX_OWNER_KEYS} owner keys")
        out = []
        for lineage_id in self._sets.lineages_for_owner([owner_key_hash(k) for k in keys]):
            versions = [
                x for x in self._sets.lineage(lineage_id) if x.visibility != Visibility.DISCARDED
            ]
            if versions:
                out.append(versions[-1])
        return sorted(out, key=lambda x: x.created_at, reverse=True)

    def list(
        self,
        api: str | None = None,
        limit: int = 50,
        visibilities: Sequence[str] = (Visibility.OFFICIAL,),
    ) -> list[ModelSetSnapshot]:
        limit = max(1, min(limit, 200))
        items = self._sets.list_sets(api, limit * 4, tuple(visibilities))
        if tuple(visibilities) == (Visibility.OFFICIAL,):
            seen: set[str] = set()
            latest = []
            for x in sorted(items, key=lambda x: (x.lineage, -x.version)):
                if x.lineage not in seen:
                    seen.add(x.lineage)
                    latest.append(x)
            items = sorted(latest, key=lambda x: (-x.created_at.timestamp(), x.set_id))
        return items[:limit]
