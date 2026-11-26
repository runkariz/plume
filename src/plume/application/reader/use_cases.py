"""Reader use cases. Retrieval only: Claude writes the answers, Plume returns cited material."""

import base64
import contextlib
import dataclasses
import json
import re
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any, Literal
from urllib.parse import parse_qsl, urlsplit

from plume.application.errors import ApplicationError, NotFoundError
from plume.application.ports.api_list import ApiListQuery, ApiListRow
from plume.application.ports.api_repo import ApiRepo
from plume.application.ports.asset_repo import AssetRepo
from plume.application.ports.build_repo import BuildRepo
from plume.application.ports.document_repo import DocumentRepo
from plume.application.ports.embedder import Embedder, Vector
from plume.application.ports.eval_repo import EvalRepo
from plume.application.ports.search_index import (
    ChunkHit,
    DocumentSummary,
    FactKey,
    FactQuery,
    QueryTooBroadError,
    SearchIndex,
    fact_key,
)
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
from plume.application.reader.links import linked_endpoints
from plume.application.reader.ranking import (
    auth_first,
    code_holder_first,
    context_after_named_endpoint,
    endpoint_after_window,
    endpoint_before_its_model,
    endpoints_before_returned_models,
    endpoints_before_units_on_how_to,
    error_codes_after_endpoint,
    is_page,
    keep_endpoints,
    lift_operation_endpoints,
    limit_guide_after_endpoint,
    near_duplicate_guides_last,
    pair_pages_with_endpoints,
    pair_units_with_endpoints,
    path_only_after_endpoints,
    production_before_test,
    push_first,
    rate_limit_guide_first,
    request_models_last,
    scoped_last,
    singular,
    stale_version_guides_last,
    state_change_first,
    synthesized_after_vendor,
    topic_docs_give_way,
    triggers_after_endpoints,
)
from plume.application.reader.resolve import BuildResolver, ResolvedBuild
from plume.domain.eval.metrics import K
from plume.domain.knowledge.api import ApiInfo
from plume.domain.knowledge.asset import ICON
from plume.domain.knowledge.call_check import (
    Environment,
    ServerBase,
    endpoint_server,
    environments_of,
    host_problem,
    normalize_call_path,
    path_matches,
    route_shape,
    server_bases,
    specificity,
    without_server_base,
)
from plume.domain.knowledge.citation import Citation
from plume.domain.knowledge.document import (
    ENVIRONMENTS_DOC_ID,
    HEADER_SOURCE_STANDARD,
    HTTP_METHODS,
    STANDARD_HEADER_NOTE,
    SUMMARY_HEADING,
    SUMMARY_LABEL,
    Document,
    DocumentKind,
    FieldLocation,
    conflict_concerns,
    conflicts_of,
    constraint_dict,
)
from plume.domain.knowledge.fact import Fact, FactKind
from plume.domain.knowledge.ranking import Fusion, expand_text_query, reciprocal_rank_fusion
from plume.domain.knowledge.tag import LATEST
from plume.domain.shared.ids import BuildId

DEFAULT_FUSION = Fusion()
SearchMode = Literal["hybrid", "dense", "text"]
MAX_TOP_K = 50
# The candidate pool the final order is computed on (search and the eval gate alike).
RANK_POOL = 20
RANK_K = K  # the window the ranking rules work in (the eval's recall@K)
SEARCH_POOL = MAX_TOP_K * 4  # hits per list behind the order's tail (fixed, any top_k)
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
    out = ("…" if start else "") + piece + ("…" if start + SNIPPET_CHARS < len(flat) else "")
    summary = flat.find(SUMMARY_HEADING)
    if summary >= 0 and start + len(piece) > summary and SUMMARY_HEADING not in piece:
        out = f"[{SUMMARY_LABEL}] {out}"  # the label stays with model-written text
    return out


class ListApiOverviews:
    def __init__(
        self,
        apis: ApiRepo,
        builds: BuildRepo,
        tags: TagRepo,
        index: SearchIndex,
        evals: EvalRepo | None = None,
        assets: AssetRepo | None = None,
        bulk: ApiListQuery | None = None,
    ) -> None:
        self._bulk = bulk  # the list in a few queries (else one API at a time)
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
            has_icon=bool(self._assets and self._assets.has(r.build.build_id, ICON)),
        )

    def execute(self) -> list[ApiOverview]:
        infos = self._apis.list()
        if self._bulk is not None:
            rows = self._bulk.rows([i.api_id for i in infos])
            return [self._from_row(info, rows[info.api_id]) for info in infos]
        out = []
        for info in infos:
            try:
                out.append(self._overview(info.api_id.value, None))
            except NotFoundError:
                out.append(ApiOverview(info, None, {}, (), None, None))  # no published build
        return out

    @staticmethod
    def _from_row(info: ApiInfo, row: ApiListRow) -> ApiOverview:
        """The same overview as ``_overview(api, None)``: no latest tag, no published build."""
        if row.latest is None:
            return ApiOverview(info, None, {}, (), None, None)
        latest = row.latest
        spec = latest.spec
        return ApiOverview(
            info=info,
            ref=BuildRef(info.api_id.value, latest.build_id, LATEST, latest.docs_as_of),
            counts=dict(row.counts),
            tags=row.tags,
            embed_model=spec.embed_model if spec else None,
            dims=spec.dims if spec else None,
            eval=row.eval,
            has_icon=row.has_icon,
        )

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
    query: str = "",
    auth_docs: Callable[[], Sequence[str]] = tuple,
    all_endpoints: Callable[[], Sequence[str]] = tuple,
    error_codes: Callable[[], str | None] = lambda: None,
    code_holders: Callable[[str], Sequence[str]] = lambda c: (),
    limit_guide: Callable[[], str | None] = lambda: None,
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
    order = request_models_last(order, k)
    order = near_duplicate_guides_last(order, k)
    order = auth_first(order, k, query, auth_docs)
    order = state_change_first(order, k, query, all_endpoints)
    order = synthesized_after_vendor(order, k)
    order = stale_version_guides_last(
        order,
        k,
        lambda d: unit_endpoints(documents, build_id, d),
        lambda e: endpoint_version(documents, build_id, e),
        lambda d: documents.get_document(build_id, d) is not None,
    )
    order = production_before_test(order, query)
    order = path_only_after_endpoints(order, k)
    order = rate_limit_guide_first(order, k, query)
    order = endpoint_before_its_model(order, k)
    order = endpoints_before_returned_models(
        order, k, query, lambda m, pool: returning_endpoints(documents, build_id, m, pool)
    )
    order = push_first(order, k, query, all_endpoints)
    order = context_after_named_endpoint(order, k, query)
    order = error_codes_after_endpoint(order, k, query, error_codes)
    order = triggers_after_endpoints(
        order, k, query, lambda d: trigger_resource(documents, build_id, d)
    )
    order = limit_guide_after_endpoint(order, k, query, limit_guide)
    order = code_holder_first(
        order, k, query, lambda d, c: holds_code(documents, build_id, d, c), code_holders
    )
    order = topic_docs_give_way(order, k, query, lambda d: quote_words(documents, build_id, d))
    order = scoped_last(
        order,
        k,
        query,
        lambda d: scoped_parts(documents, build_id, d),
        lambda d, topic: covers_topic(documents, build_id, d, topic),
    )
    # after keep_endpoints: it brings endpoints from below the top k into it
    order = endpoints_before_units_on_how_to(keep_endpoints(order, k), k, query)
    return endpoint_after_window(order, k, wider)


def all_endpoint_ids(index: SearchIndex, build_id: BuildId) -> list[str]:
    """Every endpoint document id of the build (for a lookup by path structure)."""
    return [s.doc_id for s in index.browse(build_id, (DocumentKind.ENDPOINT,), None, 100_000, 0)[0]]


_HTTP_CODE = re.compile(r"\b(4(?:00|01|03|04|05|06|09|10|15|22|29)|5(?:00|02|03|04))\b")
_CODES_QUERIES = ("status codes", "error codes", "response codes", "return codes")
MIN_CODES = 5  # distinct HTTP status codes a chunk lists to be the API's error-codes section


