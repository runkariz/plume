"""Keep a documentation page's endpoint next to the page in the top results.

Knowledge-export page guides often rank first for a question (they carry the page's prose), and
can push the endpoint the question is about out of the top-k. Pages are not demoted: for every
page in the top-k whose endpoints are all missing from it, the best-ranked of its endpoints
from the rest of the pool moves in right after the page, and the lowest-ranked result that is
neither a page nor such an endpoint makes room.
"""

import re
from collections.abc import Callable, Sequence

PAGE_PREFIX = "guide:page-"


def is_page(doc_id: str) -> bool:
    return doc_id.startswith(PAGE_PREFIX)


def pair_pages_with_endpoints(
    ranked: Sequence[str],
    k: int,
    endpoints_of: Callable[[str], Sequence[str]],
) -> list[str]:
    """`ranked` reordered (same ids) so each page in the top-`k` has one of its endpoints there
    too, when the pool holds one."""
    top, rest = list(ranked[:k]), list(ranked[k:])
    protected: set[str] = {d for d in top if is_page(d)}
    for page in [d for d in top if is_page(d)]:
        endpoints = set(endpoints_of(page))
        if not endpoints:
            continue
        present = [d for d in top if d in endpoints]
        if present:
            protected.update(present)
            continue
        candidate = next((d for d in rest if d in endpoints), None)
        victim = next((d for d in reversed(top) if d not in protected), None)
        if candidate is None or victim is None:
            continue
        top.remove(victim)
        top.insert(top.index(page) + 1, candidate)
        rest.remove(candidate)
        rest.insert(0, victim)
        protected.add(candidate)
    return top + rest


def lift_operation_endpoints(
    ranked: Sequence[str], k: int, owner_of: Callable[[str], str | None]
) -> list[str]:
    """`ranked` reordered (same ids) so a per-operation model in the top-`k` (Mirakl's
    `a02-response-200-...`: a piece of PUT /api/account's response) has its endpoint just before
    it, when the pool holds that endpoint. The pieces stay; the endpoint the question is about
    comes first."""
    top, rest = list(ranked[:k]), list(ranked[k:])
    placed: set[str] = set()
    for doc in list(top):
        if doc not in top:  # pushed out by an earlier lift
            continue
        owner = owner_of(doc)
        if owner is None or owner in placed:
            continue
        placed.add(owner)
        if owner in top:
            if top.index(owner) > top.index(doc):
                top.remove(owner)
                top.insert(top.index(doc), owner)
            continue
        if owner not in rest:
            continue
        rest.remove(owner)
        top.insert(top.index(doc), owner)
        rest.insert(0, top.pop())
    return top + rest


def pair_units_with_endpoints(
    ranked: Sequence[str],
    k: int,
    linked_of: Callable[[str], Sequence[str]],
    wider: Callable[[], Sequence[str]],
) -> list[str]:
    """`ranked` reordered so a knowledge unit in the top-`k` that names its endpoints
    (``endpointIds``) has one of them right after it, like a page does.

    A unit's question ("which scope does the Logistic Centers API need?") is about its endpoint,
    but the unit's prose outranks the endpoint's thin text. The endpoint comes from the pool, or
    else from `wider` (the endpoints ranked for the query; asked once, only when needed). The
    result that makes room is the lowest-ranked one below the unit that is neither an endpoint
    nor a unit/page with links: nothing ranked above the unit moves out, no endpoint is evicted.
    Units without links leave the order unchanged."""
    top, rest = list(ranked[:k]), list(ranked[k:])
    anchors = [d for d in top if not is_page(d) and linked_of(d)]
    if not anchors:
        return top + rest
    protected = set(anchors) | {d for d in top if d.startswith("endpoint:") or is_page(d)}
    extra: list[str] | None = None
    for unit in anchors:
        endpoints = set(linked_of(unit))
        present = [d for d in top if d in endpoints]
        if present:
            continue
        candidate = next((d for d in rest if d in endpoints), None)
        if candidate is None:
            if extra is None:
                extra = list(wider())
            candidate = next((d for d in extra if d in endpoints), None)
        position = top.index(unit)
        victim = next(
            (d for d in reversed(top) if d not in protected and top.index(d) > position), None
        )
        if candidate is None or victim is None:
            continue
        top.remove(victim)
        top.insert(top.index(unit) + 1, candidate)
        if candidate in rest:
            rest.remove(candidate)
        rest.insert(0, victim)
        protected.add(candidate)
    return top + rest


