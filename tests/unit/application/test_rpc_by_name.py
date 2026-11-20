"""RPC-by-name APIs (AliExpress: 156 operations at POST /sync, picked by a fixed `method`
query value): check_call and find_fact need that value, and say so when it is missing."""

from types import SimpleNamespace
from typing import Any

from plume.application.reader.use_cases import CheckCall, FindFact, split_values
from plume.domain.knowledge.citation import Citation
from plume.domain.knowledge.document import DocumentKind, FieldLocation
from plume.domain.knowledge.fact import Fact, FactKind
from plume.domain.shared.ids import BuildId

OPS = {"endpoint:POST~/sync@a": "shop.order.get", "endpoint:POST~/sync@b": "shop.product.get"}
BUILD = BuildId("b-" + "0" * 32)


def _endpoint(owner: str) -> Fact:
    return Fact(FactKind.ENDPOINT, owner, DocumentKind.ENDPOINT, "POST /sync", Citation(owner))


def _method(owner: str, value: str) -> Fact:
    return Fact(FactKind.FIELD, owner, DocumentKind.ENDPOINT, "method", Citation(owner),
                location=FieldLocation.QUERY, type="string",
                constraints=f'{{"enum": ["{value}"]}}')  # fmt: skip


ENDPOINTS = [_endpoint(o) for o in OPS]
METHODS = [_method(o, v) for o, v in OPS.items()]


def _find(_b: BuildId, name: str, **kw: Any) -> list[Fact]:
    pool = METHODS + ENDPOINTS
    kind = kw.get("kind")
    return [f for f in pool if f.name.lower() == name.lower() and kind in (None, f.kind)]


FACTS = SimpleNamespace(
    endpoints=lambda _b: ENDPOINTS,
    find=_find,
    for_owner=lambda _b, owner: [f for f in METHODS if f.owner_id == owner],
    incomplete_owners=lambda *_a, **_k: [],
    bounded_owners=lambda *_a, **_k: {},
)
INDEX = SimpleNamespace(
    counts=lambda _b: {"endpoint": 2},
    summaries=lambda _b, ids: {},
    text=lambda *_a, **_k: [],
)
RESOLVED = SimpleNamespace(
    api=SimpleNamespace(api_id=SimpleNamespace(value="ali"), versions=()),
    build=SimpleNamespace(build_id=BUILD), tag="latest", docs_as_of=None,
)  # fmt: skip
RESOLVER = SimpleNamespace(resolve=lambda _api, _v=None: RESOLVED)


def test_split_values() -> None:
    assert split_values(["method=shop.order.get", "fields"]) == (
        ["method", "fields"], {"method": "shop.order.get"},
    )  # fmt: skip


def test_check_call_needs_the_method_value() -> None:
    check = CheckCall(RESOLVER, FACTS, INDEX)  # type: ignore[arg-type]
    vague = check.execute("ali", "POST", "/sync")
    assert vague.verdict == "ambiguous"
    assert vague.note is not None
    assert vague.note.startswith("ambiguous: 2 operations share POST /sync; pass method=<name>")
    picked = check.execute("ali", "POST", "/sync", ["method=shop.product.get"])
    assert (picked.verdict, picked.matched_id) == ("documented", "endpoint:POST~/sync@b")
    as_query = check.execute("ali", "POST", "/sync", query=["method=SHOP.ORDER.GET"])
    assert as_query.matched_id == "endpoint:POST~/sync@a"
    wrong = check.execute("ali", "POST", "/sync", ["method=nope"])
    assert (wrong.verdict, wrong.note) == (
        "not_documented", "no operation at POST /sync has method=nope",
    )  # fmt: skip


def test_find_fact_needs_the_method_value() -> None:
    find = FindFact(RESOLVER, FACTS, INDEX)  # type: ignore[arg-type]
    vague = find.execute("ali", "POST /sync", kind="endpoint")
    assert vague.reasons[0].startswith("ambiguous: 2 operations share POST /sync")
    assert vague.complete is False
    picked = find.execute("ali", "POST /sync?method=shop.order.get", kind="endpoint")
    assert [m.owner_id for m in picked.matches] == ["endpoint:POST~/sync@a"]
    assert picked.reasons == ()