def _code_token(code: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w.]){re.escape(code)}(?![\w.])")


# Words a scoped guide's quotes share with any limit question: they name no part of the API.
_GENERIC_WORDS = (
    "about after also allow allowed and any are api apis been before but call calls can cannot "
    "data each earlier file files for from has have hour hours import imports into item items "
    "its larger limit limited limits line lines max maximum may minute minutes more most must "
    "not number one only page pages per rate request requests response second seconds size "
    "than that the their there these this time times total upload uploads up use used using "
    "value values was when which will with within you your batch batches bulk record records "
    "state states webhook webhooks "
    # a token's lifetime: the topic's own wording, not a part of the API
    "token tokens lifetime expire expires expired expiry expiration valid validity access "
    "refresh oauth bearer grant credential credentials user application new create obtain "
    "current long how "
    # the other topics' own wording (error format, state transitions, sandbox, webhooks)
    "error errors response responses format formats code codes status statuses message "
    "messages body http json field fields order orders transition transitions exist exists "
    "allowed which what happens happen get got return returned sandbox test testing environment "
    "environments url urls base event events notification notifications subscribe subscription "
    "callback callbacks"
)
_GENERIC_PART = frozenset(_GENERIC_WORDS.split())


# A documented paging parameter in an endpoint's parameter list ("- `max` (integer): ...").
_PAGING_PARAM = re.compile(
    r"^- `(max|limit|page_?size|per_?page|pagesize|perpage|size|page\[size\]|max_?results"
    r"|maxresults|count)` \(",
    re.IGNORECASE | re.MULTILINE,
)


def covers_topic(documents: DocumentRepo, build_id: BuildId, doc_id: str, topic: str) -> bool:
    """Whether a result answers a scoped topic by its content: for request limits, an endpoint
    that documents a paging parameter (its own maximum page size)."""
    if topic != "request-limits" or not doc_id.startswith("endpoint:"):
        return False
    doc = documents.get_document(build_id, doc_id)
    return doc is not None and bool(_PAGING_PARAM.search(doc.text))


def quote_words(documents: DocumentRepo, build_id: BuildId, doc_id: str) -> frozenset[str]:
    """The words of a topic / scoped document's quote lines ("> ...", not Scope / Source), in
    singular and as written."""
    doc = documents.get_document(build_id, doc_id)
    if doc is None:
        return frozenset()
    quotes = [ln[1:] for ln in doc.text.splitlines() if ln.startswith(">")
              and not re.match(r">\s*(Scope|Source):", ln)]  # fmt: skip
    words = re.findall(r"[a-z][a-z0-9]+", " ".join(quotes).lower())
    return frozenset(words) | frozenset(singular(w) for w in words)


def scoped_parts(documents: DocumentRepo, build_id: BuildId, doc_id: str) -> frozenset[str]:
    """The parts of the API a scoped guide's quotes are about: the distinctive words of its
    quote lines ("> ...", not Scope / Source) and of its endpoints' paths."""
    doc = documents.get_document(build_id, doc_id)
    if doc is None:
        return frozenset()
    quotes = [ln[1:] for ln in doc.text.splitlines() if ln.startswith(">")
              and not re.match(r">\s*(Scope|Source):", ln)]  # fmt: skip
    raw = doc.raw if isinstance(doc.raw, dict) else {}
    paths = [e.split("~", 1)[-1] for e in raw.get("endpoints") or [] if isinstance(e, str)]
    words = re.findall(r"[a-z][a-z0-9]{2,}", " ".join(quotes + paths).lower())
    return frozenset(
        singular(w) for w in words if w not in _GENERIC_PART and singular(w) not in _GENERIC_PART
    )


def code_holders(index: SearchIndex, build_id: BuildId, code: str) -> list[str]:
    """The documents whose text contains this exact code (a text search, then the token)."""
    token = _code_token(code)
    hits = index.text(build_id, code, 20)
    return list(dict.fromkeys(h.doc_id for h in hits if token.search(h.text)))


def holds_code(documents: DocumentRepo, build_id: BuildId, doc_id: str, code: str) -> bool:
    """Whether the document's full text contains this exact code."""
    doc = documents.get_document(build_id, doc_id)
    return doc is not None and bool(_code_token(code).search(doc.text))


_LIMIT_LINE = re.compile(
    r"\b(maximum|max|limit|up to|at most|no more than|exceed\w*)\b[^\n]{0,80}?\b\d+\b"
    r"|\b\d+\b[^\n]{0,30}\b(maximum|max)\b",
    re.IGNORECASE,
)
_LIMIT_STOP = frozenset(
    [
        "about",
        "allow",
        "allowed",
        "call",
        "calls",
        "could",
        "does",
        "each",
        "every",
        "fetch",
        "fetched",
        "filter",
        "filters",
        "from",
        "have",
        "into",
        "item",
        "items",
        "limit",
        "limits",
        "list",
        "make",
        "many",
        "maximum",
        "more",
        "most",
        "much",
        "number",
        "per",
        "query",
        "querying",
        "request",
        "requests",
        "result",
        "results",
        "return",
        "returns",
        "search",
        "send",
        "should",
        "specify",
        "than",
        "that",
        "their",
        "there",
        "this",
        "time",
        "times",
        "total",
        "under",
        "using",
        "value",
        "values",
        "what",
        "when",
        "where",
        "which",
        "will",
        "with",
        "would",
    ]
)


def limit_line_guide(index: SearchIndex, build_id: BuildId, query: str) -> str | None:
    """The guide with a line stating a field's limit (maximum / limit / up to ... N), the field
    named by question words ("charity ids" -> charity_ids): the line naming the most question
    words wins, the first found on a tie."""
    words = [w for w in dict.fromkeys(re.findall(r"[a-z][a-z0-9]{3,}", query.lower()))
             if w not in _LIMIT_STOP]  # fmt: skip
    asked = set(re.findall(r"[a-z0-9]+", query.lower()))
    best: tuple[int, str] | None = None
    for word in words:
        for h in index.text(build_id, word, 20, (DocumentKind.GUIDE,)):
            for line in h.text.splitlines():
                clean = line.replace("\\", "").lower()
                norm = clean.replace("_", " ")
                names = set(re.findall(r"[a-z0-9]+", norm))
                if word not in names or not _LIMIT_LINE.search(norm):
                    continue
                # the limit is a field's: an identifier made of question words (charity_ids)
                fields = re.findall(r"[a-z0-9]+(?:_[a-z0-9]+)+", clean)
                if not any(set(f.split("_")) <= asked for f in fields):
                    continue
                score = sum(w in names for w in words)
                if best is None or score > best[0]:
                    best = (score, h.doc_id)
    return best[1] if best else None


def error_codes_guide(index: SearchIndex, build_id: BuildId) -> str | None:
    """The guide whose chunk lists the most HTTP status codes (at least MIN_CODES), among the
    guide chunks a text search for status / error codes finds."""
    best: tuple[int, str] | None = None
    for q in _CODES_QUERIES:
        for h in index.text(build_id, q, 20, (DocumentKind.GUIDE,)):
            n = len(set(_HTTP_CODE.findall(h.text)))
            if n >= MIN_CODES and (best is None or n > best[0]):
                best = (n, h.doc_id)
    return best[1] if best else None


def own_auth_docs(
    index: SearchIndex, build_id: BuildId, kinds: Sequence[DocumentKind]
) -> list[str]:
    """The API's auth schemes, then its app (setup) document, for an auth question none of
    whose ranked documents is about auth."""
    out: list[str] = []
    for kind in (k for k in (DocumentKind.AUTH, DocumentKind.APP) if k in kinds):
        out += [s.doc_id for s in index.browse(build_id, (kind,), None, 20, 0)[0]]
    return out


