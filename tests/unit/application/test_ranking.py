"""A knowledge-export page keeps one of its endpoints next to it in the top-k (no page demotion)."""

from plume.application.reader.ranking import (
    code_holder_first,
    error_codes_after_endpoint,
    limit_guide_after_endpoint,
    pair_pages_with_endpoints,
    query_code,
    scoped_last,
    stale_version_guides_last,
    triggers_after_endpoints,
)

EPS = {"guide:page-orders": ["endpoint:GET~/orders", "endpoint:POST~/orders"]}


def _pair(ranked: list[str], k: int) -> list[str]:
    return pair_pages_with_endpoints(ranked, k, lambda d: EPS.get(d, []))


def test_endpoint_moves_in_right_after_its_page() -> None:
    ranked = ["guide:page-orders", "model:a", "model:b", "endpoint:GET~/x",
              "endpoint:POST~/orders", "endpoint:GET~/orders"]  # fmt: skip
    out = _pair(ranked, 4)
    assert out[:4] == ["guide:page-orders", "endpoint:POST~/orders", "model:a", "model:b"]
    assert sorted(out) == sorted(ranked)  # same ids, only reordered
    assert out[4] == "endpoint:GET~/x"  # the displaced result comes first after the top-k


def test_nothing_moves_when_an_endpoint_is_already_there_or_none_in_the_pool() -> None:
    present = ["model:a", "guide:page-orders", "endpoint:GET~/orders", "model:b"]
    assert _pair(present, 3) == present
    absent = ["guide:page-orders", "model:a", "model:b", "model:c"]
    assert _pair(absent, 2) == absent


def test_pages_are_never_demoted() -> None:
    EPS["guide:page-refunds"] = ["endpoint:GET~/refunds"]
    ranked = ["guide:page-orders", "guide:page-refunds", "endpoint:GET~/orders",
              "endpoint:GET~/refunds"]  # fmt: skip
    out = _pair(ranked, 2)
    assert out[:2] == ["guide:page-orders", "guide:page-refunds"]  # no non-page to replace


def test_a_guide_of_a_version_the_endpoints_lack_gives_way_to_its_sibling() -> None:
    """Amazon "how many requests per second to get orders": the Orders API v0 rate-limit guide
    led, linked to the package's v2026-01-01 getOrder; the v2026-01-01 guide was outside."""
    v0 = "guide:rate-limit-orders-api-v0-rate-limits"
    v26 = "guide:rate-limit-orders-api-v2026-01-01-rate-limits"
    ep = "endpoint:GET~/orders/{version}/orders/{orderId}"
    links = {v0: [ep], v26: [ep]}
    versions = {ep: "2026-01-01"}
    ranked = [v0, ep, "guide:other", "model:x"]
    out = stale_version_guides_last(ranked, 3, lambda d: links.get(d, []), versions.get,
                                    lambda d: d == v26)  # fmt: skip
    assert out[:3] == [v26, ep, v0]
    # a guide of the version the endpoints carry stays
    same = stale_version_guides_last([v26, ep], 3, lambda d: links.get(d, []), versions.get,
                                     lambda d: False)  # fmt: skip
    assert same == [v26, ep]
    # no sibling: behind its endpoint
    alone = stale_version_guides_last(ranked, 3, lambda d: links.get(d, []), versions.get,
                                      lambda d: False)  # fmt: skip
    assert alone[:2] == [ep, v0]
    # unknown endpoint versions: unchanged
    assert stale_version_guides_last(ranked, 3, lambda d: links.get(d, []), lambda e: None,
                                     lambda d: True) == ranked  # fmt: skip


def test_an_http_status_question_keeps_the_error_codes_guide_behind_the_endpoint() -> None:
    """Mirakl N4: the accept endpoint names ORDER_INVALID_STATE; the 400 is in guide:context."""
    ranked = ["endpoint:PUT~/api/orders/{order_id}/accept", "endpoint:GET~/api/orders", "m:x"]
    q = "What HTTP status do I get when I accept an order in the wrong state?"
    out = error_codes_after_endpoint(ranked, 3, q, lambda: "guide:context")
    assert out[:3] == [ranked[0], "guide:context", ranked[1]]
    # an order-state question, or the guide already in the top k: unchanged
    assert error_codes_after_endpoint(ranked, 3, "what status will the order receive",
                                      lambda: "guide:context") == ranked  # fmt: skip
    already = ["guide:context", *ranked]
    assert error_codes_after_endpoint(already, 3, q, lambda: "guide:context") == already


