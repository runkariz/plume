import json
import shutil
from pathlib import Path

from plume.domain.knowledge.document import DocumentKind
from plume.infrastructure.sources import knowledge_export
from plume.infrastructure.sources.gold_file import JsonGoldSource
from plume.infrastructure.sources.gold_import import import_gold
from plume.infrastructure.sources.stream_package import StreamPackageSource, display_name

source = StreamPackageSource()


def test_strip_code_keeps_prose_and_drops_payloads() -> None:
    text = (
        "Delete a coupon This API helps you delete a coupon. curl -X DELETE "
        'https://example.com/wp-json/wc/v3/coupons/719?force=true { "id": 719, "code": "10off", '
        '"amount": "5.00" } Available parameters force Use true whether to permanently delete.'
    )
    out = knowledge_export.strip_code(text)
    assert out.startswith("Delete a coupon This API helps you delete a coupon.")
    assert "permanently delete." in out
    assert '"code":' not in out
    assert "…" in out


def test_page_sections_follow_the_item_anchors(packages: Path) -> None:
    root = packages / "woo-mini" / "knowledge-export"
    assert knowledge_export.detect(root)
    export = knowledge_export.load(root)
    assert export.complete
    page = export.pages[0]
    assert page.title == "Coupons"
    anchor, text = page.sections["delete-wp-json-wc-v3-coupons-id"]
    assert anchor == "#delete-a-coupon"
    assert text.startswith("Delete a coupon")
    assert "Batch update coupons" not in text  # the next item's section starts there
    assert "Coupon properties" in page.intro
    assert export.gold_path is not None


def test_endpoints_are_enriched_and_pages_become_guides(packages: Path) -> None:
    pkg = source.load(str(packages / "woo-mini"))
    assert pkg.warnings == ()
    delete = next(d for d in pkg.documents if d.source_id == "delete-wp-json-wc-v3-coupons-id")
    assert "## From the documentation page" in delete.text
    assert "update the order's coupon lines" in delete.text
    assert "## Rules" in delete.text
    assert delete.anchor == "#delete-a-coupon"
    guides = [d for d in pkg.documents if d.doc_id.startswith("guide:page-")]
    assert len(guides) == 1
    assert guides[0].title == "Coupons"
    assert (
        guides[0].source_url == "https://developer.woocommerce.com/docs/apis/rest-api/v3/coupons/"
    )
    assert pkg.api.name == "WooCommerce"


def test_without_export_nothing_changes(packages: Path, tmp_path: Path) -> None:
    shutil.copytree(packages / "woo-mini" / "connector", tmp_path / "connector")
    plain = source.load(str(tmp_path))
    full = source.load(str(packages / "woo-mini"))
    assert len(full.documents) == len(plain.documents) + 1  # one page guide
    assert plain.package_hash != full.package_hash
    delete = next(d for d in plain.documents if d.source_id == "delete-wp-json-wc-v3-coupons-id")
    assert "## From the documentation page" not in delete.text


def test_gold_import(packages: Path, tmp_path: Path) -> None:
    out = tmp_path / "woocommerce.json"
    count, skipped = import_gold(str(packages / "woo-mini"), str(out))
    assert (count, skipped) == (3, [])
    gold, _ = JsonGoldSource().load(str(out))
    assert gold.api == "woocommerce"
    expected = {d for q in gold.questions for d in q.expect_docs}
    assert "endpoint:DELETE~/wp-json/wc/{version}/coupons/{id}" in expected
    raw = json.loads(out.read_text())
    assert raw["version"] == "stream-1"


def test_display_name() -> None:
    assert display_name("woocommerce", ["Manage WooCommerce store resources"]) == "WooCommerce"
    assert display_name("Test Catalog API", []) == "Test Catalog API"
    assert display_name("acme", ["nothing here"]) == "Acme"
    assert display_name("shop", ["a Shopify store"]) == "Shop"  # whole-word match only
    pkg = source.load(str(Path(__file__).resolve().parents[2] / "fixtures/packages/test-catalog"))
    assert pkg.api.name == "Test Catalog API"
    assert DocumentKind.APP in {d.kind for d in pkg.documents}