MIN_ENDPOINTS = 2


def keep_endpoints(ranked: Sequence[str], k: int, minimum: int = MIN_ENDPOINTS) -> list[str]:
    """At least ``minimum`` endpoints in the top-k when the pool has them: the best-ranked
    endpoints below the top-k replace its lowest-ranked other results (which move to the front
    of the rest); the top-k keeps the pool's order. Knowledge units outnumber endpoints several
    times over, and a question about an operation was otherwise answered by guides alone."""
    top, rest = list(ranked[:k]), list(ranked[k:])
    have = sum(1 for d in top if d.startswith("endpoint:"))
    for candidate in [d for d in rest if d.startswith("endpoint:")]:
        if have >= min(minimum, k):
            break
        victim = next((d for d in reversed(top) if not d.startswith("endpoint:")), None)
        if victim is None:
            break
        top[top.index(victim)] = candidate
        rest.remove(candidate)
        rest.insert(0, victim)
        have += 1
    position = {d: i for i, d in enumerate(ranked)}
    return sorted(top, key=position.__getitem__) + rest


def request_models_last(ranked: Sequence[str], k: int) -> list[str]:
    """A request-body model (what a client sends) is rarely what a question is after: within
    the top 2k, they move behind the other results (the endpoint that takes them stays)."""
    window, rest = list(ranked[: 2 * k]), list(ranked[2 * k :])
    first = [d for d in window if not (d.startswith("model:") and "request" in d)]
    last = [d for d in window if d.startswith("model:") and "request" in d]
    return first + last + rest


# words every guide id of a package shares (its kind, the vendor's doc site): no meaning
_GUIDE_FILLER = frozenset({
    "guide", "page", "docs", "doc", "developer", "com", "www", "api", "apis", "workflow",
    "lifecycle", "state", "machine", "validation", "resource", "rules", "rule", "best",
    "practice", "using", "the", "and", "for", "with", "how", "overview", "us", "marketplace",
})  # fmt: skip
DUPLICATE_GUIDE = 0.5  # word overlap (Jaccard) of two guide ids that say the same thing


def _guide_words(doc_id: str) -> frozenset[str]:
    words = re.split(r"[^a-z0-9]+", doc_id.removeprefix("guide:").lower())
    return frozenset(w for w in words if len(w) > 2 and w not in _GUIDE_FILLER)


def near_duplicate_guides_last(ranked: Sequence[str], k: int) -> list[str]:
    """A guide whose id says nearly what a better-ranked guide's says (Walmart's access token
    lifecycle in three sections) moves behind the top 2k: one of them is enough."""
    window, rest = list(ranked[: 2 * k]), list(ranked[k * 2 :])
    kept: list[str] = []
    moved: list[str] = []
    seen: list[frozenset[str]] = []
    for d in window:
        if d.startswith("guide:"):
            words = _guide_words(d)
            if words and any(len(words & w) / len(words | w) >= DUPLICATE_GUIDE for w in seen):
                moved.append(d)
                continue
            seen.append(words)
        kept.append(d)
    return kept + rest + moved


# a question about authenticating / signing requests (not about an operation named "sign")
_AUTH_QUERY = re.compile(
    r"\bsign(s|ed|ing)?\b.*\b(requests?|calls?|param\w*)\b|\bsignatures?\b.*\b(requests?|calls?)\b"
    r"|\b(compute|calculate|generate)\b.*\bsign(ature)?\b|\bsign param"
    r"|\b(access|app|api|bearer|refresh|admin api)[ -]?(tokens?|keys?)\b|\boauth\b"
    r"|\bclient credentials\b|\bauthenticat\w*\b.*\b(requests?|calls?|the api|api)\b"
    r"|\bauth(entication|orization)? headers?\b|\bwhich header authenticates\b"
    r"|^\s*(how (do|can|should) (i|we|you) (authenticate|log ?in)|(api )?authentication|"
    r"how does (the )?authentication work)\s*\??\s*$",
    re.IGNORECASE,
)
_SCOPE_QUERY = re.compile(r"\b(which|what) (oauth )?scopes?\b|\bscopes? (do i|are) need", re.I)
_SIGN_QUERY = re.compile(r"\bsign(s|ed|ing|ature)?\b", re.IGNORECASE)
_AUTH_DOC = re.compile(r"auth|sign|token|credential|oauth|hmac", re.IGNORECASE)


