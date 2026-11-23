# ruff: noqa: E501
"""oneOf / anyOf members are flattened (Sendcloud POST /shipments: to_address ->
$defs.ToAddress -> oneOf [Address Object] gave only "to_address"); allOf is not walked."""

from typing import Any

from plume.domain.knowledge.document import FieldLocation
from plume.domain.knowledge.fact import facts_of
from plume.infrastructure.sources.stream_package import _RefScope, _walk_fields

ADDRESS = {
    "title": "Address Object",
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Name of the recipient."},
        "company_name": {"type": "string"},
        "address_line_1": {"type": "string"},
        "house_number": {"type": "string"},
        "postal_code": {"type": "string"},
        "city": {"type": "string", "description": "City of the recipient."},
        "country_code": {"type": "string"},
        "po_box": {"type": "string"},
    },
}
BODY: dict[str, Any] = {  # the exact shape of Sendcloud's POST /shipments body
    "type": "object",
    "properties": {
        "to_address": {"$ref": "#/$defs/ToAddress", "description": "The recipient's address."},
    },
    "$defs": {
        "ToAddress": {
            "title": "To Address",
            "type": "object",
            "required": ["name", "address_line_1", "postal_code", "city", "country_code"],
            "oneOf": [ADDRESS],
        }
    },
}


def _fields(schema: dict[str, Any]) -> dict[str, Any]:
    walked = _walk_fields(
        schema, FieldLocation.BODY, "body.json#", scope=_RefScope(schema, "body.json")
    )
    return {f.name: f for f in walked}


def test_a_single_alternative_gives_plain_fields_with_the_parents_required() -> None:
    fields = _fields(BODY)
    assert {"to_address", "to_address.city", "to_address.po_box", "to_address.name"} <= set(fields)
    city = fields["to_address.city"]
    assert city.required is True  # ToAddress.required applies
    assert city.description == "City of the recipient."  # no alternative mark: only one
    assert city.pointer == "body.json#/$defs/ToAddress/oneOf/0/properties/city"
    assert fields["to_address.po_box"].required is False
    assert fields["to_address.company_name"].required is False


def test_several_alternatives_are_a_union_each_field_once_and_marked() -> None:
    parcel_shop = {"title": "Service Point", "type": "object", "required": ["city"],
                   "properties": {"service_point_id": {"type": "integer"},
                                  "city": {"type": "string", "description": "City of the point."}}}  # fmt: skip
    body = {**BODY, "$defs": {"ToAddress": {
        "type": "object", "required": ["name"], "anyOf": [ADDRESS, parcel_shop]}}}  # fmt: skip
    fields = _fields(body)
    assert fields["to_address.city"].description == "City of the recipient."  # in both: no mark
    assert fields["to_address.city"].required is False  # only the alternatives require it
    assert fields["to_address.name"].required is True  # the parent requires it
    assert fields["to_address.po_box"].description.endswith(
        "(only in the alternative(s): Address Object)"
    )
    assert fields["to_address.service_point_id"].description == (
        "(only in the alternative(s): Service Point)"
    )
    from plume.domain.knowledge.document import Document, DocumentKind  # noqa: PLC0415

    doc = Document(doc_id="endpoint:POST~/shipments", kind=DocumentKind.ENDPOINT, title="t",
                   text="t", fields=tuple(_walk_fields(body, FieldLocation.BODY, "b#",
                                                       scope=_RefScope(body, "b"))))  # fmt: skip
    ids = [f.fact_id for f in facts_of(doc)]
    assert len(ids) == len(set(ids))  # one fact per field


def test_a_member_repeating_a_parent_property_adds_nothing() -> None:
    schema = {"type": "object", "properties": {"city": {"type": "string", "description": "own"}},
              "oneOf": [{"properties": {"city": {"type": "string", "description": "member"}}}]}  # fmt: skip
    fields = _fields(schema)
    assert list(fields) == ["city"]
    assert fields["city"].description == "own"


def test_all_of_is_not_walked() -> None:
    schema = {"allOf": [{"type": "object", "properties": {"id": {"type": "string"}}}]}
    assert _fields(schema) == {}
