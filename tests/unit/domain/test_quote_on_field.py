"""A citation's quote must be about the mapped field (M7), and quotes match across HTML markup
(M10)."""

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
