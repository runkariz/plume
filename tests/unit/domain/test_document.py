import pytest

from plume.domain.knowledge.document import (
    Document,
    DocumentKind,
    endpoint_doc_id,
    normalize_endpoint_path,
    slug_doc_id,
)
from plume.domain.shared.errors import InvalidIdentifierError


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/admin/api/2026-10/products.json", "/admin/api/{version}/products.json"),
        ("/admin/api/latest/products.json", "/admin/api/{version}/products.json"),
        ("/api/v1/orders", "/api/{version}/orders"),
        ("/api/v2.1/orders?x=1", "/api/{version}/orders"),
        ("api/orders/{order_id}", "/api/orders/{order_id}"),
        ("/api/custom-7/orders", "/api/{version}/orders"),
    ],
)
def test_version_segment_is_stripped(path: str, expected: str) -> None:
    assert normalize_endpoint_path(path, known_versions=["custom-7"]) == expected


def test_latest_and_dated_paths_give_the_same_id() -> None:
    a = endpoint_doc_id("get", normalize_endpoint_path("/admin/api/latest/products.json"))
    b = endpoint_doc_id("GET", normalize_endpoint_path("/admin/api/2026-10/products.json"))
    assert a == b == "endpoint:GET~/admin/api/{version}/products.json"


def test_unknown_method_is_refused() -> None:
    with pytest.raises(InvalidIdentifierError):
        endpoint_doc_id("FETCH", "/x")


def test_document_id_must_match_kind() -> None:
    with pytest.raises(InvalidIdentifierError):
        Document(doc_id="model:x", kind=DocumentKind.GUIDE, title="X", text="t")
    with pytest.raises(ValueError, match="no title"):
        Document(
            doc_id=slug_doc_id(DocumentKind.GUIDE, "x"), kind=DocumentKind.GUIDE, title=" ", text=""
        )


def test_content_hash_covers_title_text_and_source() -> None:
    base = Document(doc_id="guide:x", kind=DocumentKind.GUIDE, title="X", text="t")
    assert (
        base.content_hash
        == Document(doc_id="guide:x", kind=DocumentKind.GUIDE, title="X", text="t").content_hash
    )
    assert (
        base.content_hash
        != Document(doc_id="guide:x", kind=DocumentKind.GUIDE, title="Y", text="t").content_hash
    )
    assert (
        base.content_hash
        != Document(
            doc_id="guide:x", kind=DocumentKind.GUIDE, title="X", text="t", source_url="u"
        ).content_hash
    )


def test_a_generic_alias_after_the_version_is_a_literal_segment() -> None:
    """WooCommerce GET /wp-json/wc/v3/data/currencies/current is not .../currencies/{version}
    (it collided with .../currencies/{currency}); Metro .../export/latest likewise."""
    from plume.domain.knowledge.document import normalize_endpoint_path as norm  # noqa: PLC0415

    assert norm("/wp-json/wc/v3/data/currencies/current") == (
        "/wp-json/wc/{version}/data/currencies/current"
    )
    assert norm("/openapi/v1/product-list/export/latest") == (
        "/openapi/{version}/product-list/export/latest"
    )
    assert norm("/admin/api/latest/products.json") == "/admin/api/{version}/products.json"
    assert norm("/api/current/orders") == "/api/{version}/orders"  # the alias IS the version
