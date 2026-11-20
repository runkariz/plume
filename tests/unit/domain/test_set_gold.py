# ruff: noqa: E501
"""Set gold: the tester's relation table becomes plume.set-gold.v1, and a set's relations score
against it (design: kind + cardinality; per API: a source path or the fetch endpoint)."""

from typing import Any

from plume.domain.models.model_set import parse_set_draft
from plume.domain.models.set_gold import parse_set_gold, score_set
from plume.infrastructure.models.gold_markdown import import_set_markdown, is_set_report

REPORT = """# Model set Order + Order line + Customer across magento, bigcommerce (group 4), tested x

## Expected mapping (gold)
Members reuse the concept golds. Relations:

| relation | from | to | cardinality | key (per API: path → path) |
|---|---|---|---|---|
| order-lines | Order | Order line | embedded 1:n, field `lines` | magento `items` → `items[].item_id`; bigcommerce `products` (link to `GET /orders/{order_id}/products`) → `id` |
| order-customer | Order | Customer | reference n:1, `customer_id` → `Customer.id` | magento `customer_id` → `id`; bigcommerce n/a |

| member field | note |
|---|---|
| Order.lines | an array |
"""


def test_the_relation_table_becomes_a_set_gold() -> None:
    assert is_set_report(REPORT)
    gold = import_set_markdown(REPORT, group="4")
    assert (gold["members"], gold["apis"]) == (["Order", "Order line", "Customer"],
                                               ["magento", "bigcommerce"])  # fmt: skip
    lines, customer = gold["relations"]
    assert (lines["kind"], lines["cardinality"], lines["field"]) == ("embedded", "1:n", "lines")
    assert lines["apis"]["bigcommerce"] == {
        "paths": ["products"], "fetch": "GET /orders/{order_id}/products",
    }  # fmt: skip
    assert (customer["kind"], customer["cardinality"], customer["key"]) == (
        "reference",
        "n:1",
        "id",
    )
    assert customer["apis"]["bigcommerce"] == {"notAvailable": True}


def _source(as_: str, paths: list[str], fetch: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"as": as_, "paths": paths,
                           "evidence": [{"doc_id": "d", "quote": "the order lines of an order"}]}  # fmt: skip
    return {**out, "fetch": fetch} if fetch else out


def test_a_sets_relations_score_against_the_gold() -> None:
    gold = parse_set_gold(import_set_markdown(REPORT), "set-g4.json")
    draft = parse_set_draft({
        "name": "Orders", "description": "d",
        "members": [{"concept": "Order", "model_id": "m1"}, {"concept": "Order line", "model_id": "m2"},
                    {"concept": "Customer", "model_id": "m3"}, {"concept": "Address", "model_id": "m4"}],
        "relations": [
            {"id": "r1", "from": "Order", "to": "Order line", "kind": "embedded", "cardinality": "1:n",
             "embed": {"field": "lines"}, "confirmed": True,
             "sources": {"magento": _source("nested", ["items[]"]),
                         "bigcommerce": _source("sub_resource", [],
                                                "GET /{version}/orders/{id}/products")}},
            {"id": "r2", "from": "Order", "to": "Customer", "kind": "embedded", "cardinality": "1:1",
             "embed": {"field": "customer"}, "confirmed": True,
             "sources": {"magento": _source("nested", ["customer"]),
                         "bigcommerce": _source("nested", ["customer"])}},
            {"id": "r3", "from": "Customer", "to": "Address", "kind": "embedded", "cardinality": "1:n",
             "embed": {"field": "addresses"}, "confirmed": True,
             "sources": {"magento": _source("nested", ["addresses"])}},
        ],
    })  # fmt: skip
    result = score_set(draft, gold)
    lines, customer = result.relations
    assert (lines.verdict, lines.sources) == ("correct", {"magento": "correct",
                                                          "bigcommerce": "correct"})  # fmt: skip
    assert customer.verdict == "wrong"  # embedded 1:1 vs the gold's reference n:1
    assert customer.sources == {"magento": "wrong", "bigcommerce": "invented"}  # n/a in gold
    assert result.invented == ("r3",)
    assert result.counts == {"correct": 1, "wrong": 1, "invented": 1}


def test_set_golds_live_beside_model_golds(tmp_path: Any) -> None:
    import json  # noqa: PLC0415

    from plume.infrastructure.models.gold_files import JsonModelGold  # noqa: PLC0415

    (tmp_path / "set-g4.json").write_text(json.dumps(import_set_markdown(REPORT)))
    source = JsonModelGold((tmp_path,))
    assert source.all() == ()  # not a model gold
    [gold] = source.sets()
    assert [r.id for r in gold.relations] == ["order-lines", "order-customer"]
    assert source.load_sets("set-g4.json") == (gold,)


def test_scorer_fixes_from_the_group_1_check() -> None:
    """Group 1 (tester: 7/7 correct) scored correct 7, wrong 1, missed 1, invented 1: two
    Order -> Address relations matched one gold row; path forms (data[].order_id vs order_id,
    line_items vs line_items[].id) read as wrong; alternative rows counted as required."""
    from plume.domain.models.set_gold import _same_path  # noqa: PLC0415

    assert _same_path("fulfillments[].order_id", "order_id")
    assert _same_path("data[].shipment_lines[].order_line_id", "shipment_lines[].order_line_id")
    assert _same_path("line_items", "line_items[].id")
    assert not _same_path("order_id", "customer_id")
    gold = parse_set_gold({"schema": "plume.set-gold.v1", "members": ["Order", "Address", "Customer"],
        "apis": ["a"], "relations": [
        {"id": "order-shipping-address", "from": "Order", "to": "Address", "kind": "embedded",
         "cardinality": "1:1", "field": "shipping_address", "apis": {"a": {"paths": ["shipping"]}}},
        {"id": "order-billing-address", "from": "Order", "to": "Address", "kind": "embedded",
         "cardinality": "1:1", "field": "billing_address", "apis": {"a": {"paths": ["billing"]}}},
        {"id": "order-customer", "from": "Order", "to": "Customer", "kind": "reference",
         "cardinality": "n:1", "apis": {"a": {"paths": ["customer_id"]}}},
        {"id": "order-customer (embedded alternative)", "from": "Order", "to": "Customer",
         "kind": "embedded", "cardinality": "1:1", "apis": {"a": {"paths": ["customer"]}}},
    ]})  # fmt: skip
    draft = parse_set_draft({
        "name": "S", "description": "d",
        "members": [{"concept": c, "model_id": c} for c in ("Order", "Address", "Customer")],
        "relations": [
            {"id": "order-billing-address", "from": "Order", "to": "Address", "kind": "embedded",
             "cardinality": "1:1", "embed": {"field": "billing_address"}, "confirmed": True,
             "sources": {"a": _source("nested", ["billing"])}},
            {"id": "order-shipping-address", "from": "Order", "to": "Address", "kind": "embedded",
             "cardinality": "1:1", "embed": {"field": "shipping_address"}, "confirmed": True,
             "sources": {"a": _source("nested", ["shipping"])}},
            {"id": "order-customer", "from": "Order", "to": "Customer", "kind": "embedded",
             "cardinality": "1:1", "embed": {"field": "customer"}, "confirmed": True,
             "sources": {"a": _source("nested", ["customer"])}},
        ],
    })  # fmt: skip
    result = score_set(draft, gold)
    assert result.counts == {"correct": 3, "invented": 0}  # the embedded alternative is chosen
    assert all(v == "correct" for r in result.relations for v in r.sources.values())