def _unsplit_package(packages: Path, tmp_path: Path, with_rule: bool) -> Path:
    """woo-mini whose page has no locatable sections (headings without markers)."""
    dst = tmp_path / "unsplit"
    shutil.copytree(packages / "woo-mini", dst)
    page = next((dst / "knowledge-export" / "pages").glob("*.md"))
    page.write_text(page.read_text(encoding="utf-8").replace("\u200b", ""), encoding="utf-8")
    rules_file = dst / "knowledge-export" / "rules.json"
    rules = json.loads(rules_file.read_text())
    url = "https://developer.woocommerce.com/docs/apis/rest-api/v3/coupons/"
    rules["rules"] = (
        [
            {
                "id": "r-x",
                "scope": "resource",
                "type": "constraint",
                "text": "Codes are unique.",
                "quote": "Coupon code.",
                "sourceUrl": url,
                "confidence": 0.9,
            }
        ]
        if with_rule
        else []
    )
    rules_file.write_text(json.dumps(rules))
    return dst


def test_unsplit_page_keeps_only_rules_and_an_index(packages: Path, tmp_path: Path) -> None:
    pkg = source.load(str(_unsplit_package(packages, tmp_path, with_rule=True)))
    guide = next(d for d in pkg.documents if d.doc_id.startswith("guide:page-"))
    assert "(documentation page: rules)" in guide.text
    assert "## Endpoints" in guide.text
    assert "Codes are unique." in guide.text
    assert "Coupon properties" not in guide.text  # the page text is not indexed
    delete = next(d for d in pkg.documents if d.source_id == "delete-wp-json-wc-v3-coupons-id")
    assert "## From the documentation page" not in delete.text


def test_unsplit_page_without_rules_adds_no_guide(packages: Path, tmp_path: Path) -> None:
    pkg = source.load(str(_unsplit_package(packages, tmp_path / "b", with_rule=False)))
    assert not any(d.doc_id.startswith("guide:page-") for d in pkg.documents)


def test_resource_rules_reach_the_pages_endpoints_of_that_resource(
    packages: Path, tmp_path: Path
) -> None:
    """Zalando's "the Logistic Centers API requires the .../read scope" is scoped to a resource,
    not an endpoint: it also goes into the page's endpoints of that resource, so a question
    about it finds the endpoint and not only the page guide."""
    dst = tmp_path / "resource-rules"
    shutil.copytree(packages / "woo-mini", dst)
    rules_file = dst / "knowledge-export" / "rules.json"
    rules = json.loads(rules_file.read_text())
    url = "https://developer.woocommerce.com/docs/apis/rest-api/v3/coupons/"
    rules["rules"].extend(
        [
            {
                "id": "r-scope",
                "scope": "resource",
                "type": "precondition",
                "text": "Coupon calls need the coupons/write scope.",
                "quote": "requires the coupons/write scope",
                "sourceUrl": url,
                "confidence": 0.95,
                "resource": "coupon",
            },
            {
                "id": "r-other",
                "scope": "resource",
                "type": "precondition",
                "text": "Reports are cached for an hour.",
                "quote": "cached for an hour",
                "sourceUrl": url,
                "confidence": 0.95,
                "resource": "Report",
            },
        ]
    )
    rules_file.write_text(json.dumps(rules))
    pkg = source.load(str(dst))
    coupons = [
        d for d in pkg.documents if d.kind is DocumentKind.ENDPOINT and d.resource == "Coupon"
    ]
    assert coupons
    for doc in coupons:
        assert "## Rules for this resource" in doc.text
        assert "coupons/write scope" in doc.text
        assert "cached for an hour" not in doc.text  # another resource
    guide = next(d for d in pkg.documents if d.doc_id.startswith("guide:page-"))
    assert "coupons/write scope" in guide.text  # the page guide keeps it
