"""Reader use cases. Retrieval only: Claude writes the answers, Plume returns cited material."""

import re
import time
from collections.abc import Callable, Sequence
from typing import Literal

from plume.application.errors import ApplicationError, NotFoundError
from plume.application.ports.api_repo import ApiRepo
from plume.application.ports.asset_repo import AssetRepo
from plume.application.ports.build_repo import BuildRepo
from plume.application.ports.document_repo import DocumentRepo
from plume.application.ports.embedder import Embedder, Vector
from plume.application.ports.eval_repo import EvalRepo
from plume.application.ports.search_index import ChunkHit, DocumentSummary, FactQuery, SearchIndex
from plume.application.ports.tag_repo import TagRepo
from plume.application.reader.dto import (
    ApiOverview,
    BuildRef,
    CheckCallResult,
    DocumentResult,
    FactMatch,
    FindFactResult,
    ParamCheck,
    SearchHit,
    SearchResult,
    TraceStep,
)
from plume.application.reader.ranking import (
    is_page,
    lift_operation_endpoints,
    pair_pages_with_endpoints,
    pair_units_with_endpoints,
)
from plume.application.reader.resolve import BuildResolver, ResolvedBuild
from plume.domain.knowledge.asset import ICON
from plume.domain.knowledge.call_check import normalize_call_path, path_matches, specificity
from plume.domain.knowledge.citation import Citation
from plume.domain.knowledge.document import (
    HTTP_METHODS,
    DocumentKind,
    FieldLocation,
    constraint_dict,
)
from plume.domain.knowledge.fact import Fact, FactKind
from plume.domain.knowledge.ranking import Fusion, reciprocal_rank_fusion
from plume.domain.shared.ids import BuildId

DEFAULT_FUSION = Fusion()
SearchMode = Literal["hybrid", "dense", "text"]
MAX_TOP_K = 50
SNIPPET_CHARS = 320


class ReaderInputError(ApplicationError, ValueError):
    code = "invalid_input"


def _ref(r: ResolvedBuild) -> BuildRef:
    return BuildRef(r.api.api_id.value, r.build.build_id.value, r.tag, r.docs_as_of)


def _timed[R](trace: list[TraceStep], source: str, label: str, fn: Callable[[], R]) -> R:
    start = time.perf_counter()
    result = fn()
    trace.append(TraceStep(source, label, round((time.perf_counter() - start) * 1000, 2)))
    return result


def _kinds(kind: str | None) -> tuple[DocumentKind, ...]:
    if kind in (None, "", "all"):
        return ()
    try:
        return (DocumentKind(kind),)
    except ValueError as exc:
        raise ReaderInputError(f"unknown kind {kind!r}") from exc


def _subtitle(summary: DocumentSummary | None, kind: DocumentKind) -> str:
    if summary is not None and summary.method and summary.path:
        return f"{summary.method} {summary.path}"
    if summary is not None and summary.resource:
        return f"{kind.value} · {summary.resource}"
    return kind.value


_PARAM_HINTS = ("param", "query", "argument", "=", "pagination", "paginate")


def _term_use(text: str, name: str) -> tuple[int, int]:
    """(score, position) of the best use of ``name`` as a parameter in ``text``: in backticks
    or quotes, next to "parameter" / "query" / "=" ("offset from UTC" in a date-format passage
    scores lower than "the `offset` query parameter"). (-1, -1) when it is not there."""
    flat = " ".join(text.split())
    best = (-1, -1)
    for m in re.finditer(rf"(?<![\w.]){re.escape(name)}(?![\w])", flat, re.IGNORECASE):
        around = flat[max(0, m.start() - 60) : m.end() + 60].lower()
        score = 1 + sum(2 for h in _PARAM_HINTS if h in around)
        if flat[max(0, m.start() - 1) : m.start()] in ("`", "'", '"'):
            score += 3
        if score > best[0]:
            best = (score, m.start())
    return best


def _snippet(text: str, query: str, exact: str | None = None) -> str:
    flat = " ".join(text.split())
    words = [w for w in query.lower().split() if len(w) > 2]
    lower = flat.lower()
    pos = min((lower.find(w) for w in words if lower.find(w) >= 0), default=0)
    if exact:
        score, at = _term_use(flat, exact)
        if score >= 0:
            pos = at
    start = max(0, pos - 80)
    piece = flat[start : start + SNIPPET_CHARS]
    return ("…" if start else "") + piece + ("…" if start + SNIPPET_CHARS < len(flat) else "")


