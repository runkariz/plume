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


def _woo_with_export_links(packages: Path, tmp_path: Path) -> Path:
    dst = tmp_path / "woo-linked"
    shutil.copytree(packages / "woo-mini", dst)
    unit = dst / "connector" / "knowledge" / "authentication.json"
    data = json.loads(unit.read_text())
    data["endpointId"] = "get-wp-json-wc-v3-coupons"  # the unit's own (text) link
    unit.write_text(json.dumps(data))
    export = dst / "knowledge-export"
    (export / "unit-links.json").write_text(
        json.dumps(
            {
                "schema": "plume.unit-links.v1",
                "links": [
                    {
                        "unitId": "authentication",
                        "endpointIds": ["get-wp-json-wc-v3-coupons", "post-wp-json-wc-v3-coupons"],
                        "linkBasis": "page",
                    },
                    {"unitId": "hub", "endpointIds": [], "linkBasis": "page"},  # hub: nothing
                    {"unitId": "gone", "endpointIds": ["post-wp-json-wc-v3-coupons"]},
                ],
            }
        )
    )
    rules = json.loads((export / "rules.json").read_text())
    for r in rules["rules"]:
        if r["id"] == "r-d1bb813122":  # resource rule, now linked to one endpoint
            r["endpointIds"] = ["put-wp-json-wc-v3-coupons-id"]
    (export / "rules.json").write_text(json.dumps(rules))
    return dst


WOO = "endpoint:{m}~/wp-json/wc/{{version}}/coupons{p}"


def test_unit_links_file_adds_page_links_after_the_units_own(
    packages: Path, tmp_path: Path
) -> None:
    pkg = source.load(str(_woo_with_export_links(packages, tmp_path)))
    unit = _doc(pkg.documents, "guide:authentication")
    get, post = WOO.format(m="GET", p=""), WOO.format(m="POST", p="")
    assert links.linked_endpoints(unit) == [get, post]
    assert links.endpoint_links(unit) == [
        {"endpointId": get, "linkBasis": "text"},  # the connector's link wins
        {"endpointId": post, "linkBasis": "page"},
    ]
    assert links.linked_guides(_doc(pkg.documents, post)) == ["guide:authentication"]
    assert any("unit-links.json names 1 unknown unit(s), e.g. gone" in w for w in pkg.warnings)


def test_rules_go_to_their_endpoint_ids_before_the_resource_fallback(
    packages: Path, tmp_path: Path
) -> None:
    pkg = source.load(str(_woo_with_export_links(packages, tmp_path)))
    put = _doc(pkg.documents, WOO.format(m="PUT", p="/{id}"))
    get_one = _doc(pkg.documents, WOO.format(m="GET", p="/{id}"))
    linked = "any other coupons already applied will be removed"
    assert linked in put.text.split("## Rules for this resource")[0]
    assert linked not in get_one.text  # no longer spread to every coupon endpoint
    other = "applying this coupon will enable free shipping"
    assert other in get_one.text  # unlinked resource rules keep the fallback
    page = next(d for d in pkg.documents if d.doc_id.startswith("guide:page-"))
    assert linked in page.text  # a resource rule stays in its page guide


def test_without_unit_links_file_the_units_keep_text_links(packages: Path) -> None:
    pkg = source.load(str(packages / "woo-mini"))
    assert all(not links.endpoint_links(d) for d in pkg.documents)
