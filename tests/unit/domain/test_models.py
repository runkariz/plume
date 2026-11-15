import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from plume.domain.models.canonical_model import DraftFormatError, parse_draft
from plume.domain.models.snapshot import ModelSnapshot, PinnedInput, draft_json, snapshot_id_for
from plume.domain.models.validation import Oracle, quote_in, validate

DRAFTS = Path(__file__).resolve().parents[2] / "fixtures" / "drafts"
APIS = frozenset({"test-catalog-api", "second-catalog-api"})


def _good() -> dict[str, object]:
    return json.loads((DRAFTS / "catalog-order-good.json").read_text())  # type: ignore[no-any-return]


def test_parse_and_round_trip() -> None:
    draft = parse_draft(_good())
    assert draft.name == "Order"
    assert [f.name for f in draft.fields][:2] == ["id", "number"]
    total = draft.fields[2]
    assert total.source("second-catalog-api").derived  # type: ignore[union-attr]
    assert not draft.fields[0].source("test-catalog-api").derived  # type: ignore[union-attr]
    assert parse_draft(draft_json(draft)) == draft
    assert draft.open_questions[0].options == ("gross", "net")


@pytest.mark.parametrize(
    ("raw", "match"),
    [
        ([], "JSON object"),
        ({"fields": []}, "name"),
        ({"name": "X", "fields": []}, "must not be empty"),
        ({"name": "X", "fields": [{"name": "a b", "type": "t"}]}, "valid field name"),
        (
            {"name": "X", "fields": [{"name": "a", "type": "t"}, {"name": "a", "type": "t"}]},
            "duplicate",
        ),
        ({"name": "X", "fields": [{"name": "a", "type": "t", "sources": []}]}, "keyed by api"),
        (
            {
                "name": "X",
                "fields": [{"name": "a", "type": "t", "sources": {"x": {"evidence": [1]}}}],
            },
            "must be an object",
        ),
    ],
)
def test_parse_errors(raw: object, match: str) -> None:
    with pytest.raises(DraftFormatError, match=match):
        parse_draft(raw)


def test_quote_matching_ignores_case_whitespace_and_backticks() -> None:
    assert quote_in("total  MONETARY amount", "- `total` (string): Total monetary amount billed")
    assert not quote_in("total net amount", "Total monetary amount billed")


def _oracle(
    docs: dict[tuple[str, str], str], fields: set[tuple[str, str]], endpoints: set[tuple[str, str]]
) -> Oracle:
    return Oracle(
        doc_text=lambda api, doc: docs.get((api, doc)),
        field_exists=lambda api, path: (api, path) in fields,
        endpoint_exists=lambda api, call: (api, call) in endpoints,
    )


def test_validation_codes() -> None:
    raw = {
        "name": "M",
        "fields": [
            {
                "name": "a",
                "type": "t",
                "sources": {
                    "x": {"paths": ["p"], "evidence": []},
                    "y": {
                        "paths": ["nope"],
                        "fetch": "GET /z",
                        "evidence": [
                            {"doc_id": "d", "quote": "not there"},
                            {"doc_id": "gone", "quote": "q"},
                        ],
                    },
                    "z": {"paths": ["p"], "evidence": [{"doc_id": "d", "quote": "q"}]},
                },
            },
            {"name": "b", "type": "t", "sources": {}},
        ],
    }
    oracle = _oracle({("y", "d"): "some text"}, {("x", "p")}, set())
    issues = validate(parse_draft(raw), frozenset({"x", "y"}), oracle)
    codes = sorted((i.code, i.field, i.api) for i in issues)
    assert codes == [
        ("API_NOT_IN_SESSION", "a", "z"),
        ("DOC_NOT_FOUND", "a", "y"),
        ("ENDPOINT_NOT_FOUND", "a", "y"),
        ("FIELD_NOT_FOUND", "a", "y"),
        ("MISSING_CITATION", "a", "x"),
        ("NO_SOURCES", "b", None),
        ("QUOTE_NOT_FOUND", "a", "y"),
    ]


def test_snapshot_support_coverage_and_id() -> None:
    draft = parse_draft(_good())
    inputs = (PinnedInput("test-catalog-api", "b-1"), PinnedInput("second-catalog-api", "b-2"))
    snap = ModelSnapshot(
        "m-x", "s-1", "Order", inputs, draft, datetime(2026, 11, 15, tzinfo=UTC), 10
    )
    assert snap.support("second-catalog-api")["total"] == "derived"
    assert snap.support("test-catalog-api")["id"] == "supported"
    assert snap.coverage() == {"test-catalog-api": (5, 5), "second-catalog-api": (5, 5)}
    a = snapshot_id_for(inputs, "Order", draft)
    assert a == snapshot_id_for(tuple(reversed(inputs)), "Order", draft)
    assert a != snapshot_id_for((PinnedInput("test-catalog-api", "b-9"), inputs[1]), "Order", draft)
    assert a.startswith("m-")