class ListApiOverviews:
    def __init__(
        self,
        apis: ApiRepo,
        builds: BuildRepo,
        tags: TagRepo,
        index: SearchIndex,
        evals: EvalRepo | None = None,
        assets: AssetRepo | None = None,
    ) -> None:
        self._assets = assets
        self._evals = evals
        self._apis = apis
        self._resolver = BuildResolver(apis, builds, tags)
        self._tags = tags
        self._index = index

    def _overview(self, api: str, version: str | None) -> ApiOverview:
        r = self._resolver.resolve(api, version)
        spec = r.build.spec
        return ApiOverview(
            info=r.api,
            ref=_ref(r),
            counts=self._index.counts(r.build.build_id),
            tags=tuple(t.name.value for t in self._tags.list(r.api.api_id)),
            embed_model=spec.embed_model if spec else None,
            dims=spec.dims if spec else None,
            eval=self._evals.get(r.build.build_id) if self._evals else None,
            has_icon=bool(self._assets and self._assets.get(r.build.build_id, ICON)),
        )

    def execute(self) -> list[ApiOverview]:
        out = []
        for info in self._apis.list():
            try:
                out.append(self._overview(info.api_id.value, None))
            except NotFoundError:
                out.append(ApiOverview(info, None, {}, (), None, None))  # no published build
        return out

    def one(self, api: str, version: str | None = None) -> ApiOverview:
        return self._overview(api, version)


class BrowseDocuments:
    def __init__(self, resolver: BuildResolver, index: SearchIndex) -> None:
        self._resolver = resolver
        self._index = index

    def execute(
        self,
        api: str,
        kind: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
        version: str | None = None,
        tag: str | None = None,
    ) -> tuple[BuildRef, list[DocumentSummary], int]:
        if not 1 <= limit <= 500 or offset < 0:
            raise ReaderInputError("limit must be 1..500 and offset >= 0")
        r = self._resolver.resolve(api, version)
        items, total = self._index.browse(
            r.build.build_id, _kinds(kind), query, limit, offset, tag=tag or None
        )
        return _ref(r), items, total


def fuse_hits(
    dense: Sequence[ChunkHit],
    text: Sequence[ChunkHit],
    query: str,
    top_k: int,
    fusion: Fusion = DEFAULT_FUSION,
) -> list[SearchHit]:
    def best_per_doc(hits: Sequence[ChunkHit]) -> list[ChunkHit]:
        seen: dict[str, ChunkHit] = {}
        for h in hits:
            seen.setdefault(h.doc_id, h)
        return list(seen.values())

    d, t = best_per_doc(dense), best_per_doc(text)
    by_doc_d = {h.doc_id: h for h in d}
    by_doc_t = {h.doc_id: h for h in t}
    max_text = max((h.score for h in t), default=0.0) or 1.0
    fused = reciprocal_rank_fusion(
        [[h.doc_id for h in d], [h.doc_id for h in t]],
        k=fusion.k,
        weights=(fusion.dense_weight, 1.0),
    )
    out = []
    for f in fused[:top_k]:
        hd, ht = by_doc_d.get(f.key), by_doc_t.get(f.key)
        best = ht if ht is not None else hd
        if best is None:  # pragma: no cover - every fused key comes from one of the lists
            continue
        out.append(
            SearchHit(
                doc_id=f.key,
                kind=best.kind,
                title=best.title,
                subtitle="",
                snippet=_snippet(best.text, query),
                source_url=None,
                dense_rank=f.ranks[0],
                text_rank=f.ranks[1],
                dense_score=round(max(0.0, hd.score), 4) if hd else 0.0,
                text_score=round(ht.score / max_text, 4) if ht else 0.0,
                fused=round(f.score, 6),
            )
        )
    return out


OWNER_CACHE = 64
_OPERATION_MODEL = re.compile(r"^model:([a-z]+[0-9]+)-(?:response|request)-")


def _operation_owner(doc_id: str, owners: dict[str, str]) -> str | None:
    """The endpoint a per-operation model belongs to (`model:a02-response-200-...` -> A02)."""
    m = _OPERATION_MODEL.match(doc_id)
    return owners.get(m.group(1)) if m else None


_OWNERS: dict[str, dict[str, str]] = {}


