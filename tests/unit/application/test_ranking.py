"""A knowledge-export page keeps one of its endpoints next to it in the top-k (no page demotion)."""

from plume.application.reader.ranking import pair_pages_with_endpoints

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