def page_endpoints(documents: DocumentRepo, build_id: BuildId, doc_id: str) -> list[str]:
    """The endpoints a knowledge-export page documents (recorded on the page guide)."""
    if not is_page(doc_id):
        return []
    doc = documents.get_document(build_id, doc_id)
    raw = doc.raw if doc is not None and isinstance(doc.raw, dict) else {}
    endpoints = raw.get("endpoints")
    return [e for e in endpoints if isinstance(e, str)] if isinstance(endpoints, list) else []


WIDER_POOL = 50  # endpoints ranked for a query, for a knowledge unit's endpoint (rank_order)


_URL_VERSION = re.compile(r"/(v\d+(?:\.\d+)?|\d{4}-\d\d-\d\d)(?=/|$)")


def endpoint_version(documents: DocumentRepo, build_id: BuildId, doc_id: str) -> str | None:
    """The API version an endpoint carries: its apiVersion, else a version segment of its url."""
    if not doc_id.startswith("endpoint:"):
        return None
    doc = documents.get_document(build_id, doc_id)
    raw = doc.raw if doc is not None and isinstance(doc.raw, dict) else {}
    if isinstance(raw.get("apiVersion"), str) and raw["apiVersion"].strip():
        return str(raw["apiVersion"])
    m = _URL_VERSION.search(raw["url"]) if isinstance(raw.get("url"), str) else None
    return m.group(1) if m else None


def trigger_resource(documents: DocumentRepo, build_id: BuildId, doc_id: str) -> str | None:
    """The resource a trigger (webhook event) is about (Trendyol UNSUPPLIED: order)."""
    if not doc_id.startswith("trigger:"):
        return None
    doc = documents.get_document(build_id, doc_id)
    raw = doc.raw if doc is not None and isinstance(doc.raw, dict) else {}
    return str(raw["resource"]) if isinstance(raw.get("resource"), str) else None


def returning_endpoints(
    documents: DocumentRepo, build_id: BuildId, model_id: str, candidates: Sequence[str]
) -> list[str]:
    """The candidate endpoints that return a model: named by the package (x-plume-returned-by),
    or the vendor requests the model was built from (x-vendor-requests, a Postman folder's
    "Categories: Browse") equal to an endpoint's summary or name."""
    doc = documents.get_document(build_id, model_id)
    raw = doc.raw if doc is not None and isinstance(doc.raw, dict) else {}
    named = raw.get("x-plume-returned-by")
    out = (
        [e for e in named if isinstance(e, str) and e in candidates]
        if isinstance(named, list)
        else []
    )
    requests = raw.get("x-vendor-requests")
    wanted = (
        {r.strip().lower() for r in requests if isinstance(r, str)}
        if isinstance(requests, list)
        else set()
    )
    if not wanted:
        return out
    for e in candidates:
        if e in out:
            continue
        edoc = documents.get_document(build_id, e)
        eraw = edoc.raw if edoc is not None and isinstance(edoc.raw, dict) else {}
        names = {str(eraw.get(n, "")).strip().lower() for n in ("summary", "name")}
        if names & wanted:
            out.append(e)
    return out


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
        pool = SEARCH_POOL  # fixed: the order must not depend on top_k
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
                lambda: self._index.text(
                    build_id,
                    expand_text_query(query, lambda w: bool(self._index.text(build_id, w, 1))),
                    pool,
                    kinds,
                ),
            )
        # The order is computed as the eval gate computes it (the first RANK_POOL hits of each
        # list, the rules over the top RANK_K), whatever top_k asks for; a longer list only
        # appends the rest of the larger pool. (CDON "how do I authenticate": the auth scheme
        # was 1st at top_k 10 and 20, missing at 3, 5 and 8.)
        fused = _timed(
            trace,
            "plume",
            "fuse (RRF)",
            lambda: fuse_hits(dense[:RANK_POOL], text[:RANK_POOL], query, RANK_POOL, self._fusion),
        )
        rest = fuse_hits(dense, text, query, pool, self._fusion)
        wider_hits: list[ChunkHit] = []

        def wider() -> list[str]:
            if vector is None or (kinds and DocumentKind.ENDPOINT not in kinds):
                return []
            wider_hits.extend(
                self._index.dense(build_id, vector, WIDER_POOL, (DocumentKind.ENDPOINT,))
            )
            return list(dict.fromkeys(h.doc_id for h in wider_hits))

        def auth_docs() -> list[str]:
            allowed = [k for k in (DocumentKind.AUTH, DocumentKind.APP) if not kinds or k in kinds]
            return own_auth_docs(self._index, build_id, allowed)

        def endpoint_ids() -> list[str]:
            if kinds and DocumentKind.ENDPOINT not in kinds:
                return []
            return all_endpoint_ids(self._index, build_id)

        order = rank_order(
            self._documents,
            build_id,
            [h.doc_id for h in fused],
            RANK_K,
            wider,
            query,
            auth_docs,
            endpoint_ids,
            lambda: (
                None
                if kinds and DocumentKind.GUIDE not in kinds
                else error_codes_guide(self._index, build_id)
            ),
            lambda c: code_holders(self._index, build_id, c),
            lambda: (
                None
                if kinds and DocumentKind.GUIDE not in kinds
                else limit_line_guide(self._index, build_id, query)
            ),
        )
        order += [h.doc_id for h in rest if h.doc_id not in order]
        by_id = {h.doc_id: h for h in fuse_hits(wider_hits, [], query, WIDER_POOL)}
        by_id.update({h.doc_id: h for h in rest})
        by_id.update({h.doc_id: h for h in fused})
        for d, summary in self._index.summaries(
            build_id, [d for d in order[:top_k] if d not in by_id]
        ).items():  # brought in by path or as the API's own auth document: no ranks
            full = self._documents.get_document(build_id, d)
            by_id[d] = SearchHit(d, summary.kind, summary.title, "",
                                 _snippet(full.text if full else "", query), None, None, None,
                                 0.0, 0.0, 0.0)  # fmt: skip
        order = [d for d in order if d in by_id]
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


MAX_USED_BY = 50  # a shared model (Money) is used by hundreds of endpoints
RETURNED_BY_KEY = "x-plume-returned-by"


class GetDocument:
    def __init__(self, resolver: BuildResolver, documents: DocumentRepo) -> None:
        self._resolver = resolver
        self._documents = documents

    def execute(self, api: str, doc_id: str, version: str | None = None) -> DocumentResult:
        r = self._resolver.resolve(api, version)
        doc = self._documents.get_document(r.build.build_id, doc_id)
        if doc is None:
            raise NotFoundError(f"{doc_id} is not in build {r.build.build_id}")
        used = self._used_by(r.build.build_id, doc) if doc.kind is DocumentKind.MODEL else []
        return DocumentResult(
            _ref(r),
            doc,
            Citation(doc.doc_id, doc.source_url, doc.anchor, None),
            tuple(used[:MAX_USED_BY]),
            len(used),
        )

    def _used_by(self, build_id: BuildId, doc: Document) -> list[tuple[str, tuple[str, ...], str]]:
        """The endpoints whose fields have the model's type, then those the package says
        return it by a bundled response title (x-plume-returned-by), each once."""
        out = [(d, where, "ref") for d, where in self._documents.model_users(build_id, doc.doc_id)]
        seen = {d for d, _, _ in out}
        returned = doc.raw.get(RETURNED_BY_KEY) if isinstance(doc.raw, dict) else None
        for d in returned if isinstance(returned, list) else []:
            if isinstance(d, str) and d not in seen:
                out.append((d, ("response",), "returned-by"))
                seen.add(d)
        return out


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
        note=STANDARD_HEADER_NOTE if fact.evidence.anchor == HEADER_SOURCE_STANDARD else None,
    )


def _general_guide(h: ChunkHit) -> bool:
    """The API's own guides (connector knowledge), not one page of an exported site."""
    return h.kind is DocumentKind.GUIDE and not h.doc_id.startswith("guide:page-")


BOUNDED_SHOWN = 3