def operation_owners(documents: DocumentRepo, build_id: BuildId) -> dict[str, str]:
    """{operation code: endpoint doc id} from request.json specOperationId (Mirakl "A02");
    sealed builds never change, so it is computed once per build (bounded cache)."""
    cached = _OWNERS.get(build_id.value)
    if cached is None:
        cached = {}
        for d in documents.list_documents(build_id):
            if d.kind is not DocumentKind.ENDPOINT:
                continue
            op = (d.raw or {}).get("specOperationId")
            if isinstance(op, str) and op.strip():
                cached.setdefault(op.strip().lower(), d.doc_id)
        if len(_OWNERS) > OWNER_CACHE:
            _OWNERS.clear()
        _OWNERS[build_id.value] = cached
    return cached


def rank_order(
    documents: DocumentRepo,
    build_id: BuildId,
    fused: Sequence[str],
    k: int,
    wider: Callable[[], Sequence[str]] = tuple,
) -> list[str]:
    """The final order of fused hits, shared by search and the eval gate: a page brings one of
    its endpoints into the top-k, so does a knowledge unit that names its endpoints (from the
    pool or `wider`: the endpoints ranked for the query); a per-operation model brings its
    endpoint just before it."""
    order = pair_pages_with_endpoints(fused, k, lambda d: page_endpoints(documents, build_id, d))
    order = pair_units_with_endpoints(
        order, k, lambda d: unit_endpoints(documents, build_id, d), wider
    )
    owners = operation_owners(documents, build_id)
    if owners:
        order = lift_operation_endpoints(order, k, lambda d: _operation_owner(d, owners))
    return order


def page_endpoints(documents: DocumentRepo, build_id: BuildId, doc_id: str) -> list[str]:
    """The endpoints a knowledge-export page documents (recorded on the page guide)."""
    if not is_page(doc_id):
        return []
    doc = documents.get_document(build_id, doc_id)
    raw = doc.raw if doc is not None and isinstance(doc.raw, dict) else {}
    endpoints = raw.get("endpoints")
    return [e for e in endpoints if isinstance(e, str)] if isinstance(endpoints, list) else []


WIDER_POOL = 50  # endpoints ranked for a query, for a knowledge unit's endpoint (rank_order)


def unit_endpoints(documents: DocumentRepo, build_id: BuildId, doc_id: str) -> list[str]:
    """The endpoints a knowledge unit names (Core's endpointId/endpointIds, as document ids)."""
    if not doc_id.startswith("guide:") or is_page(doc_id):
        return []
    doc = documents.get_document(build_id, doc_id)
    raw = doc.raw if doc is not None and isinstance(doc.raw, dict) else {}
    endpoints = raw.get("endpoints")
    return [e for e in endpoints if isinstance(e, str)] if isinstance(endpoints, list) else []


