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
    assert specificity("/a/{id}/b") == 4  # two literal segments (2 each)


def test_semantic_fusion_keeps_a_clear_dense_winner_that_text_misses() -> None:
    """The Zalando case: the right unit is dense #1 but absent from full text, while a generic
    sibling is dense #4 and text #1. Plain RRF ranks the sibling first; the semantic fusion keeps
    the dense winner."""
    from plume.application.ports.search_index import ChunkHit  # noqa: PLC0415
    from plume.application.reader.use_cases import fuse_hits  # noqa: PLC0415
    from plume.domain.knowledge.document import DocumentKind  # noqa: PLC0415
    from plume.domain.knowledge.ranking import SEMANTIC_FUSION, Fusion  # noqa: PLC0415

    def hits(ids: list[str]) -> list[ChunkHit]:
        return [
            ChunkHit(f"{d}#0", d, DocumentKind.GUIDE, d, "", 1.0 - i / 10)
            for i, d in enumerate(ids)
        ]

    dense = hits(["right", "page", "other", "sibling"])
    text = hits(["sibling", "x", "y", "z"])
    plain = [h.doc_id for h in fuse_hits(dense, text, "q", 10)]
    semantic = [h.doc_id for h in fuse_hits(dense, text, "q", 10, SEMANTIC_FUSION)]
    assert plain[0] == "sibling"
    assert semantic[0] == "right"
    assert semantic.index("sibling") < semantic.index("x")  # text still counts
    with pytest.raises(ValueError, match="fusion"):
        Fusion(k=0)


def test_environment_words_expand_only_where_the_api_lacks_them() -> None:
    """Shopware has no sandbox, but documents a staging instance: "does Shopware have a
    sandbox" also searches staging. An API that names its sandbox keeps the question."""
    from plume.domain.knowledge.ranking import expand_text_query  # noqa: PLC0415

    q = "does Shopware have a sandbox environment for testing"
    expanded = expand_text_query(q, lambda w: w != "sandbox")
    assert expanded.startswith(q)
    assert "staging" in expanded
    assert "test account" in expanded
    assert expand_text_query(q, lambda _w: True) == q  # the API documents its sandbox
    assert expand_text_query("list orders", lambda _w: False) == "list orders"


def test_a_variable_inside_a_segment_matches() -> None:
    """Meta act_{AD_ACCOUNT_ID}, Google's {id}:verb, Shopify's {id}.json, {a}-{b}."""
    assert path_matches("/act_{AD_ACCOUNT_ID}/campaigns", "/act_123/campaigns")
    assert path_matches("/act_{AD_ACCOUNT_ID}/campaigns", "/act_{AD_ACCOUNT_ID}/campaigns")
    assert not path_matches("/act_{AD_ACCOUNT_ID}/campaigns", "/123/campaigns")  # no act_ prefix
    assert not path_matches("/act_{AD_ACCOUNT_ID}/campaigns", "/act_/campaigns")  # empty value
    assert path_matches("/accounts/{id}:listSubaccounts", "/accounts/7:listSubaccounts")
    assert path_matches("/orders/{id}.json", "/orders/42.json")
    assert path_matches("/rates/{from}-{to}", "/rates/EUR-USD")
    assert not path_matches("/rates/{from}-{to}", "/rates/EURUSD")


def test_the_more_literal_template_wins() -> None:
    """GET /accounts/{v}/accounts/7:listSubaccounts matched the plain account endpoint too."""
    plain, verb = "/accounts/{accountsId}", "/accounts/{accountsId}:listSubaccounts"
    call = "/accounts/7:listSubaccounts"
    assert path_matches(plain, call)  # {accountsId} takes "7:listSubaccounts"
    assert path_matches(verb, call)
    assert specificity(verb) > specificity(plain)
    assert specificity("/act_{id}/campaigns") > specificity("/{id}/campaigns")