def test_a_trigger_gives_way_to_its_endpoint_unless_the_question_is_about_events() -> None:
    """Trendyol "report an item as unsupplied": trigger:unsupplied led the endpoint."""
    ep = "endpoint:PUT~/integration/order/shipment-packages/{packageId}/items/unsupplied"
    ranked = ["trigger:unsupplied", ep, "trigger:undelivered", "endpoint:GET~/claims"]
    res = {"trigger:unsupplied": "order", "trigger:undelivered": "order"}.get
    out = triggers_after_endpoints(ranked, 4, "report an item as unsupplied", res)
    assert out[:2] == [ep, "trigger:unsupplied"]
    # by resource: behind the first top-k endpoint of the trigger's resource
    by_res = {"trigger:returned": "order"}.get
    out = triggers_after_endpoints(
        ["trigger:returned", "endpoint:GET~/orders/{id}"],
        2,
        "how are returned packages sorted",
        by_res,
    )
    assert out == ["endpoint:GET~/orders/{id}", "trigger:returned"]
    # an event question keeps the trigger first
    q = "which webhook event fires when an item is unsupplied"
    assert triggers_after_endpoints(ranked, 4, q, res) == ranked


def test_a_named_code_leads_with_the_document_that_contains_it() -> None:
    """eBay Buy "what does error 12006 mean": the Offer error guide led; 12006 is in Browse's."""
    ranked = ["guide:error-codes-buy-offer", "guide:topic-error-format", "model:error"]
    holders = {"12006": ["guide:error-codes-buy-browse"]}
    out = code_holder_first(ranked, 3, "what does error 12006 mean", lambda d, c: False,
                            lambda c: holders.get(c, []))  # fmt: skip
    assert out[:2] == ["guide:error-codes-buy-browse", "guide:error-codes-buy-offer"]
    assert query_code("what does error 12006 mean") == "12006"
    assert query_code("how many orders since 2024") is None  # no error / code wording
    assert query_code("what does a 409 error mean") is None  # HTTP statuses: their own rule
    # TikTok: the endpoint at rank 1 has the code (not among the text-search hits): it stays
    held = ["endpoint:GET~/coupons/{id}", "app:tiktokshop"]
    out = code_holder_first(held, 3, "error code 36009003", lambda d, c: d.startswith("endpoint"),
                            lambda c: ["app:tiktokshop"])  # fmt: skip
    assert out == held


def test_a_limit_question_keeps_the_guide_stating_the_limit_behind_the_endpoint() -> None:
    """eBay Buy "how many charity ids can I filter a search by": 20, one row of the Browse
    error-code table."""
    ranked = ["endpoint:GET~/search", "endpoint:POST~/search_by_image", "guide:a", "model:b"]
    q = "how many charity ids can I filter a search by"
    out = limit_guide_after_endpoint(ranked, 4, q, lambda: "guide:error-codes-buy-browse")
    assert out[:3] == ["endpoint:GET~/search", "guide:error-codes-buy-browse", ranked[1]]
    assert limit_guide_after_endpoint(ranked, 4, "list orders", lambda: "guide:g") == ranked


def test_a_scoped_guide_gives_way_unless_the_question_names_its_part() -> None:
    """BigCommerce: scoped-request-limits (one quote: an 8 MB product image) led a whole-API
    import-size question."""
    ranked = ["guide:scoped-request-limits", "endpoint:PUT~/catalog/products", "app:bc", "m:x"]
    parts = {"guide:scoped-request-limits": frozenset({"image", "product", "catalog"})}.get
    out = scoped_last(
        ranked, 2, "what is the maximum import file size", lambda d: parts(d, frozenset())
    )
    assert out == ["endpoint:PUT~/catalog/products", "app:bc", "m:x", "guide:scoped-request-limits"]
    kept = scoped_last(
        ranked, 2, "how large can a product image be", lambda d: parts(d, frozenset())
    )
    assert kept == ranked
