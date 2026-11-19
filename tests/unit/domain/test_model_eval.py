"""Model gold parsing and scoring: correct / wrong / invented / missed / not available, the
conversion checks, alignment by name, alias and path, and the release gate."""

import pytest

from plume.domain.models.canonical_model import parse_draft
from plume.domain.models.model_eval import (
    CONVERSION_MISSING,
    CONVERSION_OK,
    CONVERSION_WRONG,
    CORRECT,
    INVENTED,
    MISSED,
    NOT_AVAILABLE_CORRECT,
    WRONG,
    ModelGatePolicy,
    score,
)
from plume.domain.models.model_gold import GoldFormatError, parse_gold

FIELDS = {
    "shop": {"total_price", "currency", "financial_status", "line_items.sku", "line_items.quantity",
             "subtotal_price", "id"},
    "woo": {"total", "status", "line_items.sku", "line_items.quantity", "id", "currency"},
}  # fmt: skip


def exists(api: str, path: str) -> bool:
    names = FIELDS[api]
    return any(n == path or n.endswith("." + path) for n in names)


GOLD = {
    "schema": "plume.model-gold.v1",
    "concept": "Order",
    "group": "1",
    "apis": ["shop", "woo", "mirakl"],
    "fields": [
        {"name": "total", "aliases": ["grand_total"], "type": "money", "required": True,
         "apis": {"shop": {"paths": ["total_price"],
                           "conversion": {"kind": "money-decimal-string"}},
                  "woo": {"paths": ["total"], "conversion": {"kind": "money-decimal-string"}}}},
        {"name": "status", "apis": {
            "shop": {"paths": ["financial_status"],
                     "conversion": {"kind": "enum", "map": {"paid": "PAID", "pending": "PENDING"}}},
            "woo": {"paths": ["status"],
                    "conversion": {"kind": "enum", "map": {"completed": "PAID"}}}}},
        {"name": "order_number", "apis": {"shop": {"notAvailable": True},
                                          "woo": {"notAvailable": True}}},
        {"name": "id", "apis": {"shop": {"paths": ["id"]}, "woo": {"paths": ["id"]}}},
        {"name": "lines", "type": "array", "apis": {}, "fields": [
            {"name": "sku", "apis": {"shop": {"paths": ["line_items[].sku", "line_items.sku"]},
                                     "woo": {"paths": ["line_items.sku"]}}},
            {"name": "quantity", "apis": {"shop": {"paths": ["line_items.quantity"]}}}]},
    ],
}  # fmt: skip


def _src(path: str, transform: str | None = None) -> dict[str, object]:
    src: dict[str, object] = {"paths": [path], "evidence": [{"doc_id": "model:x", "quote": "q"}]}
    if transform:
        src["transform"] = transform
    return src


DRAFT = parse_draft(
    {
        "name": "Order",
        "description": "an order",
        "fields": [
            {
                "name": "grand_total",
                "type": "money",
                "description": "d",
                "sources": {
                    "shop": _src("total_price"),  # right, no transform: conversion missing
                    "woo": _src("total", "cents / 100"),
                },
            },  # right path, minor-unit transform: wrong
            {
                "name": "status",
                "type": "string",
                "description": "d",
                "sources": {
                    "shop": _src("financial_status", "paid -> PAID, pending -> OPEN"),  # enum wrong
                    "woo": _src("currency"),
                },
            },  # an existing but wrong field
            {
                "name": "order_number",
                "type": "string",
                "description": "d",
                "sources": {
                    "shop": _src("subtotal_price"),  # gold: not available; an existing field: wrong
                    "woo": _src("number"),
                },
            },  # not a field of woo: invented
            {
                "name": "identifier",
                "type": "string",
                "description": "d",
                "sources": {"shop": _src("id", "as is")},
            },  # matched by path, not by name; woo: missed
            {
                "name": "lines",
                "type": "array",
                "description": "d",
                "fields": [
                    {
                        "name": "sku",
                        "type": "string",
                        "description": "d",
                        "sources": {"shop": _src("line_items.sku"), "woo": _src("line_items.sku")},
                    }
                ],
            },
            {
                "name": "notes",
                "type": "string",
                "description": "d",
                "sources": {"woo": _src("customer_note")},
            },  # not in gold, invented
        ],
    }
)


