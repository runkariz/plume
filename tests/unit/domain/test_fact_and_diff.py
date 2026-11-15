from plume.domain.knowledge.diff import diff_items
from plume.domain.knowledge.document import Document, DocumentKind, FieldLocation, FieldSpec
from plume.domain.knowledge.fact import FactKind, facts_of
from plume.domain.shared.hashing import content_hash


def _endpoint(complete: bool = True) -> Document:
    return Document(
        doc_id="endpoint:GET~/orders",
        kind=DocumentKind.ENDPOINT,
        title="List orders",
        text="t",
        source_url="https://docs/orders",
        resource="Order",
        method="GET",
        path="/orders",
        complete=complete,
        fields=(
            FieldSpec(
                "limit", FieldLocation.QUERY, "integer", False, "Page size", "p#/properties/limit"
            ),
            FieldSpec("orders[].id", FieldLocation.RESPONSE, "string", True, None, "r#/x"),
        ),
        scopes=("read_orders",),
    )


def test_endpoint_field_and_scope_facts_with_evidence() -> None:
    facts = facts_of(_endpoint())
    kinds = sorted((f.kind.value, f.name) for f in facts)
    assert kinds == [
        ("endpoint", "GET /orders"),
        ("field", "limit"),
        ("field", "orders[].id"),
        ("scope", "read_orders"),
    ]
    limit = next(f for f in facts if f.name == "limit")
    assert limit.location is FieldLocation.QUERY
    assert limit.evidence.doc_id == "endpoint:GET~/orders"
    assert limit.evidence.anchor == "p#/properties/limit"
    assert limit.evidence.quote == "Page size"
    assert limit.complete


def test_completeness_flows_to_facts() -> None:
    assert all(not f.complete for f in facts_of(_endpoint(complete=False)))


def test_fact_ids_are_stable_and_unique() -> None:
    a, b = facts_of(_endpoint()), facts_of(_endpoint())
    assert [f.fact_id for f in a] == [f.fact_id for f in b]
    assert len({f.fact_id for f in a}) == len(a)
    assert {f.kind for f in a} == {FactKind.ENDPOINT, FactKind.FIELD, FactKind.SCOPE}


def test_diff_items() -> None:
    a, b, c = content_hash("a"), content_hash("b"), content_hash("c")
    diff = diff_items({"x": a, "y": b, "z": c}, {"x": a, "y": c, "w": a})
    assert diff.added == ("w",)
    assert diff.changed == ("y",)
    assert diff.removed == ("z",)
    assert diff.unchanged == 1
    assert not diff.is_empty
    assert diff_items({"x": a}, {"x": a}).is_empty