def _bounded_reason(bounded: dict[str, int]) -> str:
    """ "not listed: <doc> schema truncated at nesting level N" (a few named, then a count)."""
    shown = "; ".join(
        f"{doc} schema truncated at nesting level {level}"
        for doc, level in list(bounded.items())[:BOUNDED_SHOWN]
    )
    more = len(bounded) - BOUNDED_SHOWN
    return f"not listed: {shown}" + (f"; +{more} more truncated schema(s)" if more > 0 else "")


def _fact_wording(
    build: str,
    found: int,
    complete: bool,
    checked: dict[str, int],
    reasons: list[str],
    mentioned: bool,
) -> str:
    if found:
        return f"Documented in build {build} ({found} match(es)); cite the evidence."
    if complete:
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
    if mentioned:
        wording += " The name appears in prose; read text_mentions before concluding."
    return wording


_ENDPOINT_FORM = re.compile(
    r"^(?:(?P<method>GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+)?(?P<path>(?:[a-z]+://\S+?)?/\S*)$",
    re.I,
)


FIND_FACT_LIMIT = 50  # matches per call (Shopware "id": 25k facts in 844 documents)
FIND_FACT_MAX_BYTES = 200_000  # a backstop on one page's matches


def _cursor(key: FactKey, total: int) -> str:
    """The last match's key and the lookup's total (so later pages need no count)."""
    raw = json.dumps([*key, total]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _after(cursor: str | None) -> tuple[FactKey | None, int | None]:
    """The key to page after and the total the first page counted (None: a v2.1 cursor)."""
    if not cursor:
        return None, None
    try:
        raw = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except (ValueError, TypeError) as exc:
        raise ReaderInputError("cursor is not one find_fact returned") from exc
    ok = isinstance(raw, list) and len(raw) in (4, 5) and all(isinstance(x, str) for x in raw[:4])
    if not ok or (len(raw) == 5 and not isinstance(raw[4], int)):
        raise ReaderInputError("cursor is not one find_fact returned")
    return (raw[0], raw[1], raw[2], raw[3]), (raw[4] if len(raw) == 5 else None)


class ReaderBusyError(ApplicationError):
    """Too many lookups at once in this process: retry in a moment."""

    code = "busy"


class LookupLimit:
    """At most ``n`` concurrent database lookups of one kind per process; a caller waits up to
    ``wait`` seconds for a slot, then gets ReaderBusyError (never an unbounded queue)."""

    def __init__(self, n: int, wait: float = 0.5) -> None:
        self._slots = threading.BoundedSemaphore(max(1, n))
        self._wait = wait
        self.n = max(1, n)

    def __enter__(self) -> None:
        if not self._slots.acquire(timeout=self._wait):
            raise ReaderBusyError(
                f"busy: {self.n} lookups are already running on this server; retry in a few seconds"
            )

    def __exit__(self, *_exc: object) -> None:
        self._slots.release()


def _match_bytes(m: FactMatch) -> int:
    return len(json.dumps(dataclasses.asdict(m), default=str))


class FindFact:
    """Presence/absence of an endpoint, field or scope, with evidence and a completeness flag."""

    MENTIONS = 5

    def __init__(
        self,
        resolver: BuildResolver,
        facts: FactQuery,
        index: SearchIndex,
        documents: DocumentRepo | None = None,
        limit: LookupLimit | None = None,
    ) -> None:
        self._resolver = resolver
        self._facts = facts
        self._index = index
        self._documents = documents
        self._limit = limit  # concurrent paged lookups per process (None: unbounded)

    def _conflict_note(
        self, build_id: BuildId, fact: Fact, docs: dict[str, Any] | None = None
    ) -> str | None:
        """x-kariz-conflicts of the fact's document that concern it: the endpoint itself, or a
        statement about this parameter (param:<name>). Every statement, never one picked.
        ``docs``: the call's cache of owner documents (one load per owner)."""
        if self._documents is None:
            return None
        cache = docs if docs is not None else {}
        if fact.owner_id not in cache:
            cache[fact.owner_id] = self._documents.get_document(build_id, fact.owner_id)
        doc = cache[fact.owner_id]
        conflicts = conflicts_of(doc.raw) if doc is not None else ()
        hits = [
            c for c in conflicts
            if (fact.kind is FactKind.ENDPOINT and c.field is None)
            or conflict_concerns(c, fact.name)
        ]  # fmt: skip
        return "\n".join(c.text for c in hits) or None

    def _with_conflicts(
        self, build_id: BuildId, m: FactMatch, fact: Fact, docs: dict[str, Any] | None = None
    ) -> FactMatch:
        conflict = self._conflict_note(build_id, fact, docs)
        return replace(m, note="\n".join(x for x in (m.note, conflict) if x)) if conflict else m

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

    def _endpoint_forms(
        self, build_id: BuildId, name: str, kind: FactKind | None
    ) -> tuple[list[Fact], list[str]]:
        """An endpoint asked as "/path" (any method) or "METHOD /path", path parameters matched
        by position ({id} = {order_id}), a full URL's host and query ignored. Returns the
        matches, and reasons why absence is NOT proven (only the method differs, or the query
        is not an endpoint form while endpoints were asked for)."""
        m = _ENDPOINT_FORM.match(name.strip())
        if m is None:
            if kind is FactKind.ENDPOINT:
                return [], [f'{name!r} is not an endpoint form; ask "METHOD /path" or "/path"']
            return [], []
        method = (m.group("method") or "").upper()
        path, _, qs = re.sub(r"^[a-z]+://[^/]+", "", m.group("path"), flags=re.I).partition("?")
        on_path = [
            f
            for f in self._facts.endpoints(build_id)
            if (p := f.name.partition(" ")[2]) == path or path_matches(p, path)
        ]
        hits = [f for f in on_path if not method or f.name.partition(" ")[0] == method]
        if len(hits) > 1 and len({f.name for f in hits}) == 1:  # RPC by name (POST /sync)
            return self._by_value(build_id, hits, split_values(qs.split("&"))[1])
        if hits or not on_path:
            return hits, []
        others = sorted({f.name.partition(" ")[0] for f in on_path})
        return [], [f"{path} is documented for {', '.join(others)}, not {method}"]

    def _by_value(
        self, build_id: BuildId, hits: list[Fact], values: dict[str, str]
    ) -> tuple[list[Fact], list[str]]:
        """Operations sharing METHOD + path: the fixed value given in the query string picks
        one ("POST /sync?method=aliexpress.x.get"); without it, say which to pass."""
        owners = [f.owner_id for f in hits]
        fixed, picks = fixed_values(self._facts, build_id, owners, list(values))
        if not picks:
            return hits, []
        if any(k in values for k in picks):
            chosen = set(pick_operations(owners, fixed, picks, values))
            return [f for f in hits if f.owner_id in chosen], []
        key = picks[0]
        example = sorted(v[key] for v in fixed.values() if key in v)[0]
        return hits[:MAX_AMBIGUOUS_MATCHES], [
            f"ambiguous: {len(hits)} operations share {hits[0].name}; pass {key}=<name> "
            f'(e.g. "{hits[0].name}?{key}={example}"); {MAX_AMBIGUOUS_MATCHES} shown'
        ]

    def _fetch(
        self,
        api: str,
        build_id: BuildId,
        name: str,
        fact_kind: FactKind | None,
        owner: str | None,
        resource: str | None,
        loc: FieldLocation | None,
        limit: int,
        after: FactKey | None,
    ) -> tuple[list[Fact], int, bool, list[str]]:
        """One page of matches (the database bounds it), the total, whether more follow, and
        the reasons an endpoint form gives."""
        try:
            with self._limit if self._limit is not None else contextlib.nullcontext():
                found, total = self._facts.find_page(
                    build_id, name, kind=fact_kind, owner_id=owner, resource=resource,
                    location=loc, limit=limit + 1, after=after,
                )  # fmt: skip
        except QueryTooBroadError as exc:
            raise ReaderInputError(
                f"too broad: looking up {name!r} in {api} took too long; narrow it with "
                'owner= (an endpoint such as "GET /orders" or a document id), kind=, '
                "location= or resource="
            ) from exc
        more = len(found) > limit
        found = found[:limit]
        endpoint_reasons: list[str] = []
        if not found and after is None and fact_kind in (None, FactKind.ENDPOINT):
            found, endpoint_reasons = self._endpoint_forms(build_id, name, fact_kind)
            total, more = len(found), False
        elif (
            after is None
            and len(found) > 1
            and all(f.kind is FactKind.ENDPOINT for f in found)
            and len({f.name for f in found}) == 1
        ):  # "POST /sync" itself: 156 AliExpress operations, a method value picks one
            same = self._facts.find(build_id, name, kind=FactKind.ENDPOINT, owner_id=owner)
            found, endpoint_reasons = self._by_value(build_id, same, {})
            total, more = len(found), False
            found = found[:limit]
        return found, total, more, endpoint_reasons

    def _page(
        self, build_id: BuildId, found: list[Fact], titles: dict[str, str], total: int,
        more: bool,
    ) -> tuple[list[FactMatch], str | None, str | None]:  # fmt: skip
        """The page's matches under the byte backstop, the next cursor and the hint."""
        docs: dict[str, Any] = {}
        matches: list[FactMatch] = []
        size = 0
        for f in found:
            m = self._with_conflicts(build_id, _match(f, titles), f, docs)
            size += _match_bytes(m)
            if matches and size > FIND_FACT_MAX_BYTES:  # the rest on the next page
                more = True
                break
            matches.append(m)
        kept = found[: len(matches)]
        next_cursor = _cursor(fact_key(kept[-1]), max(total, len(found))) if more and kept else None
        hint = None
        if next_cursor is not None:
            hint = (
                f"{max(total, len(found))} matches; {len(matches)} shown. Narrow it with owner= "
                '(an endpoint such as "GET /orders" or a document id), kind=, location= or '
                "resource=, or pass cursor for the next page."
            )
        return matches, next_cursor, hint

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
        limit: int = FIND_FACT_LIMIT,
        cursor: str | None = None,
    ) -> FindFactResult:
        """At most ``limit`` matches (≤ FIND_FACT_LIMIT, and ≤ FIND_FACT_MAX_BYTES), paged by
        ``cursor``; the total counts every match."""
        name = name.strip()
        limit = max(1, min(limit, FIND_FACT_LIMIT))
        after, known_total = _after(cursor)
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
        found, total, more, endpoint_reasons = self._fetch(
            api, build_id, name, fact_kind, owner, resource, loc, limit, after
        )
        if known_total is not None:  # later pages: the first page's total (no count query)
            total = known_total
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
            o
            for o in self._facts.incomplete_owners(build_id, owner_id=owner, resource=resource)
            # a model's completeness says nothing about whether an endpoint exists
            if fact_kind is not FactKind.ENDPOINT or not o.startswith("model:")
        )
        complete = not incomplete and not endpoint_reasons
        reasons: list[str] = list(endpoint_reasons)  # what to ask instead comes first
        reasons += [f"{o} is flagged incomplete by its source" for o in incomplete]
        field_like = fact_kind in (None, FactKind.FIELD) and loc not in (
            FieldLocation.PATH,
            FieldLocation.QUERY,
            FieldLocation.HEADER,
        )
        if not found and field_like:
            bounded = self._facts.bounded_owners(build_id, owner_id=owner, resource=resource)
            if bounded:
                # The field may sit deeper than Plume lists for these schemas: not proven.
                complete = False
                reasons.append(_bounded_reason(bounded))
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
        matches, next_cursor, hint = self._page(build_id, found, titles, total, more)
        wording = _fact_wording(
            r.build.build_id.value, max(total, len(found)), complete, checked, reasons,
            bool(mentions),
        )  # fmt: skip
        return FindFactResult(
            ref=_ref(r),
            name=name,
            found=bool(found),
            total=max(total, len(found)),
            next_cursor=next_cursor,
            hint=hint,
            matches=tuple(matches),
            complete=complete,
            checked=checked,
            text_mentions=mentions,
            wording=wording,
            incomplete_sources=incomplete,
            reasons=tuple(reasons),
        )


