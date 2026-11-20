"""A citation's quote must be about the mapped field (M7), and quotes match across HTML markup
(M10)."""

from typing import Any

from plume.domain.models.canonical_model import parse_draft
from plume.domain.models.validation import Oracle, quote_in, validate

DOCS = {
    "model:order": "# Order\n- `id` (integer): Unique identifier.\n- `total` (string): Grand "
    "total of the order.",
    "guide:orders": "Every order has an id; the total includes taxes.",
}
FIELDS = {("model:order", "id"): ("Unique identifier.", "- `id` (integer): Unique identifier."),
          ("model:order", "total"): ("Grand total of the order.",)}  # fmt: skip


def _oracle() -> Oracle:
    return Oracle(
        doc_text=lambda _api, doc: DOCS.get(doc),
        field_exists=lambda _api, path: path in {"id", "total"},
        endpoint_exists=lambda _api, _call: True,
        field_texts=lambda _api, doc, path: FIELDS.get((doc, path)),
    )


def _draft(path: str, doc: str, quote: str) -> object:
    source = {"paths": [path], "evidence": [{"doc_id": doc, "quote": quote}]}
    field = {"name": "x", "type": "string", "description": "d", "sources": {"woo": source}}
    return parse_draft({"name": "Order", "description": "d", "fields": [field]})


def _codes(path: str, doc: str, quote: str) -> list[str]:
    return [i.code for i in validate(_draft(path, doc, quote), frozenset({"woo"}), _oracle())]  # type: ignore[arg-type]


def test_a_quote_about_another_field_is_refused() -> None:
    assert _codes("id", "model:order", "Grand total of the order.") == ["QUOTE_NOT_ON_FIELD"]
    assert _codes("id", "model:order", "Unique identifier.") == []
    assert _codes("id", "model:order", "`id` (integer): Unique identifier") == []  # its line


def test_prose_must_name_the_field() -> None:
    assert _codes("total", "guide:orders", "the total includes taxes") == []
    assert _codes("id", "guide:orders", "the total includes taxes") == ["QUOTE_NOT_ON_FIELD"]


def test_an_unknown_path_is_field_not_found_only() -> None:
    assert _codes("nope", "model:order", "Unique identifier.") == ["FIELD_NOT_FOUND"]


def test_quotes_match_across_html() -> None:
    doc = "Order state.<br>One of: <ul><li>SHIPPING</li><li>SHIPPED</li></ul> &amp; more"
    assert quote_in("Order state. One of: SHIPPING SHIPPED & more", doc)
    assert quote_in(
        "Order state.<br>One of: <ul><li>SHIPPING</li>", "Order state. One of: SHIPPING"
    )


JUNK = {("model:order", "status"): ("Important!", "- `status` (string): Important!")}


def _junk_oracle() -> Oracle:
    texts = {**FIELDS, **JUNK}
    return Oracle(
        doc_text=lambda _api, doc: DOCS.get(doc, "") + "\n- `status` (string): Important!",
        field_exists=lambda _api, path: path in {"id", "total", "status"},
        endpoint_exists=lambda _api, _call: True,
        field_texts=lambda _api, doc, path: texts.get((doc, path)),
    )


def _evidence(path: str, evidence: dict[str, str]) -> list[str]:
    field = {"name": "x", "type": "string", "description": "d",
             "sources": {"woo": {"paths": [path], "evidence": [evidence]}}}  # fmt: skip
    draft = parse_draft({"name": "Order", "description": "d", "fields": [field]})
    return [i.code for i in validate(draft, frozenset({"woo"}), _junk_oracle())]


def test_a_quote_must_carry_information() -> None:
    assert _evidence("status", {"doc_id": "model:order", "quote": "Important!"}) == [
        "QUOTE_TOO_SHORT"
    ]
    assert _evidence("total", {"doc_id": "model:order", "quote": "Grand total of the order."}) == []
    assert _evidence("id", {"doc_id": "model:order", "quote": "Unique identifier."}) == []  # whole


def test_no_quote_only_where_the_field_has_nothing_to_quote() -> None:
    junk = {"doc_id": "model:order", "noQuote": "the description is only 'Important!'"}
    assert _evidence("status", junk) == []
    has_text = {"doc_id": "model:order", "noQuote": "lazy"}
    assert _evidence("total", has_text) == ["NO_QUOTE_NOT_ALLOWED"]
    elsewhere = {"doc_id": "guide:orders", "noQuote": "not listed there"}
    assert _evidence("status", elsewhere) == ["NO_QUOTE_NOT_ALLOWED"]


ONE_WORD = {
    ("model:order", "quantity"): ("quantity", "- `lineItems[].quantity` (integer): quantity",
                                  "- `offer.quantity` (integer): Units of the offer in stock."),
}  # fmt: skip


def _one_word_oracle() -> Oracle:
    return Oracle(
        doc_text=lambda _api, _doc: "- `lineItems[].quantity` (integer): quantity",
        field_exists=lambda _api, path: path == "quantity",
        endpoint_exists=lambda _api, _call: True,
        field_texts=lambda _api, doc, path: ONE_WORD.get((doc, path)),
    )


def test_a_one_word_description_can_be_cited_with_no_quote() -> None:
    """set-g3: "quantity" was too short to quote AND refused as noQuote: a dead end."""

    def codes(evidence: dict[str, Any]) -> list[str]:
        source = {"paths": ["quantity"], "evidence": [evidence]}
        field = {"name": "qty", "type": "integer", "description": "d", "sources": {"woo": source}}
        draft = parse_draft({"name": "Line", "description": "d", "fields": [field]})
        return [i.code for i in validate(draft, frozenset({"woo"}), _one_word_oracle())]

    assert codes({"doc_id": "model:order", "quote": "quantity"}) == ["QUOTE_TOO_SHORT"]
    assert codes({"doc_id": "model:order", "noQuote": "the description is one word"}) == []


def test_no_quote_must_be_a_reason() -> None:
    import pytest  # noqa: PLC0415

    from plume.domain.models.canonical_model import DraftFormatError  # noqa: PLC0415

    source = {"paths": ["quantity"], "evidence": [{"doc_id": "m", "noQuote": True}]}
    field = {"name": "q", "type": "integer", "description": "d", "sources": {"woo": source}}
    draft = {"name": "L", "description": "d", "fields": [field]}
    with pytest.raises(DraftFormatError, match="noQuote must be a string"):
        parse_draft(draft)


def test_enum_and_format_lines_are_not_sentences() -> None:
    """set-g1: Mirakl order_state "Order's state" + 'Enum: "STAGING", ...' refused noQuote."""
    from plume.domain.models.validation import usable_sentence  # noqa: PLC0415

    enum_line = 'Enum: "STAGING", "WAITING_ACCEPTANCE", "WAITING_DEBIT", "SHIPPING", "SHIPPED"'
    assert usable_sentence(["Order's state\n" + enum_line]) is None
    assert usable_sentence(["Order's state. " + enum_line]) is None
    assert usable_sentence(["Format: date-time (ISO 8601, e.g. 2024-01-01T00:00:00Z)"]) is None
    assert (
        usable_sentence(["- `order_state` (string): Order's state, one of the order states"])
        is None
    )
    long = "The state of the order in the Mirakl workflow.\n" + enum_line
    assert usable_sentence([long]) == "The state of the order in the Mirakl workflow."
