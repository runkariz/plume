"""A property documented on its own page (x-source-url): its fact cites that page, and the
page's guide lists it with the endpoint and path it belongs to (Meta's custom-data table)."""

from typing import Any

from plume.domain.knowledge.document import Document, DocumentKind, FieldLocation, FieldSpec
from plume.domain.knowledge.fact import facts_of
from plume.infrastructure.db.repos._codec import fields_from_json, fields_to_json
from plume.infrastructure.sources.stream_package import (
    _fields_by_page,
    _RefScope,
    _walk_fields,
    url_key,
)

PAGE = "https://developers.facebook.com/documentation/ads-commerce/conversions-api/parameters/custom-data"
OWN = "https://developers.facebook.com/documentation/ads-commerce/conversions-api/using-the-api"
BODY: dict[str, Any] = {"type": "object", "properties": {"data": {"type": "array", "items": {
    "type": "object", "properties": {
        "event_name": {"type": "string", "description": "The event."},
        "custom_data": {"type": "object", "properties": {
            "availability": {"type": "string", "x-source-url": PAGE, "x-table-row": "availability",
                             "description": "Value must be available_soon, for_rent, ..."},
            "currency": {"type": "string", "x-source-url": PAGE + "/", "description": "ISO code."},
        }},
    }}}}}  # fmt: skip


def _endpoint(path: str) -> Document:
    fields = tuple(_walk_fields(BODY, FieldLocation.BODY, "body.schema.json#",
                                scope=_RefScope(BODY, "body.schema.json")))  # fmt: skip
    return Document(doc_id=f"endpoint:POST~{path}", kind=DocumentKind.ENDPOINT, title="Events",
                    text="t", source_url=OWN, method="POST", path=path, fields=fields)  # fmt: skip


def test_a_fact_cites_the_page_that_documents_its_field() -> None:
    facts = {f.name: f for f in facts_of(_endpoint("/{pixel_id}/events"))}
    own = facts["data[].custom_data.availability"]
    assert own.owner_id == "endpoint:POST~/{pixel_id}/events"  # the endpoint stays the owner
    assert own.evidence.source_url == PAGE
    assert own.evidence.anchor is None  # the package pointer is no anchor of that page
    plain = facts["data[].event_name"]
    assert (plain.evidence.source_url, plain.evidence.anchor) == (
        OWN,
        "body.schema.json#/properties/data/items/properties/event_name",
    )


def test_the_page_guide_lists_the_fields_that_cite_it_once_each() -> None:
    by_page = _fields_by_page([_endpoint("/{pixel_id}/events"), _endpoint("/{app_id}/events")])
    fields = {f.name: f for f in by_page[url_key(PAGE)]}  # trailing slash: the same page
    assert set(fields) == {"data[].custom_data.availability", "data[].custom_data.currency"}
    avail = fields["data[].custom_data.availability"]
    assert avail.description == (
        "Value must be available_soon, for_rent, ... (in POST /{pixel_id}/events, "
        "POST /{app_id}/events: data[].custom_data.availability)")  # fmt: skip
    assert avail.pointer is None
    guide = Document(doc_id="guide:page-x", kind=DocumentKind.GUIDE, title="p", text="t",
                     source_url=PAGE, fields=by_page[url_key(PAGE)])  # fmt: skip
    ids = [f.fact_id for f in facts_of(guide)]
    assert len(ids) == len(set(ids)) == 2


def test_the_source_url_survives_the_store() -> None:
    spec = FieldSpec("a", FieldLocation.BODY, source_url=PAGE)
    assert fields_from_json(fields_to_json([spec]))[0].source_url == PAGE
    assert '"source_url"' not in fields_to_json([FieldSpec("b", FieldLocation.BODY)])  # old rows
