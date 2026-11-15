import pytest

from plume.domain.knowledge.call_check import normalize_call_path, path_matches, specificity
from plume.domain.knowledge.ranking import reciprocal_rank_fusion


def test_rrf_rewards_agreement() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "a", "d"]])
    assert [f.key for f in fused][:2] in (["a", "b"], ["b", "a"])
    assert fused[0].score == pytest.approx(1 / 61 + 1 / 62)
    assert {f.key for f in fused} == {"a", "b", "c", "d"}
    d = next(f for f in fused if f.key == "d")
    assert d.ranks == (None, 3)


def test_rrf_deterministic_tie_break_and_weights() -> None:
    fused = reciprocal_rank_fusion([["x"], ["y"]])
    assert [f.key for f in fused] == ["x", "y"]
    weighted = reciprocal_rank_fusion([["x"], ["y"]], weights=[1.0, 2.0])
    assert weighted[0].key == "y"
    with pytest.raises(ValueError, match="weight"):
        reciprocal_rank_fusion([["x"]], weights=[1.0, 2.0])


def test_rrf_duplicate_keys_keep_best_rank() -> None:
    fused = reciprocal_rank_fusion([["a", "a", "b"]])
    assert fused[0].ranks == (1,)


@pytest.mark.parametrize(
    ("template", "path", "ok"),
    [
        ("/api/{version}/products/{product_id}.json", "/api/{version}/products/42.json", True),
        ("/admin/api/{version}/products.json", "/admin/api/{version}/products.json", True),
        ("/api/{version}/orders", "/api/{version}/orders/7", False),
        ("/api/{version}/orders/{id}", "/api/{version}/orders/7", True),
        ("/a/{id}.json", "/a/.json", False),
        ("/a/{id}.json", "/a/7.xml", False),
        ("/a/b", "/a/c", False),
    ],
)  # fmt: skip
def test_path_matches(template: str, path: str, ok: bool) -> None:
    assert path_matches(template, path) is ok


def test_normalize_call_path_and_specificity() -> None:
    assert normalize_call_path("https://shop.test/admin/api/2026-10/products/1.json?x=1") == (
        "/admin/api/{version}/products/1.json"
    )
    assert specificity("/a/{id}/b") == 2
