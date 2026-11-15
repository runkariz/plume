import json
import shutil
from pathlib import Path

import pytest

from plume.application.errors import SourcePackageError
from plume.domain.knowledge.document import DocumentKind, FieldLocation
from plume.infrastructure.sources.stream_package import StreamPackageSource

source = StreamPackageSource()


def test_reads_the_test_catalog(packages: Path) -> None:
    pkg = source.load(str(packages / "test-catalog"))
    assert pkg.api.api_id.value == "test-catalog-api"
    assert pkg.api.category is not None
    assert pkg.api.category.key == "e-commerce"
    assert pkg.contract_version == "1.2"
    kinds = sorted(d.kind.value for d in pkg.documents)
    assert kinds == ["app", "auth", "endpoint", "endpoint", "guide", "model", "model", "model"]
    orders = next(d for d in pkg.documents if d.doc_id == "endpoint:GET~/api/{version}/orders")
    assert orders.title == "List orders"
    assert orders.method == "GET"
    assert {f.location for f in orders.fields} >= {FieldLocation.QUERY, FieldLocation.RESPONSE}
    assert "## Errors" in orders.text
    assert pkg.warnings == ()


def test_shopify_ids_strip_the_version(packages: Path) -> None:
    pkg = source.load(str(packages / "shopify-mini"))
    ids = {d.doc_id for d in pkg.documents if d.kind is DocumentKind.ENDPOINT}
    assert "endpoint:PUT~/admin/api/{version}/products/{product_id}.json" in ids
    assert "endpoint:GET~/admin/api/{version}/products.json" in ids
    assert not any("2026-10" in i or "latest" in i for i in ids)
    put = next(d for d in pkg.documents if d.doc_id.startswith("endpoint:PUT"))
    assert put.source_id == "put-admin-api-latest-products-product-id-json-2026-10"
    assert any(f.location is FieldLocation.PATH and f.name == "product_id" for f in put.fields)
    assert any(
        f.location is FieldLocation.BODY and f.name.startswith("product.") for f in put.fields
    )


def test_required_scopes_and_auth_scopes(packages: Path) -> None:
    pkg = source.load(str(packages / "shopify-mini"))
    assigned = next(d for d in pkg.documents if "assigned_fulfillment_orders" in d.doc_id)
    assert assigned.scopes == ("read_assigned_fulfillment_orders",)
    auth = next(d for d in pkg.documents if d.kind is DocumentKind.AUTH)
    assert "read_products" in auth.scopes


def test_incomplete_model_is_flagged(packages: Path) -> None:
    pkg = source.load(str(packages / "shopify-mini"))
    customer = next(d for d in pkg.documents if d.doc_id == "model:customer")
    assert not customer.complete
    assert "incomplete" in customer.text
    assert next(d for d in pkg.documents if d.doc_id == "model:address").complete


def test_hash_is_stable_and_content_sensitive(packages: Path, tmp_path: Path) -> None:
    a = source.load(str(packages / "test-catalog")).package_hash
    copy = tmp_path / "copy"
    shutil.copytree(packages / "test-catalog", copy)
    assert source.load(str(copy)).package_hash == a
    assert source.load(str(copy / "connector")).package_hash == a
    model = copy / "connector" / "models" / "order.schema.json"
    data = json.loads(model.read_text())
    data["description"] = "changed"
    model.write_text(json.dumps(data))
    assert source.load(str(copy)).package_hash != a


def test_knowledge_export_pages_are_guides(packages: Path, tmp_path: Path) -> None:
    copy = tmp_path / "pkg"
    shutil.copytree(packages / "test-catalog", copy)
    export = copy / "knowledge-export" / "resources"
    export.mkdir(parents=True)
    (export / "orders.md").write_text(
        "---\nsource_url: https://example.test/orders\n---\n# Orders\n\nOrders can be cancelled "
        "only before they ship.\n",
        encoding="utf-8",
    )
    pkg = source.load(str(copy))
    page = next(d for d in pkg.documents if d.doc_id == "guide:export-resources-orders")
    assert page.title == "Orders"
    assert page.source_url == "https://example.test/orders"
    assert "cancelled only before" in " ".join(page.text.split())


def test_missing_app_json_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(SourcePackageError, match=r"app\.json"):
        source.load(str(tmp_path))


def test_unsupported_contract_major(packages: Path, tmp_path: Path) -> None:
    copy = tmp_path / "pkg"
    shutil.copytree(packages / "test-catalog", copy)
    (copy / "connector" / "package.json").write_text('{"schemaVersion": "2.0"}')
    with pytest.raises(SourcePackageError, match="schemaVersion"):
        source.load(str(copy))


def test_bad_json_is_reported(packages: Path, tmp_path: Path) -> None:
    copy = tmp_path / "pkg"
    shutil.copytree(packages / "test-catalog", copy)
    (copy / "connector" / "models" / "order.schema.json").write_text("{nope")
    with pytest.raises(SourcePackageError, match=r"order\.schema\.json"):
        source.load(str(copy))


def test_bundled_model_titles_get_display_names(packages: Path) -> None:
    pkg = source.load(str(packages / "mirakl-mini"))
    models = {d.doc_id: d for d in pkg.documents if d.kind is DocumentKind.MODEL}
    billing = models["model:a01-response-200-billinginfo"]
    assert billing.title == "Billing Info"
    assert billing.source_id == "A01_Response_200_BillingInfo"
    assert billing.text.startswith("# Billing Info (model)\n\nSource title: A01_Response_200_")
    root = models["model:a01-response-200"]
    assert root.title == "A01 response 200"
    assert root.resource is None
    shipping = models["model:dr12-response-200-data-shippingto-address"]
    assert shipping.title == "Shipping To / Address"
    same = models["model:a02-request-address"], models["model:a02-response-200-updated-address"]
    assert same[0].shape == same[1].shape
    assert len({m.shape for m in models.values()}) == 11


def test_shape_ignores_wording() -> None:
    from plume.infrastructure.sources.stream_package import shape_hash  # noqa: PLC0415

    a = {
        "type": "object",
        "title": "A",
        "properties": {"x": {"type": "string", "description": "d"}},
    }
    b = {
        "type": "object",
        "title": "B",
        "x-note": 1,
        "properties": {"x": {"type": "string", "examples": ["e"]}},
    }
    c = {"type": "object", "properties": {"x": {"type": "integer"}}}
    assert shape_hash(a) == shape_hash(b) != shape_hash(c)
