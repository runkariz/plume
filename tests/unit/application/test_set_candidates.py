"""Set relation candidates under the members' names: each API's own concept counts for a
member through its role names (Shopify line item = "Order line"; fulfillment = "Shipment"),
and candidates landing on the same pair merge."""

from plume.application.models.concepts import role_keys
from plume.application.models.model_sets import _as_members
from plume.application.models.relations import CandidateEvidence, RelationCandidate


def _cand(parent: str, child: str, api: str, path: str) -> RelationCandidate:
    ev = CandidateEvidence("nested", f"model:{parent}", "quote", (path,), many=True)
    return RelationCandidate(parent, child, {api: [ev]})


def test_role_keys() -> None:
    assert role_keys("Order line") == ("orderline", "lineitem", "orderitem", "orderlineitem")
    assert "fulfillment" in role_keys("Shipment")
    assert "shipping" not in role_keys("Shipment")  # a shipping address is no shipment
    assert {"billing", "shipping", "billingaddress", "defaultaddress"} <= set(role_keys("Address"))


def test_candidates_merge_under_member_names() -> None:
    found = [
        _cand("order", "orderline", "mirakl", "orders[].order_lines[]"),
        _cand("order", "lineitem", "shopify", "line_items[]"),
        _cand("order", "fulfillment", "shopify", "fulfillments[]"),
        _cand("order", "refund", "shopify", "refunds[]"),  # not a member: dropped
    ]
    members = _as_members(found, ["Order", "Order line", "Shipment"])
    assert [(c.parent, c.child, sorted(c.sources)) for c in members] == [
        ("order", "orderline", ["mirakl", "shopify"]),
        ("order", "shipment", ["shopify"]),
    ]


def test_a_member_reached_only_through_a_role_name_has_a_label(packages, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """bol "orderitem" / eBay "lineitem" for "Order line": the context's options need a label
    for the member key (KeyError 'orderline' on plume-l2)."""
    from tests.fakes.knowledge import WordEmbedder  # noqa: PLC0415
    from tests.fakes.stack import FakeStack  # noqa: PLC0415

    stack = FakeStack(embedder=WordEmbedder())
    for p in ("shopify-mini", "test-catalog"):
        stack.load(str(packages / p))
    found = [_cand("order", "lineitem", "shopify", "line_items[]")]
    labels = {"order": "Order", "lineitem": "Line Item"}  # the APIs never say "Order line"
    sets = stack.model_sets()
    monkeypatch.setattr(sets._related, "candidates", lambda *_a, **_k: (found, [], labels))
    session = sets.start(["shopify", "test-catalog-api"], ["Order", "Order line"])
    ctx = sets.context(session.session_id, maintainer=True)
    [cand] = ctx["relation_candidates"]
    assert (cand["from"], cand["to"]) == ("Order", "Order line")
    assert cand["options"]


def test_the_same_evidence_is_listed_once() -> None:
    """plume-da: products[].variants[].product_id appeared twice on one candidate."""
    found = [
        _cand("order", "orderline", "shopify", "line_items[]"),
        _cand("order", "lineitem", "shopify", "line_items[]"),  # same evidence, other name
    ]
    [merged] = _as_members(found, ["Order", "Order line"])
    assert len(merged.sources["shopify"]) == 1