# incoming calls (webhook / callback / notification; Turkish "bildirim")
_WEBHOOK_DOC = re.compile(r"webhook|callback|notification|bildirim", re.IGNORECASE)
_WEBHOOK_QUERY = re.compile(r"\b(webhooks?|callbacks?|notifications?)\b", re.IGNORECASE)
_AUTH_OPERATION = re.compile(r"token|oauth|auth", re.IGNORECASE)  # not "sign": namesakes


def _auth_doc(doc_id: str) -> bool:
    """An auth scheme, a guide about auth / signing / tokens, or an operation or doc page that
    issues or explains tokens (Magento POST /integration/admin/token, Shopify's OAuth page)."""
    if doc_id.startswith(("auth:", "app:")):  # the app document carries the setup / signing text
        return True
    if _WEBHOOK_DOC.search(doc_id):  # verifying incoming calls, not calling the API (Trendyol)
        return False
    if doc_id.startswith((PAGE_PREFIX, "endpoint:")):
        return bool(_AUTH_OPERATION.search(doc_id.split(":", 1)[1]))
    return doc_id.startswith("guide:") and bool(_AUTH_DOC.search(doc_id.removeprefix("guide:")))


def _webhook_auth_doc(window: Sequence[str]) -> str | None:
    """A guide about authenticating webhook calls, one that says "webhook" first."""
    docs = [d for d in window if d.startswith("guide:") and _WEBHOOK_DOC.search(d)
            and _AUTH_DOC.search(d)]  # fmt: skip
    return next((d for d in docs if "webhook" in d.lower()), None) or next(iter(docs), None)


def auth_first(
    ranked: Sequence[str],
    k: int,
    query: str,
    own: Callable[[], Sequence[str]] = tuple,
) -> list[str]:
    """An auth question puts the best-ranked auth document (a scheme, or a guide about auth /
    signing / tokens) first, ahead of operations that merely share a word (Lazada's sponsor
    /account/sign endpoints for "how do I sign a request"). With none ranked, the first of
    ``own()`` (the API's auth schemes, then its app document: TikTok's signing setup)."""
    if _SCOPE_QUERY.search(query):  # the scheme lists the scopes (Allegro "which scope …")
        if ranked and "scope" in ranked[0].lower():  # a scope guide leads (Zalando): keep it
            return list(ranked)
        scheme = next((d for d in ranked[: 2 * k] if d.startswith("auth:")), None) or next(
            (d for d in own() if d.startswith("auth:")), None
        )
        if scheme is not None and ranked and ranked[0] != scheme:
            return [scheme] + [d for d in ranked if d != scheme]
        return list(ranked)
    if not _AUTH_QUERY.search(query):
        return list(ranked)
    window = list(ranked[: 2 * k])
    if _WEBHOOK_QUERY.search(query):  # how incoming calls are authenticated: webhook docs only
        best = _webhook_auth_doc(window)
    else:  # the API's own scheme first, then any other auth document
        best = next((d for d in window if d.startswith("auth:")), None) or next(
            (d for d in window if _auth_doc(d)), None
        )
    if best is None and not _WEBHOOK_QUERY.search(query):  # the API's own schemes / app doc
        options = list(own())
        if _SIGN_QUERY.search(query):  # signing is set up in the app text, not a scheme
            options.sort(key=lambda d: not d.startswith("app:"))
        best = next(iter(options), None)
    if best is None or (window and _auth_doc(window[0])):  # an auth answer already leads
        return list(ranked)
    return [best] + [d for d in ranked if d != best]


