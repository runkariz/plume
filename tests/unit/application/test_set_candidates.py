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
