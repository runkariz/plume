"""The tester's markdown "Expected mapping (gold)" table -> a model gold file."""

import pytest

from plume.domain.models.model_gold import parse_gold
from plume.infrastructure.models.gold_markdown import GoldImportError, import_markdown

REPORT = """# Order (+ order line) across shopify, woocommerce, mirakl, tested 2026-11-20
## Summary
fields 4; correct 3
## Expected mapping (gold)
| canonical field | shopify | woocommerce | mirakl | conversion |
|---|---|---|---|---|
| total | `total_price` | `total` | not available | money-decimal-string: string amount |
| status | `financial_status` | `status` | `order_state` | shopify: enum paid/open; mirakl: enum |
| lines[].sku | `line_items[].sku` | `line_items[].sku` + `line_items[].variation_id` | — | |
| id | `id` | `id` | `order_id` | id-type: number vs string |
"""


def test_the_table_becomes_gold() -> None:
    gold = import_markdown(REPORT, group="1")
    assert (gold["concept"], gold["apis"], gold["group"]) == (
        "Order",
        ["shopify", "woocommerce", "mirakl"],
        "1",
    )
    by_name = {f["name"]: f for f in gold["fields"]}
    total = by_name["total"]["apis"]
    assert total["shopify"] == {
        "paths": ["total_price"],
        "conversion": {"kind": "money-decimal-string", "note": "string amount"},
    }
    assert total["mirakl"] == {"notAvailable": True}  # no conversion on a missing field
    status = by_name["status"]["apis"]
    assert status["shopify"]["conversion"] == {"kind": "enum", "note": "paid/open"}
    assert "conversion" not in status["woocommerce"]
    assert status["mirakl"]["conversion"] == {"kind": "enum"}
    sku = by_name["lines"]["fields"][0]
    assert sku["name"] == "sku"
    assert sku["apis"]["woocommerce"]["paths"] == ["line_items[].sku", "line_items[].variation_id"]
    assert "mirakl" not in sku["apis"]  # "—": not judged
    [model] = parse_gold(gold)
    assert [p for p, _, _ in model.walk()] == ["total", "status", "lines", "lines.sku", "id"]


def test_held_out_flag_and_errors() -> None:
    assert import_markdown(REPORT, held_out=True)["heldOut"] is True
    with pytest.raises(GoldImportError, match="title"):
        import_markdown("no title")
    with pytest.raises(GoldImportError, match="Expected mapping"):
        import_markdown("# Order across shopify, tested x\n")