# "mark an order as shipped", "change the state of a delivery": an operation that moves a state
_MARK_AS = re.compile(r"\bmark\b.*?\bas\s+(?:a\s+|an\s+)?(?P<state>[a-z]+)", re.IGNORECASE)
_SET_STATE = re.compile(r"\b(change|set|update|move)\b.*\b(status|state)\b", re.IGNORECASE)
_IRREGULAR = {"sent": "send", "paid": "pay", "shipped": "ship", "cancelled": "cancel",
              "canceled": "cancel", "dispatched": "dispatch", "fulfilled": "fulfill",
              "delivered": "deliver", "received": "receive", "accepted": "accept",
              "refunded": "refund", "returned": "return", "read": "read"}  # fmt: skip
_STATE_WORDS = frozenset({"state", "status", "transition", "transitions"})
_QUERY_STOP = frozenset({"mark", "as", "the", "a", "an", "of", "or", "and", "with", "to", "my",
                         "change", "set", "update", "move", "status", "state", "how", "do", "i",
                         "can", "number", "tracking", "code", "order"})  # fmt: skip


def _stem(word: str) -> str:
    word = word.lower()
    if word in _IRREGULAR:
        return _IRREGULAR[word]
    for suffix in ("ed", "d"):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[: -len(suffix)]
    return word


def _path_words(doc_id: str) -> list[str]:
    path = doc_id.split("~", 1)[-1].split("@", 1)[0]
    return [w for w in re.split(r"[^a-z0-9]+", path.lower()) if w]


def state_change_first(
    ranked: Sequence[str],
    k: int,
    query: str,
    endpoints: Callable[[], Sequence[str]] = tuple,
) -> list[str]:
    """ "mark X as shipped" / "change the state of X": the write operation that makes that
    change goes first (Shopware POST /_action/order_delivery/{id}/state/{transition}, Mirakl
    PUT /orders/{id}/ship), ahead of the resource's generic update and create endpoints. Found
    by path among all of the API's endpoints (Shopware's rank below its thousands of CRUD
    ones): it names a noun of the question, and the state's verb or a state / transition."""
    m = _MARK_AS.search(query)
    if m is None and not _SET_STATE.search(query):
        return list(ranked)
    verb = _stem(m.group("state")) if m else None
    nouns = {
        _stem(w).removesuffix("s")
        for w in re.split(r"[^a-z]+", query.lower())
        if len(w) > 3 and w not in _QUERY_STOP
    } - ({verb} if verb else set())

    def score(doc_id: str) -> int:
        """Nouns of the question the path names (0: not a state change of them)."""
        if not doc_id.startswith("endpoint:") or doc_id.startswith("endpoint:GET~"):
            return 0
        words = _path_words(doc_id)
        changes = (verb is not None and verb in words) or bool(_STATE_WORDS & set(words))
        named = sum(1 for n in nouns if any(n in w for w in words))
        return named if changes else 0

    window = list(ranked[: 2 * k])
    if window and score(window[0]):
        return list(ranked)
    pool = list(dict.fromkeys([*window, *endpoints()]))
    scored = [(score(d), -i, d) for i, d in enumerate(pool)]
    best = max((x for x in scored if x[0] > 0), default=None)
    if best is None:
        return list(ranked)
    return [best[2]] + [d for d in ranked if d != best[2]]


# guides Plume makes from the package's structured data (not the vendor's prose)
_SYNTHESIZED = ("guide:webhook-delivery-", "guide:environments-and-base-urls")


def synthesized_after_vendor(ranked: Sequence[str], k: int) -> list[str]:
    """A guide Plume made from structured data (webhook delivery, environments) gives way to
    the vendor's own guide on the topic: it moves just behind the first vendor guide of the
    top-k (bol's signature-verification guide, Woo's webhooks page); with none it stays."""
    order = list(ranked)
    for doc in [d for d in order[:k] if d.startswith(_SYNTHESIZED)]:
        at = order.index(doc)
        vendor = next(
            (i for i, d in enumerate(order[:k]) if i > at and d.startswith("guide:")
             and not d.startswith(_SYNTHESIZED)),
            None,
        )  # fmt: skip
        if vendor is not None:
            order.insert(vendor, order.pop(at))
    return order


_TEST_SEGMENT = re.compile(r"/(test|tests|sandbox|simulations?|staging)(?=/|$)", re.IGNORECASE)
_ASKS_FOR_TEST = re.compile(r"\b(test(ing)?|sandbox|staging|simulat\w*|demo)\b", re.IGNORECASE)