_VERSION_SEGMENT = re.compile(r"^(?:v\d+(?:\.\d+)*|\d{4}-\d{2}(?:-\d{2})?)$", re.I)


PAGING_TERM_SCORE = 3  # used as a parameter in the guide (quoted, or next to "parameter")


def _is_version(segment: str) -> bool:
    return bool(_VERSION_SEGMENT.match(segment))


# Parameters RPC-by-name APIs pick the operation with (AliExpress POST /sync?method=...)
RPC_PARAMS = ("method", "action", "operation", "op", "command", "cmd", "function", "service")
MAX_AMBIGUOUS_MATCHES = 10


def path_query(path: str) -> list[str]:
    """The query string of a call path as "name=value" entries (``/sync?method=a.b&x`` ->
    ["method=a.b", "x"])."""
    pairs = parse_qsl(urlsplit(path.strip()).query, keep_blank_values=True)
    return [f"{k}={v}" if v else k for k, v in pairs]


def split_values(entries: Sequence[str]) -> tuple[list[str], dict[str, str]]:
    """``["method=aliexpress.x.get", "fields"]`` -> the names, and {name: value} where a
    value is given."""
    names, values = [], {}
    for entry in entries:
        name, eq, value = entry.partition("=")
        names.append(name.strip())
        if eq and value.strip():
            values[name.strip().lower()] = value.strip()
    return names, values


def fixed_values(
    facts: FactQuery, build_id: BuildId, owners: Sequence[str], names: Sequence[str]
) -> tuple[dict[str, dict[str, str]], list[str]]:
    """The fixed parameter values (a single-value enum) of these operations, for the given
    names and the usual RPC ones: {owner: {name: value}}, and the names whose value differs
    between them (what picks one operation at a shared METHOD + path)."""
    wanted = set(owners)
    out: dict[str, dict[str, str]] = {o: {} for o in owners}
    for name in dict.fromkeys(n.lower() for n in (*names, *RPC_PARAMS)):
        for f in facts.find(build_id, name, kind=FactKind.FIELD):
            if f.owner_id not in wanted or f.name.lower() != name or f.location not in (
                FieldLocation.QUERY, FieldLocation.HEADER, FieldLocation.BODY,
            ):  # fmt: skip
                continue
            enum = constraint_dict(f.constraints).get("enum")
            if isinstance(enum, list) and len(enum) == 1:
                out[f.owner_id][name] = str(enum[0])
    picks = sorted(
        n for n in {k for v in out.values() for k in v} if len({v.get(n) for v in out.values()}) > 1
    )
    return out, picks


def pick_operations(
    owners: Sequence[str], fixed: dict[str, dict[str, str]], picks: Sequence[str],
    values: dict[str, str],
) -> list[str]:  # fmt: skip
    """The operations whose fixed values match the given ones (case-insensitive)."""
    given = {k: v.lower() for k, v in values.items() if k in picks}
    return [o for o in owners if all(fixed[o].get(k, "").lower() == v for k, v in given.items())]


# words a guide id may have and still be about paging in general (not one resource's paging)
_GENERAL_PAGING_WORDS = frozenset({
    "guide", "page", "pages", "paging", "pagination", "paginated", "paginate", "cursor",
    "cursors", "query", "parameter", "parameters", "param", "params", "request", "requests",
    "response", "responses", "result", "results", "limit", "limits", "restriction",
    "restrictions", "rule", "rules", "best", "practice", "practices", "implementation",
    "implementing", "workflow", "validation", "rest", "api", "general", "overview", "how",
    "to", "and", "the", "of", "for", "with", "using", "use", "list", "lists", "size", "offset",
    "token", "tokens", "next", "link", "header", "headers", "conventions", "convention",
})  # fmt: skip


