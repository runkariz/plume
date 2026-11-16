"""Field value constraints (enum, minimum, maximum, default, format, pattern) are carried
verbatim from the package schemas into fields, facts and the document text."""

import json
import shutil
from pathlib import Path

from plume.domain.knowledge.document import constraint_text, constraints_of
from tests.fakes.stack import FakeStack

API = "test-catalog-api"


def test_constraints_of_and_text() -> None:
    assert constraints_of({"type": "string", "description": "x"}) is None
    c = constraints_of({"type": "integer", "maximum": 100, "format": "int32", "default": 10})
    assert json.loads(c or "") == {"default": 10, "format": "int32", "maximum": 100}
    assert constraint_text(c) == "max 100; default 10; format int32"
    arr = constraints_of({"type": "array", "items": {"enum": ["a", "b"]}})
    assert constraint_text(arr) == "one of: a, b"


def test_constraints_reach_fields_facts_and_text(packages: Path, tmp_path: Path) -> None:
    copy = tmp_path / "pkg"
    shutil.copytree(packages / "test-catalog", copy)
    path = copy / "connector" / "models" / "order.schema.json"
    schema = json.loads(path.read_text())
    schema["properties"]["currency"].update({"enum": ["EUR", "USD"], "pattern": "^[A-Z]{3}$"})
    path.write_text(json.dumps(schema))
    s = FakeStack()
    s.load(str(copy))
    doc = s.get_document().execute(API, "model:order").document
    currency = next(f for f in doc.fields if f.name == "currency")
    assert currency.constraint_dict == {"enum": ["EUR", "USD"], "pattern": "^[A-Z]{3}$"}
    assert "[one of: EUR, USD; pattern ^[A-Z]{3}$]" in doc.text
    match = next(m for m in s.find_fact().execute(API, "currency").matches
                 if m.owner_id == "model:order")  # fmt: skip
    assert match.constraints == {"enum": ["EUR", "USD"], "pattern": "^[A-Z]{3}$"}


def test_real_path_only_when_the_operation_fixes_its_version() -> None:
    from plume.domain.knowledge.document import real_path  # noqa: PLC0415

    amazon = {"url": "{{app_env.servers.api}}/vendor/orders/v1/purchaseOrders", "apiVersion": "v1"}
    assert real_path(amazon, "/vendor/orders/{version}/purchaseOrders") == (
        "/vendor/orders/v1/purchaseOrders"
    )
    shopify = {"url": "{{app_env.servers.api}}/admin/api/2026-10/orders.json",
               "apiVersion": "2026-10"}  # fmt: skip
    assert real_path(shopify, "/admin/api/{version}/orders.json", rolling=True) is None
    latest = {"url": "{{app_env.servers.api}}/admin/api/latest/orders.json"}
    assert real_path(latest, "/admin/api/{version}/orders.json") is None  # no apiVersion
    mirakl = {"url": "{{app_env.servers.api}}/api/products", "apiVersion": "v1"}
    assert real_path(mirakl, "/api/products") is None  # no version segment


def _with_limits(packages: Path, dest: Path, limit: int, cost: int) -> Path:
    shutil.copytree(packages / "test-catalog", dest)
    app_path = dest / "connector" / "app.json"
    app = json.loads(app_path.read_text())
    app["rateLimits"] = [{"scope": "operation", "group": "orders", "limit": limit,
                          "windowSeconds": 1, "algorithm": "token-bucket",
                          "notes": "Burst 20."}]  # fmt: skip
    app_path.write_text(json.dumps(app))
    for req_path in (dest / "connector" / "endpoints").glob("*/request.json"):
        req = json.loads(req_path.read_text())
        if "orders" in req["url"]:
            req["rateLimitCost"] = {"bucket": "orders", "cost": cost}
            req_path.write_text(json.dumps(req))
    return dest


def test_rate_limits_on_documents_facts_api_and_release_notes(
    packages: Path, tmp_path: Path
) -> None:
    s = FakeStack()
    s.load(str(_with_limits(packages, tmp_path / "a", 10, 1)))
    doc_id = "endpoint:GET~/api/{version}/orders"
    doc = s.get_document().execute(API, doc_id).document
    assert json.loads(doc.rate_limit or "") == {
        "bucket": "orders", "cost": 1,
        "group": {"scope": "operation", "group": "orders", "limit": 10, "windowSeconds": 1,
                  "algorithm": "token-bucket", "notes": "Burst 20."},
    }  # fmt: skip
    assert "Rate limit: bucket orders, cost 1; 10 per 1 s (token-bucket); Burst 20." in doc.text
    fact = s.find_fact().execute(API, "rate limit", owner=doc_id).matches[0]
    assert fact.citation.quote == "bucket orders, cost 1; 10 per 1 s (token-bucket); Burst 20."
    assert s.sections().rate_limits(API)[0]["group"] == "orders"
    b = s.load(str(_with_limits(packages, tmp_path / "b", 5, 2)))  # lower rate, higher cost
    notes = s.release_notes().get(API, b, full=True)
    items = notes["items"] + [i for g in notes["report"] for i in g["items"]]
    rl = {(i["subject"]["fieldPath"], i["breaking"]) for i in items if i["kind"] == "rate_limit"}
    assert ("rateLimits.orders.limit", True) in rl
    assert ("rateLimit.cost", True) in rl


def test_packages_without_rate_limits_are_fine(packages: Path) -> None:
    s = FakeStack()
    s.load(str(packages / "test-catalog"))
    assert s.sections().rate_limits(API) == []
    doc = s.get_document().execute(API, "endpoint:GET~/api/{version}/orders").document
    assert doc.rate_limit is None


def test_pseudo_concepts_are_dropped_and_labels_tidied() -> None:
    from plume.application.models.concepts import concept_label, tidy_concept  # noqa: PLC0415

    known = {"product", "collection", "collect", "ship", "order"}
    words = {"listing"}
    for noise in ("Get Purchase Orders Response", "Order List", "Shipment Success",
                  "Updated Order", "Top Sellers Report", "Send Invite", "Previous",
                  "Account Activation Url", "Productid"):  # fmt: skip
        assert tidy_concept(noise, known, words) is None, noise
    assert tidy_concept("Productlisting", known, words) == "Product Listing"
    assert tidy_concept("Collection", known, words) == "Collection"
    assert tidy_concept("Shipment", known, words) == "Shipment"
    assert concept_label("customer_customer_address") == "Customer Address"


def test_a_per_operation_model_brings_its_endpoint_first() -> None:
    from plume.application.reader.ranking import lift_operation_endpoints  # noqa: PLC0415

    owners = {"model:a02-response-200-updated": "endpoint:PUT~/api/account",
              "model:a02-response-200": "endpoint:PUT~/api/account"}  # fmt: skip
    ranked = ["model:a02-response-200-updated", "guide:x", "model:a02-response-200", "doc:y",
              "endpoint:PUT~/api/account", "doc:z"]  # fmt: skip
    out = lift_operation_endpoints(ranked, 4, owners.get)
    assert out[:4] == ["endpoint:PUT~/api/account", "model:a02-response-200-updated", "guide:x",
                       "model:a02-response-200"]  # fmt: skip
    assert sorted(out) == sorted(ranked)  # same ids
    assert lift_operation_endpoints(["a", "b"], 2, lambda d: None) == ["a", "b"]
