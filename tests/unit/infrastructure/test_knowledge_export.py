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