def _cells(result: object) -> dict[tuple[str, str], tuple[str, str | None]]:
    return {(c.field, c.api): (c.result, c.conversion) for c in result.cells}  # type: ignore[attr-defined]


def test_every_class_and_the_metrics() -> None:
    [gold] = parse_gold(GOLD, "order-1.json")
    result = score(DRAFT, gold, ("shop", "woo"), exists)
    assert result.apis == ("shop", "woo")  # mirakl is not in the model: not scored
    assert _cells(result) == {
        ("total", "shop"): (CORRECT, CONVERSION_MISSING),
        ("total", "woo"): (CORRECT, CONVERSION_WRONG),
        ("status", "shop"): (CORRECT, CONVERSION_WRONG),
        ("status", "woo"): (WRONG, None),
        ("order_number", "shop"): (WRONG, None),
        ("order_number", "woo"): (INVENTED, None),
        ("id", "shop"): (CORRECT, None),
        ("id", "woo"): (MISSED, None),
        ("lines.sku", "shop"): (CORRECT, None),
        ("lines.sku", "woo"): (CORRECT, None),
        ("lines.quantity", "shop"): (MISSED, None),
    }
    assert [c.model_field for c in result.extra_invented] == ["notes"]
    assert result.invented == 2
    assert result.counts[CORRECT] == 6
    assert result.precision == round(6 / (6 + 2 + 1), 4)
    assert result.recall == round(6 / 9, 4)  # 9 cells expect a path
    assert result.conversion_missing_rate == round(1 / 6, 4)
    assert result.conversion_wrong_rate == round(2 / 6, 4)
    wrong_enum = next(c for c in result.cells if (c.field, c.api) == ("status", "shop"))
    assert wrong_enum.detail == "pending -> OPEN (gold PENDING)"


def test_not_available_and_conversion_ok() -> None:
    [gold] = parse_gold(GOLD)
    draft = parse_draft({"name": "Order", "description": "d", "fields": [
        {"name": "total", "type": "money", "description": "d", "sources": {
            "shop": _src("total_price", "parse decimal string")}},
    ]})  # fmt: skip
    cells = _cells(score(draft, gold, ("shop",), exists))
    assert cells[("total", "shop")] == (CORRECT, CONVERSION_OK)
    assert cells[("order_number", "shop")] == (NOT_AVAILABLE_CORRECT, None)


def test_gate() -> None:
    [gold] = parse_gold(GOLD)
    result = score(DRAFT, gold, ("shop", "woo"), exists)
    [invented] = ModelGatePolicy().failures(result)
    assert (invented.message, invented.overridable) == (
        "2 invented mapping(s): notes, order_number",
        False,
    )
    clean = parse_draft({"name": "Order", "description": "d", "fields": [
        {"name": "total", "type": "money", "description": "d", "sources": {
            "shop": _src("total_price"), "woo": _src("total")}}]})  # fmt: skip
    ok = score(clean, gold, ("shop", "woo"), exists)
    assert ModelGatePolicy().failures(ok) == []  # no threshold yet: invented = 0 is enough
    [low] = ModelGatePolicy(min_recall=0.5).failures(ok)
    assert (low.message, low.overridable) == (f"recall {ok.recall} below 0.5", True)


