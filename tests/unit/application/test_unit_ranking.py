"""A knowledge unit that names its endpoints (endpointIds) brings one of them into the top-k,
from the pool or the wider endpoint ranking; nothing above the unit and no endpoint moves out."""

from collections.abc import Sequence

from plume.application.reader.ranking import pair_units_with_endpoints

LINKS = {
    "guide:scope-logistic": [
        "endpoint:GET~/logistic-centers",
        "endpoint:GET~/logistic-centers/{id}",
    ],
    "guide:sandbox": ["endpoint:POST~/stocks"],
}


def _pair(ranked: list[str], k: int, wider: Sequence[str] = ()) -> tuple[list[str], int]:
    asked = 0

    def more() -> Sequence[str]:
        nonlocal asked
        asked += 1
        return wider

    return pair_units_with_endpoints(ranked, k, lambda d: LINKS.get(d, []), more), asked


def test_a_unit_brings_its_endpoint_from_the_pool() -> None:
    ranked = ["guide:scope-logistic", "guide:a", "guide:b", "guide:c", "guide:d",
              "endpoint:GET~/logistic-centers/{id}"]  # fmt: skip
    out, asked = _pair(ranked, 5)
    assert out[:5] == ["guide:scope-logistic", "endpoint:GET~/logistic-centers/{id}",
                       "guide:a", "guide:b", "guide:c"]  # fmt: skip
    assert out[5] == "guide:d"
    assert sorted(out) == sorted(ranked)
    assert asked == 0  # the pool had it


def test_the_wider_ranking_is_asked_once_when_the_pool_lacks_it() -> None:
    ranked = ["guide:scope-logistic", "guide:sandbox", "guide:a", "guide:b", "guide:c"]
    wider = ["endpoint:GET~/other", "endpoint:POST~/stocks", "endpoint:GET~/logistic-centers"]
    out, asked = _pair(ranked, 5, wider)
    assert out[:5] == ["guide:scope-logistic", "endpoint:GET~/logistic-centers",
                       "guide:sandbox", "endpoint:POST~/stocks", "guide:a"]  # fmt: skip
    assert asked == 1


def test_endpoints_and_results_above_the_unit_never_move_out() -> None:
    ranked = ["endpoint:GET~/x", "guide:a", "endpoint:GET~/y", "guide:scope-logistic",
              "endpoint:GET~/z", "endpoint:GET~/logistic-centers"]  # fmt: skip
    out, _ = _pair(ranked, 5)
    assert out == ranked  # only endpoints, the unit and results above it: nothing to replace


def test_without_links_nothing_moves_and_nothing_is_asked() -> None:
    ranked = ["guide:a", "guide:b", "endpoint:GET~/x", "model:m"]
    out, asked = _pair(ranked, 3, ["endpoint:GET~/logistic-centers"])
    assert out == ranked
    assert asked == 0


def test_an_endpoint_already_in_the_top_is_enough() -> None:
    ranked = ["guide:scope-logistic", "guide:a", "endpoint:GET~/logistic-centers", "guide:b"]
    out, asked = _pair(ranked, 4, ["endpoint:GET~/logistic-centers/{id}"])
    assert out == ranked
    assert asked == 0


def test_keep_endpoints_brings_two_endpoints_into_the_top_k() -> None:
    from plume.application.reader.ranking import keep_endpoints  # noqa: PLC0415

    ranked = [
        "guide:a",
        "guide:b",
        "model:m",
        "guide:c",
        "guide:d",
        "endpoint:1",
        "x",
        "endpoint:2",
    ]
    out = keep_endpoints(ranked, 5)
    assert out[:5] == ["guide:a", "guide:b", "model:m", "endpoint:1", "endpoint:2"]
    assert out[5:7] == ["guide:c", "guide:d"]  # evicted ones lead the rest
    assert sorted(out) == sorted(ranked)
    already = ["endpoint:1", "guide:a", "endpoint:2", "guide:b", "guide:c", "endpoint:3"]
    assert keep_endpoints(already, 5) == already
    assert keep_endpoints(["guide:a", "guide:b"], 5) == ["guide:a", "guide:b"]  # none in pool
    assert keep_endpoints(["guide:a", "endpoint:1"], 1) == ["endpoint:1", "guide:a"]
