"""Set relation candidates under the members' names: each API's own concept counts for a
member through its role names (Shopify line item = "Order line"; fulfillment = "Shipment"),
and candidates landing on the same pair merge."""

from typing import Any

from plume.application.models.concepts import role_keys
from plume.application.models.model_sets import _as_members
from plume.application.models.relations import CandidateEvidence, RelationCandidate


def _cand(parent: str, child: str, api: str, path: str) -> RelationCandidate:
    ev = CandidateEvidence("nested", f"model:{parent}", "quote", (path,), many=True)
    return RelationCandidate(parent, child, {api: [ev]})


def test_role_keys() -> None:
    assert role_keys("Order line") == (
        "orderline", "lineitem", "orderitem", "orderlineitem", "orderproduct", "positionitem"
    )  # fmt: skip
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


def _ev(kind: str, doc: str, path: str, *, read: bool = True, home: bool = True) -> Any:
    return CandidateEvidence(kind, doc, "quote", (path,), many=True, read=read, home=home)


def test_another_name_gives_way_to_the_same_kind_under_the_own_name() -> None:
    """set-g4: BigCommerce /orders/{id}/consignments sat beside /orders/{id}/shipments for
    Order > Shipment; Zalando's orderitem id field must stay beside order_lines[] (other kind)."""
    found = [
        RelationCandidate("order", "shipment", {"bigcommerce": [
            _ev("sub_resource", "endpoint:shipments", "order_id")]}),
        RelationCandidate("order", "consignment", {"bigcommerce": [
            _ev("sub_resource", "endpoint:consignments", "order_id")]}),
        RelationCandidate("order", "orderline", {"zalando": [
            _ev("nested", "model:announcedreturnorder", "order_lines[]")]}),
        RelationCandidate("order", "orderitem", {"zalando": [
            _ev("id_field", "model:orderitem", "attributes.order_id")]}),
    ]  # fmt: skip
    by_pair = {(c.parent, c.child): c for c in _as_members(found, ["Order", "Order line",
                                                                   "Shipment"])}  # fmt: skip
    shipments = by_pair[("order", "shipment")].sources["bigcommerce"]
    assert [e.doc_id for e in shipments] == ["endpoint:shipments"]
    lines = by_pair[("order", "orderline")].sources["zalando"]
    assert {e.kind for e in lines} == {"nested", "id_field"}


def test_evidence_from_the_two_concepts_documents_first() -> None:
    """set-g4: Shopware taxruletype rules[].country.orderAddresses[] and ordertag paths beside
    the order's own billingAddress; write echoes in other resources only are no evidence."""
    from plume.application.models.relations import _ranked  # noqa: PLC0415

    bucket = [
        _ev("nested", "model:taxruletype", "rules[].country.orderAddresses[]", home=False),
        _ev("nested", "model:order", "addresses[]"),
        _ev("nested", "model:order", "billingAddress"),
    ]
    assert [e.doc_id for e in _ranked(bucket)] == ["model:order", "model:order"]
    echoes = [_ev("nested", "endpoint:PUT checkout", "data.consignments[]", read=False,
                  home=False)]  # fmt: skip
    assert _ranked(echoes) == []


def test_an_orders_items_list_is_its_order_lines() -> None:
    from plume.application.models.relations import _compound  # noqa: PLC0415

    assert _compound("order", "item") == "orderitem"  # Magento items[]
    assert _compound("order", "product") == "orderproduct"  # BigCommerce /orders/{id}/products
    assert _compound("product", "variant") is None
    assert _compound("order", "lineitem") is None  # already a role name of its own


def test_a_merged_packages_section_suffix_is_not_part_of_the_concept() -> None:
    """OTTO: models "Address__Orders-V4", resources "OrdersV4"."""
    from plume.application.models.concepts import concept_key  # noqa: PLC0415

    assert concept_key("Address__Orders-V4") == "address"
    assert concept_key("PositionItem__Shipments-V1") == "positionitem"
    assert concept_key("OrdersV4") == "order"
    assert concept_key("Order line") == "orderline"
    assert concept_key("MP3") == "mp3"
