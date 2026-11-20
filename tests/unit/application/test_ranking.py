"""A knowledge-export page keeps one of its endpoints next to it in the top-k (no page demotion)."""

from plume.application.reader.ranking import pair_pages_with_endpoints, stale_version_guides_last

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
