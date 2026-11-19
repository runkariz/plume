"""A rule stated on several pages (stream merges repeats): sourceUrl + sourceUrls. It goes to
every page it names, its resource fallback covers all those pages, and the documents that
carry it cite every page (sourceUrl first). Rules without sourceUrls are unchanged."""

import json
import shutil
from pathlib import Path

from plume.application.reader import links
from plume.domain.knowledge.document import RULE_SOURCES_KEY, Document, DocumentKind
from plume.infrastructure.sources import knowledge_export
from plume.infrastructure.sources.knowledge_export import ExportPage, KnowledgeExport, Rule
from plume.infrastructure.sources.stream_package import _apply_export

A = "https://d.example/docs/orders"
B = "https://d.example/docs/returns"
C = "https://d.example/docs/%C3%BCr%C3%BCn"  # matched loosely to the decoded page URL


def _page(url: str, items: list[str]) -> ExportPage:
    return ExportPage(
        file=url.rsplit("/", 1)[-1] + ".md", source_url=url, title=url.rsplit("/", 1)[-1],
        intro="intro", items=[(i, f"GET {i}") for i in items],
    )  # fmt: skip


def _endpoint(source_id: str, resource: str) -> Document:
    return Document(
        doc_id=f"endpoint:GET~/{source_id}", kind=DocumentKind.ENDPOINT, title=source_id,
        text=f"# {source_id}", method="GET", path=f"/{source_id}", source_id=source_id,
        resource=resource,
    )  # fmt: skip


def _rule(rule_id: str, scope: str, url: str, others: tuple[str, ...] = ()) -> Rule:
    return Rule(
        rule_id, scope, "rule", f"text {rule_id}", "quote", url, None, None,
        "Order" if scope == "resource" else None, source_urls=others,
    )  # fmt: skip


PAGES = [
    _page(A, ["get-a1", "get-a2"]),
    _page(B, ["get-b1", "get-b2"]),
    _page("https://d.example/docs/ürün", ["get-c1", "get-c2"]),
]
DOCS = [
    _endpoint("get-a1", "Order"),
    _endpoint("get-a2", "Customer"),
    _endpoint("get-b1", "Order"),
    _endpoint("get-b2", "Order"),
    _endpoint("get-c1", "Order"),
    _endpoint("get-c2", "Customer"),
]


def _apply(rules: list[Rule]) -> dict[str, Document]:
    export = KnowledgeExport(complete=True, pages=PAGES, rules=rules, gold_path=None)
    warnings: list[str] = []
    out = {d.doc_id: d for d in _apply_export(list(DOCS), export, warnings)}
    assert warnings == []
    return out


def test_a_merged_rule_goes_to_every_page_it_names() -> None:
    out = _apply([_rule("merged", "page", A, (B, C))])
    guides = {d.source_url: d for d in out.values() if d.kind is DocumentKind.GUIDE}
    assert set(guides) == {A, B, "https://d.example/docs/ürün"}
    for guide in guides.values():
        assert "text merged" in guide.text
        assert links.rule_sources(guide) == [{"ruleId": "merged", "urls": [A, B, C]}]


def test_the_resource_fallback_covers_all_its_pages() -> None:
    out = _apply([_rule("res", "resource", A, (B, C))])
    with_rule = sorted(k for k, d in out.items() if "## Rules for this resource" in d.text)
    assert with_rule == [  # the Order endpoints of all three pages, not the Customer ones
        "endpoint:GET~/get-a1",
        "endpoint:GET~/get-b1",
        "endpoint:GET~/get-b2",
        "endpoint:GET~/get-c1",
    ]
    cited = links.rule_sources(out["endpoint:GET~/get-b2"])
    assert cited == [{"ruleId": "res", "urls": [A, B, C]}]


def test_rules_on_one_page_carry_no_extra_citation() -> None:
    out = _apply([_rule("single", "page", A), _rule("res", "resource", B)])
    assert all(RULE_SOURCES_KEY not in (d.raw or {}) for d in out.values())
    assert all(links.rule_sources(d) == [] for d in out.values())


def test_source_urls_are_read_from_rules_json(packages: Path, tmp_path: Path) -> None:
    root = tmp_path / "export"
    shutil.copytree(packages / "woo-mini" / "knowledge-export", root)
    data = json.loads((root / "rules.json").read_text())
    data["rules"][0]["sourceUrls"] = [B, " ", B, 7]
    (root / "rules.json").write_text(json.dumps(data))
    rules = knowledge_export.load(root).rules
    first = rules[0]
    assert first.source_urls == (B,)
    assert first.urls == (first.source_url, B)
    assert rules[1].source_urls == ()
