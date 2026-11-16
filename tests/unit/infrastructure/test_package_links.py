"""Links a package states between documents: knowledge units -> endpoints (Core's endpointId /
endpointIds) and requiredScopes -> auth schemes. Packages without them load unchanged."""

import json
import shutil
from pathlib import Path

from plume.application.reader import links
from plume.domain.knowledge.document import Document, DocumentKind
from plume.infrastructure.sources.stream_package import StreamPackageSource

source = StreamPackageSource()
PRODUCTS = "endpoint:GET~/admin/api/{version}/products.json"
CREATE = "endpoint:POST~/admin/api/{version}/products.json"
FULFILLMENT = "endpoint:GET~/admin/api/{version}/assigned_fulfillment_orders.json"


def _linked_package(packages: Path, tmp_path: Path) -> Path:
    dst = tmp_path / "shopify-linked"
    shutil.copytree(packages / "shopify-mini", dst)
    knowledge = dst / "connector" / "knowledge"
    unit = knowledge / "rate-limit-admin-rest-rest-admin-api-request-rate-limits.json"
    data = json.loads(unit.read_text())
    data["endpointIds"] = ["get-admin-api-latest-products-json", "no-such-endpoint"]
    data["endpointId"] = "post-admin-api-latest-products-json"
    unit.write_text(json.dumps(data))
    single = knowledge / "versioning.json"
    data = json.loads(single.read_text())
    data["endpointId"] = "get-admin-api-latest-products-json"
    single.write_text(json.dumps(data))
    request = dst / "connector/endpoints/get-admin-api-latest-products-json/request.json"
    req = json.loads(request.read_text())
    req["requiredScopes"] = [{"scopes": ["read_products"]}]  # no authId: every scheme
    request.write_text(json.dumps(req))
    return dst


def _doc(docs: tuple[Document, ...], doc_id: str) -> Document:
    return next(d for d in docs if d.doc_id == doc_id)


def test_units_link_their_endpoints_both_ways(packages: Path, tmp_path: Path) -> None:
    pkg = source.load(str(_linked_package(packages, tmp_path)))
    unit = _doc(pkg.documents, "guide:rate-limit-admin-rest-rest-admin-api-request-rate-limits")
    assert links.linked_endpoints(unit) == [CREATE, PRODUCTS]  # endpointId first, then the list
    assert links.linked_guides(_doc(pkg.documents, PRODUCTS)) == [
        "guide:rate-limit-admin-rest-rest-admin-api-request-rate-limits",
        "guide:versioning",
    ]
    assert links.linked_guides(_doc(pkg.documents, CREATE)) == [
        "guide:rate-limit-admin-rest-rest-admin-api-request-rate-limits"
    ]
    assert any("unknown endpoint no-such-endpoint" in w for w in pkg.warnings)


def test_required_scopes_reach_their_scheme(packages: Path, tmp_path: Path) -> None:
    pkg = source.load(str(_linked_package(packages, tmp_path)))
    auth = next(d for d in pkg.documents if d.kind is DocumentKind.AUTH)
    assert links.scope_endpoints(auth) == {
        "read_assigned_fulfillment_orders": [FULFILLMENT],
        "read_products": [PRODUCTS],
    }
    assert links.required_scopes(_doc(pkg.documents, PRODUCTS)) == [
        {"authId": None, "scopes": ["read_products"]}
    ]


def test_without_links_documents_keep_their_text_and_have_no_links(packages: Path) -> None:
    plain = source.load(str(packages / "woo-mini"))
    for doc in plain.documents:
        assert links.linked_endpoints(doc) == []
        assert links.linked_guides(doc) == []
        assert links.scope_endpoints(doc) == {}
    shop = source.load(str(packages / "shopify-mini"))
    unit = _doc(shop.documents, "guide:versioning")
    assert unit.raw is None
    assert not any("unknown endpoint" in w for w in shop.warnings)


def test_links_do_not_change_embedded_text(packages: Path, tmp_path: Path) -> None:
    plain = {d.doc_id: d.text for d in source.load(str(packages / "shopify-mini")).documents}
    linked = source.load(str(_linked_package(packages, tmp_path))).documents
    changed = [d.doc_id for d in linked if plain.get(d.doc_id) != d.text]
    assert changed == [PRODUCTS]  # only the endpoint whose requiredScopes the test added