def _general_paging(doc_id: str) -> bool:
    """A guide id about paging in general (rest-pagination, workflow-best-practices-pagination-
    implementation), not one resource's paging (virtual-packs-...-query-parameters)."""
    words = [w for w in re.split(r"[^a-z0-9]+", doc_id.removeprefix("guide:").lower()) if w]
    return any(w.startswith("pag") for w in words) and all(
        w in _GENERAL_PAGING_WORDS or w.isdigit() for w in words
    )


def _param_key(name: str) -> str:
    """A parameter's match key: the full name, case-insensitive, list marks ignored
    (items[].sku = items.sku); page[number] stays its own name."""
    return name.strip().lower().replace("[]", "")


# Places a call names its parameters in; headers that auth fills are not asked for.
_ASKED = frozenset({FieldLocation.QUERY, FieldLocation.BODY, FieldLocation.HEADER})
_AUTH_HEADER = re.compile(  # fallback when the auth schemes name no header
    r"authorization|api[-_]?key|access[-_]?token|signature|secret|cookie|x-auth", re.IGNORECASE
)


_AUTH_TEMPLATE = re.compile(r"\{\{[^}]*\bauth\??\.", re.IGNORECASE)


def _auth_default(f: Fact) -> bool:
    """A header whose default is a template over the auth connection's variables (MyDeal
    SellerID: "{{ auth?.oauth?.vars?.SellerID }}"): auth fills it, like an auth header."""
    try:
        default = json.loads(f.constraints or "{}").get("default")
    except (ValueError, AttributeError):
        return False
    return isinstance(default, str) and bool(_AUTH_TEMPLATE.search(default))


