"""Reader use cases. Retrieval only: Claude writes the answers, Plume returns cited material."""

import time
from collections.abc import Callable, Sequence
from typing import Literal

from plume.application.errors import ApplicationError, NotFoundError
from plume.application.ports.api_repo import ApiRepo
from plume.application.ports.asset_repo import AssetRepo
from plume.application.ports.build_repo import BuildRepo
from plume.application.ports.document_repo import DocumentRepo
from plume.application.ports.embedder import Embedder
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
from plume.application.reader.ranking import is_page, pair_pages_with_endpoints
from plume.application.reader.resolve import BuildResolver, ResolvedBuild
from plume.domain.knowledge.asset import ICON
from plume.domain.knowledge.call_check import normalize_call_path, path_matches, specificity
from plume.domain.knowledge.citation import Citation
from plume.domain.knowledge.document import HTTP_METHODS, DocumentKind, FieldLocation
from plume.domain.knowledge.fact import Fact, FactKind
from plume.domain.knowledge.ranking import reciprocal_rank_fusion
from plume.domain.shared.ids import BuildId

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


def _snippet(text: str, query: str) -> str:
    flat = " ".join(text.split())
    words = [w for w in query.lower().split() if len(w) > 2]
    lower = flat.lower()
    pos = min((lower.find(w) for w in words if lower.find(w) >= 0), default=0)
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
    dense: Sequence[ChunkHit], text: Sequence[ChunkHit], query: str, top_k: int
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
    fused = reciprocal_rank_fusion([[h.doc_id for h in d], [h.doc_id for h in t]])
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


def page_endpoints(documents: DocumentRepo, build_id: BuildId, doc_id: str) -> list[str]:
    """The endpoints a knowledge-export page documents (recorded on the page guide)."""
    if not is_page(doc_id):
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
    ) -> None:
        self._resolver = resolver
        self._index = index
        self._embedder = embedder
        self._documents = documents

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
        fused = _timed(trace, "plume", "fuse (RRF)", lambda: fuse_hits(dense, text, query, pool))
        order = pair_pages_with_endpoints(
            [h.doc_id for h in fused], top_k, lambda d: page_endpoints(self._documents, build_id, d)
        )
        by_id = {h.doc_id: h for h in fused}
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
    )


class FindFact:
    """Presence/absence of an endpoint, field or scope, with evidence and a completeness flag."""

    def __init__(
        self,
        resolver: BuildResolver,
        facts: FactQuery,
        index: SearchIndex,
    ) -> None:
        self._resolver = resolver
        self._facts = facts
        self._index = index

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
            if len({f.owner_id for f in matches}) == 1:
                return matches[0].owner_id
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
            hits = self._index.text(build_id, name.replace(".", " ").replace("_", " "), 5, ())
            mentions = tuple(
                SearchHit(
                    doc_id=h.doc_id,
                    kind=h.kind,
                    title=h.title,
                    subtitle="",
                    snippet=_snippet(h.text, name),
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
        candidates.sort(key=lambda c: (-c[0], c[2]))
        _, endpoint, matched_path = candidates[0]
        owned = self._facts.for_owner(build_id, endpoint.owner_id)
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
        )