class SearchDocs:
    """Hybrid search: dense (embedding) + full text, fused with RRF, one hit per document."""

    def __init__(
        self,
        resolver: BuildResolver,
        index: SearchIndex,
        embedder: Embedder,
        documents: DocumentRepo,
        fusion: Fusion = DEFAULT_FUSION,
    ) -> None:
        self._resolver = resolver
        self._index = index
        self._embedder = embedder
        self._documents = documents
        self._fusion = fusion

    def execute(
        self,
        api: str,
        query: str,
        mode: SearchMode = "hybrid",
        kind: str | None = None,
        top_k: int = 8,
        version: str | None = None,
    ) -> SearchResult:
        query = query.strip()
        if not query:
            raise ReaderInputError("query is empty")
        if not 1 <= top_k <= MAX_TOP_K:
            raise ReaderInputError(f"top_k must be 1..{MAX_TOP_K}")
        if mode not in ("hybrid", "dense", "text"):
            raise ReaderInputError(f"unknown mode {mode!r}")
        started = time.perf_counter()
        trace: list[TraceStep] = []
        r = _timed(trace, "postgres", "resolve build", lambda: self._resolver.resolve(api, version))
        build_id = r.build.build_id
        kinds = _kinds(kind)
        spec = r.build.spec
        if mode != "text" and spec is not None and spec.embed_model != self._embedder.model:
            raise ApplicationError(
                f"build {build_id} was embedded with {spec.embed_model}; this server embeds "
                f"queries with {self._embedder.model}. Use mode=text or load the build again."
            )
        pool = max(top_k * 4, 20)
        dense: list[ChunkHit] = []
        text: list[ChunkHit] = []
        vector: Vector | None = None
        if mode in ("hybrid", "dense"):
            vector = _timed(
                trace, "embedder", "embed query", lambda: self._embedder.embed_query(query)
            )
            dense = _timed(
                trace,
                "postgres",
                "vector search",
                lambda: self._index.dense(build_id, vector, pool, kinds),
            )
        if mode in ("hybrid", "text"):
            text = _timed(
                trace,
                "postgres",
                "full-text search",
                lambda: self._index.text(build_id, query, pool, kinds),
            )
        fused = _timed(
            trace, "plume", "fuse (RRF)", lambda: fuse_hits(dense, text, query, pool, self._fusion)
        )
        wider_hits: list[ChunkHit] = []

        def wider() -> list[str]:
            if vector is None or (kinds and DocumentKind.ENDPOINT not in kinds):
                return []
            wider_hits.extend(
                self._index.dense(build_id, vector, WIDER_POOL, (DocumentKind.ENDPOINT,))
            )
            return list(dict.fromkeys(h.doc_id for h in wider_hits))

        order = rank_order(self._documents, build_id, [h.doc_id for h in fused], top_k, wider)
        by_id = {h.doc_id: h for h in fuse_hits(wider_hits, [], query, WIDER_POOL)}
        by_id.update({h.doc_id: h for h in fused})
        hits = [by_id[d] for d in order[:top_k]]
        summaries = self._index.summaries(build_id, [h.doc_id for h in hits])
        enriched = []
        for h in hits:
            doc = self._documents.get_document(build_id, h.doc_id)
            enriched.append(
                SearchHit(
                    doc_id=h.doc_id,
                    kind=h.kind,
                    title=h.title,
                    subtitle=_subtitle(summaries.get(h.doc_id), h.kind),
                    snippet=h.snippet,
                    source_url=doc.source_url if doc else None,
                    dense_rank=h.dense_rank,
                    text_rank=h.text_rank,
                    dense_score=h.dense_score,
                    text_score=h.text_score,
                    fused=h.fused,
                )
            )
        total = round((time.perf_counter() - started) * 1000, 2)
        return SearchResult(_ref(r), query, mode, tuple(enriched), tuple(trace), total)


class GetDocument:
    def __init__(self, resolver: BuildResolver, documents: DocumentRepo) -> None:
        self._resolver = resolver
        self._documents = documents

    def execute(self, api: str, doc_id: str, version: str | None = None) -> DocumentResult:
        r = self._resolver.resolve(api, version)
        doc = self._documents.get_document(r.build.build_id, doc_id)
        if doc is None:
            raise NotFoundError(f"{doc_id} is not in build {r.build.build_id}")
        return DocumentResult(_ref(r), doc, Citation(doc.doc_id, doc.source_url, doc.anchor, None))


def _match(fact: Fact, titles: dict[str, str]) -> FactMatch:
    return FactMatch(
        kind=fact.kind,
        name=fact.name,
        owner_id=fact.owner_id,
        owner_title=titles.get(fact.owner_id),
        resource=fact.resource,
        location=fact.location,
        type=fact.type,
        required=fact.required,
        complete=fact.complete,
        citation=fact.evidence,
        constraints=constraint_dict(fact.constraints) or None,
    )


def _general_guide(h: ChunkHit) -> bool:
    """The API's own guides (connector knowledge), not one page of an exported site."""
    return h.kind is DocumentKind.GUIDE and not h.doc_id.startswith("guide:page-")