class CheckCall:
    """Is ``METHOD /path`` with these params documented? Matches templates like ``{id}``."""

    def __init__(
        self,
        resolver: BuildResolver,
        facts: FactQuery,
        index: SearchIndex,
        documents: DocumentRepo | None = None,
    ) -> None:
        self._resolver = resolver
        self._facts = facts
        self._index = index
        self._documents = documents

    def execute(
        self,
        api: str,
        method: str,
        path: str,
        params: Sequence[str] = (),
        version: str | None = None,
        query: Sequence[str] = (),
        body: Sequence[str] = (),
    ) -> CheckCallResult:
        """``params``: names in any request location; ``query`` / ``body``: names checked in
        that location only. A parameter the schema does not list is documented by pagination
        when the endpoint's pagination contract or the API's pagination guide names it. A call
        whose version segment differs from the endpoint's fixed version is not documented."""
        method = method.upper().strip()
        if method not in HTTP_METHODS:
            raise ReaderInputError(f"unknown HTTP method {method!r}")
        params, given = split_values(params)  # "method=aliexpress.x.get": a name and a value
        # a query string in the path counts as query parameters (POST /sync?method=aliexpress.x)
        in_path = [q for q in path_query(path) if q not in query]
        query, given_q = split_values([*query, *in_path])
        given |= given_q
        if not path.strip():
            raise ReaderInputError("path is empty")
        r = self._resolver.resolve(api, version)
        build_id = r.build.build_id
        candidates, call_paths, servers = self._candidates(build_id, method, path, r.api.versions)
        counts = self._index.counts(build_id)
        checked = {"endpoints": counts.get("endpoint", 0), "models": counts.get("model", 0)}
        names = [(p, None) for p in params] + [(q, FieldLocation.QUERY) for q in query]
        names += [(b, FieldLocation.BODY) for b in body]
        version_note: str | None = None
        if candidates:
            fitting = [
                c for c in candidates
                if self._same_version(build_id, c[1].owner_id, call_paths.get(c[1].owner_id, path))
            ]  # fmt: skip
            if not fitting:
                fixed = self._real_path(build_id, candidates[0][1].owner_id)
                version_note = f"the documented operation is {method} {fixed}"
            candidates = fitting
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
                tuple(ParamCheck(p, False, None) for p, _ in names),
                checked,
                None,
                note=version_note,
            )
        candidates.sort(key=lambda c: (-c[0], c[2], c[1].owner_id))
        best = candidates[0]
        # Several operations at the same METHOD + path, or the same route shape under different
        # parents (Graph-style GET /{campaign_id}/copies and /{ad_id}/copies): the one that
        # documents the most of these params; the others are named as alternatives.
        shape = route_shape(best[2])
        tied = [c for c in candidates if c[0] == best[0] and route_shape(c[2]) == shape]
        # RPC by name (one path, AliExpress POST /sync): a fixed parameter value picks the
        # operation; not across parents, where a single-value enum is just a constraint
        if len(tied) > 1 and len({c[2] for c in tied}) == 1:
            owners = [c[1].owner_id for c in tied]
            by_owner, picks = fixed_values(self._facts, build_id, owners, [p for p, _ in names])
            if picks:
                if not any(k in given for k in picks):
                    return self._ambiguous(r, method, path, best[2], owners, by_owner, picks, names,
                                           checked)  # fmt: skip
                chosen = set(pick_operations(owners, by_owner, picks, given))
                if not chosen:
                    asked = ", ".join(f"{k}={v}" for k, v in given.items() if k in picks)
                    return CheckCallResult(
                        _ref(r), method, path, "not_documented", True, None, None, None,
                        tuple(ParamCheck(p, False, None) for p, _ in names), checked, None,
                        note=f"no operation at {method} {best[2]} has {asked}",
                    )  # fmt: skip
                tied = [c for c in tied if c[1].owner_id in chosen]
        scored, deprecated = self._score(build_id, tied, names)
        _, _, endpoint, matched_path, checks = scored[0]
        alternatives = tuple(x[1] for x in scored[1:])
        per_candidate = _per_candidate(scored, deprecated) if len(scored) > 1 else ()
        if not all(c.found for c in checks) and per_candidate:
            if split := self._split(r, method, path, matched_path, scored, names, checked,
                                    deprecated):  # fmt: skip
                return split
            checks = _with_sibling_params(checks, scored)
        complete = endpoint.complete
        verdict, note, missing = self._verdict(build_id, endpoint.owner_id, path, checks, names)
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
            note=note,
            matched_server=(
                servers[endpoint.owner_id].label
                if endpoint.owner_id in servers
                else self._server_label(build_id, endpoint.owner_id)
            ),
            missing_required=missing,
            candidates=per_candidate,
        )

    def _score(
        self,
        build_id: BuildId,
        tied: Sequence[tuple[int, Fact, str]],
        names: Sequence[tuple[str, FieldLocation | None]],
    ) -> tuple[list[tuple[int, str, Fact, str, list[ParamCheck]]], frozenset[str]]:
        """The equal candidates best first: the most of these params documented, then not
        deprecated (Meta POST /{ad_id}/adlabels is, /{ad_creative_id}/adlabels is not), then
        by id; and the deprecated ones among them."""
        scored = []
        for _, f, f_path in tied:
            checks = self._param_checks(build_id, f.owner_id, names)
            scored.append((-sum(c.found for c in checks), f.owner_id, f, f_path, checks))
        summaries = (
            self._index.summaries(build_id, [x[1] for x in scored]) if len(scored) > 1 else {}
        )
        deprecated = frozenset(o for o, s in summaries.items() if s.deprecated)
        scored.sort(key=lambda x: (x[0], x[1] in deprecated, x[1]))
        return scored, deprecated

    @staticmethod
    def _split(
        r: ResolvedBuild,
        method: str,
        path: str,
        matched: str,
        scored: Sequence[tuple[int, str, Fact, str, list[ParamCheck]]],
        names: Sequence[tuple[str, FieldLocation | None]],
        checked: dict[str, int],
        deprecated: frozenset[str] = frozenset(),
    ) -> CheckCallResult | None:
        """Equal candidates and no one documents all the params, but together they do: the
        call is ambiguous (which parent node is it?), with the params each one documents.
        None when some param is documented by none of them."""
        found_by: dict[str, list[str]] = {}
        for _, owner, _, _, checks in scored:
            for c in checks:
                if c.found:
                    found_by.setdefault(c.name, []).append(owner)
        if any(n not in found_by for n, _ in names):
            return None
        per = _per_candidate(scored, deprecated)
        listed = "; ".join(
            f"{o}{' (deprecated)' if dep else ''}: {', '.join(p) or 'none of them'}"
            for o, p, dep in per
        )
        note = (
            f"ambiguous: {len(scored)} operations match {method} {path} equally and none "
            f"documents all these params ({listed}); call the one for your parent object"
        )
        params = tuple(
            ParamCheck(n, True, None, note=f"documented on {', '.join(found_by[n])}")
            for n, _ in names
        )
        owners = tuple(x[1] for x in scored)
        return CheckCallResult(
            _ref(r), method, path, "ambiguous", True, None, method, matched, params, checked,
            None, owners, note=note, candidates=per,
        )  # fmt: skip

    def _missing_required(
        self, build_id: BuildId, owner_id: str, passed: Sequence[str]
    ) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """The documented required parameters the call did not pass, per place (query, body,
        header; path parameters are in the path and auth headers are filled by auth). A nested
        field counts only when it is top-level or its parent object was passed (a passed child
        passes its parent too), so a flat list never asks for the inside of an object the call
        leaves out."""
        given = {_param_key(p) for p in passed}
        auth = self._auth_headers(build_id)

        def present(key: str) -> bool:
            return key in given or any(g.startswith(key + ".") for g in given)

        out: dict[str, list[str]] = {}
        for f in self._facts.for_owner(build_id, owner_id):
            if f.kind is not FactKind.FIELD or not f.required or f.location not in _ASKED:
                continue
            if f.location is FieldLocation.HEADER and (
                f.name.lower() in auth or _AUTH_HEADER.search(f.name) or _auth_default(f)
            ):
                continue
            key = _param_key(f.name)
            parent = key.rsplit(".", 1)[0] if "." in key else None
            if present(key) or (parent is not None and not present(parent)):
                continue
            where = f.location.value if f.location else "body"
            if f.name not in out.setdefault(where, []):
                out[where].append(f.name)
        order = ("query", "body", "header")
        return tuple((w, tuple(sorted(out[w]))) for w in order if out.get(w))

    def _ambiguous(
        self,
        r: ResolvedBuild,
        method: str,
        path: str,
        matched: str,
        owners: list[str],
        fixed: dict[str, dict[str, str]],
        picks: list[str],
        names: Sequence[tuple[str, FieldLocation | None]],
        checked: dict[str, int],
    ) -> CheckCallResult:
        """Several operations share METHOD + path and a parameter value picks one: say which
        to pass, with examples (AliExpress: 218 operations at POST /sync)."""
        key = picks[0]
        values = sorted(v[key] for v in fixed.values() if key in v)
        examples = values[:3]
        unpicked = len(owners) - len(values)  # operations stating no fixed value for it
        note = (
            f"ambiguous: {len(owners)} operations share {method} {matched}; pass "
            f"{key}=<name> in params or query (e.g. {', '.join(f'{key}={e}' for e in examples)})"
            + (f"; {len(values)} state a {key} value, {unpicked} do not" if unpicked else "")
        )
        return CheckCallResult(
            _ref(r), method, path, "ambiguous", True, None, method, matched,
            tuple(ParamCheck(p, False, None) for p, _ in names), checked, None,
            tuple(sorted(owners)[:MAX_AMBIGUOUS_MATCHES]), note=note, pick_param=key,
            pick_options=tuple(sorted((v[key], o) for o, v in fixed.items() if key in v)),
        )  # fmt: skip

    def _candidates(
        self, build_id: BuildId, method: str, path: str, versions: tuple[str, ...]
    ) -> tuple[list[tuple[int, Fact, str]], dict[str, str], dict[str, ServerBase]]:
        """The endpoints at METHOD + path: as given, or with a server's base path taken off
        (the path a developer calls may carry eBay api_3's /commerce/media/v1_beta, which the
        stored paths do not). Also, per endpoint matched that way, the call path as stored and
        the server."""
        wanted = normalize_call_path(path, versions)
        stripped = [
            (b, rest, normalize_call_path(rest, versions))
            for b, rest in without_server_base(path, self._server_bases(build_id))
        ]
        candidates: list[tuple[int, Fact, str]] = []
        call_paths: dict[str, str] = {}
        servers: dict[str, ServerBase] = {}
        for f in self._facts.endpoints(build_id):
            f_method, _, f_path = f.name.partition(" ")
            if f_method != method:
                continue
            if path_matches(f_path, wanted):
                candidates.append((specificity(f_path), f, f_path))
                continue
            for base, rest, alt in stripped:
                if path_matches(f_path, alt) and base.serves(
                    self._endpoint_server(build_id, f.owner_id)
                ):
                    candidates.append((specificity(f_path), f, f_path))
                    call_paths[f.owner_id], servers[f.owner_id] = rest, base
                    break
        return candidates, call_paths, servers

    def _auth_headers(self, build_id: BuildId) -> set[str]:
        """The headers the API's auth schemes fill (their headerName), lower case."""
        if self._documents is None:
            return set()
        out: set[str] = set()
        schemes, _ = self._index.browse(build_id, (DocumentKind.AUTH,), None, 50, 0)
        for d in schemes:
            doc = self._documents.get_document(build_id, d.doc_id)
            raw: dict[str, Any] = doc.raw if doc and isinstance(doc.raw, dict) else {}
            nested = raw.get("scheme")
            scheme: dict[str, Any] = nested if isinstance(nested, dict) else raw
            name = scheme.get("headerName")
            if isinstance(name, str) and name:
                out.add(name.lower())
        return out

    def _server_bases(self, build_id: BuildId) -> list[ServerBase]:
        """The API's servers with a base path, from the loader's environments guide."""
        if self._documents is None:
            return []
        doc = self._documents.get_document(build_id, ENVIRONMENTS_DOC_ID)
        return server_bases(doc.text) if doc is not None else []

    def _verdict(
        self,
        build_id: BuildId,
        owner_id: str,
        path: str,
        checks: Sequence[ParamCheck],
        names: Sequence[tuple[str, FieldLocation | None]],
    ) -> tuple[str, str | None, tuple[tuple[str, tuple[str, ...]], ...]]:
        """documented when every parameter is found; the note on missing required fields; and a
        full URL on a host that does not serve the endpoint (another server's host: not
        documented; an unknown host: a warning)."""
        verdict = "documented" if all(c.found for c in checks) else "not_documented"
        missing = self._missing_required(build_id, owner_id, [n for n, _ in names])
        note = None
        if missing and verdict == "documented":
            listed = "; ".join(f"{where}: {', '.join(fields)}" for where, fields in missing)
            note = f"documented, but these required fields are missing: {listed}"
        problem = host_problem(
            path, self._endpoint_server(build_id, owner_id), self._environments(build_id)
        )
        if problem is not None:
            kind, why = problem
            if kind == "other_server":  # not this endpoint's surface: its params don't apply
                return "not_documented", why, missing
            note = f"{why}; {note}" if note else why
        deprecation = self._deprecation(build_id, owner_id)
        if deprecation is not None:  # the contract still holds: a note, not a verdict
            note = f"{note}; {deprecation}" if note else deprecation
        return verdict, note, missing

    def _deprecation(self, build_id: BuildId, owner_id: str) -> str | None:
        """For a deprecated endpoint: "this endpoint is deprecated: <the package's words>" (its
        deprecation notice, else its first rule line about it), plain when it states none."""
        doc = self._documents.get_document(build_id, owner_id) if self._documents else None
        if doc is None or not doc.deprecated:
            return None
        return "this endpoint is deprecated" + (
            f": {why}" if (why := deprecation_text(doc)) else ""
        )

    def _server_label(self, build_id: BuildId, owner_id: str) -> str | None:
        """The endpoint's server ("api_2: https://ads-api.facebook.com", the default
        environment's URL) when the API lists separate servers; None for a single-server API."""
        key = self._endpoint_server(build_id, owner_id)
        envs = self._environments(build_id)
        if key is None or not envs or not any(e.servers for e in envs):
            return None
        return f"{key}: {envs[0].url_of(key)}"

    def _environments(self, build_id: BuildId) -> list[Environment]:
        if self._documents is None:
            return []
        doc = self._documents.get_document(build_id, ENVIRONMENTS_DOC_ID)
        return environments_of(doc.text) if doc is not None else []

    def _endpoint_server(self, build_id: BuildId, owner_id: str) -> str | None:
        doc = self._documents.get_document(build_id, owner_id) if self._documents else None
        url = doc.raw.get("url") if doc is not None and isinstance(doc.raw, dict) else None
        return endpoint_server(url) if isinstance(url, str) else None

    def _real_path(self, build_id: BuildId, doc_id: str) -> str | None:
        summary = self._index.summaries(build_id, [doc_id]).get(doc_id)
        return summary.real_path if summary else None

    def _same_version(self, build_id: BuildId, owner_id: str, call_path: str) -> bool:
        """The call's version segment equals the endpoint's fixed version (real path), when
        the package fixes one; a variable version accepts any."""
        fixed = self._real_path(build_id, owner_id)
        if not fixed:
            return True
        call = call_path.split("?", 1)[0].strip("/").split("/")
        real = fixed.strip("/").split("/")
        offset = len(call) - len(real)  # a host prefix in the call shifts the segments
        return not any(
            0 <= i + offset < len(call)
            and _is_version(seg)
            and _is_version(call[i + offset])
            and seg.lower() != call[i + offset].lower()
            for i, seg in enumerate(real)
        )

    def _pagination(self, build_id: BuildId, owner_id: str) -> set[str]:
        """The parameter names the endpoint's pagination contract gives (e.g. Shopify
        page_info, Mirakl max / offset), as match keys."""
        doc = self._documents.get_document(build_id, owner_id) if self._documents else None
        contract = doc.raw.get("pagination") if doc and isinstance(doc.raw, dict) else None
        if not isinstance(contract, dict):
            return set()
        return {_param_key(v) for v in contract.values() if isinstance(v, str) and v.strip()}

    def _conflict(self, build_id: BuildId, owner_id: str, name: str) -> str | None:
        """The docs' different values for this parameter (x-kariz-conflicts), every statement
        with its place; the check itself stays the vendor's text (never one value picked)."""
        doc = self._documents.get_document(build_id, owner_id) if self._documents else None
        texts = [
            c.text for c in (conflicts_of(doc.raw) if doc is not None else ())
            if conflict_concerns(c, name)
        ]  # fmt: skip
        return "\n".join(texts) or None

    def _paging_guide(
        self, build_id: BuildId, owner_id: str, hits: list[ChunkHit]
    ) -> ChunkHit | None:
        """The paging guide to point to: one tied to this endpoint or its resource (by its
        endpoint links or resource), else a general one (tied to no resource); never a guide
        about another resource (Walmart GET /orders pointed to virtual packs' paging)."""
        if not hits or self._documents is None:
            return None
        endpoint = self._documents.get_document(build_id, owner_id)
        resource = (endpoint.resource or "").lower() if endpoint else ""
        general: ChunkHit | None = None
        for h in hits:
            g = self._documents.get_document(build_id, h.doc_id)
            if g is None:
                continue
            links = linked_endpoints(g)
            if owner_id in links or (resource and (g.resource or "").lower() == resource):
                return h  # this endpoint's own, or its resource's
            if resource and any(
                (e := self._documents.get_document(build_id, x)) is not None
                and (e.resource or "").lower() == resource
                for x in links
            ):
                return h
            if not links and not g.resource and general is None and _general_paging(h.doc_id):
                general = h  # about paging in general
        return general

    def _paging_guides(self, build_id: BuildId) -> list[ChunkHit]:
        """The API's guides about paging, for a name the endpoint does not document."""
        return list(self._index.text(build_id, "pagination paging page", 10, (DocumentKind.GUIDE,)))

    def _param_checks(
        self,
        build_id: BuildId,
        owner_id: str,
        names: Sequence[tuple[str, FieldLocation | None]],
    ) -> list[ParamCheck]:
        owned = self._facts.for_owner(build_id, owner_id)
        paging: set[str] | None = None
        guides: list[ChunkHit] | None = None
        checks = []
        for p, location in names:
            wanted = _param_key(p)
            hits = [  # the full name only: status is not publication.status (Allegro gate B1)
                f
                for f in owned
                if f.kind is FactKind.FIELD
                and _param_key(f.name) == wanted
                and f.location is not FieldLocation.RESPONSE
                and (location is None or f.location is location)
            ]
            if hits:
                where = hits[0].location.value if hits[0].location else None
                checks.append(
                    ParamCheck(p, True, where, note=self._conflict(build_id, owner_id, p))
                )
                continue
            if location is not FieldLocation.BODY:
                if paging is None:
                    paging = self._pagination(build_id, owner_id)
                # only what the endpoint's own pagination contract names: a guide that uses
                # "page" does not make page a parameter of an endpoint paging by offset/limit
                if wanted in paging:
                    checks.append(ParamCheck(p, True, "pagination"))
                    continue
                if guides is None:
                    guides = self._paging_guides(build_id)
                guide = self._paging_guide(
                    build_id,
                    owner_id,
                    [h for h in guides if _term_use(h.text, p)[0] >= PAGING_TERM_SCORE],
                )
                if guide is not None:  # point to it; do not assert the name
                    checks.append(ParamCheck(p, False, None, note=(
                        "Not in this endpoint's documented parameters. Paging for this API is "
                        f"described in {guide.doc_id} ({guide.title}); check it before using "
                        "this name."
                    ), guide_id=guide.doc_id))  # fmt: skip
                    continue
            checks.append(ParamCheck(p, False, None))
        return checks