def production_before_test(ranked: Sequence[str], query: str) -> list[str]:
    """A test / sandbox / simulation endpoint gives way to the first production endpoint of
    the same method ranked below it (Trendyol PUT /integration/test/order/.../status above the
    production shipment-package PUTs), unless the question asks for the test environment."""
    if _ASKS_FOR_TEST.search(query):
        return list(ranked)
    order = list(ranked)
    for doc in [d for d in order if d.startswith("endpoint:") and _TEST_SEGMENT.search(d)]:
        method = doc.split("~", 1)[0]
        at = order.index(doc)
        prod = next(
            (i for i, d in enumerate(order) if i > at and d.split("~", 1)[0] == method
             and not _TEST_SEGMENT.search(d)),
            None,
        )  # fmt: skip
        if prod is not None:
            order.insert(at, order.pop(prod))
    return order


def _path_only(doc_id: str) -> bool:
    """GET /{file_path}: an endpoint whose path is only parameters (a URL another call
    returned), not a resource of its own."""
    if not doc_id.startswith("endpoint:"):
        return False
    path = doc_id.split("~", 1)[-1].split("@", 1)[0]
    segs = [x for x in path.strip("/").split("/") if x]
    return bool(segs) and all(x.startswith("{") for x in segs)


def path_only_after_endpoints(ranked: Sequence[str], k: int) -> list[str]:
    """A path-only endpoint (Mirakl GET /{file_path}: fetch a chunk of an export file) moves
    just behind the first other endpoint of the top-k: it is a follow-up step, not the
    answer (it ranked 1 for invoice questions)."""
    order = list(ranked)
    for doc in [d for d in order[:k] if _path_only(d)]:
        at = order.index(doc)
        other = next(
            (i for i, d in enumerate(order[:k]) if i > at and d.startswith("endpoint:")
             and not _path_only(d)),
            None,
        )  # fmt: skip
        if other is not None:
            order.insert(other, order.pop(at))
    return order


_RATE_QUERY = re.compile(r"\b(rate[ -]?limit\w*|429|throttl\w*|too many requests|quota)\b", re.I)
_RATE_DOC = re.compile(r"rate-?limit|throttl|quota", re.IGNORECASE)


def rate_limit_guide_first(ranked: Sequence[str], k: int, query: str) -> list[str]:
    """A rate-limit question leads with a guide about rate limits (its id says so) rather than
    a one-sentence rule that states one endpoint's limit (Mirakl resource-rules-api-2 at 1)."""
    if not _RATE_QUERY.search(query):
        return list(ranked)
    window = list(ranked[: 2 * k])
    if window and _RATE_DOC.search(window[0]):
        return list(ranked)
    best = next((d for d in window if d.startswith("guide:") and _RATE_DOC.search(d)), None)
    if best is None:
        return list(ranked)
    return [best] + [d for d in ranked if d != best]


def _singular(word: str) -> str:
    word = word.lower()
    for suffix, repl in (("ies", "y"), ("sses", "ss"), ("s", "")):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[: -len(suffix)] + repl
    return word


def _endpoint_key(doc_id: str) -> str:
    """The last literal path segment, singular and without separators (orders -> order)."""
    path = doc_id.split("~", 1)[-1].split("@", 1)[0]
    literals = [x.split(".", 1)[0] for x in path.strip("/").split("/") if x and "{" not in x]
    return _singular(re.sub(r"[^a-z0-9]", "", literals[-1].lower())) if literals else ""


def _model_key(doc_id: str) -> str:
    return _singular(re.sub(r"[^a-z0-9]", "", doc_id.removeprefix("model:").lower()))


def endpoint_before_its_model(ranked: Sequence[str], k: int) -> list[str]:
    """A model ranked just above the endpoint of the same resource gives way to it (Amazon
    model:destination above POST /notifications/destinations; model:order above GET
    /orders/{orderId}): the endpoint is the operation asked about, the model its shape."""
    order = list(ranked)
    for model in [d for d in order[:k] if d.startswith("model:")]:
        key = _model_key(model)
        at = order.index(model)
        twin = next(
            (i for i, d in enumerate(order[:k]) if i > at and d.startswith("endpoint:")
             and _endpoint_key(d) == key),
            None,
        )  # fmt: skip
        if twin is not None:
            order.insert(at, order.pop(twin))
    return order
