"""x-kariz-conflicts on a knowledge-export rule (rules.json) or page entry (index.json): shown
on every document the rule is shown on (its endpoints, its guide) and on the page's guide, the
same as on request.json / knowledge/<id>.json (Zalando rule r-2ca6a48ffd, "100 requests per
minute", attached to the attribute endpoints)."""

import json
from dataclasses import replace
from pathlib import Path

from plume.domain.knowledge.document import (
    CONFLICTS_KEY,
    Document,
    DocumentKind,
    conflicts_of,
)
from plume.infrastructure.sources import knowledge_export
from plume.infrastructure.sources.stream_package import _apply_export

PAGE = "https://developers.merchants.zalando.com/docs/product-attributes-api.html"
RATE = {
    "limit": "the attribute API's request rate",
    "statements": [
        {"where": "page:" + PAGE, "quote": "100 requests per minute"},
        {"where": "description", "quote": "Up to 600 requests per minute."},
    ],
}
SIZE = {
    "limit": "attribute values per request",
    "statements": [
        {"where": "page:" + PAGE, "quote": "at most 50 values"},
        {"where": "param:values", "quote": "max 100", "isExample": True},
    ],
}


def _export(root: Path) -> knowledge_export.KnowledgeExport:
    pages = root / "pages"
    pages.mkdir(parents=True)
    items = "\n".join(
        f'  - id: "get-attr-{n}"\n    kind: endpoint\n    method: GET\n'
        f'    path: "/attributes/{n}"\n    name: "Attribute {n}"\n    anchor: "#a{n}"'
        for n in (1, 2)
    )
    body = "Intro text about attributes.\n\n" + "".join(
        f'<a id="a{n}"></a>\n## Attribute {n}\nSection {n}.\n\n' for n in (1, 2)
    )
    (pages / "attrs.md").write_text(f'---\nsource: "{PAGE}"\nitems:\n{items}\n---\n{body}')
    index = {"schema": "plume.knowledge-export.v1", "complete": True,
             "pages": [{"file": "pages/attrs.md", "x-kariz-conflicts": [SIZE]}]}  # fmt: skip
    (root / "index.json").write_text(json.dumps(index))
    rule = {"id": "r-2ca6a48ffd", "scope": "resource", "type": "rate-limit",
            "text": "100 requests per minute", "quote": "100 requests per minute",
            "sourceUrl": PAGE, "resource": "Attribute",
            "endpointIds": ["get-attr-1", "get-attr-2"], "x-kariz-conflicts": [RATE]}  # fmt: skip
    (root / "rules.json").write_text(json.dumps({"rules": [rule]}))
    return knowledge_export.load(root)


def _endpoint(n: int) -> Document:
    return Document(
        doc_id=f"endpoint:GET~/attributes/{n}", kind=DocumentKind.ENDPOINT,
        title=f"Attribute {n}", text=f"# Attribute {n}", method="GET",
        path=f"/attributes/{n}", source_id=f"get-attr-{n}", resource="Attribute",
    )  # fmt: skip


def test_rule_and_page_conflicts_reach_every_document_showing_them(tmp_path: Path) -> None:
    export = _export(tmp_path / "knowledge-export")
    assert export.rules[0].conflicts == (RATE,)
    assert export.pages[0].conflicts == [SIZE]
    warnings: list[str] = []
    out = _apply_export([_endpoint(1), _endpoint(2)], export, warnings)
    showing_rule = [d for d in out if "100 requests per minute" in d.text]
    assert {d.doc_id for d in showing_rule} >= {"endpoint:GET~/attributes/1",
                                               "endpoint:GET~/attributes/2"}  # fmt: skip
    for d in showing_rule:
        limits = [c.limit for c in conflicts_of(d.raw)]
        assert limits.count("the attribute API's request rate") == 1, d.doc_id
    [page_guide] = [d for d in out if d.kind is DocumentKind.GUIDE and d.source_url == PAGE]
    limits = {c.limit for c in conflicts_of(page_guide.raw)}
    assert "attribute values per request" in limits
    [rate] = [c for c in conflicts_of(out[0].raw) if c.limit.endswith("request rate")]
    assert rate.text.splitlines()[1] == f'- page:{PAGE}: "100 requests per minute"'


def test_entries_without_conflicts_leave_raw_unchanged(tmp_path: Path) -> None:
    export = _export(tmp_path / "knowledge-export")
    export.rules[0] = replace(export.rules[0], conflicts=())
    export.pages[0].conflicts = []
    out = _apply_export([_endpoint(1), _endpoint(2)], export, [])
    assert all(CONFLICTS_KEY not in (d.raw or {}) for d in out)