_RULE_SUFFIX = re.compile(
    r"\s*\((?:constraint|rule|precondition|effect|limit|state-transition)[^)]*\)\s*$"
)


def deprecation_text(doc: Document) -> str | None:
    """The package's words on why an endpoint is deprecated: its request's deprecation notice
    (message / notes / note / reason / sunset), else its first line about deprecation under a
    "Rules" heading (never a field line)."""
    raw = doc.raw if isinstance(doc.raw, dict) else {}
    notice = raw.get("deprecation")
    if isinstance(notice, dict):
        words = [str(notice[k]).strip() for k in ("message", "notes", "note", "reason", "sunset")
                 if isinstance(notice.get(k), str) and notice[k].strip()]  # fmt: skip
        if words:
            return " ".join(words)
    elif isinstance(notice, str) and notice.strip():
        return notice.strip()
    in_rules = False
    for line in doc.text.splitlines():
        if line.startswith("#"):
            in_rules = line.lstrip("#").strip().lower().startswith("rules")
            continue
        text = _RULE_SUFFIX.sub("", line.strip().removeprefix("- ")).strip()
        if in_rules and line.lstrip().startswith("- ") and "deprecat" in text.lower():
            return text  # the rule's own words (its quoted source may mention it in passing)
    return None


def _with_sibling_params(
    checks: Sequence[ParamCheck],
    scored: Sequence[tuple[int, str, Fact, str, list[ParamCheck]]],
) -> list[ParamCheck]:
    """A param the matched endpoint lacks but an equal candidate documents is found there
    (never not_documented for a param a candidate documents), with a note naming it."""
    out = []
    for c in checks:
        sibling = next(
            (o for _, o, _, _, cs in scored[1:] for x in cs if x.name == c.name and x.found), None
        )
        out.append(
            c if c.found or sibling is None else ParamCheck(
                c.name, True, None, note=f"documented on {sibling}, not on the matched operation"
            )
        )  # fmt: skip
    return out


def _per_candidate(
    scored: Sequence[tuple[int, str, Fact, str, list[ParamCheck]]],
    deprecated: frozenset[str] = frozenset(),
) -> tuple[tuple[str, tuple[str, ...], bool], ...]:
    """(operation id, the call's params it documents, deprecated) per equal candidate."""
    return tuple((x[1], tuple(c.name for c in x[4] if c.found), x[1] in deprecated) for x in scored)