class FindFact:
    """Presence/absence of an endpoint, field or scope, with evidence and a completeness flag."""

    MENTIONS = 5

    def __init__(
        self,
        resolver: BuildResolver,
        facts: FactQuery,
        index: SearchIndex,
    ) -> None:
        self._resolver = resolver
        self._facts = facts
        self._index = index

    def _mentions(self, build_id: BuildId, name: str) -> list[ChunkHit]:
        """Prose mentions, the API's own guides first: those general notes (pagination, rate
        limits) are easily outranked by many pages that use the word."""
        query = name.replace(".", " ").replace("_", " ")
        guides = sorted(  # per guide, the chunk using the name most like a parameter
            (h for h in self._index.text(build_id, query, 20, (DocumentKind.GUIDE,))
             if _general_guide(h)),
            key=lambda h: -_term_use(h.text, name)[0],
        )  # fmt: skip
        out: list[ChunkHit] = []
        for h in guides[:2] + self._index.text(build_id, query, self.MENTIONS, ()):
            if h.doc_id not in {x.doc_id for x in out}:
                out.append(h)
        return out[: self.MENTIONS + 1]

    def _owner_id(self, build_id: BuildId, owner: str | None) -> str | None:
        """A document id as is; "GET /api/products" (how endpoints are shown everywhere) maps to
        the endpoint's document, matching path templates the same way check_call does."""
        if owner is None or not owner.strip():
            return None
        owner = owner.strip()
        if self._index.summaries(build_id, [owner]):
            return owner
        method, _, path = owner.partition(" ")
        if method.upper() in HTTP_METHODS and path.strip().startswith("/"):
            path = path.strip().split("?", 1)[0]
            exact = [
                f
                for f in self._facts.endpoints(build_id)
                if f.name.partition(" ")[0] == method.upper()
                and f.name.partition(" ")[2] in (path, path.rstrip("/"))
            ]
            matches = exact or [
                f
                for f in self._facts.endpoints(build_id)
                if f.name.partition(" ")[0] == method.upper()
                and path_matches(f.name.partition(" ")[2], path)
            ]
            owners = sorted({f.owner_id for f in matches})
            if len(owners) == 1:
                return owners[0]
            if len(owners) > 1:
                raise ReaderInputError(
                    f"{method.upper()} {path} matches {len(owners)} operations; pass one of "
                    f"these document ids as owner: {', '.join(owners)}"
                )
        return owner  # unknown: reported as not in the build below

    def execute(
        self,
        api: str,
        name: str,
        *,
        kind: str | None = None,
        owner: str | None = None,
        resource: str | None = None,
        location: str | None = None,
        version: str | None = None,
    ) -> FindFactResult:
        name = name.strip()
        if not name:
            raise ReaderInputError("name is empty")
        try:
            fact_kind = FactKind(kind) if kind else None
            loc = FieldLocation(location) if location else None
        except ValueError as exc:
            raise ReaderInputError(str(exc)) from exc
        r = self._resolver.resolve(api, version)
        build_id = r.build.build_id
        owner = self._owner_id(build_id, owner)
        found = self._facts.find(
            build_id, name, kind=fact_kind, owner_id=owner, resource=resource, location=loc
        )
        titles = {
            k: s.title
            for k, s in self._index.summaries(build_id, [f.owner_id for f in found]).items()
        }
        counts = self._index.counts(build_id)
        checked = {
            "endpoints": counts.get("endpoint", 0),
            "models": counts.get("model", 0),
        }
        if owner is not None and not self._index.summaries(build_id, [owner]):
            raise NotFoundError(f"{owner} is not in build {build_id}")
        # The completeness of the sources in scope decides whether absence is proven.
        incomplete = tuple(
            self._facts.incomplete_owners(build_id, owner_id=owner, resource=resource)
        )
        complete = not incomplete
        reasons: list[str] = [f"{o} is flagged incomplete by its source" for o in incomplete]
        field_like = fact_kind in (None, FactKind.FIELD) and loc not in (
            FieldLocation.PATH,
            FieldLocation.QUERY,
            FieldLocation.HEADER,
        )
        if not found and field_like and counts.get("model", 0) == 0:
            # Without model schemas, response/model fields are only known where an endpoint
            # documents its response; absence of a data field is not proven.
            complete = False
            reasons.append(f"no model schemas are indexed for {api}")
        mentions: tuple[SearchHit, ...] = ()
        if not found:
            hits = self._mentions(build_id, name)
            general = [h for h in hits if _general_guide(h) and _term_use(h.text, name)[0] >= 0]
            if general and fact_kind in (None, FactKind.FIELD) and loc is not FieldLocation.PATH:
                # A name the API's own guide describes once for many endpoints (Mirakl paging
                # parameters, Shopify currency rules): absence on one endpoint is not proven.
                g = general[0]
                complete = False
                reasons.append(
                    f"{g.doc_id} describes {name!r} in general guidance that may apply to many "
                    f'endpoints: "{_snippet(g.text, name, name)}"; endpoint schemas do not '
                    "list it"
                )
            mentions = tuple(
                SearchHit(
                    doc_id=h.doc_id,
                    kind=h.kind,
                    title=h.title,
                    subtitle="",
                    snippet=_snippet(h.text, name, name),
                    source_url=None,
                    dense_rank=None,
                    text_rank=i + 1,
                    dense_score=0.0,
                    text_score=0.0,
                    fused=0.0,
                )
                for i, h in enumerate(hits)
            )
        build = r.build.build_id.value
        if found:
            wording = f"Documented in build {build} ({len(found)} match(es)); cite the evidence."
        elif complete:
            wording = (
                f"Not documented in build {build}: checked {checked['endpoints']} endpoints and "
                f"{checked['models']} models with complete schemas. Say 'not documented', never "
                "'does not exist'."
            )
        else:
            wording = (
                f"Not found in build {build}, but absence is NOT proven ({'; '.join(reasons)}). "
                "Say it is not documented here and may exist."
            )
        if not found and mentions:
            wording += " The name appears in prose; read text_mentions before concluding."
        return FindFactResult(
            ref=_ref(r),
            name=name,
            found=bool(found),
            matches=tuple(_match(f, titles) for f in found),
            complete=complete,
            checked=checked,
            text_mentions=mentions,
            wording=wording,
            incomplete_sources=incomplete,
            reasons=tuple(reasons),
        )