def test_held_out_and_sets() -> None:
    models = parse_gold(
        {"schema": "plume.model-gold.v1", "apis": ["shop"], "heldOut": True, "models": [
            {"concept": "Order", "fields": [{"name": "id", "apis": {"shop": {"paths": ["id"]}}}]},
            {"concept": "Customer",
             "fields": [{"name": "id", "apis": {"shop": {"paths": ["id"]}}}]},
        ]},
        "set-1.json",
    )  # fmt: skip
    assert [(m.concept, m.held_out, m.apis) for m in models] == [
        ("Order", True, ("shop",)),
        ("Customer", True, ("shop",)),
    ]


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"schema": "x"}, "schema must be"),
        ({**GOLD, "apis": []}, "apis is empty"),
        ({**GOLD, "fields": [{"name": "a", "apis": {"nope": {"paths": ["a"]}}}]},
         "not in the gold"),
        ({**GOLD, "fields": [{"name": "a", "apis": {"shop": {}}}]}, "either paths or notAvailable"),
        ({**GOLD, "fields": [{"name": "a", "apis": {"shop": {"paths": ["a"],
          "conversion": {"kind": "magic"}}}}]}, "is not one of"),
    ],
)  # fmt: skip
def test_bad_gold_is_refused(raw: dict[str, object], message: str) -> None:
    with pytest.raises(GoldFormatError, match=message):
        parse_gold(raw)


def _stated(conversion: dict[str, object] | None) -> object:
    src = _src("total_price")
    if conversion is not None:
        src["conversion"] = conversion
    return parse_draft({"name": "Order", "description": "d", "fields": [
        {"name": "total", "type": "money", "description": "d", "sources": {"shop": src}},
        {"name": "status", "type": "string", "description": "d", "sources": {
            "shop": {**_src("financial_status"), "conversion": conversion}
            if conversion and conversion.get("kind") == "enum" else _src("financial_status")}},
    ]})  # fmt: skip


@pytest.mark.parametrize(
    ("conversion", "total", "status"),
    [
        ({"kind": "money-decimal"}, CONVERSION_OK, CONVERSION_MISSING),  # decimal ~ decimal-string
        ({"kind": "money-minor"}, CONVERSION_WRONG, CONVERSION_MISSING),
        ({"kind": "datetime", "format": "UTC"}, CONVERSION_WRONG, CONVERSION_MISSING),
        ({"kind": "enum", "map": {"paid": "PAID", "pending": "OPEN"}}, CONVERSION_WRONG,
         CONVERSION_WRONG),
        ({"kind": "enum", "map": {"paid": "PAID"}}, CONVERSION_WRONG, CONVERSION_OK),
    ],
)  # fmt: skip
def test_a_stated_conversion_is_checked_against_gold(
    conversion: dict[str, object], total: str, status: str
) -> None:
    [gold] = parse_gold(GOLD)
    cells = _cells(score(_stated(conversion), gold, ("shop",), exists))  # type: ignore[arg-type]
    assert cells[("total", "shop")] == (CORRECT, total)
    assert cells[("status", "shop")] == (CORRECT, status)


def test_gold_other_accepts_any_stated_kind() -> None:
    cell = {"paths": ["total_price"], "conversion": {"kind": "other", "note": "see docs"}}
    gold = {**GOLD, "fields": [{"name": "total", "apis": {"shop": cell}}]}
    [model] = parse_gold(gold)
    cells = _cells(score(_stated({"kind": "split"}), model, ("shop",), exists))  # type: ignore[arg-type]
    assert cells[("total", "shop")] == (CORRECT, CONVERSION_OK)


def test_draft_conversion_parse_and_hash_stability() -> None:
    from plume.domain.models.canonical_model import DraftFormatError  # noqa: PLC0415
    from plume.domain.models.snapshot import draft_json  # noqa: PLC0415

    with pytest.raises(DraftFormatError, match="is not one of"):
        _stated({"kind": "magic"})
    plain = draft_json(_stated(None))  # type: ignore[arg-type]
    assert "conversion" not in plain["fields"][0]["sources"]["shop"]  # old models keep their ids
    stated = draft_json(_stated({"kind": "meta-entry", "format": "_tracking_number"}))  # type: ignore[arg-type]
    assert stated["fields"][0]["sources"]["shop"]["conversion"] == {
        "kind": "meta-entry",
        "format": "_tracking_number",
    }
