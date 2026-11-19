"""find_fact for endpoints: "/path" (any method), "METHOD /path" with other path parameter
names or a concrete version, and never a false complete absence (bol-retailer F9)."""

from pathlib import Path

import pytest

from tests.fakes.stack import FakeStack


@pytest.fixture
def stack(packages: Path) -> FakeStack:
    s = FakeStack()
    s.load(str(packages / "shopify-mini"))
    return s


def _find(stack: FakeStack, name: str, kind: str | None = "endpoint"):  # type: ignore[no-untyped-def]
    return stack.find_fact().execute("shopify", name, kind=kind)


def test_a_path_without_method_finds_every_method(stack: FakeStack) -> None:
    r = _find(stack, "/admin/api/{version}/products/{id}.json")
    assert r.found is True
    assert sorted(m.name.split(" ")[0] for m in r.matches) == ["DELETE", "GET", "PUT"]
    assert _find(stack, "/admin/api/2026-10/products.json", kind=None).found is True


def test_other_parameter_names_and_a_full_url(stack: FakeStack) -> None:
    r = _find(stack, "GET /admin/api/{version}/fulfillment_orders/{id}.json")
    assert [m.name for m in r.matches] == [
        "GET /admin/api/{version}/fulfillment_orders/{fulfillment_order_id}.json"
    ]
    url = "GET https://shop.myshopify.com/admin/api/2026-10/products.json?limit=5"
    assert _find(stack, url).found is True


def test_another_method_is_not_a_complete_absence(stack: FakeStack) -> None:
    r = _find(stack, "PATCH /admin/api/{version}/products.json")
    assert r.found is False
    assert r.complete is False
    assert any("is documented for GET, POST, not PATCH" in x for x in r.reasons)


def test_a_non_endpoint_form_never_proves_absence(stack: FakeStack) -> None:
    r = _find(stack, "products list")
    assert (r.found, r.complete) == (False, False)
    assert any("not an endpoint form" in x for x in r.reasons)


def test_an_absent_path_adds_no_doubt_of_its_own(stack: FakeStack) -> None:
    r = _find(stack, "GET /admin/api/{version}/nope.json")
    assert r.found is False
    assert not any("endpoint form" in x or "documented for" in x for x in r.reasons)
    # (shopify-mini flags model:customer incomplete: that alone keeps complete false here)
    assert r.reasons == ("model:customer is flagged incomplete by its source",)