class CheckCall:
    """Is ``METHOD /path`` with these params documented? Matches templates like ``{id}``."""

    def __init__(self, resolver: BuildResolver, facts: FactQuery, index: SearchIndex) -> None:
        self._resolver = resolver
        self._facts = facts
        self._index = index

    def execute(
        self,
        api: str,
        method: str,
        path: str,
        params: Sequence[str] = (),
        version: str | None = None,
    ) -> CheckCallResult:
        method = method.upper().strip()
        if method not in HTTP_METHODS:
            raise ReaderInputError(f"unknown HTTP method {method!r}")
        if not path.strip():
            raise ReaderInputError("path is empty")
        r = self._resolver.resolve(api, version)
        build_id = r.build.build_id
        wanted = normalize_call_path(path, r.api.versions)
        endpoints = self._facts.endpoints(build_id)
        candidates = []
        for f in endpoints:
            f_method, _, f_path = f.name.partition(" ")
            if f_method == method and path_matches(f_path, wanted):
                candidates.append((specificity(f_path), f, f_path))
        counts = self._index.counts(build_id)
        checked = {"endpoints": counts.get("endpoint", 0), "models": counts.get("model", 0)}
        if not candidates:
            return CheckCallResult(
                _ref(r),
                method,
                path,
                "not_documented",
                True,
                None,
                None,
                None,
                tuple(ParamCheck(p, False, None) for p in params),
                checked,
                None,
            )
        candidates.sort(key=lambda c: (-c[0], c[2], c[1].owner_id))
        best = candidates[0]
        # Several operations at the same METHOD + path: the one that documents the most of
        # these params; the others are named as alternatives.
        tied = [c for c in candidates if c[2] == best[2]]
        scored = []
        for _, f, f_path in tied:
            checks = self._param_checks(build_id, f.owner_id, params)
            scored.append((-sum(c.found for c in checks), f.owner_id, f, f_path, checks))
        scored.sort(key=lambda x: (x[0], x[1]))
        _, _, endpoint, matched_path, checks = scored[0]
        alternatives = tuple(x[1] for x in scored[1:])
        complete = endpoint.complete
        verdict = "documented" if all(c.found for c in checks) else "not_documented"
        return CheckCallResult(
            _ref(r),
            method,
            path,
            verdict,
            complete,
            endpoint.owner_id,
            method,
            matched_path,
            tuple(checks),
            checked,
            endpoint.evidence,
            alternatives,
            self._real_path(r.build.build_id, endpoint.owner_id),
        )

    def _real_path(self, build_id: BuildId, doc_id: str) -> str | None:
        summary = self._index.summaries(build_id, [doc_id]).get(doc_id)
        return summary.real_path if summary else None

    def _param_checks(
        self, build_id: BuildId, owner_id: str, params: Sequence[str]
    ) -> list[ParamCheck]:
        owned = self._facts.for_owner(build_id, owner_id)
        checks = []
        for p in params:
            hits = [
                f
                for f in owned
                if f.kind is FactKind.FIELD
                and (f.name.lower() == p.lower() or f.name.lower().endswith("." + p.lower()))
                and f.location is not FieldLocation.RESPONSE
            ]
            where = hits[0].location.value if hits and hits[0].location else None
            checks.append(ParamCheck(p, bool(hits), where))
        return checks
