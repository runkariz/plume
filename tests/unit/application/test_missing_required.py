# ruff: noqa: E501
"""check_call reports the documented required parameters a call did not pass (missingRequired),
per place; nested ones only when their parent was passed; never path or auth headers."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListBuilds
from plume.application.reader.use_cases import CheckCall
from plume.domain.knowledge.document import FieldLocation
from plume.domain.knowledge.fact import FactKind
from plume.interfaces.http.app import HttpDependencies, create_app
from plume.interfaces.payloads import check_call_payload
from tests.fakes.stack import FakeStack

# Google Merchant products/v1 productInputs:insert (package b, vendor-stated required flags)
B: Any = None  # the stub's facts ignore the build
GOOGLE = [
    ("path", "accountsId"), ("header", "Authorization"), ("query", "dataSource"),
    ("body", "contentLanguage"), ("body", "offerId"), ("body", "feedLabel"),
    ("body", "productAttributes.externalSellerId"),
    ("body", "productAttributes.productWidth.unit"),
    ("body", "productAttributes.productWidth.value"),
    ("body", "productAttributes.relatedProducts[].id"),
]  # fmt: skip


def _google() -> CheckCall:
    facts = [SimpleNamespace(kind=FactKind.FIELD, required=True, location=FieldLocation(loc),
                             name=name) for loc, name in GOOGLE]  # fmt: skip
    facts.append(SimpleNamespace(kind=FactKind.FIELD, required=False,
                                 location=FieldLocation.BODY, name="productAttributes.title"))  # fmt: skip
    stub: Any = SimpleNamespace(for_owner=lambda _b, _o: facts)
    return CheckCall(B, stub, B, None)


def test_google_merchant_insert() -> None:
    call = _google()
    bare = call._missing_required(B, "o", [])
    assert bare == (
        ("query", ("dataSource",)),
        ("body", ("contentLanguage", "feedLabel", "offerId")),
    )
    done = call._missing_required(B, "o", ["dataSource", "contentLanguage", "offerId", "feedLabel"])
    assert done == ()


def test_a_nested_required_field_only_when_its_parent_is_passed() -> None:
    call = _google()
    passed = ["dataSource", "contentLanguage", "offerId", "feedLabel", "productAttributes.title",
              "productAttributes.productWidth.unit"]  # fmt: skip
    missing = dict(call._missing_required(B, "o", passed))
    # productAttributes and productWidth were passed (by a child); relatedProducts was not
    assert missing == {"body": ("productAttributes.externalSellerId",
                                "productAttributes.productWidth.value")}  # fmt: skip


@pytest.fixture
def stack(packages: Path) -> FakeStack:
    s = FakeStack()
    for p in ("test-catalog", "mirakl-mini"):
        s.load(str(packages / p))
    return s


def test_mirakl_accept_and_auth_headers_through_check_call(stack: FakeStack) -> None:
    cc = stack.check_call()
    accept = "/api/orders/O1/accept"
    bare = cc.execute("mirakl", "PUT", accept)
    assert bare.verdict == "documented"  # the verdict does not change
    assert bare.missing_required == (("body", ("order_lines",)),)
    assert bare.note == "documented, but these required fields are missing: body: order_lines"
    some = cc.execute("mirakl", "PUT", accept, [], None, [], ["order_lines[].id"])
    assert some.missing_required == (("body", ("order_lines[].accepted",)),)
    full = cc.execute("mirakl", "PUT", accept, [], None, [], ["order_lines[].id",
                                                             "order_lines[].accepted"])  # fmt: skip
    assert (full.missing_required, full.note) == ((), None)
    # X-Catalog-Key is required, but the API's auth scheme fills it
    assert cc.execute("test-catalog-api", "GET", "/api/v1/orders").missing_required == ()
    assert check_call_payload(bare)["missingRequired"] == {"body": ["order_lines"]}


def test_the_http_answer_carries_it(stack: FakeStack) -> None:
    client = TestClient(create_app(HttpDependencies(
        overviews=stack.overviews, browse=stack.browse, search=stack.search,
        get_document=stack.get_document, find_fact=stack.find_fact, check_call=stack.check_call,
        list_builds=lambda: ListBuilds(stack.builds, stack.tags),
        diff_builds=lambda: DiffBuilds(stack.builds), resolver=stack.resolver,
        rate_limit_per_minute=0,
    )))  # fmt: skip
    r = client.post(
        "/v1/apis/mirakl/check-call", json={"method": "PUT", "path": "/api/orders/O1/accept"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["missingRequired"] == {"body": ["order_lines"]}
    assert r.json()["verdict"] == "documented"
